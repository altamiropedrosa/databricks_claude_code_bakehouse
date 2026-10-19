# Camada semântica

As métricas de negócio do Bakehouse são definidas **uma única vez**, como
[metric views do Unity Catalog](https://docs.databricks.com/metric-views/), e consumidas por dashboards,
Genie e SQL. Assim "receita" ou "ticket médio" significam a mesma coisa em todo lugar.

| Metric view | Fonte (com contrato) | Conteúdo |
|---|---|---|
| `gold.sales_metrics` | `silver.transactions` | 13 dimensões (data, mês, produto, franquia, país, pagamento...) e 7 medidas: `revenue`, `orders`, `units_sold`, `avg_ticket`, `units_per_order`, `unique_customers`, `active_franchises` |

## Como consultar

As medidas são chamadas com `MEASURE()` e agregadas pelas dimensões do `GROUP BY`:

```sql
SELECT franchise_country, transaction_month,
       MEASURE(revenue) AS receita, MEASURE(avg_ticket) AS ticket_medio
FROM bakehouse_prod.gold.sales_metrics
GROUP BY ALL
ORDER BY receita DESC;
```

- Medidas compostas (`avg_ticket = MEASURE(revenue) / MEASURE(orders)`) são recalculadas no nível consultado.
  Não tire a média de médias nem some `unique_customers` entre linhas.
- Nunca filtre por medida no `WHERE`: use `HAVING`.

## Como funciona

- Cada arquivo `semantic/<schema>/<view>.yaml` é a definição YAML da metric view (versão 1.1). O `source`
  não leva catálogo (`silver.transactions`): a tarefa `publish_metric_views` do job adiciona o catálogo
  do target e roda `CREATE OR REPLACE VIEW ... WITH METRICS`.
- A publicação roda **depois** da verificação dos contratos: se um contrato for violado, a camada
  semântica não é republicada.
- `tests/test_semantic_layer.py` (CI, offline) garante que:
  - a fonte tem contrato de dados e toda coluna usada está no contrato;
  - nenhuma coluna classificada como dado pessoal (`classification`) é exposta;
  - todo campo tem `comment` e `display_name` (usados pelo Genie e pelos dashboards);
  - medidas compostas referenciam medidas existentes.

## Como adicionar uma métrica

1. Adicione a dimensão ou medida no YAML, com `comment`, `display_name` e `synonyms` em português e inglês.
2. Se ela usar uma coluna nova, a coluna precisa estar antes no contrato da fonte.
3. `DATABRICKS_SKIP_CONNECT=1 uv run pytest tests/test_semantic_layer.py`
4. Publique em dev e rode o job.

> Para testar um `CREATE ... WITH METRICS` manualmente, use o SQL editor ou a Statement Execution API.
> O comando `databricks experimental aitools tools query` altera a indentação de textos com várias
> linhas e quebra o YAML.
