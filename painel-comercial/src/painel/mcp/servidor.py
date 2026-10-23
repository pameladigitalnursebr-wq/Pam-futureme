"""Ferramentas MCP usadas pelo Claude. Só leitura, sem dados pessoais.

Os filtros chegam por NOME ("UNIP", "Medicina", "Campinas") e são resolvidos aqui para
os valores exatos da base, usando a mesma busca do painel. Nome ambíguo não vira filtro:
a ferramenta devolve as opções para o Claude perguntar à pessoa.
"""

from __future__ import annotations

import time
from typing import Any, Literal

from mcp.server.mcpserver import Context, MCPServer
from pydantic import BaseModel, Field

from ..consultas import metricas
from ..consultas.filtros import DIMENSOES, Filtros
from ..db import conexao
from ..seguranca import permissoes
from ..seguranca.usuarios import Usuario, registrar_consulta

INSTRUCOES = """\
Base de inteligência comercial da FutureMe: alunos do ensino médio (escolas públicas de SP, RJ, MT e TO)
interessados em instituições de ensino superior privadas.

Como ler os números:
- "alunos" = alunos distintos. "interesses" = opções de instituição; cada aluno escolhe até 3 (1ª, 2ª, 3ª opção).
  Para "quantos interessados", responda com alunos e cite interesses quando ajudar.
- Cursos (pódio) e modalidade são preferências do ALUNO, não da instituição. Curso + instituição juntos significa
  "alunos com o curso no pódio que escolheram a instituição".
- Estado, cidade e região são os da ESCOLA do aluno (origem da demanda), não da instituição.
- Não existem na base: turno, nome do aluno, localização da instituição.
Fluxo: use `buscar` quando não souber o nome exato; depois `resumo`/`ranking` com filtros por nome.
Sempre informe a data da base (campo base_atualizada_em) e repasse os avisos que vierem na resposta.
"""

Dimensao = Literal[
    "instituicao", "grupo", "posicao", "status_comercial", "curso", "modalidade", "uf", "regiao_geografica",
    "regiao_ensino", "cidade", "escola", "ano_cadastro", "faixa_etaria", "genero", "situacao_atual",
    "plano_pos_medio", "aceita_comunicados",
]


class FiltrosNome(BaseModel):
    """Filtros cumulativos (E entre campos; OU entre valores do mesmo campo). Use nomes como aparecem na fala."""

    instituicao: list[str] | None = Field(None, description="Ex.: ['UNIP', 'Mackenzie']")
    grupo: list[str] | None = Field(None, description="Grupo educacional. Ex.: ['Cogna']")
    curso: list[str] | None = Field(None, description="Ex.: ['Medicina', 'Administração']")
    modalidade: list[str] | None = Field(None, description="Presencial, Híbrido ou Online (EAD)")
    uf: list[str] | None = Field(None, description="Sigla do estado da escola do aluno. Ex.: ['SP']")
    cidade: list[str] | None = Field(None, description="Cidade da escola do aluno. Ex.: ['Campinas']")
    regiao_ensino: list[str] | None = Field(None, description="Região/diretoria de ensino")
    regiao_geografica: list[str] | None = Field(None, description="Sudeste, Sul, Norte, Nordeste, Centro-Oeste")
    escola: list[str] | None = None
    posicao: list[int] | None = Field(None, description="Posição da opção: 1, 2 e/ou 3")
    ano_cadastro: list[int] | None = Field(None, description="Ano de cadastro do aluno. Ex.: [2026]")
    genero: list[str] | None = None
    faixa_etaria: list[str] | None = None
    status_comercial: list[str] | None = Field(None, description="Ex.: ['Já cliente']")
    incluir_suspeitas: bool = Field(False, description="Incluir respostas livres que não parecem instituição")


class _Ambiguo(Exception):
    def __init__(self, dimensao: str, termo: str, opcoes: list[dict]):
        self.dimensao, self.termo, self.opcoes = dimensao, termo, opcoes


