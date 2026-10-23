"""Importação de planilhas para o banco SQLite (modo Cowork).

Mesmas regras do sistema principal (src/painel/importacao):
- cada linha da base de interessados é um interesse (aluno, posição, instituição); nada é deduplicado por aluno;
- instituições ligadas só por nome normalizado idêntico;
- detecção de novos, alterados, reativados, inalterados e removidos por hash;
- exclusão lógica; trava contra exportação incompleta; arquivo repetido não é reprocessado;
- tudo em uma transação: ou a importação inteira entra, ou nada muda.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from collections import defaultdict
from pathlib import Path

from . import normalizacao as norm
from .esquemas import ESQUEMAS, Esquema
from .ocorrencias import Ocorrencias
from .xlsx import ler_planilhas

LIMITE_REMOCAO = 0.20
LINHAS_BUSCA_CABECALHO = 15
UFS_VALIDAS = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA",
    "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
}
# Colunas que variam de uma linha para outra do mesmo aluno (o resto é dado do aluno).
_COLUNAS_DA_LINHA = {"_linha", "posicao", "instituicao"}
ATRIBUTOS = ("porte", "grupo", "afiliado", "comissao", "tipo_comissao", "status_comercial")


class ImportacaoRejeitada(Exception):
    pass


def _hash(*partes: object) -> str:
    return hashlib.md5("\x1f".join("" if p is None else str(p) for p in partes).encode()).hexdigest()


def _sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Identificação das abas
# ---------------------------------------------------------------------------

def identificar(planilhas: dict[str, list[tuple[int, list]]]):
    """[(aba, esquema, linha do cabeçalho, registros, colunas desconhecidas)] e abas ignoradas."""
    abas, ignoradas = [], []
    for nome, linhas in planilhas.items():
        achado = None
        for numero, cabecalho in linhas[:LINHAS_BUSCA_CABECALHO]:
            for esquema in ESQUEMAS:
                mapa, desconhecidas = esquema.mapear(cabecalho)
                if all(c in mapa for c in esquema.obrigatorias()):
                    achado = (esquema, numero, mapa, desconhecidas)
                    break
            if achado:
                break
        if achado is None:
            ignoradas.append(nome)
            continue
        esquema, n_cab, mapa, desconhecidas = achado
        registros = []
        for numero, valores in linhas:
            if numero <= n_cab:
                continue
            r = {col: (valores[i] if i < len(valores) else None) for col, i in mapa.items()}
            if any(not norm.vazio(v) for v in r.values()):
                r["_linha"] = numero
                registros.append(r)
        abas.append((nome, esquema, n_cab, registros, desconhecidas))
    if not abas:
        raise ImportacaoRejeitada(_diagnostico(planilhas))
    if len({a[1].fonte for a in abas}) > 1:
        raise ImportacaoRejeitada("O arquivo mistura a base de interessados e a de instituições. "
                                  "Envie cada base em um arquivo separado.")
    return abas, ignoradas


def _diagnostico(planilhas) -> str:
    melhor = None
    for nome, linhas in planilhas.items():
        for _, cabecalho in linhas[:LINHAS_BUSCA_CABECALHO]:
            for esquema in ESQUEMAS:
                mapa, _ = esquema.mapear(cabecalho)
                achadas = sum(c in mapa for c in esquema.obrigatorias())
                if achadas and (melhor is None or achadas > melhor[0]):
                    melhor = (achadas, nome, esquema, [c for c in esquema.obrigatorias() if c not in mapa])
    if melhor is None:
        return "Nenhuma aba tem cabeçalhos reconhecidos. Confira se é a exportação correta."
    _, nome, esquema, faltam = melhor
    sinonimos = {c.nome: c.sinonimos[0] for c in esquema.colunas}
    return (f"A aba '{nome}' parece ser '{esquema.descricao}', mas faltam as colunas obrigatórias: "
            f"{', '.join(sinonimos[c] for c in faltam)}.")


# ---------------------------------------------------------------------------
# Orquestração
# ---------------------------------------------------------------------------

def importar(conn: sqlite3.Connection, caminho: Path, modo: str = "completo", forcar: bool = False) -> dict:
    caminho = Path(caminho)
    if modo not in ("completo", "incremental"):
        raise ValueError("modo deve ser 'completo' ou 'incremental'")
    sha = _sha256(caminho)
    if not forcar:
        anterior = conn.execute("SELECT id, concluido_em FROM importacao WHERE sha256 = ? AND status = 'concluida' "
                                "ORDER BY id DESC LIMIT 1", (sha,)).fetchone()
        if anterior:
            raise ImportacaoRejeitada(f"Este arquivo já foi importado (importação #{anterior['id']}, "
                                      f"{anterior['concluido_em']} UTC). Nada a atualizar.")
    abas, ignoradas = identificar(ler_planilhas(caminho))
    fonte = abas[0][1].fonte
    oc = Ocorrencias()
    for nome, _, n_cab, _, desconhecidas in abas:
        for coluna in desconhecidas:
            oc.aviso("coluna_ignorada", f"Coluna não reconhecida na aba '{nome}'; ignorada.", n_cab, coluna)
    linhas_lidas = sum(len(a[3]) for a in abas)

    conn.execute("BEGIN IMMEDIATE")
    try:
        imp = conn.execute("INSERT INTO importacao (fonte, modo, status, arquivo, sha256) VALUES (?, ?, ?, ?, ?)",
                           (fonte, modo, "processando", caminho.name, sha)).lastrowid
        resumo: dict = {"abas": {a[0]: a[1].nome for a in abas}, "abas_ignoradas": ignoradas}
        if fonte == "leads":
            resumo.update(_importar_leads(conn, imp, modo, abas[0][3], oc, forcar))
        else:
            resumo.update(_importar_instituicoes(conn, {a[1].nome: a[3] for a in abas}, oc))
        _gravar_snapshot(conn, imp)
        resumo["ocorrencias"] = oc.resumo()
        conn.executemany("INSERT INTO ocorrencia VALUES (?, ?, ?, ?, ?, ?, ?)",
                         [(imp, *d) for d in oc.detalhes])
        conn.execute("""UPDATE importacao SET status = 'concluida', concluido_em = datetime('now'), linhas_lidas = ?,
                        linhas_ignoradas = ?, erros = ?, avisos = ?, resumo = ? WHERE id = ?""",
                     (linhas_lidas, len(oc.linhas_ignoradas), oc.total_erros, oc.total_avisos,
                      json.dumps(resumo, ensure_ascii=False), imp))
        conn.execute("COMMIT")
    except ImportacaoRejeitada as e:
        conn.execute("ROLLBACK")
        conn.execute("INSERT INTO importacao (fonte, modo, status, arquivo, sha256, mensagem) VALUES (?, ?, ?, ?, ?, ?)",
                     (fonte, modo, "rejeitada", caminho.name, sha, str(e)))
        raise
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    return relatorio(conn, imp)


def relatorio(conn: sqlite3.Connection, importacao_id: int) -> dict:
    r = dict(conn.execute("SELECT * FROM importacao WHERE id = ?", (importacao_id,)).fetchone())
    r["resumo"] = json.loads(r["resumo"] or "{}")
    return r


def _verificar_remocao(entidade: str, removidos: int, ativos: int, forcar: bool) -> None:
    if forcar or ativos == 0 or removidos / ativos <= LIMITE_REMOCAO:
        return
    raise ImportacaoRejeitada(
        f"Esta importação desativaria {removidos} de {ativos} {entidade} ativos ({removidos / ativos:.0%}), "
        f"acima do limite de segurança de {LIMITE_REMOCAO:.0%}. Confira se a exportação está completa. "
        "Se estiver, importe de novo com --forcar, ou use --modo incremental para arquivos parciais.")


# ---------------------------------------------------------------------------
# Dimensões (get-or-create com cache em memória)
# ---------------------------------------------------------------------------

class _Dimensoes:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.novas: dict[str, int] = defaultdict(int)
        self.regiao = {(r["uf"], r["nome_norm"]): r["id"] for r in conn.execute("SELECT * FROM regiao_ensino")}
        self.cidade = {(r["uf"], r["nome_norm"]): r["id"] for r in conn.execute("SELECT * FROM cidade")}
        self.escola = {(r["uf"], r["cidade_id"], r["nome_norm"]): r["id"] for r in conn.execute("SELECT * FROM escola")}
        self.curso = {r["nome_norm"]: r["id"] for r in conn.execute("SELECT id, nome_norm FROM curso")}
        self.grupo = {r["nome_norm"]: r["id"] for r in conn.execute("SELECT id, nome_norm FROM grupo")}
        self.alias = {r["nome_norm"]: r["instituicao_id"] for r in conn.execute("SELECT * FROM instituicao_alias")}

    def _criar(self, cache: dict, chave, tipo: str, sql: str, params: tuple) -> int:
        if chave not in cache:
            cache[chave] = self.conn.execute(sql, params).lastrowid
            self.novas[tipo] += 1
        return cache[chave]

    def regiao_id(self, uf, nome, k):
        if not (uf and k):
            return None
        return self._criar(self.regiao, (uf, k), "regioes_ensino",
                           "INSERT INTO regiao_ensino (uf, nome, nome_norm) VALUES (?, ?, ?)", (uf, nome, k))

    def cidade_id(self, uf, nome, k):
        if not (uf and k):
            return None
        return self._criar(self.cidade, (uf, k), "cidades",
                           "INSERT INTO cidade (uf, nome, nome_norm) VALUES (?, ?, ?)", (uf, nome, k))

    def escola_id(self, uf, cidade_id, regiao_id, nome, k, bairro):
        if not (uf and k):
            return None
        return self._criar(self.escola, (uf, cidade_id or 0, k), "escolas",
                           "INSERT INTO escola (uf, cidade_id, regiao_ensino_id, nome, nome_norm, bairro) "
                           "VALUES (?, ?, ?, ?, ?, ?)", (uf, cidade_id or 0, regiao_id, nome, k, bairro))

    def curso_id(self, nome, k):
        return self._criar(self.curso, k, "cursos", "INSERT INTO curso (nome, nome_norm, grau) VALUES (?, ?, ?)",
                           (nome, k, norm.grau_curso(nome)))

    def grupo_id(self, nome):
        k = norm.chave(nome)
        if not k:
            return None
        return self._criar(self.grupo, k, "grupos", "INSERT INTO grupo (nome, nome_norm) VALUES (?, ?)", (nome, k))

    def instituicao_id(self, nome, k, origem):
        if k not in self.alias:
            iid = self.conn.execute(
                "INSERT INTO instituicao (nome, nome_norm, sigla, origem, qualidade) VALUES (?, ?, ?, ?, ?)",
                (nome, k, norm.sigla_instituicao(nome), origem,
                 "suspeita" if norm.instituicao_suspeita(nome) else "ok")).lastrowid
            self.conn.execute("INSERT INTO instituicao_alias VALUES (?, ?, 'automatico')", (k, iid))
            self.alias[k] = iid
            self.novas["instituicoes"] += 1
        return self.alias[k]


# ---------------------------------------------------------------------------
# Base de interessados
# ---------------------------------------------------------------------------

def _dados_aluno(r: dict, linha: int, oc: Ocorrencias) -> tuple:
    uf = norm.chave(r.get("uf"))
    if uf is not None and uf not in UFS_VALIDAS:
        oc.aviso("uf_invalida", "Estado não reconhecido; campo deixado vazio.", linha, "Estado", r.get("uf"))
        uf = None
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
            oc.aviso("booleano_invalido", "Valor deveria ser Sim/Não; campo deixado vazio.", linha, coluna, r.get(campo))
            booleanos.append(None)
    return (uf, norm.texto(r.get("cidade")), norm.texto(r.get("regiao_ensino")), norm.texto(r.get("escola")),
            norm.texto(r.get("bairro")), cadastrado_em, nascimento, norm.texto(r.get("genero")),
            norm.texto(r.get("situacao_atual")), norm.texto(r.get("plano_pos_medio")), booleanos[0], booleanos[1])


def _cursos(r: dict) -> list[tuple[int, str, str]]:
    vistos, saida = set(), []
    for pos in (1, 2, 3):
        nome = norm.texto(r.get(f"curso_{pos}"))
        k = norm.chave(nome)
        if k and k not in vistos:
            vistos.add(k)
            saida.append((pos, nome, k))
    return saida


def _preparar_leads(registros: list[dict], oc: Ocorrencias):
    alunos: dict[str, dict] = {}
    interesses: dict[tuple[str, int], tuple[str, str]] = {}
    assinaturas: dict[str, tuple] = {}
    suspeitas_avisadas: set[str] = set()
    for r in registros:
        linha = r["_linha"]
        bruto = norm.texto(r.get("aluno_id"))
        try:
            aluno_id = str(uuid.UUID(bruto)) if bruto else None
        except ValueError:
            aluno_id = None
        if aluno_id is None:
            oc.erro("id_invalido", "ID do aluno ausente ou inválido; linha ignorada.", linha, "ID", bruto)
            continue
        try:
            posicao = norm.inteiro(r.get("posicao"))
        except ValueError:
            oc.erro("posicao_invalida", "Posição da opção não é número; linha ignorada.", linha,
                    "Posição da opção de faculdade", r.get("posicao"))
            continue
        nome_inst = norm.texto(r.get("instituicao"))
        if nome_inst is not None and posicao is None:
            oc.erro("posicao_ausente", "Instituição informada sem a posição; linha ignorada.", linha,
                    "Posição da opção de faculdade")
            continue
        if posicao is not None and not 1 <= posicao <= 3:
            oc.erro("posicao_invalida", "Posição da opção deve ser 1, 2 ou 3; linha ignorada.", linha,
                    "Posição da opção de faculdade", posicao)
            continue
        if posicao is not None and nome_inst is None:
            oc.aviso("instituicao_ausente", "Posição informada sem instituição; só os dados do aluno entram.",
                     linha, "Instituição Privada")
            posicao = None

        assinatura = tuple(str(v) for k, v in sorted(r.items()) if k not in _COLUNAS_DA_LINHA)
        anterior = assinaturas.get(aluno_id)
        if anterior is None:
            assinaturas[aluno_id] = assinatura
            dados = _dados_aluno(r, linha, oc)
            cursos = _cursos(r)
            mods, desconhecidas = norm.modalidades(r.get("modalidade"))
            for termo in desconhecidas:
                oc.aviso("modalidade_desconhecida", "Modalidade não reconhecida; ignorada.", linha, "Modalidade", termo)
            alunos[aluno_id] = {"dados": dados, "cursos": cursos, "modalidades": mods,
                                "hash": _hash(*dados, *(c[2] for c in cursos), *mods)}
        elif anterior != assinatura:
            oc.aviso("aluno_divergente", "O mesmo ID aparece com dados de aluno diferentes; valem os da primeira linha.",
                     linha, "ID", aluno_id)

        if posicao is None:
            continue
        k = norm.chave(nome_inst)
        existente = interesses.get((aluno_id, posicao))
        if existente is not None:
            if existente[1] == k:
                oc.aviso("linha_repetida", "Linha repetida (mesmo aluno, posição e instituição); contada uma vez.",
                         linha, "ID", aluno_id)
            else:
                oc.erro("chave_duplicada",
                        f"Aluno com duas instituições diferentes na posição {posicao}; vale a primeira linha.",
                        linha, "Instituição Privada", nome_inst)
            continue
        interesses[(aluno_id, posicao)] = (nome_inst, k)
        if norm.instituicao_suspeita(nome_inst) and k not in suspeitas_avisadas:
            suspeitas_avisadas.add(k)
            oc.aviso("instituicao_suspeita", "Texto não parece instituição; entra marcado como suspeito.",
                     linha, "Instituição Privada", nome_inst)
    return alunos, interesses


def _contar(tipo: dict) -> dict:
    return {"novos": tipo.get("novo", 0), "atualizados": tipo.get("atualizado", 0),
            "reativados": tipo.get("reativado", 0), "inalterados": tipo.get("inalterado", 0)}


def _importar_leads(conn, imp: int, modo: str, registros: list[dict], oc: Ocorrencias, forcar: bool) -> dict:
    alunos, interesses = _preparar_leads(registros, oc)
    dim = _Dimensoes(conn)

    # ---------------- alunos ----------------
    atuais = {r["id"]: (r["hash"], r["ativo"]) for r in conn.execute("SELECT id, hash, ativo FROM aluno")}
    tipos: dict[str, str] = {}
    for aid, a in alunos.items():
        atual = atuais.get(aid)
        tipos[aid] = ("novo" if atual is None else "reativado" if not atual[1]
                      else "atualizado" if atual[0] != a["hash"] else "inalterado")
    removidos = [aid for aid, (_, ativo) in atuais.items() if ativo and aid not in alunos] if modo == "completo" else []
    _verificar_remocao("alunos", len(removidos), sum(1 for _, at in atuais.values() if at), forcar)

    linhas_aluno, cursos, modalidades, alterados = [], [], [], []
    for aid, a in alunos.items():
        if tipos[aid] == "inalterado":
            continue
        (uf, cidade, regiao, escola, bairro, cadastrado, nasc, genero, situacao, plano, comunic, relat) = a["dados"]
        regiao_id = dim.regiao_id(uf, regiao, norm.chave(regiao))
        cidade_id = dim.cidade_id(uf, cidade, norm.chave(cidade))
        escola_id = dim.escola_id(uf, cidade_id, regiao_id, escola, norm.chave(escola), bairro)
        linhas_aluno.append((aid, uf, cidade_id, regiao_id, escola_id,
                             cadastrado.isoformat() if cadastrado else None, cadastrado.year if cadastrado else None,
                             nasc.isoformat() if nasc else None, genero, situacao, plano,
                             comunic, relat, a["hash"], imp, imp))
        cursos += [(aid, pos, dim.curso_id(nome, k)) for pos, nome, k in a["cursos"]]
        modalidades += [(aid, m, ordem) for ordem, m in enumerate(a["modalidades"], start=1)]
        if tipos[aid] != "novo":
            alterados.append((aid,))
    conn.executemany("""
        INSERT INTO aluno (id, uf, cidade_id, regiao_ensino_id, escola_id, cadastrado_em, ano_cadastro,
            data_nascimento, genero, situacao_atual, plano_pos_medio, aceita_comunicados, concluiu_relatorio,
            hash, ativo, removido_em, importacao_criacao, importacao_alteracao)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, NULL, ?, ?)
        ON CONFLICT (id) DO UPDATE SET uf = excluded.uf, cidade_id = excluded.cidade_id,
            regiao_ensino_id = excluded.regiao_ensino_id, escola_id = excluded.escola_id,
            cadastrado_em = excluded.cadastrado_em, ano_cadastro = excluded.ano_cadastro,
            data_nascimento = excluded.data_nascimento, genero = excluded.genero,
            situacao_atual = excluded.situacao_atual, plano_pos_medio = excluded.plano_pos_medio,
            aceita_comunicados = excluded.aceita_comunicados, concluiu_relatorio = excluded.concluiu_relatorio,
            hash = excluded.hash, ativo = 1, removido_em = NULL, importacao_alteracao = excluded.importacao_alteracao
        """, linhas_aluno)
    conn.executemany("DELETE FROM aluno_curso WHERE aluno_id = ?", alterados)
    conn.executemany("DELETE FROM aluno_modalidade WHERE aluno_id = ?", alterados)
    conn.executemany("INSERT INTO aluno_curso VALUES (?, ?, ?)", cursos)
    conn.executemany("INSERT INTO aluno_modalidade VALUES (?, ?, ?)", modalidades)
    conn.executemany("UPDATE aluno SET ativo = 0, removido_em = datetime('now'), importacao_alteracao = ? "
                     "WHERE id = ?", [(imp, aid) for aid in removidos])
    resumo_alunos = {**_contar(_agrupar(tipos)), "removidos": len(removidos)}

    # ---------------- interesses ----------------
    atuais_i = {(r["aluno_id"], r["posicao"]): (r["hash"], r["ativo"])
                for r in conn.execute("SELECT aluno_id, posicao, hash, ativo FROM interesse")}
    tipos_i: dict[tuple, str] = {}
    linhas_i = []
    for chave, (nome, k) in interesses.items():
        h = _hash(k)
        atual = atuais_i.get(chave)
        tipo = ("novo" if atual is None else "reativado" if not atual[1]
                else "atualizado" if atual[0] != h else "inalterado")
        tipos_i[chave] = tipo
        if tipo != "inalterado":
            linhas_i.append((*chave, dim.instituicao_id(nome, k, "leads"), nome, h, imp, imp))
    # Completo: some tudo o que não veio. Incremental: só opções antigas dos alunos que vieram no arquivo.
    removidos_i = [c for c, (_, ativo) in atuais_i.items()
                   if ativo and c not in interesses and (modo == "completo" or c[0] in alunos)]
    if modo == "completo":
        _verificar_remocao("interesses", len(removidos_i), sum(1 for _, at in atuais_i.values() if at), forcar)
    conn.executemany("""
        INSERT INTO interesse (aluno_id, posicao, instituicao_id, nome_origem, hash, ativo, removido_em,
                               importacao_criacao, importacao_alteracao)
        VALUES (?, ?, ?, ?, ?, 1, NULL, ?, ?)
        ON CONFLICT (aluno_id, posicao) DO UPDATE SET instituicao_id = excluded.instituicao_id,
            nome_origem = excluded.nome_origem, hash = excluded.hash, ativo = 1, removido_em = NULL,
            importacao_alteracao = excluded.importacao_alteracao""", linhas_i)
    conn.executemany("UPDATE interesse SET ativo = 0, removido_em = datetime('now'), importacao_alteracao = ? "
                     "WHERE aluno_id = ? AND posicao = ?", [(imp, *c) for c in removidos_i])
    return {"alunos": resumo_alunos,
            "interesses": {**_contar(_agrupar(tipos_i)), "removidos": len(removidos_i)},
            "cadastros_novos": dict(dim.novas)}


def _agrupar(tipos: dict) -> dict:
    contagem: dict[str, int] = defaultdict(int)
    for t in tipos.values():
        contagem[t] += 1
    return contagem


# ---------------------------------------------------------------------------
# Base de instituições
# ---------------------------------------------------------------------------

def _linhas_validas(registros, oc: Ocorrencias, campo_nome: str, rotulo: str):
    vistos: set = set()
    for r in registros:
        linha = r["_linha"]
        nome = norm.texto(r.get(campo_nome))
        if nome is None:
            oc.erro("nome_ausente", f"{rotulo} sem nome; linha ignorada.", linha, rotulo)
            continue
        uf = norm.chave(r.get("uf"))
        if uf not in UFS_VALIDAS:
            oc.erro("uf_invalida", "UF ausente ou inválida; linha ignorada.", linha, "UF", r.get("uf"))
            continue
        try:
            ano = norm.inteiro(r.get("ano"))
            total = norm.inteiro(r.get("total")) or 0
            if ano is None or not 2000 <= ano <= 2100:
                raise ValueError
        except ValueError:
            oc.erro("valor_invalido", "Ano ou total inválido; linha ignorada.", linha, "Ano/Total")
            continue
        assinatura = tuple(str(v) for k, v in sorted(r.items()) if k != "_linha")
        if assinatura in vistos:
            oc.aviso("linha_repetida", "Linha idêntica a outra já lida; contada uma vez.", linha)
            continue
        vistos.add(assinatura)
        yield linha, uf, ano, nome, norm.chave(nome), total, r


def _importar_instituicoes(conn, abas: dict[str, list[dict]], oc: Ocorrencias) -> dict:
    if "universidades" not in abas:
        raise ImportacaoRejeitada("A base de instituições precisa da aba de universidades "
                                  "(colunas UF, Ano, Universidade, Total).")
    dim = _Dimensoes(conn)
    volumes: dict[tuple, int] = defaultdict(int)
    nomes: dict[str, str] = {}
    atributos: dict[str, dict[str, tuple[int, str]]] = defaultdict(dict)
    for linha, uf, ano, nome, k, total, r in _linhas_validas(abas["universidades"], oc, "instituicao", "Universidade"):
        nomes.setdefault(k, nome)
        volumes[(k, uf, ano)] += total
        for campo in ATRIBUTOS:
            valor = norm.valor_canonico(campo, r.get(campo))
            atual = atributos[k].get(campo)
            if valor is not None and (atual is None or ano >= atual[0]):
                atributos[k][campo] = (ano, valor)

    contagem = {"novas": 0, "atualizadas": 0, "inalteradas": 0}
    for k, nome in nomes.items():
        attrs = {c: atributos[k][c][1] if c in atributos[k] else None for c in ATRIBUTOS}
        h = _hash(*(attrs[c] for c in ATRIBUTOS))
        nova = k not in dim.alias
        iid = dim.instituicao_id(nome, k, "base_instituicoes")
        atual = conn.execute("SELECT hash_atributos FROM instituicao WHERE id = ?", (iid,)).fetchone()[0]
        if atual == h:
            contagem["inalteradas"] += 1
            continue
        contagem["novas" if nova else "atualizadas"] += 1
        conn.execute("""UPDATE instituicao SET grupo_id = ?, porte = ?, afiliado = ?, comissao_valor = ?,
                        tipo_comissao = ?, status_comercial = ?, hash_atributos = ?,
                        origem = CASE WHEN origem = 'leads' THEN 'base_instituicoes' ELSE origem END WHERE id = ?""",
                     (dim.grupo_id(attrs["grupo"]), attrs["porte"], attrs["afiliado"], norm.moeda(attrs["comissao"]),
                      attrs["tipo_comissao"], attrs["status_comercial"], h, iid))
    conn.execute("DELETE FROM volume_instituicao_anual")
    agregados: dict[tuple, int] = defaultdict(int)
    for (k, uf, ano), total in volumes.items():
        agregados[(dim.alias[k], uf, ano)] += total
    conn.executemany("INSERT INTO volume_instituicao_anual VALUES (?, ?, ?, ?)",
                     [(*c, t) for c, t in agregados.items()])
    resumo = {"instituicoes": {**contagem, "linhas_volume": len(agregados)}}

    if "cursos" in abas:
        vol_cursos: dict[tuple, int] = defaultdict(int)
        for _, uf, ano, nome, k, total, _ in _linhas_validas(abas["cursos"], oc, "curso", "Curso"):
            vol_cursos[(dim.curso_id(nome, k), uf, ano)] += total
        conn.execute("DELETE FROM volume_curso_anual")
        conn.executemany("INSERT INTO volume_curso_anual VALUES (?, ?, ?, ?)", [(*c, t) for c, t in vol_cursos.items()])
        resumo["volume_cursos"] = {"linhas_volume": len(vol_cursos)}
    nao_usadas = [a for a in abas if a not in ("universidades", "cursos", "leads")]
    if nao_usadas:
        resumo["abas_lidas_nao_usadas_no_cowork"] = nao_usadas
    resumo["cadastros_novos"] = dict(dim.novas)
    return resumo


def _gravar_snapshot(conn, imp: int) -> None:
    """Fotografia das métricas desta importação (comparação entre importações)."""
    conn.execute("""
        INSERT INTO snapshot_metrica (importacao_id, dimensao, chave, rotulo, alunos, interesses)
        SELECT ?, 'total', 'total', 'Total', count(DISTINCT aluno_id), count(*) FROM v_interesse WHERE qualidade = 'ok'
        UNION ALL
        SELECT ?, 'instituicao', v.instituicao_id, i.nome, count(DISTINCT v.aluno_id), count(*)
        FROM v_interesse v JOIN instituicao i ON i.id = v.instituicao_id WHERE v.qualidade = 'ok'
        GROUP BY v.instituicao_id
        UNION ALL
        SELECT ?, 'curso', ac.curso_id, c.nome, count(*), 0
        FROM aluno_curso ac JOIN aluno a ON a.id = ac.aluno_id AND a.ativo = 1 JOIN curso c ON c.id = ac.curso_id
        GROUP BY ac.curso_id
        UNION ALL
        SELECT ?, 'uf', uf, uf, count(*), 0 FROM aluno WHERE ativo = 1 AND uf IS NOT NULL GROUP BY uf
        UNION ALL
        SELECT ?, 'cidade', a.cidade_id, c.nome || ' (' || c.uf || ')', count(*), 0
        FROM aluno a JOIN cidade c ON c.id = a.cidade_id WHERE a.ativo = 1 GROUP BY a.cidade_id
        """, (imp, imp, imp, imp, imp))
