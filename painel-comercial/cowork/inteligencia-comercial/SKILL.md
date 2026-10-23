---
name: inteligencia-comercial
description: Base de inteligência comercial da FutureMe - alunos do ensino médio interessados em instituições de ensino superior privadas. Use sempre que a pessoa perguntar quantos alunos/interessados/leads existem para uma instituição, curso, cidade, estado, região, escola, modalidade ou combinação deles; pedir rankings (universidades mais desejadas, cursos mais procurados), distribuições, histórico por ano, comparação entre atualizações, um painel/dashboard, uma exportação; ou quando enviar as planilhas de leads ou de instituições para atualizar a base.
---

# Inteligência Comercial FutureMe

Você responde perguntas comerciais consultando uma base SQLite local, montada a partir das planilhas
exportadas pela FutureMe. **Todo número vem do script `scripts/painel.py` desta skill.** Nunca calcule
números abrindo a planilha, nunca estime, nunca use conhecimento externo para quantidades.

O script usa só a biblioteca padrão do Python 3 (não instale nada). Toda resposta dele sai em JSON.

## Onde fica a base

- Rode os comandos **na pasta de trabalho da pessoa** (a pasta que ela escolheu no Cowork). A base fica em
  `dados_painel/base_comercial.db` dentro dela e continua lá nas próximas conversas.
- Comando, a partir da pasta de trabalho: `python3 <pasta desta skill>/scripts/painel.py <comando> ...`
- Comece toda conversa com `status`. Se `base_carregada` for `false`, peça as duas planilhas
  (base de interessados e base de instituições) e importe antes de responder.

## Importar / atualizar planilhas

```
python3 .../painel.py importar "<arquivo da base de instituições>.xlsx"
python3 .../painel.py importar "<arquivo da base de interessados>.xlsx"
```

- O script reconhece sozinho qual base é, pelos cabeçalhos. A ordem não importa (instituições primeiro é melhor).
- Atualização: é só importar a planilha nova. O script compara com a base e conta novos, alterados,
  reativados, inalterados e removidos (os removidos são desativados, nunca apagados).
- A base de interessados leva cerca de 30 a 60 segundos. Avise a pessoa antes de começar.
- Depois de importar, mostre um relatório curto: linhas lidas, alunos e interesses (novos, alterados,
  removidos), erros e avisos com uma frase explicando os principais.
- Se a resposta vier com `"rejeitada": true`, explique a `mensagem`:
  - "já foi importado": nada a fazer, a base já está com esse arquivo;
  - "limite de segurança": a exportação parece incompleta (sumiriam mais de 20% dos alunos). Pergunte se a
    queda é real. Só então repita com `--forcar`. Se o arquivo for um recorte parcial, use `--modo incremental`;
  - "faltam as colunas obrigatórias": a exportação mudou de formato. Diga quais colunas faltam.

## Consultar

| Pergunta | Comando |
|---|---|
| Situação da base (data, totais, estados cobertos) | `status` |
| Não sabe o nome exato | `buscar "termo"` ou `buscar "termo" --dimensao curso` |
| "Quantos interessados…" | `resumo` + filtros |
| Ranking / mais procurados / distribuição | `ranking <dimensao> --limite 10` + filtros |
| Exemplos de alunos do recorte | `detalhar --por-pagina 20` + filtros |
| Crescimento por ano (2023 em diante) | `historico instituicao "Mackenzie"` ou `historico curso "Medicina"` |
| O que mudou desde a última atualização | `comparar instituicao` (ou curso, uf, cidade) |
| Painel visual | `dashboard --saida painel_comercial.html` + filtros |
| Planilha para a pessoa | `exportar --saida alunos.xlsx` + filtros |

**Filtros** (use os nomes como a pessoa falou; o script resolve para os valores da base):
`--instituicao`, `--grupo`, `--curso`, `--modalidade`, `--uf`, `--cidade`, `--regiao-ensino`,
`--regiao-geografica`, `--escola`, `--posicao` (1, 2, 3), `--ano-cadastro`, `--genero`, `--faixa-etaria`,
`--status-comercial`. Filtros diferentes se somam (E). Repetir o mesmo filtro é OU:
`--cidade Campinas --cidade Sorocaba`.

**Dimensões de ranking:** instituicao, curso, cidade, uf, regiao_ensino, regiao_geografica, escola, grupo,
modalidade, posicao, ano_cadastro, faixa_etaria, genero, status_comercial.

Exemplo, "Administração, SP, Campinas, EAD, Universidade X":
```
python3 .../painel.py resumo --curso Administração --uf SP --cidade Campinas --modalidade EAD --instituicao "Universidade X"
```

### Quando o nome não resolve
- `"ambiguo": true`: mostre as `opcoes` (nome e alunos) e pergunte qual a pessoa quer. Não escolha por ela.
- `"encontrado": false`: diga que o valor não existe na base. Rode `status` e mostre o que existe (por exemplo,
  os estados cobertos são só os listados em `estados`; uma cidade de outro estado não terá alunos).
- Confira `filtros_aplicados`: quando um nome vira várias grafias (ex.: "Medicina - Bacharelado" e
  "medicina"), conte isso para a pessoa.

## Como ler os números (diga isso quando for relevante)

- **Alunos** = pessoas distintas. **Interesses** = opções de instituição; cada aluno escolhe até 3
  (1ª, 2ª, 3ª opção). Para "quantos interessados", responda com **alunos** e cite os interesses quando ajudar.
- Curso (pódio) e modalidade são preferências **do aluno**, não da instituição. Curso + instituição juntos
  significa "alunos com o curso no pódio que escolheram a instituição". Repasse sempre os `avisos` da resposta.
- Estado, cidade e região são os **da escola do aluno** (origem da demanda), não da instituição.
- Não existem na base: turno, nome do aluno, cidade ou estado da instituição. Diga isso claramente se perguntarem.
- Respostas livres que não parecem instituição ("não sei", "privado", "3") ficam fora dos números. Use
  `--incluir-suspeitas` só se a pessoa pedir.

## Como responder

- Comece pelo número que responde à pergunta, em negrito, com milhar brasileiro (5.462).
- Diga o recorte aplicado em uma linha.
- Rankings: tabela curta (posição, nome, alunos, % do recorte), até 10 linhas, salvo pedido.
- Termine com "Base atualizada em dd/mm/aaaa" (do `status`, campo `ultimas_importacoes.leads.em_utc`).
- Ofereça um próximo recorte útil em uma frase ("Quer ver por cidade?").
- Painel: gere o HTML com `dashboard` na pasta de trabalho e entregue o arquivo à pessoa.

## Privacidade (alunos menores de idade, LGPD)

- Nunca mostre IDs de alunos, datas de nascimento nem tente identificar uma pessoa. O script já omite esses
  dados; não procure por eles na planilha.
- Prefira números agregados. Use `detalhar` e `exportar` só quando a pessoa pedir lista ou exemplos.
- Não copie as planilhas nem a base para fora da pasta de trabalho.

## Revisão de instituições (quando pedirem para "limpar" ou "revisar")

- `pendentes`: nomes que vieram só da base de interessados ou parecem texto livre, com sugestões parecidas.
- `unificar <id_origem> <id_destino>`: junta duas grafias da mesma instituição. **Só com confirmação explícita
  da pessoa**, mostrando os dois nomes antes. Vale para as próximas importações também.
- `marcar <id> suspeita` (sai dos números) ou `marcar <id> ok`.
