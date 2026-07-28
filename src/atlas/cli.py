import argparse
import json
import sys
from pathlib import Path

from atlas.coverage import analyse, load_inventory, render_markdown
from atlas.loader import SchemaError, load_dataset
from atlas.problems import Problem
from atlas.rawcheck import check_against_raw
from atlas.render import to_graph
from atlas.validate import validate_dataset

DATASET_REL_PATH = Path("data") / "relationships.yaml"


def _report(problems: list[Problem], path: str) -> None:
    for problem in problems:
        print(problem.render(path), file=sys.stderr)


def _build(root: Path, check_only: bool) -> int:
    dataset_path = root / DATASET_REL_PATH
    display_path = str(DATASET_REL_PATH)

    try:
        dataset = load_dataset(dataset_path)
    except FileNotFoundError:
        print(f"{display_path}: not found", file=sys.stderr)
        return 1
    except SchemaError as exc:
        for problem in exc.problems:
            print(f"{display_path}  error  {problem}", file=sys.stderr)
        return 1

    errors = validate_dataset(dataset)
    warnings = check_against_raw(dataset, root / "data" / "raw")
    _report(errors + warnings, display_path)

    if errors:
        print(f"{len(errors)} error(s) — not writing output", file=sys.stderr)
        return 1

    inventory = load_inventory(root / "data" / "inventory.yaml")
    report = analyse(dataset, inventory=inventory)
    print(
        f"ok: {report.node_count} nodes, {report.edge_count} edges, "
        f"{len(report.orphans)} orphans, {len(warnings)} warning(s)"
    )

    if check_only:
        return 0

    graph_path = root / "public" / "graph.json"
    graph_path.parent.mkdir(parents=True, exist_ok=True)
    graph_path.write_text(json.dumps(to_graph(dataset), indent=2) + "\n", encoding="utf-8")

    coverage_path = root / "docs" / "coverage.md"
    coverage_path.parent.mkdir(parents=True, exist_ok=True)
    coverage_path.write_text(render_markdown(report), encoding="utf-8")

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="atlas")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="validate the dataset and render graph.json")
    build.add_argument("--root", type=Path, default=Path.cwd())
    build.add_argument(
        "--check", action="store_true", help="validate only; write no files"
    )

    args = parser.parse_args(argv)
    if args.command == "build":
        return _build(args.root, args.check)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
