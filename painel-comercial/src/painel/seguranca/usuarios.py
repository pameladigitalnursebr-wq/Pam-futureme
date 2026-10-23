"""Usuários, senhas, sessões (JWT) e chaves de API."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from psycopg.types.json import Jsonb

from ..config import config
from ..db import conexao
from .permissoes import ESCOPOS, PAPEIS, permissoes_do_papel

PREFIXO_CHAVE = "pcf_"


@dataclass
class Usuario:
    id: int
    email: str
    nome: str
    papel: str
    permissoes: set[str] = field(default_factory=set)
    via_chave: str | None = None     # nome da chave de API, quando autenticado por chave

    def pode(self, permissao: str) -> bool:
        return permissao in self.permissoes

    def publico(self) -> dict[str, Any]:
        return {"id": self.id, "email": self.email, "nome": self.nome, "papel": self.papel,
                "permissoes": sorted(self.permissoes)}


# ---------------------------------------------------------------------------
# Senhas (scrypt da biblioteca padrão)
# ---------------------------------------------------------------------------

def hash_senha(senha: str) -> str:
    sal = secrets.token_bytes(16)
    h = hashlib.scrypt(senha.encode(), salt=sal, n=2**14, r=8, p=1)
    return f"scrypt${sal.hex()}${h.hex()}"


def conferir_senha(senha: str, armazenado: str | None) -> bool:
    if not armazenado or not armazenado.startswith("scrypt$"):
        return False
    _, sal, h = armazenado.split("$")
    calculado = hashlib.scrypt(senha.encode(), salt=bytes.fromhex(sal), n=2**14, r=8, p=1)
    return hmac.compare_digest(calculado.hex(), h)


def validar_email(email: str) -> str:
    email = email.strip().lower()
    dominio = config().dominio_email
    if "@" not in email or not email.endswith("@" + dominio):
        raise ValueError(f"Use um e-mail @{dominio}.")
    return email


# ---------------------------------------------------------------------------
# Usuários
# ---------------------------------------------------------------------------

def salvar_usuario(email: str, nome: str, papel: str, senha: str | None = None,
                   ativo: bool = True, autor_id: int | None = None) -> dict:
    email = validar_email(email)
    if papel not in PAPEIS:
        raise ValueError(f"Papel inválido. Use: {', '.join(PAPEIS)}.")
    if senha is not None and len(senha) < 10:
        raise ValueError("A senha precisa de pelo menos 10 caracteres.")
    with conexao() as conn:
        u = conn.execute("""
            INSERT INTO seg.usuario (email, nome, papel, senha_hash, ativo) VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (email) DO UPDATE SET nome = EXCLUDED.nome, papel = EXCLUDED.papel, ativo = EXCLUDED.ativo,
                senha_hash = COALESCE(EXCLUDED.senha_hash, seg.usuario.senha_hash)
            RETURNING id, email, nome, papel, ativo""",
            (email, nome, papel, hash_senha(senha) if senha else None, ativo)).fetchone()
        auditar(conn, autor_id, "usuario_salvo", f"usuario:{u['id']}", {"papel": papel, "ativo": ativo})
    return dict(u)


def buscar_por_email(email: str) -> dict | None:
    with conexao() as conn:
        u = conn.execute("SELECT * FROM seg.usuario WHERE email = %s", (email.strip().lower(),)).fetchone()
    return dict(u) if u else None


def listar_usuarios() -> list[dict]:
    with conexao() as conn:
        return [dict(u) for u in conn.execute(
            "SELECT id, email, nome, papel, ativo, criado_em, ultimo_acesso FROM seg.usuario ORDER BY nome")]


def _carregar(usuario_id: int) -> Usuario | None:
    with conexao() as conn:
        u = conn.execute("SELECT * FROM seg.usuario WHERE id = %s AND ativo", (usuario_id,)).fetchone()
    if u is None:
        return None
    return Usuario(u["id"], u["email"], u["nome"], u["papel"], permissoes_do_papel(u["papel"]))


def autenticar_senha(email: str, senha: str) -> Usuario | None:
    u = buscar_por_email(email)
    if u is None or not u["ativo"] or not conferir_senha(senha, u["senha_hash"]):
        return None
    with conexao() as conn:
        conn.execute("UPDATE seg.usuario SET ultimo_acesso = now() WHERE id = %s", (u["id"],))
    return Usuario(u["id"], u["email"], u["nome"], u["papel"], permissoes_do_papel(u["papel"]))


# ---------------------------------------------------------------------------
# Sessão do painel (JWT assinado, enviado em cookie HttpOnly)
# ---------------------------------------------------------------------------

def emitir_sessao(usuario: Usuario) -> str:
    agora = datetime.now(timezone.utc)
    return jwt.encode({"sub": str(usuario.id), "iat": agora, "exp": agora + timedelta(hours=config().sessao_horas)},
                      config().secret_key, algorithm="HS256")


def usuario_da_sessao(token: str) -> Usuario | None:
    try:
        dados = jwt.decode(token, config().secret_key, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    return _carregar(int(dados["sub"]))


# ---------------------------------------------------------------------------
# Chaves de API
# ---------------------------------------------------------------------------

def _hash_chave(chave: str) -> str:
    return hashlib.sha256(chave.encode()).hexdigest()


def criar_chave_api(usuario_id: int, nome: str, escopos: list[str], autor_id: int | None = None) -> str:
    invalidos = [e for e in escopos if e not in ESCOPOS]
    if invalidos:
        raise ValueError(f"Escopo inválido: {', '.join(invalidos)}. Use: {', '.join(ESCOPOS)}.")
    chave = PREFIXO_CHAVE + secrets.token_urlsafe(32)
    with conexao() as conn:
        conn.execute("""INSERT INTO seg.chave_api (usuario_id, nome, prefixo, hash, escopos)
                        VALUES (%s, %s, %s, %s, %s)""",
                     (usuario_id, nome, chave[:10], _hash_chave(chave), escopos))
        auditar(conn, autor_id or usuario_id, "chave_api_criada", f"usuario:{usuario_id}",
                {"nome": nome, "escopos": escopos})
    return chave


def listar_chaves() -> list[dict]:
    with conexao() as conn:
        return [dict(c) for c in conn.execute("""
            SELECT c.id, c.nome, c.prefixo, c.escopos, c.criado_em, c.ultimo_uso, c.revogada_em,
                   u.email AS usuario
            FROM seg.chave_api c JOIN seg.usuario u ON u.id = c.usuario_id ORDER BY c.criado_em DESC""")]


def revogar_chave(chave_id: int, autor_id: int) -> None:
    with conexao() as conn:
        conn.execute("UPDATE seg.chave_api SET revogada_em = now() WHERE id = %s AND revogada_em IS NULL",
                     (chave_id,))
        auditar(conn, autor_id, "chave_api_revogada", f"chave:{chave_id}", {})


def usuario_da_chave(chave: str) -> Usuario | None:
    if not chave.startswith(PREFIXO_CHAVE):
        return None
    with conexao() as conn:
        c = conn.execute("""
            UPDATE seg.chave_api SET ultimo_uso = now()
            WHERE hash = %s AND revogada_em IS NULL RETURNING usuario_id, nome, escopos""",
            (_hash_chave(chave),)).fetchone()
    if c is None:
        return None
    u = _carregar(c["usuario_id"])
    if u is None:
        return None
    concedidas = set().union(*(ESCOPOS[e] for e in c["escopos"] if e in ESCOPOS))
    u.permissoes &= concedidas       # a chave nunca dá mais do que o papel do dono
    u.via_chave = c["nome"]
    return u


# ---------------------------------------------------------------------------
# Trilhas
# ---------------------------------------------------------------------------

def auditar(conn, usuario_id: int | None, acao: str, alvo: str | None, detalhes: dict) -> None:
    conn.execute("INSERT INTO seg.auditoria (usuario_id, acao, alvo, detalhes) VALUES (%s, %s, %s, %s)",
                 (usuario_id, acao, alvo, Jsonb(detalhes)))


def registrar_consulta(usuario_id: int | None, origem: str, operacao: str, parametros: dict,
                       duracao_ms: int) -> None:
    with conexao() as conn:
        conn.execute("""INSERT INTO seg.consulta_log (usuario_id, origem, operacao, parametros, duracao_ms)
                        VALUES (%s, %s, %s, %s, %s)""",
                     (usuario_id, origem, operacao, Jsonb(parametros), duracao_ms))
