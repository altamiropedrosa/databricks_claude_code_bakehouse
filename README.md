# Bakehouse Lakehouse

🇧🇷 Português · [🇺🇸 English](README.en.md)

**Lakehouse de ponta a ponta no Databricks: da ingestão à pergunta em linguagem natural, com IA generativa,
contratos de dados e CI/CD, tudo declarado como código e desenvolvido com agentes de IA a partir de especificações.**

[![Databricks CI/CD](https://github.com/altamiropedrosa/databricks_claude_code_bakehouse/actions/workflows/databricks.yml/badge.svg)](https://github.com/altamiropedrosa/databricks_claude_code_bakehouse/actions/workflows/databricks.yml)
![Databricks](https://img.shields.io/badge/Databricks-Lakeflow%20%7C%20Unity%20Catalog-FF3621?logo=databricks&logoColor=white)
![SQL](https://img.shields.io/badge/SQL-pipeline-4479A1?logo=databricks&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![MCP](https://img.shields.io/badge/MCP-servidor%20pr%C3%B3prio-1B3139)
![GitHub Actions](https://img.shields.io/badge/GitHub%20Actions-CI%2FCD-2088FF?logo=githubactions&logoColor=white)
[![Licença: MIT](https://img.shields.io/badge/licen%C3%A7a-MIT-5A6F77)](LICENSE)

![Dashboard AI/BI Bakehouse Lakehouse - Vendas e Satisfação](docs/images/dashboard.png)

Pipeline em **arquitetura medalhão** (bronze → silver → gold) sobre o dataset de exemplo `samples.bakehouse`,
uma rede fictícia de padarias. As avaliações dos clientes são lidas por **IA generativa**, que diz não só se o
cliente gostou, mas **de qual produto e por quê**. As métricas de negócio têm uma **definição única**, e qualquer
gestor pode perguntar em português *"por que as avaliações desta franquia são negativas?"* e receber a resposta
direto dos dados.

## Em números

| 17 | 9 | 213 | 3 | 3 | 25 |
|:---:|:---:|:---:|:---:|:---:|:---:|
| tabelas no pipeline | contratos de dados | testes automatizados | ambientes (dev, ci, prod) | especificações (SDD) | pull requests revisados |

## Em resumo

- **Pipeline declarativo serverless** (Lakeflow) com 17 tabelas em três camadas, escrito em SQL.
- **IA generativa nos dados:** sentimento das avaliações (`ai_analyze_sentiment`) e **opinião por produto**
  (`ai_extract`): qual produto foi criticado e por quê. Cada avaliação vai ao modelo **uma única vez**.
- **Contratos de dados** (ODCS v3) cobrados no pull request e após cada execução em produção.
- **Camada semântica** (metric view) com as métricas de vendas, compartilhada pelo dashboard, pelo Genie e pelo
  servidor MCP.
- **Dashboard AI/BI** e **Genie space** para perguntas em linguagem natural.
- **Servidor MCP próprio:** agentes de IA consultam os dados pelas regras governadas, somente leitura e sem SQL livre.
- **Spec-Driven Development:** cada funcionalidade nova começa por uma especificação com critérios de aceite,
  aprovada antes do código e medida depois da entrega.
- **CI/CD com GitHub Actions:** testes offline, ambiente de integração, aprovação manual e deploy em produção
  por um service principal.
- **Tudo como código** com Declarative Automation Bundles (DABs): schemas, pipeline, job, contratos, métricas,
  dashboard e Genie são promovidos entre ambientes trocando apenas o catálogo.

## O que este projeto demonstra

| Competência | Como aparece aqui | Onde ver |
|---|---|---|
| Engenharia de dados | Medalhão com streaming tables e materialized views, ingestão incremental, expectations de qualidade | [`src/pipelines/`](src/pipelines/bakehouse/transformations), [camadas de dados](docs/camadas-de-dados.md) |
| IA generativa aplicada | Sentimento e opinião por produto extraídos das avaliações com AI Functions em SQL; Genie respondendo em linguagem natural sobre métricas governadas | [`reviews_sentiment.sql`](src/pipelines/bakehouse/transformations/silver/reviews_sentiment.sql), [`review_product_opinions.sql`](src/pipelines/bakehouse/transformations/silver/review_product_opinions.sql), [`genie/`](genie/README.md) |
| Qualidade e governança | Contratos ODCS v3 com SemVer, tags de dado pessoal no Unity Catalog, mascaramento do cartão | [`contracts/`](contracts/README.md) |
| Modelagem analítica | Marts gold aditivos e metric view com dimensões e medidas reutilizáveis | [`semantic/`](semantic/README.md) |
| DevOps / DataOps | Infraestrutura como código, três ambientes, gate de integração, deploy com aprovação | [`databricks.yml`](databricks.yml), [CI/CD](docs/ci-cd.md) |
| Testes automatizados | Mais de 200 testes offline cobrando convenções, contratos, camada semântica, opiniões por produto e servidor MCP | [`tests/`](tests), [desenvolvimento](docs/desenvolvimento.md#testes) |
| Spec-Driven Development | Specs com evidências dos dados, critérios de aceite e decisões de revisão, aprovadas antes do código; resultados medidos em dev e em produção | [`specs/`](specs/README.md) |
| Model Context Protocol (MCP) | Servidor MCP próprio que expõe a camada governada a agentes de IA, somente leitura e sem SQL livre | [Servidor MCP](#servidor-mcp-para-agentes-de-ia), [`src/mcp_server/`](src/mcp_server) |
| Desenvolvimento com IA | Agente de IA como par de programação, com guardrails, skills, hooks e revisão humana antes de cada entrega | [Desenvolvimento assistido por IA](#desenvolvimento-assistido-por-ia) |

## Arquitetura

```mermaid
flowchart LR
    src[("samples.bakehouse<br/>(somente leitura)")]

    subgraph pipeline["Lakeflow Declarative Pipeline (serverless)"]
        direction LR
        bronze["🥉 bronze<br/>ingestão bruta"]
        silver["🥈 silver<br/>limpeza, tipos, qualidade<br/>+ ai_analyze_sentiment<br/>+ ai_extract"]
        gold["🥇 gold<br/>marts para BI"]
        bronze --> silver --> gold
    end

    src --> bronze
    contracts{{"📜 Contratos de dados<br/>schema · chave · prazo"}}
    silver & gold -. verificadas por .-> contracts
    silver --> mv["📐 Metric view<br/>gold.sales_metrics"]
    mv --> dash["📊 Dashboard AI/BI<br/>Vendas e Satisfação"]
    gold --> dash
    mv --> genie["💬 Genie space<br/>Vendas e Satisfação"]
    gold --> genie
    agents["🤖 Agentes de IA<br/>(Claude Code)"] --> mcp["🔌 Servidor MCP<br/>bakehouse"]
    mcp --> mv
    mcp --> gold
    mcp -.-> contracts
    job["⏰ Job diário 06:00<br/>America/Sao_Paulo"] -. dispara .-> pipeline
```

O job diário encadeia quatro tarefas: **pipeline → verificação dos contratos → metric views → Genie**.
Se um contrato for violado, o job para ali e as métricas não são republicadas com dados fora do padrão.

| Camada | Tabelas | Papel |
|---|---|---|
| 🥉 Bronze | 5 streaming tables | Cópia fiel e incremental da origem, com metadados de ingestão. Única camada que lê `samples.bakehouse` |
| 🥈 Silver | 3 materialized views + 2 streaming tables | Tipos, padronização, enriquecimento, expectations de qualidade, sentimento e opiniões por IA |
| 🥇 Gold | 7 marts | Vendas por dia, produto e país, desempenho, sentimento e opiniões por franquia, ranking de clientes |

Detalhe de cada tabela em [docs/camadas-de-dados.md](docs/camadas-de-dados.md).

## O que os dados mostram

Números de produção, nas vendas de 1 a 17 de maio de 2024 e nas 204 avaliações dos clientes:

- **Dois mercados concentram a receita.** Japão e Estados Unidos somam 64% dos 66.471 faturados (3.333 pedidos,
  ticket médio de 19,94).
- **A satisfação é o ponto fraco:** 42% das avaliações são negativas, e só 25% são positivas. A pior franquia é a
  Tokyo Treats, em Tóquio, com sentimento líquido de -0,50.
- **O problema principal é o sabor de dois produtos.** Golden Gate Ginger (73 críticas) e Orchard Oasis (72) são os
  mais criticados, quase sempre pelo sabor.
- **Outros dois produtos têm problema de sabor e de textura ao mesmo tempo.** Austin Almond Biscotti e Outback
  Oatmeal dividem as críticas entre os dois motivos (por exemplo, "seco e quebradiço").

Os dados são sintéticos, e a extração por IA não é determinística. A [spec 001](specs/001-opinioes-por-produto.md)
registra a qualidade medida e as limitações.

## IA nos dados

**Sentimento das avaliações.** A tabela `silver.reviews_sentiment` classifica cada avaliação como `positive`,
`negative`, `neutral` ou `mixed` com a AI Function `ai_analyze_sentiment`, direto no SQL do pipeline, sem
endpoint de modelo para manter. A gold agrega o resultado em um `net_sentiment` ∈ [-1, 1] por franquia.

**Por que o sentimento é ruim.** A tabela `silver.review_product_opinions` usa `ai_extract` para tirar de cada
avaliação **qual produto foi elogiado ou criticado e por qual motivo** (sabor, textura, frescor, preço,
disponibilidade). O dashboard mostra o produto mais criticado de cada franquia, e o Genie responde perguntas como
*"Por que as avaliações da Tokyo Treats são negativas?"*. A funcionalidade nasceu de uma
[especificação aprovada antes do código](specs/001-opinioes-por-produto.md), com critérios de aceite medidos.

![Seção "O que os clientes criticam" do dashboard: críticas por produto e motivo, e o produto mais criticado de cada franquia](docs/images/opinioes.png)

**Perguntas em linguagem natural.** O Genie space *Bakehouse Lakehouse - Vendas e Satisfação* responde em português
perguntas como *"Quais franquias têm o pior sentimento nas avaliações?"*. Ele consulta a metric view, então
a IA usa as **mesmas definições de receita e ticket médio** do dashboard em vez de inventar o próprio cálculo.
A configuração (instruções, perguntas de exemplo, tabelas) é versionada em YAML e publicada pelo job.

![Genie respondendo em português quais franquias têm o pior sentimento nas avaliações](docs/images/genie.svg)

## Servidor MCP para agentes de IA

O servidor [MCP](https://modelcontextprotocol.io) `bakehouse` ([docs/mcp.md](docs/mcp.md)) deixa qualquer agente de
IA, como o Claude Code, consultar os dados **pelas mesmas definições do dashboard e do Genie**: vendas pela metric
view, opiniões e sentimento pelos marts gold e contratos pelos arquivos versionados. Ele é somente leitura e não
aceita SQL livre: medidas, dimensões e colunas vêm de listas de permissão lidas de `semantic/` e `contracts/`, os
valores viajam como parâmetros e dado pessoal nunca sai. Quem clona o repositório já o recebe configurado em
[`.mcp.json`](.mcp.json). Nasceu da [spec 002](specs/002-servidor-mcp.md) e foi verificado em dev e em produção
com sessões reais do Claude Code respondendo só com as ferramentas do servidor.

## Qualidade e governança

Cada tabela publicada tem um **contrato de dados** no formato
[Open Data Contract Standard (ODCS) v3](https://bitol-io.github.io/open-data-contract-standard/), com colunas,
tipos, chave primária, classificação de dado pessoal, dono e SLA (atualização diária, no máximo 26 h).

| Quando | O que garante |
|---|---|
| No pull request (CI, offline) | O SQL declara exatamente as colunas, tipos, `NOT NULL`, comentários e expectations do contrato; mudança incompatível exige versão MAJOR |
| Na tabela | Colunas obrigatórias são `NOT NULL`: um nulo inesperado falha o pipeline em vez de chegar ao dashboard |
| Após cada execução | O que **foi publicado** bate com o contrato (schema, chave sem duplicatas, prazo); tags `data_contract` e `classification` aplicadas no Unity Catalog |

A **camada semântica** `gold.sales_metrics` define uma única vez 13 dimensões e 7 medidas de vendas, e nunca
expõe colunas de dado pessoal (verificado no CI):

```sql
SELECT franchise_country, MEASURE(revenue) AS receita, MEASURE(avg_ticket) AS ticket_medio
FROM bakehouse_prod.gold.sales_metrics
GROUP BY ALL;
```

Mais em [contracts/README.md](contracts/README.md) e [semantic/README.md](semantic/README.md).

## CI/CD e ambientes

```mermaid
flowchart LR
    pr["Pull request"] --> test["lint + pytest"] --> ci["deploy + execução<br/>completa no target ci"]
    merge["Merge na master"] --> test2["lint + pytest"] --> ci2["deploy + execução<br/>completa no target ci"] --> approve{{"Aprovação<br/>manual"}} --> deploy["deploy em prod<br/>(service principal)"]
```

| | `dev` | `ci` | `prod` |
|---|---|---|---|
| Catálogo | `bakehouse_dev` | `bakehouse_ci` | `bakehouse_prod` |
| Deploy | Desenvolvedor, pela CLI | GitHub Actions | GitHub Actions, após aprovação |
| Agendamento | Pausado | Pausado (o CI dispara) | Diário, 06:00 |

Ninguém publica em produção pela própria máquina: o deploy é feito pelo CI, como service principal com OAuth
M2M, só depois de o job inteiro passar no ambiente de integração e de uma aprovação manual. Detalhes em
[docs/ci-cd.md](docs/ci-cd.md).

## Decisões técnicas

| Decisão | Por quê |
|---|---|
| Sentimento e opiniões em **streaming tables**, não materialized views | Cada avaliação é enviada à IA uma única vez. Uma materialized view poderia reprocessar todas a cada atualização e multiplicar o custo de inferência |
| **Opinião por produto** com `ai_extract`, não temas gerais com `ai_classify` | Testado na exploração: com temas gerais, "textura" aparecia em 100% das avaliações e não explicava nada. Por produto, os padrões ficam acionáveis (ver [spec 001](specs/001-opinioes-por-produto.md)) |
| **O catálogo é a única diferença** entre ambientes | O mesmo SQL roda em dev, ci e prod; promover é trocar uma variável. Testes impedem catálogo fixo no código |
| Target `dev` **sem** `mode: development` | Esse modo prefixa os schemas com o nome do usuário; aqui eles precisam se chamar exatamente `bronze`, `silver` e `gold`. Os benefícios do modo são replicados com *presets* |
| Gate de integração no target `ci` | Ambiente com o mesmo formato de prod (service principal, `run_as`), que roda o job completo antes de qualquer deploy. Erros de permissão ou de dados aparecem no PR, não em produção |
| **Prod nunca volta no tempo** | Depois da aprovação, o deploy confere se o commit ainda é a ponta da `master`. Um *Re-run* antigo aborta em vez de sobrescrever uma versão mais nova |
| Contratos cobrados **antes e depois** | O teste no PR pega o erro cedo e barato; a verificação após a execução pega o que só aparece com dados reais (duplicatas, atraso) |
| **Métrica com um só dono** | Ticket médio calculado como média de médias dá resultado errado ao agregar. A metric view recalcula a razão em qualquer nível, e dashboard, Genie e servidor MCP usam a mesma definição |
| Servidor MCP **sem SQL livre** | O valor do servidor é consultar só pelas definições governadas. Listas de permissão lidas dos arquivos versionados fazem uma medida nova aparecer sem mudar código, e um dado pessoal marcado no contrato ficar bloqueado sozinho (ver [spec 002](specs/002-servidor-mcp.md)) |
| Expectations que **descartam** vs. que **registram** | Linha sem chave ou com valor impossível é descartada; inconsistência tolerável (ex.: total ≠ quantidade × preço) só é medida, sem perder dado |
| Cartão reduzido aos **4 últimos dígitos** já na silver | O dado sensível não chega às camadas consumidas por BI e IA |

## Desenvolvimento assistido por IA

O projeto foi desenvolvido com um agente de IA ([Claude Code](https://claude.com/claude-code)) como par de
programação. A autonomia do agente é limitada por um processo e por guardrails explícitos:

- **Spec-Driven Development** em [`specs/`](specs/README.md): cada funcionalidade nova começa por uma especificação
  com evidências dos dados e critérios de aceite, revisada e aprovada num PR próprio **antes** do código. A
  implementação mede cada critério, e a spec registra o resultado em dev e em produção.
- **Revisão humana antes de cada entrega:** o agente abre os PRs, mas o merge e a aprovação do deploy em produção
  são sempre do autor.
- **Instruções e skills** em [`AGENTS.md`](AGENTS.md): o agente usa as skills do Databricks para seguir o fluxo de
  autenticação, de exploração dos dados e de deploy do bundle.
- **Lista de bloqueios** em [`.claude/settings.json`](.claude/settings.json): o agente não pode destruir o bundle,
  apagar catálogos, schemas ou tabelas, fazer deploy em prod nem `push --force`.
- **Hook de segurança** em [`.claude/hooks/block_destructive.py`](.claude/hooks/block_destructive.py), que
  intercepta todo comando antes de executar e bloqueia `DROP`, `TRUNCATE`, `DELETE FROM` e remoções pela CLI,
  inclusive as chamadas às ferramentas MCP do projeto. Ele falha fechado: na dúvida, bloqueia.
- **Integração via MCP:** o [servidor `bakehouse`](docs/mcp.md) dá ao agente acesso aos dados pelas definições
  governadas, em vez de SQL livre.
- **Testes e CI como rede de segurança:** todo código, gerado ou não, passa por lint, testes offline e
  execução completa no ambiente de integração antes de chegar a produção.

## Stack

**Databricks:** Lakeflow Declarative Pipelines · Lakeflow Jobs · Unity Catalog · AI Functions · Metric Views ·
AI/BI Dashboards · Genie · computação serverless · Declarative Automation Bundles<br/>
**Linguagens:** SQL (pipeline) · Python 3.12 (tarefas do job, servidor MCP e testes)<br/>
**IA:** AI Functions (`ai_analyze_sentiment`, `ai_extract`) · Genie · Model Context Protocol (SDK `mcp`) · Claude Code<br/>
**Qualidade:** Open Data Contract Standard v3 · pytest · ruff<br/>
**Entrega:** GitHub Actions · OAuth M2M com service principal · uv

## Como executar

Pré-requisitos: workspace Databricks com Unity Catalog e serverless, Databricks CLI v1.21.0, uv e Python 3.12.

```bash
databricks auth login --host https://<seu-workspace>.cloud.databricks.com
uv sync --dev
DATABRICKS_SKIP_CONNECT=1 uv run pytest      # testes offline
databricks bundle deploy                     # publica em dev
databricks bundle run bakehouse_medallion_job
```

Para usar o servidor MCP, abra o Claude Code na pasta do projeto e aprove o servidor `bakehouse`
([docs/mcp.md](docs/mcp.md)). Passo a passo completo, estrutura do repositório e convenções em
[docs/desenvolvimento.md](docs/desenvolvimento.md).

## Próximos passos

- **Qualidade da IA com avaliação humana:** a qualidade da extração por produto foi medida numa amostra rotulada
  por outro modelo ([spec 001](specs/001-opinioes-por-produto.md), CA5); falta uma rotulagem humana, também para o
  sentimento.
- **Benchmarks do Genie** versionados, com perguntas e SQL esperado.
- **Metric view de opiniões**, para que Genie e servidor MCP calculem proporções de críticas pela camada semântica.
- **Servidor MCP como Databricks App**, para acesso remoto sem rodar nada na máquina de quem usa.
- Custo por execução a partir das system tables de billing.
- Página de qualidade no dashboard com as métricas das expectations, lidas do event log do pipeline.

## Documentação

| Documento | Conteúdo |
|---|---|
| [specs/](specs/README.md) | Especificações: cada funcionalidade nova começa por uma spec aprovada antes do código |
| [docs/camadas-de-dados.md](docs/camadas-de-dados.md) | Cada tabela das camadas bronze, silver e gold, e o dashboard |
| [docs/desenvolvimento.md](docs/desenvolvimento.md) | Pré-requisitos, desenvolvimento local, testes, estrutura do repositório e convenções |
| [docs/ci-cd.md](docs/ci-cd.md) | Ambientes, fluxo de CI/CD e configuração de produção |
| [docs/mcp.md](docs/mcp.md) | Servidor MCP `bakehouse`: ferramentas, uso com o Claude Code, teste em produção e segurança |
| [docs/solucao-de-problemas.md](docs/solucao-de-problemas.md) | Problemas reais encontrados, com causa e solução |
| [contracts/README.md](contracts/README.md) | Contratos de dados: formato, regras de versão e passo a passo |
| [semantic/README.md](semantic/README.md) | Camada semântica: dimensões, medidas e como evoluir |
| [genie/README.md](genie/README.md) | Genie space: configuração e publicação |

### Referências

[Declarative Automation Bundles](https://docs.databricks.com/dev-tools/bundles/index.html) ·
[Lakeflow Declarative Pipelines](https://docs.databricks.com/aws/en/dlt/) ·
[ODCS](https://bitol-io.github.io/open-data-contract-standard/) ·
[Metric views](https://docs.databricks.com/metric-views/) ·
[Genie](https://docs.databricks.com/genie/) ·
[`ai_analyze_sentiment`](https://docs.databricks.com/aws/en/sql/language-manual/functions/ai_analyze_sentiment) ·
[`ai_extract`](https://docs.databricks.com/sql/language-manual/functions/ai_extract) ·
[Model Context Protocol](https://modelcontextprotocol.io) ·
[OAuth M2M](https://docs.databricks.com/aws/en/dev-tools/auth/oauth-m2m)

## Sobre este projeto

Este projeto faz parte do meu Career Break, dedicado ao estudo de inglês e de **AI-Assisted Engineering**:
desenvolvimento de pipelines de dados e analytics com agentes de IA ([Claude Code](https://claude.com/claude-code)),
usando [Spec-Driven Development](specs/README.md), com especificação e critérios de aceite aprovados antes do
código, planejamento das mudanças, automações com [hooks](.claude/hooks/block_destructive.py) e skills, integrações
via MCP (incluindo um [servidor MCP próprio](docs/mcp.md)) e revisão humana antes de cada entrega.

## Autor

**Altamiro Pedrosa** · [LinkedIn](https://www.linkedin.com/in/altamiropedrosa) · [GitHub](https://github.com/altamiropedrosa)

## Licença

[MIT](LICENSE). O dataset `samples.bakehouse` é um conjunto de exemplo fornecido pelo Databricks.
