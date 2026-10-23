# Modo Cowork: o Claude consulta a base sozinho, sem servidor

Neste modo o próprio Claude (no Cowork) monta a base a partir das planilhas e responde as perguntas.
Não precisa de servidor, HTTPS nem instalar nada. As regras e os números são os mesmos do sistema
principal: testamos com as planilhas reais e as respostas batem.

## O que você precisa
1. **A skill**: o arquivo [`inteligencia-comercial.zip`](inteligencia-comercial.zip) (botão *Download* no GitHub).
2. **As duas planilhas** de sempre: a base de interessados (leads) e a base de instituições.
3. **O texto para colar**, que está no fim desta página.

## Passo a passo (uma vez só)
1. **Instale a skill.** No app do Claude, vá em *Configurações → Capacidades* (ou *Skills*), escolha
   *Enviar skill* e selecione o `inteligencia-comercial.zip`. Confirme que ela aparece ativada.
   - Se a sua conta não mostrar a opção de enviar skills: anexe o `.zip` na própria conversa do Cowork junto
     com o texto abaixo. O Claude descompacta e segue as instruções do mesmo jeito.
2. **Escolha uma pasta no Cowork** (ex.: `Documentos/Inteligência Comercial`). A base fica salva nela
   (`dados_painel/base_comercial.db`) e continua lá nas próximas conversas.
3. **Primeira carga:** anexe as duas planilhas e cole o texto abaixo. A carga leva cerca de 1 minuto.

## No dia a dia
- **Perguntar:** "Quantos alunos querem a UNIP?", "Top 10 cursos em Campinas", "Medicina no RJ por modalidade",
  "Gere o painel de SP".
- **Atualizar a base:** anexe a planilha nova e diga "atualize a base com esta planilha". O Claude mostra o que
  entrou, mudou e saiu.
- **Painel visual:** peça "gere o painel" (com ou sem filtros). O Claude cria um arquivo HTML na pasta, e você abre
  no navegador.

## Limites deste modo
- Quem tem acesso à conversa ou à pasta vê os dados. Não há login nem perfis como no sistema principal.
- A base fica na pasta do seu computador. Para outra pessoa usar, ela instala a skill e importa as planilhas
  na pasta dela (ou vocês compartilham a pasta).
- Turno, nome do aluno e cidade da instituição não existem nas planilhas, então o Claude não consegue responder
  sobre eles.

---

## Texto para colar no Cowork (primeira conversa)

```
Use a skill "inteligencia-comercial" (Inteligência Comercial FutureMe).
1. Rode o status da base nesta pasta.
2. Importe as planilhas anexadas: primeiro a base de instituições, depois a base de interessados.
3. Me mostre o relatório da importação em poucas linhas e um resumo geral da base:
   total de alunos, interesses, instituições, os 5 cursos mais procurados e as 5 instituições mais desejadas.
A partir daqui, responda minhas perguntas comerciais sempre consultando a base pela skill,
com o número principal em destaque e a data da base no final.
```
