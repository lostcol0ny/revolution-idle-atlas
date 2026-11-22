import shutil
from pathlib import Path

import pytest

from atlas.cli import main
from atlas.gamemap import (
    GAME_FILE_REL_PATH,
    grade_thresholds,
    map_catalog,
    map_particles,
    readable,
    to_yaml,
)
from atlas.loader import load_game
from atlas.models import Kind, Node

ROOT = Path(__file__).resolve().parents[1]


def _node(node_id: str, name: str, system: str, kind: Kind = Kind.UPGRADE) -> Node:
    return Node(id=node_id, name=name, system=system, kind=kind)


def _entry(index: int, name: str | None, desc: str | None = "d") -> dict:
    return {"index": index, "name": name, "desc": desc}


RELICS = [
    _node("relic-1", "Silver Coin", "relics", Kind.RELIC),
    _node("relic-2", "Magestic Halberd", "relics", Kind.RELIC),
    _node("relic-3", "Wolf Skull", "relics", Kind.RELIC),
]


def test_relics_map_by_index_and_verify_by_name():
    families = {
        "UNI_RELIC": [
            _entry(0, "Silver Coin", "A simple boost"),
            # A spelling fix still verifies, and is reported as a rename.
            _entry(1, "Majestic Halberd"),
            # An unrelated name at a known index means the numbering slipped.
            _entry(2, "Golden Tooth"),
            # A new relic with no wiki node yet is created.
            _entry(3, "Pocket Blackjack"),
            # ...unless its name is already some other relic's.
            _entry(4, "Wolf Skull"),
        ]
    }
    game, reports, skipped = map_catalog(families, RELICS, "123")

    assert game.buildid == "123"
    assert [(n.id, n.name, n.system, n.kind) for n in game.nodes] == [
        ("relic-1", "Silver Coin", None, None),
        ("relic-2", "Majestic Halberd", None, None),
        ("relic-4", "Pocket Blackjack", "relics", Kind.RELIC),
    ]
    assert game.nodes[0].description == "A simple boost"
    report = reports["UNI_RELIC"]
    assert (report.matched, report.added) == (2, 1)
    assert report.renamed == ["relic-2: 'Magestic Halberd' -> 'Majestic Halberd'"]
    assert report.unmatched == [
        "#2 'Golden Tooth': relic-3 is 'Wolf Skull'",
        "#4 'Wolf Skull': clashes with relic-3",
    ]
    assert skipped == []


def test_numbered_names_verify_by_number_and_compose_a_label():
    nodes = [
        _node("infinity-challenge-1", "Infinity Challenge 1", "infinity-challenges"),
        _node("infinity-challenge-2", "Infinity Challenge 2", "infinity-challenges"),
        _node("rp-upgrade-1", "RP Upgrade 1 (IP Gain)", "laboratory"),
    ]
    families = {
        "INF_CHL": [
            _entry(0, "<color=#D8BBF4>#1</color> Ionized Speed", "Promotions disabled"),
            _entry(1, "<color=#D8BBF4>#3</color> Out Of Order"),
        ],
        "ETR_RP_UPGRADE": [
            _entry(0, "#1 IP Gain ({0})", "Multiply IP gain by x{0} (total: x{1})")
        ],
    }
    game, reports, _ = map_catalog(families, nodes, None)

    assert [(n.id, n.name, n.description) for n in game.nodes] == [
        ("infinity-challenge-1", "Infinity Challenge 1 (Ionized Speed)", "Promotions disabled"),
        # Descriptions are reworded where game.yaml is written, not in the UI.
        ("rp-upgrade-1", "RP Upgrade 1 (IP Gain)", "Multiply IP gain by a multiplier"),
    ]
    assert reports["INF_CHL"].unmatched == ["#1 '#3 Out Of Order': does not read as #2"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Multiply IP gain by x{0} (total: x{1})", "Multiply IP gain by a multiplier"),
        (
            "Increase Common Exponent by +{0} (total: +{1})",
            "Increase Common Exponent by an amount",
        ),
        ("Raises Gold gain to ^{0}", "Raises Gold gain to an exponent"),
        ("Atoms Nerf at e10K: /{0}", "Atoms Nerf at e10K: a divisor"),
        ("Gain +{0}% more VP", "Gain a percentage more VP"),
        ("Gain {0:F2}% more VP", "Gain a percentage more VP"),
        ("Costs are reduced by -{1}", "Costs are reduced by an amount"),
        # Awkward before a noun, but only achievements use this shape and they
        # are not mapped.
        ("Reach {0} Score", "Reach a value Score"),
        # A parenthesis holding more than a number is prose and stays.
        ("Boost (per level: x{0}, capped)", "Boost (per level: a multiplier, capped)"),
    ],
)
def test_readable_words_runtime_placeholders(raw, expected):
    assert readable(raw) == expected


