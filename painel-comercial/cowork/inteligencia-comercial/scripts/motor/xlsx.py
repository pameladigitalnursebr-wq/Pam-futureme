"""Leitor mínimo de .xlsx/.csv usando só a biblioteca padrão (o ambiente do Claude pode não ter pandas).

Lê os valores brutos das células: números, textos, booleanos. Datas do Excel chegam como número
serial e são convertidas pela normalização.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from pathlib import Path
from typing import Iterator
from xml.etree.ElementTree import iterparse

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_NS_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_COLUNA = re.compile(r"([A-Z]+)")


def _indice_coluna(ref: str) -> int:
    letras = _COLUNA.match(ref).group(1)
    n = 0
    for c in letras:
        n = n * 26 + (ord(c) - 64)
    return n - 1


def _textos_compartilhados(z: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in z.namelist():
        return []
    textos = []
    with z.open("xl/sharedStrings.xml") as f:
        for _, el in iterparse(f):
            if el.tag == _NS + "si":
                textos.append("".join(t.text or "" for t in el.iter(_NS + "t")))
                el.clear()
    return textos


def _abas(z: zipfile.ZipFile) -> list[tuple[str, str]]:
    """[(nome da aba, caminho do xml)] na ordem da pasta de trabalho."""
    rels = {}
    with z.open("xl/_rels/workbook.xml.rels") as f:
        for _, el in iterparse(f):
            if el.tag.endswith("Relationship"):
                alvo = el.get("Target").lstrip("/")
                rels[el.get("Id")] = alvo if alvo.startswith("xl/") else "xl/" + alvo
    abas = []
    with z.open("xl/workbook.xml") as f:
        for _, el in iterparse(f):
            if el.tag == _NS + "sheet":
                abas.append((el.get("name"), rels[el.get(_NS_REL + "id")]))
    return abas


def _valor(celula, compartilhados: list[str]):
    tipo = celula.get("t")
    if tipo == "inlineStr":
        return "".join(t.text or "" for t in celula.iter(_NS + "t"))
    v = celula.find(_NS + "v")
    if v is None or v.text is None:
        return None
    if tipo == "s":
        return compartilhados[int(v.text)]
    if tipo in ("str", "d"):
        return v.text
    if tipo == "b":
        return v.text == "1"
    if tipo == "e":
        return None
    numero = float(v.text)
    return int(numero) if numero.is_integer() else numero


def _linhas_xml(z: zipfile.ZipFile, caminho: str, compartilhados: list[str]) -> Iterator[tuple[int, list]]:
    with z.open(caminho) as f:
        for _, el in iterparse(f):
            if el.tag != _NS + "row":
                continue
            valores: list = []
            for c in el.iter(_NS + "c"):
                i = _indice_coluna(c.get("r")) if c.get("r") else len(valores)
                if i >= len(valores):
                    valores.extend([None] * (i + 1 - len(valores)))
                valores[i] = _valor(c, compartilhados)
            yield int(el.get("r")), valores
            el.clear()


def ler_planilhas(caminho: Path) -> dict[str, list[tuple[int, list]]]:
    """{nome da aba: [(número da linha, valores)]}."""
    caminho = Path(caminho)
    if caminho.suffix.lower() in (".csv", ".txt"):
        bruto = caminho.read_bytes()
        try:
            texto = bruto.decode("utf-8-sig")
        except UnicodeDecodeError:
            texto = bruto.decode("latin-1")
        dialeto = csv.Sniffer().sniff(texto[:5000], delimiters=";,\t")
        linhas = [[v if v != "" else None for v in l] for l in csv.reader(io.StringIO(texto), dialeto)]
        return {caminho.stem: list(enumerate(linhas, start=1))}
    if caminho.suffix.lower() not in (".xlsx", ".xlsm"):
        raise ValueError(f"Formato não suportado: '{caminho.suffix}'. Envie .xlsx ou .csv.")
    with zipfile.ZipFile(caminho) as z:
        compartilhados = _textos_compartilhados(z)
        return {nome: list(_linhas_xml(z, xml, compartilhados)) for nome, xml in _abas(z)}
