"""Configuração lida do ambiente (variáveis PAINEL_*). Ver .env.example."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def _carregar_dotenv(caminho: Path) -> None:
    """Carrega um .env simples (CHAVE=valor) sem sobrescrever o ambiente."""
    if not caminho.is_file():
        return
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        os.environ.setdefault(chave.strip(), valor.strip())


@dataclass(frozen=True)
class Config:
    database_url: str
    secret_key: str
    dominio_email: str
    sessao_horas: int
    limite_remocao: float
    cookie_seguro: bool
    hosts_mcp: tuple[str, ...]


@lru_cache
def config() -> Config:
    _carregar_dotenv(Path.cwd() / ".env")
    secret = os.environ.get("PAINEL_SECRET_KEY", "")
    if not secret:
        raise RuntimeError("Defina PAINEL_SECRET_KEY (ver .env.example).")
    return Config(
        database_url=os.environ.get("PAINEL_DATABASE_URL", "postgresql://localhost/painel"),
        secret_key=secret,
        dominio_email=os.environ.get("PAINEL_DOMINIO_EMAIL", "futureme.tech").lower(),
        sessao_horas=int(os.environ.get("PAINEL_SESSAO_HORAS", "12")),
        limite_remocao=float(os.environ.get("PAINEL_LIMITE_REMOCAO", "0.20")),
        cookie_seguro=os.environ.get("PAINEL_COOKIE_SEGURO", "true").lower() != "false",
        hosts_mcp=tuple(h.strip() for h in os.environ.get("PAINEL_HOSTS_MCP", "").split(",") if h.strip()),
    )
