# Templates WhatsApp — Universidades

Status: **rascunho para validação da Pamela. Ainda NÃO enviados à Meta.**
Envio à Meta é irreversível (não dá para editar nem excluir depois), então só sobe com OK explícito.

Configuração comum aos dois:

| Item | Valor |
|---|---|
| Inbox | FutureME - B2B (`6a7dc8cd8ecb055a17f25a9d`) — mesmo número de Escolas |
| Categoria | MARKETING |
| Idioma | pt_BR |
| Formato de parâmetro | named (padrão dos templates atuais da Nuvia) |
| Remetente na mensagem | Pamela (não a Bia) |

## Variáveis (campos de contato na Nuvia)

| No playbook | Campo na Nuvia | Variável no template | Formato na planilha |
|---|---|---|---|
| `{{primeiro_nome}}` | nativo (primeiro nome) | `{{v_c_f_name}}` | Só o primeiro nome, sem "Prof.", "Dr." |
| `{{instituicao}}` | Instituição | `{{v_c_instituicao}}` | Nome curto e legível (ex.: "Unifor", "PUC Minas") |
| `{{leads_2026}}` | Leads 2026 | `{{v_c_leads_2026}}` | Texto já formatado (ex.: `1.240`) |
| `{{receita_24m}}` | Receita Potencial 24m | `{{v_c_receita_pote_2sg}}` | Texto sem "R$" (ex.: `2,4 milhões`) |
| `{{matriculas_estimadas}}` | Matrículas Estimadas | `{{v_c_matriculas_e_l2y}}` | Não usado nos templates; fica para o agente/relatório |

Os campos são texto de propósito: assim o número sai formatado do jeito que está na planilha.
Contato com campo vazio **não pode** entrar na lista (a mensagem sairia com buraco).

## Template A — volume de leads

Nome: `universidades_abertura_a_leads`

```
Olá, {{v_c_f_name}}, tudo bem? Aqui é a Pamela, da FutureMe, solução de orientação profissional para escolas públicas que conecta os alunos com o ensino superior.

Temos {{v_c_leads_2026}} alunos que estão se formando e têm interesse em estudar na {{v_c_instituicao}}.

Gostaria de entender como esses alunos podem se tornar matrícula neste ciclo. Teria 30 minutos nesta semana ou na próxima?
```

Botões (resposta rápida): `Tenho interesse` · `Prefiro na próxima semana` · `Não sou a pessoa certa`

## Template B — potencial de receita

Nome: `universidades_abertura_b_receita`

```
Olá, {{v_c_f_name}}, tudo bem? Aqui é a Pamela, da FutureMe, solução de orientação profissional para escolas públicas que conecta os alunos com o ensino superior.

Temos {{v_c_leads_2026}} alunos que estão se formando e têm interesse em estudar na {{v_c_instituicao}}, com receita potencial estimada de R$ {{v_c_receita_pote_2sg}} em mensalidades nos primeiros 24 meses.

Quer saber como acessar essa base qualificada? Teria 30 minutos nesta semana ou na próxima?
```

Botões (resposta rápida): `Tenho interesse` · `Prefiro na próxima semana` · `Não sou a pessoa certa`

## O que mudou em relação ao playbook (.docx)

- "conecta os alunos **com o** ensino superior" (artigo) e texto igual nos dois braços até o número, para o A/B testar só o argumento.
- Pitch B: "Gostaria de saber como acessar…?" virou "Quer saber como acessar…?".
- Botões de resposta rápida, como nos templates de Escolas: clique em botão conta como resposta e "Não sou a pessoa certa" já abre o redirecionamento para quem cuida da captação.

## Follow-up (dia seguinte)

No dia seguinte a janela de 24h do WhatsApp está fechada para quem não respondeu, então o follow-up também precisa ser template aprovado. Opções:

1. **Reusar `fup1_abordagembia3`** (já aprovado, sem variáveis, genérico):
   "Consegue me dar um retorno sobre a mensagem que te mandei? Se fizer sentido, a gente combina uma conversa rápida com alguém do nosso time"
   Vantagem: zero espera de aprovação. Ficam só os dois templates novos.
2. Criar follow-ups específicos A e B (texto do playbook, sem "quinta ou sexta", que não funciona para os lotes 2 e 3):
   - A: "Oi, {{v_c_f_name}}! Retomando minha mensagem de ontem sobre os {{v_c_leads_2026}} alunos interessados em estudar na {{v_c_instituicao}}. Tenho horários nos próximos dias. Qual período funciona melhor para você?"
   - B: "Oi, {{v_c_f_name}}! Retomando minha mensagem de ontem sobre o potencial de R$ {{v_c_receita_pote_2sg}} em matrículas para a {{v_c_instituicao}}. Tenho horários nos próximos dias. Qual período funciona melhor para você?"

Recomendação: opção 1 para não travar a semana.
