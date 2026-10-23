-- 003 · Segurança, permissões e trilhas (schema seg)

CREATE SCHEMA IF NOT EXISTS seg;

CREATE TABLE seg.usuario (
    id             bigserial PRIMARY KEY,
    email          text NOT NULL UNIQUE CHECK (email = lower(email)),
    nome           text NOT NULL,
    papel          text NOT NULL CHECK (papel IN ('admin', 'gestor', 'analista', 'leitor')),
    senha_hash     text,                        -- nulo enquanto o convite não foi aceito / SSO
    ativo          boolean NOT NULL DEFAULT true,
    criado_em      timestamptz NOT NULL DEFAULT now(),
    ultimo_acesso  timestamptz
);

-- Chaves para integrações (conector MCP do Claude, automações, BI).
-- Só o hash é guardado; a chave aparece uma única vez, na criação.
CREATE TABLE seg.chave_api (
    id            bigserial PRIMARY KEY,
    usuario_id    bigint NOT NULL REFERENCES seg.usuario (id),
    nome          text NOT NULL,
    prefixo       text NOT NULL,               -- primeiros caracteres, para identificar na lista
    hash          text NOT NULL UNIQUE,
    escopos       text[] NOT NULL,             -- ex.: {consulta}
    criado_em     timestamptz NOT NULL DEFAULT now(),
    ultimo_uso    timestamptz,
    revogada_em   timestamptz
);

-- Histórico de consultas (painel, API e Claude).
CREATE TABLE seg.consulta_log (
    id          bigserial PRIMARY KEY,
    usuario_id  bigint REFERENCES seg.usuario (id),
    origem      text NOT NULL CHECK (origem IN ('web', 'api', 'mcp', 'cli')),
    operacao    text NOT NULL,
    parametros  jsonb NOT NULL DEFAULT '{}'::jsonb,
    duracao_ms  integer,
    criado_em   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX consulta_log_data_idx ON seg.consulta_log (criado_em DESC);
CREATE INDEX consulta_log_usuario_idx ON seg.consulta_log (usuario_id, criado_em DESC);

-- Ações administrativas (importações, unificação de instituições, usuários).
CREATE TABLE seg.auditoria (
    id          bigserial PRIMARY KEY,
    usuario_id  bigint REFERENCES seg.usuario (id),
    acao        text NOT NULL,
    alvo        text,
    detalhes    jsonb NOT NULL DEFAULT '{}'::jsonb,
    criado_em   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX auditoria_data_idx ON seg.auditoria (criado_em DESC);

-- Consultas salvas por usuário (base para dashboards personalizados e alertas).
CREATE TABLE seg.consulta_salva (
    id          bigserial PRIMARY KEY,
    usuario_id  bigint NOT NULL REFERENCES seg.usuario (id) ON DELETE CASCADE,
    nome        text NOT NULL,
    filtros     jsonb NOT NULL,
    compartilhada boolean NOT NULL DEFAULT false,
    criado_em   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (usuario_id, nome)
);

ALTER TABLE imp.importacao
    ADD CONSTRAINT importacao_usuario_fk FOREIGN KEY (usuario_id) REFERENCES seg.usuario (id);
