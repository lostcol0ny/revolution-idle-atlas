from pathlib import Path

from atlas.extract.refs import Vocabulary
from atlas.extract.relics import extract, parse
from atlas.models import EdgeConfidence, Op, Rel

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"

TABLE = """
{| class="wikitable sortable"
! colspan="6" |Relics
|-
!Number
!Name
!Icon
!Effect
!Effect per level
!Unlock requirements
|-
|3
|Copper Bunny \nStatuette
|[[File:Relic 003.png|128px|link=]]
|[[Zodiacs]] Level Sum (ZLM) Boost [[Attacks|(''Attacks'') Damage Mult]]
| +0.0002
|Attack level 20
|-
|38
|Smart Man
|[[File:Relic 038.png|128px|link=]]
|Adds base to [[Minerals#Refinement|Refine]] Node 2
''(Attacks bulk leveling)''
| +1.00
|Attack level 1,000
|-
|66
|Spring Crocodile
|[[File:Relic 066.png|128px|link=]]
|Multiplies Relic 62 effect
| +(?)
| Attack level 39,000
|}
"""


def test_node_shape():
    result = parse(TABLE)
    by_id = {n.id: n for n in result.nodes}
    assert set(by_id) == {"relic-3", "relic-38", "relic-66"}

    relic = by_id["relic-3"]
    assert relic.name == "Copper Bunny Statuette"
    assert relic.system == "relics"
    assert relic.kind == "relic"
    assert relic.wiki == "Relics"
    assert relic.effects[0].text == (
        "Zodiacs Level Sum (ZLM) Boost (Attacks) Damage Mult"
    )
    assert relic.effects[0].per_level == "+0.0002"
    assert relic.effects[0].op is Op.ADD


def test_multi_line_effect_text_is_kept_in_one_cell():
    relic = {n.id: n for n in parse(TABLE).nodes}["relic-38"]
    assert relic.effects[0].text == (
        "Adds base to Refine Node 2 (Attacks bulk leveling)"
    )


def test_edges_are_emitted_for_resolved_references():
    edges = {(e.from_, e.to): e for e in parse(TABLE).edges}
    assert set(edges) == {
        ("relic-38", "refine-node-2"),
        ("relic-66", "relic-62"),
    }
    edge = edges[("relic-38", "refine-node-2")]
    assert edge.rel == "boosts"
    assert edge.op is Op.ADD
    assert edge.source == "wiki:Relics"
    assert edge.confidence is EdgeConfidence.PROVISIONAL
    assert edge.note == "Adds base to Refine Node 2 (Attacks bulk leveling)"


def test_a_question_mark_in_the_coefficient_downgrades_confidence():
    edges = {(e.from_, e.to): e for e in parse(TABLE).edges}
    assert edges[("relic-66", "relic-62")].confidence is EdgeConfidence.UNCERTAIN


def test_the_real_page_yields_seventy_relics():
    result = extract(RAW_DIR)
    assert len(result.nodes) == 70
    assert [n.id for n in result.nodes][:3] == ["relic-1", "relic-2", "relic-3"]
    # Documents the wiki's current shape — one Effect column per relic row —
    # not the parser's handling of multi-effect relics. If the page grew a
    # second effect column the parser would silently ignore it and this would
    # stay green; Node.effects is a list precisely so that can be fixed then.
    assert all(len(n.effects) == 1 for n in result.nodes)
    # The whole point of the exercise: relics must actually point at things.
    assert len(result.edges) >= 20
    # The count alone cannot tell 20 correct edges from 20 wrong ones, and a
    # fabricated edge is worse than a missing one — the UI renders it as an
    # authoritative claim about game mechanics. These name the endpoints.
    edge_set = {(e.from_, e.to) for e in result.edges}
    # Both targets come out of one sentence ("relics 2 and 4"), pinning the
    # multi-reference path through the resolver.
    assert ("relic-15", "relic-2") in edge_set  # Comfortable Telescope -> Pinewood Bracelet
    assert ("relic-15", "relic-4") in edge_set  # Comfortable Telescope -> Four Leaf Clover
    assert ("relic-50", "relic-38") in edge_set  # Troll Face -> Smart Man
    # Crosses from a relic to a refine-tree node, pinning the id vocabulary
    # across two sources — the seam Tasks 6-8 lean on.
    assert ("relic-38", "refine-node-2") in edge_set


def _table_with_row(number: str, name: str, effect: str, per_level: str) -> str:
    """One relic row wrapped in the six-column table structure parse() expects."""
    return (
        '{| class="wikitable sortable"\n'
        "! colspan=\"6\" |Relics\n"
        "|-\n"
        "!Number\n!Name\n!Icon\n!Effect\n!Effect per level\n!Unlock requirements\n"
        "|-\n"
        f"|{number}\n"
        f"|{name}\n"
        f"|[[File:Relic 00{number}.png|128px|link=]]\n"
        f"|{effect}\n"
        f"| {per_level}\n"
        f"|Attack level 1\n"
        "|}"
    )


def test_a_vocabulary_hit_in_a_relic_effect_becomes_an_uncertain_edge():
    raw = _table_with_row("38", "Smart Man", "Multiplies your Luck", "+1.00")
    vocab = Vocabulary([("Luck", "luck")])
    result = parse(raw, vocab)

    edge = next(e for e in result.edges if e.to == "luck")
    # Uncertain even though the per_level "+1.00" carries no "?" — so the base
    # confidence at this call site would have been provisional. Only the
    # from_vocabulary flag can produce uncertain here.
    assert edge.confidence is EdgeConfidence.UNCERTAIN
    assert edge.rel is Rel.BOOSTS
    assert edge.from_ == "relic-38"


def test_a_structural_hit_keeps_its_own_confidence_when_a_vocabulary_is_supplied():
    # The other half of the pair. Passing a vocabulary must not weaken the edges
    # the entity regexes produce, or every relic edge in derived.yaml would
    # silently downgrade to uncertain.
    raw = _table_with_row("38", "Smart Man", "Adds base to Refine Node 2", "+1.00")
    result = parse(raw, Vocabulary([("Luck", "luck")]))

    edge = next(e for e in result.edges if e.to == "refine-node-2")
    assert edge.confidence is EdgeConfidence.PROVISIONAL


def test_parse_without_a_vocabulary_is_unchanged():
    raw = _table_with_row("38", "Smart Man", "Multiplies your Luck", "+1.00")
    assert parse(raw).edges == []
