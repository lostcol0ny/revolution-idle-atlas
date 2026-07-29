from pathlib import Path

from atlas.extract.elements import extract, parse

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"

PAGE = """
=== Element Factors ===
{| class="wikitable"
! colspan=2|
! Description
! Unlock Condition
|-
! rowspan="3" style="background-color:rgba(111, 54, 26, 0.5)"| Fire
! Factor 1
| Score
| None
|-
! Factor 2
| Score Exponent
| King of Wands card
|-
! Factor 3
| Asc. Power
| Fire Node 11
|-
|}

=== Element Upgrades ===

==== Fire ====
{| class="wikitable"
|+
!Node
!Price
!effect
|-
|4
|10
|Fire boosts Relic 26 effect ''(improves Quality donut)''
|-
|6
|1e25
|Fire adds base to {{Keyword|node|Refine Tree Node 60}}
|-
|11
|1e1300
|Unlocks third factor for fire
|}
"""


def test_factor_nodes_are_named_and_described():
    by_id = {n.id: n for n in parse(PAGE).nodes}
    factor = by_id["fire-factor-2"]
    assert factor.name == "Fire Factor 2"
    assert factor.system == "elements"
    assert factor.kind == "stat"
    assert factor.wiki == "Elements"
    assert factor.effects[0].text == "Score Exponent"


def test_upgrade_nodes_carry_their_effect_text():
    node = {n.id: n for n in parse(PAGE).nodes}["fire-node-6"]
    assert node.name == "Fire Node 6"
    assert node.kind == "upgrade"
    assert node.effects[0].text == "Fire adds base to Refine Tree Node 60"


def test_unlock_conditions_become_edges_into_the_factor():
    unlocks = {(e.from_, e.to) for e in parse(PAGE).edges if e.rel == "unlocks"}
    assert unlocks == {
        ("tarot-king-of-wands", "fire-factor-2"),
        ("fire-node-11", "fire-factor-3"),
    }


def test_the_none_unlock_condition_produces_no_edge():
    assert not any(e.to == "fire-factor-1" for e in parse(PAGE).edges)


def test_upgrade_effects_become_boosts_edges():
    boosts = {(e.from_, e.to) for e in parse(PAGE).edges if e.rel == "boosts"}
    assert boosts == {
        ("fire-node-4", "relic-26"),
        ("fire-node-6", "refine-node-60"),
    }


def test_the_real_page_yields_twelve_factors_and_every_upgrade_node():
    result = extract(RAW_DIR)
    factors = [n for n in result.nodes if n.kind == "stat"]
    upgrades = [n for n in result.nodes if n.kind == "upgrade"]
    assert len(factors) == 12
    assert {n.id for n in factors} >= {"fire-factor-1", "water-factor-3"}
    assert len(upgrades) >= 40
    assert "fire-node-11" in {n.id for n in upgrades}


# --- Additional tests required by task hygiene ---


def test_unlock_edge_direction_is_unlocking_node_to_factor():
    # The acting thing (unlocking node) is `from_`; the thing being unlocked
    # (factor) is `to`. Pins both endpoints of the tuple so a reversal cannot
    # pass this test.
    unlocks = {(e.from_, e.to) for e in parse(PAGE).edges if e.rel == "unlocks"}
    assert ("tarot-king-of-wands", "fire-factor-2") in unlocks
    # Direction guard: the factor must never appear on the `from_` side of an
    # unlock edge. A single-field negative is not enough (it goes silent when
    # the value migrates to the other field), so we check the pair.
    assert ("fire-factor-2", "tarot-king-of-wands") not in unlocks
    assert ("fire-factor-3", "fire-node-11") not in unlocks


def test_none_unlock_produces_no_edge_either_direction():
    # Checks both sides so the assertion is not silently satisfied if the factor
    # appears as `from_` instead.
    edges = [(e.from_, e.to) for e in parse(PAGE).edges]
    assert not any(
        "fire-factor-1" in pair for pair in edges
    )


