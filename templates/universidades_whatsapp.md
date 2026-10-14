# Templates WhatsApp — Universidades

## Em uso

**`universidades_abertura_a_fernanda`** — template A (volume de leads)

| Item | Valor |
|---|---|
| Número | FutureMe - Jornada do Futuro (`6ac6a6a095d8d8d9bbbb95ee`) |
| Status | **Aprovado** pela Meta (ID `1768246244419174`) |
| Categoria | MARKETING · pt_BR · parâmetros nomeados |
| Remetente na mensagem | Fernanda |

```
Olá, {{v_c_f_name}}, tudo bem? Aqui é a Fernanda, da FutureMe, solução de orientação profissional para escolas públicas que conecta os alunos com o ensino superior.

Temos {{v_c_leads_2026}} alunos que estão se formando e têm interesse em estudar na {{v_c_instituicao}}.

Gostaria de entender como esses alunos podem se tornar matrícula neste ciclo. Teria 30 minutos nesta semana ou na próxima?
```

Botões (resposta rápida): `Tenho interesse` · `Prefiro na próxima semana` · `Não sou a pessoa certa`

## Follow-up

**`universidades_followup_fernanda`** — enviado à Meta em 14/10 (em análise, ID `1646601943524011`)

```
Olá, {{v_c_f_name}}, tudo bem? Você tem interesse em marcar uma conversa?
```

Botões: `Tenho interesse` · `Agora não`. Sai no dia útil seguinte à abertura, às 15h.

## Variáveis (campos de contato na Nuvia)

| No playbook | Campo | Variável no template | Slug (API) | Formato |
|---|---|---|---|---|
| primeiro nome | nativo | `{{v_c_f_name}}` | — | Primeiro nome limpo |
| instituição | Instituição | `{{v_c_instituicao}}` | `instituicao` | Nome que soe bem depois de "na" (ex.: "Universidade Presbiteriana Mackenzie", "ITE Bauru") |
| leads 2026 | Leads 2026 | `{{v_c_leads_2026}}` | `leads-2026` | Texto formatado (ex.: `1.240`) |
| receita 24m | Receita Potencial 24m | `{{v_c_receita_pote_2sg}}` | `receita-potencial-24m` | Sem "R$" (ex.: `2,4 milhões`, `1,5 milhão`, `959 mil`) |
| matrículas | Matrículas Estimadas | `{{v_c_matriculas_e_l2y}}` | `matriculas-estimadas` | Não usado no template |

## Reserva — pitch B (receita)

Não enviado no número Jornada do Futuro. Será avaliado com a Pamela antes do lote 2. Texto validado:

```
Olá, {{v_c_f_name}}, tudo bem? Aqui é a Fernanda, da FutureMe, solução de orientação profissional para escolas públicas que conecta os alunos com o ensino superior.

Temos {{v_c_leads_2026}} alunos que estão se formando e têm interesse em estudar na {{v_c_instituicao}}, com receita potencial estimada de R$ {{v_c_receita_pote_2sg}} em mensalidades nos primeiros 24 meses.

Quer saber como acessar essa base qualificada? Teria 30 minutos nesta semana ou na próxima?
```

Atenção: a receita usa mensalidades estimadas (confiança média/baixa na base). Validar os valores das IES premium antes de usar.

## Não usar

`universidades_abertura_a_leads` e `universidades_abertura_b_receita` foram enviados em 13/10 no número **FutureME - B2B** (assinados "Pamela"). O número da operação é o Jornada do Futuro, então esses não entram nas campanhas.
