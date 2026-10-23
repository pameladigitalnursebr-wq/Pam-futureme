"""Consultas do modo Cowork: mesmas definições do sistema principal (src/painel/consultas).

- alunos:     alunos distintos no recorte (um aluno conta uma vez, mesmo com 3 opções)
- interesses: opções de instituição (aluno × posição); um aluno gera até 3
Filtros: E entre dimensões, OU entre valores da mesma dimensão.
"""

from __future__ import annotations

import difflib
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from . import normalizacao as norm

AVISO_CURSO_INSTITUICAO = (
    "Curso e instituição são escolhas independentes do aluno: o resultado conta alunos que têm o curso "
    "no pódio E escolheram a instituição, não necessariamente aquele curso naquela instituição."
)


@dataclass(frozen=True)
class Dim:
    titulo: str
    nivel: str                       # aluno | interesse
    coluna: str = ""                 # coluna em v_aluno (a) ou v_interesse (i)
    tabela: str | None = None        # tabela de rótulos
    rotulo: str = "nome"
    ponte: str | None = None         # tabela aluno_x (curso, modalidade): o aluno tem vários valores
    ponte_coluna: str = ""


DIMS: dict[str, Dim] = {
    "instituicao": Dim("Instituição", "interesse", "instituicao_id", "instituicao"),
    "grupo": Dim("Grupo educacional", "interesse", "grupo_id", "grupo"),
    "posicao": Dim("Posição da opção", "interesse", "posicao"),
    "status_comercial": Dim("Status comercial", "interesse", "status_comercial"),
    "curso": Dim("Curso (pódio do aluno)", "aluno", tabela="curso", ponte="aluno_curso", ponte_coluna="curso_id"),
    "modalidade": Dim("Modalidade", "aluno", tabela="modalidade", ponte="aluno_modalidade",
                      ponte_coluna="modalidade_id"),
    "uf": Dim("Estado", "aluno", "uf", "uf", rotulo="sigla || ' – ' || nome"),
    "regiao_geografica": Dim("Região do país", "aluno", "regiao_geografica"),
    "regiao_ensino": Dim("Região de ensino", "aluno", "regiao_ensino_id", "regiao_ensino", "nome || ' (' || uf || ')'"),
    "cidade": Dim("Cidade", "aluno", "cidade_id", "cidade", "nome || ' (' || uf || ')'"),
    "escola": Dim("Escola", "aluno", "escola_id", "escola", "nome || ' (' || uf || ')'"),
    "ano_cadastro": Dim("Ano de cadastro", "aluno", "ano_cadastro"),
    "faixa_etaria": Dim("Faixa etária", "aluno", "faixa_etaria"),
    "genero": Dim("Gênero", "aluno", "genero"),
    "situacao_atual": Dim("Faz no momento", "aluno", "situacao_atual"),
    "plano_pos_medio": Dim("Plano pós-médio", "aluno", "plano_pos_medio"),
    "aceita_comunicados": Dim("Aceita comunicados", "aluno", "aceita_comunicados"),
}
NUMERICAS = {"posicao", "ano_cadastro"}
DIMS_BUSCA = ("instituicao", "curso", "cidade", "uf", "regiao_ensino", "escola", "grupo")


class Ambiguo(Exception):
    def __init__(self, dimensao: str, termo: str, opcoes: list[dict]):
        super().__init__(termo)
        self.dimensao, self.termo, self.opcoes = dimensao, termo, opcoes


@dataclass
class Filtros:
    valores: dict[str, list[Any]] = field(default_factory=dict)
    incluir_suspeitas: bool = False

    @property
    def tem_interesse(self) -> bool:
        return any(DIMS[d].nivel == "interesse" for d in self.valores)

    def avisos(self) -> list[str]:
        return [AVISO_CURSO_INSTITUICAO] if "curso" in self.valores and self.tem_interesse else []


def _marcadores(vals: list) -> str:
    return ", ".join("?" * len(vals))


