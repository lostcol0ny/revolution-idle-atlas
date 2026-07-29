from pathlib import Path

from atlas.extract.relics import extract, parse
from atlas.models import EdgeConfidence, Op

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
    assert all(len(n.effects) == 1 for n in result.nodes)
    # The whole point of the exercise: relics must actually point at things.
    assert len(result.edges) >= 20
