"""Métricas do painel: a única implementação usada pelo painel web, pela API e pelo Claude (MCP).

Medidas
- alunos:      alunos distintos no recorte (um aluno conta uma vez, mesmo com 3 opções)
- interesses:  opções de instituição (aluno × posição); um aluno gera até 3
"""

from __future__ import annotations

from typing import Any

import psycopg

from .. import normalizacao as norm
from . import cache
from .filtros import ALUNO, DIMENSOES, INTERESSE, Dimensao, Filtros

AVISO_CURSO_INSTITUICAO = (
    "Curso e instituição são escolhas independentes do aluno: o resultado conta alunos que têm o curso "
    "no pódio E escolheram a instituição, não necessariamente aquele curso naquela instituição."
)

# Dimensões oferecidas na busca rápida, na ordem em que aparecem.
DIMENSOES_BUSCA = ("instituicao", "curso", "cidade", "uf", "regiao_ensino", "escola", "grupo")


def _avisos(f: Filtros) -> list[str]:
    avisos = []
    if "curso" in f.valores and f.tem_nivel_interesse:
        avisos.append(AVISO_CURSO_INSTITUICAO)
    return avisos


# ---------------------------------------------------------------------------
# Resumo
# ---------------------------------------------------------------------------

def resumo(conn: psycopg.Connection, f: Filtros) -> dict[str, Any]:
    return cache.obter(conn, ("resumo", f.chave_cache()), lambda: _resumo(conn, f))


def _resumo(conn: psycopg.Connection, f: Filtros) -> dict[str, Any]:
    w_a, p_a = f.where_alunos("m")
    w_i, p_i = f.where(INTERESSE, "m")
    a = conn.execute(f"""
        SELECT count(*) AS alunos, count(DISTINCT uf) AS estados, count(DISTINCT cidade_id) AS cidades,
               count(DISTINCT escola_id) AS escolas
        FROM ana.mv_aluno m WHERE {w_a}""", p_a).fetchone()
    c = conn.execute(f"""
        SELECT count(DISTINCT x.v) AS cursos FROM ana.mv_aluno m CROSS JOIN LATERAL unnest(m.cursos) AS x(v)
        WHERE {w_a}""", p_a).fetchone()
    i = conn.execute(f"""
        SELECT count(*) AS interesses, count(DISTINCT aluno_id) AS alunos_com_interesse,
               count(DISTINCT instituicao_id) AS instituicoes
        FROM ana.mv_interesse m WHERE {w_i}""", p_i).fetchone()
    return {**a, **c, **i, "filtros": f.como_dict(), "avisos": _avisos(f)}


# ---------------------------------------------------------------------------
# Ranking / distribuição
# ---------------------------------------------------------------------------

def _expr(dim: Dimensao) -> tuple[str, str]:
    """(expressão da chave, FROM extra) para a dimensão."""
    if dim.vetor:
        return "x.v", f" CROSS JOIN LATERAL unnest(m.{dim.coluna}) AS x(v)"
    return f"m.{dim.coluna}", ""


def rotulos(conn: psycopg.Connection, dim: Dimensao, chaves: list[Any]) -> dict[Any, str]:
    if not chaves:
        return {}
    if dim.tabela:
        linhas = conn.execute(
            f"SELECT {dim.chave_tabela} AS k, {dim.rotulo} AS r FROM {dim.tabela} WHERE {dim.chave_tabela} = ANY(%s)",
            (chaves,)).fetchall()
        return {l["k"].strip() if isinstance(l["k"], str) else l["k"]: l["r"] for l in linhas}
    if dim.nome == "posicao":
        return {k: f"{k}ª opção" for k in chaves}
    if dim.tipo == "bool":
        return {k: "Sim" if k else "Não" for k in chaves}
    return {k: str(k) for k in chaves}


def ranking(conn: psycopg.Connection, dimensao: str, f: Filtros, limite: int = 10, deslocamento: int = 0,
            somente: list[Any] | None = None) -> dict[str, Any]:
    limite = max(1, min(int(limite), 500))
    chave_cache = ("ranking", dimensao, f.chave_cache(), limite, deslocamento, repr(somente))
    return cache.obter(conn, chave_cache, lambda: _ranking(conn, dimensao, f, limite, deslocamento, somente))


