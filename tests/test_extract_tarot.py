from pathlib import Path

from atlas.extract.tarot import extract, parse

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"

PAGE = """
{{Tarot Cards
| icon = Tarot ace of swords.png
| card_name = Ace of Swords
| effect1 = Base Swords Generation /s
| effect2 = Attack Mult Gain from VP +^
}}
{{Tarot Cards
| icon = Tarot queen of swords.png
| card_name = Queen of Swords
| effect1 = Swords Knight first effect mult x
| effect2 = {{Keyword|ach|Ach 232|link=Achievements}} reward is multiplied by +x
}}
{{Tarot Cards/Arcans
| icon = Tarot the fool.png
| card_name = The Fool
| effect = Instantly spawns a black gem with Lv.# (''base lvl + 1'')
| duration = 0ms
| cooldown = 3 hours
}}
"""


def test_suit_cards_carry_two_effects():
    by_id = {n.id: n for n in parse(PAGE).nodes}
    card = by_id["tarot-ace-of-swords"]
    assert card.name == "Ace of Swords"
    assert card.system == "tarot"
    assert card.kind == "tarot-card"
    assert card.wiki == "Tarot"
    assert [e.text for e in card.effects] == [
        "Base Swords Generation /s",
        "Attack Mult Gain from VP +^",
    ]


def test_arcans_carry_one_effect():
    card = {n.id: n for n in parse(PAGE).nodes}["tarot-the-fool"]
    assert card.name == "The Fool"
    assert [e.text for e in card.effects] == [
        "Instantly spawns a black gem with Lv.# (base lvl + 1)"
    ]


def test_keyword_templates_inside_an_effect_survive_the_field_split():
    card = {n.id: n for n in parse(PAGE).nodes}["tarot-queen-of-swords"]
    assert card.effects[1].text == "Ach 232 reward is multiplied by +x"


def test_a_card_referencing_another_card_becomes_an_edge():
    edges = [(e.from_, e.to, e.targets_effect) for e in parse(PAGE).edges]
    assert edges == [("tarot-queen-of-swords", "tarot-knight-of-swords", 0)]


def test_the_real_page_yields_seventy_eight_cards():
    result = extract(RAW_DIR)
    assert len(result.nodes) == 78
    assert sum(1 for n in result.nodes if len(n.effects) == 2) == 56
    assert sum(1 for n in result.nodes if len(n.effects) == 1) == 22
    # Pins one Major Arcana id from the real page. relic-55's effect text names
    # "The Devil" and will resolve against this id at Task 9, so the spelling is
    # a cross-task contract and not merely an internal detail.
    assert "tarot-the-devil" in {n.id for n in result.nodes}


def test_numeric_suit_ref_produces_an_edge():
    # "Two of Swords" effect1 = "Swords 1 first effect mult x"
    # Numeric reference: "1" -> "ace". Covers the number-to-rank mapping path.
    result = extract(RAW_DIR)
    edge_tuples = {(e.from_, e.to, e.targets_effect) for e in result.edges}
    assert ("tarot-two-of-swords", "tarot-ace-of-swords", 0) in edge_tuples


def test_cross_system_edges_point_outward_from_the_card():
    edges = extract(RAW_DIR).edges
    tuples = {(e.from_, e.to, e.targets_effect) for e in edges}
    assert ("tarot-four-of-swords", "relic-3", None) in tuples
    assert ("tarot-the-high-priestess", "refine-node-1", None) in tuples
    assert ("tarot-six-of-wands", "fire-node-3", None) in tuples
    assert ("tarot-seven-of-wands", "water-node-1", None) in tuples
    # The direction guard. Written as a check on the `from_` *side* rather than
    # as `not any(e.to == ...)`: a single-field negative goes silently
    # unfalsifiable the moment the value starts surfacing on the other endpoint,
    # which is how Task 6 shipped 158 reversed edges under a passing test.
    assert not any(e.from_.startswith(("relic-", "refine-node-")) for e in edges)


def test_a_possessive_reference_without_an_ordinal_still_produces_an_edge():
    # Ten of Pentacles: "Makes Pentacles 8's effect +x stronger" — the only
    # card that boosts a non-adjacent sibling, and the only possessive on the
    # page. targets_effect is None because the wiki does not say which of the
    # two effects it means; 0 would fabricate precision the source lacks.
    result = extract(RAW_DIR)
    tuples = {(e.from_, e.to, e.targets_effect) for e in result.edges}
    assert ("tarot-ten-of-pentacles", "tarot-eight-of-pentacles", None) in tuples
