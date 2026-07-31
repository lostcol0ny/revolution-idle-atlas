from atlas.models import Dataset, Edge, Node, SystemDef
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


def test_problem_render_prefers_its_own_path_over_the_callers():
    # A problem built during the merge knows which of the two input files it
    # read. The caller printing it holds one path and cannot recover that, so
    # the problem's own path has to win.
    p = Problem(
        severity="error",
        message="duplicate node id 'b'",
        line=6,
        path="data/derived.yaml",
    )
    assert p.render("data/relationships.yaml") == (
        "data/derived.yaml:6  error  duplicate node id 'b'"
    )


def test_problem_render_falls_back_to_the_callers_path_when_it_has_none():
    # The common case: validation problems see the merged dataset and have no
    # provenance to carry, so they must still render under the caller's path.
    p = Problem(severity="error", message="some problem", line=6)
    assert p.render("data/relationships.yaml").startswith("data/relationships.yaml:6")


def test_node_system_must_be_declared_when_systems_are_present(node):
    ds = Dataset(
        systems=[SystemDef(id="unity", name="Unity")],
        nodes=[node("a", system="not-declared")],
    )
    problems = validate_dataset(ds)
    assert any("not-declared" in p.message for p in problems)
    assert all(p.severity == "error" for p in problems)


def test_node_system_is_unchecked_when_no_systems_are_declared(node):
    ds = Dataset(nodes=[node("a", system="anything-at-all")])
    assert validate_dataset(ds) == []


def test_unknown_system_gets_a_did_you_mean_hint(node):
    ds = Dataset(
        systems=[SystemDef(id="relics", name="Relics")],
        nodes=[node("a", system="relic")],
    )
    problems = validate_dataset(ds)
    assert "did you mean 'relics'?" in problems[0].message


def test_system_parent_must_be_declared():
    ds = Dataset(systems=[SystemDef(id="relics", name="Relics", parent="untiy")])
    problems = validate_dataset(ds)
    assert any("parent" in p.message and "untiy" in p.message for p in problems)


def test_duplicate_system_ids_are_an_error():
    ds = Dataset(
        systems=[SystemDef(id="unity", name="Unity"), SystemDef(id="unity", name="Unity Again")]
    )
    problems = validate_dataset(ds)
    assert any("duplicate system id 'unity'" in p.message for p in problems)


def test_two_systems_may_share_a_display_name_under_distinct_ids():
    # Infinity, Eternity and Unity each have a subsection called "Challenges".
    # Uniqueness is a property of `id`, never of `name` — a check on `name`
    # would make the real taxonomy unrepresentable.
    ds = Dataset(
        systems=[
            SystemDef(id="infinity-challenges", name="Challenges", parent="infinity"),
            SystemDef(id="eternity-challenges", name="Challenges", parent="eternity"),
            SystemDef(id="infinity", name="Infinity"),
            SystemDef(id="eternity", name="Eternity"),
        ]
    )
    assert validate_dataset(ds) == []


def test_a_system_cycle_is_an_error():
    ds = Dataset(
        systems=[
            SystemDef(id="a", name="A", parent="b"),
            SystemDef(id="b", name="B", parent="a"),
        ]
    )
    problems = validate_dataset(ds)
    assert any("cycle" in p.message for p in problems)


def test_a_system_that_is_its_own_parent_is_an_error():
    ds = Dataset(systems=[SystemDef(id="a", name="A", parent="a")])
    problems = validate_dataset(ds)
    assert any("cycle" in p.message for p in problems)


def test_targets_effect_must_index_an_existing_effect_on_the_target(node):
    target = node("b")
    target.effects = [{"text": "one effect"}]
    ds = Dataset(
        nodes=[node("a"), target],
        edges=[
            Edge(
                **{
                    "from": "a",
                    "to": "b",
                    "rel": "boosts",
                    "source": "wiki:Relics",
                    "targets_effect": 3,
                }
            )
        ],
    )
    problems = validate_dataset(ds)
    assert any("targets_effect 3" in p.message for p in problems)


def test_targets_effect_within_range_is_accepted(node):
    target = node("b")
    target.effects = [{"text": "one effect"}, {"text": "another"}]
    ds = Dataset(
        nodes=[node("a"), target],
        edges=[
            Edge(
                **{
                    "from": "a",
                    "to": "b",
                    "rel": "boosts",
                    "source": "wiki:Relics",
                    "targets_effect": 1,
                }
            )
        ],
    )
    assert validate_dataset(ds) == []


def test_targets_effect_equal_to_effect_count_is_rejected(node):
    # `targets_effect` is a 0-based index, so the valid range is [0, len-1].
    # An index equal to len is one past the end and must be rejected.
    target = node("b")
    target.effects = [{"text": "effect 0"}, {"text": "effect 1"}]
    ds = Dataset(
        nodes=[node("a"), target],
        edges=[
            Edge(
                **{
                    "from": "a",
                    "to": "b",
                    "rel": "boosts",
                    "source": "wiki:Relics",
                    "targets_effect": 2,
                }
            )
        ],
    )
    problems = validate_dataset(ds)
    assert any("targets_effect 2" in p.message for p in problems)
    assert all(p.severity == "error" for p in problems)