def _resolver(conn, filtros: FiltrosNome | None) -> tuple[Filtros, list[dict]]:
    """Nomes -> valores da base. Devolve os filtros e o que foi considerado em cada um."""
    if filtros is None:
        return Filtros(), []
    dados = filtros.model_dump(exclude_none=True)
    suspeitas = dados.pop("incluir_suspeitas", False)
    valores: dict[str, list] = {}
    considerados: list[dict] = []
    for dim, termos in dados.items():
        if DIMENSOES[dim].tipo == "int" and not DIMENSOES[dim].tabela:
            valores[dim] = list(termos)
            continue
        escolhidos: list[dict] = []
        for termo in termos:
            opcoes = metricas.valores(conn, dim, str(termo), limite=10)
            if not opcoes:
                raise _Ambiguo(dim, str(termo), [])
            exatos = [o for o in opcoes if o.get("exato")]
            if exatos:
                escolhidos += exatos          # grafias equivalentes do mesmo nome entram juntas
            elif len(opcoes) == 1 or opcoes[0]["alunos"] >= 0.8 * sum(o["alunos"] for o in opcoes):
                escolhidos.append(opcoes[0])
            else:
                raise _Ambiguo(dim, str(termo), opcoes)
        valores[dim] = [o["chave"] for o in escolhidos]
        considerados.append({"filtro": dim, "valores": [o["rotulo"] for o in escolhidos]})
    return Filtros(valores, suspeitas), considerados


# ---------------------------------------------------------------------------
# Contexto: quem está consultando
# ---------------------------------------------------------------------------

_usuario_stdio: Usuario | None = None


def _usuario(ctx: Context | None) -> Usuario:
    try:
        req = ctx.request_context.request if ctx else None
        u = getattr(req.state, "usuario", None) if req is not None else None
    except (AttributeError, LookupError, ValueError):
        u = None
    u = u or _usuario_stdio
    if u is None or not u.pode(permissoes.CONSULTAR):
        raise PermissionError("Acesso negado: chave de API sem permissão de consulta.")
    return u


def _executar(ctx: Context | None, operacao: str, parametros: dict, funcao) -> dict[str, Any]:
    usuario = _usuario(ctx)
    inicio = time.monotonic()
    with conexao() as conn:
        try:
            resultado = funcao(conn)
        except _Ambiguo as a:
            if not a.opcoes:
                resultado = {"encontrado": False,
                             "mensagem": f"Nenhum valor de '{a.dimensao}' corresponde a '{a.termo}' na base."}
            else:
                resultado = {"ambiguo": True, "filtro": a.dimensao, "termo": a.termo,
                             "mensagem": "Mais de um valor corresponde ao termo. Pergunte qual a pessoa quer, "
                                         "ou repita a consulta com o nome exato.",
                             "opcoes": [{"nome": o["rotulo"], "alunos": o["alunos"]} for o in a.opcoes]}
        estado = conn.execute("SELECT atualizado_em FROM imp.estado").fetchone()
    resultado["base_atualizada_em"] = estado["atualizado_em"].isoformat()
    registrar_consulta(usuario.id, "mcp", operacao, parametros, int((time.monotonic() - inicio) * 1000))
    return resultado


def _limpar_itens(itens: list[dict]) -> list[dict]:
    return [{"nome": i["rotulo"], "alunos": i["alunos"], "interesses": i["interesses"],
             "percentual_dos_alunos": i["percentual"]} for i in itens]


# ---------------------------------------------------------------------------
# Servidor e ferramentas
# ---------------------------------------------------------------------------

servidor = MCPServer(name="painel-comercial", title="Painel Comercial FutureMe", instructions=INSTRUCOES)


@servidor.tool(description="Situação da base: data da última importação, totais e período coberto.")
def status_base(ctx: Context) -> dict[str, Any]:
    def f(conn):
        s = metricas.status_base(conn)
        return {"alunos": s["alunos"], "interesses": s["interesses"],
                "instituicoes_com_interesse": s["instituicoes_com_interesse"], "estados": s["estados"],
                "cadastros_de": s["primeiro_cadastro"].date().isoformat() if s["primeiro_cadastro"] else None,
                "cadastros_ate": s["ultimo_cadastro"].date().isoformat() if s["ultimo_cadastro"] else None,
                "ultimas_importacoes": {k: {"arquivo": v["arquivo_nome"], "em": v["concluido_em"].isoformat(),
                                            "linhas": v["linhas_lidas"]}
                                        for k, v in s["ultimas_importacoes"].items()}}
    return _executar(ctx, "status_base", {}, f)


@servidor.tool(description="Procura nomes na base (instituições, cursos, cidades, escolas, grupos, regiões). "
                           "Use para descobrir o nome exato antes de filtrar. 'dimensao' restringe a busca.")
def buscar(termo: str, ctx: Context, dimensao: Dimensao | None = None, limite: int = 8) -> dict[str, Any]:
    def f(conn):
        if dimensao:
            return {"dimensao": dimensao, "resultados": _limpar_itens(metricas.valores(conn, dimensao, termo, limite))}
        r = metricas.busca_rapida(conn, termo, limite)
        return {"termo": termo, "resultados": {g["dimensao"]: _limpar_itens(g["itens"]) for g in r["grupos"]}}
    return _executar(ctx, "buscar", {"termo": termo, "dimensao": dimensao}, f)


