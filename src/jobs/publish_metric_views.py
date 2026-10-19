"""Publishes the metric views defined in semantic/ (the semantic layer).

Runs in bakehouse_medallion_job after the data contracts are checked. Each
semantic/<schema>/<view>.yaml is a metric view YAML whose `source` has no catalog
(e.g. silver.transactions); the target catalog is added here, so the same file
serves every bundle target. CREATE OR REPLACE keeps the run idempotent.
"""

import argparse
import pathlib
import re
import sys

import yaml

SOURCE_LINE = re.compile(r"^source:[ \t]*(\S+)[ \t]*$", re.MULTILINE)


def load_definitions(semantic_dir: pathlib.Path) -> list[tuple[str, str]]:
    """(schema.view, YAML text) for every metric view definition."""
    return [(f"{p.parent.name}.{p.stem}", p.read_text(encoding="utf-8")) for p in sorted(semantic_dir.glob("*/*.yaml"))]


def create_statement(catalog: str, view: str, text: str) -> str:
    # The YAML text is sent as written (re-serializing it produced layouts the metric view
    # parser rejects); only the top-level source line gets the catalog.
    body, count = SOURCE_LINE.subn(lambda m: f"source: {catalog}.{m.group(1)}", text)
    if count != 1:
        raise ValueError(f"{view}: expected exactly one top-level 'source:' line, found {count}")
    return f"CREATE OR REPLACE VIEW {catalog}.{view}\nWITH METRICS\nLANGUAGE YAML\nAS $$\n{body}$$"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--semantic-dir", required=True, type=pathlib.Path)
    args = parser.parse_args(argv)

    definitions = load_definitions(args.semantic_dir)
    if not definitions:
        sys.exit(f"no metric view definitions found in {args.semantic_dir}")

    from pyspark.sql import SparkSession

    spark = SparkSession.builder.getOrCreate()
    for view, text in definitions:
        spark.sql(create_statement(args.catalog, view, text))
        definition = yaml.safe_load(text)
        print(
            f"published {args.catalog}.{view}: {len(definition['dimensions'])} dimensions, "
            f"{len(definition['measures'])} measures"
        )


if __name__ == "__main__":
    main()
