import pytest
from fastapi.testclient import TestClient

from painel.api.app import criar_app
from painel.importacao.servico import importar
from painel.seguranca import usuarios
from tests.conftest import linha_lead


@pytest.fixture
def cliente(limpo, planilha_leads, base_padrao):
    importar(planilha_leads(base_padrao))
    usuarios.salvar_usuario("admin@futureme.tech", "Admin", "admin", "senha-forte-123")
    usuarios.salvar_usuario("leitor@futureme.tech", "Leitor", "leitor", "senha-forte-123")
    with TestClient(criar_app()) as c:
        yield c


def _login(c, email):
    assert c.post("/api/sessao", json={"email": email, "senha": "senha-forte-123"}).status_code == 200


def test_exige_login(cliente):
    assert cliente.get("/api/resumo").status_code == 401
    assert cliente.post("/api/sessao", json={"email": "admin@futureme.tech", "senha": "errada"}).status_code == 401


def test_consulta_com_filtros_na_url(cliente):
    _login(cliente, "leitor@futureme.tech")
    assert cliente.get("/api/resumo").json()["alunos"] == 3
    assert cliente.get("/api/resumo?uf=RJ").json()["alunos"] == 1
    assert cliente.get("/api/resumo?ano_cadastro=abc").status_code == 400
    r = cliente.get("/api/ranking/instituicao?limite=2").json()
    assert len(r["itens"]) == 2


def test_permissoes_por_papel(cliente):
    _login(cliente, "leitor@futureme.tech")
    assert cliente.get("/api/exportar?formato=csv").status_code == 403
    assert cliente.get("/api/usuarios").status_code == 403
    _login(cliente, "admin@futureme.tech")
    r = cliente.get("/api/exportar?formato=csv")
    assert r.status_code == 200 and r.content.decode("utf-8-sig").startswith("Aluno (ID);")
    assert cliente.get("/api/exportar?formato=xlsx&tipo=ranking&dimensao=curso").status_code == 200


def test_dominio_de_email_restrito():
    with pytest.raises(ValueError, match="futureme.tech"):
        usuarios.validar_email("alguem@gmail.com")


def test_chave_de_api_e_escopo(cliente):
    admin = usuarios.buscar_por_email("admin@futureme.tech")
    chave = usuarios.criar_chave_api(admin["id"], "teste", ["consulta"])
    h = {"authorization": f"Bearer {chave}"}
    assert cliente.get("/api/resumo", headers=h).status_code == 200
    assert cliente.get("/api/exportar?formato=csv", headers=h).status_code == 403   # escopo limita o papel
    assert cliente.post("/mcp", json={}).status_code == 401                        # MCP sem chave


def test_upload_de_planilha(cliente, planilha_leads, base_padrao):
    _login(cliente, "admin@futureme.tech")
    caminho = planilha_leads(base_padrao + [linha_lead(8, 1, "USP")], "nova.xlsx")

    def enviar():
        with open(caminho, "rb") as f:
            return cliente.post("/api/importacoes", files={"arquivo": ("leads.xlsx", f)}, data={"modo": "completo"})

    r = enviar()
    assert r.status_code == 200 and r.json()["resumo"]["alunos"]["novos"] == 1
    r = enviar()
    assert r.status_code == 409 and "já foi importado" in r.json()["detail"]["mensagem"]
    assert len(cliente.get("/api/importacoes").json()) == 2
