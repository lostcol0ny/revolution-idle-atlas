import argparse
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path

import yaml

from atlas.coverage import analyse, load_inventory, page_title, render_markdown
from atlas.extract import ExtractError, run_all
from atlas.extract.emit import to_yaml
from atlas.extract.manifest import load_manifest
from atlas.extract.refs import SurfaceFormCollision
from atlas.extract.vocab import build_vocabulary
from atlas.game import (
    CATALOG_REL_PATH,
    DEFAULT_INSTALL,
    STRINGS_REL_PATH,
    GameError,
    find_families,
    read_install,
    write_outputs,
)
from atlas.gamemap import (
    ACHIEVEMENT_PREFIX,
    GAME_FILE_REL_PATH,
    grade_thresholds,
    map_achievements,
    map_catalog,
    map_particles,
    wiki_achievements,
)
from atlas.gamemap import to_yaml as game_to_yaml
from atlas.loader import SchemaError, load_dataset, load_game
from atlas.merge import merge
from atlas.models import Dataset, GameData
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
# `atlas game` lists this many unmatched entities per family, then a count.
UNMATCHED_SHOWN = 10


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


def _load[T](path: Path, display_path: str, loader: Callable[[Path], T]) -> T | None:
    """Load one input file, printing any failure. None means "do not build"."""
    try:
        return loader(path)
    except SchemaError as exc:
        for problem in exc.problems:
            print(f"{display_path}  error  {problem}", file=sys.stderr)
    except yaml.YAMLError as exc:
        # PyYAML names the source "<unicode string>" because the loader is built
        # from text, so the real path has to come from us.
        print(f"{display_path}: invalid YAML: {exc}", file=sys.stderr)
    return None


def _load_inputs(root: Path) -> tuple[Dataset, Dataset] | None:
    """Load the derived and curated datasets, printing any failure."""
    dataset_path = root / DATASET_REL_PATH
    if not dataset_path.is_file():
        print(f"{DATASET_REL_PATH}: not found", file=sys.stderr)
        return None

    curated = _load(dataset_path, str(DATASET_REL_PATH), load_dataset)
    if curated is None:
        return None

    # A missing generated file degrades to an empty one rather than skipping the
    # merge: `suppress` and the duplicate-id check are merge's job, and a branch
    # that bypasses it would make both silently inert on a fresh clone.
    derived_path = root / DERIVED_REL_PATH
    derived = Dataset()
    if derived_path.is_file():
        loaded = _load(derived_path, str(DERIVED_REL_PATH), load_dataset)
        if loaded is None:
            return None
        derived = loaded
    return derived, curated


def _load_game_file(root: Path) -> GameData | None:
    """Load data/game.yaml, printing any failure. None means "do not build".

    Absent on a checkout that has never run `atlas game`, and then empty: the
    build is exactly the two-file merge, and extraction adds no game edges.
    """
    game_path = root / GAME_FILE_REL_PATH
    if not game_path.is_file():
        return GameData()
    return _load(game_path, str(GAME_FILE_REL_PATH), load_game)


def _build(root: Path, check_only: bool) -> int:
    display_path = str(DATASET_REL_PATH)
    inputs = _load_inputs(root)
    if inputs is None:
        return 1
    derived, curated = inputs

    game = _load_game_file(root)
    if game is None:
        return 1

    dataset, merge_problems = merge(
        derived,
        curated,
        derived_path=str(DERIVED_REL_PATH),
        curated_path=display_path,
        game=game,
        game_path=str(GAME_FILE_REL_PATH),
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
        loaded = _load(curated_path, str(DATASET_REL_PATH), load_dataset)
        if loaded is None:
            return 1
        curated = loaded

    game = _load_game_file(root)
    if game is None:
        return 1

    try:
        result = run_all(
            raw_dir,
            build_vocabulary(curated.nodes),
            frozenset(curated.node_ids()),
            manifest=load_manifest(root / SWEEP_REL_PATH),
            game=game,
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


def _game(root: Path, install: Path) -> int:
    try:
        dump = read_install(install)
    except GameError as exc:
        print(f"game failed: {exc}", file=sys.stderr)
        return 1
    families = find_families(dump["strings"])
    write_outputs(root, dump, families)
    print(
        f"ok: {len(dump['strings'])} strings (buildid {dump['buildid']}, "
        f"Unity {dump['unity']}) to {STRINGS_REL_PATH.as_posix()}"
    )
    print(f"ok: {len(families)} families to {CATALOG_REL_PATH.as_posix()}")
    for prefix, entries in families.items():
        print(f"  {prefix}: {len(entries)}")

    inputs = _load_inputs(root)
    if inputs is None:
        return 1
    # Mapped against wiki ids only: the previous game file must not vouch for
    # the nodes it added itself.
    dataset, _ = merge(*inputs)
    game, reports, skipped = map_catalog(families, dataset.nodes, dump["buildid"])
    # The wiki numbers grade bonuses by threshold; the game only by position.
    particles_page = root / "data" / "raw" / "Particles.wikitext"
    thresholds = (
        grade_thresholds(particles_page.read_text(encoding="utf-8"))
        if particles_page.is_file()
        else {}
    )
    particles, particle_reports = map_particles(
        dump["strings"], dataset.nodes, thresholds
    )
    game.nodes.extend(particles)
    reports.update(particle_reports)
    achievements_page = root / "data" / "raw" / "Achievements.wikitext"
    achievements, reports[ACHIEVEMENT_PREFIX] = map_achievements(
        dump["strings"],
        dataset.nodes,
        wiki_achievements(achievements_page.read_text(encoding="utf-8"))
        if achievements_page.is_file()
        else {},
    )
    game.nodes.extend(achievements)
    (root / GAME_FILE_REL_PATH).write_text(
        game_to_yaml(game), encoding="utf-8", newline="\n"
    )
    print(f"ok: {len(game.nodes)} nodes to {GAME_FILE_REL_PATH.as_posix()}")
    for prefix, report in reports.items():
        print(
            f"  {prefix}: {report.matched} matched, {report.added} added, "
            f"{len(report.unmatched)} unmatched"
        )
        for line in report.renamed:
            print(f"    renamed {line}")
        if report.left_out:
            print(f"    left out {report.left_out} with no reward")
        for line in report.unmatched[:UNMATCHED_SHOWN]:
            print(f"    unmatched {line}")
        if len(report.unmatched) > UNMATCHED_SHOWN:
            print(f"    ... {len(report.unmatched) - UNMATCHED_SHOWN} more unmatched")
    if skipped:
        print(f"  skipped, no system to map onto: {', '.join(skipped)}")
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

    game = sub.add_parser(
        "game",
        help="read English strings from a local game install into data/game/, "
        "and map them onto graph nodes in data/game.yaml",
    )
    game.add_argument("--root", type=Path, default=Path.cwd())
    game.add_argument("--install", type=Path, default=DEFAULT_INSTALL)

    args = parser.parse_args(argv)
    if args.command == "build":
        return _build(args.root, args.check)
    if args.command == "extract":
        return _extract(args.root)
    if args.command == "scrape":
        return _scrape(args.root)
    if args.command == "game":
        return _game(args.root, args.install)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
