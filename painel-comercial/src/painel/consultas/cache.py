"""Cache de consultas atrelado à versão da base.

A chave inclui imp.estado.versao, que avança a cada importação. Por isso o cache
nunca devolve número desatualizado e não precisa de expiração por tempo.
Em memória por processo; com várias instâncias da API, trocar por Redis (mesma interface).
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any, Callable

import psycopg

_LIMITE_ITENS = 2000
_TTL_VERSAO_S = 2.0           # evita ler a versão do banco a cada chamada em rajadas

_itens: OrderedDict[tuple, Any] = OrderedDict()
_trava = threading.Lock()
_versao_lida: tuple[float, int] = (0.0, -1)


def versao(conn: psycopg.Connection) -> int:
    global _versao_lida
    agora = time.monotonic()
    if agora - _versao_lida[0] > _TTL_VERSAO_S:
        v = conn.execute("SELECT versao FROM imp.estado").fetchone()["versao"]
        _versao_lida = (agora, v)
    return _versao_lida[1]


def obter(conn: psycopg.Connection, chave: tuple, calcular: Callable[[], Any]) -> Any:
    k = (versao(conn), *chave)
    with _trava:
        if k in _itens:
            _itens.move_to_end(k)
            return _itens[k]
    valor = calcular()
    with _trava:
        _itens[k] = valor
        while len(_itens) > _LIMITE_ITENS:
            _itens.popitem(last=False)
    return valor


def limpar() -> None:
    global _versao_lida
    with _trava:
        _itens.clear()
        _versao_lida = (0.0, -1)
