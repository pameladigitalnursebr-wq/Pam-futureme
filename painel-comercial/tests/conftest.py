"""Fixtures: banco de teste isolado e planilhas sintéticas (nenhum dado real)."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from openpyxl import Workbook

os.environ.setdefault("PAINEL_SECRET_KEY", "segredo-de-teste-com-mais-de-32-caracteres")
os.environ["PAINEL_DATABASE_URL"] = os.environ.get(
    "PAINEL_TESTE_DATABASE_URL", "postgresql://postgres@/painel_teste?host=/tmp")
os.environ["PAINEL_COOKIE_SEGURO"] = "false"

from painel import db  # noqa: E402
from painel.consultas import cache  # noqa: E402

CABECALHO_LEADS = ["ID", "Criado em...", "Escola", "Estado", "Região", "Cidade", "Bairro da escola",
                   "Data de nascimento", "Gênero", "Faz no Momento", "Plano pós médio", "Receber comunicados",
                   "PodioCursos1", "PodioCursos2", "PodioCursos3", "Posição da opção de faculdade",
                   "Instituição Privada", "Modalidade", "Concluiu Relatório de Perfil Profissional"]


@pytest.fixture(scope="session")
def banco():
    with db.conexao() as conn:
        conn.execute("DROP SCHEMA IF EXISTS core, ana, imp, seg CASCADE")
        conn.execute("DROP TABLE IF EXISTS public.schema_migracao")
        conn.commit()
        db.migrar(conn)
    yield
    db.fechar_pool()


@pytest.fixture
def limpo(banco):
    with db.conexao() as conn:
        conn.execute("""TRUNCATE core.interesse, core.aluno_curso, core.aluno_modalidade, core.aluno,
            core.volume_instituicao_anual, core.volume_curso_anual, core.volume_cidade_anual, core.volume_escola_anual,
            core.instituicao_alias, core.instituicao, core.grupo_educacional, core.curso, core.escola, core.cidade,
            core.regiao_ensino, ana.snapshot_metrica, imp.importacao_ocorrencia, seg.consulta_log, seg.auditoria,
            seg.chave_api, seg.consulta_salva, seg.usuario, imp.importacao RESTART IDENTITY CASCADE""")
        conn.execute("INSERT INTO imp.estado DEFAULT VALUES ON CONFLICT DO NOTHING")   # TRUNCATE ... CASCADE o esvazia
        conn.execute("REFRESH MATERIALIZED VIEW ana.mv_aluno")
        conn.execute("REFRESH MATERIALIZED VIEW ana.mv_interesse")
    cache.limpar()
    yield


def aluno(n: int) -> str:
    return str(uuid.UUID(int=n))


def linha_lead(n: int, posicao: int | None, instituicao: str | None, *, cidade="CAMPINAS", uf="SP",
               cursos=("Administração - Bacharelado", "Direito - Bacharelado", None), modalidade="Presencial, Online",
               escola="EE ESCOLA TESTE", nascimento="2009-03-15"):
    return [aluno(n), "2026-05-14 11:23:48.313+00", escola, uf, "REGIAO TESTE", cidade, "CENTRO", nascimento,
            "Feminino", "Apenas estudo", "Estudar e trabalhar", True, *cursos, posicao, instituicao, modalidade, "Sim"]


def salvar_xlsx(caminho: Path, abas: dict[str, list[list]]) -> Path:
    wb = Workbook()
    wb.remove(wb.active)
    for nome, linhas in abas.items():
        ws = wb.create_sheet(nome)
        for linha in linhas:
            ws.append(linha)
    wb.save(caminho)
    return caminho


@pytest.fixture
def planilha_leads(tmp_path):
    """Gera uma base de leads: planilha_leads(linhas, nome='leads.xlsx')."""
    def gerar(linhas: list[list], nome: str = "leads.xlsx", cabecalho=CABECALHO_LEADS) -> Path:
        return salvar_xlsx(tmp_path / nome, {"Página1": [cabecalho, *linhas]})
    return gerar


@pytest.fixture
def base_padrao():
    """3 alunos: A com 3 opções (repete a UNIP em duas), B com 1 opção, C sem instituição."""
    return [
        linha_lead(1, 1, "UNIP - UNIVERSIDADE PAULISTA"),
        linha_lead(1, 2, "PUC-CAMPINAS - PONTIFÍCIA UNIVERSIDADE CATÓLICA DE CAMPINAS"),
        linha_lead(1, 3, "Unip - Universidade  Paulista"),
        linha_lead(2, 1, "MACKENZIE - UNIVERSIDADE PRESBITERIANA MACKENZIE", cidade="SÃO PAULO",
                   cursos=("Medicina - Bacharelado", None, None), modalidade="Presencial"),
        linha_lead(3, None, None, cidade="RIO DE JANEIRO", uf="RJ", cursos=("Psicologia - Bacharelado", None, None),
                   modalidade=None),
    ]
