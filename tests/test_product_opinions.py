"""Offline checks of specs/001-opinioes-por-produto.md (opinions per product extracted from reviews).

The closed lists of products, opinions and reasons live in three places: the ai_extract schema the
model answers with, the silver expectations that drop anything else (CA1) and the gold contract that
consumers read. A value added to one of them and not the others would be silently dropped or never
produced, so all of them must hold exactly the same values.
"""

import json
import pathlib
import re

import pytest
import yaml

ROOT = pathlib.Path(__file__).parent.parent
TRANSFORMATIONS = ROOT / "src" / "pipelines" / "bakehouse" / "transformations"
SILVER_SQL = TRANSFORMATIONS / "silver" / "review_product_opinions.sql"
CONTRACTS = {
    "silver": ROOT / "contracts" / "silver" / "review_product_opinions.yaml",
    "gold": ROOT / "contracts" / "gold" / "product_opinions_by_franchise.yaml",
}
FIELDS = ("product", "opinion", "reason")


def _extraction_schema() -> dict:
    match = re.search(r"ai_extract\(\s*review,\s*'(\{.*?\})',", SILVER_SQL.read_text(encoding="utf-8"), re.DOTALL)
    assert match, "ai_extract schema literal not found"
    return json.loads(match.group(1))["mentions"]["items"]["properties"]


def _allowed_values(layer: str) -> dict[str, list[str]]:
    """{column: values} from the `<column> IN (...)` quality rules of a contract."""
    rules = yaml.safe_load(CONTRACTS[layer].read_text(encoding="utf-8"))["schema"][0]["quality"]
    allowed = {}
    for rule in rules:
        if match := re.fullmatch(r"(\w+) IN \((.*)\)", " ".join(rule["implementation"].split())):
            allowed[match.group(1)] = re.findall(r"'([^']*)'", match.group(2))
    return allowed


@pytest.mark.parametrize("field", FIELDS)
def test_silver_expectations_accept_exactly_what_the_model_may_answer(field):
    assert _allowed_values("silver")[field] == _extraction_schema()[field]["enum"]


@pytest.mark.parametrize("field", ("product", "reason"))
def test_gold_contract_lists_the_same_values_as_silver(field):
    assert _allowed_values("gold")[field] == _allowed_values("silver")[field]


def test_every_review_is_sent_to_the_model_once():
    sql = re.sub(r"--[^\n]*", "", SILVER_SQL.read_text(encoding="utf-8"))
    assert "CREATE OR REFRESH STREAMING TABLE" in sql, "a materialized view would extract every review again"
    assert re.search(r"FROM\s+STREAM\(", sql), "the source must be read as a stream"
    assert sql.count("ai_extract(") == 1


def test_gold_measures_are_additive_counts():
    properties = yaml.safe_load(CONTRACTS["gold"].read_text(encoding="utf-8"))["schema"][0]["properties"]
    measures = [p for p in properties if p["name"].endswith("mentions")]
    assert measures and all(p["physicalType"] == "BIGINT" and p["required"] for p in measures)
