from pathlib import Path

from atlas.extract.refine_tree import extract, parse
from atlas.models import Op

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"

PAGE = """
{{RN|1| max = 997 | rfp = 1
| rfp increase = 10x
| effect = Increases mineral base by 1 (starts at 3)
| req = 0 }}
{{RN|4| max = 10 | rfp = 2
| rfp increase = 2x
| effect = Polish sword eff. x1.1 (maxes at x2)
| req = 2,3 }}
{{RN|8| max = 1 | rfp = 20
| rfp increase =
| effect = Relic 12 effect powered to ^128
| req = 4 }}
"""


def test_nodes_carry_the_effect_text_and_no_coefficient():
    by_id = {n.id: n for n in parse(PAGE).nodes}
    assert set(by_id) == {"refine-node-1", "refine-node-4", "refine-node-8"}

    node = by_id["refine-node-1"]
    assert node.name == "Refine Node 1"
    assert node.system == "refine-tree"
    assert node.kind == "tree-node"
    assert node.wiki == "Minerals/Refine_Tree"
    assert node.effects[0].text == "Increases mineral base by 1 (starts at 3)"
    # The refine tree states no per-level coefficient anywhere on the page.
    assert node.effects[0].per_level is None
    assert node.effects[0].op is None


def test_requires_edges_point_from_the_child_to_each_parent():
    edges = [e for e in parse(PAGE).edges if e.rel == "requires"]
    assert {(e.from_, e.to) for e in edges} == {
        ("refine-node-4", "refine-node-2"),
        ("refine-node-4", "refine-node-3"),
        ("refine-node-8", "refine-node-4"),
    }
    assert all(e.source == "wiki:Minerals/Refine_Tree" for e in edges)


def test_the_zero_sentinel_produces_no_requirement_edge():
    edges = parse(PAGE).edges
    assert not any(e.to == "refine-node-0" for e in edges)


def test_effect_references_become_boosts_edges():
    edges = [e for e in parse(PAGE).edges if e.rel == "boosts"]
    assert [(e.from_, e.to) for e in edges] == [("refine-node-8", "relic-12")]
    assert edges[0].note == "Relic 12 effect powered to ^128"


def test_the_real_page_yields_one_hundred_and_thirty_six_nodes():
    result = extract(RAW_DIR)
    assert len(result.nodes) == 136
    requires = [e for e in result.edges if e.rel == "requires"]
    assert len(requires) == 158
    assert any(e.rel == "boosts" for e in result.edges)