def _where_aluno(f: Filtros) -> tuple[str, list]:
    partes, params = ["1 = 1"], []
    for nome, vals in f.valores.items():
        d = DIMS[nome]
        if d.nivel != "aluno":
            continue
        if d.ponte:
            partes.append(f"EXISTS (SELECT 1 FROM {d.ponte} p WHERE p.aluno_id = a.id "
                          f"AND p.{d.ponte_coluna} IN ({_marcadores(vals)}))")
        else:
            partes.append(f"a.{d.coluna} IN ({_marcadores(vals)})")
        params += vals
    return " AND ".join(partes), params


def _where_interesse(f: Filtros) -> tuple[str, list]:
    partes, params = ["1 = 1"], []
    for nome, vals in f.valores.items():
        d = DIMS[nome]
        if d.nivel == "interesse":
            partes.append(f"i.{d.coluna} IN ({_marcadores(vals)})")
            params += vals
    if not f.incluir_suspeitas:
        partes.append("i.qualidade = 'ok'")
    return " AND ".join(partes), params


def _recorte_alunos(f: Filtros) -> tuple[str, list]:
    """FROM/WHERE dos alunos do recorte (alias a)."""
    wa, pa = _where_aluno(f)
    if f.tem_interesse:
        wi, pi = _where_interesse(f)
        return f"v_aluno a WHERE {wa} AND EXISTS (SELECT 1 FROM v_interesse i WHERE i.aluno_id = a.id AND {wi})", pa + pi
    return f"v_aluno a WHERE {wa}", pa


def _recorte_interesses(f: Filtros) -> tuple[str, list]:
    """FROM/WHERE dos interesses do recorte (alias i, com o aluno em a)."""
    wa, pa = _where_aluno(f)
    wi, pi = _where_interesse(f)
    return f"v_interesse i JOIN v_aluno a ON a.id = i.aluno_id WHERE {wa} AND {wi}", pa + pi


# ---------------------------------------------------------------------------
# Resumo e ranking
# ---------------------------------------------------------------------------

def resumo(conn: sqlite3.Connection, f: Filtros) -> dict:
    ra, pa = _recorte_alunos(f)
    ri, pi = _recorte_interesses(f)
    a = conn.execute(f"""SELECT count(*) AS alunos, count(DISTINCT a.uf) AS estados,
                         count(DISTINCT a.cidade_id) AS cidades, count(DISTINCT a.escola_id) AS escolas FROM {ra}""",
                     pa).fetchone()
    c = conn.execute(f"SELECT count(DISTINCT ac.curso_id) FROM aluno_curso ac WHERE ac.aluno_id IN "
                     f"(SELECT a.id FROM {ra})", pa).fetchone()[0]
    i = conn.execute(f"""SELECT count(*) AS interesses, count(DISTINCT i.aluno_id) AS alunos_com_interesse,
                         count(DISTINCT i.instituicao_id) AS instituicoes FROM {ri}""", pi).fetchone()
    return {**dict(a), "cursos": c, **dict(i), "avisos": f.avisos()}


def rotulos(conn: sqlite3.Connection, dim: str, chaves: list) -> dict:
    d = DIMS[dim]
    if not chaves:
        return {}
    if d.tabela:
        chave = "sigla" if d.tabela == "uf" else "id"
        return {r[0]: r[1] for r in conn.execute(
            f"SELECT {chave}, {d.rotulo} FROM {d.tabela} WHERE {chave} IN ({_marcadores(chaves)})", chaves)}
    if dim == "posicao":
        return {k: f"{k}ª opção" for k in chaves}
    if dim == "aceita_comunicados":
        return {k: "Sim" if k else "Não" for k in chaves}
    return {k: str(k) for k in chaves}


