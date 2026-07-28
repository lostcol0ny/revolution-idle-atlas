import json

from atlas.loader import load_dataset
from atlas.render import to_graph
from tests.test_coverage import _edge, _node  # noqa: F401
from atlas.models import Dataset

from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def test_graph_has_schema_version_and_counts():
    ds = Dataset(nodes=[_node("a"), _node("b")], edges=[_edge("a", "b")])
    graph = to_graph(ds)
    assert graph["version"] == 1
    assert len(graph["nodes"]) == 2
    assert len(graph["edges"]) == 1


def test_edge_uses_from_not_from_underscore():
    ds = Dataset(nodes=[_node("a"), _node("b")], edges=[_edge("a", "b")])
    edge = to_graph(ds)["edges"][0]
    assert edge["from"] == "a"
    assert "from_" not in edge


def test_none_fields_are_omitted():
    ds = Dataset(nodes=[_node("a"), _node("b")], edges=[_edge("a", "b")])
    graph = to_graph(ds)
    assert "op" not in graph["edges"][0]
    assert "wiki" not in graph["nodes"][0]


def test_line_numbers_are_not_serialised():
    ds = load_dataset(FIXTURES / "minimal.yaml")
    graph = to_graph(ds)
    assert "line" not in graph["nodes"][0]
    assert "line" not in graph["edges"][0]


def test_output_is_deterministic():
    ds = load_dataset(FIXTURES / "minimal.yaml")
    assert json.dumps(to_graph(ds)) == json.dumps(to_graph(ds))


def test_matches_golden_file():
    ds = load_dataset(FIXTURES / "minimal.yaml")
    expected = json.loads((FIXTURES / "expected_graph.json").read_text())
    assert to_graph(ds) == expected
