from painel import revisao
from painel.consultas import metricas
from painel.consultas.filtros import Filtros
from painel.db import conexao
from painel.importacao.servico import importar
from painel.seguranca import usuarios
from tests.conftest import linha_lead


def test_unificar_grafias_vale_para_importacoes_futuras(limpo, planilha_leads):
    importar(planilha_leads([linha_lead(1, 1, "PUC-CAMPINAS - PONTIFÍCIA UNIVERSIDADE CATÓLICA DE CAMPINAS"),
                             linha_lead(2, 1, "PUCCAMP")], "v1.xlsx"))
    admin = usuarios.salvar_usuario("admin@futureme.tech", "Admin", "admin", "senha-forte-123")
    with conexao() as conn:
        ids = {r["nome"]: r["id"] for r in conn.execute("SELECT id, nome FROM core.instituicao")}
        assert len(ids) == 2                                   # nunca une sozinho
        pend = revisao.pendentes(conn)
        assert any(i["nome"] == "PUCCAMP" for i in pend["itens"])
        revisao.unificar(conn, ids["PUCCAMP"], ids["PUC-CAMPINAS - PONTIFÍCIA UNIVERSIDADE CATÓLICA DE CAMPINAS"],
                         admin["id"])
    importar(planilha_leads([linha_lead(1, 1, "PUC-CAMPINAS - PONTIFÍCIA UNIVERSIDADE CATÓLICA DE CAMPINAS"),
                             linha_lead(2, 1, "PUCCAMP"), linha_lead(3, 1, "puccamp")], "v2.xlsx"))
    with conexao() as conn:
        assert conn.execute("SELECT count(*) AS n FROM core.instituicao").fetchone()["n"] == 1
        r = metricas.ranking(conn, "instituicao", Filtros())
        assert r["itens"][0]["alunos"] == 3
        assert conn.execute("SELECT count(*) AS n FROM seg.auditoria WHERE acao = 'instituicao_unificada'"
                            ).fetchone()["n"] == 1
