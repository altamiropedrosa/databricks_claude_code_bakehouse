# 001 · Opiniões por produto nas avaliações

| | |
|---|---|
| **Status** | Aprovada |
| **Autor** | Altamiro Pedrosa |
| **Data** | 20/10/2026 (proposta e aprovação, PR #18) |
| **Implementação** | PR #19 |

## 1. Problema

`silver.reviews_sentiment` diz **se** uma avaliação é positiva ou negativa, mas não **por quê**. O dashboard
mostra que a Tokyo Treats tem o pior sentimento líquido da rede (-0,50), e ninguém consegue responder, sem ler
as avaliações uma a uma, o que os clientes criticam lá: qual produto e qual aspecto dele.

## 2. Objetivo

Para cada franquia e país, responder **quais produtos são elogiados ou criticados e por qual motivo**, a partir
do texto das avaliações, com IA, e disponibilizar isso no dashboard e no Genie.

## 3. Evidências da exploração

Consultas de leitura em `bakehouse_prod`, em 20/10/2026. Nada foi gravado.

**Os dados**
- 204 avaliações de 48 franquias, de 20/05 a 31/05/2024, em inglês, com 657 caracteres em média.
- Sentimento atual: 86 negativas, 67 mistas e 51 positivas.
- As avaliações falam quase só dos 6 produtos da rede, os mesmos de `silver.transactions`: Outback Oatmeal,
  Austin Almond Biscotti, Orchard Oasis, Golden Gate Ginger, Tokyo Tidbits e Pearly Pies.
- Temas como atendimento ou espera quase não aparecem. A busca por *sold out*, *not available*, *overpriced*,
  *staff* ou *service* encontra 28 avaliações, a maioria sobre produto esgotado ou caro.
- Não há dado pessoal: a avaliação não identifica o cliente.

**Teste 1 · temas gerais da avaliação (descartado).** `ai_classify` com vários rótulos ao mesmo tempo
(sabor, textura, frescor, preço, disponibilidade, atendimento, ambiente), numa amostra de 60 avaliações:

| Tema | Avaliações | Das quais negativas |
|---|---|---|
| textura | 60 (100%) | 25 |
| sabor | 53 (88%) | 18 |
| frescor | 9 | 7 |
| disponibilidade | 6 | 4 |
| ambiente | 6 | 0 |
| preço | 5 | 3 |

Um tema que aparece em todas as avaliações, elogiando ou criticando, não explica nada. Descartado.

**Teste 2 · opinião por produto (proposto).** `ai_extract` com uma lista de menções por avaliação, cada uma
com produto, opinião e motivo em listas fechadas, na mesma amostra: 295 menções, nenhum erro, toda avaliação
com pelo menos uma menção. As críticas mais frequentes já mostram padrões acionáveis:

| Produto | Motivo | Menções negativas |
|---|---|---|
| Golden Gate Ginger | sabor | 20 |
| Orchard Oasis | sabor | 19 |
| Austin Almond Biscotti | textura | 13 |
| Outback Oatmeal | textura | 13 |
| Austin Almond Biscotti | sabor | 12 |
| Outback Oatmeal | sabor | 12 |

## 4. Escopo

**Dentro**
- Extração de opiniões por produto em todas as avaliações, atuais e futuras.
- Uma tabela silver no nível da menção e um mart gold por franquia, com contrato de dados.
- Uma seção nova no dashboard e o mart anexado ao Genie.

**Fora**
- Temas que não são de produto (atendimento, ambiente): raros nestes dados. Ver questão Q2.
- Alterar ou reprocessar `silver.reviews_sentiment`.
- Traduzir o texto das avaliações.
- Medir a evolução no tempo: os dados cobrem só 12 dias.

## 5. Requisitos funcionais

**RF1 · `silver.review_product_opinions`**: uma linha por avaliação e produto citado.

| Coluna | Tipo | Regra |
|---|---|---|
| `review_id` | INT | Obrigatória. Chave, junto com `product` |
| `franchise_id` | BIGINT | Obrigatória |
| `review_date` | DATE | Obrigatória |
| `product` | STRING | Obrigatória. Um dos 6 produtos da rede |
| `opinion` | STRING | Obrigatória. `positive`, `negative` ou `neutral` |
| `reason` | STRING | Obrigatória. `taste`, `texture`, `freshness`, `price`, `availability` ou `other` |
| `_ingested_at` | TIMESTAMP | Momento da extração |

- Se o modelo citar o mesmo produto duas vezes na mesma avaliação, fica uma única linha.
- Avaliação sem nenhum produto citado não gera linha, mas é contada (ver CA2).
- Erro de extração é registrado nas métricas de qualidade do pipeline, sem derrubar a execução.

**RF2 · `gold.product_opinions_by_franchise`**: uma linha por franquia, produto e motivo.

| Coluna | Regra |
|---|---|
| `franchise_id`, `franchise_name`, `city`, `country` | Identificação da franquia, como em `gold.sentiment_by_franchise` |
| `product`, `reason` | Chave, junto com `franchise_id` |
| `mentions`, `positive_mentions`, `negative_mentions`, `neutral_mentions` | Contagens, todas aditivas |

Razões (por exemplo, a proporção de menções negativas) são calculadas na consulta, nunca guardadas: assim
continuam corretas em qualquer agregação.

**RF3 · Contrato de dados** ODCS v3 para `gold.product_opinions_by_franchise`, como as demais tabelas gold,
com as listas fechadas de `product`, `opinion` e `reason` como regras de qualidade.

**RF4 · Dashboard**: nova seção *O que os clientes criticam*, com:
- barras empilhadas de menções negativas por produto, coloridas por motivo;
- tabela por franquia com o produto e o motivo mais criticados;
- respeito ao filtro de país existente.

**RF5 · Genie**: anexar `gold.product_opinions_by_franchise` ao espaço existente, com duas perguntas de exemplo
e o SQL validado:
- *"Por que as avaliações da Tokyo Treats são negativas?"*
- *"Qual produto mais recebe críticas no Japão?"*

## 6. Requisitos não funcionais

- **RNF1 · IA uma vez por avaliação:** a silver é uma streaming table. Atualizar o pipeline sem avaliação nova
  não chama o modelo de novo.
- **RNF2 · Convenções do projeto:** catálogo nunca fixo no código, um arquivo SQL por tabela na pasta da camada,
  nomes de schema vindos do bundle. Os testes existentes cobram isso.
- **RNF3 · Custo:** a carga inicial faz 204 chamadas ao modelo; as seguintes, só as avaliações novas.
- **RNF4 · Sem dado pessoal:** as tabelas novas não têm colunas pessoais.
- **RNF5 · Tema claro:** os widgets novos seguem a paleta e o teste de tema do dashboard.

## 7. Critérios de aceite

| Nº | Critério | Como verificar |
|---|---|---|
| CA1 | `product`, `opinion` e `reason` só têm valores das listas fechadas, e todo `product` existe em `silver.transactions` | Expectations no SQL e teste offline do contrato |
| CA2 | No máximo 5% das avaliações com texto ficam sem nenhuma menção | Consulta após a carga, resultado registrado na seção 11 |
| CA3 | Nenhuma linha duplicada por `review_id` + `product` na silver e por `franchise_id` + `product` + `reason` na gold | Verificação de chave do `enforce_data_contracts` |
| CA4 | Em avaliações `negative`, pelo menos 70% das menções são negativas; em `positive`, pelo menos 70% são positivas | Consulta após a carga, registrada na seção 11 |
| CA5 | Concordância de pelo menos 80% em `opinion` e 70% em `reason`, numa amostra de 30 menções rotuladas manualmente pelo autor (alterado na implementação, ver seção 10) | Amostra e resultado registrados na seção 11 |
| CA6 | Uma segunda atualização do pipeline, sem avaliação nova, não altera a silver | Contagem e `_ingested_at` antes e depois |
| CA7 | O dashboard mostra a seção nova, e as consultas batem com a gold | Consultas testadas antes do deploy |
| CA8 | O Genie responde às duas perguntas do RF5 usando o mart novo | Conversation API, resposta registrada na seção 11 |
| CA9 | CI verde: lint, testes offline, execução completa no target `ci` | GitHub Actions |

## 8. Decisões técnicas propostas

- **`ai_extract` com esquema e listas fechadas** em vez de `ai_classify` com vários rótulos: o teste 1 mostrou
  que temas da avaliação inteira não discriminam. `ai_query` fica como último recurso, se `ai_extract` não
  atender.
- **Tabela nova em vez de coluna em `reviews_sentiment`:** acrescentar uma coluna a uma streaming table exige
  refazer a carga inteira, o que pontuaria de novo o sentimento de todas as avaliações.
- **Lista de produtos fixa no esquema da extração:** os 6 produtos são os mesmos das vendas. Um produto novo
  exige atualizar esta spec, o SQL e o contrato, com versão MINOR do contrato.
- **Valores em inglês na tabela** (`taste`, `negative`), como em `sentiment`. A tradução para português fica no
  dashboard e no Genie.

## 9. Riscos

| Risco | Mitigação |
|---|---|
| O modelo muda de versão e passa a responder diferente | `version` fixada nas opções da função; a streaming table não reprocessa o que já foi extraído |
| Dados sintéticos: avaliações parecidas entre si podem inflar padrões | Os critérios CA4 e CA5 medem a qualidade; a limitação fica registrada no contrato |
| Avaliação longa com opinião ambígua | Opinião `neutral` e motivo `other` existem para não forçar uma classificação |

## 10. Decisões da revisão

| Questão | Decisão |
|---|---|
| **Q1 · Nomes:** `review_product_opinions` e `product_opinions_by_franchise` estão bons? | Mantidos |
| **Q2 · Temas fora de produto:** incluir um motivo `service` (atendimento), mesmo raro nestes dados? | Não incluir. Atendimento quase não aparece nas avaliações; volta numa spec futura se surgir nos dados |
| **Q3 · Limites:** 5% (CA2), 70% (CA4) e 80%/70% (CA5) são aceitáveis? | Mantidos, coerentes com a amostra da seção 3 |
| **Q4 · Camada semântica:** criar uma metric view de opiniões para o Genie, ou o mart gold basta nesta entrega? | O mart gold basta. Uma metric view de opiniões fica para uma spec futura |

**Alteração durante a implementação (PR #19):** a pedido do autor, a amostra do CA5 foi rotulada pelo
assistente de IA (Claude Code), e não manualmente pelo autor. O critério passa a medir a concordância entre o
modelo de extração e uma segunda leitura feita por outro modelo, o que **não equivale a uma avaliação humana
independente**. Os rótulos e o critério de cada um estão no arquivo da amostra, para revisão do autor.

## 11. Resultado

Medido em `bakehouse_dev` em 20/10/2026, na carga inicial. Os números de produção entram aqui depois do
deploy.

| Nº | Resultado | Situação |
|---|---|---|
| CA1 | Expectations e testes offline (`tests/test_product_opinions.py`) garantem as listas fechadas; os 6 produtos extraídos existem em `silver.transactions` | ✅ |
| CA2 | 2 de 204 avaliações (1,0%) sem menção. As duas citam produtos: falha do modelo, não ausência de produto (ver limitações) | ✅ |
| CA3 | `enforce_data_contracts`: 9/9 contratos satisfeitos, chaves sem duplicatas | ✅ |
| CA4 | Avaliações `negative`: 96,7% das menções negativas. Avaliações `positive`: 89,1% positivas | ✅ |
| CA5 | Opinião: 30/30 (100%). Motivo: 27/30 (90%). Rotulado pelo assistente de IA a pedido do autor (seção 10); amostra em [001-amostra-ca5.csv](001-amostra-ca5.csv) | ✅ |
| CA6 | Segunda atualização sem avaliação nova: 1.007 linhas e `_ingested_at` iguais antes e depois | ✅ |
| CA7 | Consultas do dashboard testadas; a gold soma as mesmas 1.007 menções e 466 críticas da silver | ✅ |
| CA8 | Genie de dev respondeu às duas perguntas com o mart novo, em português e com motivos traduzidos | ✅ |
| CA9 | CI do PR de implementação | ⏳ |

**Números da carga:** 1.007 menções em 202 avaliações, 466 delas negativas. Os produtos mais criticados são
Orchard Oasis (74 críticas de sabor) e Golden Gate Ginger (68 de sabor). Austin Almond Biscotti e Outback
Oatmeal dividem as críticas entre sabor e textura.

**Respostas do Genie (CA8):**
- *Tokyo Treats:* críticas concentradas em sabor e textura; o produto mais criticado é o Orchard Oasis, pelo
  sabor (4 críticas).
- *Japão:* Golden Gate Ginger, Austin Almond Biscotti e Outback Oatmeal empatam com 33 críticas. A resposta
  cita o empate, mas apresenta o primeiro como "o que mais recebe críticas".

**Rotulagem do CA5:** a opinião está certa quando bate com o que o cliente disse sobre aquele produto; o motivo,
quando é o principal citado (com dois motivos de mesmo peso, qualquer um vale). Os 3 erros de motivo:
- #13: o elogio ao Outback Oatmeal é à textura, e o modelo disse sabor;
- #16 e #19: o texto não dá motivo (o certo seria `other`), e o modelo disse sabor. O #25 tem o mesmo texto do #19
  e acertou `other`: o modelo não é totalmente consistente entre textos idênticos.

**Limitações observadas:**
- As 2 avaliações sem menção (ids 48 e 163) citam produtos no texto; o modelo não devolveu nenhuma menção para
  elas. Como a silver é streaming, elas não são reprocessadas automaticamente.
- Produto que o cliente ainda não provou ("can't wait to try the Pearly Pies") pode virar uma menção
  `neutral`/`other`, quando o ideal seria não gerar menção.
- Opinião sem motivo explícito tende a ser classificada como sabor (`taste`), o motivo mais frequente.
