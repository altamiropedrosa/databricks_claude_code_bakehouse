"""Query building for the bakehouse MCP server (specs/002-servidor-mcp.md), without any Databricks access.

Every tool turns validated inputs into exactly one SELECT. Identifiers (measures, dimensions, columns)
come from allowlists read from the governed files, semantic/ and contracts/, so they can be written in
the SQL text; every user value travels as a named parameter of the Statement Execution API. Columns
classified as personal data in a contract are never selectable. The catalog comes from the bundle
target in databricks.yml, never from this code.
"""

import dataclasses
import datetime as dt
import pathlib
import re

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
MAX_ROWS = 1000
IDENTIFIER = re.compile(r"[a-z_][a-z0-9_]*")


@dataclasses.dataclass(frozen=True)
class Query:
    sql: str
    parameters: dict[str, tuple[str, str]]  # name -> (type, value), e.g. {"country": ("STRING", "Japan")}
    limit: int


def _load(path: pathlib.Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def target_catalog(target: str, root: pathlib.Path = ROOT) -> str:
    targets = _load(root / "databricks.yml")["targets"]
    if target not in targets:
        raise ValueError(f"unknown bundle target '{target}', expected one of {sorted(targets)}")
    catalog = targets[target]["variables"]["catalog"]
    if not IDENTIFIER.fullmatch(catalog):
        raise ValueError(f"unexpected catalog name '{catalog}'")
    return catalog


def warehouse_name(root: pathlib.Path = ROOT) -> str:
    return _load(root / "databricks.yml")["variables"]["warehouse_id"]["lookup"]["warehouse"]


def contracts(root: pathlib.Path = ROOT) -> dict[str, dict]:
    """{'<layer>.<table>': contract} for every data contract."""
    return {f"{p.parent.name}.{p.stem}": _load(p) for p in sorted((root / "contracts").glob("*/*.yaml"))}


def restricted_columns(root: pathlib.Path = ROOT) -> set[str]:
    """Columns classified as personal data in any contract."""
    return {
        prop["name"]
        for contract in contracts(root).values()
        for prop in contract["schema"][0]["properties"]
        if prop.get("classification")
    }


def metric_view_fields(root: pathlib.Path = ROOT) -> tuple[list[str], list[str]]:
    """(dimensions, measures) of gold.sales_metrics, without personal data."""
    view = _load(root / "semantic" / "gold" / "sales_metrics.yaml")
    blocked = restricted_columns(root)
    dimensions = [d["name"] for d in view["dimensions"] if d["name"] not in blocked]
    measures = [m["name"] for m in view["measures"] if m["name"] not in blocked]
    return dimensions, measures


def _check_limit(limit: int) -> int:
    if not isinstance(limit, int) or not 1 <= limit <= MAX_ROWS:
        raise ValueError(f"limit must be an integer between 1 and {MAX_ROWS}")
    return limit


def _check_allowed(kind: str, values: list[str], allowed: list[str]) -> list[str]:
    unknown = [v for v in values if v not in allowed]
    if unknown:
        raise ValueError(f"unknown {kind} {unknown}; allowed: {allowed}")
    if len(set(values)) != len(values):
        raise ValueError(f"repeated {kind} in {values}")
    return values


def _check_date(name: str, value: str) -> str:
    try:
        return dt.date.fromisoformat(value).isoformat()
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a date in the format YYYY-MM-DD") from None


def _ensure_selectable(columns: list[str], root: pathlib.Path) -> None:
    exposed = set(columns) & restricted_columns(root)
    if exposed:
        raise ValueError(f"columns {sorted(exposed)} are personal data and cannot be returned")


def sales_metrics(
    catalog: str,
    measures: list[str],
    dimensions: list[str] | None = None,
    franchise_country: str | None = None,
    franchise_name: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 100,
    root: pathlib.Path = ROOT,
) -> Query:
    allowed_dimensions, allowed_measures = metric_view_fields(root)
    if not measures:
        raise ValueError(f"at least one measure is required; allowed: {allowed_measures}")
    measures = _check_allowed("measures", list(measures), allowed_measures)
    dimensions = _check_allowed("dimensions", list(dimensions or []), allowed_dimensions)
    _ensure_selectable(measures + dimensions, root)

    select = [*dimensions, *(f"MEASURE({m}) AS {m}" for m in measures)]
    where, parameters = [], {}
    if franchise_country is not None:
        where.append("franchise_country = :franchise_country")
        parameters["franchise_country"] = ("STRING", franchise_country)
    if franchise_name is not None:
        where.append("franchise_name = :franchise_name")
        parameters["franchise_name"] = ("STRING", franchise_name)
    if date_from is not None:
        where.append("transaction_date >= :date_from")
        parameters["date_from"] = ("DATE", _check_date("date_from", date_from))
    if date_to is not None:
        where.append("transaction_date <= :date_to")
        parameters["date_to"] = ("DATE", _check_date("date_to", date_to))

    sql = f"SELECT {', '.join(select)} FROM {catalog}.gold.sales_metrics"
    if where:
        sql += f" WHERE {' AND '.join(where)}"
    if dimensions:
        sql += f" GROUP BY ALL ORDER BY {measures[0]} DESC"
    sql += f" LIMIT {_check_limit(limit)}"
    return Query(sql, parameters, limit)


OPINIONS = ("negative", "positive", "neutral")


def product_opinions(
    catalog: str,
    franchise_name: str | None = None,
    country: str | None = None,
    opinion: str = "negative",
    limit: int = 50,
    root: pathlib.Path = ROOT,
) -> Query:
    if opinion not in OPINIONS:
        raise ValueError(f"opinion must be one of {list(OPINIONS)}")
    columns = ["product", "reason", "mentions", "negative_mentions", "positive_mentions", "neutral_mentions"]
    _ensure_selectable(columns, root)
    where, parameters = [], {}
    if franchise_name is not None:
        where.append("franchise_name = :franchise_name")
        parameters["franchise_name"] = ("STRING", franchise_name)
    if country is not None:
        where.append("country = :country")
        parameters["country"] = ("STRING", country)
    sql = (
        "SELECT product, reason, SUM(mentions) AS mentions, SUM(negative_mentions) AS negative_mentions, "
        "SUM(positive_mentions) AS positive_mentions, SUM(neutral_mentions) AS neutral_mentions "
        f"FROM {catalog}.gold.product_opinions_by_franchise"
    )
    if where:
        sql += f" WHERE {' AND '.join(where)}"
    sql += f" GROUP BY product, reason HAVING SUM({opinion}_mentions) > 0"
    sql += f" ORDER BY {opinion}_mentions DESC, product, reason LIMIT {_check_limit(limit)}"
    return Query(sql, parameters, limit)


def franchise_sentiment(
    catalog: str,
    country: str | None = None,
    order: str = "worst",
    limit: int = 10,
    root: pathlib.Path = ROOT,
) -> Query:
    if order not in ("worst", "best"):
        raise ValueError("order must be 'worst' or 'best'")
    columns = ["franchise_name", "city", "country", "reviews", "positive_reviews", "negative_reviews", "net_sentiment"]
    _ensure_selectable(columns, root)
    where, parameters = ["reviews > 0"], {}
    if country is not None:
        where.append("country = :country")
        parameters["country"] = ("STRING", country)
    direction = "ASC" if order == "worst" else "DESC"
    sql = (
        f"SELECT {', '.join(columns)} FROM {catalog}.gold.sentiment_by_franchise "
        f"WHERE {' AND '.join(where)} ORDER BY net_sentiment {direction}, reviews DESC LIMIT {_check_limit(limit)}"
    )
    return Query(sql, parameters, limit)


def describe_contract(table: str | None = None, root: pathlib.Path = ROOT) -> dict:
    """A data contract summary, or the list of contracted tables when no table is given."""
    available = contracts(root)
    if table is None:
        return {
            "tables": [
                {"table": name, "purpose": c["description"]["purpose"], "version": c["version"]}
                for name, c in available.items()
            ]
        }
    if table not in available:
        raise ValueError(f"no data contract for '{table}'; available: {sorted(available)}")
    contract = available[table]
    obj = contract["schema"][0]
    return {
        "table": table,
        "version": contract["version"],
        "status": contract["status"],
        "owner": [m["username"] for m in contract["team"] if m.get("role") == "owner"],
        "purpose": contract["description"]["purpose"],
        "usage": contract["description"].get("usage"),
        "limitations": contract["description"].get("limitations"),
        "granularity": obj["dataGranularityDescription"],
        "primary_key": [p["name"] for p in obj["properties"] if p.get("primaryKey")],
        "columns": [
            {
                "name": p["name"],
                "type": p["physicalType"],
                "required": p["required"],
                "description": p["description"],
                "personal_data": bool(p.get("classification")),
            }
            for p in obj["properties"]
        ],
        "sla": {s["property"]: f"{s['value']} {s.get('unit', '')}".strip() for s in contract["slaProperties"]},
    }
