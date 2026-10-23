"""Orquestração de uma importação: registro, trava, validação, gravação, recálculo e relatório."""

from __future__ import annotations

import time
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from ..config import config
from ..db import conexao
from . import instituicoes, leads
from .leitor import Arquivo, ArquivoInvalido, ler
from .ocorrencias import Ocorrencias

# Identificador da trava (pg_advisory_xact_lock) que impede importações simultâneas.
TRAVA_IMPORTACAO = 724_310_001


class ImportacaoRejeitada(Exception):
    def __init__(self, mensagem: str, importacao_id: int | None = None):
        super().__init__(mensagem)
        self.importacao_id = importacao_id


def atualizar_camada_analitica(conn: psycopg.Connection, importacao_id: int | None) -> None:
    """Recalcula as visões do painel, grava o snapshot de métricas e avança a versão da base."""
    conn.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY ana.mv_aluno")
    conn.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY ana.mv_interesse")
    if importacao_id is not None:
        conn.execute("""
            INSERT INTO ana.snapshot_metrica (importacao_id, dimensao, chave, rotulo, interesses, alunos)
            SELECT %(imp)s, 'total', 'total', 'Total', count(*), count(DISTINCT aluno_id) FROM ana.mv_interesse
            UNION ALL
            SELECT %(imp)s, 'instituicao', m.instituicao_id::text, max(i.nome), count(*), count(DISTINCT m.aluno_id)
            FROM ana.mv_interesse m JOIN core.instituicao i ON i.id = m.instituicao_id GROUP BY m.instituicao_id
            UNION ALL
            SELECT %(imp)s, 'grupo', m.grupo_id::text, max(g.nome), count(*), count(DISTINCT m.aluno_id)
            FROM ana.mv_interesse m JOIN core.grupo_educacional g ON g.id = m.grupo_id GROUP BY m.grupo_id
            UNION ALL
            SELECT %(imp)s, 'uf', m.uf, m.uf, count(*), count(DISTINCT m.aluno_id)
            FROM ana.mv_interesse m WHERE m.uf IS NOT NULL GROUP BY m.uf
            UNION ALL
            SELECT %(imp)s, 'cidade', m.cidade_id::text, max(c.nome || ' (' || c.uf || ')'), count(*),
                   count(DISTINCT m.aluno_id)
            FROM ana.mv_interesse m JOIN core.cidade c ON c.id = m.cidade_id GROUP BY m.cidade_id
            UNION ALL
            SELECT %(imp)s, 'curso', x.curso_id::text, max(c.nome), 0, count(*)
            FROM ana.mv_aluno a CROSS JOIN LATERAL unnest(a.cursos) AS x(curso_id)
            JOIN core.curso c ON c.id = x.curso_id GROUP BY x.curso_id""", {"imp": importacao_id})
    conn.execute("""UPDATE imp.estado SET versao = versao + 1,
                    ultima_importacao = COALESCE(%s, ultima_importacao), atualizado_em = now()""",
                 (importacao_id,))


