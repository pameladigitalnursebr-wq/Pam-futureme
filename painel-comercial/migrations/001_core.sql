-- 001 · Modelo de negócio (schema core) e controle de importações (schema imp)
-- Fonte de verdade do painel. Ver docs/ARQUITETURA.md, seções 2 a 4.

CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;

CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS imp;

-- ---------------------------------------------------------------------------
-- Importações (criada primeiro: as tabelas de negócio apontam para ela)
-- ---------------------------------------------------------------------------
CREATE TABLE imp.importacao (
    id               bigserial PRIMARY KEY,
    fonte            text NOT NULL CHECK (fonte IN ('leads', 'instituicoes')),
    modo             text NOT NULL CHECK (modo IN ('completo', 'incremental')),
    status           text NOT NULL DEFAULT 'processando'
                     CHECK (status IN ('processando', 'concluida', 'falhou', 'rejeitada')),
    arquivo_nome     text NOT NULL,
    arquivo_sha256   text NOT NULL,
    arquivo_bytes    bigint,
    usuario_id       bigint,                       -- FK criada em 003 (seg.usuario)
    iniciado_em      timestamptz NOT NULL DEFAULT now(),
    concluido_em     timestamptz,
    duracao_ms       integer,
    linhas_lidas     integer NOT NULL DEFAULT 0,
    linhas_ignoradas integer NOT NULL DEFAULT 0,
    total_erros      integer NOT NULL DEFAULT 0,
    total_avisos     integer NOT NULL DEFAULT 0,
    resumo           jsonb NOT NULL DEFAULT '{}'::jsonb,  -- contagens por entidade (novos, atualizados...)
    mensagem         text
);
CREATE INDEX importacao_fonte_idx ON imp.importacao (fonte, iniciado_em DESC);
CREATE INDEX importacao_sha_idx ON imp.importacao (arquivo_sha256) WHERE status = 'concluida';

CREATE TABLE imp.importacao_ocorrencia (
    id            bigserial PRIMARY KEY,
    importacao_id bigint NOT NULL REFERENCES imp.importacao (id) ON DELETE CASCADE,
    severidade    text NOT NULL CHECK (severidade IN ('erro', 'aviso')),
    codigo        text NOT NULL,
    linha         integer,             -- linha da planilha (1 = cabeçalho)
    coluna        text,
    valor         text,
    mensagem      text NOT NULL
);
CREATE INDEX importacao_ocorrencia_imp_idx ON imp.importacao_ocorrencia (importacao_id, severidade, codigo);

-- Versão da base: avança a cada importação concluída. Usada como chave do cache.
CREATE TABLE imp.estado (
    id                 boolean PRIMARY KEY DEFAULT true CHECK (id),
    versao             bigint NOT NULL DEFAULT 0,
    ultima_importacao  bigint REFERENCES imp.importacao (id),
    atualizado_em      timestamptz NOT NULL DEFAULT now()
);
INSERT INTO imp.estado DEFAULT VALUES;

-- ---------------------------------------------------------------------------
-- Dimensões geográficas e de origem do aluno
-- ---------------------------------------------------------------------------
CREATE TABLE core.uf (
    sigla             char(2) PRIMARY KEY,
    nome              text NOT NULL,
    regiao_geografica text NOT NULL
);

CREATE TABLE core.regiao_ensino (
    id        serial PRIMARY KEY,
    uf        char(2) NOT NULL REFERENCES core.uf (sigla),
    nome      text NOT NULL,
    nome_norm text NOT NULL,
    UNIQUE (uf, nome_norm)
);

CREATE TABLE core.cidade (
    id           serial PRIMARY KEY,
    uf           char(2) NOT NULL REFERENCES core.uf (sigla),
    nome         text NOT NULL,
    nome_norm    text NOT NULL,
    codigo_ibge  integer,                     -- reservado para o mapa (roadmap)
    UNIQUE (uf, nome_norm)
);
CREATE INDEX cidade_trgm_idx ON core.cidade USING gin (nome_norm gin_trgm_ops);

CREATE TABLE core.escola (
    id               serial PRIMARY KEY,
    uf               char(2) NOT NULL REFERENCES core.uf (sigla),
    cidade_id        integer REFERENCES core.cidade (id),
    regiao_ensino_id integer REFERENCES core.regiao_ensino (id),
    nome             text NOT NULL,
    nome_norm        text NOT NULL,
    bairro           text,
    UNIQUE NULLS NOT DISTINCT (uf, cidade_id, nome_norm)
);
CREATE INDEX escola_trgm_idx ON core.escola USING gin (nome_norm gin_trgm_ops);

