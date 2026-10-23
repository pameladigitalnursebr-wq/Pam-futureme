"""Revisão de instituições: nomes suspeitos, não verificados e unificação de grafias.

Unificar é a única forma de ligar dois nomes diferentes. É sempre decisão humana,
fica na auditoria e vale para todas as importações futuras (via core.instituicao_alias).
"""

from __future__ import annotations

from typing import Any

import psycopg

from .importacao.servico import TRAVA_IMPORTACAO, atualizar_camada_analitica
from .seguranca.usuarios import auditar


def pendentes(conn: psycopg.Connection, limite: int = 50, deslocamento: int = 0) -> dict[str, Any]:
    """Instituições a revisar (não verificadas que vieram só dos leads, ou suspeitas), com sugestões."""
    linhas = conn.execute("""
        WITH contagem AS (
            SELECT instituicao_id, count(*) AS interesses FROM core.interesse WHERE ativo GROUP BY instituicao_id
        )
        SELECT i.id, i.nome, i.origem, i.qualidade, COALESCE(c.interesses, 0) AS interesses,
               count(*) OVER () AS total
        FROM core.instituicao i LEFT JOIN contagem c ON c.instituicao_id = i.id
        WHERE NOT i.verificada AND (i.origem = 'leads' OR i.qualidade = 'suspeita')
        ORDER BY COALESCE(c.interesses, 0) DESC, i.nome
        LIMIT %s OFFSET %s""", (limite, deslocamento)).fetchall()
    itens = []
    for l in linhas:
        item = dict(l)
        item.pop("total")
        item["sugestoes"] = sugestoes(conn, l["id"])
        itens.append(item)
    return {"total": linhas[0]["total"] if linhas else 0, "itens": itens}


def sugestoes(conn: psycopg.Connection, instituicao_id: int, limite: int = 3) -> list[dict]:
    """Instituições com nome parecido (trigramas). Só sugestão: nada é unificado sozinho."""
    return [dict(r) for r in conn.execute("""
        SELECT o.id, o.nome, round(similarity(o.nome_norm, i.nome_norm)::numeric, 2) AS semelhanca
        FROM core.instituicao i JOIN core.instituicao o
          ON o.id <> i.id AND o.nome_norm %% i.nome_norm AND o.qualidade = 'ok'
        WHERE i.id = %s
        ORDER BY similarity(o.nome_norm, i.nome_norm) DESC LIMIT %s""", (instituicao_id, limite))]


def marcar(conn: psycopg.Connection, instituicao_id: int, usuario_id: int, *, verificada: bool | None = None,
           qualidade: str | None = None) -> None:
    if qualidade is not None and qualidade not in {"ok", "suspeita"}:
        raise ValueError("qualidade deve ser 'ok' ou 'suspeita'")
    conn.execute("""UPDATE core.instituicao SET verificada = COALESCE(%s, verificada),
                    qualidade = COALESCE(%s, qualidade), atualizado_em = now() WHERE id = %s""",
                 (verificada, qualidade, instituicao_id))
    auditar(conn, usuario_id, "instituicao_marcada", f"instituicao:{instituicao_id}",
            {"verificada": verificada, "qualidade": qualidade})
    if qualidade is not None:
        atualizar_camada_analitica(conn, None)


def unificar(conn: psycopg.Connection, origem_id: int, destino_id: int, usuario_id: int) -> dict[str, Any]:
    """Move interesses, volumes e grafias da instituição 'origem' para 'destino' e remove a origem."""
    if origem_id == destino_id:
        raise ValueError("Origem e destino são a mesma instituição.")
    conn.execute("SELECT pg_advisory_xact_lock(%s)", (TRAVA_IMPORTACAO,))
    nomes = {r["id"]: r["nome"] for r in conn.execute(
        "SELECT id, nome FROM core.instituicao WHERE id = ANY(%s)", ([origem_id, destino_id],))}
    if len(nomes) != 2:
        raise ValueError("Instituição não encontrada.")
    movidos = conn.execute("UPDATE core.interesse SET instituicao_id = %s WHERE instituicao_id = %s",
                           (destino_id, origem_id)).rowcount
    conn.execute("""
        INSERT INTO core.volume_instituicao_anual (instituicao_id, uf, ano, total)
        SELECT %s, uf, ano, total FROM core.volume_instituicao_anual WHERE instituicao_id = %s
        ON CONFLICT (instituicao_id, uf, ano) DO UPDATE
            SET total = core.volume_instituicao_anual.total + EXCLUDED.total""", (destino_id, origem_id))
    conn.execute("""UPDATE core.instituicao_alias SET instituicao_id = %s, origem = 'unificacao'
                    WHERE instituicao_id = %s""", (destino_id, origem_id))
    conn.execute("DELETE FROM core.instituicao WHERE id = %s", (origem_id,))
    conn.execute("UPDATE core.instituicao SET verificada = true, atualizado_em = now() WHERE id = %s", (destino_id,))
    auditar(conn, usuario_id, "instituicao_unificada", f"instituicao:{destino_id}",
            {"origem_id": origem_id, "origem": nomes[origem_id], "destino": nomes[destino_id],
             "interesses_movidos": movidos})
    atualizar_camada_analitica(conn, None)
    return {"origem": nomes[origem_id], "destino": nomes[destino_id], "interesses_movidos": movidos}
