import argparse
import json
import os
import sys
from pathlib import Path

import yaml

from atlas.coverage import analyse, load_inventory, page_title, render_markdown
from atlas.extract import ExtractError, run_all
from atlas.extract.emit import to_yaml
from atlas.extract.manifest import load_manifest
from atlas.extract.refs import SurfaceFormCollision
from atlas.extract.vocab import build_vocabulary
from atlas.loader import SchemaError, load_dataset
from atlas.merge import merge
from atlas.models import Dataset
from atlas.problems import Problem
from atlas.rawcheck import check_against_raw
from atlas.render import to_graph
from atlas.scrape import ScrapeError, fetch_pages, make_client, write_raw
from atlas.validate import validate_dataset

DATASET_REL_PATH = Path("data") / "relationships.yaml"
DERIVED_REL_PATH = Path("data") / "derived.yaml"
SWEEP_REL_PATH = Path("data") / "sweep.yaml"
# Used when a problem cannot be pinned to a single file. See _report.
MERGED_LABEL = "dataset"
# Extraction warnings come from more than one source — a manifest page that
# reads empty, a tarot card whose name another node claims — and no single file
# is the one to open for all of them, so each message names its own subject.
EXTRACT_LABEL = "extract"


def _report(problems: list[Problem], curated_path: str) -> None:
    """Print each problem against a file the reader can actually open.

    A problem that knows its own file renders under it — `Problem.render`
    handles that. This chooses the fallback for the ones that do not, which
    are the problems found after the merge, against a dataset with no
    provenance left in it. There a line number can only have come from a
    curated record, since `merge` nulls `line` on every derived one, and using
    it is worth it because curating `relationships.yaml` is the main loop. A
    line-less problem cannot be pinned to a file at all, so it gets the
    neutral label.
    """
    for problem in problems:
        fallback = curated_path if problem.line is not None else MERGED_LABEL
        print(problem.render(fallback), file=sys.stderr)


def _load(path: Path, display_path: str) -> Dataset | None:
    """Load one dataset file, printing any failure. None means "do not build"."""
    try:
        return load_dataset(path)
    except SchemaError as exc:
        for problem in exc.problems:
            print(f"{display_path}  error  {problem}", file=sys.stderr)
    except yaml.YAMLError as exc:
        # PyYAML names the source "<unicode string>" because the loader is built
        # from text, so the real path has to come from us.
        print(f"{display_path}: invalid YAML: {exc}", file=sys.stderr)
    return None


