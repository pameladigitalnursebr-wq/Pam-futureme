"""Aplicação web: API REST (/api), painel (/), documentação (/docs) e endpoint MCP (/mcp)."""

from __future__ import annotations

import contextlib
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from .. import __version__
from ..config import config
from ..db import fechar_pool
from ..mcp.servidor import servidor as servidor_mcp
from ..seguranca import permissoes
from ..seguranca.usuarios import usuario_da_chave
from . import rotas_admin, rotas_consulta

PASTA_WEB = Path(__file__).resolve().parent.parent / "web"


class AutenticacaoMCP:
    """Exige chave de API com permissão de consulta no endpoint MCP.

    A chave vai no cabeçalho Authorization: Bearer <chave> ou, para conectores que não
    permitem cabeçalho, no parâmetro ?chave=<chave> da URL.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        chave = ""
        for nome, valor in scope.get("headers", []):
            if nome == b"authorization" and valor.lower().startswith(b"bearer "):
                chave = valor[7:].decode().strip()
        if not chave:
            from urllib.parse import parse_qs
            chave = (parse_qs(scope.get("query_string", b"").decode()).get("chave") or [""])[0]
        usuario = usuario_da_chave(chave) if chave else None
        if usuario is None or not usuario.pode(permissoes.CONSULTAR):
            await JSONResponse({"erro": "Chave de API ausente, inválida ou sem escopo de consulta."},
                               status_code=401)(scope, receive, send)
            return
        scope.setdefault("state", {})["usuario"] = usuario
        await self.app(scope, receive, send)


def criar_app() -> FastAPI:
    hosts = list(config().hosts_mcp)
    seguranca = TransportSecuritySettings(
        enable_dns_rebinding_protection=bool(hosts),
        allowed_hosts=hosts + ["127.0.0.1:*", "localhost:*"],
        allowed_origins=[f"https://{h}" for h in hosts] + ["https://claude.ai"],
    )
    app_mcp = servidor_mcp.streamable_http_app(streamable_http_path="/mcp", stateless_http=True,
                                               json_response=True, transport_security=seguranca)

    @contextlib.asynccontextmanager
    async def ciclo_de_vida(app: FastAPI):
        async with servidor_mcp.session_manager.run():
            yield
        fechar_pool()

    app = FastAPI(title="Painel de Inteligência Comercial — FutureMe", version=__version__, lifespan=ciclo_de_vida)
    app.include_router(rotas_consulta.rotas)
    app.include_router(rotas_admin.rotas)
    app.mount("/static", StaticFiles(directory=PASTA_WEB), name="static")

    @app.get("/", include_in_schema=False)
    def painel() -> FileResponse:
        return FileResponse(PASTA_WEB / "index.html")

    @app.get("/saude", include_in_schema=False)
    def saude() -> dict:
        return {"ok": True, "versao": __version__}

    # Por último: o app MCP responde em /mcp; as rotas acima têm prioridade.
    app.mount("/", AutenticacaoMCP(app_mcp))
    return app
