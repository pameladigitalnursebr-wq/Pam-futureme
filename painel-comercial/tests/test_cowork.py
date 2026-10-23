"""Modo Cowork (SQLite, só biblioteca padrão): mesmas regras e mesmos números do sistema principal."""

import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.conftest import linha_lead, salvar_xlsx

RAIZ_COWORK = Path(__file__).resolve().parents[1] / "cowork"
SCRIPTS = RAIZ_COWORK / "inteligencia-comercial" / "scripts"
sys.path.insert(0, str(SCRIPTS))
banco = importlib.import_module("motor.banco")
importacao = importlib.import_module("motor.importacao")
q = importlib.import_module("motor.consultas")


@pytest.fixture
def conn(tmp_path):
    c = banco.conectar(tmp_path / "base.db")
    yield c
    c.close()


def test_regras_copiadas_estao_sincronizadas():
    sys.path.insert(0, str(RAIZ_COWORK))
    montar = importlib.import_module("montar")
    for origem, (destino, _) in montar.COPIAS.items():
        atual = (SCRIPTS / "motor" / destino).read_text(encoding="utf-8")
        assert atual == montar.conteudo_copia(origem), f"Rode: python cowork/montar.py ({destino} desatualizado)"


def test_importa_e_responde_como_o_sistema_principal(conn, planilha_leads, base_padrao):
    r = importacao.importar(conn, planilha_leads(base_padrao))
    assert r["resumo"]["alunos"]["novos"] == 3 and r["resumo"]["interesses"]["novos"] == 4
    f, aplicados = q.resolver(conn, {"instituicao": ["unip"]})
    assert q.resumo(conn, f)["alunos"] == 1 and q.resumo(conn, f)["interesses"] == 2
    geral = q.resumo(conn, q.Filtros())
    assert (geral["alunos"], geral["interesses"], geral["alunos_com_interesse"]) == (3, 4, 2)
    f, _ = q.resolver(conn, {"curso": ["Medicina"], "instituicao": ["Mackenzie"]})
    assert q.resumo(conn, f)["alunos"] == 1 and q.resumo(conn, f)["avisos"] == [q.AVISO_CURSO_INSTITUICAO]
    uf = q.ranking(conn, "uf", q.Filtros())
    assert {i["chave"]: i["alunos"] for i in uf["itens"]} == {"SP": 2, "RJ": 1}


def test_atualizacao_trava_e_arquivo_repetido(conn, planilha_leads, base_padrao):
    v1 = planilha_leads(base_padrao, "v1.xlsx")
    importacao.importar(conn, v1)
    with pytest.raises(importacao.ImportacaoRejeitada, match="já foi importado"):
        importacao.importar(conn, v1)
    with pytest.raises(importacao.ImportacaoRejeitada, match="limite de segurança"):
        importacao.importar(conn, planilha_leads(base_padrao[:1], "v2.xlsx"))
    v3 = base_padrao + [linha_lead(4, 1, "USP")]
    r = importacao.importar(conn, planilha_leads(v3, "v3.xlsx"))
    assert r["resumo"]["alunos"] == {"novos": 1, "atualizados": 0, "reativados": 0, "inalterados": 3, "removidos": 0}


def test_nome_inexistente_e_ambiguo(conn, planilha_leads, base_padrao):
    importacao.importar(conn, planilha_leads(base_padrao))
    with pytest.raises(q.Ambiguo) as e:
        q.resolver(conn, {"cidade": ["Curitiba"]})
    assert e.value.opcoes == []


def test_base_de_instituicoes_e_historico(conn, planilha_leads, base_padrao, tmp_path):
    importacao.importar(conn, planilha_leads(base_padrao))
    base1 = salvar_xlsx(tmp_path / "inst.xlsx", {"BaseUniversidades": [
        ["UF", "Ano", "Universidade", "Total", "Porte", "Grupo", "Afiliado", "Comissão", "Tipo de comissão", "Comercial"],
        ["SP", 2025, "UNIP - UNIVERSIDADE PAULISTA", 4, None, None, None, None, None, None],
        ["SP", 2026, "Unip - Universidade Paulista", 10, None, "Cogna", None, "R$ 300.00", None, "Já cliente"]]})
    r = importacao.importar(conn, base1)
    assert r["resumo"]["instituicoes"]["novas"] == 0                 # a UNIP já existia, veio dos leads
    unip = q.buscar(conn, "instituicao", "unip", 1)[0]["chave"]
    assert q.historico_anual(conn, "instituicao", unip)["por_ano"] == [{"ano": 2025, "total": 4},
                                                                         {"ano": 2026, "total": 10}]


def test_linha_de_comando_responde_json(tmp_path, planilha_leads, base_padrao):
    arquivo = planilha_leads(base_padrao)
    cmd = [sys.executable, "-I", str(SCRIPTS / "painel.py"), "--base", str(tmp_path / "cli.db")]
    assert subprocess.run(cmd + ["importar", str(arquivo)], capture_output=True).returncode == 0
    saida = subprocess.run(cmd + ["resumo", "--uf", "SP"], capture_output=True, text=True)
    assert json.loads(saida.stdout)["alunos"] == 2
    painel = tmp_path / "painel.html"
    assert subprocess.run(cmd + ["dashboard", "--saida", str(painel)], capture_output=True).returncode == 0
    assert "Alunos interessados" in painel.read_text(encoding="utf-8")


def test_sigla_exata_sem_volume_nao_vence_instituicoes_reais(conn, planilha_leads):
    linhas = [linha_lead(i, 1, "PUC-CAMPINAS - PONTIFÍCIA UNIVERSIDADE CATÓLICA DE CAMPINAS") for i in range(1, 21)]
    linhas += [linha_lead(i, 1, "PUCSP - PONTIFÍCIA UNIVERSIDADE CATÓLICA DE SÃO PAULO") for i in range(21, 36)]
    linhas += [linha_lead(99, 1, "PUC - Rio")]                     # resposta livre: sigla "PUC", 1 aluno
    importacao.importar(conn, planilha_leads(linhas))
    with pytest.raises(q.Ambiguo) as e:
        q.resolver(conn, {"instituicao": ["puc"]})
    assert e.value.opcoes[0]["alunos"] == 20                         # pergunta, mostrando as reais primeiro
