from pathlib import Path

from atlas.extract.refs import Vocabulary
from atlas.extract.refine_tree import extract, parse
from atlas.models import EdgeConfidence

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


def test_requires_edges_point_from_each_parent_to_the_child():
    # Parent -> child: the arrow is flow, not grammar. See the comment in
    # refine_tree.py — the frontend renders `from -> to` as "This feeds".
    edges = [e for e in parse(PAGE).edges if e.rel == "requires"]
    assert {(e.from_, e.to) for e in edges} == {
        ("refine-node-2", "refine-node-4"),
        ("refine-node-3", "refine-node-4"),
        ("refine-node-4", "refine-node-8"),
    }
    assert all(e.source == "wiki:Minerals/Refine_Tree" for e in edges)
    assert all(e.confidence == "documented" for e in edges)


def test_the_zero_sentinel_produces_no_requirement_edge():
    # Checked on both endpoints deliberately. Under parent -> child the
    # sentinel would surface as `from`, so asserting only on `to` (as it read
    # while edges pointed child -> parent) passes even with the guard removed.
    edges = parse(PAGE).edges
    assert not any("refine-node-0" in (e.from_, e.to) for e in edges)


def test_effect_references_become_boosts_edges():
    edges = [e for e in parse(PAGE).edges if e.rel == "boosts"]
    assert [(e.from_, e.to) for e in edges] == [("refine-node-8", "relic-12")]
    assert edges[0].note == "Relic 12 effect powered to ^128"
    assert edges[0].confidence == "provisional"


def test_a_node_naming_itself_produces_no_self_loop():
    # Real case: refine-node-125 reads "Adds Refine Node 125 as a Singularity
    # Mult Factor". The resolver matches it, and only the self-reference guard
    # stops the node from boosting itself.
    page = """
{{RN|125| max = 1 | rfp = 5
| rfp increase =
| effect = Adds Refine Node 125 as a Singularity Mult Factor
| req = 4 }}
"""
    edges = [e for e in parse(page).edges if e.rel == "boosts"]
    assert edges == []


def test_the_real_page_yields_one_hundred_and_thirty_six_nodes():
    result = extract(RAW_DIR)
    assert len(result.nodes) == 136
    requires = [e for e in result.edges if e.rel == "requires"]
    assert len(requires) == 158
    assert any(e.rel == "boosts" for e in result.edges)


def test_the_real_page_orients_requires_from_parent_to_child():
    # A count alone cannot catch a wholesale direction flip: reversing every
    # edge preserves it exactly. Pin a known parent/child pair both ways.
    # RN2 declares "req = 1", so node 1 is the prerequisite and feeds node 2.
    edges = {(e.from_, e.to) for e in extract(RAW_DIR).edges if e.rel == "requires"}
    assert ("refine-node-1", "refine-node-2") in edges
    assert ("refine-node-2", "refine-node-1") not in edges


def test_the_real_page_yields_eighteen_boosts_edges():
    boosts = [e for e in extract(RAW_DIR).edges if e.rel == "boosts"]
    assert len(boosts) == 18
    assert not any(e.from_ == e.to for e in boosts)


def test_a_vocabulary_hit_in_a_refine_node_effect_becomes_an_uncertain_edge():
    raw = "{{RN|2| max = 10 | rfp = 2\n| effect = Boosts Special Minerals Merge Factor\n| req = 1 }}"
    result = parse(raw, Vocabulary([("Special Minerals Merge Factor", "smmf")]))
    edge = next(e for e in result.edges if e.to == "smmf")
    assert edge.confidence is EdgeConfidence.UNCERTAIN
