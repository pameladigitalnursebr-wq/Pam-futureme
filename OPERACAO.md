# Playbook de Pré-vendas Outbound — Universidades (FutureMe)

Dona da operação: Pamela Freitas · Versão de 13/10/2026

Este playbook junta duas fontes:
- o **modelo base** da operação de Escolas (mecânica, regras de aprovação, higienização, HubSpot);
- o **plano de prospecção de Universidades** da semana de 13 a 16/10 (base, lotes, pitch, cronograma).

Itens marcados **[PENDENTE]** ainda precisam de definição antes do disparo.

> Repositório público: aqui entram só regras, textos e IDs de configuração.
> Listas, telefones, nomes de leads e a base de universidades **nunca** sobem para cá (ver `.gitignore`).

---

## 1. Objetivo da semana

Em quatro dias, as 91 universidades da base recebem primeira mensagem e follow-up, para abrir as primeiras conversas comerciais.

| Lote | Canal | Universidades | Contatos | 1ª mensagem | Follow-up |
|---|---|---|---|---|---|
| 1 | WhatsApp, maior volume de leads | 26 | 42 | Ter 13/10 | Qua 14/10 |
| 2 | WhatsApp, demais | 32 | 41 | Qua 14/10 | Qui 15/10 |
| 3 | LinkedIn / a levantar | 35 | 46 | Qui 15/10 | Sex 16/10 |
| **Total** | | **91** | **129** | | |

Meta de reuniões: **[PENDENTE]**

## 2. Quem abordar (ICP e cargos)

Ordem de prioridade dentro de cada universidade:
1. Captação de alunos → marketing → comercial / C-level (CMO, diretor de marketing, head de vendas, gerente de captação).
2. Reitoria ou diretoria geral: primeiro contato nas instituições menores (menos de 500 leads em 2026 ou sem área de marketing/captação mapeada); nas demais, só quando não houver decisor de captação, marketing ou comercial.

Qualquer contato da instituição serve como ponte: se não for a pessoa, pedimos quem responde pela captação.
Ordem proposta, a validar com a consultoria.

**Até dois contatos por universidade ao mesmo tempo** (diferente de Escolas, que era um por dia). Os demais ficam de reserva na planilha.

## 3. Formação dos lotes

1. Canal: quem tem WhatsApp vai para os lotes 1 e 2; só LinkedIn, só e-mail ou sem contato vai para o lote 3.
2. Volume de leads 2026: lote 1 = universidades com mais leads; lote 2 = demais.
3. Cargo: ordem da seção 2.
4. Até dois contatos por universidade, com preferência para quem tem WhatsApp.

Lote 3 por WhatsApp só para quem for enriquecido. Enriquecer telefone pela Nuvia custa 10 créditos por contato (~460 para os 46): decidir antes **[PENDENTE]**.

## 4. Higienização antes de cada lista (herdado de Escolas)

- DDD inválido fica fora; DDD de outro estado e números terminados em "000" ficam fora (foram a maior causa de falha de entrega em Escolas: 19 de 80 em 09/10).
- Contato que já tem conversa na Nuvia fica fora.
- Todas as variáveis do template preenchidas; campo vazio = contato fora.
- Primeiro nome limpo (sem "Prof.", "Dr.", sem segundo nome).
- Montar a lista completa **antes** de criar a campanha e conferir inscritos antes de ativar (em Escolas, lista alterada depois da campanha deixou 52 contatos sem mensagem).
- Cruzar com o HubSpot: tirar instituições em negociação, perdidas ou clientes **[PENDENTE: pipeline de Universidades]**.

## 5. Mensagens

Textos finais e variáveis: [`templates/universidades_whatsapp.md`](templates/universidades_whatsapp.md).

- Dois templates de abertura, teste A/B:
  - **A — volume de leads** (`universidades_abertura_a_leads`)
  - **B — potencial de receita** (`universidades_abertura_b_receita`)
- Follow-up no dia seguinte: recomendação de reusar `fup1_abordagembia3` (já aprovado).
- Divisão A/B: intercalar por volume de leads dentro de cada lote, para os braços ficarem comparáveis **[PENDENTE: confirmar]**.

