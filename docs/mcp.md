# Servidor MCP `bakehouse`

Servidor [MCP](https://modelcontextprotocol.io) (Model Context Protocol) que expõe a camada governada do projeto
como ferramentas para agentes de IA, como o Claude Code. Especificação:
[specs/002-servidor-mcp.md](../specs/002-servidor-mcp.md).

O agente consulta vendas, satisfação e contratos **pelas mesmas definições** do dashboard e do Genie, somente
leitura e sem SQL livre.

## Ferramentas

| Ferramenta | Fonte | Para que serve |
|---|---|---|
| `query_sales_metrics` | Metric view `gold.sales_metrics` | Receita, pedidos, ticket médio e as demais medidas, por qualquer dimensão, com filtros de país, franquia e período |
| `get_product_opinions` | `gold.product_opinions_by_franchise` | Produtos e motivos das críticas (ou elogios) extraídos das avaliações |
| `get_franchise_sentiment` | `gold.sentiment_by_franchise` | Franquias com o pior (ou melhor) sentimento |
| `describe_data_contract` | `contracts/` | Finalidade, colunas, chave, dono, SLA e versão de uma tabela publicada |

## Como usar com o Claude Code

1. Autentique a CLI do Databricks (`databricks auth login`) e rode `uv sync --dev`.
2. Abra o Claude Code na pasta do projeto. Na primeira vez, ele pede para aprovar o servidor `bakehouse`,
   declarado em [`.mcp.json`](../.mcp.json).
3. Pergunte normalmente, por exemplo: *"Por que a Tokyo Treats é mal avaliada e quanto ela faturou?"*.

`claude mcp list` mostra se o servidor está conectado. O servidor usa a autenticação da CLI do Databricks, com
as permissões de quem o executa, e consulta o warehouse definido no bundle.

## Segurança

| Regra | Como é garantida |
|---|---|
| Somente leitura, sem SQL livre | Cada ferramenta monta um único `SELECT`; medidas, dimensões e colunas só entram se estiverem nas listas de permissão lidas de `semantic/` e `contracts/` |
| Sem injeção | Valores de filtro viajam como parâmetros da Statement Execution API, nunca no texto da consulta |
| Sem dado pessoal | Colunas marcadas como `classification: restricted` nos contratos nunca são devolvidas |
| Catálogo certo | Vem do target do bundle em `databricks.yml`. O padrão é `dev`; para outro, altere `BAKEHOUSE_TARGET` no `.mcp.json` local |
| Guardrail | O hook de segurança do Claude Code intercepta as ferramentas `mcp__bakehouse__*` |
| Limites | No máximo 1.000 linhas por resposta e 120 s por consulta |

Tudo isso é coberto por testes offline em `tests/test_mcp_server.py`.

## Código

- `src/mcp_server/queries.py`: listas de permissão e montagem das consultas, sem acesso ao Databricks (testável offline).
- `src/mcp_server/server.py`: as ferramentas MCP (SDK oficial `mcp`, transporte stdio) e a execução no warehouse.