def _registrar_inicio(arquivo: Arquivo, modo: str, usuario_id: int | None) -> int:
    with conexao() as conn:
        return conn.execute(
            """INSERT INTO imp.importacao (fonte, modo, arquivo_nome, arquivo_sha256, arquivo_bytes, usuario_id)
               VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
            (arquivo.fonte, modo, arquivo.nome, arquivo.sha256, arquivo.bytes, usuario_id),
        ).fetchone()["id"]


def _gravar_ocorrencias(conn: psycopg.Connection, importacao_id: int, oc: Ocorrencias) -> None:
    with conn.cursor().copy(
        "COPY imp.importacao_ocorrencia (importacao_id, severidade, codigo, linha, coluna, valor, mensagem) "
        "FROM STDIN"
    ) as cp:
        for d in oc.detalhes:
            cp.write_row((importacao_id, *d))


def _finalizar(importacao_id: int, status: str, inicio: float, oc: Ocorrencias, resumo: dict,
               mensagem: str | None, linhas_lidas: int, conn: psycopg.Connection | None = None) -> None:
    sql = """UPDATE imp.importacao SET status = %s, concluido_em = now(), duracao_ms = %s, linhas_lidas = %s,
                    linhas_ignoradas = %s, total_erros = %s, total_avisos = %s, resumo = %s, mensagem = %s
             WHERE id = %s"""
    params = (status, int((time.monotonic() - inicio) * 1000), linhas_lidas, len(oc.linhas_ignoradas),
              oc.total_erros, oc.total_avisos, Jsonb({**resumo, "ocorrencias": oc.resumo()}), mensagem,
              importacao_id)
    if conn is not None:
        conn.execute(sql, params)
        return
    with conexao() as c:
        c.execute(sql, params)
        _gravar_ocorrencias(c, importacao_id, oc)


def importar(caminho: Path, nome_original: str | None = None, modo: str = "completo",
             usuario_id: int | None = None, forcar: bool = False) -> dict:
    """Importa uma planilha. Devolve o relatório (linha de imp.importacao).

    Levanta ArquivoInvalido (nada registrado: o arquivo nem foi reconhecido) ou
    ImportacaoRejeitada (registrada com status 'rejeitada' e o motivo).
    """
    if modo not in {"completo", "incremental"}:
        raise ValueError("modo deve ser 'completo' ou 'incremental'")
    inicio = time.monotonic()
    arquivo = ler(Path(caminho), nome_original)

    if not forcar:
        with conexao() as conn:
            anterior = conn.execute(
                "SELECT id, concluido_em FROM imp.importacao WHERE arquivo_sha256 = %s AND status = 'concluida' "
                "ORDER BY id DESC LIMIT 1", (arquivo.sha256,)).fetchone()
        if anterior:
            raise ImportacaoRejeitada(
                f"Este arquivo já foi importado (importação #{anterior['id']}, "
                f"{anterior['concluido_em']:%d/%m/%Y %H:%M}). Nada a atualizar.", anterior["id"])

    importacao_id = _registrar_inicio(arquivo, modo, usuario_id)
    oc = Ocorrencias()
    for aba in arquivo.abas:
        for coluna in aba.colunas_desconhecidas:
            oc.aviso("coluna_ignorada", f"Coluna não reconhecida na aba '{aba.nome}'; ignorada.", aba.linha_cabecalho,
                     coluna)
    resumo: dict = {"abas": {a.nome: a.esquema.nome for a in arquivo.abas},
                    "abas_ignoradas": arquivo.abas_ignoradas}
    linhas_lidas = sum(len(a.dados) for a in arquivo.abas)

    try:
        if arquivo.fonte == "leads":
            preparado = leads.preparar(arquivo.abas[0], oc)
        with conexao() as conn:
            obtida = conn.execute("SELECT pg_try_advisory_xact_lock(%s) AS ok", (TRAVA_IMPORTACAO,)).fetchone()["ok"]
            if not obtida:
                raise ImportacaoRejeitada("Outra importação está em andamento. Tente novamente em alguns minutos.")
            if arquivo.fonte == "leads":
                resumo.update(leads.gravar(conn, importacao_id, modo, preparado, forcar, config().limite_remocao))
            else:
                resumo.update(instituicoes.importar(conn, arquivo, oc))
            _gravar_ocorrencias(conn, importacao_id, oc)
            atualizar_camada_analitica(conn, importacao_id)
            conn.execute("INSERT INTO seg.auditoria (usuario_id, acao, alvo, detalhes) VALUES (%s, %s, %s, %s)",
                         (usuario_id, "importacao", f"importacao:{importacao_id}",
                          Jsonb({"arquivo": arquivo.nome, "fonte": arquivo.fonte, "modo": modo, "forcar": forcar})))
            _finalizar(importacao_id, "concluida", inicio, oc, resumo, None, linhas_lidas, conn)
    except (leads.RemocaoExcessiva, ImportacaoRejeitada, ArquivoInvalido) as e:
        _finalizar(importacao_id, "rejeitada", inicio, oc, resumo, str(e), linhas_lidas)
        raise ImportacaoRejeitada(str(e), importacao_id) from e
    except Exception as e:
        _finalizar(importacao_id, "falhou", inicio, oc, resumo, f"Erro inesperado: {e}", linhas_lidas)
        raise
    return relatorio(importacao_id)


def relatorio(importacao_id: int) -> dict:
    with conexao() as conn:
        linha = conn.execute("SELECT * FROM imp.importacao WHERE id = %s", (importacao_id,)).fetchone()
    if linha is None:
        raise KeyError(importacao_id)
    return dict(linha)
