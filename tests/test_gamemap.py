import shutil
from pathlib import Path

from atlas.cli import main
from atlas.gamemap import GAME_FILE_REL_PATH, map_catalog, to_yaml
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
        "ETR_RP_UPGRADE": [_entry(0, "#1 IP Gain ({0})", "Multiply IP gain by x{0}")],
    }
    game, reports, _ = map_catalog(families, nodes, None)

    assert [(n.id, n.name, n.description) for n in game.nodes] == [
        ("infinity-challenge-1", "Infinity Challenge 1 (Ionized Speed)", "Promotions disabled"),
        # Placeholders are the game's runtime values and are kept verbatim.
        ("rp-upgrade-1", "RP Upgrade 1 (IP Gain)", "Multiply IP gain by x{0}"),
    ]
    assert reports["INF_CHL"].unmatched == ["#1 '#3 Out Of Order': does not read as #2"]


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
