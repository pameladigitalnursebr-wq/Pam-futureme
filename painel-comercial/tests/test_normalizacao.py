from datetime import date

import pytest

from painel import normalizacao as n


def test_chave_ignora_acento_caixa_e_espacos():
    assert n.chave("  Centro Universitário   Anhanguera de São Paulo ") == "CENTRO UNIVERSITARIO ANHANGUERA DE SAO PAULO"
    assert n.chave('"FACULDADE ""OSWALDO CRUZ"""') == "FACULDADE OSWALDO CRUZ"
    assert n.chave(None) is None and n.chave("   ") is None
    assert n.texto("N/A") is None and n.texto("#N/A") is None and n.vazio(" null ")


def test_modalidades_em_qualquer_ordem_e_sinonimos():
    assert n.modalidades("Presencial, Híbrido, Online") == ([1, 2, 3], [])
    assert n.modalidades("Online, Presencial") == ([3, 1], [])
    assert n.modalidades("EAD; semipresencial") == ([3, 2], [])
    assert n.modalidades("Noturno") == ([], ["Noturno"])


def test_datas_validas_e_corrompidas():
    assert n.data("15/10/2008") == date(2008, 10, 15)
    assert n.data(39736) == date(2008, 10, 15)          # serial do Excel
    with pytest.raises(ValueError):
        n.data(6613532)                                  # caso real: serial corrompido na exportação


def test_booleanos():
    assert n.booleano("Sim") is True and n.booleano(0) is False and n.booleano(None) is None
    with pytest.raises(ValueError):
        n.booleano("talvez")


@pytest.mark.parametrize("nome,suspeita", [("3", True), ("privado", True), ("Não sei.", True), ("nenhuma", True), ("esc", True), ("30042008", True),
                                           ("UNIP - UNIVERSIDADE PAULISTA", False), ("USP", False)])
def test_instituicao_suspeita(nome, suspeita):
    assert n.instituicao_suspeita(nome) is suspeita


def test_grau_sigla_moeda_e_valores_canonicos():
    assert n.grau_curso("Medicina - Bacharelado") == "Bacharelado"
    assert n.grau_curso("Técnico em Informática") == "Técnico"
    assert n.sigla_instituicao("UNIP - UNIVERSIDADE PAULISTA") == "UNIP"
    assert n.moeda("R$ 300.00") == 300.0 and n.moeda("R$ 1.300,50") == 1300.5
    assert n.valor_canonico("afiliado", "Não têm") == "Não tem"
    assert n.valor_canonico("porte", "Grupos educacionais") == n.valor_canonico("porte", "Grupos Educacionais")
