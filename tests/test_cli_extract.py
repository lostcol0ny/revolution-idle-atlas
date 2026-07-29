from pathlib import Path

import pytest
import yaml

from atlas.cli import main
from atlas.loader import load_dataset

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
    assert derived.read_text(encoding="utf-8") == first