Variáveis na Nuvia (campos de contato criados em 13/10):

| Variável | Campo | Chave |
|---|---|---|
| primeiro nome | nativo | `v_c_f_name` |
| instituição | Instituição | `v_c_instituicao` |
| leads 2026 | Leads 2026 | `v_c_leads_2026` |
| receita 24m | Receita Potencial 24m | `v_c_receita_pote_2sg` |
| matrículas estimadas | Matrículas Estimadas | `v_c_matriculas_e_l2y` |

### E-mail (mesmo dia da 1ª mensagem)

Pitch A — Assunto: `{{leads_2026}} alunos interessados em estudar na {{instituicao}}`

> Olá, {{primeiro_nome}}, tudo bem?
> Aqui é a Pamela, da FutureMe. Somos uma solução de orientação profissional para escolas públicas que conecta os alunos com o ensino superior.
> Hoje temos {{leads_2026}} alunos que estão se formando e têm interesse em estudar na {{instituicao}}.
> Gostaria de saber como esses alunos podem chegar até vocês neste ciclo. Teria 30 minutos esta semana ou na próxima?
> Abraço,
> Pamela | FutureMe

Pitch B — Assunto: `R$ {{receita_24m}} em potencial de matrículas para a {{instituicao}}`

> Olá, {{primeiro_nome}}, tudo bem?
> Aqui é a Pamela, da FutureMe. Somos uma solução de orientação profissional para escolas públicas que conecta os alunos com o ensino superior.
> Hoje temos {{leads_2026}} alunos que estão se formando e têm interesse em estudar na {{instituicao}}. Estimamos uma receita potencial de R$ {{receita_24m}} em mensalidades nos primeiros 24 meses.
> Quer saber como acessar esta base qualificada? Teria 30 minutos esta semana ou na próxima?
> Abraço,
> Pamela | FutureMe

### Roteiro de ligação

1. Abertura: "Olá, {{primeiro_nome}}, aqui é a Pamela, da FutureMe. Somos uma solução de orientação profissional para escolas públicas que conecta os alunos com o ensino superior. Te liguei porque temos {{leads_2026}} alunos que estão se formando e querem estudar na {{instituicao}}." No grupo B, completar com o potencial de receita.
2. Qualificação: "Quem aí responde pela captação de novos alunos?" Se não for a pessoa, pedir nome e contato do responsável.
3. Pedido: "Gostaria de entender como esses alunos podem se tornar matrícula neste ciclo. Podemos conversar por 30 minutos?"
4. Fechamento: confirmar data, horário e e-mail para o convite.

Objeções:
- **"Já temos fornecedor de leads."** São alunos que estão se formando e demonstraram interesse na sua instituição, não leads genéricos de mídia. Vale comparar a qualidade.
- **"Estamos sem verba."** A conversa é para mostrar o recorte e as possibilidades de parceria. Temos formatos de pagamento por sucesso.
- **"Me manda por e-mail."** Enviar resumo de três linhas e propor dois horários na mesma mensagem.

## 6. Campanhas na Nuvia

| Item | Configuração |
|---|---|
| Tipo | WhatsApp (WAP_AUTO_CLOSER), gatilho MANUAL, audiência = lista |
| Listas | `DD/MM A - universidades_abertura_a_leads` e `DD/MM B - universidades_abertura_b_receita` |
| Etapa 1 | Template de abertura do braço |
| Etapa 2 | Follow-up no dia seguinte (~24h) |
| Inbox | FutureME - B2B **[PENDENTE: confirmar mesmo número de Escolas]** |
| Dono | Pamela (HUMAN_USER) |
| Agente de IA | **[PENDENTE: Bia responde Universidades ou a Pamela atende direto?]** |
| Estado | Sempre criada em **RASCUNHO**; só ativa com OK explícito |

Janela de ativação: de manhã (9h30–11h30). O follow-up do dia seguinte não depende da hora, mas a primeira resposta precisa de alguém disponível para atender.