def test_readable_strips_rich_text_but_not_prose_brackets():
    raw = (
        "<color=#D8BBF4>Ritual</color>:<br><pos=5%>Rotate <s>twice</s> "
        "<sprite name=troll> <gradient=\"Fire\">x{0}</gradient> <== here"
    )
    assert readable(raw) == "Ritual: Rotate twice a multiplier <== here"


def test_readable_escapes_dollars_so_they_cannot_open_inline_math():
    assert readable("$ {0}") == "\\$ a value"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "Attack exponent multiplied ×(1 + 0.05 × rank).",
            r"Attack exponent multiplied $\times (1 + 0.05 \times \text{rank})$.",
        ),
        (
            "Golden Resource gain is multiplied by x{0} (10 x (Rank + 1) x (Tier + 1))",
            r"Golden Resource gain is multiplied by a multiplier "
            r"$(10 \times (\text{Rank} + 1) \times (\text{Tier} + 1))$",
        ),
        # The exponent's braces replace its parentheses.
        (
            "Tarot gold: (gain × 100)^(1 + 0.1 × pent) / 100.",
            r"Tarot gold: $(\text{gain} \times 100)^{1 + 0.1 \times \text{pent}} / 100$.",
        ),
        (
            "speed + 0.01 x Sqrt(rank). Softcap at 0.10",
            r"speed $+ 0.01 \times \sqrt{\text{rank}}$. Softcap at 0.10",
        ),
        # Two formulas, and a trailing parenthetical that is prose.
        (
            "base ×(β + 1)^0.2 (improved by refinement node 147). Luck ^(1 + tier / 100).",
            r"base $\times (β + 1)^{0.2}$ (improved by refinement node 147). "
            r"Luck $^{1 + \text{tier} / 100}$.",
        ),
        # Two operands with no operator between them are two runs, not one.
        (
            "Above tetr 10, this bonus uses 10 ×(tetr / 10)^0.32.",
            r"Above tetr 10, this bonus uses $10 \times (\text{tetr} / 10)^{0.32}$.",
        ),
        # A word other than a grade is an operand only inside parentheses, so
        # the noun before the exponent stays prose.
        (
            "Attack gold gain ^(1 + 0.01 × tetr).",
            r"Attack gold gain $^{1 + 0.01 \times \text{tetr}}$.",
        ),
    ],
)
def test_formulas_are_typeset(raw, expected):
    assert readable(raw, formulas=True) == expected


@pytest.mark.parametrize(
    "raw",
    [
        # Shorthand: a lone leading operator is not a formula.
        "Sacrifice dust gain increased by ^1.1.",
        "β generator base ×tier.",
        "Particle Rank boosts Luck by {0} (+0.01 per rank)",
        "The rank 8 bonus is 10 times stronger: +0.5 attack multiplier power per rank.",
        "Remove the atom gain penalty at 1.6e256 atoms.",
        # Unbalanced inside, so not read as arithmetic.
        "Boosts (1 + (rank by 2",
        # "x" is a letter unless it sits between two operands.
        "Gen x 3 bonus",
    ],
)
def test_formula_shorthand_stays_prose(raw):
    assert readable(raw, formulas=True) == readable(raw)


