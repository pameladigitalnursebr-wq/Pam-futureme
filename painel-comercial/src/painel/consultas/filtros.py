"""Dimensões pesquisáveis e tradução de filtros combinados em SQL parametrizado.

Só dimensões desta lista podem ser filtradas ou ranqueadas: não existe SQL livre.
Filtros são cumulativos: E entre dimensões, OU entre valores da mesma dimensão.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

# Nível "interesse": atributo da opção de instituição. Nível "aluno": atributo do aluno.
INTERESSE = "interesse"
ALUNO = "aluno"


@dataclass(frozen=True)
class Dimensao:
    nome: str
    titulo: str
    coluna: str
    nivel: str
    tipo: str = "int"                 # int | text | bool
    vetor: bool = False               # coluna é um array (pódio de cursos, modalidades)
    tabela: str | None = None         # tabela de rótulos (id -> nome)
    rotulo: str = "nome"              # expressão SQL do rótulo na tabela
    busca: str = "nome_norm"          # coluna para busca textual na tabela
    tipo_pg: str | None = None        # tipo do array no PostgreSQL, quando difere do padrão
    chave_tabela: str = "id"          # coluna da tabela de rótulos que corresponde ao valor


DIMENSOES: dict[str, Dimensao] = {d.nome: d for d in (
    Dimensao("instituicao", "Instituição", "instituicao_id", INTERESSE, tabela="core.instituicao"),
    Dimensao("grupo", "Grupo educacional", "grupo_id", INTERESSE, tabela="core.grupo_educacional"),
    Dimensao("posicao", "Posição da opção", "posicao", INTERESSE),
    Dimensao("status_comercial", "Status comercial", "status_comercial", INTERESSE, tipo="text"),
    Dimensao("curso", "Curso (pódio do aluno)", "cursos", ALUNO, vetor=True, tabela="core.curso"),
    Dimensao("modalidade", "Modalidade", "modalidades", ALUNO, vetor=True, tabela="core.modalidade",
             busca="nome", tipo_pg="smallint[]"),
    Dimensao("uf", "Estado", "uf", ALUNO, tipo="text", tabela="core.uf", rotulo="sigla || ' – ' || nome",
             busca="sigla || ' ' || nome", chave_tabela="sigla"),
    Dimensao("regiao_geografica", "Região do país", "regiao_geografica", ALUNO, tipo="text"),
    Dimensao("regiao_ensino", "Região de ensino", "regiao_ensino_id", ALUNO, tabela="core.regiao_ensino",
             rotulo="nome || ' (' || uf || ')'"),
    Dimensao("cidade", "Cidade", "cidade_id", ALUNO, tabela="core.cidade", rotulo="nome || ' (' || uf || ')'"),
    Dimensao("escola", "Escola", "escola_id", ALUNO, tabela="core.escola", rotulo="nome || ' (' || uf || ')'"),
    Dimensao("ano_cadastro", "Ano de cadastro", "ano_cadastro", ALUNO),
    Dimensao("faixa_etaria", "Faixa etária", "faixa_etaria", ALUNO, tipo="text"),
    Dimensao("genero", "Gênero", "genero", ALUNO, tipo="text"),
    Dimensao("situacao_atual", "Faz no momento", "situacao_atual", ALUNO, tipo="text"),
    Dimensao("plano_pos_medio", "Plano pós-médio", "plano_pos_medio", ALUNO, tipo="text"),
    Dimensao("aceita_comunicados", "Aceita comunicados", "aceita_comunicados", ALUNO, tipo="bool"),
)}

_TIPOS_PG = {"int": "int[]", "text": "text[]", "bool": "boolean[]"}


def _converter(dim: Dimensao, valor: Any) -> Any:
    if dim.tipo == "int":
        return int(valor)
    if dim.tipo == "bool":
        if isinstance(valor, bool):
            return valor
        return str(valor).strip().lower() in {"true", "1", "sim", "s"}
    return str(valor)


class FiltroInvalido(ValueError):
    pass


@dataclass
class Filtros:
    valores: dict[str, list[Any]] = field(default_factory=dict)
    incluir_suspeitas: bool = False   # instituições com nome suspeito ('3', 'privado'...)

    @classmethod
    def de_dict(cls, dados: dict[str, Any] | None) -> "Filtros":
        """Aceita {"uf": ["SP"], "curso": "12,15", "incluir_suspeitas": true}."""
        dados = dict(dados or {})
        suspeitas = dados.pop("incluir_suspeitas", False)
        valores: dict[str, list[Any]] = {}
        for nome, bruto in dados.items():
            if bruto in (None, "", []):
                continue
            dim = DIMENSOES.get(nome)
            if dim is None:
                raise FiltroInvalido(f"Filtro desconhecido: '{nome}'. Use um de: {', '.join(DIMENSOES)}.")
            itens = bruto.split(",") if isinstance(bruto, str) else (bruto if isinstance(bruto, list) else [bruto])
            try:
                convertidos = sorted({_converter(dim, v) for v in itens if str(v).strip() != ""})
            except ValueError as e:
                raise FiltroInvalido(f"Valor inválido para '{nome}': {bruto}") from e
            if convertidos:
                valores[nome] = convertidos
        if isinstance(suspeitas, str):
            suspeitas = suspeitas.lower() in {"true", "1", "sim"}
        return cls(valores, bool(suspeitas))

    def com(self, nome: str, valores: list[Any]) -> "Filtros":
        novo = dict(self.valores)
        novo[nome] = valores
        return Filtros(novo, self.incluir_suspeitas)

    def sem(self, nome: str) -> "Filtros":
        return Filtros({k: v for k, v in self.valores.items() if k != nome}, self.incluir_suspeitas)

    @property
    def tem_nivel_interesse(self) -> bool:
        return any(DIMENSOES[n].nivel == INTERESSE for n in self.valores)

    def chave_cache(self) -> str:
        return json.dumps({"v": self.valores, "s": self.incluir_suspeitas}, sort_keys=True, default=str)

    def como_dict(self) -> dict[str, Any]:
        return {**self.valores, **({"incluir_suspeitas": True} if self.incluir_suspeitas else {})}

    def where(self, nivel: str, alias: str = "m") -> tuple[str, list[Any]]:
        """Cláusula WHERE para a visão do nível dado ('aluno' ignora filtros de interesse)."""
        partes: list[str] = []
        params: list[Any] = []
        for nome, vals in self.valores.items():
            dim = DIMENSOES[nome]
            if dim.nivel == INTERESSE and nivel != INTERESSE:
                continue
            tipo_pg = dim.tipo_pg or _TIPOS_PG[dim.tipo]
            if dim.vetor:
                partes.append(f"{alias}.{dim.coluna} && %s::{tipo_pg}")
            else:
                partes.append(f"{alias}.{dim.coluna} = ANY(%s::{tipo_pg})")
            params.append(vals)
        if nivel == INTERESSE and not self.incluir_suspeitas:
            partes.append(f"{alias}.instituicao_qualidade = 'ok'")
        return (" AND ".join(partes) if partes else "true"), params

    def where_alunos(self, alias: str = "m") -> tuple[str, list[Any]]:
        """Alunos do recorte: filtros de aluno + (se houver) existência de interesse que bata."""
        sql, params = self.where(ALUNO, alias)
        if self.tem_nivel_interesse:
            sql_i, params_i = self.where(INTERESSE, "i")
            sql += f" AND EXISTS (SELECT 1 FROM ana.mv_interesse i WHERE i.aluno_id = {alias}.aluno_id AND {sql_i})"
            params += params_i
        return sql, params
