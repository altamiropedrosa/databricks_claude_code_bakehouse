# 002 · Servidor MCP da camada governada

| | |
|---|---|
| **Status** | Aprovada |
| **Autor** | Altamiro Pedrosa |
| **Data** | 20/10/2026 (proposta e aprovação, PR #22) |
| **Implementação** | A definir, depois da aprovação |

## 1. Problema

Hoje, um agente de IA que trabalha neste repositório (como o Claude Code) só alcança os dados de duas
formas: escrevendo SQL livre pela CLI ou abrindo o Genie no navegador. No primeiro caso, ele pode reinventar
fórmulas (por exemplo, calcular o ticket médio como média de médias), ler colunas de dado pessoal ou consultar
o catálogo errado. No segundo, o Genie não fica disponível como ferramenta dentro do fluxo de desenvolvimento.

O projeto já tem as regras de negócio governadas, mas nenhum agente consegue usá-las de forma direta e segura:
a metric view `gold.sales_metrics`, os marts gold com contrato e os contratos em `contracts/`.

## 2. Objetivo

Expor a camada governada como um **servidor MCP** (Model Context Protocol) versionado neste repositório. Com
ele, qualquer cliente MCP consulta vendas, satisfação e contratos **pelas mesmas definições** do dashboard e do
Genie, somente leitura e sem SQL livre.

## 3. Contexto verificado

Verificado no repositório e no workspace em 20/10/2026.

- Nenhum servidor MCP está configurado no projeto (não existe `.mcp.json`) nem no Claude Code do autor. Todo o
  acesso ao Databricks feito até aqui foi pela CLI.
- O hook `.claude/hooks/block_destructive.py` já intercepta ferramentas `mcp__databricks__*`, mas só por
  prevenção.
- A metric view `gold.sales_metrics` tem 13 dimensões (`transaction_date`, `transaction_month`,
  `transaction_weekday`, `transaction_hour`, `product`, `payment_method`, `franchise_id`, `franchise_name`,
  `franchise_city`, `franchise_country`, `franchise_size`, `customer_country`, `customer_continent`) e 7 medidas
  (`revenue`, `orders`, `units_sold`, `avg_ticket`, `units_per_order`, `unique_customers`, `active_franchises`).
- Os contratos marcam como dado pessoal (`classification: restricted`) as colunas `customer_name` e
  `card_last4`.
- O SDK Python do Databricks (`databricks-sdk`) já é dependência de desenvolvimento. O SDK Python do MCP
  (`mcp`) ainda não.

## 4. Escopo

**Dentro**
- Um servidor MCP local (transporte stdio), em Python, com 4 ferramentas somente leitura.
- Registro no `.mcp.json` do projeto, para que quem clonar o repositório já tenha o servidor disponível.
- Guardrails, testes offline e documentação.

**Fora**
- Ferramentas que escrevem dados ou executam SQL livre (decisão Q3).
- Publicar o servidor como Databricks App, para acesso remoto (decisão Q5).
- Conectar os servidores MCP gerenciados do Databricks, como o do Genie: pode virar uma spec própria.

## 5. Requisitos funcionais

Nomes e descrições das ferramentas ficam em inglês, como o código do projeto (decisão Q4). Todas devolvem
dados tabulares com as colunas nomeadas e o catálogo consultado.

**RF1 · `query_sales_metrics`:** consulta a metric view `gold.sales_metrics` com `MEASURE()`.
- Entradas: medidas (uma ou mais), dimensões (zero ou mais), filtros opcionais por país da franquia, nome da
  franquia e intervalo de datas, e limite de linhas.
- Medidas e dimensões só são aceitas se existirem em `semantic/gold/sales_metrics.yaml`. O servidor lê essa
  lista do arquivo, sem cópia no código.

**RF2 · `get_product_opinions`:** opiniões por produto de `gold.product_opinions_by_franchise` (spec 001).
- Entradas opcionais: franquia, país e opinião (`negative` por padrão).
- Devolve produto, motivo e contagens, das mais citadas para as menos citadas.

**RF3 · `get_franchise_sentiment`:** sentimento por franquia de `gold.sentiment_by_franchise`.
- Entradas opcionais: país, ordem (piores ou melhores primeiro) e quantidade de franquias.

**RF4 · `describe_data_contract`:** descreve o contrato de uma tabela publicada, lido de `contracts/`, sem
acessar o Databricks.
- Entrada: a tabela (`gold.sales_by_country`, por exemplo). Sem entrada, lista as tabelas com contrato.
- Devolve finalidade, colunas com tipo e descrição, chave, dono, SLA e versão.

## 6. Requisitos não funcionais

- **RNF1 · Somente leitura e sem SQL livre:** cada ferramenta monta uma única consulta `SELECT` a partir de
  entradas validadas por listas de permissão. Valores de filtro vão como parâmetros da Statement Execution API,
  nunca concatenados no texto.
- **RNF2 · Catálogo nunca fixo:** o servidor recebe o **target** do bundle (`dev`, `ci` ou `prod`) e lê o
  catálogo correspondente em `databricks.yml`. O teste de convenções existente, que procura catálogos fixos em
  `src/`, passa a cobrir o servidor.
- **RNF3 · Sem dado pessoal:** nenhuma ferramenta devolve coluna marcada como `restricted` nos contratos. A
  lista vem dos contratos, sem cópia no código.
- **RNF4 · Autenticação do Databricks:** o servidor usa a autenticação unificada do SDK (perfil da CLI), com as
  permissões de quem o executa. Nenhum segredo vai para o repositório.
- **RNF5 · Guardrail:** o hook de segurança passa a interceptar também as ferramentas do servidor novo.
- **RNF6 · Limites:** no máximo 1.000 linhas por resposta e tempo limite por consulta, com erro claro quando
  excedido.
- **RNF7 · Reprodutível:** `uv sync` instala tudo; nenhuma instalação manual além do que o README descreve.

## 7. Critérios de aceite

| Nº | Critério | Como verificar |
|---|---|---|
| CA1 | Depois de `uv sync`, o Claude Code lista o servidor como conectado e mostra as 4 ferramentas | `claude mcp list` e sessão registrada na seção 11 |
| CA2 | `query_sales_metrics` devolve a mesma receita total e o mesmo ticket médio por país que a metric view consultada direto | Comparação registrada na seção 11 |
| CA3 | `get_product_opinions` para a Tokyo Treats devolve as mesmas contagens que a gold | Comparação registrada na seção 11 |
| CA4 | Medida, dimensão, tabela ou filtro fora das listas de permissão é rejeitado antes de chegar ao Databricks, inclusive tentativas de injeção (`revenue; DROP TABLE ...`) | Testes offline |
| CA5 | Toda consulta gerada é um único `SELECT`, sem catálogo fixo e com os filtros como parâmetros | Testes offline |
| CA6 | Nenhuma ferramenta consegue devolver `customer_name` ou `card_last4` | Testes offline, com a lista lida dos contratos |
| CA7 | O hook de segurança intercepta as ferramentas do servidor | Teste offline sobre `.claude/settings.json` |
| CA8 | Numa sessão real, o Claude Code responde *"Por que a Tokyo Treats é mal avaliada e quanto ela faturou?"* combinando duas ferramentas, sem escrever SQL | Sessão registrada na seção 11 |
| CA9 | CI verde: lint, testes offline e execução completa no target `ci` | GitHub Actions |

## 8. Decisões técnicas propostas

- **SDK oficial do MCP para Python (`mcp`, com FastMCP)**, transporte stdio: é o padrão para servidores
  locais e funciona com qualquer cliente MCP, não só com o Claude Code.
- **Statement Execution API do `databricks-sdk`** no warehouse que o bundle já usa (*Serverless Starter
  Warehouse*, resolvido por nome): não exige cluster nem Databricks Connect.
- **Listas de permissão lidas dos arquivos governados** (`semantic/` e `contracts/`): uma medida nova na metric
  view fica disponível no servidor sem mudar o código, e um dado pessoal novo marcado no contrato fica
  bloqueado automaticamente.
- **Código em `src/mcp_server/`**, com a lógica de montagem das consultas separada do transporte MCP, para ser
  testável offline.
- **Dependências num grupo próprio** do `pyproject.toml`, instalado pelo `uv sync`.

## 9. Riscos

| Risco | Mitigação |
|---|---|
| O agente pede uma combinação de dimensões que gera muitas linhas | Limite de linhas (RNF6) e mensagem orientando a agregar mais |
| Permissão diferente entre quem roda o servidor e o service principal | O servidor usa as permissões do usuário; a documentação explica o acesso necessário |
| O target `prod` exposto a um agente | Somente leitura, sem SQL livre e com guardrail; o target padrão é `dev` (decisão Q2) |
| Mudança na API do SDK do MCP | Versão fixada no `uv.lock` |

## 10. Decisões da revisão

| Questão | Decisão |
|---|---|
| **Q1 · Nome do servidor:** `bakehouse`, com as ferramentas aparecendo como `mcp__bakehouse__*` no Claude Code? | `bakehouse`. O hook de segurança passa a cobrir o prefixo `mcp__bakehouse__` |
| **Q2 · Target padrão:** `dev` (menor privilégio) ou `prod` (dados mais completos)? | `dev`. O `prod` fica disponível só por configuração explícita |
| **Q3 · SQL livre somente leitura:** incluir uma quinta ferramenta para SQL livre? | Não. O servidor consulta só pelas definições governadas |
| **Q4 · Idioma das ferramentas:** nomes e descrições em inglês? | Inglês, como o código. As respostas aos usuários ficam a cargo do cliente |
| **Q5 · Databricks App (MCP remoto):** publicar como app agora ou numa spec futura? | Spec futura |

## 11. Resultado

*Preenchido depois da implementação.*
