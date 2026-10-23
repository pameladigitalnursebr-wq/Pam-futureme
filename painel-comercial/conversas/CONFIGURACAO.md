# Configurar o Claude ("Cloud Conversas")

O Claude consulta o painel por um **conector MCP**. Ele não recebe cópia das planilhas: cada pergunta vira uma chamada às ferramentas do endpoint `/mcp` deste serviço, que usa a mesma camada de consultas do painel web.

## Pré-requisitos
- O serviço publicado com HTTPS em um endereço acessível pela internet (ex.: `https://painel.futureme.tech`). Ver [`docs/OPERACAO.md`](../docs/OPERACAO.md).
- `PAINEL_HOSTS_MCP` com esse domínio (ex.: `PAINEL_HOSTS_MCP=painel.futureme.tech`).
- Plano do claude.ai com conectores personalizados e projetos (Team ou Enterprise, para compartilhar com a equipe).

## Passo a passo

1. **Criar a chave do conector.** No painel, em *Usuários e acesso → Chaves de API*, crie a chave "Conector Claude" com escopo `consulta`. Copie a chave (aparece uma vez).
   Recomendado: crie antes um usuário técnico `claude@futureme.tech` com papel `leitor` e gere a chave em nome dele. Assim a chave nunca tem mais acesso do que consulta.
   Pela linha de comando: `painel criar-chave claude@futureme.tech "Conector Claude"`.

2. **Adicionar o conector no claude.ai** (um administrador da organização):
   *Configurações → Conectores → Adicionar conector personalizado*
   - Nome: `Painel Comercial`
   - URL: `https://painel.futureme.tech/mcp?chave=<CHAVE>`

   O endpoint também aceita a chave no cabeçalho `Authorization: Bearer <CHAVE>`, para clientes que permitem cabeçalhos.

3. **Criar o projeto** *Inteligência Comercial* no claude.ai:
   - Cole as instruções de [`INSTRUCOES_PROJETO.md`](INSTRUCOES_PROJETO.md).
   - Ative o conector "Painel Comercial" nas conversas do projeto.
   - Compartilhe o projeto com a equipe FutureMe.

4. **Testar** com perguntas como:
   - "Quantos alunos têm interesse na UNIP?"
   - "Quais os 10 cursos mais procurados em Campinas?"
   - "Administração, SP, Campinas, EAD: quantos interessados?"
   - "Como cresceu o Mackenzie de 2024 para 2026?"

## Segurança
- As ferramentas são só de leitura e não devolvem dados pessoais (nascimento, gênero individual, ID completo do aluno).
- Cada chamada fica em `seg.consulta_log` com `origem = 'mcp'` (tela *Usuários e acesso → Últimas consultas*).
- Para cortar o acesso, revogue a chave no painel: o conector para na hora.
- A chave na URL é prática, mas aparece em logs de proxy. Quando houver SSO, troque por OAuth (roadmap em `docs/ARQUITETURA.md`).

## Uso local (Claude Desktop ou Claude Code)
Com acesso direto ao banco, dá para usar o mesmo servidor via stdio, sem expor nada na internet:

```json
{
  "mcpServers": {
    "painel-comercial": {
      "command": "painel",
      "args": ["mcp-stdio", "--email", "seu.nome@futureme.tech"],
      "env": { "PAINEL_DATABASE_URL": "postgresql://...", "PAINEL_SECRET_KEY": "..." }
    }
  }
}
```
