from atlas.models import Dataset, Edge, Node
from atlas.validate import suggest, validate_dataset


def _node(node_id: str, line: int | None = None) -> Node:
    return Node(id=node_id, name=node_id, system="unity", kind="relic", line=line)


def _edge(src: str, dst: str, line: int | None = None) -> Edge:
    return Edge(
        **{"from": src, "to": dst, "rel": "boosts", "source": "observed", "line": line}
    )


def test_clean_dataset_has_no_problems():
    ds = Dataset(nodes=[_node("relic-69"), _node("atoms-gain")],
                 edges=[_edge("relic-69", "atoms-gain")])
    assert validate_dataset(ds) == []


def test_dangling_reference_is_an_error():
    ds = Dataset(nodes=[_node("relic-69")], edges=[_edge("relic-96", "relic-69", line=12)])
    problems = validate_dataset(ds)
    assert len(problems) == 1
    assert problems[0].severity == "error"
    assert problems[0].line == 12
    assert "relic-96" in problems[0].message


def test_dangling_reference_suggests_closest_id():
    ds = Dataset(nodes=[_node("relic-69")], edges=[_edge("relic-96", "relic-69")])
    problems = validate_dataset(ds)
    assert "did you mean 'relic-69'?" in problems[0].message


def test_no_suggestion_when_nothing_is_close():
    ds = Dataset(nodes=[_node("relic-69")], edges=[_edge("zzzzzzzz", "relic-69")])
    assert "did you mean" not in validate_dataset(ds)[0].message


def test_duplicate_node_ids_are_an_error():
    ds = Dataset(nodes=[_node("relic-69", line=2), _node("relic-69", line=8)], edges=[])
    problems = validate_dataset(ds)
    assert len(problems) == 1
    assert "duplicate node id 'relic-69'" in problems[0].message
    assert problems[0].line == 8


def test_self_edge_is_an_error():
    ds = Dataset(nodes=[_node("relic-69")], edges=[_edge("relic-69", "relic-69")])
    problems = validate_dataset(ds)
    assert len(problems) == 1
    assert "self-edge" in problems[0].message


def test_both_endpoints_dangling_reports_twice():
    ds = Dataset(nodes=[_node("a")], edges=[_edge("x", "y")])
    assert len(validate_dataset(ds)) == 2


def test_suggest_returns_none_for_empty_candidates():
    assert suggest("anything", []) is None


def test_problem_render_includes_path_and_line():
    ds = Dataset(nodes=[_node("a")], edges=[_edge("b", "a", line=42)])
    rendered = validate_dataset(ds)[0].render("data/relationships.yaml")
    assert rendered.startswith("data/relationships.yaml:42  error  ")
