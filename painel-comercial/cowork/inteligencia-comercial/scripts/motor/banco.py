"""Banco SQLite local: mesmo modelo do PostgreSQL do sistema principal (docs/ARQUITETURA.md), simplificado.

Um arquivo só (base_comercial.db). Sem servidor. Criado na primeira importação.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

VERSAO_ESQUEMA = 1

ESQUEMA = """
CREATE TABLE IF NOT EXISTS importacao (
    id INTEGER PRIMARY KEY, fonte TEXT NOT NULL, modo TEXT NOT NULL, status TEXT NOT NULL,
    arquivo TEXT NOT NULL, sha256 TEXT NOT NULL, iniciado_em TEXT NOT NULL DEFAULT (datetime('now')),
    concluido_em TEXT, linhas_lidas INTEGER, linhas_ignoradas INTEGER, erros INTEGER, avisos INTEGER,
    resumo TEXT, mensagem TEXT
);
CREATE TABLE IF NOT EXISTS ocorrencia (
    importacao_id INTEGER NOT NULL REFERENCES importacao(id), severidade TEXT, codigo TEXT,
    linha INTEGER, coluna TEXT, valor TEXT, mensagem TEXT
);

CREATE TABLE IF NOT EXISTS uf (sigla TEXT PRIMARY KEY, nome TEXT, regiao_geografica TEXT);
CREATE TABLE IF NOT EXISTS regiao_ensino (
    id INTEGER PRIMARY KEY, uf TEXT NOT NULL, nome TEXT NOT NULL, nome_norm TEXT NOT NULL, UNIQUE (uf, nome_norm));
CREATE TABLE IF NOT EXISTS cidade (
    id INTEGER PRIMARY KEY, uf TEXT NOT NULL, nome TEXT NOT NULL, nome_norm TEXT NOT NULL, UNIQUE (uf, nome_norm));
CREATE TABLE IF NOT EXISTS escola (
    id INTEGER PRIMARY KEY, uf TEXT NOT NULL, cidade_id INTEGER NOT NULL DEFAULT 0, regiao_ensino_id INTEGER,
    nome TEXT NOT NULL, nome_norm TEXT NOT NULL, bairro TEXT, UNIQUE (uf, cidade_id, nome_norm));
