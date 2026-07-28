from atlas.models import Dataset, Edge, Node
from atlas.problems import Problem
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


def test_suggest_near_miss_returns_closest():
    assert suggest("relic-96", ["relic-69"]) == "relic-69"


def test_suggest_no_match_returns_none():
    assert suggest("zzzzzzzz", ["relic-69"]) is None


def test_suggest_respects_the_similarity_cutoff():
    # 'atom'/'atoms-gain' scores ~0.571 — under the 0.6 cutoff but over a
    # loosened one. Pins the cutoff: a change to 0.3 would return a match here.
    assert suggest("atom", ["atoms-gain"]) is None


def test_problem_render_includes_path_and_line():
    ds = Dataset(nodes=[_node("a")], edges=[_edge("b", "a", line=42)])
    rendered = validate_dataset(ds)[0].render("data/relationships.yaml")
    assert rendered.startswith("data/relationships.yaml:42  error  ")


def test_problem_render_omits_line_when_none():
    p = Problem(severity="error", message="some problem", line=None)
    rendered = p.render("data/relationships.yaml")
    assert rendered == "data/relationships.yaml  error  some problem"
    assert "None" not in rendered  # guard against accidental f-string interpolation


def test_problem_render_keeps_line_zero():
    # Guards the `is not None` check: a falsy `if not self.line` would drop line 0.
    p = Problem(severity="warning", message="some problem", line=0)
    assert p.render("data/relationships.yaml").startswith(
        "data/relationships.yaml:0  warning  "
    )
