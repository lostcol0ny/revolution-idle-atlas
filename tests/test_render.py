import json
from pathlib import Path

from atlas.loader import load_dataset
from atlas.models import Dataset, Edge, Effect, Kind, Node, Op, SystemDef
from atlas.render import to_graph

FIXTURES = Path(__file__).parent / "fixtures"


def test_graph_has_schema_version_and_counts(node, edge):
    ds = Dataset(nodes=[node("a"), node("b")], edges=[edge("a", "b")])
    graph = to_graph(ds)
    assert graph["version"] == 1
    assert len(graph["nodes"]) == 2
    assert len(graph["edges"]) == 1


def test_edge_uses_from_not_from_underscore(node, edge):
    ds = Dataset(nodes=[node("a"), node("b")], edges=[edge("a", "b")])
    serialised = to_graph(ds)["edges"][0]
    assert serialised["from"] == "a"
    assert "from_" not in serialised


def test_none_fields_are_omitted(node, edge):
    ds = Dataset(nodes=[node("a"), node("b")], edges=[edge("a", "b")])
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


def _node(**overrides):
    base = {"id": "relic-1", "name": "Relic 1", "system": "relics", "kind": "relic"}
    return Node(**(base | overrides))


def test_empty_effects_are_omitted_entirely():
    doc = to_graph(Dataset(nodes=[_node()]))
    assert "effects" not in doc["nodes"][0]


def test_populated_effects_are_emitted():
    node = _node(effects=[{"text": "Boosts gold", "per_level": "+0.01", "op": "add"}])
    doc = to_graph(Dataset(nodes=[node]))
    assert doc["nodes"][0]["effects"] == [
        {"op": "add", "per_level": "+0.01", "text": "Boosts gold"}
    ]


def test_systems_key_is_absent_when_no_systems_are_declared():
    doc = to_graph(Dataset(nodes=[_node()]))
    assert "systems" not in doc


def test_systems_are_emitted_when_declared():
    ds = Dataset(
        systems=[SystemDef(id="unity", name="Unity"), SystemDef(id="relics", name="Relics", parent="unity")],
        nodes=[_node()],
    )
    doc = to_graph(ds)
    assert doc["systems"] == [
        {"id": "unity", "name": "Unity"},
        {"id": "relics", "name": "Relics", "parent": "unity"},
    ]


def test_targets_effect_is_omitted_when_unset_and_emitted_when_set():
    bare = Edge(**{"from": "a", "to": "b", "rel": "boosts", "source": "wiki:Relics"})
    pointed = Edge(
        **{
            "from": "a",
            "to": "b",
            "rel": "boosts",
            "source": "wiki:Relics",
            "targets_effect": 1,
        }
    )
    doc = to_graph(Dataset(edges=[bare, pointed]))
    assert "targets_effect" not in doc["edges"][0]
    assert doc["edges"][1]["targets_effect"] == 1


def test_document_key_order_is_version_nodes_edges_then_systems():
    ds = Dataset(systems=[SystemDef(id="unity", name="Unity")], nodes=[_node()])
    assert list(to_graph(ds)) == ["version", "nodes", "edges", "systems"]


def test_nested_effect_fields_are_dropped_when_unset():
    """`_clean` only reaches the top level; effects are nested one deeper.

    Asserted with `not in` rather than `.get(...) is None`, which passes both
    when the key is absent and when it is present-and-null — the exact
    distinction this test exists to make.
    """
    ds = Dataset(
        nodes=[
            Node(
                id="relic-1",
                name="One",
                system="relics",
                kind=Kind.RELIC,
                effects=[Effect(text="no op and no per_level here")],
            )
        ]
    )
    effect = to_graph(ds)["nodes"][0]["effects"][0]
    assert effect == {"text": "no op and no per_level here"}
    assert "op" not in effect
    assert "per_level" not in effect


def test_nested_effect_fields_are_kept_when_set():
    """The guard against fixing the null by dropping the field entirely.

    Without this, `_clean`-recurses and `del effect["op"]` are
    indistinguishable, and the second one silently deletes real data.
    """
    ds = Dataset(
        nodes=[
            Node(
                id="relic-1",
                name="One",
                system="relics",
                kind=Kind.RELIC,
                effects=[Effect(text="boosts things", per_level="+0.2", op=Op.ADD)],
            )
        ]
    )
    effect = to_graph(ds)["nodes"][0]["effects"][0]
    assert effect == {"text": "boosts things", "per_level": "+0.2", "op": "add"}