def test_formulas_escape_the_prose_around_them():
    assert readable("$5 for ×(1 + rank)", formulas=True) == (
        r"\$5 for $\times (1 + \text{rank})$"
    )


def test_named_families_match_by_normalised_name():
    nodes = [
        _node("plague-er-base-stealth", "Base Stealth", "plague"),
        _node("plague-er-twin-a", "Twin", "plague"),
        _node("plague-er-twin-b", "TWIN", "plague"),
        # Same name, other system or id family: never a candidate.
        _node("stealth", "Base Stealth", "plague", Kind.STAT),
        _node("special-minerals", "Paper", "minerals", Kind.CURRENCY),
    ]
    families = {
        "PLAGUE_ENDO_UPGRADE": [
            _entry(0, "base  stealth"),
            _entry(1, "Twin"),
            _entry(2, "Essence Density"),
            _entry(3, None, "orphan description"),
        ],
        "UNI_MIN_COMMON": [_entry(0, "Paper")],
        "ACH": [_entry(0, "A Million")],
    }
    game, reports, skipped = map_catalog(families, nodes, None)

    assert [(n.id, n.name, n.system) for n in game.nodes] == [
        ("plague-er-base-stealth", "base stealth", None),
        ("plague-er-essence-density", "Essence Density", "plague"),
    ]
    plague = reports["PLAGUE_ENDO_UPGRADE"]
    assert (plague.matched, plague.added) == (1, 1)
    assert plague.unmatched == [
        "#1 'Twin': names plague-er-twin-a, plague-er-twin-b",
        "#3: the game has no name for it",
    ]
    # Mineral tiers are matched only, never created.
    assert reports["UNI_MIN_COMMON"].unmatched == ["#0 'Paper': no node"]
    assert skipped == ["ACH"]


def test_game_file_round_trips_through_the_loader(tmp_path):
    families = {"UNI_RELIC": [_entry(0, "Silver Coin"), _entry(5, "New", None)]}
    game, _, _ = map_catalog(families, RELICS, "42")
    path = tmp_path / "game.yaml"
    path.write_text(to_yaml(game), encoding="utf-8")

    loaded = load_game(path)
    # `line` is excluded from the dump; the loader records it, the mapper cannot.
    assert loaded.model_dump() == game.model_dump()
    assert loaded.nodes[1].description is None


def test_build_overlays_the_game_file(tmp_path):
    (tmp_path / "data").mkdir()
    shutil.copy(
        ROOT / "tests" / "fixtures" / "minimal.yaml",
        tmp_path / "data" / "relationships.yaml",
    )
    (tmp_path / GAME_FILE_REL_PATH).write_text(
        "nodes:\n"
        "  - id: singularity\n"
        "    name: Game Singularity\n"
        "    description: From the game\n",
        encoding="utf-8",
    )
    assert main(["build", "--root", str(tmp_path)]) == 0

    graph = (tmp_path / "public" / "graph.json").read_text(encoding="utf-8")
    # The curated name wins; the description only the game supplies lands.
    assert '"description": "From the game"' in graph
    assert "Game Singularity" not in graph


def test_build_rejects_a_malformed_game_file(tmp_path, capsys):
    (tmp_path / "data").mkdir()
    shutil.copy(
        ROOT / "tests" / "fixtures" / "minimal.yaml",
        tmp_path / "data" / "relationships.yaml",
    )
    (tmp_path / GAME_FILE_REL_PATH).write_text(
        "nodes:\n  - id: singularity\n", encoding="utf-8"
    )
    assert main(["build", "--root", str(tmp_path)]) == 1
    assert "game.yaml" in capsys.readouterr().err
    assert not (tmp_path / "public").exists()


def test_game_needs_the_dataset_to_map_onto(tmp_path, monkeypatch):
    # Stands in for a real install: everything up to the mapping is covered by
    # test_game.py, and this run must fail before it writes data/game.yaml.
    monkeypatch.setattr(
        "atlas.cli.read_install",
        lambda _: {"buildid": None, "unity": "x", "strings": {}},
    )
    assert main(["game", "--root", str(tmp_path)]) == 1
    assert not (tmp_path / GAME_FILE_REL_PATH).exists()


