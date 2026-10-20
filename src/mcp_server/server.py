"""MCP server 'bakehouse': read-only tools over the governed layer of this project (specs/002-servidor-mcp.md).

Run by MCP clients through .mcp.json (stdio). The bundle target comes from BAKEHOUSE_TARGET (default: dev)
and Databricks authentication from the SDK unified auth (CLI profile or environment), with the
permissions of whoever runs the server. Queries are built in queries.py; this module only executes them.
"""

import os
import sys
import time

# src/ is scanned as text by tests/test_bundle_conventions.py: never leave .pyc files in it.
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import queries
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

TARGET = os.environ.get("BAKEHOUSE_TARGET", "dev")
TIMEOUT_SECONDS = 120
READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)

server = MCPServer(
    name="bakehouse",
    instructions=(
        "Read-only access to the Bakehouse lakehouse through its governed definitions: the sales metric view, "
        "the gold marts with data contracts and the contracts themselves. There is no free SQL: pick measures "
        "and dimensions from the lists the tools accept. Values such as product or reason are in English."
    ),
)

_client = None
_warehouse_id = None


def _workspace():
    global _client, _warehouse_id
    if _client is None:
        from databricks.sdk import WorkspaceClient

        _client = WorkspaceClient()
        name = queries.warehouse_name()
        matches = [w.id for w in _client.warehouses.list() if w.name == name]
        if not matches:
            raise RuntimeError(f"SQL warehouse '{name}' not found")
        _warehouse_id = matches[0]
    return _client, _warehouse_id


def _execute(query: queries.Query) -> dict:
    from databricks.sdk.service.sql import Disposition, Format, StatementParameterListItem, StatementState

    client, warehouse_id = _workspace()
    response = client.statement_execution.execute_statement(
        statement=query.sql,
        warehouse_id=warehouse_id,
        parameters=[StatementParameterListItem(name=n, type=t, value=v) for n, (t, v) in query.parameters.items()],
        disposition=Disposition.INLINE,
        format=Format.JSON_ARRAY,
        row_limit=query.limit,
        wait_timeout="30s",
    )
    deadline = time.monotonic() + TIMEOUT_SECONDS
    while response.status.state in (StatementState.PENDING, StatementState.RUNNING):
        if time.monotonic() > deadline:
            client.statement_execution.cancel_execution(response.statement_id)
            raise TimeoutError(f"query cancelled after {TIMEOUT_SECONDS} s; aggregate with fewer dimensions")
        time.sleep(2)
        response = client.statement_execution.get_statement(response.statement_id)
    if response.status.state != StatementState.SUCCEEDED:
        error = response.status.error.message if response.status.error else response.status.state.value
        raise RuntimeError(f"query failed: {error}")
    columns = [c.name for c in response.manifest.schema.columns]
    rows = (response.result.data_array or []) if response.result else []
    return {"catalog": queries.target_catalog(TARGET), "columns": columns, "rows": rows}


@server.tool(annotations=READ_ONLY)
def query_sales_metrics(
    measures: list[str],
    dimensions: list[str] | None = None,
    franchise_country: str | None = None,
    franchise_name: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 100,
) -> dict:
    """Sales metrics from the governed metric view gold.sales_metrics, aggregated with MEASURE().

    measures: one or more of revenue, orders, units_sold, avg_ticket, units_per_order, unique_customers,
    active_franchises. Ratios such as avg_ticket are recomputed correctly at any grain.
    dimensions: zero or more of the metric view dimensions, e.g. franchise_country, franchise_name, product,
    payment_method, transaction_date, transaction_month, transaction_weekday, transaction_hour.
    Optional filters: franchise_country, franchise_name, date_from and date_to (YYYY-MM-DD).
    """
    catalog = queries.target_catalog(TARGET)
    return _execute(
        queries.sales_metrics(
            catalog, measures, dimensions, franchise_country, franchise_name, date_from, date_to, limit
        )
    )


@server.tool(annotations=READ_ONLY)
def get_product_opinions(
    franchise_name: str | None = None,
    country: str | None = None,
    opinion: str = "negative",
    limit: int = 50,
) -> dict:
    """What customers praise or criticize in each product, and why, extracted from reviews with AI.

    Returns product, reason (taste, texture, freshness, price, availability, other) and mention counts,
    sorted by the chosen opinion: negative (default), positive or neutral. Filter by franchise_name or country.
    """
    catalog = queries.target_catalog(TARGET)
    return _execute(queries.product_opinions(catalog, franchise_name, country, opinion, limit))


@server.tool(annotations=READ_ONLY)
def get_franchise_sentiment(country: str | None = None, order: str = "worst", limit: int = 10) -> dict:
    """Review sentiment per franchise: net_sentiment from -1 (all negative) to 1 (all positive).

    order: worst (default) or best first. Optional country filter.
    """
    catalog = queries.target_catalog(TARGET)
    return _execute(queries.franchise_sentiment(catalog, country, order, limit))


@server.tool(annotations=READ_ONLY)
def describe_data_contract(table: str | None = None) -> dict:
    """The data contract of a published table: purpose, columns, primary key, owner, SLA and version.

    table: '<layer>.<table>', e.g. gold.sales_by_country. Without it, lists every table with a contract.
    Read from the repository, without querying Databricks.
    """
    return queries.describe_contract(table)


if __name__ == "__main__":
    queries.target_catalog(TARGET)  # fail fast on an unknown target
    server.run("stdio")