def _ranking(conn: psycopg.Connection, dimensao: str, f: Filtros, limite: int, deslocamento: int,
             somente: list[Any] | None) -> dict[str, Any]:
    dim = DIMENSOES.get(dimensao)
    if dim is None:
        raise ValueError(f"Dimensão desconhecida: '{dimensao}'. Use uma de: {', '.join(DIMENSOES)}.")
    k, juncao = _expr(dim)
    restricao, p_restricao = "", []
    if somente is not None:
        restricao = f" AND {k} = ANY(%s)"
        p_restricao = [somente]

    w_i, p_i = f.where(INTERESSE, "m")
    if dim.nivel == INTERESSE:
        linhas = conn.execute(f"""
            SELECT {k} AS chave, count(*) AS interesses, count(DISTINCT m.aluno_id) AS alunos,
                   count(*) OVER () AS total_valores
            FROM ana.mv_interesse m{juncao}
            WHERE {w_i} AND {k} IS NOT NULL{restricao}
            GROUP BY {k} ORDER BY alunos DESC, interesses DESC, chave LIMIT %s OFFSET %s""",
            [*p_i, *p_restricao, limite, deslocamento]).fetchall()
        itens = [dict(l) for l in linhas]
    else:
        w_a, p_a = f.where_alunos("m")
        linhas = conn.execute(f"""
            SELECT {k} AS chave, count(*) AS alunos, count(*) OVER () AS total_valores
            FROM ana.mv_aluno m{juncao}
            WHERE {w_a} AND {k} IS NOT NULL{restricao}
            GROUP BY {k} ORDER BY alunos DESC, chave LIMIT %s OFFSET %s""",
            [*p_a, *p_restricao, limite, deslocamento]).fetchall()
        itens = [dict(l) for l in linhas]
        chaves = [i["chave"] for i in itens]
        interesses = {}
        if chaves:
            interesses = {l["chave"]: l["n"] for l in conn.execute(f"""
                SELECT {k} AS chave, count(*) AS n FROM ana.mv_interesse m{juncao}
                WHERE {w_i} AND {k} = ANY(%s) GROUP BY {k}""", [*p_i, chaves]).fetchall()}
        for i in itens:
            i["interesses"] = interesses.get(i["chave"], 0)

    total_valores = itens[0]["total_valores"] if itens else 0
    base = resumo(conn, f)["alunos"]
    nomes = rotulos(conn, dim, [i["chave"] for i in itens])
    for i in itens:
        i.pop("total_valores", None)
        i["rotulo"] = nomes.get(i["chave"], str(i["chave"]))
        i["percentual"] = round(100 * i["alunos"] / base, 1) if base else 0.0
    return {"dimensao": dimensao, "titulo": dim.titulo, "itens": itens, "total_valores": total_valores,
            "alunos_no_recorte": base, "filtros": f.como_dict(), "avisos": _avisos(f)}


# ---------------------------------------------------------------------------
# Valores de dimensão (autocompletar) e busca rápida
# ---------------------------------------------------------------------------

def valores(conn: psycopg.Connection, dimensao: str, termo: str = "", limite: int = 20) -> list[dict[str, Any]]:
    """Valores de uma dimensão que contêm o termo, com o número de alunos (base inteira)."""
    return cache.obter(conn, ("valores", dimensao, termo, limite), lambda: _valores(conn, dimensao, termo, limite))


