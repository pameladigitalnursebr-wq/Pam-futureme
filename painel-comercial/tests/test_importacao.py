import pytest

from painel.db import conexao
from painel.importacao.servico import ImportacaoRejeitada, importar
from tests.conftest import linha_lead


def _contar(sql):
    with conexao() as conn:
        return conn.execute(sql).fetchone()["n"]


def test_importacao_inicial_entende_um_aluno_em_varias_linhas(limpo, planilha_leads, base_padrao):
    r = importar(planilha_leads(base_padrao))
    assert r["status"] == "concluida"
    assert r["linhas_lidas"] == 5
    assert r["resumo"]["alunos"]["novos"] == 3
    # 4 interesses: A tem 3 (UNIP aparece duas vezes, em posições diferentes) e B tem 1. C não escolheu instituição.
    assert r["resumo"]["interesses"]["novos"] == 4
    # "UNIP - UNIVERSIDADE PAULISTA" e "Unip - Universidade  Paulista" são a mesma instituição (nome normalizado).
    assert _contar("SELECT count(*) AS n FROM core.instituicao") == 3
    assert _contar("SELECT count(*) AS n FROM core.aluno_modalidade") == 3


def test_reimportar_o_mesmo_arquivo(limpo, planilha_leads, base_padrao):
    caminho = planilha_leads(base_padrao)
    importar(caminho)
    with pytest.raises(ImportacaoRejeitada, match="já foi importado"):
        importar(caminho)
    r = importar(caminho, forcar=True)
    assert r["resumo"]["alunos"] == {"novos": 0, "atualizados": 0, "reativados": 0, "inalterados": 3, "removidos": 0}
    assert r["resumo"]["interesses"]["inalterados"] == 4


def test_atualizacao_detecta_novos_alterados_e_removidos(limpo, planilha_leads, base_padrao):
    importar(planilha_leads(base_padrao, "v1.xlsx"))
    v2 = [l[:] for l in base_padrao]
    v2[3] = linha_lead(2, 1, "FGV - FUNDAÇÃO GETULIO VARGAS", cidade="SÃO PAULO",
                       cursos=("Medicina - Bacharelado", None, None), modalidade="Presencial")   # B trocou de opção
    v2 = [l for l in v2 if l[15] != 3]                                                          # A tirou a 3ª opção
    v2.append(linha_lead(4, 1, "USP"))                                                          # D é novo
    r = importar(planilha_leads(v2, "v2.xlsx"), forcar=True)
    assert r["resumo"]["alunos"]["novos"] == 1
    assert r["resumo"]["interesses"]["novos"] == 1
    assert r["resumo"]["interesses"]["atualizados"] == 1
    assert r["resumo"]["interesses"]["removidos"] == 1
    with conexao() as conn:
        removido = conn.execute("""SELECT ativo, removido_em FROM core.interesse
                                   WHERE posicao = 3""").fetchone()
    assert removido["ativo"] is False and removido["removido_em"] is not None   # exclusão lógica, nunca física


def test_modo_incremental_nao_remove_quem_nao_veio(limpo, planilha_leads, base_padrao):
    importar(planilha_leads(base_padrao, "v1.xlsx"))
    r = importar(planilha_leads([linha_lead(9, 1, "USP")], "v2.xlsx"), modo="incremental")
    assert r["resumo"]["alunos"]["removidos"] == 0
    assert _contar("SELECT count(*) AS n FROM core.aluno WHERE ativo") == 4


def test_trava_de_seguranca_contra_exportacao_incompleta(limpo, planilha_leads, base_padrao):
    importar(planilha_leads(base_padrao, "v1.xlsx"))
    with pytest.raises(ImportacaoRejeitada, match="limite de segurança"):
        importar(planilha_leads(base_padrao[:1], "v2.xlsx"))
    assert _contar("SELECT count(*) AS n FROM core.aluno WHERE ativo") == 3     # nada mudou
    assert _contar("SELECT count(*) AS n FROM imp.importacao WHERE status = 'rejeitada'") == 1


def test_validacao_registra_erros_e_avisos_sem_derrubar_a_importacao(limpo, planilha_leads, base_padrao):
    linhas = base_padrao + [
        ["nao-e-uuid", *linha_lead(5, 1, "USP")[1:]],                                 # erro: ID inválido
        linha_lead(1, 1, "OUTRA FACULDADE"),                                          # erro: posição 1 do aluno A repetida
        linha_lead(6, 7, "USP"),                                                      # erro: posição fora de 1..3
        linha_lead(7, 1, "3", nascimento=6613532),                                    # avisos: suspeita + data inválida
    ]
    r = importar(planilha_leads(linhas))
    assert r["status"] == "concluida"
    assert r["linhas_ignoradas"] == 3
    codigos = {o["codigo"] for o in r["resumo"]["ocorrencias"]}
    assert {"id_invalido", "chave_duplicada", "posicao_invalida", "instituicao_suspeita", "data_invalida"} <= codigos
    with conexao() as conn:
        assert conn.execute("SELECT qualidade FROM core.instituicao WHERE nome = '3'").fetchone()["qualidade"] == "suspeita"
        assert conn.execute("SELECT count(*) AS n FROM imp.importacao_ocorrencia").fetchone()["n"] >= 5


def test_base_de_instituicoes_enriquece_as_mesmas_instituicoes(limpo, planilha_leads, base_padrao, tmp_path):
    from tests.conftest import salvar_xlsx
    importar(planilha_leads(base_padrao))
    base1 = salvar_xlsx(tmp_path / "inst.xlsx", {
        "BaseUniversidades": [
            ["UF", "Ano", "Universidade", "Total", "Porte", "Grupo", "Afiliado", "Comissão", "Tipo de comissão",
             "Comercial"],
            ["SP", 2026, "UNIP - UNIVERSIDADE PAULISTA", 10, None, None, "Não têm", None, None, "Consultoria Marcos"],
            ["SP", 2025, "unip - universidade paulista", 4, None, None, None, None, None, None],
            ["SP", 2026, "ANHANGUERA", 7, "Grupos Educacionais", "Cogna", "Programa Próprio", "R$ 300.00", "Teto",
             "Já cliente"],
        ],
        "BaseCursos": [["UF", "Ano", "Curso", "Total"], ["SP", 2026, "Medicina - Bacharelado", 5],
                       ["SP", 2026, "Medicina - Bacharelado", 5]],     # linha idêntica: conta uma vez
    })
    r = importar(base1)
    assert r["fonte"] == "instituicoes" and r["status"] == "concluida"
    assert r["resumo"]["instituicoes"]["novas"] == 1          # só a Anhanguera; a UNIP já existia pelos leads
    with conexao() as conn:
        unip = conn.execute("""SELECT i.origem, i.afiliado, i.status_comercial,
                                      (SELECT sum(total) FROM core.volume_instituicao_anual v
                                       WHERE v.instituicao_id = i.id) AS total
                               FROM core.instituicao i WHERE sigla = 'UNIP'""").fetchone()
        anh = conn.execute("""SELECT i.comissao_valor, g.nome AS grupo FROM core.instituicao i
                              JOIN core.grupo_educacional g ON g.id = i.grupo_id""").fetchone()
        medicina = conn.execute("SELECT sum(total) AS n FROM core.volume_curso_anual").fetchone()["n"]
    assert unip["origem"] == "base_instituicoes" and unip["afiliado"] == "Não tem" and unip["total"] == 14
    assert float(anh["comissao_valor"]) == 300.0 and anh["grupo"] == "Cogna"
    assert medicina == 5
