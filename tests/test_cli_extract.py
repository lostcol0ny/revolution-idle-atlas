import os
import subprocess
import sys
from pathlib import Path

from atlas.cli import main
from atlas.extract.result import DroppedEdge, ExtractResult
from atlas.loader import load_dataset
from atlas.models import Edge, Kind, Node

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


def test_run_all_prunes_dangling_edges(tmp_path, monkeypatch):
    """run_all must call prune_dangling — replacing it with `return combined` is silent.

    The real corpus currently has zero dangling edges, so the CI artifact check
    cannot catch a missing call. This test wires a stub parser that emits an edge
    pointing at a node no parser mints, then asserts that edge is absent from the
    result and present in `dropped`.
    """
    import types

    import atlas.extract as extract_module
    from atlas.extract.result import ExtractResult

    known_node = Node(id="relic-1", name="One", system="relics", kind=Kind.RELIC)
    # "ghost-node" is never produced by any parser, so this edge is dangling.
    dangling_edge = Edge(
        **{"from": "relic-1", "to": "ghost-node", "rel": "boosts", "source": "Relics"}
    )

    stub_with_dangling = ExtractResult(nodes=[known_node], edges=[dangling_edge])
    filler = ExtractResult(
        nodes=[Node(id="filler", name="Filler", system="relics", kind=Kind.RELIC)],
        edges=[],
    )

    # Build four SimpleNamespace stubs so run_all's module-tuple iteration works
    # without touching the filesystem or the network.
    def _stub(result: ExtractResult) -> types.SimpleNamespace:
        return types.SimpleNamespace(extract=lambda _raw_dir: result)

    monkeypatch.setattr(extract_module, "relics", _stub(stub_with_dangling))
    monkeypatch.setattr(extract_module, "refine_tree", _stub(filler))
    monkeypatch.setattr(extract_module, "tarot", _stub(filler))
    monkeypatch.setattr(extract_module, "elements", _stub(filler))

    raw_dir = tmp_path / "data" / "raw"
    raw_dir.mkdir(parents=True)

    result = extract_module.run_all(raw_dir)

    edge_pairs = [(e.from_, e.to) for e in result.edges]
    assert ("relic-1", "ghost-node") not in edge_pairs

    dropped_pairs = [(d.from_id, d.to_id) for d in result.dropped]
    assert ("relic-1", "ghost-node") in dropped_pairs


def test_build_merges_the_derived_file_when_present(tmp_path):
    data = tmp_path / "data"
    data.mkdir(parents=True)
    # relic-38 appears in both files: derived has the raw name, curated overrides it.
    # relic-39 appears only in derived: the merged output must include it, which
    # proves that derived.yaml was actually read (not just the curated file alone).
    (data / "derived.yaml").write_text(
        "nodes:\n"
        "  - id: relic-38\n"
        "    name: Relic 38\n"
        "    system: relics\n"
        "    kind: relic\n"
        "  - id: relic-39\n"
        "    name: Relic 39\n"
        "    system: relics\n"
        "    kind: relic\n"
        "edges: []\n",
        encoding="utf-8",
    )
    (data / "relationships.yaml").write_text(
        "nodes:\n"
        "  - id: relic-38\n"
        "    name: Smart Man\n"
        "    system: relics\n"
        "    kind: relic\n"
        "edges: []\n",
        encoding="utf-8",
    )

    assert main(["build", "--root", str(tmp_path)]) == 0

    import json

    doc = json.loads((tmp_path / "public" / "graph.json").read_text(encoding="utf-8"))
    names = [n["name"] for n in doc["nodes"]]
    # relic-39 only exists in derived.yaml — if it's absent, derived was never read.
    assert "Relic 39" in names
    # Curated name wins for relic-38.
    assert "Smart Man" in names
    assert "Relic 38" not in names


