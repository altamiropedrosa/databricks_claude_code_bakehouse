"""Creates or updates the Genie spaces defined in genie/ (one YAML file per space).

Runs in bakehouse_medallion_job after the metric views are published. The space is identified by
its title, "[<target>] <title>", so every run updates the same space instead of creating a new
one; after a rename, the space is found by one of its `previous_titles` and gets the new title. The YAML `space` block is the Genie serialized_space: ${catalog} is replaced with the target
catalog, single strings become the arrays the API expects, and id-keyed lists are sorted.
"""

import argparse
import copy
import json
import pathlib
import sys

import yaml

LINE_FIELDS = {"sql", "content"}  # multi-line text, sent as one array item per line
TEXT_FIELDS = {"question", "description", "usage_guidance"}  # sent as a single-item array
ID_LISTS = {"sample_questions", "example_question_sqls", "text_instructions", "join_specs", "measures", "filters"}
ID_LISTS |= {"expressions", "questions"}


def load_definitions(genie_dir: pathlib.Path) -> list[dict]:
    return [yaml.safe_load(p.read_text(encoding="utf-8")) for p in sorted(genie_dir.glob("*.yaml"))]


def _resolve(node, catalog: str):
    if isinstance(node, str):
        return node.replace("${catalog}", catalog)
    if isinstance(node, list):
        return [_resolve(item, catalog) for item in node]
    if isinstance(node, dict):
        return {key: _resolve(value, catalog) for key, value in node.items()}
    return node


def _normalize(node, key: str | None = None):
    if isinstance(node, dict):
        return {k: _normalize(v, k) for k, v in node.items()}
    if isinstance(node, list):
        items = [_normalize(item) for item in node]
        if key in ID_LISTS:
            items.sort(key=lambda item: item["id"])
        elif key in ("tables", "metric_views"):
            items.sort(key=lambda item: item["identifier"])
        elif key == "column_configs":
            items.sort(key=lambda item: item["column_name"])
        return items
    if isinstance(node, str) and key in LINE_FIELDS:
        return node.strip().splitlines(keepends=True)
    if isinstance(node, str) and key in TEXT_FIELDS:
        return [" ".join(node.split())]
    return node


def build_space(definition: dict, catalog: str) -> dict:
    """The serialized_space payload (as a dict) for the target catalog."""
    return _normalize(_resolve(copy.deepcopy(definition["space"]), catalog))


def space_title(definition: dict, target: str) -> str:
    return f"[{target}] {definition['title']}"


def find_space(spaces, title: str):
    matches = [s for s in spaces if s.title == title]
    if len(matches) > 1:
        raise RuntimeError(f"{len(matches)} Genie spaces named '{title}': keep one and trash the others")
    return matches[0] if matches else None


def find_existing_space(spaces, definition: dict, target: str):
    """The space under its current title or, after a rename, under one of its previous_titles."""
    for title in [definition["title"], *definition.get("previous_titles", [])]:
        space = find_space(spaces, f"[{target}] {title}")
        if space:
            return space
    return None


def _all_spaces(w):
    token = None
    while True:
        page = w.genie.list_spaces(page_size=100, page_token=token)
        yield from page.spaces or []
        token = page.next_page_token
        if not token:
            return


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--warehouse-id", required=True)
    parser.add_argument("--parent-path", required=True)
    parser.add_argument("--genie-dir", required=True, type=pathlib.Path)
    args = parser.parse_args(argv)

    definitions = load_definitions(args.genie_dir)
    if not definitions:
        sys.exit(f"no Genie space definitions found in {args.genie_dir}")

    from databricks.sdk import WorkspaceClient

    w = WorkspaceClient()
    w.workspace.mkdirs(args.parent_path)
    spaces = list(_all_spaces(w))
    for definition in definitions:
        title = space_title(definition, args.target)
        serialized = json.dumps(build_space(definition, args.catalog), ensure_ascii=False)
        fields = {"title": title, "description": " ".join(definition["description"].split())}
        existing = find_existing_space(spaces, definition, args.target)
        if existing:
            w.genie.update_space(
                existing.space_id, serialized_space=serialized, warehouse_id=args.warehouse_id, **fields
            )
            print(f"updated Genie space '{title}' ({existing.space_id})")
        else:
            space = w.genie.create_space(args.warehouse_id, serialized, parent_path=args.parent_path, **fields)
            print(f"created Genie space '{title}' ({space.space_id})")


if __name__ == "__main__":
    main()
