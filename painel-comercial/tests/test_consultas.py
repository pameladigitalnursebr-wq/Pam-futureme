import pytest

from painel.consultas import metricas
from painel.consultas.filtros import FiltroInvalido, Filtros
from painel.db import conexao
from painel.importacao.servico import importar


@pytest.fixture
def carregado(limpo, planilha_leads, base_padrao):
    importar(planilha_leads(base_padrao))
    with conexao() as conn:
        yield conn


def _id(conn, dim, termo):
    return metricas.valores(conn, dim, termo, 1)[0]["chave"]


def test_resumo_geral_diferencia_alunos_e_interesses(carregado):
    r = metricas.resumo(carregado, Filtros())
    assert r["alunos"] == 3 and r["interesses"] == 4 and r["alunos_com_interesse"] == 2
    assert r["instituicoes"] == 3 and r["estados"] == 2


def test_interessados_por_instituicao_conta_aluno_uma_vez(carregado):
    unip = _id(carregado, "instituicao", "unip")
    r = metricas.resumo(carregado, Filtros({"instituicao": [unip]}))
    assert r["alunos"] == 1 and r["interesses"] == 2     # mesmo aluno escolheu a UNIP em 1ª e 3ª opção


def test_filtros_combinados_e_aviso_curso_mais_instituicao(carregado):
    medicina = _id(carregado, "curso", "medicina")
    mack = _id(carregado, "instituicao", "mackenzie")
    r = metricas.resumo(carregado, Filtros({"curso": [medicina], "uf": ["SP"], "instituicao": [mack]}))
    assert r["alunos"] == 1
    assert r["avisos"] == [metricas.AVISO_CURSO_INSTITUICAO]
    r = metricas.resumo(carregado, Filtros({"curso": [medicina], "uf": ["RJ"]}))
    assert r["alunos"] == 0


def test_ranking_e_distribuicao(carregado):
    r = metricas.ranking(carregado, "instituicao", Filtros())
    assert [(i["rotulo"][:4], i["alunos"], i["interesses"]) for i in r["itens"]][0] == ("UNIP", 1, 2)
    uf = metricas.ranking(carregado, "uf", Filtros())
    assert {i["chave"]: i["alunos"] for i in uf["itens"]} == {"SP": 2, "RJ": 1}
    mod = metricas.ranking(carregado, "modalidade", Filtros())
    assert {i["rotulo"]: i["alunos"] for i in mod["itens"]} == {"Presencial": 2, "Online (EAD)": 1}


def test_busca_e_valores(carregado):
    assert metricas.valores(carregado, "uf", "sp")[0]["chave"] == "SP"
    grupos = {g["dimensao"] for g in metricas.busca_rapida(carregado, "campinas")["grupos"]}
    assert {"instituicao", "cidade"} <= grupos


def test_detalhe_protege_dados_pessoais(carregado):
    sem = metricas.detalhe(carregado, Filtros(), dados_pessoais=False)
    com = metricas.detalhe(carregado, Filtros(), dados_pessoais=True)
    assert sem["total"] == 3 and sem["itens"][0]["aluno"].endswith("…")
    assert "data_nascimento" not in sem["itens"][0] and "data_nascimento" in com["itens"][0]


def test_filtro_desconhecido_e_rejeitado():
    with pytest.raises(FiltroInvalido):
        Filtros.de_dict({"tabela": "x; DROP TABLE"})


def test_suspeitas_ficam_fora_por_padrao(limpo, planilha_leads):
    from tests.conftest import linha_lead
    importar(planilha_leads([linha_lead(1, 1, "privado"), linha_lead(2, 1, "USP")]))
    with conexao() as conn:
        assert metricas.resumo(conn, Filtros())["interesses"] == 1
        assert metricas.resumo(conn, Filtros(incluir_suspeitas=True))["interesses"] == 2