def ranking(conn: sqlite3.Connection, dim: str, f: Filtros, limite: int = 10, somente: list | None = None) -> dict:
    if dim not in DIMS:
        raise ValueError(f"Dimensão desconhecida: '{dim}'. Use uma de: {', '.join(DIMS)}.")
    d = DIMS[dim]
    limite = max(1, min(int(limite), 500))
    ra, pa = _recorte_alunos(f)
    ri, pi = _recorte_interesses(f)
    if d.ponte:
        k_a, juncao_a = f"p.{d.ponte_coluna}", f" JOIN {d.ponte} p ON p.aluno_id = a.id"
        k_i, juncao_i = f"p.{d.ponte_coluna}", f" JOIN {d.ponte} p ON p.aluno_id = i.aluno_id"
    else:
        prefixo = "i" if d.nivel == "interesse" else "a"
        k_a = k_i = f"{prefixo}.{d.coluna}"
        juncao_a = juncao_i = ""
    restricao, p_restricao = "", []
    if somente is not None:
        restricao = f" AND {k_i} IN ({_marcadores(somente)})"
        p_restricao = list(somente)

    def com_juncao(recorte: str, juncao: str) -> str:
        de, onde = recorte.split(" WHERE ", 1)
        return f"{de}{juncao} WHERE {onde}"

    if d.nivel == "interesse":
        linhas = conn.execute(f"""
            SELECT {k_i} AS chave, count(DISTINCT i.aluno_id) AS alunos, count(*) AS interesses
            FROM {com_juncao(ri, juncao_i)} AND {k_i} IS NOT NULL{restricao}
            GROUP BY {k_i} ORDER BY alunos DESC, interesses DESC LIMIT ?""", pi + p_restricao + [limite]).fetchall()
        itens = [dict(l) for l in linhas]
        total_valores = conn.execute(f"SELECT count(DISTINCT {k_i}) FROM {com_juncao(ri, juncao_i)} "
                                     f"AND {k_i} IS NOT NULL{restricao}", pi + p_restricao).fetchone()[0]
    else:
        restricao_a = restricao.replace(k_i, k_a)
        linhas = conn.execute(f"""
            SELECT {k_a} AS chave, count(DISTINCT a.id) AS alunos FROM {com_juncao(ra, juncao_a)}
            AND {k_a} IS NOT NULL{restricao_a} GROUP BY {k_a} ORDER BY alunos DESC LIMIT ?""",
            pa + p_restricao + [limite]).fetchall()
        itens = [dict(l) for l in linhas]
        total_valores = conn.execute(f"SELECT count(DISTINCT {k_a}) FROM {com_juncao(ra, juncao_a)} "
                                     f"AND {k_a} IS NOT NULL{restricao_a}", pa + p_restricao).fetchone()[0]
        chaves = [i["chave"] for i in itens]
        interesses = {}
        if chaves:
            interesses = dict(conn.execute(f"""
                SELECT {k_i}, count(*) FROM {com_juncao(ri, juncao_i)} AND {k_i} IN ({_marcadores(chaves)})
                GROUP BY {k_i}""", pi + chaves).fetchall())
        for i in itens:
            i["interesses"] = interesses.get(i["chave"], 0)
    base = resumo(conn, f)["alunos"]
    nomes = rotulos(conn, dim, [i["chave"] for i in itens])
    for i in itens:
        i["nome"] = nomes.get(i["chave"], str(i["chave"]))
        i["percentual_dos_alunos"] = round(100 * i["alunos"] / base, 1) if base else 0.0
    return {"dimensao": d.titulo, "itens": itens, "total_de_valores": total_valores,
            "alunos_no_recorte": base, "avisos": f.avisos()}


# ---------------------------------------------------------------------------
# Busca e resolução de nomes
# ---------------------------------------------------------------------------