GRADE_BONUSES_PAGE = """
=== Grade Bonuses ===
{| class="wikitable"
|+
! colspan="2" |Grade Bonuses
|-
!Threshold
!Bonus
|-
! colspan="2" |Rank Bonuses
|-
|0
|Alpha generator base
|-
|20
|
|-
! colspan="2" |Tetr Bonuses
|-
|1
|Unlock a free first Gamma generator level.
|}

=== Particle Prestige ===
|-
|5
|Not a grade bonus
"""


def test_grade_thresholds_read_each_grade_section():
    # An empty bonus cell still holds a threshold; text past the section does not.
    assert grade_thresholds(GRADE_BONUSES_PAGE) == {"rank": ["0", "20"], "tetr": ["1"]}


def test_particles_map_grade_bonuses_tree_effects_and_sparks():
    strings = {
        "PARTICLES_BONUS_RANK_0": "α generator base: +0.01 per rank.",
        "PARTICLES_BONUS_RANK_1": "Golden Resource gain is multiplied by x{0}",
        # The wiki lists one Tetr bonus and the game two: no pairing by position.
        "PARTICLES_BONUS_TETR_0": "Luck ^(1 + tetr / 10).",
        "PARTICLES_BONUS_TETR_1": "Attack gold gain ^(1 + 0.01 × tetr).",
        "PARTICLES_BONUSES_RANK": "Rank bonuses",
        # A14 on the game's Epsilon Tree screen: EPSILON_EFFECT_15 is A1.
        "EPSILON_EFFECT_28": "Spark Luck",
        # Below 15 is no outer node, so it is reported rather than placed.
        "EPSILON_EFFECT_3": "Inner",
        "EPSILON_BOOST": "Boosts {0} efficiency",
        "ENUM_SPARKTYPE_BLUE": "Blue",
        "ENUM_SPARKTYPE_EFFECT_BLUE": "Atoms Nerf at e10K: /{0}",
        "UNI_PARTICLES_SPARK_NAME": "{0} Spark",
    }
    nodes = [_node("particles-spark-blue", "Spark Blue", "particles")]
    thresholds = {"rank": ["0", "3"], "tetr": ["1"]}
    mapped, reports = map_particles(strings, nodes, thresholds)

    assert [(n.id, n.name, n.description, n.system, n.kind) for n in mapped] == [
        (
            "particles-rank-bonus-1",
            "Rank 0 Bonus",
            "α generator base: +0.01 per rank.",
            "particles-grades",
            Kind.UPGRADE,
        ),
        (
            "particles-rank-bonus-2",
            "Rank 3 Bonus",
            "Golden Resource gain is multiplied by a multiplier",
            "particles-grades",
            Kind.UPGRADE,
        ),
        (
            "particles-tetr-bonus-1",
            "Tetr Bonus #1",
            r"Luck $^{1 + \text{tetr} / 10}$.",
            "particles-grades",
            Kind.UPGRADE,
        ),
        (
            "particles-tetr-bonus-2",
            "Tetr Bonus #2",
            r"Attack gold gain $^{1 + 0.01 \times \text{tetr}}$.",
            "particles-grades",
            Kind.UPGRADE,
        ),
        (
            "epsilon-tree-a14",
            "Epsilon Tree A14 (Spark Luck)",
            "Spark Luck",
            "epsilon-tree",
            Kind.TREE_NODE,
        ),
        # The wiki's spark node exists, so it is overlaid rather than created.
        ("particles-spark-blue", "Blue Spark", "Atoms Nerf at e10K: a divisor", None, None),
    ]
    assert {prefix: (r.matched, r.added) for prefix, r in reports.items()} == {
        "PARTICLES_BONUS_RANK": (0, 2),
        "PARTICLES_BONUS_TETR": (0, 2),
        "EPSILON_EFFECT": (0, 1),
        "ENUM_SPARKTYPE": (1, 0),
    }
    assert reports["EPSILON_EFFECT"].unmatched == ["#3: not an outer node (A1 is #15)"]