CREATE TABLE IF NOT EXISTS grupo (id INTEGER PRIMARY KEY, nome TEXT NOT NULL, nome_norm TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS instituicao (
    id INTEGER PRIMARY KEY, nome TEXT NOT NULL, nome_norm TEXT NOT NULL UNIQUE, sigla TEXT,
    grupo_id INTEGER REFERENCES grupo(id), porte TEXT, afiliado TEXT, comissao_valor REAL, tipo_comissao TEXT,
    status_comercial TEXT, origem TEXT NOT NULL, qualidade TEXT NOT NULL DEFAULT 'ok',
    verificada INTEGER NOT NULL DEFAULT 0, hash_atributos TEXT);
CREATE TABLE IF NOT EXISTS instituicao_alias (
    nome_norm TEXT PRIMARY KEY, instituicao_id INTEGER NOT NULL REFERENCES instituicao(id), origem TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS curso (id INTEGER PRIMARY KEY, nome TEXT NOT NULL, nome_norm TEXT NOT NULL UNIQUE, grau TEXT);
CREATE TABLE IF NOT EXISTS modalidade (id INTEGER PRIMARY KEY, nome TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS aluno (
    id TEXT PRIMARY KEY, uf TEXT, cidade_id INTEGER, regiao_ensino_id INTEGER, escola_id INTEGER,
    cadastrado_em TEXT, ano_cadastro INTEGER, data_nascimento TEXT, genero TEXT, situacao_atual TEXT,
    plano_pos_medio TEXT, aceita_comunicados INTEGER, concluiu_relatorio INTEGER,
    hash TEXT NOT NULL, ativo INTEGER NOT NULL DEFAULT 1, removido_em TEXT,
    importacao_criacao INTEGER, importacao_alteracao INTEGER);
CREATE TABLE IF NOT EXISTS aluno_curso (
    aluno_id TEXT NOT NULL, posicao INTEGER NOT NULL, curso_id INTEGER NOT NULL, PRIMARY KEY (aluno_id, posicao));
CREATE TABLE IF NOT EXISTS aluno_modalidade (
    aluno_id TEXT NOT NULL, modalidade_id INTEGER NOT NULL, ordem INTEGER, PRIMARY KEY (aluno_id, modalidade_id));
CREATE TABLE IF NOT EXISTS interesse (
    aluno_id TEXT NOT NULL, posicao INTEGER NOT NULL, instituicao_id INTEGER NOT NULL, nome_origem TEXT,
    hash TEXT NOT NULL, ativo INTEGER NOT NULL DEFAULT 1, removido_em TEXT,
    importacao_criacao INTEGER, importacao_alteracao INTEGER, PRIMARY KEY (aluno_id, posicao));

CREATE TABLE IF NOT EXISTS volume_instituicao_anual (
    instituicao_id INTEGER NOT NULL, uf TEXT NOT NULL, ano INTEGER NOT NULL, total INTEGER NOT NULL,
    PRIMARY KEY (instituicao_id, uf, ano));
CREATE TABLE IF NOT EXISTS volume_curso_anual (
    curso_id INTEGER NOT NULL, uf TEXT NOT NULL, ano INTEGER NOT NULL, total INTEGER NOT NULL,
    PRIMARY KEY (curso_id, uf, ano));
CREATE TABLE IF NOT EXISTS volume_cidade_anual (
    cidade_id INTEGER NOT NULL, ano INTEGER NOT NULL, leads_3a_serie INTEGER, leads_9o_ano INTEGER,
    PRIMARY KEY (cidade_id, ano));

CREATE TABLE IF NOT EXISTS snapshot_metrica (
    importacao_id INTEGER NOT NULL, dimensao TEXT NOT NULL, chave TEXT NOT NULL, rotulo TEXT,
    alunos INTEGER, interesses INTEGER, PRIMARY KEY (importacao_id, dimensao, chave));

CREATE INDEX IF NOT EXISTS aluno_uf_idx ON aluno (uf) WHERE ativo = 1;
CREATE INDEX IF NOT EXISTS aluno_cidade_idx ON aluno (cidade_id);
CREATE INDEX IF NOT EXISTS aluno_regiao_idx ON aluno (regiao_ensino_id);
CREATE INDEX IF NOT EXISTS aluno_escola_idx ON aluno (escola_id);
CREATE INDEX IF NOT EXISTS aluno_curso_curso_idx ON aluno_curso (curso_id, aluno_id);
CREATE INDEX IF NOT EXISTS aluno_mod_mod_idx ON aluno_modalidade (modalidade_id, aluno_id);
CREATE INDEX IF NOT EXISTS interesse_inst_idx ON interesse (instituicao_id, aluno_id);

-- Visões usadas por todas as consultas: só registros ativos, com rótulos e faixa etária resolvidos.
CREATE VIEW IF NOT EXISTS v_aluno AS
SELECT a.*, u.regiao_geografica,
       CASE WHEN a.data_nascimento IS NULL THEN 'Não informado'
            WHEN date(a.data_nascimento, '+14 years') > date('now') THEN 'Até 13 anos'
            WHEN date(a.data_nascimento, '+18 years') > date('now') THEN '14 a 17 anos'
            WHEN date(a.data_nascimento, '+25 years') > date('now') THEN '18 a 24 anos'
            ELSE '25 anos ou mais' END AS faixa_etaria
FROM aluno a LEFT JOIN uf u ON u.sigla = a.uf WHERE a.ativo = 1;

CREATE VIEW IF NOT EXISTS v_interesse AS
SELECT i.aluno_id, i.posicao, i.instituicao_id, inst.grupo_id, inst.qualidade, inst.status_comercial
FROM interesse i JOIN instituicao inst ON inst.id = i.instituicao_id
JOIN aluno a ON a.id = i.aluno_id AND a.ativo = 1
WHERE i.ativo = 1;
"""

UFS = [
    ("AC", "Acre", "Norte"), ("AL", "Alagoas", "Nordeste"), ("AP", "Amapá", "Norte"), ("AM", "Amazonas", "Norte"),
    ("BA", "Bahia", "Nordeste"), ("CE", "Ceará", "Nordeste"), ("DF", "Distrito Federal", "Centro-Oeste"),
    ("ES", "Espírito Santo", "Sudeste"), ("GO", "Goiás", "Centro-Oeste"), ("MA", "Maranhão", "Nordeste"),
    ("MT", "Mato Grosso", "Centro-Oeste"), ("MS", "Mato Grosso do Sul", "Centro-Oeste"),
    ("MG", "Minas Gerais", "Sudeste"), ("PA", "Pará", "Norte"), ("PB", "Paraíba", "Nordeste"),
    ("PR", "Paraná", "Sul"), ("PE", "Pernambuco", "Nordeste"), ("PI", "Piauí", "Nordeste"),
    ("RJ", "Rio de Janeiro", "Sudeste"), ("RN", "Rio Grande do Norte", "Nordeste"),
    ("RS", "Rio Grande do Sul", "Sul"), ("RO", "Rondônia", "Norte"), ("RR", "Roraima", "Norte"),
    ("SC", "Santa Catarina", "Sul"), ("SP", "São Paulo", "Sudeste"), ("SE", "Sergipe", "Nordeste"),
    ("TO", "Tocantins", "Norte"),
]
MODALIDADES = [(1, "Presencial"), (2, "Híbrido"), (3, "Online (EAD)")]


def caminho_padrao() -> Path:
    """PAINEL_BASE, ou ./dados_painel/base_comercial.db na pasta de trabalho."""
    return Path(os.environ.get("PAINEL_BASE", Path.cwd() / "dados_painel" / "base_comercial.db"))


def conectar(caminho: Path | None = None) -> sqlite3.Connection:
    caminho = Path(caminho or caminho_padrao())
    caminho.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(caminho, isolation_level=None)   # transações explícitas (BEGIN/COMMIT)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(ESQUEMA)
    conn.executemany("INSERT OR IGNORE INTO uf VALUES (?, ?, ?)", UFS)
    conn.executemany("INSERT OR IGNORE INTO modalidade VALUES (?, ?)", MODALIDADES)
    conn.execute(f"PRAGMA user_version = {VERSAO_ESQUEMA}")
    return conn