def _candidatos(conn: sqlite3.Connection, dim: str, k: str) -> list[tuple[Any, bool]]:
    """[(chave, exato)] dos valores cujo nome contém o termo normalizado."""
    d = DIMS[dim]
    padrao = f"%{k}%"
    if dim == "instituicao":
        linhas = conn.execute("SELECT id, upper(coalesce(sigla, '')) = ? FROM instituicao WHERE nome_norm LIKE ?",
                              (k, padrao)).fetchall()
    elif dim == "curso":
        linhas = conn.execute("SELECT id, nome_norm = ? OR nome_norm LIKE ? FROM curso WHERE nome_norm LIKE ?",
                              (k, f"{k} - %", padrao)).fetchall()
    elif d.tabela in ("cidade", "escola", "regiao_ensino", "grupo"):
        linhas = conn.execute(f"SELECT id, nome_norm = ? FROM {d.tabela} WHERE nome_norm LIKE ?",
                              (k, padrao)).fetchall()
    elif dim == "uf":
        linhas = [(r[0], r[0] == k or norm.chave(r[1]) == k) for r in conn.execute("SELECT sigla, nome FROM uf")
                  if k in r[0] or k in (norm.chave(r[1]) or "")]
    elif dim == "modalidade":
        linhas = [(r[0], norm.chave(r[1]) == k) for r in conn.execute("SELECT id, nome FROM modalidade")
                  if k in (norm.chave(r[1]) or "")]
    else:
        return []
    return [(l[0], bool(l[1])) for l in linhas]


def buscar(conn: sqlite3.Connection, dim: str, termo: str, limite: int = 10) -> list[dict]:
    """Valores de uma dimensão que contêm o termo, com alunos e interesses (base inteira)."""
    k = norm.chave(termo) or ""
    todos = Filtros(incluir_suspeitas=True)
    if not k:
        return ranking(conn, dim, todos, limite)["itens"]
    if not DIMS[dim].tabela:          # dimensões de texto livre: compara com os valores existentes
        itens = ranking(conn, dim, todos, 500)["itens"]
        achados = [{**i, "exato": norm.chave(i["nome"]) == k} for i in itens if k in (norm.chave(i["nome"]) or "")]
        return sorted(achados, key=lambda i: not i["exato"])[:limite]
    candidatos = _candidatos(conn, dim, k)
    if not candidatos:
        return []
    exatos = {c for c, e in candidatos if e}
    chaves = [c for c, _ in candidatos]
    itens = []
    for i in range(0, len(chaves), 500):
        itens += ranking(conn, dim, todos, 500, somente=chaves[i:i + 500])["itens"]
    if dim == "instituicao":         # instituição sem interessados ainda é resposta válida
        encontrados = {i["chave"] for i in itens}
        faltam = [c for c in chaves if c not in encontrados][:50]
        itens += [{"chave": c, "nome": n, "alunos": 0, "interesses": 0, "percentual_dos_alunos": 0.0}
                  for c, n in rotulos(conn, dim, faltam).items()]
    for i in itens:
        i["exato"] = i["chave"] in exatos
    itens.sort(key=lambda i: (not i["exato"], -i["alunos"]))
    return itens[:limite]


def busca_rapida(conn: sqlite3.Connection, termo: str, limite: int = 5) -> dict:
    palavras = [p for p in termo.split() if len(norm.chave(p) or "") >= 3]
    grupos = {}
    for dim in DIMS_BUSCA:
        itens = buscar(conn, dim, termo, limite)
        if not itens and len(palavras) > 1:
            vistos: dict = {}
            for p in palavras:
                for i in buscar(conn, dim, p, limite):
                    vistos.setdefault(i["chave"], i)
            itens = sorted(vistos.values(), key=lambda i: -i["alunos"])[:limite]
        if itens:
            grupos[dim] = itens
    return grupos


def escolher(dim: str, termo: str, opcoes: list[dict]) -> list[dict]:
    """Decide quais valores um nome representa, ou levanta Ambiguo.

    - Correspondências exatas (sigla, nome igual, curso + grau) entram juntas, desde que a maior delas tenha
      volume real: pelo menos 10% dos alunos da opção mais citada. Assim "puc" não vira uma resposta livre
      "PUC - Rio" com 1 aluno quando existem PUC-Campinas, PUC-SP...
    - Sem exata: vale a opção dominante (80% dos alunos entre as candidatas), senão é ambíguo.
    """
    if not opcoes:
        raise Ambiguo(dim, termo, [])
    maior = max(o["alunos"] for o in opcoes)
    exatos = [o for o in opcoes if o.get("exato")]
    if exatos and max(o["alunos"] for o in exatos) >= 0.1 * maior:
        return exatos
    if len(opcoes) == 1 or opcoes[0]["alunos"] >= 0.8 * sum(o["alunos"] for o in opcoes):
        return [max(opcoes, key=lambda o: o["alunos"])]
    raise Ambiguo(dim, termo, sorted(opcoes, key=lambda o: -o["alunos"]))


