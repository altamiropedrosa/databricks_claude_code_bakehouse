"""Offline checks of the data contracts in contracts/ (ODCS v3) against the pipeline SQL.

A contract is the public interface of a table: if the SQL drifts from it, consumers break
silently after the next refresh. These tests keep both in sync and enforce the versioning
rules of contracts/README.md against the base branch (CONTRACTS_BASE_REF, default origin/master).
"""

import os
import pathlib
import re
import subprocess

import pytest
import yaml

ROOT = pathlib.Path(__file__).parent.parent
CONTRACTS = ROOT / "contracts"
TRANSFORMATIONS = ROOT / "src" / "pipelines" / "bakehouse" / "transformations"
BASE_REF = os.environ.get("CONTRACTS_BASE_REF", "origin/master")

CONTRACT_FILES = sorted(CONTRACTS.glob("*/*.yaml"))
STATUSES = {"draft", "active", "deprecated", "retired"}
LOGICAL_TYPES = {
    "integer": {"TINYINT", "SMALLINT", "INT", "BIGINT"},
    "number": {"DECIMAL", "DOUBLE", "FLOAT"},
    "string": {"STRING"},
    "date": {"DATE", "TIMESTAMP"},
    "boolean": {"BOOLEAN"},
}
ON_VIOLATION = {"warn": None, "drop_row": "DROP ROW", "fail_update": "FAIL UPDATE"}

COLUMN = re.compile(
    r"^(?P<name>\w+)\s+(?P<type>\w+(?:\s*\([^)]*\))?)(?P<not_null>\s+NOT\s+NULL)?"
    r"(?:\s+COMMENT\s+'(?P<comment>(?:[^'\\]|\\.)*)')?$",
    re.IGNORECASE | re.DOTALL,
)
EXPECTATION = re.compile(
    r"^CONSTRAINT\s+(?P<name>\w+)\s+EXPECT\s*\((?P<expr>.*)\)(?:\s+ON\s+VIOLATION\s+(?P<action>DROP\s+ROW|FAIL\s+UPDATE))?$",
    re.IGNORECASE | re.DOTALL,
)


def _id(path: pathlib.Path) -> str:
    return f"{path.parent.name}/{path.stem}"


def _load(path: pathlib.Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _norm_type(physical_type: str) -> str:
    return re.sub(r"\s+", "", physical_type).upper()


def _semver(version: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", str(version))
    assert match, f"version '{version}' is not semver MAJOR.MINOR.PATCH"
    return tuple(int(part) for part in match.groups())


def _split_top_level(body: str) -> list[str]:
    """Split a column list on commas outside parentheses and string literals."""
    items, depth, quoted, start = [], 0, False, 0
    for i, char in enumerate(body):
        if quoted:
            if char == "'" and body[i - 1] != "\\":
                quoted = False
        elif char == "'":
            quoted = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == "," and depth == 0:
            items.append(body[start:i].strip())
            start = i + 1
    items.append(body[start:].strip())
    return [item for item in items if item]


def _sql_definition(layer: str, table: str) -> dict:
    """Declared columns, expectations and table comment of a pipeline dataset."""
    sql = re.sub(r"--[^\n]*", "", (TRANSFORMATIONS / layer / f"{table}.sql").read_text(encoding="utf-8"))
    header = re.search(
        r"CREATE\s+OR\s+REFRESH\s+(?:STREAMING\s+TABLE|MATERIALIZED\s+VIEW)\s+\S+\s*", sql, re.IGNORECASE
    )
    assert header, "no CREATE OR REFRESH statement"
    columns, expectations = [], []
    if sql[header.end()] == "(":
        depth = 0
        for end in range(header.end(), len(sql)):
            depth += {"(": 1, ")": -1}.get(sql[end], 0)
            if depth == 0:
                break
        for item in _split_top_level(sql[header.end() + 1 : end]):
            if expectation := EXPECTATION.match(item):
                action = expectation["action"]
                expectations.append((expectation["name"], _norm(expectation["expr"]), action and _norm(action).upper()))
            else:
                column = COLUMN.match(item)
                assert column, f"cannot parse column definition: {item}"
                columns.append(column.groupdict())
    comment = re.search(r"^COMMENT\s+'((?:[^'\\]|\\.)*)'", sql, re.MULTILINE)
    return {"columns": columns, "expectations": expectations, "comment": comment and comment.group(1)}


def _contract_expectations(obj: dict) -> list[tuple]:
    rules = []
    for rule in obj.get("quality", []):
        if rule.get("engine") != "lakeflow":
            continue
        props = {p["property"]: p["value"] for p in rule.get("customProperties", [])}
        assert props.get("onViolation") in ON_VIOLATION, (
            f"{rule['name']}: onViolation must be one of {list(ON_VIOLATION)}"
        )
        rules.append((rule["name"], _norm(rule["implementation"]), ON_VIOLATION[props["onViolation"]]))
    return rules


# --- coverage --------------------------------------------------------------------------------


def test_every_gold_table_has_a_contract():
    gold_tables = {p.stem for p in (TRANSFORMATIONS / "gold").glob("*.sql")}
    contracts = {p.stem for p in (CONTRACTS / "gold").glob("*.yaml")}
    assert gold_tables - contracts == set(), "gold tables without a contract"


@pytest.mark.parametrize("path", CONTRACT_FILES, ids=_id)
def test_contract_points_to_a_pipeline_table(path):
    assert (TRANSFORMATIONS / path.parent.name / f"{path.stem}.sql").exists(), "no SQL for this contract"


# --- contract shape --------------------------------------------------------------------------


@pytest.mark.parametrize("path", CONTRACT_FILES, ids=_id)
def test_contract_header(path):
    layer, table = path.parent.name, path.stem
    contract = _load(path)
    assert contract["apiVersion"].startswith("v3.")
    assert contract["kind"] == "DataContract"
    assert contract["id"] == f"bakehouse.{layer}.{table}"
    assert contract["name"] == table
    assert contract["status"] in STATUSES
    _semver(contract["version"])
    assert any(member.get("role") == "owner" for member in contract["team"]), "contract needs an owner"
    assert {sla["property"] for sla in contract["slaProperties"]} >= {"frequency", "latency"}
    assert len(contract["schema"]) == 1, "one table per contract"
    obj = contract["schema"][0]
    assert obj["name"] == table
    assert obj["physicalName"] == f"{layer}.{table}", "physicalName is <layer>.<table>, never with the catalog"
    assert obj["description"] and obj["dataGranularityDescription"]


@pytest.mark.parametrize("path", CONTRACT_FILES, ids=_id)
def test_contract_properties(path):
    properties = _load(path)["schema"][0]["properties"]
    names = [p["name"] for p in properties]
    assert len(names) == len(set(names)), "duplicated column"
    for prop in properties:
        base_type = re.match(r"\w+", prop["physicalType"]).group(0).upper()
        assert base_type in LOGICAL_TYPES.get(prop["logicalType"], set()), f"{prop['name']}: logicalType/physicalType"
        assert isinstance(prop["required"], bool), f"{prop['name']}: required must be true/false"
        assert prop.get("description"), f"{prop['name']}: missing description"
        assert "'" not in prop["description"], f"{prop['name']}: no quotes in descriptions (they become SQL COMMENTs)"
        if prop.get("primaryKey"):
            assert prop["required"], f"{prop['name']}: a primary key column must be required"


# --- contract vs SQL -------------------------------------------------------------------------


@pytest.mark.parametrize("path", CONTRACT_FILES, ids=_id)
def test_sql_declares_the_contract_schema(path):
    obj = _load(path)["schema"][0]
    sql = _sql_definition(path.parent.name, path.stem)
    expected = [(p["name"], _norm_type(p["physicalType"]), p["required"], p["description"]) for p in obj["properties"]]
    declared = [(c["name"], _norm_type(c["type"]), bool(c["not_null"]), c["comment"]) for c in sql["columns"]]
    assert declared == expected
    assert sql["comment"] == obj["description"], "table COMMENT must match the contract description"


@pytest.mark.parametrize("path", CONTRACT_FILES, ids=_id)
def test_sql_expectations_match_contract_quality(path):
    obj = _load(path)["schema"][0]
    assert _sql_definition(path.parent.name, path.stem)["expectations"] == _contract_expectations(obj)


# --- versioning against the base branch ------------------------------------------------------


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], check=False, cwd=ROOT, capture_output=True, text=True, encoding="utf-8")