def test_build_warns_about_a_suppression_that_matches_nothing(tmp_path, capsys):
    data = tmp_path / "data"
    data.mkdir(parents=True)
    (data / "relationships.yaml").write_text(
        "nodes: []\n"
        "edges: []\n"
        "suppress:\n"
        "  - from: relic-1\n"
        "    to: relic-2\n"
        "    rel: boosts\n"
        "    reason: the wiki removed this sentence\n",
        encoding="utf-8",
    )
    (data / "derived.yaml").write_text("nodes: []\nedges: []\n", encoding="utf-8")

    # A stale suppression is a warning, so the build still succeeds.
    assert main(["build", "--root", str(tmp_path)]) == 0
    assert "matches no edge" in capsys.readouterr().err


def test_build_works_when_the_derived_file_is_absent(tmp_path):
    import json

    data = tmp_path / "data"
    data.mkdir(parents=True)
    (data / "relationships.yaml").write_text(
        "nodes:\n"
        "  - id: singularity\n"
        "    name: Singularity\n"
        "    system: unity\n"
        "    kind: currency\n"
        "edges: []\n",
        encoding="utf-8",
    )
    # A missing generated file degrades to the curated file alone rather than
    # failing: a fresh clone that has not run `atlas extract` still builds.
    assert main(["build", "--root", str(tmp_path)]) == 0

    doc = json.loads((tmp_path / "public" / "graph.json").read_text(encoding="utf-8"))
    # The curated node must appear in the output — an empty graph would also exit 0.
    node_ids = [n["id"] for n in doc["nodes"]]
    assert "singularity" in node_ids


def test_build_applies_a_curated_suppression_when_the_derived_file_is_absent(
    tmp_path,
):
    """Suppression must not depend on `derived.yaml` existing.

    A branch that skips the merge when the generated file is absent makes every
    curated-vs-curated suppression silently inert, which is the one failure the
    `suppress` mechanism cannot survive: the edge stays and nothing says so.
    """
    data = tmp_path / "data"
    data.mkdir(parents=True)
    (data / "relationships.yaml").write_text(
        "nodes:\n"
        "  - id: a\n"
        "    name: A\n"
        "    system: relics\n"
        "    kind: relic\n"
        "  - id: b\n"
        "    name: B\n"
        "    system: relics\n"
        "    kind: relic\n"
        "edges:\n"
        "  - from: a\n"
        "    to: b\n"
        "    rel: boosts\n"
        "    source: wiki\n"
        "suppress:\n"
        "  - from: a\n"
        "    to: b\n"
        "    rel: boosts\n"
        "    reason: the wiki sentence was a comparison\n",
        encoding="utf-8",
    )
    assert not (data / "derived.yaml").exists()

    assert main(["build", "--root", str(tmp_path)]) == 0

    import json

    doc = json.loads((tmp_path / "public" / "graph.json").read_text(encoding="utf-8"))
    assert doc["edges"] == []