def resolver(conn: sqlite3.Connection, por_nome: dict[str, list], incluir_suspeitas: bool = False):
    """Nomes ditos pela pessoa -> valores da base. Devolve (Filtros, filtros_aplicados).

    Grafias equivalentes do mesmo nome entram juntas (ex.: 'Medicina - Bacharelado' e 'medicina').
    Nome ambíguo levanta Ambiguo com as opções, para o Claude perguntar à pessoa.
    """
    valores, aplicados = {}, []
    for dim, termos in por_nome.items():
        if not termos:
            continue
        if dim in NUMERICAS:
            valores[dim] = [int(t) for t in termos]
            continue
        if dim == "aceita_comunicados":
            valores[dim] = [1 if str(t).lower() in ("1", "sim", "true", "s") else 0 for t in termos]
            continue
        escolhidos = []
        for termo in termos:
            escolhidos += escolher(dim, str(termo), buscar(conn, dim, str(termo), 10))
        valores[dim] = [o["chave"] for o in escolhidos]
        aplicados.append({"filtro": dim, "valores": [o["nome"] for o in escolhidos]})
    return Filtros(valores, incluir_suspeitas), aplicados


# ---------------------------------------------------------------------------
# Detalhe, histórico, comparação, situação da base
# ---------------------------------------------------------------------------

def detalhar(conn: sqlite3.Connection, f: Filtros, pagina: int = 1, por_pagina: int = 20) -> dict:
    """Alunos do recorte, um por linha, sem dados pessoais."""
    ra, pa = _recorte_alunos(f)
    total = conn.execute(f"SELECT count(*) FROM {ra}", pa).fetchone()[0]
    por_pagina = max(1, min(int(por_pagina), 100000))
    linhas = conn.execute(f"""
        SELECT substr(a.cadastrado_em, 1, 10) AS cadastro, a.uf, c.nome AS cidade, r.nome AS regiao_ensino,
               e.nome AS escola,
               (SELECT group_concat(nome, ' | ') FROM (SELECT cu.nome FROM aluno_curso ac
                  JOIN curso cu ON cu.id = ac.curso_id WHERE ac.aluno_id = a.id ORDER BY ac.posicao)) AS cursos,
               (SELECT group_concat(nome, ', ') FROM (SELECT m.nome FROM aluno_modalidade am
                  JOIN modalidade m ON m.id = am.modalidade_id WHERE am.aluno_id = a.id ORDER BY am.ordem)) AS modalidades,
               (SELECT inst.nome FROM interesse x JOIN instituicao inst ON inst.id = x.instituicao_id
                  WHERE x.aluno_id = a.id AND x.ativo = 1 AND x.posicao = 1) AS opcao_1,
               (SELECT inst.nome FROM interesse x JOIN instituicao inst ON inst.id = x.instituicao_id
                  WHERE x.aluno_id = a.id AND x.ativo = 1 AND x.posicao = 2) AS opcao_2,
               (SELECT inst.nome FROM interesse x JOIN instituicao inst ON inst.id = x.instituicao_id
                  WHERE x.aluno_id = a.id AND x.ativo = 1 AND x.posicao = 3) AS opcao_3,
               a.faixa_etaria, CASE a.aceita_comunicados WHEN 1 THEN 'Sim' WHEN 0 THEN 'Não' END AS aceita_comunicados
        FROM {ra.replace('v_aluno a', 'v_aluno a LEFT JOIN cidade c ON c.id = a.cidade_id '
                         'LEFT JOIN regiao_ensino r ON r.id = a.regiao_ensino_id '
                         'LEFT JOIN escola e ON e.id = a.escola_id', 1)}
        ORDER BY a.cadastrado_em DESC LIMIT ? OFFSET ?""", pa + [por_pagina, (max(1, pagina) - 1) * por_pagina])
    return {"total_alunos": total, "pagina": pagina, "paginas": (total + por_pagina - 1) // por_pagina,
            "alunos": [dict(l) for l in linhas], "avisos": f.avisos()}


