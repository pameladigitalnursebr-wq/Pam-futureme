# Cópia gerada por cowork/montar.py a partir de src/painel/importacao/ocorrencias.py. Não edite aqui.
"""Coleta de erros e avisos de uma importação."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

# Acima deste número, as ocorrências continuam contadas, mas não são gravadas uma a uma.
LIMITE_DETALHE = 5000


@dataclass
class Ocorrencias:
    detalhes: list[tuple[str, str, int | None, str | None, str | None, str]] = field(default_factory=list)
    contagem: Counter = field(default_factory=Counter)
    linhas_ignoradas: set[int] = field(default_factory=set)

    def _registrar(self, severidade: str, codigo: str, mensagem: str,
                   linha: int | None, coluna: str | None, valor: object) -> None:
        self.contagem[(severidade, codigo)] += 1
        if len(self.detalhes) < LIMITE_DETALHE:
            v = None if valor is None else str(valor)[:300]
            self.detalhes.append((severidade, codigo, linha, coluna, v, mensagem))

    def erro(self, codigo: str, mensagem: str, linha: int | None = None,
             coluna: str | None = None, valor: object = None, ignora_linha: bool = True) -> None:
        """Erro: a linha (ou parte dela) não entra na base."""
        self._registrar("erro", codigo, mensagem, linha, coluna, valor)
        if ignora_linha and linha is not None:
            self.linhas_ignoradas.add(linha)

    def aviso(self, codigo: str, mensagem: str, linha: int | None = None,
              coluna: str | None = None, valor: object = None) -> None:
        """Aviso: a linha entra; o campo problemático fica vazio ou é marcado."""
        self._registrar("aviso", codigo, mensagem, linha, coluna, valor)

    @property
    def total_erros(self) -> int:
        return sum(n for (sev, _), n in self.contagem.items() if sev == "erro")

    @property
    def total_avisos(self) -> int:
        return sum(n for (sev, _), n in self.contagem.items() if sev == "aviso")

    def resumo(self) -> list[dict]:
        return [{"severidade": sev, "codigo": cod, "quantidade": n}
                for (sev, cod), n in sorted(self.contagem.items(), key=lambda x: (x[0][0], -x[1]))]
