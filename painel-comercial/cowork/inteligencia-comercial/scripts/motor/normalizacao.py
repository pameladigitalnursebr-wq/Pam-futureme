# Cópia gerada por cowork/montar.py a partir de src/painel/normalizacao.py. Não edite aqui.
"""Regras de normalização de texto e valores, compartilhadas por importação e consultas.

Normalizar é o que permite ligar as duas bases sem ID: dois textos representam a
mesma coisa somente se a forma normalizada for idêntica (nada de "parecido").
"""

from __future__ import annotations

import math
import re
import unicodedata
from datetime import date, datetime, timedelta
from functools import lru_cache

_ESPACOS = re.compile(r"\s+")
# Marcadores de "sem valor" comuns em exportações. São tratados como vazio por regra explícita,
# independentemente da biblioteca usada para ler a planilha.
_NULOS = {"N/A", "#N/A", "NULL", "NAN", "NONE", "#REF!", "#VALUE!", "#DIV/0!"}
_ASPAS = re.compile(r"[\"“”'`´]")


def sem_acento(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")


def vazio(valor: object) -> bool:
    if valor is None:
        return True
    if isinstance(valor, float) and math.isnan(valor):
        return True
    if isinstance(valor, str):
        t = valor.strip()
        return not t or t.upper() in _NULOS
    try:  # pandas.NA / NaT
        return bool(valor != valor)
    except (TypeError, ValueError):
        return False


@lru_cache(maxsize=262_144)
def _texto_str(valor: str) -> str | None:
    t = _ESPACOS.sub(" ", valor).strip()
    return None if not t or t.upper() in _NULOS else t


@lru_cache(maxsize=262_144)
def _chave_str(t: str) -> str | None:
    t = _ASPAS.sub("", sem_acento(t)).upper()
    return _ESPACOS.sub(" ", t).strip() or None


def texto(valor: object) -> str | None:
    """Texto limpo para exibição (espaços colapsados), ou None se vazio."""
    if isinstance(valor, str):
        return _texto_str(valor)
    if vazio(valor):
        return None
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    return _texto_str(str(valor))


def chave(valor: object) -> str | None:
    """Forma normalizada usada como chave de ligação: MAIÚSCULAS, sem acento e sem aspas."""
    t = texto(valor)
    return None if t is None else _chave_str(t)


def chave_coluna(nome: object) -> str:
    """Normaliza cabeçalhos: 'Criado em...' -> 'criado em'."""
    t = sem_acento(str(nome or "")).lower()
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return t.strip()


# ---------------------------------------------------------------------------
# Instituições
# ---------------------------------------------------------------------------

def sigla_instituicao(nome: str) -> str | None:
    """'UNIP - UNIVERSIDADE PAULISTA' -> 'UNIP'."""
    if " - " in nome:
        sigla = nome.split(" - ", 1)[0].strip()
        if 1 < len(sigla) <= 20:
            return sigla
    return None


def instituicao_suspeita(nome: str) -> bool:
    """Texto livre que provavelmente não é uma instituição ('3', 'privado', datas...)."""
    k = chave(nome) or ""
    letras = re.sub(r"[^A-Z]", "", k)
    if len(letras) < 3:
        return True
    k = re.sub(r"[^A-Z0-9 ]", "", k).strip()
    if k.startswith(("NAO SEI", "NENHUM", "NEMNHUM", "AINDA NAO")):
        return True
    if k in {"PRIVADO", "PRIVADA", "PUBLICA", "PUBLICO", "NAO SEI", "NENHUMA", "NENHUM",
             "OUTRA", "OUTRO", "OUTROS", "ESC", "ESCOLA", "FACULDADE", "UNIVERSIDADE", "TESTE"}:
        return True
    return False


# Grafias equivalentes nos atributos comerciais da Base 1.
_VALORES_CANONICOS = {
    "porte": {"GRUPOS EDUCACIONAIS": "Grupos educacionais", "GRANDES GRUPOS": "Grandes grupos",
              "GRANDE": "Grande", "MEDIA": "Média", "PEQUENA": "Pequena"},
    "afiliado": {"PROGRAMA PROPRIO": "Programa próprio", "NAO TEM": "Não tem"},
}


def valor_canonico(campo: str, valor: object) -> str | None:
    """Unifica grafias ('Programa Próprio' e 'Programa próprio'; 'Não têm' e 'Não tem')."""
    t = texto(valor)
    if t is None:
        return None
    return _VALORES_CANONICOS.get(campo, {}).get(chave(t), t)


def moeda(valor: object) -> float | None:
    """'R$ 1.300,50' | 'R$ 300.00' | 300 -> 300.0"""
    if vazio(valor):
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    t = re.sub(r"[^0-9,.\-]", "", str(valor))
    if not t:
        return None
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".") else t.replace(",", "")
    elif "," in t:
        t = t.replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Cursos e modalidades