def historico_anual(conn: sqlite3.Connection, dim: str, chave: int) -> dict:
    tabela = {"instituicao": ("volume_instituicao_anual", "instituicao_id"),
              "curso": ("volume_curso_anual", "curso_id")}.get(dim)
    if tabela is None:
        raise ValueError("Histórico anual disponível para 'instituicao' e 'curso'.")
    linhas = [dict(r) for r in conn.execute(
        f"SELECT ano, uf, total FROM {tabela[0]} WHERE {tabela[1]} = ? ORDER BY ano, uf", (chave,))]
    por_ano: dict[int, int] = {}
    for l in linhas:
        por_ano[l["ano"]] = por_ano.get(l["ano"], 0) + l["total"]
    return {"nome": rotulos(conn, dim, [chave]).get(chave),
            "por_ano": [{"ano": a, "total": t} for a, t in sorted(por_ano.items())], "por_ano_e_uf": linhas,
            "fonte": "Base de instituições (totais anuais por UF de origem do lead)"}


def comparar_importacoes(conn: sqlite3.Connection, dim: str, limite: int = 15) -> dict:
    ids = [r[0] for r in conn.execute("""SELECT id FROM importacao WHERE status = 'concluida' AND fonte = 'leads'
                                         ORDER BY id DESC LIMIT 2""")]
    if len(ids) < 2:
        return {"itens": [], "mensagem": "A comparação precisa de pelo menos duas importações da base de interessados."}
    atual, anterior = ids
    linhas = conn.execute("""
        WITH a AS (SELECT * FROM snapshot_metrica WHERE importacao_id = ? AND dimensao = ?),
             b AS (SELECT * FROM snapshot_metrica WHERE importacao_id = ? AND dimensao = ?),
             chaves AS (SELECT chave FROM a UNION SELECT chave FROM b)
        SELECT coalesce(b.rotulo, a.rotulo) AS nome, coalesce(a.alunos, 0) AS alunos_antes,
               coalesce(b.alunos, 0) AS alunos_depois, coalesce(b.alunos, 0) - coalesce(a.alunos, 0) AS variacao
        FROM chaves k LEFT JOIN a ON a.chave = k.chave LEFT JOIN b ON b.chave = k.chave
        ORDER BY abs(coalesce(b.alunos, 0) - coalesce(a.alunos, 0)) DESC LIMIT ?""",
        (anterior, dim, atual, dim, limite))
    return {"importacao_anterior": anterior, "importacao_atual": atual, "itens": [dict(l) for l in linhas]}


def status(conn: sqlite3.Connection) -> dict:
    ultimas = {r["fonte"]: {"importacao": r["id"], "arquivo": r["arquivo"], "em_utc": r["concluido_em"],
                            "linhas": r["linhas_lidas"]}
               for r in conn.execute("""SELECT * FROM importacao WHERE id IN (SELECT max(id) FROM importacao
                                        WHERE status = 'concluida' GROUP BY fonte)""")}
    t = conn.execute("""SELECT (SELECT count(*) FROM v_aluno) AS alunos,
                               (SELECT count(*) FROM v_interesse WHERE qualidade = 'ok') AS interesses,
                               (SELECT count(DISTINCT instituicao_id) FROM v_interesse WHERE qualidade = 'ok')
                                   AS instituicoes_com_interesse,
                               (SELECT group_concat(uf, ', ') FROM (SELECT DISTINCT uf FROM v_aluno
                                   WHERE uf IS NOT NULL ORDER BY uf)) AS estados,
                               (SELECT min(substr(cadastrado_em, 1, 10)) FROM v_aluno) AS cadastros_de,
                               (SELECT max(substr(cadastrado_em, 1, 10)) FROM v_aluno) AS cadastros_ate""").fetchone()
    return {"base_carregada": bool(ultimas), **dict(t), "ultimas_importacoes": ultimas}


