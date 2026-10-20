# Contratos de dados

Cada tabela publicada tem um contrato em `contracts/<camada>/<tabela>.yaml`, no formato
[Open Data Contract Standard (ODCS) v3](https://bitol-io.github.io/open-data-contract-standard/).
O contrato é a **interface pública** da tabela: colunas, tipos, obrigatoriedade, chave, significado de
cada coluna, regras de qualidade, dono e prazo de atualização.

Hoje há contrato para todas as tabelas **gold** (obrigatório), para `silver.transactions`, que é a
base da camada semântica, e para `silver.review_product_opinions`, extraída com IA.

## Como o contrato é aplicado

| Onde | O que garante |
|---|---|
| SQL do pipeline | O `CREATE OR REFRESH` declara o schema explícito: tipo, `NOT NULL` (= `required: true`) e `COMMENT` (= `description`) de cada coluna. O Unity Catalog passa a mostrar a documentação do contrato. |
| Expectations | Os `CONSTRAINT ... EXPECT` do SQL espelham a seção `quality` (`engine: lakeflow`). `onViolation`: `warn`, `drop_row` ou `fail_update`. |
| `tests/test_data_contracts.py` (CI, offline) | Toda tabela gold tem contrato; SQL e contrato declaram as mesmas colunas, tipos, `NOT NULL`, comentários e expectations; regras de versão abaixo. |
| Tarefa `enforce_data_contracts` do job (após cada execução do pipeline) | Confere o que **foi publicado**: schema no Unity Catalog igual ao contrato, chave primária sem duplicatas e atualização dentro do `latency` do SLA. Aplica as tags `data_contract`/`data_contract_version` na tabela e `classification` nas colunas com dado pessoal. Qualquer violação falha a execução do job. |

Para rodar só a verificação, sem gravar tags: `src/jobs/enforce_data_contracts.py --catalog <catálogo> --contracts-dir <pasta> --skip-tags`.

`physicalName` nunca leva o catálogo (`gold.top_customers`): o catálogo vem do target do bundle.

## Versionamento (SemVer)

A versão é comparada com a do `origin/master` (variável `CONTRACTS_BASE_REF` para outra base).

| Mudança | Exemplo | Versão |
|---|---|---|
| **Incompatível** | remover coluna, mudar tipo, coluna deixa de ser `required`, mudar chave primária | **MAJOR** (`1.2.0` → `2.0.0`) |
| Compatível | nova coluna, nova regra de qualidade | MINOR (`1.2.0` → `1.3.0`) |
| Documentação | descrição, uso, limitações | PATCH (`1.2.0` → `1.2.1`) |

- Mudança incompatível em tabela usada por terceiros: prefira publicar uma tabela nova (`<tabela>_v2`)
  e marcar a antiga como `deprecated`, com prazo para os consumidores migrarem.
- Um contrato só pode ser removido depois de estar `deprecated` ou `retired` no `master`.

## Obrigatoriedade (`required`)

`required: true` é uma **promessa** e vira `NOT NULL` na tabela: se um valor nulo aparecer, a
atualização do pipeline falha. Marque como obrigatória só a coluna que a lógica do SQL garante
(chave filtrada por expectation `drop_row`, `count(*)`, `coalesce(..., 0)`, data derivada de coluna
obrigatória), e não a que apenas não tem nulos nos dados de hoje.

## Como alterar uma tabela com contrato

1. Edite o contrato e suba a versão conforme a tabela acima.
2. Ajuste o SQL para declarar as mesmas colunas, tipos, `NOT NULL` e comentários.
3. `DATABRICKS_SKIP_CONNECT=1 uv run pytest tests/test_data_contracts.py` aponta qualquer divergência.
4. Publique e rode o pipeline em dev antes de abrir o PR.
