# Painel de Inteligência Comercial — Arquitetura

Documento de referência do projeto. Explica o que foi construído, como as peças se encaixam e por que cada decisão foi tomada.
Público: equipe FutureMe (negócio e tecnologia). Atualizado em 23/10/2026.

> **Dados nunca entram no git.** O repositório é público. Planilhas, dumps e o banco ficam fora dele (ver `.gitignore`).
> Os testes usam dados sintéticos gerados no próprio código.

Sumário
1. [Arquitetura proposta](#1-arquitetura-proposta)
2. [Banco de dados](#2-banco-de-dados)
3. [Entidades](#3-entidades)
4. [Relacionamentos](#4-relacionamentos)
5. [Fluxo de importação](#5-fluxo-de-importação)
6. [Estrutura do painel](#6-estrutura-do-painel)
7. [Como o Claude (Conversas) consome os dados](#7-como-o-claude-conversas-consome-os-dados)
8. [Atualização da base](#8-atualização-da-base)
9. [Decisões arquiteturais](#9-decisões-arquiteturais)
10. [O que os dados permitem (e não permitem) responder](#10-o-que-os-dados-permitem-e-não-permitem-responder)
11. [Roadmap de evolução](#11-roadmap-de-evolução)

---

## 1. Arquitetura proposta

O sistema tem **uma única fonte de verdade** (o banco PostgreSQL) e **uma única camada de regras** (o serviço de consultas em Python).
Tudo o que mostra dados — painel web, API, exportação e o Claude — passa por essa mesma camada. Assim, um número nunca diverge entre o painel e uma resposta do Claude.

```
                 Planilhas exportadas (.xlsx / .csv)
                               │  upload (painel ou linha de comando)
                               ▼
┌───────────────────────────────────────────────────────────────────────┐
│ Serviço "painel-comercial" (Python · FastAPI)  ← construído no Claude Code │
│                                                                       │
│  importacao/   leitura → mapeamento de colunas → validação →          │
│                staging → detecção de mudanças → gravação → relatório  │
│                                                                       │
│  consultas/    filtros combinados · métricas · rankings ·             │
│                distribuições · busca · detalhe paginado · exportação  │
│                (cache por versão da base)                             │
│                                                                       │
│  seguranca/    usuários · papéis · permissões · chaves de API ·       │
│                log de consultas · auditoria                           │
│                                                                       │
│  api/  REST /api/*        web/  painel executivo        mcp/  /mcp     │
└────────────┬──────────────────────────┬──────────────────────┬────────┘
             │                          │                      │
             ▼                          ▼                      ▼
    PostgreSQL 16 (fonte única)   Navegador da equipe    Claude (Conversas):
    core · ana · imp · seg         (login FutureMe)       projeto + conector MCP
```

| Camada | Responsabilidade | Onde está |
|---|---|---|
| **Banco** | Guardar dados normalizados, histórico de importações, usuários e logs | `migrations/*.sql` |
| **Importação** | Transformar planilhas em dados confiáveis e detectar novas linhas, alterações e exclusões | `src/painel/importacao/` |
| **Consultas** | Única implementação de métricas, filtros e rankings | `src/painel/consultas/` |
| **Segurança** | Login, papéis, permissões, chaves de API, trilha de auditoria | `src/painel/seguranca/` |
| **API REST** | Expor consultas, importação e administração | `src/painel/api/` |
| **Painel web** | Interface executiva para usuários não técnicos | `src/painel/web/` |
| **Servidor MCP** | Ferramentas de consulta para o Claude | `src/painel/mcp/` |
| **Projeto no Claude** | Instruções e configuração do "Cloud Conversas" | `conversas/` |

**Divisão de papéis pedida no briefing**
- *Claude Code* (este repositório) é dono de arquitetura, banco, regras, importação, API e configuração. É a fonte de verdade.
- *Claude Conversas* (projeto no claude.ai) é só a camada de interação: conversa com a equipe e consulta os dados **exclusivamente** pelas ferramentas do servidor MCP, que por sua vez usam a mesma camada de consultas do painel. O Claude não recebe cópias das planilhas.

---

## 2. Banco de dados

**PostgreSQL 16**, organizado em quatro *schemas*, cada um com um papel claro:

| Schema | Papel | Exemplos |
|---|---|---|
| `core` | Dados de negócio normalizados (fonte de verdade) | `aluno`, `interesse`, `instituicao`, `curso`, `cidade` |
| `ana` | Camada analítica: visões materializadas desnormalizadas e *snapshots* de métricas | `mv_aluno`, `mv_interesse`, `snapshot_metrica` |
| `imp` | Controle de importações | `importacao`, `importacao_ocorrencia`, `estado` |
| `seg` | Segurança e trilhas | `usuario`, `chave_api`, `consulta_log`, `auditoria` |

A área de carga (*staging*) usa tabelas temporárias que existem só durante a transação da importação: dados pessoais nunca ficam parados em uma área intermediária.

Extensões: `pg_trgm` (busca por semelhança e autocompletar rápido) e `unaccent` (busca sem acento).

**Por que não "uma tabela gigante"?** A planilha de leads repete os dados do aluno em até 3 linhas e mistura aluno, escola, cursos, modalidades e instituição. No banco cada coisa vive em uma tabela (forma normalizada, sem repetição). Para as consultas do painel, o banco mantém **visões materializadas desnormalizadas** (`ana.mv_interesse` e `ana.mv_aluno`): uma linha por interesse/aluno com todas as chaves de filtro já resolvidas, com índices dedicados. É o melhor dos dois mundos: escrita íntegra, leitura instantânea.

**Índices principais**
- Chaves naturais únicas: `aluno.id` (UUID de origem), `interesse (aluno_id, posicao)`, `instituicao.nome_norm`, `curso.nome_norm`, `cidade (uf, nome_norm)`.
- Visões analíticas: B-tree em cada coluna de filtro (`uf`, `cidade_id`, `regiao_ensino_id`, `escola_id`, `instituicao_id`, `grupo_id`, `ano_cadastro`, `posicao`, `genero`) e **GIN** nos vetores `cursos int[]` e `modalidades smallint[]` (filtro "tem Medicina no pódio" vira uma busca de índice).
- Trigram (GIN `gin_trgm_ops`) em nomes de instituição, curso, cidade e escola, para a busca rápida e o autocompletar.

Com o volume atual (~180 mil linhas) as consultas respondem em milissegundos. O desenho comporta dezenas de milhões de linhas sem mudança de modelo (ver seção 9).

---

## 3. Entidades

Campos identificados automaticamente nas duas planilhas recebidas:

### Base 2 — Interessados (`Dashboard dados sobre Leads`, aba `Página1`)

| Coluna na planilha | Vai para | Observação |
|---|---|---|
| `ID` | `aluno.id` | UUID do aluno. Repete-se em até 3 linhas (uma por opção). **Não é duplicidade.** |
| `Criado em...` | `aluno.cadastrado_em` | Data de cadastro (jun/2023 → hoje). Gera `ano_cadastro`. |
| `Escola` | `escola` | Escola do aluno |
| `Estado` | `aluno.uf` | Estado **da escola do aluno** (SP, RJ, MT, TO) |
| `Região` | `regiao_ensino` | Diretoria/região de ensino (ex.: "METROPOLITANA IV"), **não** é região geográfica |
| `Cidade` | `cidade` | Cidade da escola |
| `Bairro da escola` | `escola.bairro` | |
| `Data de nascimento` | `aluno.data_nascimento` | Dado pessoal de menor de idade: visível só com permissão. Gera `faixa_etaria`. |
| `Gênero` | `aluno.genero` | |
| `Faz no Momento` | `aluno.situacao_atual` | "Apenas estudo" / "Estudo e trabalho" |
| `Plano pós médio` | `aluno.plano_pos_medio` | |
| `Receber comunicados` | `aluno.aceita_comunicados` | Consentimento: relevante para ações comerciais |
| `PodioCursos1..3` | `aluno_curso` (posição 1–3) | Os 3 cursos preferidos **do aluno** |
| `Posição da opção de faculdade` | `interesse.posicao` | 1ª, 2ª ou 3ª opção |
| `Instituição Privada` | `interesse.instituicao_id` | Instituição desejada naquela posição |
| `Modalidade` | `aluno_modalidade` | Texto com várias modalidades ("Presencial, Online"). Separado e normalizado em Presencial / Híbrido / Online (EAD). |
| `Concluiu Relatório de Perfil Profissional` | `aluno.concluiu_relatorio` | |

### Base 1 — Instituições (`Base volume de leads – setor público`)

| Aba | Vai para | Conteúdo |
|---|---|---|
| `BaseUniversidades` | `instituicao`, `grupo_educacional`, `volume_instituicao_anual` | Nome, Porte, Grupo, Afiliado, Comissão, Tipo de comissão, Comercial + total de leads por UF/ano (2023–2026) |
| `BaseCursos` | `volume_curso_anual` | Total de leads por curso, UF e ano |
| `Base` | `volume_cidade_anual` | Leads da 3ª série e do 9º ano por cidade/ano (dimensão de mercado público) |
| `BaseEscolas` | `volume_escola_anual` | Total de leads por escola/ano |
| `Resumo`, `Consolidado*`, `BaseEtária`, `MoveEdu`, `Planilha1/2` | ignoradas (relatadas) | São tabelas dinâmicas e resumos derivados das bases acima. O painel recalcula tudo isso. |

Campos citados no briefing que **não existem** nas planilhas atuais: código da instituição, cidade/estado da instituição, tipo, categoria, modalidade da instituição, turno e nome do aluno. O modelo já reserva espaço para eles (colunas opcionais e `atributos jsonb`); quando aparecerem em uma exportação, basta mapear a coluna (seção 5.2).

### Entidades do modelo

| Entidade | Descrição | Chave |
|---|---|---|
| `core.uf` | 27 UFs com região geográfica (Sudeste, Sul…) | sigla |
| `core.regiao_ensino` | Região/diretoria de ensino informada na base | (uf, nome) |
| `core.cidade` | Cidade | (uf, nome normalizado) |
| `core.escola` | Escola de origem do aluno | (uf, cidade, nome normalizado) |
| `core.grupo_educacional` | Cogna, YDUQS, Ânima… | nome normalizado |
| `core.instituicao` | IES + atributos comerciais (porte, afiliado, comissão, status comercial) | id interno; `nome_norm` único |
| `core.instituicao_alias` | Grafias que apontam para a mesma instituição | nome normalizado |
| `core.curso` | Curso + grau (Bacharelado, Licenciatura, Tecnológico, Técnico) | nome normalizado |
| `core.modalidade` | Presencial, Híbrido, Online (EAD) | id |
| `core.aluno` | Aluno interessado (sem nome; identificado pelo UUID de origem) | UUID |
| `core.aluno_curso` | Pódio de cursos do aluno | (aluno, posição) |
| `core.aluno_modalidade` | Modalidades aceitas pelo aluno | (aluno, modalidade) |
| `core.interesse` | **Fato principal:** aluno × posição × instituição | (aluno, posição) |
| `core.volume_*_anual` | Totais históricos da Base 1 (2023–2026) | (entidade, uf, ano) |
| `imp.importacao` / `imp.importacao_ocorrencia` | Log de cada importação e cada erro/aviso | id |
| `ana.snapshot_metrica` | Fotografia das métricas a cada importação (base da análise temporal) | (importação, dimensão, chave) |
| `seg.usuario`, `seg.chave_api`, `seg.consulta_log`, `seg.auditoria` | Acesso, integrações e trilhas | id |

---

## 4. Relacionamentos

```
uf 1──N cidade 1──N escola N──1 regiao_ensino
                      │
                      1
                      │
                      N
                    aluno ──N aluno_curso N──1 curso
                      │   ──N aluno_modalidade N──1 modalidade
                      1
                      │
                      N  (até 3: posições 1, 2, 3)
                  interesse N──1 instituicao N──1 grupo_educacional
                                     │
                                     1──N instituicao_alias
                                     1──N volume_instituicao_anual
```

### Como as duas bases se ligam (e por que é seguro)

As planilhas **não têm ID de instituição**. A ligação é feita pelo **nome normalizado** (maiúsculas, sem acento, espaços colapsados):

- `"Centro Universitário  Anhanguera de São Paulo"` → `CENTRO UNIVERSITARIO ANHANGUERA DE SAO PAULO`.
- Na carga atual, **99,99% das linhas de interesse** encontram a instituição correspondente na Base 1 por esse critério.

Regras para nunca assumir um relacionamento errado:
1. **Só igualdade exata do nome normalizado liga automaticamente.** Nada de "parecido o suficiente".
2. Nome desconhecido vira uma instituição nova com `origem = 'leads'` e `verificada = false`. Os números continuam corretos; a instituição só fica marcada para revisão.
3. Semelhanças (ex.: `PUCCAMP` × `PUC-CAMPINAS - PONTIFÍCIA UNIVERSIDADE CATÓLICA DE CAMPINAS`) aparecem como **sugestões** na tela de revisão (busca por trigramas). A unificação só acontece quando um administrador confirma; aí o nome vira um `instituicao_alias` e passa a valer em todas as importações futuras. Toda unificação vai para a auditoria.
4. Textos livres que não parecem instituição (`"3"`, `"privado"`, `"esc"`, datas) recebem `qualidade = 'suspeita'` e podem ser excluídos dos rankings com um clique.

### Aluno × interesse × curso: atenção ao significado

- **Cada linha da planilha com instituição é um interesse**, identificado por (aluno, posição). Um aluno com 3 opções gera 3 interesses. Nada é deduplicado.
- Se o aluno escolheu a mesma instituição em duas posições, são 2 interesses e **1 aluno**. Por isso o painel sempre mostra as duas medidas: *interesses* e *alunos únicos*.
- Os cursos (pódio) e a modalidade são **do aluno**, não da instituição. A planilha não diz "Medicina **na** Universidade X". Ao combinar curso + instituição, o painel responde "alunos que têm Medicina no pódio **e** escolheram a Universidade X", e mostra esse aviso na tela e nas respostas do Claude.
- Estado, cidade e região são **da escola do aluno** (de onde vem a demanda), não da instituição.

---

## 5. Fluxo de importação

### 5.1 Etapas

```
upload ─► 1 Recebe ─► 2 Identifica ─► 3 Mapeia ─► 4 Valida ─► 5 Staging ─► 6 Compara ─► 7 Grava ─► 8 Recalcula ─► 9 Relatório
```

1. **Recebe** o arquivo (`.xlsx` ou `.csv`), calcula o SHA-256. Se o mesmo arquivo já foi importado com sucesso, avisa e não reprocessa.
2. **Identifica** o tipo de base pelos cabeçalhos, não pelo nome do arquivo ou da aba: tem `ID` + `Instituição Privada` → base de interessados; tem `Universidade` + `Total` → base de instituições.
3. **Mapeia colunas** por uma tabela de sinônimos que ignora acento, maiúsculas e pontuação (`Criado em...`, `Criado em`, `criado_em` são a mesma coluna). Colunas novas e desconhecidas geram aviso, sem quebrar a importação.
4. **Valida**
   - colunas obrigatórias presentes (se faltar, a importação é **rejeitada** antes de tocar no banco, com a lista do que faltou e do que foi encontrado);
   - tipos: UUID válido, posição 1–3, datas (inclui o caso real de datas de nascimento corrompidas no Excel), booleanos "Sim/Não/1/0", UF conhecida;
   - consistência: a mesma chave (aluno, posição) aparecendo duas vezes com dados diferentes;
   - qualidade: nome de instituição suspeito, modalidade desconhecida, cidade vazia.

   Linha com erro de chave é **ignorada** e registrada. Problema em campo secundário vira **aviso**: o campo fica vazio e a linha entra.
5. **Staging:** os dados limpos são carregados via `COPY` em tabelas temporárias da transação (rápido, não afeta quem está consultando, e nada fica salvo fora das tabelas finais).
6. **Compara** com a base atual usando um *hash* do conteúdo de cada aluno e de cada interesse:
   - chave nova → **novo**;
   - chave existente com hash diferente → **atualizado**;
   - hash igual → **inalterado** (nada é reescrito);
   - chave ativa que não veio no arquivo → **removido** (só no modo *completo*; ver 8).
7. **Grava tudo em uma única transação.** Ou a importação inteira entra, ou nada muda. Uma trava (*advisory lock*) impede duas importações simultâneas.
8. **Recalcula** as visões analíticas (`REFRESH MATERIALIZED VIEW CONCURRENTLY`, sem bloquear quem está consultando), grava o *snapshot* de métricas desta importação e avança a **versão da base**, o que invalida o cache automaticamente.
9. **Relatório** gravado em `imp.importacao` e mostrado na tela:

```
Importação #2 · leads · modo completo · concluída em 48 s          (primeira carga real)
Linhas lidas ......... 178.579 · ignoradas 0 · erros 0 · avisos 137
Alunos ............... novos 72.340
Interesses ........... novos 160.824
Cadastros novos ...... instituições 8 · cursos 12 · cidades 3 · escolas 959
Avisos ............... data_invalida 106 · instituicao_suspeita 24 · aluno_divergente 3 · linha_repetida 3 · instituicao_ausente 1

Reimportação do mesmo conteúdo:  alunos inalterados 72.340 · interesses inalterados 160.824
```

Cada erro/aviso fica em `imp.importacao_ocorrencia` (linha, coluna, valor, código, mensagem), com download em CSV.

### 5.2 Configuração das colunas

O mapeamento fica em `src/painel/importacao/esquemas.py`: nome canônico, sinônimos aceitos, tipo e obrigatoriedade. Para aceitar uma coluna nova (ex.: "Turno"), basta acrescentar uma entrada. Nenhuma regra de negócio depende da posição das colunas.

---

## 6. Estrutura do painel

Princípio: **responder uma pergunta comercial em menos de 30 segundos**, sem conhecimento técnico. Poucos gráficos, todos legíveis; números grandes; filtros sempre visíveis.

```
┌──────────────┬─────────────────────────────────────────────────────────┐
│ FILTROS      │  [ Busca rápida: "medicina curitiba", "unip"… ]          │
│              ├─────────────────────────────────────────────────────────┤
│ Instituição  │  RESUMO  Alunos │ Interesses │ Instituições │ Cursos │    │
│ Curso        │          Estados │ Cidades            (com os filtros)    │
│ Estado       ├─────────────────────────────────────────────────────────┤
│ Cidade       │  RANKINGS [Instituições][Cursos][Cidades][Estados]       │
│ Região       │           [Regiões][Escolas][Grupos]                     │
│ Modalidade   │  barras horizontais · top 10/25/50 · clique = filtrar    │
│ Grupo        ├──────────────┬──────────────┬─────────────┬─────────────┤
│ Escola       │ MODALIDADE   │ POSIÇÃO      │ ANO CADASTRO│ FAIXA ETÁRIA│
│ Posição      ├──────────────┴──────────────┴─────────────┴─────────────┤
│ Ano cadastro │  RESULTADO DETALHADO  um aluno por linha · 3 opções ·    │
│ Gênero …     │  paginação · ordenação · exportar CSV / Excel            │
│ [limpar]     │                                                          │
└──────────────┴─────────────────────────────────────────────────────────┘
```

- **Filtros cumulativos** (E entre filtros; OU dentro do mesmo filtro). Cada filtro tem autocompletar com contagem.
- **Clique em qualquer barra** de ranking adiciona aquele valor como filtro (exploração sem digitar).
- **Busca rápida** encontra instituições, cursos, cidades e escolas ao mesmo tempo; um clique vira filtro.
- **Aviso de interpretação** aparece quando curso e instituição são combinados (seção 4).
- **URL compartilhável:** os filtros ficam na URL; mandar o link para um colega abre exatamente a mesma consulta.
- **Distribuição geográfica:** estado → região de ensino → cidade pelas abas do ranking (clicar em um estado filtra, e as abas seguintes mostram só ele). O mapa entra quando a tabela de municípios do IBGE for carregada (roadmap).
- **Telas de apoio:** Importações (upload, histórico, relatório, ocorrências), Revisão de instituições (suspeitas, não verificadas, sugestões de unificação) e Usuários.

Exemplos do briefing e como ficam no painel:

| Pergunta | Como responder |
|---|---|
| Quantos interessados na Universidade XPTO? | Filtro Instituição = XPTO → cartão "Alunos únicos" |
| Medicina em Curitiba? | Filtros Curso = Medicina, Cidade = Curitiba → "Alunos únicos" |
| Administração + SP + Campinas + EAD + Univ. X | 5 filtros → resumo instantâneo |
| Cursos mais procurados / ranking de universidades | Aba de ranking correspondente |
| Distribuição por estado / cidade / modalidade | Abas Estados, Regiões e Cidades do ranking; painel de modalidade |

---

## 7. Como o Claude (Conversas) consome os dados

O "Cloud Conversas" é um **Projeto no claude.ai** da organização FutureMe, ligado a um **conector MCP** que aponta para o endpoint `/mcp` deste serviço.

```
Pessoa da equipe ──► Projeto "Inteligência Comercial" no claude.ai
                          │  instruções do projeto (conversas/INSTRUCOES_PROJETO.md)
                          ▼
                    Conector MCP "Painel Comercial"  ──HTTPS──►  /mcp  (este serviço)
                                                                     │
                                                    mesma camada consultas/ do painel
                                                                     ▼
                                                                PostgreSQL
```

Ferramentas expostas ao Claude (só leitura):

| Ferramenta | Para quê |
|---|---|
| `resumo` | Totais (interesses, alunos únicos, instituições, cursos, estados) para qualquer combinação de filtros |
| `ranking` | Top N por instituição, curso, cidade, estado, região, escola, grupo, modalidade, posição, gênero, ano |
| `buscar` | Resolve nomes digitados ("unip", "medicina", "campinas") para os valores exatos da base, com contagem |
| `detalhar` | Amostra paginada de alunos do recorte (sem dados pessoais) |
| `historico_anual` | Totais por ano da Base 1 (2023–2026) para instituição ou curso |
| `comparar_importacoes` | Quem mais ganhou ou perdeu interessados desde a importação anterior (snapshots) |
| `status_base` | Data da última importação e versão dos dados |

Regras:
- Os filtros das ferramentas aceitam **nomes**; o servidor resolve para IDs. Se o nome for ambíguo, a ferramenta devolve as opções e o Claude pergunta à pessoa. Isso evita respostas com o filtro errado.
- Toda resposta carrega a **data da última importação**, para o Claude informar de quando é o dado.
- O Claude **não** tem ferramenta de escrita, de importação nem de dados pessoais (nascimento, gênero individual). Dados de menores ficam fora da camada de conversa.
- Cada chamada é registrada em `seg.consulta_log` com `origem = 'mcp'` (histórico de consultas).
- Acesso por **chave de API** (escopo `consulta`), gerada por um administrador no painel. Passo a passo em [`conversas/CONFIGURACAO.md`](../conversas/CONFIGURACAO.md).

---

### Modo Cowork (sem servidor)

Enquanto o serviço não é publicado, o Claude Cowork usa a skill `cowork/inteligencia-comercial`: o mesmo modelo
de dados em um arquivo SQLite na pasta de trabalho da pessoa, montado a partir das planilhas, com a mesma
importação (hash, exclusão lógica, trava de 20%, arquivo repetido), as mesmas regras de normalização
(copiadas de `src/painel/` por `cowork/montar.py`, com teste que impede divergência) e as mesmas definições de
alunos e interesses. Com as planilhas reais, as respostas são idênticas às do PostgreSQL.
O que fica de fora: login e perfis, histórico de consultas, acesso compartilhado em tempo real.

## 8. Atualização da base

| Modo | Quando usar | Exclusões |
|---|---|---|
| **Completo** (padrão) | A exportação traz a base inteira (caso atual) | Alunos/interesses ausentes do arquivo são **desativados** (`ativo = false`, `removido_em`), nunca apagados fisicamente. Voltam a ficar ativos se reaparecerem. |
| **Incremental** | A exportação traz só um período ou um recorte | Nada é removido; só entra o que é novo ou mudou |

Proteções:
- **Trava de segurança contra exportação incompleta:** no modo completo, se o arquivo fosse desativar mais de 20% dos registros ativos, a importação é rejeitada com explicação. Um administrador pode confirmar com "forçar".
- **Arquivo repetido** (mesmo SHA-256) não é reprocessado.
- **Ordem das bases é livre:** se os leads chegarem antes da base de instituições, as instituições são criadas e enriquecidas depois, quando a Base 1 for importada.
- **Base 1** (instituições) atualiza atributos comerciais e substitui os volumes anuais; instituições nunca são excluídas, pois há interesses apontando para elas.

Depois de cada importação, **todas as métricas se recalculam sozinhas**: visões materializadas são atualizadas, um snapshot é gravado e o cache é invalidado. Ninguém alimenta o painel à mão.

Formas de importar: tela **Importações** no painel (gestor/admin), `POST /api/importacoes` (automação futura) ou linha de comando `painel importar arquivo.xlsx`.

---

## 9. Decisões arquiteturais

| # | Decisão | Por quê | Alternativa descartada |
|---|---|---|---|
| 1 | **PostgreSQL** como fonte única | Relacional maduro, transações, índices GIN/trigram, visões materializadas, controle de acesso; atende o CRM e o histórico futuros. Disponível como serviço gerenciado em qualquer nuvem. | Planilhas/Google Sheets (é o problema atual); banco analítico embarcado (fraco para múltiplos usuários e escrita) |
| 2 | **Modelo normalizado + visões desnormalizadas** | Escrita íntegra e sem repetição; leitura em uma tabela larga e indexada | Tabela única gigante (inconsistência, atualização difícil) |
| 3 | **Chave natural (aluno, posição)** para interesse | É exatamente o que a linha da planilha representa; permite detectar alteração da opção de um aluno sem confundir com interesse novo | Deduplicar por aluno (perderia interesses) |
| 4 | **Instituição ligada por nome normalizado exato + aliases revisados por humano** | Não há ID nas planilhas; igualdade exata não erra, e a revisão manual resolve o restante sem risco | Fuzzy matching automático (une instituições diferentes em silêncio) |
| 5 | **Diff por hash + transação única + exclusão lógica** | Importação idempotente, auditável, reversível; quem consulta nunca vê meia carga | Apagar tudo e recarregar (perde histórico; derruba o painel durante a carga) |
| 6 | **Snapshots de métricas por importação** | Análise temporal, ranking histórico e comparação entre importações ficam baratos (milhares de linhas, não milhões) | Versionar a tabela inteira a cada carga (custo alto, sem necessidade hoje) |
| 7 | **Uma camada de consultas** usada por painel, API, exportação e MCP | Um único número para cada pergunta | Lógica duplicada no front ou no Claude |
| 8 | **Filtros sobre lista fechada de dimensões, SQL parametrizado** | Segurança (sem SQL livre) e desempenho previsível | Deixar o Claude escrever SQL (risco de erro e de vazamento) |
| 9 | **Cache por versão da base** | Respostas repetidas são instantâneas e nunca ficam desatualizadas, porque a chave do cache inclui a versão da última importação | Cache com expiração por tempo (mostraria dado velho) |
| 10 | **Python (FastAPI + pandas + psycopg)** | Ecossistema de dados forte para ler Excel e validar; API rápida e tipada; mesmo código serve a linha de comando, a API e o MCP | Duas linguagens (uma para dados, outra para API) |
| 11 | **Front-end sem etapa de build** (HTML + JS) servido pela própria API | Implantação simples (um container), manutenção fácil; suficiente para um painel interno | SPA com framework e pipeline de build (custo de manutenção sem ganho agora) |
| 12 | **MCP para o Claude** | Padrão aberto suportado pelo claude.ai; o Claude consulta dados vivos sem cópia de planilha | Subir planilhas no projeto do Claude (dados velhos, sem controle de acesso, risco LGPD) |
| 13 | **Papéis + permissões finas + chaves de API com escopo** | Equipe interna com níveis diferentes; integrações sem senha de pessoa | Login único compartilhado |
| 14 | **Dados pessoais de menores restritos** | LGPD (art. 14). Agregados são liberados; nascimento e gênero individuais só com permissão `dados_pessoais`; o Claude não acessa | Expor linha a linha para todos |

**Escala:** com 10× o volume atual, nada muda. Acima de dezenas de milhões de interesses, os próximos passos já previstos são: particionar `interesse` por ano de cadastro, criar agregados pré-calculados por (instituição, UF, curso) e trocar o cache em memória por Redis quando houver mais de uma instância da API.

---

## 10. O que os dados permitem (e não permitem) responder

| Pergunta | Hoje | Observação |
|---|---|---|
| Interessados por instituição, curso, cidade, estado, região, escola, modalidade, posição, gênero, ano | ✅ | |
| Combinação livre desses filtros | ✅ | |
| "Medicina **na** Universidade X" | ⚠️ aproximado | A base liga curso ao aluno, não à instituição (seção 4) |
| Por turno | ❌ | Não existe na exportação. O modelo aceita quando a coluna vier. |
| Cidade/estado **da instituição** | ❌ | A Base 1 não traz localização da IES; a UF dela é a do aluno |
| Nome do aluno | ❌ | A exportação não traz nome (bom para LGPD). Reservado para quando houver base legal e permissão. |
| Evolução 2023–2026 por instituição/curso | ✅ | Via volumes anuais da Base 1 |
| Evolução entre importações | ✅ | A partir da segunda importação (snapshots) |

---

### Diagnóstico da primeira carga (23/10/2026)

O que a importação das planilhas reais encontrou, e como foi tratado:

| Achado | Tratamento |
|---|---|
| 72.340 alunos em 178.579 linhas; 17.752 alunos sem nenhuma instituição escolhida | Alunos entram (contam nos cursos e na geografia); sem interesse |
| 106 alunos com data de nascimento corrompida na exportação (números como 6.613.532) | Campo fica vazio, aviso no relatório; faixa etária "Não informado" |
| 1 ID de aluno em duas escolas (SP e TO) com as mesmas 3 opções | Vale a primeira linha; aviso `aluno_divergente` |
| 24 nomes de instituição digitados livremente ("não sei", "3", "privado") | Marcados como suspeitos, fora dos números por padrão, listados na revisão |
| Na aba `BaseCursos`, 10.401 linhas são cópia exata de outras (bloco colado duas vezes) | Contadas uma vez; antes, qualquer soma nessa aba dobrava os totais |
| Grafias diferentes do mesmo nome na Base 1 ("Unip"/"UNIP", 2.300 casos) | Totais somados na mesma instituição/curso |
| Atributos comerciais divergentes entre anos (145 casos, ex.: porte "Grupos Educacionais" × "Grandes Grupos") | Vale o valor do ano mais recente; aviso no relatório |
| Coluna "Comercial" mistura status ("Já cliente") com números soltos (1, 12, 86…) | Mantida como texto; vale revisar na origem |
| Cursos digitados livremente (1.844 cursos distintos no pódio, ex.: "medicina" e "Medicina - Bacharelado") | Ao filtrar "Medicina", o Claude inclui as grafias equivalentes e informa quais; unificação de cursos fica no roadmap |

## 11. Roadmap de evolução

O modelo e os módulos já deixam ganchos para:

| Funcionalidade | Gancho existente |
|---|---|
| CRM comercial | `instituicao` já tem status comercial, comissão e afiliado; um schema `crm` pode referenciar `instituicao.id` (contatos, oportunidades, atividades) |
| Histórico de importações / comparação | `imp.importacao` + `ana.snapshot_metrica` |
| Histórico de consultas | `seg.consulta_log` |
| Exportação Excel/PDF | Excel e CSV já existem; PDF entra em `consultas/exportacao.py` |
| Relatórios automáticos e alertas | Agendador chamando a camada de consultas e comparando snapshots (ex.: "instituição X cresceu 30% desde a última carga") |
| Dashboards personalizados | Tabela `seg.consulta_salva` (filtros nomeados por usuário), já suportada pelo formato de filtros em URL |
| Integração com CRM (HubSpot) / BI | API REST com chave de API; BI pode ler direto as visões `ana.*` com um usuário só-leitura |
| Mapa geográfico | Coluna `cidade.codigo_ibge` reservada; basta carregar a tabela de municípios do IBGE |
| SSO Google Workspace | `seg.usuario` já é por e-mail `@futureme.tech`; trocar o login por OIDC sem mudar permissões |
| Unificação de cursos | Mesmo mecanismo de aliases das instituições, aplicado a `core.curso` |
| OAuth no conector do Claude | Substitui a chave na URL quando houver SSO |
| Importação em segundo plano | Hoje a tela espera ~1 min; com bases maiores, mover para fila com acompanhamento de progresso |
