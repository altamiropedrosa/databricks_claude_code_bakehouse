# Camadas de dados

Detalhe de cada tabela do pipeline medalhão. Visão geral no [README](../README.md#arquitetura).

## 🥉 Bronze: ingestão

Streaming tables com ingestão incremental e cópia fiel das colunas de origem, acrescidas dos metadados
`_ingested_at` e `_source_table`. É a **única** camada que lê `samples.bakehouse`.

`customers` · `franchises` · `reviews` · `suppliers` · `transactions`

## 🥈 Silver: dados limpos e conformados

| Tabela | Tipo | Destaques |
|---|---|---|
| `customers` | Materialized view | Dimensão de clientes com país padronizado (`USA`/`US` → `United States`) |
| `franchises` | Materialized view | Dimensão de franquias com localização validada, enriquecida com o fornecedor |
| `transactions` | Materialized view | Tipos corretos, colunas de data derivadas, enriquecida com franquia e cliente. Do cartão, só os **4 últimos dígitos** são mantidos |
| `reviews_sentiment` | Streaming table | Sentimento classificado com `ai_analyze_sentiment`. Por ser streaming, cada avaliação é pontuada **uma única vez** |

**Qualidade de dados:** as tabelas silver usam *expectations*. Registros sem chave, com quantidade ou valor
não positivos são **descartados**; inconsistências como `total_price ≠ quantity × unit_price` ou meio de
pagamento desconhecido são **registradas** nas métricas do pipeline, sem descartar a linha.

## 🥇 Gold: marts para BI

| Tabela | Granularidade | Uso |
|---|---|---|
| `daily_sales_by_franchise` | dia × franquia × meio de pagamento | Tendência de vendas e mix de pagamento |
| `sales_by_product` | produto × dia × país | Mix de produtos por período e país |
| `sales_by_country` | país da franquia | Receita e participação por país |
| `franchise_performance` | franquia | Desempenho acumulado e coordenadas para mapas |
| `sentiment_by_franchise` | franquia | Contagens e `net_sentiment` ∈ [-1, 1] |
| `top_customers` | cliente | Ranking por receita e produto favorito |

As medidas das tabelas diárias são **aditivas**: qualquer agregação é um `SUM`. Para receita, pedidos,
ticket médio e afins, prefira a [camada semântica](../semantic/README.md) (`gold.sales_metrics`), que já
recalcula razões como o ticket médio corretamente em qualquer nível de agregação.

Cada tabela gold, e também `silver.transactions`, tem um [contrato de dados](../contracts/README.md).

## 📊 Dashboard

**`[<target>] Bakehouse - Vendas e Satisfacao`**, com as páginas *Visão geral* e *Filtros*. Vendas diárias e
mix de produtos vêm da metric view `gold.sales_metrics` (via `MEASURE()`); desempenho das franquias e
sentimento vêm das tabelas gold.
