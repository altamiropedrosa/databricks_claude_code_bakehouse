# Desenvolvimento

Como rodar o projeto localmente, como o repositório está organizado e quais convenções os testes cobram.

- [Pré-requisitos](#pré-requisitos)
- [Desenvolvimento local](#desenvolvimento-local)
- [Testes](#testes)
- [Estrutura do repositório](#estrutura-do-repositório)
- [Convenções do projeto](#convenções-do-projeto)

## Pré-requisitos

- [Databricks CLI](https://docs.databricks.com/dev-tools/cli/install) **v1.21.0** (a mesma versão usada no CI)
- [uv](https://docs.astral.sh/uv/getting-started/installation/) e Python **3.12**
- Workspace Databricks com Unity Catalog e computação serverless
- Catálogos `bakehouse_dev`, `bakehouse_ci` e `bakehouse_prod` já criados (o bundle cria os schemas, não os catálogos)
- SQL warehouse chamado **`Serverless Starter Warehouse`** (resolvido por nome no bundle)
- AI Functions disponíveis no workspace (para `ai_analyze_sentiment`)

## Desenvolvimento local

```bash
# 1. Autenticar no workspace
databricks auth login --host https://<seu-workspace>.cloud.databricks.com

# 2. Instalar dependências de desenvolvimento
uv sync --dev

# 3. Lint e testes (offline, sem conexão com o Databricks)
uv run ruff check .
DATABRICKS_SKIP_CONNECT=1 uv run pytest -v

# 4. Validar, publicar e executar em dev
databricks bundle validate
databricks bundle deploy
databricks bundle run bakehouse_medallion_job
```

Em execução, o job `bakehouse_medallion_job` roda a tarefa `enforce_data_contracts` depois do pipeline: ela
confere o schema publicado no Unity Catalog, a unicidade da chave primária e o prazo de atualização de cada
contrato, aplica as tags de contrato e de dado pessoal, e falha a execução se algum contrato for violado.
Em seguida, a tarefa `publish_metric_views` republica a [camada semântica](../semantic/README.md)
(`gold.sales_metrics`), que o dashboard usa para os dados de vendas, e a tarefa `publish_genie_space`
cria ou atualiza o [Genie space](../genie/README.md) `[<target>] Bakehouse Lakehouse - Vendas e Satisfação` em cima dela.

## Testes

Todos os testes rodam **offline**, sem conexão com o Databricks, no CI e na máquina do desenvolvedor.

| Arquivo | O que verifica |
|---|---|
| `tests/test_bundle_conventions.py` | As [convenções do projeto](#convenções-do-projeto): catálogo nunca fixo no código, cada SQL criando a tabela da própria camada, só a bronze lendo a origem, configuração do pipeline vinda do bundle e widgets do dashboard ligados a campos existentes |
| `tests/test_data_contracts.py` | Os [contratos de dados](../contracts/README.md): toda tabela gold tem contrato, o SQL declara exatamente as colunas, tipos, `NOT NULL`, comentários e expectations do contrato, e mudanças incompatíveis exigem versão MAJOR em relação ao `origin/master` |
| `tests/test_enforce_data_contracts.py` | A verificação em execução (`src/jobs/enforce_data_contracts.py`) |
| `tests/test_semantic_layer.py` | A camada semântica: só usa colunas do contrato da fonte, nunca colunas de dado pessoal |
| `tests/test_genie_space.py` | A configuração versionada do Genie space |
| `tests/test_mcp_server.py` | O [servidor MCP](mcp.md) ([spec 002](../specs/002-servidor-mcp.md)): só um `SELECT` por chamada, listas de permissão, parâmetros em vez de valores no texto, catálogo do target, nenhum dado pessoal e guardrail ativo |
| `tests/test_product_opinions.py` | Os critérios da [spec 001](../specs/001-opinioes-por-produto.md): listas fechadas iguais na extração, nas expectations e nos contratos, e extração uma única vez por avaliação |

## Estrutura do repositório

```text
.
├── databricks.yml                      # Bundle: variáveis e targets (dev / ci / prod)
├── resources/                          # Definição dos recursos Databricks
│   ├── bakehouse.schemas.yml
│   ├── bakehouse.pipeline.yml
│   ├── bakehouse.job.yml
│   └── bakehouse.dashboard.yml
├── src/
│   ├── pipelines/bakehouse/transformations/
│   │   ├── bronze/                     # 5 tabelas de ingestão
│   │   ├── silver/                     # 5 tabelas limpas
│   │   └── gold/                       # 7 marts
│   ├── dashboards/bakehouse_sales.lvdash.json
│   ├── mcp_server/                     # Servidor MCP bakehouse, ver docs/mcp.md
│   └── jobs/
│       ├── enforce_data_contracts.py   # Confere tabelas publicadas x contratos (tarefa do job)
│       ├── publish_metric_views.py     # Publica a camada semântica (tarefa do job)
│       └── publish_genie_space.py      # Cria/atualiza o Genie space (tarefa do job)
├── semantic/gold/sales_metrics.yaml    # Metric view de vendas, ver semantic/README.md
├── genie/                              # Genie spaces versionados, ver genie/README.md
├── contracts/                          # Contratos de dados (ODCS v3), ver contracts/README.md
│   ├── silver/                         # transactions, review_product_opinions
│   └── gold/                           # 1 contrato por mart
├── tests/                              # Testes offline (ver tabela acima)
├── docs/                               # Esta documentação
├── .claude/                            # Guardrails do agente de IA (permissões e hook)
├── AGENTS.md                           # Instruções para agentes de IA
├── .mcp.json                           # Registro do servidor MCP no Claude Code
└── .github/workflows/databricks.yml    # Pipeline de CI/CD
```

## Convenções do projeto

- **Catálogo nunca fixo no código:** vem sempre de `${var.catalog}`, definido por target em `databricks.yml`.
- **Nomes de schema** vêm de `resources/bakehouse.schemas.yml` e chegam ao SQL pela configuração do pipeline
  (`${medallion_catalog}`, `${bronze_schema}`, `${silver_schema}`, `${gold_schema}`).
- **SQL sem `USE CATALOG`/`USE SCHEMA`:** todas as tabelas são totalmente qualificadas.
- **Fonte somente leitura:** apenas a bronze lê `samples.bakehouse`.
- **Dashboard** usa nomes de tabela sem catálogo/schema; ambos são injetados pelo bundle.
- **Contrato antes do SQL:** toda tabela gold tem um contrato em `contracts/`, e o SQL declara o schema
  explícito do contrato. Mudou a tabela, mudou o contrato (com versão).
- **Métrica tem um só dono:** receita, pedidos, ticket médio e afins vêm de `gold.sales_metrics`
  (`MEASURE()`), e não são recalculados em cada consulta.

Essas regras são verificadas automaticamente pelos testes.
