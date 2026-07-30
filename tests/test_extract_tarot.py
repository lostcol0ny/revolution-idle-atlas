from pathlib import Path

from atlas.extract.refs import RANKS, Vocabulary
from atlas.extract.tarot import _NAMED_RANKS, _NUMBER_TO_RANK, extract, parse
from atlas.models import EdgeConfidence

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"


def test_named_ranks_are_the_word_spelled_subset_of_the_shared_rank_list():
    """Pin the derivation, which today's page cannot exercise on its own.

    The Tarot page writes "Swords 1", never "Swords Ace", so `ace` reaches the
    parser only through _NUMBER_TO_RANK and dropping it from _NAMED_RANKS
    changes no output. It still has to stay: the word form is valid on the wiki
    and one edit away. `king` is likewise unmatched today.
    """
    assert _NAMED_RANKS == ("ace", "page", "knight", "queen", "king")
    # Every named rank must be a real rank, or the id built from it would name
    # a card the parser never mints and the edge would silently vanish.
    assert set(_NAMED_RANKS) <= set(RANKS)
    # The number-word ranks are reachable only as digits, never as words.
    assert set(_NAMED_RANKS) & set(_NUMBER_TO_RANK.values()) == {"ace"}

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
    # "The Devil" and will resolve against this id once relic effects are wired,
    # so the spelling is a cross-parser contract and not merely an internal detail.
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
    # which is how 158 reversed edges can ship under a passing test.
    assert not any(e.from_.startswith(("relic-", "refine-node-")) for e in edges)


def test_a_possessive_reference_without_an_ordinal_still_produces_an_edge():
    # Ten of Pentacles: "Makes Pentacles 8's effect +x stronger" — the only
    # card that boosts a non-adjacent sibling, and the only possessive on the
    # page. targets_effect is None because the wiki does not say which of the
    # two effects it means; 0 would fabricate precision the source lacks.
    result = extract(RAW_DIR)
    tuples = {(e.from_, e.to, e.targets_effect) for e in result.edges}
    assert ("tarot-ten-of-pentacles", "tarot-eight-of-pentacles", None) in tuples


def _card(name: str, effect: str) -> str:
    """One Arcana card template in the shape the Tarot page uses."""
    return (
        "{{Tarot Cards/Arcans\n"
        f"| icon = Tarot {name.lower().replace(' ', '-')}.png\n"
        f"| card_name = {name}\n"
        f"| effect = {effect}\n"
        "| duration = 0ms\n"
        "| cooldown = 1 hour\n"
        "}}\n"
    )


def test_the_chariot_resolves_to_the_sms_factor_stat():
    # The owner's worked example, and the shape of the whole feature: the wiki
    # writes "SMS factor" in lower case, the curated node is named "SMS Factor",
    # and full names match case-insensitively.
    raw = _card("The Chariot", "Decreases your SMS factor by # (''base 1,000'')")
    result = parse(raw, Vocabulary([("SMS Factor", "sms-factor"), ("SMS", "sms-factor")]))

    edge = next(e for e in result.edges if e.to == "sms-factor")
    assert edge.from_ == "tarot-the-chariot"
    assert edge.confidence is EdgeConfidence.UNCERTAIN
    # One edge, not two: "SMS Factor" claims the span before the "SMS" alias can.
    assert len([e for e in result.edges if e.to == "sms-factor"]) == 1


def test_a_major_arcana_name_resolves_even_though_it_is_not_curated():
    # refs.py's _TAROT_RE comment promises this: the 22 Major Arcana are bare
    # title-case noun phrases, so they are matched from the names parsed off this
    # very page rather than from a hardcoded list or the curated file.
    raw = _card("The Devil", "Boost") + _card(
        "The Fool", "Doubles The Devil's first effect"
    )
    result = parse(raw)

    edge = next(e for e in result.edges if e.from_ == "tarot-the-fool")
    assert edge.to == "tarot-the-devil"
    assert edge.targets_effect == 0
    assert edge.confidence is EdgeConfidence.UNCERTAIN


def test_a_card_named_later_on_the_page_still_resolves():
    # The pre-pass is what makes this work. Building the vocabulary inside the
    # main loop would only ever see cards already parsed, and the page does not
    # order cards by who references whom.
    raw = _card("The Fool", "Doubles The Devil's first effect") + _card("The Devil", "Boost")
    result = parse(raw)
    assert any(e.from_ == "tarot-the-fool" and e.to == "tarot-the-devil" for e in result.edges)


def test_a_card_does_not_resolve_to_itself():
    raw = _card("The Devil", "The Devil doubles its own output")
    result = parse(raw)
    assert all(e.to != "tarot-the-devil" for e in result.edges)
