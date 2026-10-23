"""Mapeamento de colunas das planilhas para os nomes canônicos do sistema.

Para aceitar uma coluna nova ou uma grafia diferente de cabeçalho, acrescente aqui.
Os sinônimos são comparados sem acento, sem maiúsculas e sem pontuação.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..normalizacao import chave_coluna


@dataclass(frozen=True)
class Coluna:
    nome: str
    sinonimos: tuple[str, ...]
    obrigatoria: bool = False


@dataclass(frozen=True)
class Esquema:
    nome: str
    fonte: str          # tipo de importação a que pertence: leads | instituicoes
    descricao: str
    colunas: tuple[Coluna, ...]

    def obrigatorias(self) -> list[str]:
        return [c.nome for c in self.colunas if c.obrigatoria]

    def mapear(self, cabecalho: list[object]) -> tuple[dict[str, int], list[str]]:
        """Devolve {nome canônico: índice da coluna} e a lista de colunas não reconhecidas."""
        indice_por_chave: dict[str, int] = {}
        for i, nome in enumerate(cabecalho):
            k = chave_coluna(nome)
            if k and k not in indice_por_chave:
                indice_por_chave[k] = i
        mapa: dict[str, int] = {}
        usados: set[int] = set()
        for col in self.colunas:
            for sinonimo in (col.nome, *col.sinonimos):
                i = indice_por_chave.get(chave_coluna(sinonimo))
                if i is not None and i not in usados:
                    mapa[col.nome] = i
                    usados.add(i)
                    break
        desconhecidas = [str(cabecalho[i]) for i in sorted(indice_por_chave.values()) if i not in usados]
        return mapa, desconhecidas


LEADS = Esquema(
    nome="leads",
    fonte="leads",
    descricao="Base de interessados (uma linha por opção de instituição do aluno)",
    colunas=(
        Coluna("aluno_id", ("ID", "id aluno", "id do aluno", "uuid"), obrigatoria=True),
        Coluna("cadastrado_em", ("Criado em...", "criado em", "data de cadastro", "data cadastro")),
        Coluna("escola", ("Escola", "nome da escola")),
        Coluna("uf", ("Estado", "UF"), obrigatoria=True),
        Coluna("regiao_ensino", ("Região", "regiao de ensino", "diretoria de ensino")),
        Coluna("cidade", ("Cidade", "municipio")),
        Coluna("bairro", ("Bairro da escola", "bairro")),
        Coluna("data_nascimento", ("Data de nascimento", "nascimento")),
        Coluna("genero", ("Gênero", "sexo")),
        Coluna("situacao_atual", ("Faz no Momento", "situacao atual")),
        Coluna("plano_pos_medio", ("Plano pós médio", "plano pos ensino medio")),
        Coluna("aceita_comunicados", ("Receber comunicados", "aceita comunicados")),
        Coluna("curso_1", ("PodioCursos1", "podio cursos 1", "curso 1")),
        Coluna("curso_2", ("PodioCursos2", "podio cursos 2", "curso 2")),
        Coluna("curso_3", ("PodioCursos3", "podio cursos 3", "curso 3")),
        Coluna("posicao", ("Posição da opção de faculdade", "posicao da opcao", "posicao"), obrigatoria=True),
        Coluna("instituicao", ("Instituição Privada", "instituicao", "instituicao de interesse"), obrigatoria=True),
        Coluna("modalidade", ("Modalidade", "modalidades")),
        Coluna("concluiu_relatorio", ("Concluiu Relatório de Perfil Profissional", "concluiu relatorio")),
    ),
)

UNIVERSIDADES = Esquema(
    nome="universidades",
    fonte="instituicoes",
    descricao="Instituições, atributos comerciais e total de leads por UF e ano",
    colunas=(
        Coluna("uf", ("UF", "Estado"), obrigatoria=True),
        Coluna("ano", ("Ano", "ano cadastro"), obrigatoria=True),
        Coluna("instituicao", ("Universidade", "Instituição", "instituicao privada"), obrigatoria=True),
        Coluna("total", ("Total", "total leads"), obrigatoria=True),
        Coluna("porte", ("Porte",)),
        Coluna("grupo", ("Grupo", "grupo educacional")),
        Coluna("afiliado", ("Afiliado",)),
        Coluna("comissao", ("Comissão", "valor comissao")),
        Coluna("tipo_comissao", ("Tipo de comissão",)),
        Coluna("status_comercial", ("Comercial", "status comercial")),
    ),
)

CURSOS = Esquema(
    nome="cursos",
    fonte="instituicoes",
    descricao="Total de leads por curso, UF e ano",
    colunas=(
        Coluna("uf", ("UF", "Estado"), obrigatoria=True),
        Coluna("ano", ("Ano", "ano cadastro"), obrigatoria=True),
        Coluna("curso", ("Curso",), obrigatoria=True),
        Coluna("total", ("Total", "total leads"), obrigatoria=True),
    ),
)

CIDADES = Esquema(
    nome="cidades",
    fonte="instituicoes",
    descricao="Leads da 3ª série e do 9º ano por cidade e ano",
    colunas=(
        Coluna("uf", ("Estado", "UF"), obrigatoria=True),
        Coluna("regiao", ("Região",)),
        Coluna("cidade", ("Cidade", "municipio"), obrigatoria=True),
        Coluna("ano", ("Ano Cadastro", "ano"), obrigatoria=True),
        Coluna("leads_3a_serie", ("Total Leads 3ª série", "leads 3a serie"), obrigatoria=True),
        Coluna("leads_9o_ano", ("Total Leads 9º ano", "leads 9o ano")),
    ),
)

ESCOLAS = Esquema(
    nome="escolas",
    fonte="instituicoes",
    descricao="Total de leads por escola e ano",
    colunas=(
        Coluna("uf", ("Estado", "UF"), obrigatoria=True),
        Coluna("regiao", ("Região",)),
        Coluna("cidade", ("Cidade",), obrigatoria=True),
        Coluna("escola", ("Escola",), obrigatoria=True),
        Coluna("ano", ("Ano_Cadastro", "ano cadastro", "ano"), obrigatoria=True),
        Coluna("total", ("Total_Leads", "total leads", "total"), obrigatoria=True),
    ),
)

# Ordem importa: o primeiro esquema cujas colunas obrigatórias estão todas presentes vence.
ESQUEMAS: tuple[Esquema, ...] = (LEADS, UNIVERSIDADES, ESCOLAS, CIDADES, CURSOS)
