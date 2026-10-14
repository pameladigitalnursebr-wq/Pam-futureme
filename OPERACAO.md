# Playbook de Prospecção — Universidades (FutureMe)

Dona da operação: Pamela Freitas · Atendimento dos leads: Fernanda · Atualizado em 14/10/2026

> Repositório público: aqui entram só regras, textos e IDs de configuração.
> Listas, telefones, nomes de leads e a base de universidades **nunca** sobem para cá (ver `.gitignore`).

---

## 1. Como a operação funciona

| Item | Decisão |
|---|---|
| Canal | WhatsApp via Nuvia, usada **só para o disparo** |
| Número | **FutureMe - Jornada do Futuro** (`6ac6a6a095d8d8d9bbbb95ee`), não o B2B nem o B2C |
| Mensagens | Abertura (template A) às **10h30** + **um follow-up** no dia útil seguinte às **15h** |
| Quem atende | **Fernanda**, humana. Sem agente de IA (a Bia não entra nesta operação) |
| Template | **A** (volume de leads) nos dois lotes. O B fica de reserva |
| Lote 1 | **Marketing/comunicação + diretoria/reitoria** — abertura qui 15/10 10h30, follow-up sex 16/10 15h |
| Lote 2 | **Comercial/captação** — abertura sex 16/10 10h30, follow-up seg 19/10 15h |
| Sem resposta | 24h após o follow-up sem resposta → card no HubSpot **Comercial - Universidades / Leads Nuvia** |

## 2. Quem abordar

Ordem de prioridade dentro de cada universidade:
1. Captação de alunos → marketing → comercial / C-level (CMO, diretor de marketing, head de vendas, gerente de captação).
2. Reitoria ou diretoria geral: primeiro contato nas instituições menores (menos de 500 leads em 2026 ou sem área de marketing/captação mapeada); nas demais, só quando não houver decisor de captação, marketing ou comercial.

Qualquer contato da instituição serve como ponte: se não for a pessoa, perguntamos quem responde pela captação.
Até **dois contatos por universidade** ao mesmo tempo.

## 3. Formação dos lotes

1. Canal: quem tem WhatsApp vai para os lotes 1 e 2; só LinkedIn, só e-mail ou sem contato vai para o lote 3.
2. Volume de leads 2026: lote 1 = universidades com mais leads; lote 2 = demais.
3. Cargo: ordem da seção 2.

Critérios de corte para o WhatsApp (o contato vai para e-mail ou ligação):
- Menos de 50 leads 2026 (a mensagem ficaria "Temos 1 alunos…").
- Cargo fora do perfil (secretaria, financeiro, analista) quando a instituição já tem outro contato no lote.
- Nome de instituição masculino ("estudar **na** Insper/Senac" fica errado; o template não pode ser editado).
- Contato que já tem conversa na Nuvia.

Antes de cada lote:
- Nome do contato limpo na Nuvia (sem acento corrompido, sem "Sr.", "Prof."), porque a saudação usa o primeiro nome.
- Campos Instituição e Leads 2026 preenchidos; campo vazio = contato fora.
- Lista montada **antes** de criar a campanha; conferir inscritos antes de ativar.

## 4. Template

Textos e variáveis: [`templates/universidades_whatsapp.md`](templates/universidades_whatsapp.md).

| Template | Número | Uso |
|---|---|---|
| `universidades_abertura_a_fernanda` | Jornada do Futuro | **Em uso** a partir do lote 1 |
| `universidades_abertura_a_leads` / `_b_receita` | B2B | Enviados por engano de número em 13/10; **não usar** |

## 5. Campanha na Nuvia

| Item | Configuração |
|---|---|
| Tipo | WhatsApp (WAP_AUTO_CLOSER), gatilho MANUAL, audiência = lista |
| Lista | `DD/MM Universidades - Lote N - template A` |
| Agendamento | SCHEDULED, 10h30 BRT |
| Etapa 1 | `universidades_abertura_a_fernanda` |
| Etapa 2 | `universidades_followup_fernanda`, no dia útil seguinte às 15h |
| Funil | Universidades / Triagem (a etapa "Desqualificado / Sem engajamento" está mapeada para HubSpot Leads Nuvia) |
| Dono e atendimento | Fernanda (HUMAN_USER) |
| Agente de IA | Nenhum |
| Estado | Sempre criada em **RASCUNHO**; só ativa com OK explícito da Pamela |

## 6. Roteiro de ligação e objeções

1. Abertura: "Olá, {{primeiro_nome}}, aqui é a Fernanda, da FutureMe. Somos uma solução de orientação profissional para escolas públicas que conecta os alunos com o ensino superior. Te liguei porque temos {{leads_2026}} alunos que estão se formando e querem estudar na {{instituicao}}."
2. Qualificação: "Quem aí responde pela captação de novos alunos?" Se não for a pessoa, pedir nome e contato do responsável.
3. Pedido: "Gostaria de entender como esses alunos podem se tornar matrícula neste ciclo. Podemos conversar por 30 minutos?"
4. Fechamento: confirmar data, horário e e-mail para o convite.

Objeções:
- **"Já temos fornecedor de leads."** São alunos que estão se formando e demonstraram interesse na sua instituição, não leads genéricos de mídia. Vale comparar a qualidade.
- **"Estamos sem verba."** A conversa é para mostrar o recorte e as possibilidades de parceria. Temos formatos de pagamento por sucesso.
- **"Me manda por e-mail."** Enviar resumo de três linhas e propor dois horários na mesma mensagem.

## 7. Regras de aprovação

| Ação | Regra |
|---|---|
| Enviar template à Meta | Só com OK explícito (irreversível) |
| Ativar campanha | Só com OK; antes conferir rascunho, inscritos, etapa e dona |
| Enriquecer contatos (créditos) | Só com OK, informando o custo |
| Pediu para sair | Nunca reabordar |
| Repositório GitHub (público) | Nunca subir lista, telefone ou nome de lead |

## 8. Regras dos lotes (decisão de 14/10)

- Lote 1: cargos de marketing/comunicação e diretoria/reitoria; lote 2: comercial/captação.
- Fora: universidades já em negociação no funil Comercial - Universidades (cliente, em contato, reunião, proposta, perdido).
- Até 2 contatos por universidade por lote (prioridade: marketing > diretoria); excedentes ficam de reserva.
- Cortes de WhatsApp da seção 3 continuam valendo.

## 9. Status

| Lote | Contatos | Situação |
|---|---|---|
| 1 | 26 contatos, 20 IES | Campanha agendada (rascunho) para 15/10 10h30; aguarda OK de ativação |
| 2 | 4 contatos, 3 IES | Campanha agendada (rascunho) para 16/10 10h30; aguarda OK de ativação |

Pendências:
- [x] Template A aprovado pela Meta
- [ ] Template de follow-up aprovado pela Meta (enviado em 14/10)
- [ ] Etapa de follow-up nas duas campanhas
- [ ] OK da Pamela para ativar
