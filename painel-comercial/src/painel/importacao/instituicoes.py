"""Importação da base de instituições (Base 1).

Abas reconhecidas: universidades (obrigatória), cursos, cidades e escolas.
- Instituições: atributos comerciais atualizados; nunca são excluídas (há interesses apontando para elas).
- Volumes anuais: cada aba presente substitui integralmente o volume correspondente.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict

import psycopg

from .. import normalizacao as norm
from .leads import UFS_VALIDAS
from .leitor import Arquivo, ArquivoInvalido
from .ocorrencias import Ocorrencias

ATRIBUTOS = ("porte", "grupo", "afiliado", "comissao", "tipo_comissao", "status_comercial")


def _linhas_validas(aba, oc: Ocorrencias, campo_nome: str, rotulo: str, campos_total: tuple[str, ...],
                    exige_uf: bool = True):
    """Valida UF, ano, nome e totais. Gera (linha, uf, ano, nome, chave, totais, registro)."""
    vistos: set[tuple] = set()
    for r in aba.dados.to_dict("records"):
        linha = r["_linha"]
        nome = norm.texto(r.get(campo_nome))
        if nome is None:
            oc.erro("nome_ausente", f"{rotulo} sem nome; linha ignorada.", linha, rotulo)
            continue
        uf = norm.chave(r.get("uf"))
        if exige_uf and uf not in UFS_VALIDAS:
            oc.erro("uf_invalida", "UF ausente ou inválida; linha ignorada.", linha, "UF", r.get("uf"))
            continue
        try:
            ano = norm.inteiro(r.get("ano"))
            if ano is None or not 2000 <= ano <= 2100:
                raise ValueError
        except ValueError:
            oc.erro("ano_invalido", "Ano ausente ou inválido; linha ignorada.", linha, "Ano", r.get("ano"))
            continue
        totais = []
        try:
            for campo in campos_total:
                totais.append(norm.inteiro(r.get(campo)))
        except ValueError:
            oc.erro("total_invalido", "Total não é número inteiro; linha ignorada.", linha, campo, r.get(campo))
            continue
        assinatura = tuple(str(v) for k, v in r.items() if k != "_linha")
        if assinatura in vistos:
            oc.aviso("linha_repetida", "Linha idêntica a outra já lida; contada uma vez.", linha)
            continue
        vistos.add(assinatura)
        yield linha, uf, ano, nome, norm.chave(nome), totais, r


def _somar(destino: dict, chave: tuple, totais: list, oc: Ocorrencias, linha: int, rotulo: str) -> None:
    """Grafias diferentes que normalizam igual (ex.: 'Unip' e 'UNIP') têm os totais somados."""
    if chave in destino:
        destino[chave] = [(a or 0) + (b or 0) if (a is not None or b is not None) else None
                          for a, b in zip(destino[chave], totais)]
        oc.aviso("grafias_somadas", f"{rotulo} com grafias equivalentes no mesmo ano/UF; totais somados.", linha)
    else:
        destino[chave] = list(totais)


def importar(conn: psycopg.Connection, arquivo: Arquivo, oc: Ocorrencias) -> dict:
    aba_univ = arquivo.aba("universidades")
    if aba_univ is None:
        raise ArquivoInvalido("A base de instituições precisa da aba de universidades "
                              "(colunas UF, Ano, Universidade, Total).")
    cur = conn.cursor()
    resumo: dict = {"linhas_lidas": sum(len(a.dados) for a in arquivo.abas)}
    resumo["instituicoes"] = _importar_universidades(cur, aba_univ, oc)
    if (aba := arquivo.aba("cursos")) is not None:
        resumo["volume_cursos"] = _importar_cursos(cur, aba, oc)
    if (aba := arquivo.aba("cidades")) is not None:
        resumo["volume_cidades"] = _importar_cidades(cur, aba, oc)
    if (aba := arquivo.aba("escolas")) is not None:
        resumo["volume_escolas"] = _importar_escolas(cur, aba, oc)
    return resumo


def _importar_universidades(cur: psycopg.Cursor, aba, oc: Ocorrencias) -> dict:
    volumes: dict[tuple, list] = {}
    nomes: dict[str, str] = {}
    # Atributo -> valor mais recente (maior ano) por instituição.
    atributos: dict[str, dict[str, tuple[int, str]]] = defaultdict(dict)
    divergencias: set[tuple[str, str]] = set()

    for linha, uf, ano, nome, k, totais, r in _linhas_validas(aba, oc, "instituicao", "Universidade", ("total",)):
        nomes.setdefault(k, nome)
        _somar(volumes, (k, uf, ano), totais, oc, linha, "Instituição")
        for campo in ATRIBUTOS:
            valor = norm.valor_canonico(campo, r.get(campo))
            if valor is None:
                continue
            atual = atributos[k].get(campo)
            if atual is not None and atual[1] != valor and (k, campo) not in divergencias:
                divergencias.add((k, campo))
                oc.aviso("atributo_divergente",
                         f"'{campo}' com valores diferentes entre linhas; vale o do ano mais recente.",
                         linha, campo, f"{nome}: {atual[1]} / {valor}")
            if atual is None or ano >= atual[0]:
                atributos[k][campo] = (ano, valor)

    linhas_inst = []
    for k, nome in nomes.items():
        attrs = {c: atributos[k][c][1] if c in atributos[k] else None for c in ATRIBUTOS}
        comissao = norm.moeda(attrs["comissao"])
        h = hashlib.md5(repr(sorted(attrs.items())).encode()).hexdigest()
        linhas_inst.append((nome, k, norm.sigla_instituicao(nome), attrs["grupo"], norm.chave(attrs["grupo"]),
                            attrs["porte"], attrs["afiliado"], comissao, attrs["tipo_comissao"],
                            attrs["status_comercial"], norm.instituicao_suspeita(nome), h))

    cur.execute("""
        CREATE TEMP TABLE t_inst (nome text, nome_norm text PRIMARY KEY, sigla text, grupo text, grupo_norm text,
            porte text, afiliado text, comissao_valor numeric, tipo_comissao text, status_comercial text,
            suspeita boolean, hash text, instituicao_id integer) ON COMMIT DROP;
        CREATE TEMP TABLE t_vol_inst (nome_norm text, uf char(2), ano smallint, total integer) ON COMMIT DROP""")
    with cur.copy("COPY t_inst (nome, nome_norm, sigla, grupo, grupo_norm, porte, afiliado, comissao_valor, "
                  "tipo_comissao, status_comercial, suspeita, hash) FROM STDIN") as cp:
        for linha in linhas_inst:
            cp.write_row(linha)
    with cur.copy("COPY t_vol_inst (nome_norm, uf, ano, total) FROM STDIN") as cp:
        for (k, uf, ano), totais in volumes.items():
            cp.write_row((k, uf, ano, totais[0] or 0))

    cur.execute("""
        INSERT INTO core.grupo_educacional (nome, nome_norm)
        SELECT DISTINCT ON (grupo_norm) grupo, grupo_norm FROM t_inst WHERE grupo_norm IS NOT NULL
        ORDER BY grupo_norm, grupo
        ON CONFLICT (nome_norm) DO NOTHING;
        UPDATE t_inst t SET instituicao_id = a.instituicao_id
        FROM core.instituicao_alias a WHERE a.nome_norm = t.nome_norm""")
    cur.execute("""
        SELECT
          count(*) FILTER (WHERE t.instituicao_id IS NULL) AS novas,
          count(*) FILTER (WHERE t.instituicao_id IS NOT NULL AND i.atributos->>'_hash' IS DISTINCT FROM t.hash)
              AS atualizadas,
          count(*) FILTER (WHERE i.atributos->>'_hash' = t.hash) AS inalteradas
        FROM t_inst t LEFT JOIN core.instituicao i ON i.id = t.instituicao_id""")
    contagem = dict(cur.fetchone())

    cur.execute("""
        UPDATE core.instituicao i SET
            grupo_id = g.id, porte = t.porte, afiliado = t.afiliado, comissao_valor = t.comissao_valor,
            tipo_comissao = t.tipo_comissao, status_comercial = t.status_comercial,
            origem = CASE WHEN i.origem = 'leads' THEN 'base_instituicoes' ELSE i.origem END,
            sigla = COALESCE(i.sigla, t.sigla),
            atributos = i.atributos || jsonb_build_object('_hash', t.hash),
            atualizado_em = now()
        FROM t_inst t LEFT JOIN core.grupo_educacional g ON g.nome_norm = t.grupo_norm
        WHERE i.id = t.instituicao_id AND i.atributos->>'_hash' IS DISTINCT FROM t.hash;

        INSERT INTO core.instituicao (nome, nome_norm, sigla, grupo_id, porte, afiliado, comissao_valor,
                                      tipo_comissao, status_comercial, origem, qualidade, atributos)
        SELECT t.nome, t.nome_norm, t.sigla, g.id, t.porte, t.afiliado, t.comissao_valor, t.tipo_comissao,
               t.status_comercial, 'base_instituicoes', CASE WHEN t.suspeita THEN 'suspeita' ELSE 'ok' END,
               jsonb_build_object('_hash', t.hash)
        FROM t_inst t LEFT JOIN core.grupo_educacional g ON g.nome_norm = t.grupo_norm
        WHERE t.instituicao_id IS NULL
        ON CONFLICT (nome_norm) DO NOTHING;

        INSERT INTO core.instituicao_alias (nome_norm, instituicao_id, origem)
        SELECT nome_norm, id, 'automatico' FROM core.instituicao ON CONFLICT (nome_norm) DO NOTHING;

        DELETE FROM core.volume_instituicao_anual""")
    cur.execute("""
        INSERT INTO core.volume_instituicao_anual (instituicao_id, uf, ano, total)
        SELECT a.instituicao_id, v.uf, v.ano, sum(v.total)
        FROM t_vol_inst v JOIN core.instituicao_alias a ON a.nome_norm = v.nome_norm
        GROUP BY 1, 2, 3""")
    contagem["linhas_volume"] = cur.rowcount
    return contagem


def _importar_cursos(cur: psycopg.Cursor, aba, oc: Ocorrencias) -> dict:
    volumes: dict[tuple, list] = {}
    nomes: dict[str, str] = {}
    for linha, uf, ano, nome, k, totais, _ in _linhas_validas(aba, oc, "curso", "Curso", ("total",)):
        nomes.setdefault(k, nome)
        _somar(volumes, (k, uf, ano), totais, oc, linha, "Curso")
    cur.execute("CREATE TEMP TABLE t_vol_curso (nome text, nome_norm text, grau text, uf char(2), ano smallint, "
                "total integer) ON COMMIT DROP")
    with cur.copy("COPY t_vol_curso FROM STDIN") as cp:
        for (k, uf, ano), totais in volumes.items():
            cp.write_row((nomes[k], k, norm.grau_curso(nomes[k]), uf, ano, totais[0] or 0))
    cur.execute("""
        INSERT INTO core.curso (nome, nome_norm, grau)
        SELECT DISTINCT ON (nome_norm) nome, nome_norm, grau FROM t_vol_curso ORDER BY nome_norm
        ON CONFLICT (nome_norm) DO NOTHING""")
    novos = cur.rowcount
    cur.execute("""
        DELETE FROM core.volume_curso_anual""")
    cur.execute("""
        INSERT INTO core.volume_curso_anual (curso_id, uf, ano, total)
        SELECT c.id, v.uf, v.ano, v.total FROM t_vol_curso v JOIN core.curso c ON c.nome_norm = v.nome_norm""")
    return {"cursos_novos": novos, "linhas_volume": cur.rowcount}


def _importar_cidades(cur: psycopg.Cursor, aba, oc: Ocorrencias) -> dict:
    volumes: dict[tuple, list] = {}
    nomes: dict[tuple, str] = {}
    for linha, uf, ano, nome, k, totais, _ in _linhas_validas(
            aba, oc, "cidade", "Cidade", ("leads_3a_serie", "leads_9o_ano")):
        nomes.setdefault((uf, k), nome)
        _somar(volumes, (uf, k, ano), totais, oc, linha, "Cidade")
    cur.execute("CREATE TEMP TABLE t_vol_cidade (uf char(2), nome text, nome_norm text, ano smallint, "
                "leads_3a integer, leads_9o integer) ON COMMIT DROP")
    with cur.copy("COPY t_vol_cidade FROM STDIN") as cp:
        for (uf, k, ano), (l3, l9) in volumes.items():
            cp.write_row((uf, nomes[(uf, k)], k, ano, l3, l9))
    cur.execute("""
        INSERT INTO core.cidade (uf, nome, nome_norm)
        SELECT DISTINCT ON (uf, nome_norm) uf, nome, nome_norm FROM t_vol_cidade ORDER BY uf, nome_norm
        ON CONFLICT (uf, nome_norm) DO NOTHING""")
    novas = cur.rowcount
    cur.execute("""
        DELETE FROM core.volume_cidade_anual""")
    cur.execute("""
        INSERT INTO core.volume_cidade_anual (cidade_id, ano, leads_3a_serie, leads_9o_ano)
        SELECT c.id, v.ano, v.leads_3a, v.leads_9o
        FROM t_vol_cidade v JOIN core.cidade c ON c.uf = v.uf AND c.nome_norm = v.nome_norm""")
    return {"cidades_novas": novas, "linhas_volume": cur.rowcount}


def _importar_escolas(cur: psycopg.Cursor, aba, oc: Ocorrencias) -> dict:
    volumes: dict[tuple, list] = {}
    info: dict[tuple, tuple] = {}
    for linha, uf, ano, nome, k, totais, r in _linhas_validas(aba, oc, "escola", "Escola", ("total",)):
        cidade = norm.texto(r.get("cidade"))
        chave_escola = (uf, norm.chave(cidade), k)
        info.setdefault(chave_escola, (nome, cidade, norm.texto(r.get("regiao"))))
        _somar(volumes, (*chave_escola, ano), totais, oc, linha, "Escola")
    cur.execute("CREATE TEMP TABLE t_vol_escola (uf char(2), cidade text, cidade_norm text, regiao text, "
                "regiao_norm text, nome text, nome_norm text, ano smallint, total integer) ON COMMIT DROP")
    with cur.copy("COPY t_vol_escola FROM STDIN") as cp:
        for (uf, kc, ke, ano), totais in volumes.items():
            nome, cidade, regiao = info[(uf, kc, ke)]
            cp.write_row((uf, cidade, kc, regiao, norm.chave(regiao), nome, ke, ano, totais[0] or 0))
    cur.execute("""
        INSERT INTO core.cidade (uf, nome, nome_norm)
        SELECT DISTINCT ON (uf, cidade_norm) uf, cidade, cidade_norm FROM t_vol_escola
        WHERE cidade_norm IS NOT NULL ORDER BY uf, cidade_norm
        ON CONFLICT (uf, nome_norm) DO NOTHING;
        INSERT INTO core.regiao_ensino (uf, nome, nome_norm)
        SELECT DISTINCT ON (uf, regiao_norm) uf, regiao, regiao_norm FROM t_vol_escola
        WHERE regiao_norm IS NOT NULL ORDER BY uf, regiao_norm
        ON CONFLICT (uf, nome_norm) DO NOTHING""")
    cur.execute("""
        INSERT INTO core.escola (uf, cidade_id, regiao_ensino_id, nome, nome_norm)
        SELECT DISTINCT ON (v.uf, c.id, v.nome_norm) v.uf, c.id, r.id, v.nome, v.nome_norm
        FROM t_vol_escola v
        LEFT JOIN core.cidade c ON c.uf = v.uf AND c.nome_norm = v.cidade_norm
        LEFT JOIN core.regiao_ensino r ON r.uf = v.uf AND r.nome_norm = v.regiao_norm
        ORDER BY v.uf, c.id, v.nome_norm
        ON CONFLICT (uf, cidade_id, nome_norm) DO NOTHING""")
    novas = cur.rowcount
    cur.execute("""
        DELETE FROM core.volume_escola_anual""")
    cur.execute("""
        INSERT INTO core.volume_escola_anual (escola_id, ano, total)
        SELECT e.id, v.ano, sum(v.total)
        FROM t_vol_escola v
        LEFT JOIN core.cidade c ON c.uf = v.uf AND c.nome_norm = v.cidade_norm
        JOIN core.escola e ON e.uf = v.uf AND e.cidade_id IS NOT DISTINCT FROM c.id AND e.nome_norm = v.nome_norm
        GROUP BY 1, 2""")
    return {"escolas_novas": novas, "linhas_volume": cur.rowcount}
