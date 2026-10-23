import pytest

from painel.importacao.leitor import ArquivoInvalido, ler
from tests.conftest import CABECALHO_LEADS, linha_lead, salvar_xlsx


def test_identifica_base_pelo_cabecalho_mesmo_com_titulo_e_sinonimos(tmp_path):
    cabecalho = ["id do aluno", "Criado em", "Escola", "UF", "Região", "Município", "Bairro", "Nascimento", "Sexo",
                 "Faz no momento", "Plano pos medio", "Receber comunicados", "Curso 1", "Curso 2", "Curso 3",
                 "Posição", "Instituição", "Modalidades", "Concluiu relatório", "Coluna Nova"]
    caminho = salvar_xlsx(tmp_path / "x.xlsx", {"Qualquer nome": [["Exportação de outubro"], [], cabecalho,
                                                                  linha_lead(1, 1, "UNIP")],
                                                "Resumo": [["Tabela dinâmica"], [1, 2]]})
    arq = ler(caminho)
    assert arq.fonte == "leads"
    aba = arq.abas[0]
    assert aba.linha_cabecalho == 3 and aba.colunas_desconhecidas == ["Coluna Nova"]
    assert aba.dados.loc[0, "instituicao"] == "UNIP" and aba.dados.loc[0, "_linha"] == 4
    assert arq.abas_ignoradas == ["Resumo"]


def test_coluna_obrigatoria_ausente_explica_o_que_falta(tmp_path):
    cabecalho = [c for c in CABECALHO_LEADS if c != "Instituição Privada"]
    caminho = salvar_xlsx(tmp_path / "x.xlsx", {"P": [cabecalho]})
    with pytest.raises(ArquivoInvalido, match="Instituição Privada"):
        ler(caminho)


def test_csv_com_ponto_e_virgula(tmp_path):
    caminho = tmp_path / "leads.csv"
    caminho.write_text(";".join(CABECALHO_LEADS) + "\n" + ";".join(str(v) for v in linha_lead(1, 1, "UNIP")),
                       encoding="utf-8")
    assert ler(caminho).fonte == "leads"
