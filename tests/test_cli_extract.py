import os
import subprocess
import sys
from pathlib import Path

from atlas.cli import main
from atlas.extract.result import DroppedEdge, ExtractResult
from atlas.loader import load_dataset
from atlas.models import Kind, Node

REAL_RAW = Path(__file__).resolve().parents[1] / "data" / "raw"


def test_extract_writes_a_loadable_derived_file(tmp_path, capsys):
    raw = tmp_path / "data" / "raw"
    raw.mkdir(parents=True)
    for name in (
        "Relics.wikitext",
        "Minerals__Refine_Tree.wikitext",
        "Tarot.wikitext",
        "Elements.wikitext",
    ):
        (raw / name).write_text(
            (REAL_RAW / name).read_text(encoding="utf-8"), encoding="utf-8"
        )

    assert main(["extract", "--root", str(tmp_path)]) == 0

    derived = tmp_path / "data" / "derived.yaml"
    ds = load_dataset(derived)
    ids = {n.id for n in ds.nodes}
    assert "relic-38" in ids
    assert "refine-node-121" in ids
    assert "tarot-king-of-wands" in ids
    assert "fire-factor-3" in ids
    assert len(ds.nodes) > 250
    assert "ok:" in capsys.readouterr().out


def test_extract_reports_missing_raw_directory(tmp_path, capsys):
    assert main(["extract", "--root", str(tmp_path)]) == 1
    assert "data/raw" in capsys.readouterr().err


def test_extract_fails_when_a_source_yields_nothing(tmp_path, capsys):
    raw = tmp_path / "data" / "raw"
    raw.mkdir(parents=True)
    for path in REAL_RAW.glob("*.wikitext"):
        (raw / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    # A page the wiki renamed, or a table someone restructured, silently turns a
    # parser into a no-op. Zero is the one count worth hard-failing on: a floor
    # like "at least 70 relics" would break the day the game adds relic 71.
    (raw / "Relics.wikitext").write_text("== Relics ==\n", encoding="utf-8")

    assert main(["extract", "--root", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert "relics" in err
    assert not (tmp_path / "data" / "derived.yaml").exists()


def test_extract_leaves_no_dangling_edge_in_the_output(tmp_path):
    raw = tmp_path / "data" / "raw"
    raw.mkdir(parents=True)
    for path in REAL_RAW.glob("*.wikitext"):
        (raw / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")

    assert main(["extract", "--root", str(tmp_path)]) == 0

    ds = load_dataset(tmp_path / "data" / "derived.yaml")
    known = ds.node_ids()
    dangling = [
        (e.from_, e.to) for e in ds.edges if e.from_ not in known or e.to not in known
    ]
    assert dangling == []


def test_extract_is_idempotent(tmp_path):
    raw = tmp_path / "data" / "raw"
    raw.mkdir(parents=True)
    for path in REAL_RAW.glob("*.wikitext"):
        (raw / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")

    derived = tmp_path / "data" / "derived.yaml"
    assert main(["extract", "--root", str(tmp_path)]) == 0
    first = derived.read_text(encoding="utf-8")
    assert main(["extract", "--root", str(tmp_path)]) == 0
    # CI runs `git diff --exit-code` on this file. A run that is not
    # byte-identical to its predecessor turns every unrelated PR red.
    #
    # Both runs share one interpreter, so this cannot catch an ordering that
    # varies with the hash seed — set iteration is stable within a process.
    # test_extract_is_stable_across_hash_seeds covers that half.
    assert derived.read_text(encoding="utf-8") == first


def test_extract_is_stable_across_hash_seeds(tmp_path):
    """The real idempotency property: stable between *processes*, not calls.

    CI compares a fresh run against a file committed by an earlier run in a
    different interpreter. PYTHONHASHSEED randomises set iteration order, so a
    refactor that let a set reach the output would pass every same-process test
    and then flap in CI.
    """
    raw = tmp_path / "data" / "raw"
    raw.mkdir(parents=True)
    for path in REAL_RAW.glob("*.wikitext"):
        (raw / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")

    outputs = []
    for seed in ("0", "1"):
        root = tmp_path / f"run{seed}"
        (root / "data").mkdir(parents=True)
        (root / "data" / "raw").symlink_to(raw, target_is_directory=True)
        subprocess.run(
            [sys.executable, "-m", "atlas.cli", "extract", "--root", str(root)],
            check=True,
            capture_output=True,
            env={**os.environ, "PYTHONHASHSEED": seed},
        )
        outputs.append((root / "data" / "derived.yaml").read_text(encoding="utf-8"))

    assert outputs[0] == outputs[1]


def test_extract_warns_about_dropped_edges_but_still_succeeds(
    tmp_path, capsys, monkeypatch
):
    """A dropped edge is a warning, never an error.

    The resolver reads prose, so a wiki typo produces an id no parser minted.
    Failing the command would let one typo block every build, so the run must
    still write its output and still exit 0.
    """
    (tmp_path / "data" / "raw").mkdir(parents=True)

    stub = ExtractResult(
        nodes=[Node(id="relic-1", name="Kindling", system="relics", kind=Kind.RELIC)],
        edges=[],
        dropped=[
            DroppedEdge(
                from_id="relic-1",
                to_id="relic-99",
                reason="no extracted node with id relic-99",
            )
        ],
    )
    monkeypatch.setattr("atlas.cli.run_all", lambda _raw_dir: stub)

    assert main(["extract", "--root", str(tmp_path)]) == 0

    captured = capsys.readouterr()
    # Both endpoints are named so the fix is a relationships.yaml edit rather
    # than a debugging session.
    assert "relic-1" in captured.err
    assert "relic-99" in captured.err
    assert "no extracted node with id relic-99" in captured.err
    assert "warning" in captured.err
    assert (tmp_path / "data" / "derived.yaml").exists()
    assert "1 dropped edge(s)" in captured.out