def test_real_page_all_four_king_unlock_edges_present():
    # The four tarot→factor unlock edges are the cross-system claims this parser
    # uniquely produces. They cannot be reached via the PAGE fixture (which only
    # has Fire), so the real-page test pins identity for all four.
    result = extract(RAW_DIR)
    unlocks = {(e.from_, e.to) for e in result.edges if e.rel == "unlocks"}
    assert ("tarot-king-of-wands", "fire-factor-2") in unlocks
    assert ("tarot-king-of-pentacles", "earth-factor-2") in unlocks
    assert ("tarot-king-of-swords", "wind-factor-2") in unlocks
    assert ("tarot-king-of-cups", "water-factor-2") in unlocks


def test_real_page_all_four_node_unlock_edges_present():
    # High-numbered upgrade nodes unlocking factor-3 for each element. This path
    # through _parse_factors is distinct from the tarot path: a wrong element id
    # or off-by-one in the factor number would break these while leaving the
    # king-of-X assertions above green.
    result = extract(RAW_DIR)
    unlocks = {(e.from_, e.to) for e in result.edges if e.rel == "unlocks"}
    assert ("fire-node-11", "fire-factor-3") in unlocks
    assert ("earth-node-10", "earth-factor-3") in unlocks
    assert ("wind-node-12", "wind-factor-3") in unlocks
    assert ("water-node-11", "water-factor-3") in unlocks


def test_real_page_exact_node_count_with_identity():
    # Count alone cannot distinguish correct output from wrong output of the
    # same size, so we pin the totals alongside specific identity checks.
    result = extract(RAW_DIR)
    factors = [n for n in result.nodes if n.kind == "stat"]
    upgrades = [n for n in result.nodes if n.kind == "upgrade"]
    assert len(factors) == 12
    assert len(upgrades) == 44
    # Fire has 11, Earth 10, Wind 12, Water 11 upgrade nodes.
    upgrade_ids = {n.id for n in upgrades}
    assert "wind-node-12" in upgrade_ids   # last wind node (Wind has the most)
    assert "earth-node-10" in upgrade_ids  # last earth node (Earth has fewest)
    assert "water-node-1" in upgrade_ids   # first water node (named by tarot.py)


def test_real_page_boosts_edges_point_outward_from_element_nodes():
    # Pins identity and checks direction: element nodes are always `from_`, never
    # `to`. A reversal would flip every one of the 17 boosts edges and all 17
    # would still show up on one side of an endpoint check.
    result = extract(RAW_DIR)
    boosts = {(e.from_, e.to) for e in result.edges if e.rel == "boosts"}
    # Two representative cross-system boosts edges.
    assert ("fire-node-4", "relic-26") in boosts
    assert ("earth-node-2", "refine-node-1") in boosts
    assert ("wind-node-11", "refine-node-69") in boosts
    assert ("water-node-6", "refine-node-60") in boosts
    # Direction guard: element nodes must never appear as `to` in boosts edges.
    assert not any(
        e.to.endswith(("-node-1", "-node-2", "-node-3", "-node-4",
                       "-node-5", "-node-6", "-node-7", "-node-8",
                       "-node-9", "-node-10", "-node-11", "-node-12"))
        and e.to.startswith(("fire-", "earth-", "wind-", "water-"))
        for e in result.edges
        if e.rel == "boosts"
    )


def test_real_page_edge_counts_with_identity():
    # 17 boosts + 8 unlocks = 25 total. Alongside the identity tests above this
    # confirms there are no phantom duplicates or dropped edges.
    result = extract(RAW_DIR)
    boosts = [e for e in result.edges if e.rel == "boosts"]
    unlocks = [e for e in result.edges if e.rel == "unlocks"]
    assert len(boosts) == 17
    assert len(unlocks) == 8
    assert len(result.edges) == 25


def test_unlock_edges_are_documented_confidence():
    # The unlock column is a direct statement, not an inference, so confidence
    # must be DOCUMENTED. Boosts edges are PROVISIONAL (inferred from prose).
    from atlas.models import EdgeConfidence

    result = extract(RAW_DIR)
    assert all(
        e.confidence is EdgeConfidence.DOCUMENTED
        for e in result.edges
        if e.rel == "unlocks"
    )
    assert all(
        e.confidence is EdgeConfidence.PROVISIONAL
        for e in result.edges
        if e.rel == "boosts"
    )


def test_factor_nodes_all_live_in_elements_system():
    result = extract(RAW_DIR)
    for node in result.nodes:
        assert node.system == "elements"
        assert node.wiki == "Elements"
