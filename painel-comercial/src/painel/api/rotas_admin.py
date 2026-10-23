"""Sessão, importações, revisão de instituições, usuários, chaves de API e trilhas."""

from __future__ import annotations

import csv
import io
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from .. import revisao
from ..config import config
from ..db import conexao
from ..importacao.leitor import ArquivoInvalido
from ..importacao.servico import ImportacaoRejeitada, importar, relatorio
from ..seguranca import permissoes as P
from ..seguranca import usuarios as U
from ..seguranca.usuarios import Usuario
from .autenticacao import COOKIE_SESSAO, exigir, usuario_atual

rotas = APIRouter(prefix="/api")


# ---------------------------------------------------------------------------
# Sessão
# ---------------------------------------------------------------------------

class Login(BaseModel):
    email: str
    senha: str


@rotas.post("/sessao", tags=["sessão"])
def entrar(dados: Login) -> JSONResponse:
    u = U.autenticar_senha(dados.email, dados.senha)
    if u is None:
        raise HTTPException(401, "E-mail ou senha incorretos.")
    resposta = JSONResponse(u.publico())
    resposta.set_cookie(COOKIE_SESSAO, U.emitir_sessao(u), httponly=True, samesite="strict",
                        secure=config().cookie_seguro,
                        max_age=config().sessao_horas * 3600)
    return resposta


@rotas.delete("/sessao", tags=["sessão"])
def sair() -> JSONResponse:
    resposta = JSONResponse({"ok": True})
    resposta.delete_cookie(COOKIE_SESSAO)
    return resposta


@rotas.get("/eu", tags=["sessão"])
def eu(usuario: Usuario = Depends(usuario_atual)) -> dict:
    return {**usuario.publico(), "papeis": P.DESCRICAO_PAPEIS}


# ---------------------------------------------------------------------------
# Importações
# ---------------------------------------------------------------------------

@rotas.post("/importacoes", tags=["importação"])
def enviar_planilha(arquivo: UploadFile = File(...), modo: str = Form("completo"), forcar: bool = Form(False),
                    usuario: Usuario = Depends(exigir(P.IMPORTAR))) -> dict:
    sufixo = Path(arquivo.filename or "").suffix.lower()
    if sufixo not in {".xlsx", ".xlsm", ".csv"}:
        raise HTTPException(400, "Envie um arquivo .xlsx ou .csv.")
    with tempfile.NamedTemporaryFile(suffix=sufixo) as tmp:
        shutil.copyfileobj(arquivo.file, tmp)
        tmp.flush()
        try:
            return importar(Path(tmp.name), arquivo.filename, modo, usuario.id, forcar)
        except ArquivoInvalido as e:
            raise HTTPException(422, str(e)) from e
        except ImportacaoRejeitada as e:
            detalhe = {"mensagem": str(e)}
            if e.importacao_id:
                detalhe["importacao"] = relatorio(e.importacao_id)
            raise HTTPException(409, jsonable_encoder(detalhe)) from e


@rotas.get("/importacoes", tags=["importação"])
def listar_importacoes(limite: int = 50, usuario: Usuario = Depends(exigir(P.CONSULTAR))) -> list[dict]:
    with conexao() as conn:
        return [dict(r) for r in conn.execute("""
            SELECT i.id, i.fonte, i.modo, i.status, i.arquivo_nome, i.iniciado_em, i.concluido_em, i.duracao_ms,
                   i.linhas_lidas, i.linhas_ignoradas, i.total_erros, i.total_avisos, i.resumo, i.mensagem,
                   u.nome AS usuario
            FROM imp.importacao i LEFT JOIN seg.usuario u ON u.id = i.usuario_id
            ORDER BY i.id DESC LIMIT %s""", (limite,))]


