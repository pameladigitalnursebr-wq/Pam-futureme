"""Papéis e permissões. Para criar um papel ou permissão nova, altere só este arquivo
(e o CHECK de seg.usuario.papel, se for um papel novo)."""

from __future__ import annotations

CONSULTAR = "consultar"              # painel, rankings, busca, detalhe sem dados pessoais
EXPORTAR = "exportar"                # baixar CSV/Excel
DADOS_PESSOAIS = "dados_pessoais"    # ID completo, data de nascimento e gênero individuais (menores: LGPD)
IMPORTAR = "importar"                # enviar planilhas
REVISAR_INSTITUICOES = "revisar_instituicoes"   # unificar grafias, marcar suspeitas
ADMINISTRAR = "administrar"          # usuários, chaves de API, auditoria

PAPEIS: dict[str, set[str]] = {
    "leitor": {CONSULTAR},
    "analista": {CONSULTAR, EXPORTAR},
    "gestor": {CONSULTAR, EXPORTAR, IMPORTAR, REVISAR_INSTITUICOES},
    "admin": {CONSULTAR, EXPORTAR, IMPORTAR, REVISAR_INSTITUICOES, DADOS_PESSOAIS, ADMINISTRAR},
}

DESCRICAO_PAPEIS = {
    "leitor": "Consulta o painel e conversa com o Claude",
    "analista": "Leitor + exporta resultados",
    "gestor": "Analista + importa planilhas e revisa instituições",
    "admin": "Tudo, inclusive usuários, chaves de API e dados pessoais",
}

# Escopos de chave de API -> permissões concedidas (sempre limitadas às do dono da chave).
ESCOPOS: dict[str, set[str]] = {
    "consulta": {CONSULTAR},
    "exportacao": {CONSULTAR, EXPORTAR},
    "importacao": {IMPORTAR},
}


def permissoes_do_papel(papel: str) -> set[str]:
    return set(PAPEIS.get(papel, set()))
