"""Quem está chamando: sessão do painel (cookie) ou chave de API (Authorization: Bearer)."""

from __future__ import annotations

from typing import Callable

from fastapi import Depends, HTTPException, Request

from ..seguranca.usuarios import Usuario, usuario_da_chave, usuario_da_sessao

COOKIE_SESSAO = "painel_sessao"


def identificar(request: Request) -> Usuario | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return usuario_da_chave(auth[7:].strip())
    token = request.cookies.get(COOKIE_SESSAO)
    return usuario_da_sessao(token) if token else None


def usuario_atual(request: Request) -> Usuario:
    u = identificar(request)
    if u is None:
        raise HTTPException(401, "Faça login para continuar.")
    request.state.usuario = u
    return u


def exigir(permissao: str) -> Callable[[Usuario], Usuario]:
    def dependencia(usuario: Usuario = Depends(usuario_atual)) -> Usuario:
        if not usuario.pode(permissao):
            raise HTTPException(403, "Seu perfil não tem permissão para esta ação.")
        return usuario
    return dependencia
