"""Offline tests of the runtime contract checks in src/jobs/enforce_data_contracts.py."""

import datetime as dt
import importlib.util
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).parent.parent
# Loaded by path (src/ is not a package). No .pyc: test_catalog_name_never_hardcoded reads every file in src/.
_dont_write_bytecode, sys.dont_write_bytecode = sys.dont_write_bytecode, True
_spec = importlib.util.spec_from_file_location("enforce", ROOT / "src" / "jobs" / "enforce_data_contracts.py")
enforce = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(enforce)
sys.dont_write_bytecode = _dont_write_bytecode

CONTRACTS = enforce.load_contracts(ROOT / "contracts")
PROPS = [
    {"name": "id", "physicalType": "BIGINT", "required": True, "primaryKey": True, "description": "Id"},
    {"name": "amount", "physicalType": "DECIMAL(12,2)", "required": False, "description": "Amount"},
]


def _columns(*rows):
    return [dict(zip(("column_name", "full_data_type", "is_nullable", "comment"), row)) for row in rows]


def test_contracts_are_loaded():
    assert {c["id"] for c in CONTRACTS} >= {"bakehouse.silver.transactions", "bakehouse.gold.top_customers"}


def test_schema_matches():
    columns = _columns(("id", "bigint", "NO", "Id"), ("amount", "decimal(12, 2)", "YES", "Amount"))
    assert enforce.schema_violations(PROPS, columns) == []


@pytest.mark.parametrize(
    ("columns", "expected"),
    [
        ([], ["table not found"]),
        (
            _columns(("id", "bigint", "NO", "Id")),
            ["columns differ: contract ['id', 'amount'] != table ['id']"],
        ),
        (
            _columns(("id", "int", "NO", "Id"), ("amount", "decimal(12,2)", "YES", "Amount")),
            ["id: type INT != contract BIGINT"],
        ),
        (
            _columns(("id", "bigint", "YES", "Id"), ("amount", "decimal(12,2)", "YES", "Amount")),
            ["id: nullable != contract required=True"],
        ),
        (
            _columns(("id", "bigint", "NO", "Id"), ("amount", "decimal(12,2)", "YES", None)),
            ["amount: comment differs from the contract description"],
        ),
    ],
    ids=["missing-table", "missing-column", "type", "nullability", "comment"],
)
def test_schema_violations(columns, expected):
    assert enforce.schema_violations(PROPS, columns) == expected


def test_freshness():
    now = dt.datetime(2026, 10, 20, 12, tzinfo=dt.UTC)
    assert enforce.freshness_violation(now - dt.timedelta(hours=25), now, 26) is None
    assert enforce.freshness_violation(now - dt.timedelta(hours=27), now, 26) == (
        "stale: refreshed 27.0 h ago, contract latency is 26 h"
    )
    assert enforce.freshness_violation(None, now, 26) is None


@pytest.mark.parametrize("contract", CONTRACTS, ids=lambda c: c["id"])
def test_every_contract_declares_latency(contract):
    assert enforce.latency_hours(contract) == 26


def test_primary_key_follows_position():
    props = [
        {"name": "b", "primaryKey": True, "primaryKeyPosition": 2},
        {"name": "a", "primaryKey": True, "primaryKeyPosition": 1},
        {"name": "c"},
    ]
    assert enforce.primary_key(props) == ["a", "b"]


def test_tag_statements_cover_contract_and_classification():
    contract = next(c for c in CONTRACTS if c["id"] == "bakehouse.gold.top_customers")
    statements = enforce.tag_statements("bakehouse_dev", contract)
    assert statements[0] == (
        "ALTER MATERIALIZED VIEW bakehouse_dev.gold.top_customers SET TAGS "
        "('data_contract' = 'bakehouse.gold.top_customers', 'data_contract_version' = '1.0.0')"
    )
    assert statements[1:] == [
        (
            "ALTER MATERIALIZED VIEW bakehouse_dev.gold.top_customers ALTER COLUMN customer_name "
            "SET TAGS ('classification' = 'restricted')"
        )
    ]


def test_job_runs_the_check_after_the_pipeline():
    job = (ROOT / "resources" / "bakehouse.job.yml").read_text(encoding="utf-8")
    assert "python_file: ../src/jobs/enforce_data_contracts.py" in job
    assert "- task_key: refresh_medallion_pipeline" in job.split("enforce_data_contracts")[0]
    assert "${workspace.file_path}/contracts" in job
