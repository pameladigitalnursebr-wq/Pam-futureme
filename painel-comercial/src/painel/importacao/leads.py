"""Importação da base de interessados (Base 2).

Cada linha da planilha é um interesse: (aluno, posição da opção, instituição).
Um aluno aparece em até 3 linhas; os dados do aluno se repetem nelas e são
gravados uma única vez em core.aluno. Nada é deduplicado por aluno.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field

import psycopg

from .. import normalizacao as norm
from .leitor import Aba
from .ocorrencias import Ocorrencias

UFS_VALIDAS = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA",
    "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
}


class RemocaoExcessiva(Exception):
    """A importação completa desativaria mais registros do que o limite de segurança."""


# Colunas que variam de uma linha para outra do mesmo aluno (o resto é dado do aluno).
_COLUNAS_DA_LINHA = {"_linha", "posicao", "instituicao"}


def _hash(*partes: object) -> str:
    return hashlib.md5("\x1f".join("" if p is None else str(p) for p in partes).encode()).hexdigest()


@dataclass
class Preparado:
    alunos: dict[uuid.UUID, tuple] = field(default_factory=dict)
    aluno_cursos: list[tuple] = field(default_factory=list)
    aluno_modalidades: list[tuple] = field(default_factory=list)
    interesses: dict[tuple[uuid.UUID, int], tuple] = field(default_factory=dict)
    cursos: dict[str, tuple] = field(default_factory=dict)
    instituicoes: dict[str, tuple] = field(default_factory=dict)
    linhas_lidas: int = 0


def preparar(aba: Aba, oc: Ocorrencias) -> Preparado:
    """Valida e normaliza as linhas. Não acessa o banco."""
    p = Preparado()
    p.linhas_lidas = len(aba.dados)
    colunas = list(aba.dados.columns)
    colunas_aluno = [c for c in colunas if c not in _COLUNAS_DA_LINHA]
    assinatura_aluno: dict[uuid.UUID, tuple] = {}
    suspeitas_avisadas: set[str] = set()
    ids_validos: dict[str, uuid.UUID | None] = {}

    for valores in zip(*(aba.dados[c].tolist() for c in colunas)):
        r = dict(zip(colunas, valores))
        linha = r["_linha"]
        bruto_id = norm.texto(r.get("aluno_id"))
        if bruto_id not in ids_validos:
            try:
                ids_validos[bruto_id] = uuid.UUID(bruto_id) if bruto_id else None
            except ValueError:
                ids_validos[bruto_id] = None
        aluno_id = ids_validos[bruto_id]
        if aluno_id is None:
            oc.erro("id_invalido", "ID do aluno ausente ou inválido; linha ignorada.", linha, "ID", bruto_id)
            continue

        # ---------------- interesse da linha ----------------
        try:
            posicao = norm.inteiro(r.get("posicao"))
        except ValueError:
            oc.erro("posicao_invalida", "Posição da opção não é número; linha ignorada.", linha,
                    "Posição da opção de faculdade", r.get("posicao"))
            continue
        nome_inst = norm.texto(r.get("instituicao"))
        if nome_inst is not None and posicao is None:
            oc.erro("posicao_ausente", "Instituição informada sem a posição da opção; linha ignorada.",
                    linha, "Posição da opção de faculdade")
            continue
        if posicao is not None and not 1 <= posicao <= 3:
            oc.erro("posicao_invalida", "Posição da opção deve ser 1, 2 ou 3; linha ignorada.", linha,
                    "Posição da opção de faculdade", posicao)
            continue
        if posicao is not None and nome_inst is None:
            oc.aviso("instituicao_ausente", "Posição informada sem instituição; só os dados do aluno entram.",
                     linha, "Instituição Privada")
            posicao = None

        # ---------------- dados do aluno (processados na primeira linha do ID) ----------------
        assinatura = tuple(str(r[c]) for c in colunas_aluno)
        anterior = assinatura_aluno.get(aluno_id)
        if anterior is None:
            assinatura_aluno[aluno_id] = assinatura
            aluno = _dados_aluno(r, linha, oc)
            cursos = _cursos(r)
            mods, desconhecidas = norm.modalidades(r.get("modalidade"))
            for termo in desconhecidas:
                oc.aviso("modalidade_desconhecida", "Modalidade não reconhecida; ignorada.", linha,
                         "Modalidade", termo)
            for pos, nome_curso, chave_curso in cursos:
                p.aluno_cursos.append((aluno_id, pos, chave_curso))
                p.cursos.setdefault(chave_curso, (nome_curso, chave_curso, norm.grau_curso(nome_curso)))
            for ordem, mid in enumerate(mods, start=1):
                p.aluno_modalidades.append((aluno_id, mid, ordem))
            hash_aluno = _hash(*aluno, *(c[2] for c in cursos), *mods)
            p.alunos[aluno_id] = (aluno_id, *aluno, hash_aluno)
        elif anterior != assinatura:
            oc.aviso("aluno_divergente",
                     "O mesmo ID aparece com dados de aluno diferentes; valem os da primeira linha.",
                     linha, "ID", str(aluno_id))

        if posicao is None:
            continue
        chave_inst = norm.chave(nome_inst)
        chave_interesse = (aluno_id, posicao)
        existente = p.interesses.get(chave_interesse)
        if existente is not None:
            if existente[3] == chave_inst:
                oc.aviso("linha_repetida", "Linha repetida (mesmo aluno, posição e instituição); contada uma vez.",
                         linha, "ID", str(aluno_id))
            else:
                oc.erro("chave_duplicada",
                        f"Aluno com duas instituições diferentes na posição {posicao}; vale a primeira linha.",
                        linha, "Instituição Privada", nome_inst)
            continue
        p.interesses[chave_interesse] = (aluno_id, posicao, nome_inst, chave_inst, _hash(chave_inst))
        if chave_inst not in p.instituicoes:
            suspeita = norm.instituicao_suspeita(nome_inst)
            p.instituicoes[chave_inst] = (nome_inst, chave_inst, norm.sigla_instituicao(nome_inst), suspeita)
            if suspeita and chave_inst not in suspeitas_avisadas:
                suspeitas_avisadas.add(chave_inst)
                oc.aviso("instituicao_suspeita",
                         "Texto não parece nome de instituição; entra marcado como suspeito para revisão.",
                         linha, "Instituição Privada", nome_inst)
    return p


def _dados_aluno(r: dict, linha: int, oc: Ocorrencias) -> tuple:
    uf = norm.chave(r.get("uf"))
    if uf is not None and uf not in UFS_VALIDAS:
        oc.aviso("uf_invalida", "Estado não reconhecido; campo deixado vazio.", linha, "Estado", r.get("uf"))
        uf = None
    cidade = norm.texto(r.get("cidade"))
    regiao = norm.texto(r.get("regiao_ensino"))
    escola = norm.texto(r.get("escola"))

    try:
        nascimento = norm.data(r.get("data_nascimento"))
    except ValueError as e:
        oc.aviso("data_invalida", f"Data de nascimento inválida ({e}); campo deixado vazio.", linha,
                 "Data de nascimento", r.get("data_nascimento"))
        nascimento = None
    try:
        cadastrado_em = norm.data_hora(r.get("cadastrado_em"))
    except ValueError:
        oc.aviso("data_invalida", "Data de cadastro inválida; campo deixado vazio.", linha, "Criado em",
                 r.get("cadastrado_em"))
        cadastrado_em = None

    booleanos = []
    for campo, coluna in (("aceita_comunicados", "Receber comunicados"),
                          ("concluiu_relatorio", "Concluiu Relatório de Perfil Profissional")):
        try:
            booleanos.append(norm.booleano(r.get(campo)))
        except ValueError:
            oc.aviso("booleano_invalido", "Valor deveria ser Sim/Não; campo deixado vazio.", linha, coluna,
                     r.get(campo))
            booleanos.append(None)

    return (
        uf,
        cidade, norm.chave(cidade),
        regiao, norm.chave(regiao),
        escola, norm.chave(escola),
        norm.texto(r.get("bairro")),
        cadastrado_em,
        nascimento,
        norm.texto(r.get("genero")),
        norm.texto(r.get("situacao_atual")),
        norm.texto(r.get("plano_pos_medio")),
        booleanos[0],
        booleanos[1],
    )


def _cursos(r: dict) -> list[tuple[int, str, str]]:
    """Pódio de cursos: [(posição, nome, chave)], sem repetir o mesmo curso."""
    vistos: set[str] = set()
    saida = []
    for pos in (1, 2, 3):
        nome = norm.texto(r.get(f"curso_{pos}"))
        k = norm.chave(nome)
        if k and k not in vistos:
            vistos.add(k)
            saida.append((pos, nome, k))
    return saida


# ---------------------------------------------------------------------------
# Gravação (set-based, dentro da transação aberta pelo serviço de importação)
# ---------------------------------------------------------------------------

_COLUNAS_ALUNO = ("id", "uf", "cidade", "cidade_norm", "regiao", "regiao_norm", "escola", "escola_norm",
                  "bairro", "cadastrado_em", "data_nascimento", "genero", "situacao_atual",
                  "plano_pos_medio", "aceita_comunicados", "concluiu_relatorio", "hash")

_STAGING = """
CREATE TEMP TABLE t_aluno (
    id uuid PRIMARY KEY, uf char(2), cidade text, cidade_norm text, regiao text, regiao_norm text,
    escola text, escola_norm text, bairro text, cadastrado_em timestamptz, data_nascimento date,
    genero text, situacao_atual text, plano_pos_medio text, aceita_comunicados boolean,
    concluiu_relatorio boolean, hash text NOT NULL,
    cidade_id integer, regiao_id integer, escola_id integer
) ON COMMIT DROP;
CREATE TEMP TABLE t_aluno_curso (aluno_id uuid, posicao smallint, curso_norm text) ON COMMIT DROP;
CREATE TEMP TABLE t_aluno_modalidade (aluno_id uuid, modalidade_id smallint, ordem smallint) ON COMMIT DROP;
CREATE TEMP TABLE t_curso (nome text, nome_norm text PRIMARY KEY, grau text) ON COMMIT DROP;
CREATE TEMP TABLE t_instituicao (nome text, nome_norm text PRIMARY KEY, sigla text, suspeita boolean) ON COMMIT DROP;
CREATE TEMP TABLE t_interesse (
    aluno_id uuid, posicao smallint, instituicao text, instituicao_norm text, hash text,
    instituicao_id integer, PRIMARY KEY (aluno_id, posicao)
) ON COMMIT DROP;
"""


def _copiar(cur: psycopg.Cursor, tabela: str, colunas: tuple[str, ...], linhas) -> None:
    with cur.copy(f"COPY {tabela} ({', '.join(colunas)}) FROM STDIN") as cp:
        for linha in linhas:
            cp.write_row(linha)


def _contagem_por_tipo(cur: psycopg.Cursor, tabela: str) -> dict[str, int]:
    cur.execute(f"SELECT tipo, count(*) AS n FROM {tabela} GROUP BY tipo")
    base = {"novo": 0, "atualizado": 0, "reativado": 0, "inalterado": 0}
    base.update({r["tipo"]: r["n"] for r in cur.fetchall()})
    return base


def gravar(conn: psycopg.Connection, importacao_id: int, modo: str, p: Preparado,
           forcar: bool, limite_remocao: float) -> dict:
    cur = conn.cursor()
    cur.execute(_STAGING)
    _copiar(cur, "t_aluno", _COLUNAS_ALUNO, p.alunos.values())
    _copiar(cur, "t_aluno_curso", ("aluno_id", "posicao", "curso_norm"), p.aluno_cursos)
    _copiar(cur, "t_aluno_modalidade", ("aluno_id", "modalidade_id", "ordem"), p.aluno_modalidades)
    _copiar(cur, "t_curso", ("nome", "nome_norm", "grau"), p.cursos.values())
    _copiar(cur, "t_instituicao", ("nome", "nome_norm", "sigla", "suspeita"), p.instituicoes.values())
    _copiar(cur, "t_interesse", ("aluno_id", "posicao", "instituicao", "instituicao_norm", "hash"),
            p.interesses.values())
    cur.execute("ANALYZE t_aluno; ANALYZE t_interesse")

    novas = _gravar_dimensoes(cur)
    alunos = _gravar_alunos(cur, importacao_id, modo, forcar, limite_remocao)
    interesses = _gravar_interesses(cur, importacao_id, modo, forcar, limite_remocao)
    return {"alunos": alunos, "interesses": interesses, "cadastros_novos": novas}


def _gravar_dimensoes(cur: psycopg.Cursor) -> dict[str, int]:
    novas: dict[str, int] = {}
    cur.execute("""
        INSERT INTO core.regiao_ensino (uf, nome, nome_norm)
        SELECT DISTINCT ON (uf, regiao_norm) uf, regiao, regiao_norm FROM t_aluno
        WHERE uf IS NOT NULL AND regiao_norm IS NOT NULL ORDER BY uf, regiao_norm, regiao
        ON CONFLICT (uf, nome_norm) DO NOTHING""")
    novas["regioes_ensino"] = cur.rowcount
    cur.execute("""
        INSERT INTO core.cidade (uf, nome, nome_norm)
        SELECT DISTINCT ON (uf, cidade_norm) uf, cidade, cidade_norm FROM t_aluno
        WHERE uf IS NOT NULL AND cidade_norm IS NOT NULL ORDER BY uf, cidade_norm, cidade
        ON CONFLICT (uf, nome_norm) DO NOTHING""")
    novas["cidades"] = cur.rowcount
    cur.execute("""
        UPDATE t_aluno t SET regiao_id = r.id FROM core.regiao_ensino r
        WHERE r.uf = t.uf AND r.nome_norm = t.regiao_norm;
        UPDATE t_aluno t SET cidade_id = c.id FROM core.cidade c
        WHERE c.uf = t.uf AND c.nome_norm = t.cidade_norm""")
    cur.execute("""
        INSERT INTO core.escola (uf, cidade_id, regiao_ensino_id, nome, nome_norm, bairro)
        SELECT DISTINCT ON (uf, cidade_id, escola_norm) uf, cidade_id, regiao_id, escola, escola_norm, bairro
        FROM t_aluno WHERE uf IS NOT NULL AND escola_norm IS NOT NULL
        ORDER BY uf, cidade_id, escola_norm, bairro NULLS LAST
        ON CONFLICT (uf, cidade_id, nome_norm) DO NOTHING""")
    novas["escolas"] = cur.rowcount
    cur.execute("""
        UPDATE t_aluno t SET escola_id = e.id FROM core.escola e
        WHERE e.uf = t.uf AND e.cidade_id IS NOT DISTINCT FROM t.cidade_id AND e.nome_norm = t.escola_norm""")
    cur.execute("""
        INSERT INTO core.curso (nome, nome_norm, grau) SELECT nome, nome_norm, grau FROM t_curso
        ON CONFLICT (nome_norm) DO NOTHING""")
    novas["cursos"] = cur.rowcount
    cur.execute("""
        INSERT INTO core.instituicao (nome, nome_norm, sigla, origem, qualidade)
        SELECT t.nome, t.nome_norm, t.sigla, 'leads', CASE WHEN t.suspeita THEN 'suspeita' ELSE 'ok' END
        FROM t_instituicao t
        WHERE NOT EXISTS (SELECT 1 FROM core.instituicao_alias a WHERE a.nome_norm = t.nome_norm)
        ON CONFLICT (nome_norm) DO NOTHING""")
    novas["instituicoes"] = cur.rowcount
    cur.execute("""
        INSERT INTO core.instituicao_alias (nome_norm, instituicao_id, origem)
        SELECT nome_norm, id, 'automatico' FROM core.instituicao ON CONFLICT (nome_norm) DO NOTHING""")
    cur.execute("""
        UPDATE t_interesse t SET instituicao_id = a.instituicao_id
        FROM core.instituicao_alias a WHERE a.nome_norm = t.instituicao_norm""")
    return novas


def _verificar_remocao(cur: psycopg.Cursor, entidade: str, removidos: int, ativos: int,
                       forcar: bool, limite: float) -> None:
    if forcar or ativos == 0 or removidos / ativos <= limite:
        return
    raise RemocaoExcessiva(
        f"Esta importação desativaria {removidos:,} de {ativos:,} {entidade} ativos "
        f"({removidos / ativos:.0%}), acima do limite de segurança de {limite:.0%}. "
        "Confira se a exportação está completa. Se estiver, importe novamente com a opção 'forçar' "
        "ou use o modo incremental.".replace(",", ".")
    )


def _gravar_alunos(cur: psycopg.Cursor, imp: int, modo: str, forcar: bool, limite: float) -> dict:
    cur.execute("""
        CREATE TEMP TABLE t_mudanca_aluno ON COMMIT DROP AS
        SELECT t.id, CASE WHEN a.id IS NULL THEN 'novo'
                          WHEN NOT a.ativo THEN 'reativado'
                          WHEN a.hash <> t.hash THEN 'atualizado'
                          ELSE 'inalterado' END AS tipo
        FROM t_aluno t LEFT JOIN core.aluno a ON a.id = t.id""")
    contagem = _contagem_por_tipo(cur, "t_mudanca_aluno")

    removidos = 0
    if modo == "completo":
        cur.execute("""SELECT count(*) AS n FROM core.aluno a
                       WHERE a.ativo AND NOT EXISTS (SELECT 1 FROM t_aluno t WHERE t.id = a.id)""")
        removidos = cur.fetchone()["n"]
        cur.execute("SELECT count(*) AS n FROM core.aluno WHERE ativo")
        _verificar_remocao(cur, "alunos", removidos, cur.fetchone()["n"], forcar, limite)

    cur.execute("""
        INSERT INTO core.aluno (id, uf, cidade_id, regiao_ensino_id, escola_id, cadastrado_em, data_nascimento,
                                genero, situacao_atual, plano_pos_medio, aceita_comunicados, concluiu_relatorio,
                                hash, ativo, removido_em, importacao_criacao, importacao_alteracao)
        SELECT t.id, t.uf, t.cidade_id, t.regiao_id, t.escola_id, t.cadastrado_em, t.data_nascimento,
               t.genero, t.situacao_atual, t.plano_pos_medio, t.aceita_comunicados, t.concluiu_relatorio,
               t.hash, true, NULL, %(imp)s, %(imp)s
        FROM t_aluno t JOIN t_mudanca_aluno m ON m.id = t.id AND m.tipo <> 'inalterado'
        ON CONFLICT (id) DO UPDATE SET
            uf = EXCLUDED.uf, cidade_id = EXCLUDED.cidade_id, regiao_ensino_id = EXCLUDED.regiao_ensino_id,
            escola_id = EXCLUDED.escola_id, cadastrado_em = EXCLUDED.cadastrado_em,
            data_nascimento = EXCLUDED.data_nascimento, genero = EXCLUDED.genero,
            situacao_atual = EXCLUDED.situacao_atual, plano_pos_medio = EXCLUDED.plano_pos_medio,
            aceita_comunicados = EXCLUDED.aceita_comunicados, concluiu_relatorio = EXCLUDED.concluiu_relatorio,
            hash = EXCLUDED.hash, ativo = true, removido_em = NULL,
            importacao_alteracao = EXCLUDED.importacao_alteracao""", {"imp": imp})
    cur.execute("""
        DELETE FROM core.aluno_curso WHERE aluno_id IN
            (SELECT id FROM t_mudanca_aluno WHERE tipo IN ('atualizado', 'reativado'));
        DELETE FROM core.aluno_modalidade WHERE aluno_id IN
            (SELECT id FROM t_mudanca_aluno WHERE tipo IN ('atualizado', 'reativado'));
        INSERT INTO core.aluno_curso (aluno_id, posicao, curso_id)
        SELECT tc.aluno_id, tc.posicao, c.id
        FROM t_aluno_curso tc
        JOIN core.curso c ON c.nome_norm = tc.curso_norm
        JOIN t_mudanca_aluno m ON m.id = tc.aluno_id AND m.tipo <> 'inalterado';
        INSERT INTO core.aluno_modalidade (aluno_id, modalidade_id, ordem)
        SELECT tm.aluno_id, tm.modalidade_id, tm.ordem
        FROM t_aluno_modalidade tm JOIN t_mudanca_aluno m ON m.id = tm.aluno_id AND m.tipo <> 'inalterado'""")
    if modo == "completo" and removidos:
        cur.execute("""
            UPDATE core.aluno a SET ativo = false, removido_em = now(), importacao_alteracao = %(imp)s
            WHERE a.ativo AND NOT EXISTS (SELECT 1 FROM t_aluno t WHERE t.id = a.id)""", {"imp": imp})
    return {"novos": contagem["novo"], "atualizados": contagem["atualizado"],
            "reativados": contagem["reativado"], "inalterados": contagem["inalterado"], "removidos": removidos}


def _gravar_interesses(cur: psycopg.Cursor, imp: int, modo: str, forcar: bool, limite: float) -> dict:
    cur.execute("""
        CREATE TEMP TABLE t_mudanca_interesse ON COMMIT DROP AS
        SELECT t.aluno_id, t.posicao,
               CASE WHEN i.id IS NULL THEN 'novo'
                    WHEN NOT i.ativo THEN 'reativado'
                    WHEN i.hash <> t.hash THEN 'atualizado'
                    ELSE 'inalterado' END AS tipo
        FROM t_interesse t LEFT JOIN core.interesse i ON i.aluno_id = t.aluno_id AND i.posicao = t.posicao""")
    contagem = _contagem_por_tipo(cur, "t_mudanca_interesse")

    # Completo: some tudo que não veio. Incremental: só as opções antigas dos alunos que vieram no arquivo.
    filtro_remocao = ("i.ativo" if modo == "completo"
                      else "i.ativo AND EXISTS (SELECT 1 FROM t_aluno a WHERE a.id = i.aluno_id)")
    nao_veio = ("NOT EXISTS (SELECT 1 FROM t_interesse t "
                "WHERE t.aluno_id = i.aluno_id AND t.posicao = i.posicao)")
    cur.execute(f"SELECT count(*) AS n FROM core.interesse i WHERE {filtro_remocao} AND {nao_veio}")
    removidos = cur.fetchone()["n"]
    if modo == "completo":
        cur.execute("SELECT count(*) AS n FROM core.interesse WHERE ativo")
        _verificar_remocao(cur, "interesses", removidos, cur.fetchone()["n"], forcar, limite)

    cur.execute("""
        INSERT INTO core.interesse (aluno_id, posicao, instituicao_id, instituicao_nome_origem, hash,
                                    ativo, removido_em, importacao_criacao, importacao_alteracao)
        SELECT t.aluno_id, t.posicao, t.instituicao_id, t.instituicao, t.hash, true, NULL, %(imp)s, %(imp)s
        FROM t_interesse t
        JOIN t_mudanca_interesse m ON m.aluno_id = t.aluno_id AND m.posicao = t.posicao AND m.tipo <> 'inalterado'
        ON CONFLICT (aluno_id, posicao) DO UPDATE SET
            instituicao_id = EXCLUDED.instituicao_id, instituicao_nome_origem = EXCLUDED.instituicao_nome_origem,
            hash = EXCLUDED.hash, ativo = true, removido_em = NULL,
            importacao_alteracao = EXCLUDED.importacao_alteracao""", {"imp": imp})
    if removidos:
        cur.execute(f"""
            UPDATE core.interesse i SET ativo = false, removido_em = now(), importacao_alteracao = %(imp)s
            WHERE {filtro_remocao} AND {nao_veio}""", {"imp": imp})
    return {"novos": contagem["novo"], "atualizados": contagem["atualizado"],
            "reativados": contagem["reativado"], "inalterados": contagem["inalterado"], "removidos": removidos}
