"""Leitura de .xlsx/.csv e identificação automática do tipo de cada aba pelos cabeçalhos."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .esquemas import ESQUEMAS, Esquema

LINHAS_BUSCA_CABECALHO = 15


class ArquivoInvalido(Exception):
    """O arquivo não pode ser importado (formato, colunas obrigatórias, tipos mistos)."""


@dataclass
class Aba:
    nome: str
    esquema: Esquema
    linha_cabecalho: int                 # 1 = primeira linha da planilha
    dados: pd.DataFrame                  # colunas canônicas + "_linha" (linha na planilha)
    colunas_desconhecidas: list[str] = field(default_factory=list)


@dataclass
class Arquivo:
    nome: str
    sha256: str
    bytes: int
    abas: list[Aba]
    abas_ignoradas: list[str]

    @property
    def fonte(self) -> str:
        return self.abas[0].esquema.fonte

    def aba(self, esquema: str) -> Aba | None:
        return next((a for a in self.abas if a.esquema.nome == esquema), None)


def sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _ler_planilhas(caminho: Path) -> dict[str, pd.DataFrame]:
    sufixo = caminho.suffix.lower()
    if sufixo in {".xlsx", ".xlsm", ".xls"}:
        try:
            # keep_default_na=False: o que conta como vazio é decidido pela normalização, não pelo pandas.
            return pd.read_excel(caminho, sheet_name=None, header=None, dtype=object, engine="calamine",
                                 keep_default_na=False, na_values=[""])
        except ImportError:
            return pd.read_excel(caminho, sheet_name=None, header=None, dtype=object,
                                 keep_default_na=False, na_values=[""])
    if sufixo in {".csv", ".txt"}:
        for codificacao in ("utf-8-sig", "latin-1"):
            try:
                df = pd.read_csv(caminho, header=None, dtype=object, sep=None, engine="python",
                                 encoding=codificacao, keep_default_na=False, na_values=[""])
                return {caminho.stem: df}
            except UnicodeDecodeError:
                continue
    raise ArquivoInvalido(f"Formato não suportado: '{caminho.suffix}'. Envie .xlsx ou .csv.")


def _identificar(bruto: pd.DataFrame) -> tuple[Esquema, int, dict[str, int], list[str]] | None:
    limite = min(LINHAS_BUSCA_CABECALHO, len(bruto))
    for i in range(limite):
        cabecalho = bruto.iloc[i].tolist()
        for esquema in ESQUEMAS:
            mapa, desconhecidas = esquema.mapear(cabecalho)
            if all(c in mapa for c in esquema.obrigatorias()):
                return esquema, i, mapa, desconhecidas
    return None


def _diagnostico(planilhas: dict[str, pd.DataFrame]) -> str:
    """Explica, para a aba mais parecida com algum formato, quais colunas faltaram."""
    melhor: tuple[int, str, Esquema, list[str], list[object]] | None = None
    for nome, bruto in planilhas.items():
        for i in range(min(LINHAS_BUSCA_CABECALHO, len(bruto))):
            cabecalho = bruto.iloc[i].tolist()
            for esquema in ESQUEMAS:
                mapa, _ = esquema.mapear(cabecalho)
                achadas = sum(c in mapa for c in esquema.obrigatorias())
                if achadas and (melhor is None or achadas > melhor[0]):
                    faltam = [c for c in esquema.obrigatorias() if c not in mapa]
                    melhor = (achadas, nome, esquema, faltam, cabecalho)
    if melhor is None:
        return "Nenhuma aba tem cabeçalhos reconhecidos. Confira se o arquivo é a exportação correta."
    _, nome, esquema, faltam, cabecalho = melhor
    sinonimos = {c.nome: c.sinonimos[0] for c in esquema.colunas}
    encontradas = ", ".join(str(c) for c in cabecalho if isinstance(c, str))
    return (f"A aba '{nome}' parece ser '{esquema.descricao}', mas faltam as colunas obrigatórias: "
            f"{', '.join(sinonimos[c] for c in faltam)}. Colunas encontradas: {encontradas}.")


def ler(caminho: Path, nome_original: str | None = None) -> Arquivo:
    caminho = Path(caminho)
    planilhas = _ler_planilhas(caminho)
    abas: list[Aba] = []
    ignoradas: list[str] = []
    for nome, bruto in planilhas.items():
        achado = _identificar(bruto)
        if achado is None:
            ignoradas.append(nome)
            continue
        esquema, i_cab, mapa, desconhecidas = achado
        corpo = bruto.iloc[i_cab + 1:]
        dados = pd.DataFrame({col: corpo.iloc[:, idx].to_numpy() for col, idx in mapa.items()})
        dados["_linha"] = range(i_cab + 2, i_cab + 2 + len(dados))
        # Remove linhas totalmente vazias (rodapés, espaços entre blocos).
        valores = dados.drop(columns="_linha")
        dados = dados[valores.notna().any(axis=1)].reset_index(drop=True)
        abas.append(Aba(nome, esquema, i_cab + 1, dados, desconhecidas))

    if not abas:
        raise ArquivoInvalido(_diagnostico(planilhas))
    fontes = {a.esquema.fonte for a in abas}
    if len(fontes) > 1:
        raise ArquivoInvalido("O arquivo mistura a base de interessados e a base de instituições. "
                              "Envie cada base em um arquivo separado.")
    # Uma aba por esquema: se houver duas, vale a maior e a outra é relatada.
    por_esquema: dict[str, Aba] = {}
    for aba in abas:
        atual = por_esquema.get(aba.esquema.nome)
        if atual is None or len(aba.dados) > len(atual.dados):
            if atual is not None:
                ignoradas.append(atual.nome)
            por_esquema[aba.esquema.nome] = aba
        else:
            ignoradas.append(aba.nome)
    return Arquivo(
        nome=nome_original or caminho.name,
        sha256=sha256(caminho),
        bytes=caminho.stat().st_size,
        abas=list(por_esquema.values()),
        abas_ignoradas=ignoradas,
    )