@rotas.get("/importacoes/{importacao_id}/ocorrencias", tags=["importação"])
def ocorrencias(importacao_id: int, formato: str = "json", usuario: Usuario = Depends(exigir(P.IMPORTAR))):
    with conexao() as conn:
        linhas = [dict(r) for r in conn.execute("""
            SELECT severidade, codigo, linha, coluna, valor, mensagem FROM imp.importacao_ocorrencia
            WHERE importacao_id = %s ORDER BY id""", (importacao_id,))]
    if formato != "csv":
        return linhas
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=["severidade", "codigo", "linha", "coluna", "valor", "mensagem"], delimiter=";")
    w.writeheader()
    w.writerows(linhas)
    return Response(buf.getvalue().encode("utf-8-sig"), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="ocorrencias_{importacao_id}.csv"'})


# ---------------------------------------------------------------------------
# Revisão de instituições
# ---------------------------------------------------------------------------

class Marcacao(BaseModel):
    verificada: bool | None = None
    qualidade: str | None = None


class Unificacao(BaseModel):
    destino_id: int


@rotas.get("/instituicoes/revisao", tags=["instituições"])
def pendentes(limite: int = 50, deslocamento: int = 0,
              usuario: Usuario = Depends(exigir(P.REVISAR_INSTITUICOES))) -> dict:
    with conexao() as conn:
        return revisao.pendentes(conn, limite, deslocamento)


@rotas.patch("/instituicoes/{instituicao_id}", tags=["instituições"])
def marcar(instituicao_id: int, dados: Marcacao, usuario: Usuario = Depends(exigir(P.REVISAR_INSTITUICOES))) -> dict:
    with conexao() as conn:
        try:
            revisao.marcar(conn, instituicao_id, usuario.id, verificada=dados.verificada, qualidade=dados.qualidade)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
    return {"ok": True}


@rotas.post("/instituicoes/{instituicao_id}/unificar", tags=["instituições"])
def unificar(instituicao_id: int, dados: Unificacao,
             usuario: Usuario = Depends(exigir(P.REVISAR_INSTITUICOES))) -> dict:
    with conexao() as conn:
        try:
            return revisao.unificar(conn, instituicao_id, dados.destino_id, usuario.id)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e


# ---------------------------------------------------------------------------
# Usuários, chaves de API e trilhas (admin)
# ---------------------------------------------------------------------------

class NovoUsuario(BaseModel):
    email: str
    nome: str
    papel: str
    senha: str | None = None
    ativo: bool = True


class NovaChave(BaseModel):
    nome: str
    escopos: list[str] = ["consulta"]
    usuario_id: int | None = None


administrar = exigir(P.ADMINISTRAR)


@rotas.get("/usuarios", tags=["administração"])
def listar_usuarios(usuario: Usuario = Depends(administrar)) -> list[dict]:
    return U.listar_usuarios()


@rotas.post("/usuarios", tags=["administração"])
def salvar_usuario(dados: NovoUsuario, usuario: Usuario = Depends(administrar)) -> dict:
    try:
        return U.salvar_usuario(dados.email, dados.nome, dados.papel, dados.senha, dados.ativo, usuario.id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@rotas.get("/chaves", tags=["administração"])
def listar_chaves(usuario: Usuario = Depends(administrar)) -> list[dict]:
    return U.listar_chaves()


@rotas.post("/chaves", tags=["administração"])
def criar_chave(dados: NovaChave, usuario: Usuario = Depends(administrar)) -> dict:
    try:
        chave = U.criar_chave_api(dados.usuario_id or usuario.id, dados.nome, dados.escopos, usuario.id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"chave": chave, "aviso": "Copie agora: a chave não será exibida de novo."}


@rotas.delete("/chaves/{chave_id}", tags=["administração"])
def revogar_chave(chave_id: int, usuario: Usuario = Depends(administrar)) -> dict:
    U.revogar_chave(chave_id, usuario.id)
    return {"ok": True}


@rotas.get("/historico-consultas", tags=["administração"])
def historico_consultas(limite: int = 100, usuario: Usuario = Depends(administrar)) -> list[dict]:
    with conexao() as conn:
        return [dict(r) for r in conn.execute("""
            SELECT c.criado_em, u.nome AS usuario, c.origem, c.operacao, c.parametros, c.duracao_ms
            FROM seg.consulta_log c LEFT JOIN seg.usuario u ON u.id = c.usuario_id
            ORDER BY c.id DESC LIMIT %s""", (limite,))]


@rotas.get("/auditoria", tags=["administração"])
def auditoria(limite: int = 100, usuario: Usuario = Depends(administrar)) -> list[dict]:
    with conexao() as conn:
        return [dict(r) for r in conn.execute("""
            SELECT a.criado_em, u.nome AS usuario, a.acao, a.alvo, a.detalhes
            FROM seg.auditoria a LEFT JOIN seg.usuario u ON u.id = a.usuario_id
            ORDER BY a.id DESC LIMIT %s""", (limite,))]