@servidor.tool(description="Totais para qualquer combinação de filtros: alunos distintos, interesses, "
                           "instituições, cursos, estados, cidades e escolas. Responde 'quantos interessados...'.")
def resumo(ctx: Context, filtros: FiltrosNome | None = None) -> dict[str, Any]:
    def f(conn):
        filtro, considerados = _resolver(conn, filtros)
        r = metricas.resumo(conn, filtro)
        r.pop("filtros", None)
        return {**r, "filtros_aplicados": considerados}
    return _executar(ctx, "resumo", {"filtros": filtros.model_dump(exclude_none=True) if filtros else {}}, f)


@servidor.tool(description="Ranking/distribuição por uma dimensão (top instituições, cursos mais procurados, "
                           "distribuição por estado, cidade, modalidade...), com filtros opcionais.")
def ranking(dimensao: Dimensao, ctx: Context, filtros: FiltrosNome | None = None, limite: int = 10) -> dict[str, Any]:
    def f(conn):
        filtro, considerados = _resolver(conn, filtros)
        r = metricas.ranking(conn, dimensao, filtro, min(limite, 100))
        return {"dimensao": r["titulo"], "itens": _limpar_itens(r["itens"]),
                "total_de_valores": r["total_valores"], "alunos_no_recorte": r["alunos_no_recorte"],
                "filtros_aplicados": considerados, "avisos": r["avisos"]}
    return _executar(ctx, "ranking", {"dimensao": dimensao,
                                      "filtros": filtros.model_dump(exclude_none=True) if filtros else {}}, f)


@servidor.tool(description="Amostra de alunos do recorte (sem dados pessoais): escola, cidade, cursos, "
                           "modalidades e as 3 opções de instituição.")
def detalhar(ctx: Context, filtros: FiltrosNome | None = None, pagina: int = 1, por_pagina: int = 20) -> dict[str, Any]:
    def f(conn):
        filtro, considerados = _resolver(conn, filtros)
        r = metricas.detalhe(conn, filtro, pagina, min(por_pagina, 50), dados_pessoais=False)
        for item in r["itens"]:
            item.pop("aluno", None)
        return {"total_alunos": r["total"], "pagina": r["pagina"], "paginas": r["paginas"], "alunos": r["itens"],
                "filtros_aplicados": considerados, "avisos": r["avisos"]}
    return _executar(ctx, "detalhar", {"filtros": filtros.model_dump(exclude_none=True) if filtros else {},
                                       "pagina": pagina}, f)


def _uma_chave(conn, dimensao: str, nome: str) -> tuple[Any, str]:
    opcoes = metricas.valores(conn, dimensao, nome, limite=10)
    exatos = [o for o in opcoes if o.get("exato")]
    escolha = exatos[0] if exatos else (opcoes[0] if len(opcoes) == 1 else None)
    if escolha is None:
        raise _Ambiguo(dimensao, nome, opcoes)
    return escolha["chave"], escolha["rotulo"]


@servidor.tool(description="Total de leads por ano (2023 em diante, base de instituições) para uma instituição "
                           "ou um curso. Mostra crescimento ano a ano.")
def historico_anual(dimensao: Literal["instituicao", "curso"], nome: str, ctx: Context) -> dict[str, Any]:
    def f(conn):
        chave, _ = _uma_chave(conn, dimensao, nome)
        r = metricas.historico_anual(conn, dimensao, chave)
        return {"nome": r["rotulo"], "por_ano": r["por_ano"], "por_ano_e_uf": r["por_ano_uf"], "fonte": r["fonte"]}
    return _executar(ctx, "historico_anual", {"dimensao": dimensao, "nome": nome}, f)


@servidor.tool(description="Variação entre importações: quem mais ganhou ou perdeu alunos interessados desde a "
                           "importação anterior (instituicao, curso, uf, cidade ou grupo).")
def comparar_importacoes(dimensao: Literal["instituicao", "curso", "uf", "cidade", "grupo"], ctx: Context,
                         limite: int = 15) -> dict[str, Any]:
    def f(conn):
        return metricas.comparar_importacoes(conn, dimensao, limite=min(limite, 50))
    return _executar(ctx, "comparar_importacoes", {"dimensao": dimensao}, f)


def executar_stdio(email: str) -> None:
    """Modo local (Claude Desktop / Claude Code): as consultas ficam registradas em nome deste usuário."""
    global _usuario_stdio
    from ..seguranca.usuarios import _carregar, buscar_por_email
    u = buscar_por_email(email)
    if u is None:
        raise SystemExit(f"Usuário {email} não encontrado.")
    _usuario_stdio = _carregar(u["id"])
    servidor.run("stdio")

