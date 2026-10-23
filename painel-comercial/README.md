# Painel de Inteligência Comercial

Substitui as planilhas de mercado por uma **base pesquisável**: quantos alunos querem cada instituição, curso, cidade, estado ou modalidade, em qualquer combinação de filtros, em segundos. A mesma base atende o painel web, a API e o Claude (projeto "Inteligência Comercial" no claude.ai).

| Documento | Conteúdo |
|---|---|
| [`docs/ARQUITETURA.md`](docs/ARQUITETURA.md) | Arquitetura, banco, entidades, relacionamentos, importação, painel, Claude e decisões |
| [`docs/OPERACAO.md`](docs/OPERACAO.md) | Instalar, publicar, importar planilhas, revisar instituições, usuários |
| [`cowork/LEIA-ME.md`](cowork/LEIA-ME.md) | **Modo Cowork**: o Claude monta a base e responde sozinho, sem servidor (skill `inteligencia-comercial.zip`) |
| [`conversas/CONFIGURACAO.md`](conversas/CONFIGURACAO.md) | Ligar o Claude ao painel publicado (conector MCP + projeto) |
| [`conversas/INSTRUCOES_PROJETO.md`](conversas/INSTRUCOES_PROJETO.md) | Instruções para colar no projeto do claude.ai |

## Estrutura

```
migrations/          SQL versionado (core, ana, imp, seg)
src/painel/
  importacao/        leitura .xlsx/.csv, mapeamento de colunas, validação, diff e gravação
  consultas/         filtros, métricas, rankings, busca, detalhe, cache, exportação
  seguranca/         papéis, permissões, usuários, sessões, chaves de API
  api/               FastAPI: /api (REST), / (painel), /mcp (Claude)
  mcp/               ferramentas do Claude
  web/               painel (HTML + JS, sem build)
  revisao.py         revisão e unificação de instituições
  cli.py             comando `painel`
tests/               testes com dados sintéticos
conversas/           configuração do projeto no Claude (modo servidor, via MCP)
cowork/              skill do modo Cowork (SQLite, sem servidor) e montar.py, que gera o .zip
```

## Começo rápido

```bash
pip install -e ".[dev]" && cp .env.example .env
painel migrar
painel criar-usuario voce@futureme.tech "Seu Nome" --papel admin
painel importar Base_instituicoes.xlsx && painel importar Base_leads.xlsx
painel servir
```

**Dados reais nunca entram no git** (o repositório é público). Planilhas ficam fora do repositório e no banco.
