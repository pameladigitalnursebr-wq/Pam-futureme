"""Conexões com o PostgreSQL e execução das migrations."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import config

PASTA_MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"

_pool: ConnectionPool | None = None


def pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            config().database_url,
            min_size=1,
            max_size=10,
            kwargs={"row_factory": dict_row},
            open=True,
        )
    return _pool


def fechar_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def conexao() -> Iterator[psycopg.Connection]:
    """Conexão do pool; faz commit ao sair sem erro e rollback se houver exceção."""
    with pool().connection() as conn:
        yield conn


def migrar(conn: psycopg.Connection | None = None) -> list[str]:
    """Aplica, em ordem, as migrations ainda não aplicadas. Devolve as aplicadas agora."""
    if conn is None:
        with conexao() as c:
            return migrar(c)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS public.schema_migracao ("
        " versao text PRIMARY KEY, aplicado_em timestamptz NOT NULL DEFAULT now())"
    )
    aplicadas = {r["versao"] if isinstance(r, dict) else r[0]
                 for r in conn.execute("SELECT versao FROM public.schema_migracao")}
    novas = []
    for arquivo in sorted(PASTA_MIGRATIONS.glob("*.sql")):
        if arquivo.stem in aplicadas:
            continue
        conn.execute(arquivo.read_text(encoding="utf-8"))
        conn.execute("INSERT INTO public.schema_migracao (versao) VALUES (%s)", (arquivo.stem,))
        novas.append(arquivo.stem)
    conn.commit()
    return novas
