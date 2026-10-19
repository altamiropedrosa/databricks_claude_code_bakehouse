"""Checks the published tables against their data contracts after each pipeline run.

Runs as the last task of bakehouse_medallion_job. For every contract in contracts/:
  1. the table exists and its columns match the contract (name, order, type, NOT NULL, comment);
  2. the primary key is unique;
  3. the table was refreshed within the contract latency (slaProperties.latency);
  4. Unity Catalog tags are applied: contract id/version on the table, classification on columns.
Any violation fails the task, so a broken contract shows up as a failed job run.

The CI covers the same schema rules offline (tests/test_data_contracts.py); this task checks what
was actually published, including data rules a static test cannot see.
"""

import argparse
import datetime as dt
import pathlib
import re
import sys

import yaml

TABLE_KEYWORD = {"materialized_view": "MATERIALIZED VIEW", "streaming_table": "STREAMING TABLE", "table": "TABLE"}
HOURS = {"h": 1, "d": 24}


def load_contracts(contracts_dir: pathlib.Path) -> list[dict]:
    return [yaml.safe_load(p.read_text(encoding="utf-8")) for p in sorted(contracts_dir.glob("*/*.yaml"))]


def norm_type(physical_type: str) -> str:
    return re.sub(r"\s+", "", physical_type).upper()


def schema_violations(properties: list[dict], columns: list[dict]) -> list[str]:
    """Compare contract properties with information_schema.columns rows (ordered by position)."""
    expected = [(p["name"], norm_type(p["physicalType"]), p["required"], p["description"]) for p in properties]
    actual = [
        (c["column_name"], norm_type(c["full_data_type"]), c["is_nullable"] == "NO", c["comment"]) for c in columns
    ]
    if not actual:
        return ["table not found"]
    violations = []
    if [e[0] for e in expected] != [a[0] for a in actual]:
        violations.append(f"columns differ: contract {[e[0] for e in expected]} != table {[a[0] for a in actual]}")
    for exp, act in zip(expected, actual):
        if exp[0] != act[0]:
            continue
        name = exp[0]
        if exp[1] != act[1]:
            violations.append(f"{name}: type {act[1]} != contract {exp[1]}")
        if exp[2] != act[2]:
            violations.append(f"{name}: {'NOT NULL' if act[2] else 'nullable'} != contract required={exp[2]}")
        if exp[3] != act[3]:
            violations.append(f"{name}: comment differs from the contract description")
    return violations


def latency_hours(contract: dict) -> float | None:
    for sla in contract.get("slaProperties", []):
        if sla["property"] == "latency":
            return float(sla["value"]) * HOURS[sla.get("unit", "h")]
    return None


def freshness_violation(last_altered: dt.datetime | None, now: dt.datetime, max_hours: float | None) -> str | None:
    if max_hours is None or last_altered is None:
        return None
    age = (now - last_altered).total_seconds() / 3600
    return f"stale: refreshed {age:.1f} h ago, contract latency is {max_hours:g} h" if age > max_hours else None


def primary_key(properties: list[dict]) -> list[str]:
    keys = [p for p in properties if p.get("primaryKey")]
    return [p["name"] for p in sorted(keys, key=lambda p: p.get("primaryKeyPosition", 0))]


def tag_statements(catalog: str, contract: dict) -> list[str]:
    obj = contract["schema"][0]
    target = f"{TABLE_KEYWORD[obj['physicalType']]} {catalog}.{obj['physicalName']}"
    contract_tags = f"'data_contract' = '{contract['id']}', 'data_contract_version' = '{contract['version']}'"
    statements = [f"ALTER {target} SET TAGS ({contract_tags})"]
    for prop in obj["properties"]:
        if prop.get("classification"):
            statements.append(
                f"ALTER {target} ALTER COLUMN {prop['name']} SET TAGS ('classification' = '{prop['classification']}')"
            )
    return statements


def check_contract(spark, catalog: str, contract: dict, now: dt.datetime, apply_tags: bool) -> list[str]:
    obj = contract["schema"][0]
    schema, table = obj["physicalName"].split(".")
    fqn = f"{catalog}.{obj['physicalName']}"
    columns = [
        row.asDict()
        for row in spark.sql(
            f"SELECT column_name, full_data_type, is_nullable, comment FROM {catalog}.information_schema.columns "
            f"WHERE table_schema = '{schema}' AND table_name = '{table}' ORDER BY ordinal_position"
        ).collect()
    ]
    violations = schema_violations(obj["properties"], columns)
    if violations == ["table not found"]:
        return violations

    keys = primary_key(obj["properties"])
    if keys:
        key_list = ", ".join(keys)
        duplicates = spark.sql(f"SELECT count(*) - count(DISTINCT {key_list}) AS n FROM {fqn}").first()["n"]
        if duplicates:
            violations.append(f"primary key ({key_list}) has {duplicates} duplicated rows")

    last_altered = spark.sql(
        f"SELECT last_altered FROM {catalog}.information_schema.tables "
        f"WHERE table_schema = '{schema}' AND table_name = '{table}'"
    ).first()["last_altered"]
    if last_altered is not None and last_altered.tzinfo is None:
        last_altered = last_altered.replace(tzinfo=dt.UTC)
    if stale := freshness_violation(last_altered, now, latency_hours(contract)):
        violations.append(stale)

    if apply_tags:  # after the freshness check: tagging also bumps last_altered
        for statement in tag_statements(catalog, contract):
            spark.sql(statement)
    return violations


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--contracts-dir", required=True, type=pathlib.Path)
    parser.add_argument("--skip-tags", action="store_true", help="only check, do not write tags")
    args = parser.parse_args(argv)

    from pyspark.sql import SparkSession

    spark = SparkSession.builder.getOrCreate()
    spark.sql("SET TIME ZONE 'UTC'")
    now = dt.datetime.now(dt.UTC)

    contracts = load_contracts(args.contracts_dir)
    if not contracts:
        sys.exit(f"no contracts found in {args.contracts_dir}")
    failed = 0
    for contract in contracts:
        violations = check_contract(spark, args.catalog, contract, now, apply_tags=not args.skip_tags)
        status = "FAIL" if violations else "OK"
        print(f"[{status}] {args.catalog}.{contract['schema'][0]['physicalName']} (contract {contract['version']})")
        for violation in violations:
            print(f"    - {violation}")
        failed += bool(violations)
    print(f"{len(contracts) - failed}/{len(contracts)} contracts satisfied")
    if failed:
        sys.exit(f"{failed} contract(s) violated")


if __name__ == "__main__":
    main()
