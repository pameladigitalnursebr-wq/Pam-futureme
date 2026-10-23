"""Consultas do painel: resumo, rankings, busca, detalhe, exportação e histórico."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response

from ..consultas import exportacao, metricas
from ..consultas.filtros import DIMENSOES, FiltroInvalido, Filtros
from ..db import conexao
from ..seguranca import permissoes as P
from ..seguranca.usuarios import Usuario, registrar_consulta
from .autenticacao import exigir

rotas = APIRouter(prefix="/api", tags=["consultas"])
consultar = exigir(P.CONSULTAR)


def filtros_da_url(request: Request) -> Filtros:
    """Filtros vêm na URL (?instituicao=12,15&uf=SP): o link compartilhado reabre a mesma consulta."""
    dados = {k: v for k, v in request.query_params.items() if k in DIMENSOES or k == "incluir_suspeitas"}
    try:
        return Filtros.de_dict(dados)
    except FiltroInvalido as e:
        raise HTTPException(400, str(e)) from e


def _executar(usuario: Usuario, operacao: str, parametros: dict, funcao) -> Any:
    inicio = time.monotonic()
    with conexao() as conn:
        try:
            resultado = funcao(conn)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
    registrar_consulta(usuario.id, "api" if usuario.via_chave else "web", operacao, parametros,
                       int((time.monotonic() - inicio) * 1000))
    return resultado


@rotas.get("/dimensoes")
def dimensoes(usuario: Usuario = Depends(consultar)) -> list[dict]:
    return [{"nome": d.nome, "titulo": d.titulo, "nivel": d.nivel} for d in DIMENSOES.values()]


@rotas.get("/dimensoes/{dimensao}/valores")
def valores(dimensao: str, q: str = "", limite: int = Query(20, le=100),
            usuario: Usuario = Depends(consultar)) -> list[dict]:
    with conexao() as conn:
        try:
            return metricas.valores(conn, dimensao, q, limite)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e


@rotas.get("/dimensoes/{dimensao}/rotulos")
def rotulos(dimensao: str, chaves: str, usuario: Usuario = Depends(consultar)) -> dict:
    """Nomes de valores já selecionados (para reabrir um link com filtros)."""
    if dimensao not in DIMENSOES:
        raise HTTPException(400, "Dimensão desconhecida.")
    f = Filtros.de_dict({dimensao: chaves})
    with conexao() as conn:
        return {str(k): v for k, v in metricas.rotulos(conn, DIMENSOES[dimensao], f.valores.get(dimensao, [])).items()}


@rotas.get("/busca")
def busca(q: str, usuario: Usuario = Depends(consultar)) -> dict:
    return _executar(usuario, "busca", {"q": q}, lambda c: metricas.busca_rapida(c, q))


@rotas.get("/resumo")
def resumo(f: Filtros = Depends(filtros_da_url), usuario: Usuario = Depends(consultar)) -> dict:
    return _executar(usuario, "resumo", f.como_dict(), lambda c: metricas.resumo(c, f))


@rotas.get("/ranking/{dimensao}")
def ranking(dimensao: str, limite: int = Query(10, ge=1, le=500), deslocamento: int = Query(0, ge=0),
            f: Filtros = Depends(filtros_da_url), usuario: Usuario = Depends(consultar)) -> dict:
    return _executar(usuario, "ranking", {"dimensao": dimensao, **f.como_dict()},
                     lambda c: metricas.ranking(c, dimensao, f, limite, deslocamento))


@rotas.get("/detalhe")
def detalhe(pagina: int = Query(1, ge=1), por_pagina: int = Query(50, ge=1, le=500), ordenar: str = "recentes",
            f: Filtros = Depends(filtros_da_url), usuario: Usuario = Depends(consultar)) -> dict:
    return _executar(usuario, "detalhe", {"pagina": pagina, **f.como_dict()},
                     lambda c: metricas.detalhe(c, f, pagina, por_pagina, ordenar, usuario.pode(P.DADOS_PESSOAIS)))


@rotas.get("/exportar")
def exportar(formato: str = Query("xlsx", pattern="^(csv|xlsx)$"), tipo: str = Query("detalhe",
             pattern="^(detalhe|ranking)$"), dimensao: str | None = None, f: Filtros = Depends(filtros_da_url),
             usuario: Usuario = Depends(exigir(P.EXPORTAR))) -> Response:
    conteudo, media, nome = _executar(
        usuario, "exportar", {"formato": formato, "tipo": tipo, "dimensao": dimensao, **f.como_dict()},
        lambda c: exportacao.exportar(c, f, formato, tipo, dimensao, usuario.pode(P.DADOS_PESSOAIS)))
    return Response(conteudo, media_type=media, headers={"Content-Disposition": f'attachment; filename="{nome}"'})


@rotas.get("/historico/{dimensao}/{chave}")
def historico(dimensao: str, chave: int, usuario: Usuario = Depends(consultar)) -> dict:
    return _executar(usuario, "historico", {"dimensao": dimensao, "chave": chave},
                     lambda c: metricas.historico_anual(c, dimensao, chave))


@rotas.get("/evolucao/{dimensao}/{chave}")
def evolucao(dimensao: str, chave: str, usuario: Usuario = Depends(consultar)) -> dict:
    with conexao() as conn:
        return metricas.evolucao(conn, dimensao, chave)


@rotas.get("/comparacao/{dimensao}")
def comparacao(dimensao: str, anterior: int | None = None, atual: int | None = None, limite: int = 20,
               usuario: Usuario = Depends(consultar)) -> dict:
    with conexao() as conn:
        return metricas.comparar_importacoes(conn, dimensao, anterior, atual, limite)


@rotas.get("/status")
def status(usuario: Usuario = Depends(consultar)) -> dict:
    with conexao() as conn:
        return metricas.status_base(conn)