## 7. Agente de IA (se for usado)

Regras novas para Universidades:
- Pode repetir **apenas** os números que vieram no template para aquele contato (leads 2026, receita 24m). Nunca criar, arredondar ou extrapolar outro número. Se pedirem a origem: explicar o mecanismo (alunos de escolas públicas que fazem a orientação profissional da FutureMe e declaram interesse na instituição) e oferecer a conversa.
- "Não sou a pessoa certa" = Redirecionamento: perguntar quem responde pela captação e capturar nome e telefone.

Travas herdadas de Escolas (valem para qualquer BU):
- A etapa só muda em reação a mensagem do lead; clique em botão conta.
- Qualificado só com SIM explícito; nunca por inferência.
- "Agora não" / "sem interesse" não é Qualificado: sondar e, se mantido, Perdido.
- Nunca inventar caso, cliente, depoimento ou parceria.
- Tom de WhatsApp: frases curtas, perguntas sempre com "?".
- Nunca prometer pessoa específica nem agendar.
- Respostas automáticas (secretaria, horário comercial) = automática, não interesse.
- vCard = redirecionamento: ler o anexo e capturar nome e telefone.
- Edição do agente é ao vivo: backup antes, mostrar o que muda, OK explícito.

## 8. HubSpot

**[PENDENTE]**
- Pipeline de pré-vendas Universidades e etapa equivalente a "Abordados Núvia" (fila de quem não respondeu).
- Padrão de nome do card, sugestão: `Instituição, UF, Cidade [2026][BASE]`.
- Propriedades: cidade, ranking/faixa de leads, código e-MEC, leads 2026.
- Lista de etapas que a rotina nunca mexe.

Interessado: vai primeiro para a Pamela (SLA de 2 horas) com nome, instituição, telefone e o que disse.

## 9. Regras de segurança e aprovação

Nada que envia mensagem, muda o agente ou altera negócio existente acontece sem OK explícito da Pamela, no chat, para aquela ação. Um OK vale só para o que foi perguntado.

| Ação | Regra |
|---|---|
| Enviar template à Meta | Só com OK explícito (irreversível) |
| Ativar campanha | Só com OK; antes conferir rascunho, inscritos, etapas e dono |
| Editar agente de IA | Backup + mostrar mudança + OK |
| Mover etapa / nota no HubSpot | Tabela de mudanças + OK |
| Criar card novo no HubSpot | Automático, após checagem de duplicidade |
| Enriquecer contatos (créditos) | Só com OK, informando o custo |
| Pediu para sair / Perdido | Nunca reabordar |
| Repositório GitHub (público) | Nunca subir lista, telefone ou nome de lead |

## 10. Checklist antes do primeiro disparo

Templates e Nuvia
- [x] Campos de contato das variáveis criados na Nuvia (13/10)
- [x] Templates A e B validados pela Pamela
- [x] Templates enviados à Meta (13/10, em análise)
- [ ] Templates **APROVADOS** pela Meta
- [ ] Follow-up definido (reusar `fup1_abordagembia3` ou criar A/B)
- [ ] Decisão sobre agente de IA para Universidades
- [ ] Inbox confirmado

Base e listas
- [ ] Listas dos lotes recebidas (fora do repositório)
- [ ] Higienização (DDD, nome, variáveis preenchidas, conversa anterior)
- [ ] Cruzamento com HubSpot
- [ ] Divisão A/B por lote
- [ ] Contatos importados com os campos preenchidos

HubSpot
- [ ] Pipeline e etapa de fila de Universidades
- [ ] Padrão de card e propriedades

Disparo
- [ ] Listas e campanhas em rascunho conferidas
- [ ] OK da Pamela para ativar, dentro da janela

## 11. Pendências do plano original

- O lote 1 estava previsto para 13/10, mas os templates ainda não existem na Meta. O cronograma desloca conforme a aprovação.
- Os três links de listas do .docx apontam para o mesmo artifact.
- O follow-up original fixava "quinta ou sexta à tarde", o que não funciona para os lotes 2 e 3 (troca proposta em `templates/`).
