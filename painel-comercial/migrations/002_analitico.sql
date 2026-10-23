-- 002 · Camada analítica (schema ana)
-- Visões materializadas desnormalizadas: uma linha por aluno / por interesse,
-- com todas as chaves de filtro resolvidas e indexadas. Atualizadas ao fim de
-- cada importação (REFRESH ... CONCURRENTLY, sem bloquear leituras).

CREATE SCHEMA IF NOT EXISTS ana;

CREATE MATERIALIZED VIEW ana.mv_aluno AS
SELECT
    a.id                                   AS aluno_id,
    a.uf,
    u.regiao_geografica,
    a.cidade_id,
    a.regiao_ensino_id,
    a.escola_id,
    COALESCE(a.genero, 'Não informado')    AS genero,
    a.cadastrado_em,
    EXTRACT(YEAR FROM a.cadastrado_em)::smallint AS ano_cadastro,
    CASE
        WHEN a.data_nascimento IS NULL THEN 'Não informado'
        WHEN age(current_date, a.data_nascimento) < interval '14 years' THEN 'Até 13 anos'
        WHEN age(current_date, a.data_nascimento) < interval '18 years' THEN '14 a 17 anos'
        WHEN age(current_date, a.data_nascimento) < interval '25 years' THEN '18 a 24 anos'
        ELSE '25 anos ou mais'
    END                                    AS faixa_etaria,
    a.situacao_atual,
    a.plano_pos_medio,
    a.aceita_comunicados,
    a.concluiu_relatorio,
    COALESCE((SELECT array_agg(ac.curso_id ORDER BY ac.posicao)
              FROM core.aluno_curso ac WHERE ac.aluno_id = a.id), '{}')        AS cursos,
    COALESCE((SELECT array_agg(am.modalidade_id ORDER BY am.ordem)
              FROM core.aluno_modalidade am WHERE am.aluno_id = a.id), '{}')   AS modalidades,
    EXISTS (SELECT 1 FROM core.interesse i WHERE i.aluno_id = a.id AND i.ativo) AS tem_interesse
FROM core.aluno a
LEFT JOIN core.uf u ON u.sigla = a.uf
WHERE a.ativo;

CREATE UNIQUE INDEX mv_aluno_pk ON ana.mv_aluno (aluno_id);
CREATE INDEX mv_aluno_uf_idx ON ana.mv_aluno (uf);
CREATE INDEX mv_aluno_cidade_idx ON ana.mv_aluno (cidade_id);
CREATE INDEX mv_aluno_regiao_idx ON ana.mv_aluno (regiao_ensino_id);
CREATE INDEX mv_aluno_escola_idx ON ana.mv_aluno (escola_id);
CREATE INDEX mv_aluno_ano_idx ON ana.mv_aluno (ano_cadastro);
CREATE INDEX mv_aluno_cursos_idx ON ana.mv_aluno USING gin (cursos);
CREATE INDEX mv_aluno_modalidades_idx ON ana.mv_aluno USING gin (modalidades);

CREATE MATERIALIZED VIEW ana.mv_interesse AS
SELECT
    i.id                 AS interesse_id,
    i.posicao,
    i.instituicao_id,
    inst.grupo_id,
    inst.qualidade       AS instituicao_qualidade,
    inst.status_comercial,
    m.*
FROM core.interesse i
JOIN core.instituicao inst ON inst.id = i.instituicao_id
JOIN ana.mv_aluno m        ON m.aluno_id = i.aluno_id
WHERE i.ativo;

CREATE UNIQUE INDEX mv_interesse_pk ON ana.mv_interesse (interesse_id);
CREATE INDEX mv_interesse_inst_idx ON ana.mv_interesse (instituicao_id);
CREATE INDEX mv_interesse_grupo_idx ON ana.mv_interesse (grupo_id);
CREATE INDEX mv_interesse_aluno_idx ON ana.mv_interesse (aluno_id);
CREATE INDEX mv_interesse_uf_idx ON ana.mv_interesse (uf);
CREATE INDEX mv_interesse_cidade_idx ON ana.mv_interesse (cidade_id);
CREATE INDEX mv_interesse_regiao_idx ON ana.mv_interesse (regiao_ensino_id);
CREATE INDEX mv_interesse_escola_idx ON ana.mv_interesse (escola_id);
CREATE INDEX mv_interesse_ano_idx ON ana.mv_interesse (ano_cadastro);
CREATE INDEX mv_interesse_cursos_idx ON ana.mv_interesse USING gin (cursos);
CREATE INDEX mv_interesse_modalidades_idx ON ana.mv_interesse USING gin (modalidades);

-- Fotografia das métricas a cada importação: base da análise temporal,
-- do ranking histórico e da comparação entre importações.
CREATE TABLE ana.snapshot_metrica (
    importacao_id bigint NOT NULL REFERENCES imp.importacao (id) ON DELETE CASCADE,
    dimensao      text NOT NULL,         -- total | instituicao | curso | uf | cidade | grupo
    chave         text NOT NULL,         -- id da dimensão (texto) ou 'total'
    rotulo        text NOT NULL,
    interesses    integer NOT NULL,
    alunos        integer NOT NULL,
    PRIMARY KEY (importacao_id, dimensao, chave)
);
CREATE INDEX snapshot_metrica_dim_idx ON ana.snapshot_metrica (dimensao, chave, importacao_id);