# ---------------------------------------------------------------------------

def grau_curso(nome: str) -> str:
    k = chave(nome) or ""
    if k.startswith("TECNICO EM") or k.startswith("TECNICO "):
        return "Técnico"
    if k.endswith("BACHARELADO"):
        return "Bacharelado"
    if k.endswith("LICENCIATURA"):
        return "Licenciatura"
    if k.endswith("TECNOLOGICO") or k.endswith("TECNOLOGO"):
        return "Tecnológico"
    return "Outro"


MODALIDADES = {"PRESENCIAL": 1, "HIBRIDO": 2, "HIBRIDA": 2, "SEMIPRESENCIAL": 2,
               "ONLINE": 3, "EAD": 3, "A DISTANCIA": 3, "DISTANCIA": 3}


def modalidades(valor: object) -> tuple[list[int], list[str]]:
    """'Presencial, Online' -> ([1, 3], []). Devolve também os termos desconhecidos."""
    t = texto(valor)
    if t is None:
        return [], []
    ids: list[int] = []
    desconhecidos: list[str] = []
    for parte in re.split(r"[,;/|]", t):
        k = chave(parte)
        if not k:
            continue
        mid = MODALIDADES.get(k)
        if mid is None:
            desconhecidos.append(parte.strip())
        elif mid not in ids:
            ids.append(mid)
    return ids, desconhecidos


# ---------------------------------------------------------------------------
# Tipos primitivos
# ---------------------------------------------------------------------------

_EXCEL_EPOCA = datetime(1899, 12, 30)


def data(valor: object) -> date | None:
    """Aceita datetime, data serial do Excel e textos dd/mm/aaaa ou aaaa-mm-dd.

    Levanta ValueError para valores presentes porém inválidos.
    """
    if vazio(valor):
        return None
    if isinstance(valor, datetime):
        d = valor.date()
    elif isinstance(valor, date):
        d = valor
    elif isinstance(valor, (int, float)):
        if not 1 <= valor <= 80000:
            raise ValueError("data serial fora do intervalo")
        d = (_EXCEL_EPOCA + timedelta(days=float(valor))).date()
    else:
        t = str(valor).strip()
        for formato in ("%d/%m/%Y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d-%m-%Y"):
            try:
                d = datetime.strptime(t[:19] if "%H" in formato else t[:10], formato).date()
                break
            except ValueError:
                continue
        else:
            raise ValueError("formato de data não reconhecido")
    if not 1900 <= d.year <= 2100:
        raise ValueError("ano fora do intervalo")
    return d


def data_hora(valor: object) -> datetime | None:
    """Timestamp do cadastro ('2026-08-10 14:57:45.901+00')."""
    if vazio(valor):
        return None
    if isinstance(valor, datetime):
        return valor
    t = str(valor).strip()
    if t.endswith("+00"):
        t += ":00"
    try:
        return datetime.fromisoformat(t)
    except ValueError:
        d = data(valor)
        return datetime(d.year, d.month, d.day) if d else None


_VERDADEIRO = {"SIM", "S", "TRUE", "VERDADEIRO", "1", "1.0", "YES", "Y", "X"}
_FALSO = {"NAO", "N", "FALSE", "FALSO", "0", "0.0", "NO"}


def booleano(valor: object) -> bool | None:
    """Levanta ValueError para valores presentes que não são booleanos."""
    if vazio(valor):
        return None
    if isinstance(valor, bool):
        return valor
    k = chave(valor)
    if k in _VERDADEIRO:
        return True
    if k in _FALSO:
        return False
    raise ValueError("valor não é Sim/Não")


def inteiro(valor: object) -> int | None:
    if vazio(valor):
        return None
    if isinstance(valor, bool):
        raise ValueError("valor não é número inteiro")
    if isinstance(valor, (int, float)):
        if float(valor).is_integer():
            return int(valor)
        raise ValueError("valor não é número inteiro")
    t = str(valor).strip().replace(".", "").replace(",", ".")
    f = float(t)
    if not f.is_integer():
        raise ValueError("valor não é número inteiro")
    return int(f)