def _build(root: Path, check_only: bool) -> int:
    dataset_path = root / DATASET_REL_PATH
    display_path = str(DATASET_REL_PATH)

    if not dataset_path.is_file():
        print(f"{display_path}: not found", file=sys.stderr)
        return 1

    curated = _load(dataset_path, display_path)
    if curated is None:
        return 1

    # A missing generated file degrades to an empty one rather than skipping the
    # merge: `suppress` and the duplicate-id check are merge's job, and a branch
    # that bypasses it would make both silently inert on a fresh clone.
    derived_path = root / DERIVED_REL_PATH
    derived = Dataset()
    if derived_path.is_file():
        loaded = _load(derived_path, str(DERIVED_REL_PATH))
        if loaded is None:
            return 1
        derived = loaded

    dataset, merge_problems = merge(
        derived,
        curated,
        derived_path=str(DERIVED_REL_PATH),
        curated_path=display_path,
    )

    raw_dir = root / "data" / "raw"
    problems = (
        merge_problems
        + validate_dataset(dataset)
        + check_against_raw(dataset, raw_dir)
    )
    errors = [p for p in problems if p.severity == "error"]
    warning_count = len(problems) - len(errors)
    _report(problems, display_path)

    if errors:
        print(f"{len(errors)} error(s) — not writing output", file=sys.stderr)
        return 1

    inventory = load_inventory(root / "data" / "inventory.yaml")
    raw_pages = {
        page_title(path.name): path.stat().st_size
        for path in sorted(raw_dir.glob("*.wikitext"))
    } if raw_dir.is_dir() else None
    report = analyse(dataset, inventory=inventory, raw_pages=raw_pages)
    print(
        f"ok: {report.node_count} nodes, {report.edge_count} edges, "
        f"{len(report.orphans)} orphans, {warning_count} warning(s)"
    )

    if check_only:
        return 0

    graph_path = root / "public" / "graph.json"
    graph_path.parent.mkdir(parents=True, exist_ok=True)
    # ensure_ascii=False: graph.json is committed and read as a diff by humans,
    # and a name like "Café" is unreadable once escaped to "Café".
    graph_path.write_text(
        json.dumps(to_graph(dataset), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    coverage_path = root / "docs" / "coverage.md"
    coverage_path.parent.mkdir(parents=True, exist_ok=True)
    coverage_path.write_text(render_markdown(report), encoding="utf-8")

    return 0


def _extract(root: Path) -> int:
    raw_dir = root / "data" / "raw"
    if not raw_dir.is_dir():
        print(
            "data/raw/: not found — the scrape workflow populates it",
            file=sys.stderr,
        )
        return 1

    # The curated file supplies the vocabulary. Missing is tolerated — extract
    # did not read this file before, and requiring it would break a bare tree.
    # Malformed is not: an empty vocabulary and a broken one are
    # indistinguishable downstream, since both simply stop producing stat edges.
    curated_path = root / DATASET_REL_PATH
    curated = Dataset()
    if curated_path.is_file():
        loaded = _load(curated_path, str(DATASET_REL_PATH))
        if loaded is None:
            return 1
        curated = loaded

    try:
        result = run_all(
            raw_dir,
            build_vocabulary(curated.nodes),
            frozenset(curated.node_ids()),
            manifest=load_manifest(root / SWEEP_REL_PATH),
        )
    except SurfaceFormCollision as exc:
        print(f"{DATASET_REL_PATH}  error  {exc}", file=sys.stderr)
        return 1
    except ExtractError as exc:
        print(f"extract failed: {exc}", file=sys.stderr)
        return 1

    for warning in result.warnings:
        print(f"{EXTRACT_LABEL}  warning  {warning}", file=sys.stderr)

    for dropped in result.dropped:
        print(
            f"{DERIVED_REL_PATH}  warning  dropped edge "
            f"'{dropped.from_id}' -> '{dropped.to_id}': {dropped.reason}",
            file=sys.stderr,
        )

    derived_path = root / DERIVED_REL_PATH
    derived_path.parent.mkdir(parents=True, exist_ok=True)
    # Write-then-rename: write_text truncates in place, so an interrupted run
    # would leave a half-written derived.yaml that the next `atlas build` reads
    # as a corrupt dataset. The temp file sits in the destination directory so
    # os.replace stays within one filesystem, where it is atomic.
    staged_path = derived_path.with_suffix(".yaml.tmp")
    staged_path.write_text(to_yaml(result), encoding="utf-8")
    os.replace(staged_path, derived_path)

    print(
        f"ok: {len(result.nodes)} nodes, {len(result.edges)} edges, "
        f"{len(result.dropped)} dropped edge(s)"
    )
    return 0


def _scrape(root: Path) -> int:
    try:
        with make_client() as client:
            pages = fetch_pages(client)
        count = write_raw(pages, root / "data" / "raw")
    except ScrapeError as exc:
        print(f"scrape failed: {exc}", file=sys.stderr)
        return 1
    print(f"ok: wrote {count} pages to data/raw/")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="atlas")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="validate the dataset and render graph.json")
    build.add_argument("--root", type=Path, default=Path.cwd())
    build.add_argument(
        "--check", action="store_true", help="validate only; write no files"
    )

    extract = sub.add_parser(
        "extract", help="parse data/raw/ into the generated data/derived.yaml"
    )
    extract.add_argument("--root", type=Path, default=Path.cwd())

    scrape = sub.add_parser("scrape", help="fetch raw wikitext into data/raw/")
    scrape.add_argument("--root", type=Path, default=Path.cwd())

    args = parser.parse_args(argv)
    if args.command == "build":
        return _build(args.root, args.check)
    if args.command == "extract":
        return _extract(args.root)
    if args.command == "scrape":
        return _scrape(args.root)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
