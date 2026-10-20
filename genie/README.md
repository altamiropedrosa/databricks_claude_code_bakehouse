# Genie spaces

Espaços do [Genie](https://docs.databricks.com/genie/) para perguntas em linguagem natural, versionados
como código e publicados pelo job em cada target (`[dev]`, `[ci]`, `[prod]`).

| Espaço | Público | Fontes |
|---|---|---|
| Bakehouse Lakehouse - Vendas e Satisfação (`bakehouse_sales_satisfaction.yaml`) | Gestores de negócio | Metric view `gold.sales_metrics` (vendas) e `gold.sentiment_by_franchise` (satisfação) |

Perguntas que ele responde bem (validadas em dev pela API de conversa):

1. Qual franquia teve a maior receita no último mês?
2. Como evoluiu a receita diária por país?
3. Qual produto mais vende em cada país?
4. Qual o ticket médio por forma de pagamento?
5. Em que dia da semana e horário vendemos mais?
6. Quais franquias têm o pior sentimento nas avaliações?

## Como funciona

- O bloco `space` do YAML é o `serialized_space` da API do Genie (versão 2). No arquivo, `${catalog}`
  substitui o catálogo, e textos simples substituem os arrays exigidos pela API.
- A tarefa `publish_genie_space` do job (depois de `publish_metric_views`) cria o espaço
  `[<target>] <title>` na pasta `genie/` do bundle ou, se ele já existir, atualiza a configuração.
  Edições feitas pela interface são sobrescritas na próxima execução: altere sempre o YAML.
- Para renomear um espaço, mude `title` e mova o título antigo para `previous_titles`: o job encontra o
  espaço existente pelo título antigo e o renomeia, sem criar um duplicado.
- `tests/test_genie_space.py` (CI, offline) garante que:
  - as fontes são metric views de `semantic/` ou tabelas com contrato, e o catálogo nunca é fixo;
  - as colunas configuradas existem e as colunas de dado pessoal ficam ocultas;
  - o SQL só lê fontes anexadas e os snippets qualificam todas as colunas;
  - o payload gerado segue as regras da API (ids, ordenação, arrays).

## Decisões de desenho

- **Métricas vêm da metric view.** O Genie usa `MEASURE()` e não reescreve fórmulas de receita ou ticket médio.
- **Sentimento agregado** tem uma medida própria (`net_sentiment_total`), que soma as contagens. A descrição
  de `net_sentiment`/`positive_ratio` proíbe tirar média de razões entre franquias.
- **A instrução de texto é mínima**, só para o que não cabe em metadados:
  - os dados são históricos, então "último mês" significa o período mais recente nos dados;
  - "vendas" significa receita;
  - nunca usar símbolo de moeda, porque os dados não informam a moeda.
- **Entity matching** só nas colunas categóricas que as pessoas citam pelo nome (franquia, cidade, país,
  produto, pagamento, dia da semana, continente). Latitude e longitude ficam ocultas.

## Como alterar

1. Edite o YAML (novas perguntas de exemplo devem ter ids hex de 32 caracteres, únicos).
2. Valide cada SQL novo no SQL editor contra `bakehouse_dev`.
3. `DATABRICKS_SKIP_CONNECT=1 uv run pytest tests/test_genie_space.py`
4. Publique em dev, rode o job e teste as perguntas no espaço `[dev]`.