def _valores(conn: psycopg.Connection, dimensao: str, termo: str, limite: int) -> list[dict[str, Any]]:
    dim = DIMENSOES.get(dimensao)
    if dim is None:
        raise ValueError(f"Dimensão desconhecida: '{dimensao}'.")
    k = norm.chave(termo or "")
    vazio = Filtros(incluir_suspeitas=True)
    if not k:
        return ranking(conn, dimensao, vazio, limite)["itens"]

    if dim.tabela:
        campo = dim.busca if dim.busca == "nome_norm" else f"upper(unaccent({dim.busca}))"
        # Instituição: só a sigla conta como exata ("unip"); um nome igual ao termo costuma ser texto livre
        # digitado pelo aluno ("campinas") e não deve passar à frente das instituições reais.
        exato = {"instituicao": "sigla = %(k)s",
                 "curso": "nome_norm = %(k)s OR nome_norm LIKE %(k)s || ' - %%'",
                 "uf": "sigla = %(k)s OR upper(unaccent(nome)) = %(k)s"}.get(dim.nome, f"{campo} = %(k)s")
        candidatos = conn.execute(f"""
            SELECT {dim.chave_tabela} AS chave, ({exato}) AS exato
            FROM {dim.tabela} WHERE {campo} LIKE %(padrao)s
            ORDER BY ({exato}) DESC, similarity({campo}, %(k)s) DESC LIMIT 300""",
            {"k": k, "padrao": f"%{k}%"}).fetchall()
        if not candidatos:
            return []
        exatos = {c["chave"].strip() if isinstance(c["chave"], str) else c["chave"]
                  for c in candidatos if c["exato"]}
        chaves = [c["chave"].strip() if isinstance(c["chave"], str) else c["chave"] for c in candidatos]
        itens = ranking(conn, dimensao, vazio, limite=len(chaves), somente=chaves)["itens"]
        encontrados = {i["chave"] for i in itens}
        if dim.nome == "instituicao":   # instituição sem interessados ainda é resposta válida
            nomes = rotulos(conn, dim, [c for c in chaves if c not in encontrados])
            itens += [{"chave": c, "rotulo": r, "alunos": 0, "interesses": 0, "percentual": 0.0}
                      for c, r in nomes.items()]
        for i in itens:
            i["exato"] = i["chave"] in exatos
        itens.sort(key=lambda i: (not i["exato"], -i["alunos"]))
        return itens[:limite]

    itens = ranking(conn, dimensao, vazio, limite=500)["itens"]
    achados = [{**i, "exato": norm.chave(i["rotulo"]) == k or norm.chave(i["chave"]) == k}
               for i in itens if k in (norm.chave(i["rotulo"]) or "")]
    achados.sort(key=lambda i: not i["exato"])
    return achados[:limite]


def busca_rapida(conn: psycopg.Connection, termo: str, limite: int = 5) -> dict[str, Any]:
    """Procura o termo em instituições, cursos, cidades, escolas... ao mesmo tempo.

    Para frases como 'medicina campinas', procura também cada palavra separadamente.
    """
    termo = (termo or "").strip()
    palavras = [p for p in termo.split() if len(norm.chave(p) or "") >= 3]
    grupos = []
    for nome in DIMENSOES_BUSCA:
        itens = valores(conn, nome, termo, limite)
        if not itens and len(palavras) > 1:
            vistos: dict[Any, dict] = {}
            for palavra in palavras:
                for i in valores(conn, nome, palavra, limite):
                    vistos.setdefault(i["chave"], i)
            itens = sorted(vistos.values(), key=lambda i: -i["alunos"])[:limite]
        if itens:
            grupos.append({"dimensao": nome, "titulo": DIMENSOES[nome].titulo, "itens": itens})
    return {"termo": termo, "grupos": grupos}


# ---------------------------------------------------------------------------
# Resultado detalhado (um aluno por linha)
# ---------------------------------------------------------------------------

ORDENACOES = {
    "recentes": "m.cadastrado_em DESC NULLS LAST, m.aluno_id",
    "antigos": "m.cadastrado_em ASC NULLS LAST, m.aluno_id",
    "cidade": "c.nome NULLS LAST, m.aluno_id",
    "escola": "e.nome NULLS LAST, m.aluno_id",
}

COLUNAS_DETALHE = {
    "aluno": "Aluno (ID)", "cadastrado_em": "Cadastro", "uf": "UF", "cidade": "Cidade",
    "regiao_ensino": "Região de ensino", "escola": "Escola", "cursos": "Cursos (pódio)",
    "modalidades": "Modalidades", "opcao_1": "1ª opção", "opcao_2": "2ª opção", "opcao_3": "3ª opção",
    "faixa_etaria": "Faixa etária", "aceita_comunicados": "Aceita comunicados",
}
COLUNAS_PESSOAIS = {"genero": "Gênero", "data_nascimento": "Data de nascimento"}