def test_build_reports_a_duplicate_node_id_in_the_curated_file(tmp_path, capsys):
    """Merging collapses ids into a dict, so merge must catch this itself.

    With `derived.yaml` present the merge runs before `validate_dataset`, and
    the dict has already discarded one of the two records by the time the
    validator looks. Without merge reporting it, a curated record vanishes in
    silence and the build still exits 0.
    """
    data = tmp_path / "data"
    data.mkdir(parents=True)
    (data / "relationships.yaml").write_text(
        "nodes:\n"
        "  - id: relic-1\n"
        "    name: One\n"
        "    system: relics\n"
        "    kind: relic\n"
        "  - id: relic-1\n"
        "    name: Duplicate\n"
        "    system: relics\n"
        "    kind: relic\n"
        "edges: []\n",
        encoding="utf-8",
    )
    (data / "derived.yaml").write_text("nodes: []\nedges: []\n", encoding="utf-8")

    assert main(["build", "--root", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    line = next(ln for ln in err.splitlines() if "duplicate node id 'relic-1'" in ln)
    # Asserting only the message substring lets any filename through, which is
    # how the derived-side mislabelling in the next test went unnoticed.
    assert line.startswith("data/relationships.yaml:")
    # An error must block the artifact, not merely be printed alongside it.
    assert not (tmp_path / "public" / "graph.json").exists()


def test_build_names_the_derived_file_for_a_duplicate_it_contains(tmp_path, capsys):
    """A generated duplicate must name `derived.yaml`, not the curated file.

    These problems are built before the merge nulls derived line numbers, so
    they carry a line pointing into `derived.yaml`. Rendering them under the
    curated path sends the reader to the wrong file *and* to a line that means
    something else there — or, as here, does not exist in it at all.

    This fires exactly when the extractor has a bug, which is when a wrong
    pointer costs the most.
    """
    data = tmp_path / "data"
    data.mkdir(parents=True)
    # Two lines long, so a derived line number rendered against this file is
    # visibly past EOF rather than plausibly correct.
    (data / "relationships.yaml").write_text("nodes: []\nedges: []\n", encoding="utf-8")
    (data / "derived.yaml").write_text(
        "nodes:\n"
        "  - id: a\n    name: A\n    system: relics\n    kind: relic\n"
        "  - id: b\n    name: B\n    system: relics\n    kind: relic\n"
        "  - id: b\n    name: B2\n    system: relics\n    kind: relic\n"
        "edges: []\n",
        encoding="utf-8",
    )

    assert main(["build", "--root", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    line = next(ln for ln in err.splitlines() if "duplicate node id 'b'" in ln)

    assert line.startswith("data/derived.yaml:")
    assert "relationships.yaml" not in line


def test_each_problem_is_labelled_with_the_file_it_can_be_found_in(tmp_path, capsys):
    """Both halves of the labelling rule, in one build.

    A line number is always a curated line number — `merge` nulls `line` on
    every derived record — so a problem carrying one must name the curated
    file, and a problem without one must not. Asserting only the derived half
    would let "label everything generically" pass, which regresses the main
    curation loop; asserting only the curated half would let the original
    blame-everything-on-relationships.yaml bug back in.
    """
    data = tmp_path / "data"
    data.mkdir(parents=True)
    (data / "relationships.yaml").write_text(
        "nodes:\n"
        "  - id: c1\n"
        "    name: C1\n"
        "    system: relics\n"
        "    kind: relic\n"
        "edges:\n"
        "  - from: c1\n"
        "    to: curated-ghost\n"
        "    rel: boosts\n"
        "    source: wiki\n",
        encoding="utf-8",
    )
    (data / "derived.yaml").write_text(
        "nodes:\n"
        "  - id: d1\n"
        "    name: D1\n"
        "    system: relics\n"
        "    kind: relic\n"
        "edges:\n"
        "  - from: d1\n"
        "    to: derived-ghost\n"
        "    rel: boosts\n"
        "    source: Relics\n",
        encoding="utf-8",
    )

    assert main(["build", "--root", str(tmp_path)]) == 1
    lines = capsys.readouterr().err.splitlines()

    curated_line = next(line for line in lines if "curated-ghost" in line)
    derived_line = next(line for line in lines if "derived-ghost" in line)

    # The curated record has a line number, so it names a file and a position.
    assert curated_line.startswith("data/relationships.yaml:")
    # The derived record's line was nulled by the merge, so it cannot claim one.
    assert derived_line.startswith("dataset ")
    assert "data/relationships.yaml" not in derived_line


def test_build_fails_loudly_on_a_malformed_derived_file(tmp_path, capsys):
    """A corrupt generated file must stop the build, not be skipped.

    Falling through to a curated-only graph would quietly drop every generated
    node and still exit 0, which looks identical to a successful build.
    """
    data = tmp_path / "data"
    data.mkdir(parents=True)
    (data / "relationships.yaml").write_text(
        "nodes:\n"
        "  - id: singularity\n"
        "    name: Singularity\n"
        "    system: unity\n"
        "    kind: currency\n"
        "edges: []\n",
        encoding="utf-8",
    )
    (data / "derived.yaml").write_text("nodes: [oops\n", encoding="utf-8")

    assert main(["build", "--root", str(tmp_path)]) == 1
    assert "derived.yaml" in capsys.readouterr().err
    assert not (tmp_path / "public" / "graph.json").exists()
