import json
import re
from pathlib import Path

import pytest

GRAPH_PATH = Path(__file__).resolve().parents[1] / "public" / "graph.json"


@pytest.fixture(scope="module")
def graph() -> dict:
    return json.loads(GRAPH_PATH.read_text(encoding="utf-8"))


def test_no_relic_name_is_doubled(graph: dict):
    # The guard in render._relic_label is the only thing standing between a
    # stale curated placeholder and a "Relic 3 (Relic 3)" label reaching the
    # UI. Assert it on the real artifact, not just on a fixture.
    doubled = re.compile(r"^Relic \d+ \(Relic \d+\)$")
    offenders = [n["id"] for n in graph["nodes"] if doubled.match(n["name"])]
    assert offenders == []


def test_every_relic_node_is_labelled_with_its_number(graph: dict):
    numbered = re.compile(r"^Relic (\d+)(?: \(.+\))?$")
    for node in graph["nodes"]:
        if node["kind"] != "relic" or not re.match(r"^relic-\d+$", node["id"]):
            continue
        match = numbered.match(node["name"])
        assert match is not None, f"{node['id']} has uncomposed name {node['name']!r}"
        assert match.group(1) == node["id"].removeprefix("relic-")


def test_relic_18_carries_its_real_name(graph: dict):
    # relic-18 never had a curated override, so it pins the composition for the
    # ordinary case: derived supplies the name and render composes it.
    names = {n["id"]: n["name"] for n in graph["nodes"]}
    assert names["relic-18"] == "Relic 18 (Mythical Rune)"


def test_the_two_previously_stale_relics_carry_their_real_names(graph: dict):
    # These two nodes had curated placeholder names that masked
    # correctly-extracted wiki names. Naming them explicitly means a regression
    # that re-masks them fails here rather than looking plausible.
    names = {n["id"]: n["name"] for n in graph["nodes"]}
    assert names["relic-3"] == "Relic 3 (Copper Bunny Statuette)"
    assert names["relic-69"] == 'Relic 69 (Outdated "Nice" Gadget)'


def test_no_relic_is_left_with_a_bare_number_label(graph: dict):
    # Nothing in the curated file should override any of the 70 relics, so every
    # one of them must carry a real wiki name in parentheses. A bare "Relic N"
    # means a placeholder name has crept back into relationships.yaml and is
    # masking the derived name again — the exact fault the `relationships.yaml`
    # cleanup removed.
    bare = re.compile(r"^Relic \d+$")
    offenders = [n["id"] for n in graph["nodes"] if bare.match(n["name"])]
    assert offenders == []


def test_all_seventy_relics_are_present_and_composed(graph: dict):
    composed = re.compile(r"^Relic \d+ \(.+\)$")
    relics = [
        n
        for n in graph["nodes"]
        if n["kind"] == "relic" and re.match(r"^relic-\d+$", n["id"])
    ]
    assert len(relics) == 70
    uncomposed = [n["id"] for n in relics if not composed.match(n["name"])]
    assert uncomposed == []


def test_the_seeded_stats_are_all_present(graph: dict):
    ids = {n["id"] for n in graph["nodes"]}
    expected = {
        "special-minerals-merge-factor",
        "sms-factor",
        "mineral-cost-exp",
        "polish-knuckles",
        "attack-exponent",
        "damage-mult",
        "zodiac-sell-cost",
        "zodiac-exp-factor",
        "quality",
        "luck",
        "game-speed",
    }
    assert expected <= ids


def test_the_seeded_currencies_are_all_present_and_are_currencies(graph: dict):
    by_id = {n["id"]: n for n in graph["nodes"]}
    expected = {
        "eternity-points",
        "infinity-points",
        "animal-points",
        "dilation-points",
        "dilation-tree-points",
        "research-points",
        "souls",
        "time-flux",
        "runes",
        "tarot-draws",
    }
    assert expected <= set(by_id)
    assert {by_id[i]["kind"] for i in expected} == {"currency"}


def test_the_abbreviations_the_wiki_uses_are_declared_as_aliases(graph: dict):
    # These are the surface forms the vocabulary matcher actually fires on. A missing
    # alias is a silently missing edge, which is exactly the failure the
    # coverage report cannot distinguish from "the wiki never said it".
    aliases = {n["id"]: set(n.get("aliases", [])) for n in graph["nodes"]}
    assert aliases["special-minerals-merge-factor"] == {"SMMF"}
    assert aliases["sms-factor"] == {"SMS"}
    assert aliases["eternity-points"] == {"EP"}
    assert aliases["animal-points"] == {"AP"}
    assert aliases["dilation-tree-points"] == {"DTP"}
    assert aliases["time-flux"] == {"TF"}


def test_every_seeded_node_declares_a_system_that_exists(graph: dict):
    # An undeclared system is a build error, so `atlas build` already enforces
    # this. Asserting it here names the failure: it says "a seeded system id is
    # wrong" instead of "the build exited 1".
    declared = {s["id"] for s in graph.get("systems", [])}
    assert declared
    for node in graph["nodes"]:
        assert node["system"] in declared, node["id"]