def detalhe(conn: psycopg.Connection, f: Filtros, pagina: int = 1, por_pagina: int = 50,
            ordenar: str = "recentes", dados_pessoais: bool = False) -> dict[str, Any]:
    pagina = max(1, int(pagina))
    por_pagina = max(1, min(int(por_pagina), 1000))
    ordem = ORDENACOES.get(ordenar, ORDENACOES["recentes"])
    w_a, p_a = f.where_alunos("m")
    total = resumo(conn, f)["alunos"]
    pessoais = ", a.data_nascimento, m.genero" if dados_pessoais else ""
    linhas = conn.execute(f"""
        SELECT m.aluno_id, m.cadastrado_em, m.uf, c.nome AS cidade, r.nome AS regiao_ensino, e.nome AS escola,
               (SELECT string_agg(cu.nome, ' | ' ORDER BY u.ord) FROM unnest(m.cursos) WITH ORDINALITY u(id, ord)
                  JOIN core.curso cu ON cu.id = u.id) AS cursos,
               (SELECT string_agg(mo.nome, ', ' ORDER BY u.ord) FROM unnest(m.modalidades) WITH ORDINALITY u(id, ord)
                  JOIN core.modalidade mo ON mo.id = u.id) AS modalidades,
               op.opcao_1, op.opcao_2, op.opcao_3, m.faixa_etaria, m.aceita_comunicados{pessoais}
        FROM ana.mv_aluno m
        LEFT JOIN core.cidade c ON c.id = m.cidade_id
        LEFT JOIN core.regiao_ensino r ON r.id = m.regiao_ensino_id
        LEFT JOIN core.escola e ON e.id = m.escola_id
        LEFT JOIN core.aluno a ON a.id = m.aluno_id
        LEFT JOIN LATERAL (
            SELECT max(i.nome) FILTER (WHERE x.posicao = 1) AS opcao_1,
                   max(i.nome) FILTER (WHERE x.posicao = 2) AS opcao_2,
                   max(i.nome) FILTER (WHERE x.posicao = 3) AS opcao_3
            FROM core.interesse x JOIN core.instituicao i ON i.id = x.instituicao_id
            WHERE x.aluno_id = m.aluno_id AND x.ativo) op ON true
        WHERE {w_a}
        ORDER BY {ordem} LIMIT %s OFFSET %s""", [*p_a, por_pagina, (pagina - 1) * por_pagina]).fetchall()
    itens = []
    for l in linhas:
        item = dict(l)
        aluno_id = str(item.pop("aluno_id"))
        # O ID completo identifica o aluno na plataforma: só com permissão de dados pessoais.
        item = {"aluno": aluno_id if dados_pessoais else aluno_id[:8] + "…", **item}
        itens.append(item)
    colunas = {**COLUNAS_DETALHE, **(COLUNAS_PESSOAIS if dados_pessoais else {})}
    return {"total": total, "pagina": pagina, "por_pagina": por_pagina,
            "paginas": (total + por_pagina - 1) // por_pagina, "colunas": colunas, "itens": itens,
            "filtros": f.como_dict(), "avisos": _avisos(f)}


# ---------------------------------------------------------------------------
# Histórico e situação da base
# ---------------------------------------------------------------------------

def historico_anual(conn: psycopg.Connection, dimensao: str, chave: int) -> dict[str, Any]:
    """Totais por ano (Base 1, 2023 em diante) para uma instituição ou curso."""
    tabelas = {"instituicao": ("core.volume_instituicao_anual", "instituicao_id"),
               "curso": ("core.volume_curso_anual", "curso_id")}
    if dimensao not in tabelas:
        raise ValueError("Histórico anual disponível para 'instituicao' e 'curso'.")
    tabela, coluna = tabelas[dimensao]
    linhas = conn.execute(f"""
        SELECT ano, uf, total FROM {tabela} WHERE {coluna} = %s ORDER BY ano, uf""", (chave,)).fetchall()
    por_ano: dict[int, int] = {}
    for l in linhas:
        por_ano[l["ano"]] = por_ano.get(l["ano"], 0) + l["total"]
    nome = rotulos(conn, DIMENSOES[dimensao], [chave]).get(chave)
    return {"dimensao": dimensao, "chave": chave, "rotulo": nome,
            "por_ano": [{"ano": a, "total": t} for a, t in sorted(por_ano.items())],
            "por_ano_uf": [dict(l) for l in linhas],
            "fonte": "Base de instituições (totais anuais por UF de origem do lead)"}


