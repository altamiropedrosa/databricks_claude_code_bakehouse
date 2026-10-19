"""Offline checks of the Genie spaces in genie/ and of the payload built by src/jobs/publish_genie_space.py.

A Genie space may only read governed data (metric views of semantic/ or tables with a data
contract), never personal data, and its SQL must reference only attached sources with qualified
columns. The built payload must satisfy the serialized_space rules the Genie API enforces.
"""

import importlib.util
import pathlib
import re
import sys

import pytest
import yaml

ROOT = pathlib.Path(__file__).parent.parent

# Loaded by path (src/ is not a package). No .pyc: test_catalog_name_never_hardcoded reads every file in src/.
_dont_write_bytecode, sys.dont_write_bytecode = sys.dont_write_bytecode, True
_spec = importlib.util.spec_from_file_location("genie", ROOT / "src" / "jobs" / "publish_genie_space.py")
genie = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(genie)
sys.dont_write_bytecode = _dont_write_bytecode

SPACE_FILES = sorted((ROOT / "genie").glob("*.yaml"))
HEX_ID = re.compile(r"[0-9a-f]{32}")


def _id(path: pathlib.Path) -> str:
    return path.stem


def _load(path: pathlib.Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _sources(definition: dict) -> dict[str, str]:
    """{short name: '<schema>.<object>'} of every attached source."""
    sources = definition["space"]["data_sources"]
    identifiers = [s["identifier"] for s in sources.get("tables", []) + sources.get("metric_views", [])]
    return {i.split(".")[-1]: i.removeprefix("${catalog}.") for i in identifiers}


def _known_columns(source: str) -> dict[str, dict]:
    """Columns of a source: metric view fields (semantic/) or contract properties (contracts/)."""
    schema, name = source.split(".")
    metric_view = ROOT / "semantic" / schema / f"{name}.yaml"
    if metric_view.exists():
        view = _load(metric_view)
        return {f["name"]: {} for f in view["dimensions"] + view["measures"]}
    contract = ROOT / "contracts" / schema / f"{name}.yaml"
    assert contract.exists(), f"{source} is neither a metric view nor a contracted table"
    return {p["name"]: p for p in _load(contract)["schema"][0]["properties"]}


def _all_sql(definition: dict) -> list[str]:
    instructions = definition["space"].get("instructions", {})
    sql = [e["sql"] for e in instructions.get("example_question_sqls", [])]
    for kind in ("measures", "filters", "expressions"):
        sql += [s["sql"] for s in instructions.get("sql_snippets", {}).get(kind, [])]
    return sql


@pytest.mark.parametrize("path", SPACE_FILES, ids=_id)
def test_space_header(path):
    definition = _load(path)
    assert definition["title"] and not definition["title"].startswith("["), "the target prefix is added on publish"
    assert len(definition["description"]) > 80, "the description drives routing: state purpose and scope"
    assert definition["space"]["version"] == 2


@pytest.mark.parametrize("path", SPACE_FILES, ids=_id)
def test_sources_are_governed_and_never_hardcode_the_catalog(path):
    definition = _load(path)
    sources = _sources(definition)
    assert 0 < len(sources) <= 5, "keep the space focused"
    raw = path.read_text(encoding="utf-8")
    for identifier in re.findall(r"\b(\w+)\.(?:gold|silver|bronze)\.\w+", raw):
        assert identifier == "catalog", f"catalog '{identifier}' hardcoded: use ${{catalog}}"
    for source in sources.values():
        _known_columns(source)


@pytest.mark.parametrize("path", SPACE_FILES, ids=_id)
def test_column_configs_reference_existing_non_personal_columns(path):
    definition = _load(path)
    sources = definition["space"]["data_sources"]
    for entry in sources.get("tables", []) + sources.get("metric_views", []):
        columns = _known_columns(entry["identifier"].removeprefix("${catalog}."))
        for config in entry.get("column_configs", []):
            assert config["column_name"] in columns, f"{entry['identifier']}: unknown column {config['column_name']}"
        personal = [name for name, prop in columns.items() if prop.get("classification")]
        configured = {c["column_name"]: c for c in entry.get("column_configs", [])}
        for name in personal:
            assert configured.get(name, {}).get("exclude"), f"{entry['identifier']}: hide personal column {name}"


@pytest.mark.parametrize("path", SPACE_FILES, ids=_id)
def test_sql_reads_only_attached_sources_with_qualified_columns(path):
    definition = _load(path)
    sources = _sources(definition)
    for sql in _all_sql(definition):
        for schema, name in re.findall(r"\$\{catalog\}\.(\w+)\.(\w+)", sql):
            assert f"{schema}.{name}" in sources.values(), f"{schema}.{name} is not attached to the space"
    for snippet_kind in ("measures", "filters", "expressions"):
        for snippet in definition["space"]["instructions"].get("sql_snippets", {}).get(snippet_kind, []):
            columns = re.findall(r"(?<![.\w])([a-z_]\w*)(?=\s*[,)=<>+\-*/]|\s*$)", snippet["sql"])
            unqualified = [c for c in columns if c.upper() not in {"NULL", "AND", "OR"}]
            assert not unqualified, f"{snippet['alias']}: qualify columns {unqualified}"


@pytest.mark.parametrize("path", SPACE_FILES, ids=_id)
def test_built_payload_follows_api_rules(path):
    definition = _load(path)
    space = genie.build_space(definition, "my_catalog")
    assert "${catalog}" not in str(space)
    instructions = space["instructions"]
    assert len(instructions.get("text_instructions", [])) <= 1
    assert sum(len(line) for line in instructions["text_instructions"][0]["content"]) < 2000

    ids = []
    for key in ("sample_questions",):
        ids += [item["id"] for item in space["config"][key]]
    for key in ("example_question_sqls", "text_instructions", "join_specs"):
        ids += [item["id"] for item in instructions.get(key, [])]
    for kind in instructions.get("sql_snippets", {}).values():
        ids += [item["id"] for item in kind]
    assert all(HEX_ID.fullmatch(i) for i in ids), "ids are 32 lowercase hex chars"
    assert len(ids) == len(set(ids)), "ids must be unique"

    for item in space["config"]["sample_questions"] + instructions["example_question_sqls"]:
        assert isinstance(item["question"], list) and len(item["question"]) == 1
    for example in instructions["example_question_sqls"]:
        assert isinstance(example["sql"], list) and example["sql"]
    for key in ("sample_questions",):
        assert [i["id"] for i in space["config"][key]] == sorted(i["id"] for i in space["config"][key])
    assert [e["id"] for e in instructions["example_question_sqls"]] == sorted(
        e["id"] for e in instructions["example_question_sqls"]
    )
    for entry in space["data_sources"].get("tables", []) + space["data_sources"].get("metric_views", []):
        assert entry["identifier"].startswith("my_catalog.")
        names = [c["column_name"] for c in entry.get("column_configs", [])]
        assert names == sorted(names)


def test_space_title_has_the_target_prefix():
    definition = _load(SPACE_FILES[0])
    assert genie.space_title(definition, "prod") == f"[prod] {definition['title']}"


def test_find_space_by_title():
    class Space:
        def __init__(self, space_id, title):
            self.space_id, self.title = space_id, title

    spaces = [Space("1", "[dev] A"), Space("2", "[prod] A")]
    assert genie.find_space(spaces, "[prod] A").space_id == "2"
    assert genie.find_space(spaces, "[ci] A") is None
    with pytest.raises(RuntimeError, match="2 Genie spaces"):
        genie.find_space([*spaces, Space("3", "[dev] A")], "[dev] A")


def test_job_publishes_the_space_after_the_metric_views():
    job = (ROOT / "resources" / "bakehouse.job.yml").read_text(encoding="utf-8")
    task = job.split("- task_key: publish_genie_space")[1]
    assert "- task_key: publish_metric_views" in task.split("spark_python_task")[0]
    assert "${workspace.file_path}/genie" in task and "${var.warehouse_id}" in task
