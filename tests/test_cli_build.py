import json
import shutil
from pathlib import Path

from atlas.cli import main

FIXTURES = Path(__file__).parent / "fixtures"


def _project(tmp_path: Path) -> Path:
    (tmp_path / "data").mkdir()
    shutil.copy(FIXTURES / "minimal.yaml", tmp_path / "data" / "relationships.yaml")
    return tmp_path


def test_build_writes_graph_and_coverage(tmp_path):
    root = _project(tmp_path)
    assert main(["build", "--root", str(root)]) == 0
    graph = json.loads((root / "public" / "graph.json").read_text())
    assert len(graph["nodes"]) == 2
    assert (root / "docs" / "coverage.md").is_file()


def test_check_mode_writes_nothing(tmp_path):
    root = _project(tmp_path)
    assert main(["build", "--root", str(root), "--check"]) == 0
    assert not (root / "public" / "graph.json").exists()


def test_validation_error_returns_nonzero_and_writes_nothing(tmp_path):
    root = _project(tmp_path)
    (root / "data" / "relationships.yaml").write_text(
        "nodes:\n"
        "  - id: a\n"
        "    name: A\n"
        "    system: unity\n"
        "    kind: relic\n"
        "edges:\n"
        "  - from: ghost\n"
        "    to: a\n"
        "    rel: boosts\n"
        "    source: observed\n"
    )
    assert main(["build", "--root", str(root)]) == 1
    assert not (root / "public" / "graph.json").exists()


def test_warnings_do_not_fail_the_build(tmp_path, capsys):
    root = _project(tmp_path)
    raw = root / "data" / "raw"
    raw.mkdir()
    # Minerals__Refine_Tree.wikitext is deliberately absent so the missing-page
    # warning actually fires; without it this test would assert nothing.
    (raw / "Singularity.wikitext").write_text("plain text, no marker")

    assert main(["build", "--root", str(root)]) == 0

    captured = capsys.readouterr()
    assert "warning" in captured.err
    assert "refine-node-121" in captured.err
    assert "1 warning(s)" in captured.out
    assert (root / "public" / "graph.json").is_file()


def test_malformed_yaml_returns_nonzero_and_names_the_file(tmp_path, capsys):
    root = _project(tmp_path)
    (root / "data" / "relationships.yaml").write_text("nodes: [unbalanced\n")

    assert main(["build", "--root", str(root)]) == 1

    captured = capsys.readouterr()
    assert "relationships.yaml" in captured.err
    assert not (root / "public" / "graph.json").exists()