# ---------------------------------------------------------------------------
# Revisão de instituições
# ---------------------------------------------------------------------------

def pendentes(conn: sqlite3.Connection, limite: int = 30) -> list[dict]:
    """Instituições que vieram só da base de interessados ou parecem texto livre, com sugestões."""
    validas = [(r["id"], r["nome"], r["nome_norm"]) for r in
               conn.execute("SELECT id, nome, nome_norm FROM instituicao WHERE qualidade = 'ok'")]
    normas = [v[2] for v in validas]
    linhas = conn.execute("""
        SELECT i.id, i.nome, i.nome_norm, i.qualidade, count(x.aluno_id) AS interesses
        FROM instituicao i LEFT JOIN interesse x ON x.instituicao_id = i.id AND x.ativo = 1
        WHERE i.verificada = 0 AND (i.origem = 'leads' OR i.qualidade = 'suspeita')
        GROUP BY i.id ORDER BY interesses DESC LIMIT ?""", (limite,)).fetchall()
    saida = []
    for l in linhas:
        parecidos = difflib.get_close_matches(l["nome_norm"], normas, n=4, cutoff=0.6)
        sugestoes = [{"id": v[0], "nome": v[1]} for v in validas if v[2] in parecidos and v[0] != l["id"]][:3]
        saida.append({"id": l["id"], "nome": l["nome"], "qualidade": l["qualidade"],
                      "interesses": l["interesses"], "sugestoes": sugestoes})
    return saida


def unificar(conn: sqlite3.Connection, origem_id: int, destino_id: int) -> dict:
    """Junta a instituição 'origem' na 'destino' (grafias, interesses e volumes). Vale para importações futuras."""
    nomes = {r[0]: r[1] for r in conn.execute("SELECT id, nome FROM instituicao WHERE id IN (?, ?)",
                                               (origem_id, destino_id))}
    if origem_id == destino_id or len(nomes) != 2:
        raise ValueError("Informe duas instituições diferentes e existentes.")
    conn.execute("BEGIN IMMEDIATE")
    try:
        movidos = conn.execute("UPDATE interesse SET instituicao_id = ? WHERE instituicao_id = ?",
                               (destino_id, origem_id)).rowcount
        conn.execute("""INSERT INTO volume_instituicao_anual SELECT ?, uf, ano, total FROM volume_instituicao_anual
                        WHERE instituicao_id = ?
                        ON CONFLICT (instituicao_id, uf, ano) DO UPDATE SET total = total + excluded.total""",
                     (destino_id, origem_id))
        conn.execute("DELETE FROM volume_instituicao_anual WHERE instituicao_id = ?", (origem_id,))
        conn.execute("UPDATE instituicao_alias SET instituicao_id = ?, origem = 'unificacao' WHERE instituicao_id = ?",
                     (destino_id, origem_id))
        conn.execute("DELETE FROM instituicao WHERE id = ?", (origem_id,))
        conn.execute("UPDATE instituicao SET verificada = 1 WHERE id = ?", (destino_id,))
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    return {"origem": nomes[origem_id], "destino": nomes[destino_id], "interesses_movidos": movidos}


def marcar(conn: sqlite3.Connection, instituicao_id: int, qualidade: str) -> None:
    if qualidade not in ("ok", "suspeita"):
        raise ValueError("qualidade deve ser 'ok' ou 'suspeita'")
    conn.execute("UPDATE instituicao SET qualidade = ?, verificada = 1 WHERE id = ?", (qualidade, instituicao_id))
