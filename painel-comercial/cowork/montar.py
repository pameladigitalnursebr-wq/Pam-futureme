"""Monta a skill do modo Cowork: sincroniza as regras compartilhadas e gera o .zip para enviar ao Claude.

As regras de normalização e o mapeamento de colunas são os MESMOS do sistema principal:
este script copia os arquivos de src/painel/ para a skill. Rode depois de alterar qualquer um deles:

    python cowork/montar.py
"""

from __future__ import annotations

import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
SKILL = RAIZ / "inteligencia-comercial"
ORIGEM = RAIZ.parent / "src" / "painel"
MOTOR = SKILL / "scripts" / "motor"
CABECALHO = '# Cópia gerada por cowork/montar.py a partir de src/painel/{origem}. Não edite aqui.\n'

COPIAS = {
    "normalizacao.py": ("normalizacao.py", []),
    "importacao/esquemas.py": ("esquemas.py", [("from ..normalizacao import", "from .normalizacao import")]),
    "importacao/ocorrencias.py": ("ocorrencias.py", []),
}


def conteudo_copia(origem: str) -> str:
    destino, trocas = COPIAS[origem]
    texto = (ORIGEM / origem).read_text(encoding="utf-8")
    for antes, depois in trocas:
        texto = texto.replace(antes, depois)
    return CABECALHO.format(origem=origem) + texto


def sincronizar() -> None:
    for origem, (destino, _) in COPIAS.items():
        (MOTOR / destino).write_text(conteudo_copia(origem), encoding="utf-8")


def empacotar() -> Path:
    saida = RAIZ / "inteligencia-comercial.zip"
    with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as z:
        for arquivo in sorted(SKILL.rglob("*")):
            if arquivo.is_file() and "__pycache__" not in arquivo.parts:
                info = zipfile.ZipInfo(str(arquivo.relative_to(RAIZ)), date_time=(2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                z.writestr(info, arquivo.read_bytes())
    return saida


if __name__ == "__main__":
    sincronizar()
    print(f"Skill gerada: {empacotar()}")
