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


def test_the_owners_worked_example_resolves(graph: dict):
    # The one node the owner named by hand: "picking a stat (like Special
    # Minerals Merge Factor) and then looking to see all of the nodes that lead
    # up to it". If nothing points at it, the primary use case has no data.
    upstream = [e["from"] for e in graph["edges"] if e["to"] == "sms-factor"]
    assert upstream, "no edge reaches sms-factor"


def test_the_major_arcana_are_no_longer_islands(graph: dict):
    # 20 of the 22 Major Arcana were unconnected islands before the vocabulary
    # landed. This is the coverage number that says the feature works on real
    # data rather than on a fixture.
    touched = {e["from"] for e in graph["edges"]} | {e["to"] for e in graph["edges"]}
    cards = {n["id"] for n in graph["nodes"] if n["kind"] == "tarot-card"}
    islands = cards - touched
    assert len(islands) < 20, sorted(islands)


def test_the_sweep_reached_the_graph(graph: dict):
    # The manifest is a data file with no test of its own. Without this, an
    # entry silently reading zero records looks exactly like a working build.
    # One per manifest entry, not one per page: an entry reading zero records
    # looks exactly like a working build without this.
    #
    # Counts are pinned to the committed snapshot in data/raw/. A mismatch after
    # a scrape PR lands is the most useful thing the suite can say at that point.
    #
    # Each prefix is tested against provisional nodes only, so curated nodes
    # sharing a prefix (e.g. zodiac-sell-cost) are not counted. No prefix below
    # is a prefix of another — the manifest schema rejects that — so a plain
    # startswith attributes every node to exactly one entry.
    expected = {
        "special-mineral-": 10,
        "zodiac-": 12,
        "trial-": 25,
        "plague-er-": 4,
        "plague-stat-": 6,
        "singularity-milestone-": 27,
        "singularity-tree-": 13,
        "singularity-zodiac-": 12,
        "dilation-node-": 13,
        "dilation-upgrade-": 9,
    }
    swept = [n for n in graph["nodes"] if n.get("confidence") == "provisional"]
    for prefix, count in expected.items():
        owned = [n for n in swept if n["id"].startswith(prefix)]
        assert len(owned) == count, (prefix, len(owned))


def test_the_plague_statistics_table_wires_plague_into_the_graph(graph: dict):
    # Its six rows are the only thing connecting the Plague system to anything
    # else. "Max Stage Completed -> Gold Gain ^" is the clearest: `gold` is a
    # curated node, so this edge must exist or the sweep read the table and
    # resolved nothing out of it.
    stat = next(
        n for n in graph["nodes"] if n["id"] == "plague-stat-max-stage-completed"
    )
    assert stat["kind"] == "stat"
    assert any(
        e["from"] == "plague-stat-max-stage-completed" and e["to"] == "gold"
        for e in graph["edges"]
    )


def test_a_numbered_row_got_a_readable_name(graph: dict):
    # Singularity's tree rows are named "1", "2", "3.1" on the page. Without
    # name_prefix the node is called "1" and nothing says what it is.
    node = next(n for n in graph["nodes"] if n["id"] == "singularity-tree-1")
    assert node["name"] == "Tree Node 1"


def test_every_swept_edge_is_uncertain(graph: dict):
    # The precision guard, asserted against the shipped artifact rather than
    # against the reader. Swept edges must carry `uncertain` confidence because
    # a generic column-heading reader has no structural basis for claiming more.
    #
    # Two curated edges in relationships.yaml cite wiki:Singularity as their
    # source (relic-69 -> atoms-gain and refine-node-121 -> singularity). They
    # originate from parser-minted nodes, not swept ones. Filtering by the
    # `from` id prefix rather than by `confidence` discriminates on something
    # independent of the property under assertion, so a sweep emitting the
    # wrong confidence cannot satisfy this test by shrinking its own input.
    #
    # Infinity is absent from both sets on purpose. Its curated edges cite
    # wiki:Infinity and start with `infinity-upgrade-`, exactly like its swept
    # ones, so no id-prefix filter separates the two and the discrimination this
    # test depends on is unavailable for that page.
    swept_sources = {
        "wiki:Zodiacs",
        "wiki:Trials",
        "wiki:Plague",
        "wiki:Singularity",
        "wiki:Dilation_Tree",
        "wiki:Minerals",
        "wiki:Eternity",
    }
    swept_prefixes = (
        "special-mineral-",
        "zodiac-",
        "trial-",
        "plague-er-",
        "plague-stat-",
        "singularity-milestone-",
        "singularity-tree-",
        "singularity-zodiac-",
        "dilation-node-",
        "dilation-upgrade-",
    )
    swept = [
        e
        for e in graph["edges"]
        if e["source"] in swept_sources and e["from"].startswith(swept_prefixes)
    ]
    assert len(swept) == 76, f"expected 76 swept edges, got {len(swept)}"
    assert all(e.get("confidence") == "uncertain" for e in swept)


def test_a_zodiac_carries_all_four_of_its_bonuses(graph: dict):
    # Pins the multi-effect path end to end. With a single effect_column the
    # sweep would still produce a zodiac node and every other test here would
    # still pass.
    aries = next(n for n in graph["nodes"] if n["id"] == "zodiac-aries")
    assert len(aries["effects"]) == 4


def test_a_dilation_node_kept_its_rowspan_name(graph: dict):
    # "Top 2" only exists if the rowspan carry-forward works: that row's own
    # cells are ["2", effect, per_level] with no axis of its own.
    assert any(n["id"] == "dilation-node-top-2" for n in graph["nodes"])