-- ---------------------------------------------------------------------------
-- Instituições (Base 1) e cursos
-- ---------------------------------------------------------------------------
CREATE TABLE core.grupo_educacional (
    id        serial PRIMARY KEY,
    nome      text NOT NULL,
    nome_norm text NOT NULL UNIQUE
);

CREATE TABLE core.instituicao (
    id               serial PRIMARY KEY,
    nome             text NOT NULL,               -- grafia de exibição ("SIGLA - NOME")
    nome_norm        text NOT NULL UNIQUE,
    sigla            text,
    grupo_id         integer REFERENCES core.grupo_educacional (id),
    porte            text,
    afiliado         text,
    comissao_valor   numeric(10, 2),
    tipo_comissao    text,
    status_comercial text,
    origem           text NOT NULL CHECK (origem IN ('base_instituicoes', 'leads', 'manual')),
    qualidade        text NOT NULL DEFAULT 'ok' CHECK (qualidade IN ('ok', 'suspeita')),
    verificada       boolean NOT NULL DEFAULT false,
    atributos        jsonb NOT NULL DEFAULT '{}'::jsonb,  -- colunas futuras (código, cidade, tipo...)
    criado_em        timestamptz NOT NULL DEFAULT now(),
    atualizado_em    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX instituicao_trgm_idx ON core.instituicao USING gin (nome_norm gin_trgm_ops);
CREATE INDEX instituicao_grupo_idx ON core.instituicao (grupo_id);

-- Toda grafia (normalizada) que aponta para uma instituição, inclusive a própria.
-- Unificações confirmadas por um administrador viram linhas aqui.
CREATE TABLE core.instituicao_alias (
    nome_norm      text PRIMARY KEY,
    instituicao_id integer NOT NULL REFERENCES core.instituicao (id) ON DELETE CASCADE,
    origem         text NOT NULL CHECK (origem IN ('automatico', 'unificacao')),
    criado_em      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX instituicao_alias_inst_idx ON core.instituicao_alias (instituicao_id);

CREATE TABLE core.curso (
    id        serial PRIMARY KEY,
    nome      text NOT NULL,
    nome_norm text NOT NULL UNIQUE,
    grau      text NOT NULL DEFAULT 'Outro'
              CHECK (grau IN ('Bacharelado', 'Licenciatura', 'Tecnológico', 'Técnico', 'Outro'))
);
CREATE INDEX curso_trgm_idx ON core.curso USING gin (nome_norm gin_trgm_ops);

CREATE TABLE core.modalidade (
    id   smallint PRIMARY KEY,
    nome text NOT NULL UNIQUE
);
INSERT INTO core.modalidade (id, nome) VALUES (1, 'Presencial'), (2, 'Híbrido'), (3, 'Online (EAD)');

-- ---------------------------------------------------------------------------
-- Alunos e interesses (Base 2)
-- ---------------------------------------------------------------------------
CREATE TABLE core.aluno (
    id                    uuid PRIMARY KEY,        -- ID de origem da plataforma
    uf                    char(2) REFERENCES core.uf (sigla),
    cidade_id             integer REFERENCES core.cidade (id),
    regiao_ensino_id      integer REFERENCES core.regiao_ensino (id),
    escola_id             integer REFERENCES core.escola (id),
    cadastrado_em         timestamptz,
    data_nascimento       date,                    -- dado pessoal (menor): permissão dados_pessoais
    genero                text,
    situacao_atual        text,
    plano_pos_medio       text,
    aceita_comunicados    boolean,
    concluiu_relatorio    boolean,
    hash                  text NOT NULL,           -- conteúdo normalizado (detecção de alteração)
    ativo                 boolean NOT NULL DEFAULT true,
    removido_em           timestamptz,
    importacao_criacao    bigint NOT NULL REFERENCES imp.importacao (id),
    importacao_alteracao  bigint NOT NULL REFERENCES imp.importacao (id)
);
CREATE INDEX aluno_ativo_idx ON core.aluno (ativo);

CREATE TABLE core.aluno_curso (
    aluno_id uuid NOT NULL REFERENCES core.aluno (id) ON DELETE CASCADE,
    posicao  smallint NOT NULL CHECK (posicao BETWEEN 1 AND 3),
    curso_id integer NOT NULL REFERENCES core.curso (id),
    PRIMARY KEY (aluno_id, posicao)
);
CREATE INDEX aluno_curso_curso_idx ON core.aluno_curso (curso_id);

CREATE TABLE core.aluno_modalidade (
    aluno_id      uuid NOT NULL REFERENCES core.aluno (id) ON DELETE CASCADE,
    modalidade_id smallint NOT NULL REFERENCES core.modalidade (id),
    ordem         smallint NOT NULL,
    PRIMARY KEY (aluno_id, modalidade_id)
);

-- Fato principal: cada linha da planilha com instituição = um interesse.
CREATE TABLE core.interesse (
    id                       bigserial PRIMARY KEY,
    aluno_id                 uuid NOT NULL REFERENCES core.aluno (id) ON DELETE CASCADE,
    posicao                  smallint NOT NULL CHECK (posicao BETWEEN 1 AND 3),
    instituicao_id           integer NOT NULL REFERENCES core.instituicao (id),
    instituicao_nome_origem  text NOT NULL,        -- grafia exata recebida (rastreabilidade)
    hash                     text NOT NULL,
    ativo                    boolean NOT NULL DEFAULT true,
    removido_em              timestamptz,
    importacao_criacao       bigint NOT NULL REFERENCES imp.importacao (id),
    importacao_alteracao     bigint NOT NULL REFERENCES imp.importacao (id),
    UNIQUE (aluno_id, posicao)
);
CREATE INDEX interesse_instituicao_idx ON core.interesse (instituicao_id) WHERE ativo;

-- ---------------------------------------------------------------------------
-- Volumes históricos da Base 1 (substituídos a cada importação da Base 1)
-- ---------------------------------------------------------------------------
CREATE TABLE core.volume_instituicao_anual (
    instituicao_id integer NOT NULL REFERENCES core.instituicao (id) ON DELETE CASCADE,
    uf             char(2) NOT NULL REFERENCES core.uf (sigla),
    ano            smallint NOT NULL,
    total          integer NOT NULL,
    PRIMARY KEY (instituicao_id, uf, ano)
);

CREATE TABLE core.volume_curso_anual (
    curso_id integer NOT NULL REFERENCES core.curso (id) ON DELETE CASCADE,
    uf       char(2) NOT NULL REFERENCES core.uf (sigla),
    ano      smallint NOT NULL,
    total    integer NOT NULL,
    PRIMARY KEY (curso_id, uf, ano)
);

CREATE TABLE core.volume_cidade_anual (
    cidade_id       integer NOT NULL REFERENCES core.cidade (id) ON DELETE CASCADE,
    ano             smallint NOT NULL,
    leads_3a_serie  integer,
    leads_9o_ano    integer,
    PRIMARY KEY (cidade_id, ano)
);

CREATE TABLE core.volume_escola_anual (
    escola_id integer NOT NULL REFERENCES core.escola (id) ON DELETE CASCADE,
    ano       smallint NOT NULL,
    total     integer NOT NULL,
    PRIMARY KEY (escola_id, ano)
);

-- ---------------------------------------------------------------------------
-- Referência: UFs
-- ---------------------------------------------------------------------------
INSERT INTO core.uf (sigla, nome, regiao_geografica) VALUES
 ('AC','Acre','Norte'), ('AL','Alagoas','Nordeste'), ('AP','Amapá','Norte'), ('AM','Amazonas','Norte'),
 ('BA','Bahia','Nordeste'), ('CE','Ceará','Nordeste'), ('DF','Distrito Federal','Centro-Oeste'),
 ('ES','Espírito Santo','Sudeste'), ('GO','Goiás','Centro-Oeste'), ('MA','Maranhão','Nordeste'),
 ('MT','Mato Grosso','Centro-Oeste'), ('MS','Mato Grosso do Sul','Centro-Oeste'),
 ('MG','Minas Gerais','Sudeste'), ('PA','Pará','Norte'), ('PB','Paraíba','Nordeste'),
 ('PR','Paraná','Sul'), ('PE','Pernambuco','Nordeste'), ('PI','Piauí','Nordeste'),
 ('RJ','Rio de Janeiro','Sudeste'), ('RN','Rio Grande do Norte','Nordeste'),
 ('RS','Rio Grande do Sul','Sul'), ('RO','Rondônia','Norte'), ('RR','Roraima','Norte'),
 ('SC','Santa Catarina','Sul'), ('SP','São Paulo','Sudeste'), ('SE','Sergipe','Nordeste'),
 ('TO','Tocantins','Norte');
