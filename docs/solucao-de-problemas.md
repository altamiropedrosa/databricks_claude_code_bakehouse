# Solução de problemas

Problemas encontrados ao longo do desenvolvimento e da operação do projeto, com a causa e a solução.

| Sintoma | Causa provável | Solução |
|---|---|---|
| `invalid_client` / `cannot configure default credentials` no CI | Client ID ou secret incorretos, ou secret criado sem o escopo `all-apis` | Gere um novo secret com escopo `all-apis` e atualize `DATABRICKS_CLIENT_SECRET` |
| `User does not have CREATE SCHEMA and USE CATALOG` no deploy | Service principal sem permissão no catálogo | Aplique o `GRANT` da [configuração de produção](ci-cd.md#configuração-do-ambiente-de-produção) |
| Dashboard sem dados após o primeiro deploy | O pipeline ainda não rodou | Execute `databricks bundle run bakehouse_medallion_job -t <target>` |
| Deploy parado em *Waiting* | Aguardando aprovação do environment `prod` | Aprove em *Actions → run → Review deployments* |
| Deploy parado em *Pending*, sem pedir aprovação | Uma execução mais antiga ainda aguarda aprovação e segura a fila `deploy-prod` | Rejeite a aprovação da execução antiga; a mais nova segue para aprovação |
| Deploy falha com `Deploy abortado: commits antigos nunca vao para prod` | O run é de um commit que não é mais a ponta da `master` (ex.: *Re-run* de execução antiga) | Comportamento esperado: nada foi publicado. Use o run do commit mais recente; não faça *Re-run* de execuções antigas |
| Job falha em `enforce_data_contracts` | O que foi publicado não bate com o contrato (schema, chave duplicada ou tabela atrasada) | O log da tarefa lista cada violação; corrija o SQL ou atualize o contrato (com versão) |
| Gráficos de vendas sem dados após um deploy | A metric view ainda não existe no target (só é criada quando o job roda) | Execute o job do target logo após o deploy |
| `METRIC_VIEW_INVALID_VIEW_DEFINITION` ao testar a metric view manualmente | `databricks experimental aitools tools query` altera a indentação de textos com várias linhas | Teste o `CREATE ... WITH METRICS` no SQL editor ou pela Statement Execution API |
| Mudança feita na interface do Genie sumiu | O job republica o Genie a partir de `genie/*.yaml` | Altere o YAML e publique |
