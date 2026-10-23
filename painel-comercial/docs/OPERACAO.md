# Operação do painel

Como instalar, publicar, atualizar a base e administrar o acesso.

## 1. Rodar localmente

Requisitos: Python 3.11+ e PostgreSQL 16 (ou Docker).

```bash
cp .env.example .env              # ajuste PAINEL_SECRET_KEY e a URL do banco; PAINEL_COOKIE_SEGURO=false em http local
docker compose up -d banco        # ou use um PostgreSQL já existente
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
painel migrar
painel criar-usuario seu.nome@futureme.tech "Seu Nome" --papel admin
painel importar caminho/Base_volume_de_leads.xlsx           # base de instituições
painel importar caminho/Dashboard_dados_sobre_Leads.xlsx    # base de interessados
painel servir                                               # http://localhost:8000
```

Ou tudo em container: `docker compose up --build` e depois `docker compose exec app painel criar-usuario ...`.

## 2. Publicar (produção)

O serviço é **um container** + **um PostgreSQL**. Qualquer nuvem serve; a escolha é da FutureMe.

| Peça | Recomendação |
|---|---|
| Banco | PostgreSQL 16 gerenciado (ex.: Supabase, Neon, RDS, Cloud SQL) com backup diário automático. Extensões `pg_trgm` e `unaccent` (todas as nuvens citadas têm). |
| Aplicação | O `Dockerfile` deste diretório em um serviço de containers (ex.: Cloud Run, Render, Fly.io, Railway). 1 instância com 1 GB de RAM atende o volume atual. |
| Domínio | `painel.futureme.tech` com HTTPS (obrigatório: cookie seguro e conector do Claude). |
| Variáveis | As do `.env.example`. `PAINEL_SECRET_KEY` longo e secreto; `PAINEL_HOSTS_MCP=painel.futureme.tech`. |

As migrations rodam sozinhas a cada deploy (`painel migrar` no início do container).

## 3. Atualizar a base (rotina)

1. Exporte a planilha da plataforma como sempre.
2. No painel, aba **Importações** → escolha o arquivo → modo **Completo** → Importar.
3. Leia o relatório: novos, alterados, removidos, ignorados, erros e avisos. Baixe o CSV de ocorrências se houver erros.
4. Pronto: todas as métricas e o Claude já usam a base nova.

Situações comuns:

| Mensagem | O que fazer |
|---|---|
| "Este arquivo já foi importado" | Nada: a base já está com esse arquivo. |
| "faltam as colunas obrigatórias: …" | A exportação mudou de formato. Exporte de novo com as colunas, ou peça para incluir o novo nome de coluna em `importacao/esquemas.py`. |
| "desativaria X de Y … acima do limite de segurança" | A exportação provavelmente veio incompleta (filtro aplicado, corte de período). Exporte a base inteira. Se a queda for real, reimporte marcando **Forçar**, ou use o modo **Incremental** para arquivos parciais. |
| "Outra importação está em andamento" | Aguarde um minuto. |

Duração medida com a base real (178 mil linhas): cerca de 50 s para a primeira carga; reimportações sem mudanças, cerca de 40 s.

## 4. Revisar instituições

Aba **Revisar instituições** (papéis gestor e admin). Lista nomes que vieram só da base de interessados ou parecem texto livre, com sugestões de nomes parecidos.
- **Unificar com …**: junta as grafias. Vale para sempre (também nas próximas importações) e fica na auditoria.
- **É uma instituição válida**: tira da lista.
- **Marcar como suspeita**: sai dos números do painel e do Claude (pode ser reincluída marcando "Incluir respostas livres suspeitas").

## 5. Usuários e acesso

| Papel | Pode |
|---|---|
| leitor | Consultar o painel |
| analista | + exportar CSV/Excel |
| gestor | + importar planilhas e revisar instituições |
| admin | + usuários, chaves de API, dados pessoais (ID completo, nascimento, gênero individual) |

Só e-mails `@futureme.tech` são aceitos. Para tirar o acesso de alguém, salve o usuário com *ativo = não* (via API) ou mude o papel.
Chaves de API: aba **Usuários e acesso**. Use escopo `consulta` para o Claude. Revogar corta o acesso na hora.

## 6. Testes

```bash
createdb painel_teste
PAINEL_TESTE_DATABASE_URL=postgresql://localhost/painel_teste pytest
```

Os testes usam planilhas sintéticas geradas no próprio código. Nenhum dado real é necessário (nem permitido) no repositório.
