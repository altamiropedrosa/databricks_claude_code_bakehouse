"""Offline checks of the semantic layer (metric views in semantic/).

The semantic layer may only be built on contracted data: its source must have a data contract,
every column it reads must be in that contract, and no column classified as personal data may be
exposed. Every field needs the metadata Genie and dashboards rely on (comment, display_name).
"""

import importlib.util
import pathlib
import re
import sys

import pytest
import yaml

ROOT = pathlib.Path(__file__).parent.parent
SEMANTIC = ROOT / "semantic"
CONTRACTS = ROOT / "contracts"

# Loaded by path (src/ is not a package). No .pyc: test_catalog_name_never_hardcoded reads every file in src/.
_dont_write_bytecode, sys.dont_write_bytecode = sys.dont_write_bytecode, True
_spec = importlib.util.spec_from_file_location("publish", ROOT / "src" / "jobs" / "publish_metric_views.py")
publish = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(publish)
sys.dont_write_bytecode = _dont_write_bytecode

VIEW_FILES = sorted(SEMANTIC.glob("*/*.yaml"))
SQL_KEYWORDS = {
    "and", "or", "not", "null", "is", "in", "case", "when", "then", "else", "end", "distinct",
    "as", "filter", "where", "true", "false", "between", "like", "interval",
}  # fmt: skip
FORMAT_TYPES = {"number", "currency", "percentage", "byte", "date", "date_time"}


def _id(path: pathlib.Path) -> str:
    return f"{path.parent.name}/{path.stem}"


def _load(path: pathlib.Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _contract_for(source: str) -> dict:
    layer, table = source.split(".")
    path = CONTRACTS / layer / f"{table}.yaml"
    assert path.exists(), f"source {source} has no data contract"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _columns_in(expr: str) -> set[str]:
    """Bare column references in a dimension/measure expression."""
    expr = re.sub(r"'[^']*'", "", expr)  # string literals
    expr = re.sub(r"MEASURE\s*\([^)]*\)", "", expr, flags=re.IGNORECASE)  # references to other measures
    expr = re.sub(r"`[^`]*`", "", expr)
    tokens = re.findall(r"\b([A-Za-z_]\w*)\b(?!\s*\()", expr)
    return {t for t in tokens if t.lower() not in SQL_KEYWORDS and not t.isdigit()}


def test_there_is_a_semantic_layer():
    assert VIEW_FILES, "no metric view in semantic/"


@pytest.mark.parametrize("path", VIEW_FILES, ids=_id)
def test_metric_view_header(path):
    view = _load(path)
    assert path.parent.name == "gold", "metric views are published in the gold schema"
    assert str(view["version"]) == "1.1"
    assert re.fullmatch(r"[a-z_]+\.[a-z_]+", view["source"]), "source is <layer>.<table>, never with the catalog"
    assert view.get("comment"), "metric view needs a comment"
    assert view["dimensions"] and view["measures"]


@pytest.mark.parametrize("path", VIEW_FILES, ids=_id)
def test_fields_have_metadata(path):
    view = _load(path)
    fields = view["dimensions"] + view["measures"]
    names = [f["name"] for f in fields]
    assert len(names) == len(set(names)), "duplicated field name"
    for field in fields:
        assert re.fullmatch(r"[a-z][a-z0-9_]*", field["name"]), f"{field['name']}: use snake_case (no backticks)"
        assert field.get("comment") and field.get("display_name"), f"{field['name']}: comment and display_name"
        assert len(field.get("synonyms", [])) <= 10, f"{field['name']}: at most 10 synonyms"
        if "format" in field:
            assert field["format"].get("type") in FORMAT_TYPES, f"{field['name']}: format needs a valid type"


@pytest.mark.parametrize("path", VIEW_FILES, ids=_id)
def test_metric_view_reads_only_contracted_non_personal_columns(path):
    view = _load(path)
    properties = {p["name"]: p for p in _contract_for(view["source"])["schema"][0]["properties"]}
    for field in view["dimensions"] + view["measures"]:
        for column in _columns_in(field["expr"]):
            assert column in properties, f"{field['name']}: column '{column}' is not in the source contract"
            assert not properties[column].get("classification"), (
                f"{field['name']}: '{column}' is classified as {properties[column]['classification']}"
            )


@pytest.mark.parametrize("path", VIEW_FILES, ids=_id)
def test_composed_measures_reference_existing_measures(path):
    view = _load(path)
    measures = {m["name"] for m in view["measures"]}
    for measure in view["measures"]:
        for ref in re.findall(r"MEASURE\s*\(\s*`?(\w+)`?\s*\)", measure["expr"], re.IGNORECASE):
            assert ref in measures and ref != measure["name"], f"{measure['name']}: MEASURE({ref})"


@pytest.mark.parametrize("path", VIEW_FILES, ids=_id)
def test_create_statement_adds_the_catalog(path):
    statement = publish.create_statement("my_catalog", f"gold.{path.stem}", path.read_text(encoding="utf-8"))
    assert statement.startswith(f"CREATE OR REPLACE VIEW my_catalog.gold.{path.stem}\nWITH METRICS\nLANGUAGE YAML")
    assert f"\nsource: my_catalog.{_load(path)['source']}\n" in statement
    body = statement.split("$$")[1]
    assert yaml.safe_load(body)["source"] == f"my_catalog.{_load(path)['source']}"


def test_create_statement_rejects_ambiguous_source():
    with pytest.raises(ValueError, match="exactly one"):
        publish.create_statement("c", "gold.v", "version: 1.1\ndimensions: []\n")


def test_job_publishes_after_the_contracts_are_checked():
    job = (ROOT / "resources" / "bakehouse.job.yml").read_text(encoding="utf-8")
    publish_task = job.split("- task_key: publish_metric_views")[1]
    assert "- task_key: enforce_data_contracts" in publish_task.split("spark_python_task")[0]
    assert "${workspace.file_path}/semantic" in publish_task