def evolucao(conn: psycopg.Connection, dimensao: str, chave: str) -> dict[str, Any]:
    """Série das métricas a cada importação (snapshots)."""
    linhas = conn.execute("""
        SELECT i.id AS importacao, i.concluido_em, s.rotulo, s.interesses, s.alunos
        FROM ana.snapshot_metrica s JOIN imp.importacao i ON i.id = s.importacao_id
        WHERE s.dimensao = %s AND s.chave = %s ORDER BY i.id""", (dimensao, str(chave))).fetchall()
    return {"dimensao": dimensao, "chave": chave, "serie": [dict(l) for l in linhas]}


def comparar_importacoes(conn: psycopg.Connection, dimensao: str, anterior: int | None = None,
                         atual: int | None = None, limite: int = 20) -> dict[str, Any]:
    """Maiores variações de alunos entre dois snapshots (padrão: as duas últimas importações de leads)."""
    if anterior is None or atual is None:
        ids = [r["id"] for r in conn.execute("""
            SELECT DISTINCT i.id FROM imp.importacao i JOIN ana.snapshot_metrica s ON s.importacao_id = i.id
            WHERE i.status = 'concluida' AND i.fonte = 'leads' ORDER BY i.id DESC LIMIT 2""").fetchall()]
        if len(ids) < 2:
            return {"dimensao": dimensao, "itens": [],
                    "mensagem": "A comparação precisa de pelo menos duas importações de leads."}
        atual, anterior = ids[0], ids[1]
    linhas = conn.execute("""
        SELECT COALESCE(b.chave, a.chave) AS chave, COALESCE(b.rotulo, a.rotulo) AS rotulo,
               COALESCE(a.alunos, 0) AS alunos_antes, COALESCE(b.alunos, 0) AS alunos_depois,
               COALESCE(b.alunos, 0) - COALESCE(a.alunos, 0) AS variacao
        FROM (SELECT * FROM ana.snapshot_metrica WHERE importacao_id = %(a)s AND dimensao = %(d)s) a
        FULL JOIN (SELECT * FROM ana.snapshot_metrica WHERE importacao_id = %(b)s AND dimensao = %(d)s) b
          ON a.chave = b.chave
        ORDER BY abs(COALESCE(b.alunos, 0) - COALESCE(a.alunos, 0)) DESC LIMIT %(l)s""",
        {"a": anterior, "b": atual, "d": dimensao, "l": limite}).fetchall()
    return {"dimensao": dimensao, "anterior": anterior, "atual": atual, "itens": [dict(l) for l in linhas]}


def status_base(conn: psycopg.Connection) -> dict[str, Any]:
    estado = conn.execute("SELECT versao, atualizado_em FROM imp.estado").fetchone()
    ultimas = conn.execute("""
        SELECT DISTINCT ON (fonte) fonte, id, arquivo_nome, concluido_em, linhas_lidas
        FROM imp.importacao WHERE status = 'concluida' ORDER BY fonte, id DESC""").fetchall()
    totais = conn.execute("""
        SELECT (SELECT count(*) FROM ana.mv_aluno) AS alunos,
               (SELECT count(*) FROM ana.mv_interesse) AS interesses,
               (SELECT count(DISTINCT instituicao_id) FROM ana.mv_interesse) AS instituicoes_com_interesse,
               (SELECT count(*) FROM core.instituicao) AS instituicoes_cadastradas,
               (SELECT array_agg(DISTINCT uf ORDER BY uf) FROM ana.mv_aluno) AS estados,
               (SELECT min(cadastrado_em) FROM ana.mv_aluno) AS primeiro_cadastro,
               (SELECT max(cadastrado_em) FROM ana.mv_aluno) AS ultimo_cadastro""").fetchone()
    return {"versao": estado["versao"], "atualizado_em": estado["atualizado_em"],
            "ultimas_importacoes": {u["fonte"]: dict(u) for u in ultimas}, **totais}
