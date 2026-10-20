"""Offline checks of the bakehouse MCP server (specs/002-servidor-mcp.md), without Databricks access.

The server is only as safe as the queries it builds: every request must become one SELECT over the
governed layer, with identifiers from the allowlists of semantic/ and contracts/, user values as
parameters, the catalog of the bundle target and no personal data.
"""

import importlib.util
import json
import pathlib
import re
import sys

import pytest
import yaml

ROOT = pathlib.Path(__file__).parent.parent

# Loaded by path (src/ is not a package). No .pyc: test_catalog_name_never_hardcoded reads every file in src/.
_dont_write_bytecode, sys.dont_write_bytecode = sys.dont_write_bytecode, True
_spec = importlib.util.spec_from_file_location("mcp_queries", ROOT / "src" / "mcp_server" / "queries.py")
queries = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(queries)
sys.dont_write_bytecode = _dont_write_bytecode

CATALOG = queries.target_catalog("dev")
INJECTIONS = ["revenue; DROP TABLE x", "revenue --", "MEASURE(revenue)", "revenue) FROM y --", "*"]


def _all_queries() -> list:
    return [
        queries.sales_metrics(CATALOG, ["revenue", "avg_ticket"], ["franchise_country", "product"]),
        queries.sales_metrics(CATALOG, ["orders"], franchise_country="Japan", date_from="2024-05-01"),
        queries.product_opinions(CATALOG, franchise_name="Tokyo Treats"),
        queries.product_opinions(CATALOG, country="Japan", opinion="positive"),
        queries.franchise_sentiment(CATALOG, country="Japan", order="best"),
    ]


# --- CA4: only allowlisted identifiers reach the SQL --------------------------------------------


@pytest.mark.parametrize("bad", INJECTIONS)
def test_unknown_or_injected_measures_are_rejected(bad):
    with pytest.raises(ValueError, match="unknown measures"):
        queries.sales_metrics(CATALOG, [bad])


@pytest.mark.parametrize("bad", INJECTIONS)
def test_unknown_or_injected_dimensions_are_rejected(bad):
    with pytest.raises(ValueError, match="unknown dimensions"):
        queries.sales_metrics(CATALOG, ["revenue"], [bad])


@pytest.mark.parametrize(
    ("call", "message"),
    [
        (lambda: queries.sales_metrics(CATALOG, []), "at least one measure"),
        (lambda: queries.sales_metrics(CATALOG, ["revenue", "revenue"]), "repeated"),
        (lambda: queries.sales_metrics(CATALOG, ["revenue"], limit=0), "limit"),
        (lambda: queries.sales_metrics(CATALOG, ["revenue"], limit=queries.MAX_ROWS + 1), "limit"),
        (lambda: queries.sales_metrics(CATALOG, ["revenue"], date_from="2024-05-01; DROP"), "date_from"),
        (lambda: queries.product_opinions(CATALOG, opinion="negative_mentions; --"), "opinion"),
        (lambda: queries.franchise_sentiment(CATALOG, order="worst; DROP TABLE x"), "order"),
        (lambda: queries.describe_contract("gold.missing"), "no data contract"),
        (lambda: queries.target_catalog("staging"), "unknown bundle target"),
    ],
)
def test_invalid_inputs_are_rejected_before_any_query(call, message):
    with pytest.raises(ValueError, match=message):
        call()


def test_allowlists_come_from_the_metric_view():
    view = yaml.safe_load((ROOT / "semantic" / "gold" / "sales_metrics.yaml").read_text(encoding="utf-8"))
    dimensions, measures = queries.metric_view_fields()
    assert measures == [m["name"] for m in view["measures"]]
    assert set(dimensions) <= {d["name"] for d in view["dimensions"]}


# --- CA5: one SELECT, catalog from the target, values as parameters -----------------------------


@pytest.mark.parametrize("query", _all_queries(), ids=lambda q: q.sql[:40])
def test_every_query_is_a_single_select_on_the_target_catalog(query):
    assert query.sql.startswith("SELECT ") and ";" not in query.sql and "--" not in query.sql
    assert re.findall(r"FROM (\w+)\.gold\.\w+", query.sql) == [CATALOG]
    assert query.limit <= queries.MAX_ROWS and query.sql.endswith(f"LIMIT {query.limit}")


@pytest.mark.parametrize("query", _all_queries(), ids=lambda q: q.sql[:40])
def test_filter_values_are_parameters_never_sql_text(query):
    for name, (_, value) in query.parameters.items():
        assert f":{name}" in query.sql
        assert value not in query.sql


def test_catalog_follows_the_bundle_target():
    targets = yaml.safe_load((ROOT / "databricks.yml").read_text(encoding="utf-8"))["targets"]
    for target, config in targets.items():
        assert queries.target_catalog(target) == config["variables"]["catalog"]


# --- CA6: no personal data ----------------------------------------------------------------------


def test_personal_columns_come_from_the_contracts():
    assert {"customer_name", "card_last4"} <= queries.restricted_columns()


@pytest.mark.parametrize("query", _all_queries(), ids=lambda q: q.sql[:40])
def test_no_query_selects_personal_data(query):
    selected = re.search(r"SELECT (.*?) FROM", query.sql).group(1)
    for column in queries.restricted_columns():
        assert not re.search(rf"\b{column}\b", selected)


def test_personal_columns_can_never_be_requested():
    for column in queries.restricted_columns():
        with pytest.raises(ValueError):
            queries.sales_metrics(CATALOG, ["revenue"], [column])


# --- CA7 and registration -----------------------------------------------------------------------


def test_the_guardrail_hook_covers_the_server_tools():
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    matchers = [h["matcher"] for h in settings["hooks"]["PreToolUse"]]
    assert any(re.fullmatch(m, "mcp__bakehouse__query_sales_metrics") for m in matchers)


def test_the_server_is_registered_for_the_dev_target():
    config = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]["bakehouse"]
    assert config["args"][-1] == "src/mcp_server/server.py"
    assert config["env"]["BAKEHOUSE_TARGET"] == "dev", "prod only by explicit configuration (spec 002, Q2)"


def test_contract_description_flags_personal_data():
    contract = queries.describe_contract("gold.top_customers")
    flagged = {c["name"] for c in contract["columns"] if c["personal_data"]}
    assert flagged == {"customer_name"}
    assert contract["owner"] and contract["primary_key"] and contract["sla"]
    listed = {t["table"] for t in queries.describe_contract()["tables"]}
    assert {"gold.sales_by_country", "gold.product_opinions_by_franchise"} <= listed