@pytest.fixture(scope="module")
def base_ref() -> str:
    if _git("rev-parse", "--verify", "--quiet", f"{BASE_REF}^{{commit}}").returncode != 0:
        pytest.skip(f"base ref {BASE_REF} not available (shallow clone?)")
    return BASE_REF


def _base_contracts(ref: str) -> dict[str, dict]:
    listing = _git("ls-tree", "-r", "--name-only", ref, "--", "contracts/").stdout.split()
    return {
        name: yaml.safe_load(_git("show", f"{ref}:{name}").stdout)
        for name in listing
        if re.fullmatch(r"contracts/[^/]+/[^/]+\.yaml", name)
    }


def _breaking_changes(old: dict, new: dict) -> list[str]:
    old_props = {p["name"]: p for p in old["schema"][0]["properties"]}
    new_props = {p["name"]: p for p in new["schema"][0]["properties"]}
    changes = [f"column removed: {name}" for name in old_props.keys() - new_props.keys()]
    for name in old_props.keys() & new_props.keys():
        before, after = old_props[name], new_props[name]
        if _norm_type(before["physicalType"]) != _norm_type(after["physicalType"]):
            changes.append(f"{name}: type {before['physicalType']} -> {after['physicalType']}")
        if before["required"] and not after["required"]:
            changes.append(f"{name}: no longer required")
        if bool(before.get("primaryKey")) != bool(after.get("primaryKey")):
            changes.append(f"{name}: primary key changed")
    return changes


def test_contract_versions_follow_semver_rules(base_ref):
    errors = []
    current = {p.relative_to(ROOT).as_posix(): _load(p) for p in CONTRACT_FILES}
    for name, old in _base_contracts(base_ref).items():
        new = current.get(name)
        if new is None:
            if old["status"] not in {"deprecated", "retired"}:
                errors.append(f"{name}: removed without being deprecated first")
            continue
        old_version, new_version = _semver(old["version"]), _semver(new["version"])
        if new_version < old_version:
            errors.append(f"{name}: version went backwards {old['version']} -> {new['version']}")
        breaking = _breaking_changes(old, new)
        if breaking and new_version[0] <= old_version[0]:
            errors.append(f"{name}: breaking change needs a MAJOR bump ({'; '.join(breaking)})")
        elif old["schema"] != new["schema"] and new_version == old_version:
            errors.append(f"{name}: schema changed, bump MINOR (additive) or PATCH (docs)")
    assert not errors, errors
