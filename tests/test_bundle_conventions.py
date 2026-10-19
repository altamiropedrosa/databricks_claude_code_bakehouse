"""Offline checks of the bundle conventions (no Databricks connection needed).

These rules are invisible to `bundle validate` and to a pipeline run: a hardcoded catalog,
for example, deploys green and silently writes to the wrong environment.
"""

import json
import pathlib
import re

import pytest
import yaml

ROOT = pathlib.Path(__file__).parent.parent
RESOURCES = ROOT / "resources"
TRANSFORMATIONS = ROOT / "src" / "pipelines" / "bakehouse" / "transformations"
DASHBOARDS = ROOT / "src" / "dashboards"
LAYERS = ("bronze", "silver", "gold")

SQL_FILES = sorted(TRANSFORMATIONS.rglob("*.sql"))
DASHBOARD_FILES = sorted(DASHBOARDS.glob("*.lvdash.json"))


def _strip_sql_comments(sql: str) -> str:
    return re.sub(r"--[^\n]*", "", sql)


def _target_catalogs() -> set[str]:
    """Literal catalog values assigned to the targets in databricks.yml."""
    text = (ROOT / "databricks.yml").read_text(encoding="utf-8")
    return {value for value in re.findall(r"^\s+catalog:\s*(\S+)\s*$", text, re.MULTILINE) if "${" not in value}


def _pipeline_configuration() -> dict[str, str]:
    """Key/value pairs of the pipeline 'configuration:' block."""
    text = (RESOURCES / "bakehouse.pipeline.yml").read_text(encoding="utf-8")
    match = re.search(r"^(\s+)configuration:\s*\n((?:\1\s+\S.*\n?)+)", text, re.MULTILINE)
    assert match, "pipeline has no configuration block"
    return dict(re.findall(r"^\s+(\w+):\s*(\S+)\s*$", match.group(2), re.MULTILINE))


def test_layout_has_sql_for_every_layer():
    for layer in LAYERS:
        assert list((TRANSFORMATIONS / layer).glob("*.sql")), f"no SQL files in {layer}/"
    assert DASHBOARD_FILES, "no dashboard found"


def test_catalog_name_never_hardcoded():
    catalogs = _target_catalogs()
    assert catalogs, "no literal catalog found in the databricks.yml targets"
    files = [p for p in [*RESOURCES.rglob("*"), *(ROOT / "src").rglob("*")] if p.is_file()]
    offenders = [
        f"{p.relative_to(ROOT)}: {catalog}"
        for p in files
        for catalog in catalogs
        if re.search(rf"\b{re.escape(catalog)}\b", p.read_text(encoding="utf-8"))
    ]
    assert not offenders, offenders


@pytest.mark.parametrize("path", [*SQL_FILES, *DASHBOARD_FILES], ids=lambda p: p.name)
def test_no_use_catalog_or_schema(path):
    text = _strip_sql_comments(path.read_text(encoding="utf-8"))
    assert not re.search(r"\bUSE\s+(CATALOG|SCHEMA|DATABASE)\b", text, re.IGNORECASE)


@pytest.mark.parametrize("path", SQL_FILES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_sql_defines_its_own_table_in_its_layer(path):
    layer, table = path.parent.name, path.stem
    assert layer in LAYERS
    assert not table.startswith(f"{layer}_"), "table name must not repeat the layer"
    sql = _strip_sql_comments(path.read_text(encoding="utf-8"))
    targets = re.findall(r"CREATE\s+OR\s+REFRESH\s+(?:STREAMING\s+TABLE|MATERIALIZED\s+VIEW)\s+(\S+)", sql, re.IGNORECASE)
    assert targets == [f"${{medallion_catalog}}.${{{layer}_schema}}.{table}"]


@pytest.mark.parametrize("path", SQL_FILES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_source_is_read_only_and_only_read_by_bronze(path):
    sql = _strip_sql_comments(path.read_text(encoding="utf-8"))
    writes = r"\b(INSERT\s+(INTO|OVERWRITE)|MERGE\s+INTO|DELETE\s+FROM|UPDATE\s+\S+\s+SET|ALTER\s+TABLE|DROP\s+TABLE|TRUNCATE\s+TABLE)\b"
    assert not re.search(writes, sql, re.IGNORECASE)
    if path.parent.name != "bronze":
        assert "samples." not in sql, "only bronze may read samples.bakehouse"


def test_pipeline_configuration_comes_from_bundle():
    config = _pipeline_configuration()
    assert config == {
        "medallion_catalog": "${var.catalog}",
        **{f"{layer}_schema": f"${{resources.schemas.{layer}.name}}" for layer in LAYERS},
    }


@pytest.mark.parametrize("path", SQL_FILES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_sql_variables_are_configured(path):
    used = set(re.findall(r"\$\{(\w+)\}", path.read_text(encoding="utf-8")))
    assert used <= set(_pipeline_configuration()), used - set(_pipeline_configuration())


def test_schemas_are_named_after_layers():
    text = (RESOURCES / "bakehouse.schemas.yml").read_text(encoding="utf-8")
    assert set(re.findall(r"^\s+name:\s*(\S+)\s*$", text, re.MULTILINE)) == set(LAYERS)
    assert set(re.findall(r"^\s+catalog_name:\s*(\S+)\s*$", text, re.MULTILINE)) == {"${var.catalog}"}


@pytest.mark.parametrize("path", DASHBOARD_FILES, ids=lambda p: p.name)
def test_dashboard_reads_bare_gold_tables(path):
    gold_tables = {p.stem for p in (TRANSFORMATIONS / "gold").glob("*.sql")}
    gold_tables |= {p.stem for p in (ROOT / "semantic" / "gold").glob("*.yaml")}  # metric views
    for dataset in json.loads(path.read_text(encoding="utf-8"))["datasets"]:
        query = "".join(dataset["queryLines"])
        for table in re.findall(r"\b(?:FROM|JOIN)\s+([\w.`]+)", query, re.IGNORECASE):
            assert "." not in table, f"{dataset['name']}: '{table}' must be a bare table name"
            assert table in gold_tables, f"{dataset['name']}: '{table}' is not a gold table"


@pytest.mark.parametrize("path", DASHBOARD_FILES, ids=lambda p: p.name)
def test_dashboard_widgets_bind_existing_fields(path):
    dashboard = json.loads(path.read_text(encoding="utf-8"))
    datasets = {d["name"] for d in dashboard["datasets"]}
    for page in dashboard["pages"]:
        for item in page["layout"]:
            widget = item["widget"]
            queries = [q["query"] for q in widget.get("queries", [])]
            assert {q["datasetName"] for q in queries} <= datasets, widget["name"]
            names = {f["name"] for q in queries for f in q.get("fields", [])}
            encodings = widget.get("spec", {}).get("encodings", {})
            used = set()
            for key, value in encodings.items():
                if isinstance(value, dict) and "fieldName" in value:
                    used.add(value["fieldName"])
                if key in ("columns", "extra", "fields") and isinstance(value, list):
                    used |= {c["fieldName"] for c in value}
            if "coordinates" in encodings:
                used |= {encodings["coordinates"][axis]["fieldName"] for axis in ("latitude", "longitude")}
            assert used <= names, (widget["name"], used - names)


def test_prod_deploy_is_gated_by_ci_integration():
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "databricks.yml").read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    commands = [step.get("run", "") for step in jobs["integration"]["steps"]]
    assert commands[-2:] == ["databricks bundle deploy -t ci", "databricks bundle run bakehouse_medallion_job -t ci"]
    assert jobs["integration"]["concurrency"]["cancel-in-progress"] is False, "never cancel a deploy mid-way"
    assert {"validate", "integration"} <= set(jobs["deploy"]["needs"]), "prod deploy must wait for the ci run"


def test_ci_target_is_isolated_from_dev_and_prod():
    targets = yaml.safe_load((ROOT / "databricks.yml").read_text(encoding="utf-8"))["targets"]
    catalogs = [target["variables"]["catalog"] for target in targets.values()]
    assert len(catalogs) == len(set(catalogs)), "each target needs its own catalog"
    assert targets["ci"]["run_as"] == targets["prod"]["run_as"], "ci runs as the same identity as prod"
    assert targets["ci"]["presets"]["trigger_pause_status"] == "PAUSED"
