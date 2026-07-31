import json
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
GRAPH_PATH = ROOT / "public" / "graph.json"
DATA = ROOT / "data"


def _load_yaml(name: str) -> dict:
    return yaml.safe_load((DATA / name).read_text(encoding="utf-8"))


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
    # Counted against `derived.yaml`, which holds extraction output only, so a
    # curated node sharing a prefix cannot inflate an entry's total no matter
    # what confidence it carries. The test below pins prefix membership there to
    # the swept set exactly. No prefix here is a prefix of another — the manifest
    # schema rejects that — so a plain startswith attributes every node to
    # exactly one entry.
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
    derived = _load_yaml("derived.yaml")
    shipped = {n["id"] for n in graph["nodes"]}
    for prefix, count in expected.items():
        owned = [n["id"] for n in derived["nodes"] if n["id"].startswith(prefix)]
        assert len(owned) == count, (prefix, len(owned))
        for node_id in owned:
            assert node_id in shipped, f"{node_id} never reached the artifact"


def test_the_plague_statistics_table_wires_plague_into_the_graph(graph: dict):
    # Its six rows are the only thing connecting the Plague system to anything
    # else. "Max Stage Completed -> Gold Gain ^" is the clearest: this edge must
    # exist or the sweep read the table and resolved nothing out of it.
    #
    # It lands on `gold-gain`, not on `gold`. Both are curated and both match
    # that cell, but the vocabulary tries longer surface forms first and a match
    # claims its span, so "Gold Gain" wins over the "Gold" inside it. Asserting
    # the more specific target is what makes this test notice if that ordering
    # ever stops holding.
    stat = next(
        n for n in graph["nodes"] if n["id"] == "plague-stat-max-stage-completed"
    )
    assert stat["kind"] == "stat"
    assert any(
        e["from"] == "plague-stat-max-stage-completed" and e["to"] == "gold-gain"
        for e in graph["edges"]
    )


def test_no_two_nodes_share_a_display_name(graph: dict):
    # `name` is what the search box matches and what a node label renders, and
    # neither shows the system beside it, so two nodes sharing one name are
    # indistinguishable in the UI.
    #
    # The Houses table is why this exists: it names its rows "Aries".."Pisces",
    # the same twelve names the Zodiacs page uses, and a manifest entry that
    # justifies its name column by uniqueness *within its own table* cannot see
    # that. The pair below is asserted by hand as well, so removing the
    # `name_prefix` that separates them fails on the case that motivated the
    # test rather than on an anonymous count.
    names = {n["id"]: n["name"] for n in graph["nodes"]}
    assert names["singularity-zodiac-aries"] != names["zodiac-aries"]

    by_name: dict[str, list[str]] = {}
    for node_id, name in names.items():
        by_name.setdefault(name, []).append(node_id)
    shared = {name: ids for name, ids in by_name.items() if len(ids) > 1}
    assert shared == {}, shared


def test_the_misspelled_zodiac_overlay_still_has_a_row_to_correct(graph: dict):
    # The Houses table spells one cell "Saggitarius" and every other page spells
    # it correctly, so the sweep mints a misspelled node and a curated node
    # rewrites the name. The id keeps the misspelling: it is minted from the
    # same cell, and the frontend deep-links to it.
    #
    # If the wiki ever fixes that cell, the swept id moves and the curated node
    # stops overlaying anything -- it becomes a second Sagittarius rather than
    # an error, because a curated node matching no derived id is just a node.
    # Pinning both spellings turns that into a failure naming what to delete.
    derived = {n["id"] for n in _load_yaml("derived.yaml")["nodes"]}
    assert "singularity-zodiac-saggitarius" in derived
    assert "singularity-zodiac-sagittarius" not in derived

    names = {n["id"]: n["name"] for n in graph["nodes"]}
    assert names["singularity-zodiac-saggitarius"] == "Singular Zodiac Sagittarius"


def test_singularity_mult_is_not_the_singularity_count(graph: dict):
    # Two different things the wiki names similarly: `singularity` is the reset
    # count, `singularity-mult` is the multiplier a reset grants, and the page
    # gives the latter its own table of gain modifiers.
    #
    # Deleting the mult node is not an error the schema can see. The prose that
    # named it simply falls through to the shorter surface, and every edge below
    # silently re-points at the count -- still a valid id, still a rendered edge,
    # just describing a relationship the wiki never stated. So the assertion is
    # on the count's *absence* from these sources rather than on the mult's
    # presence: an edge list that has quietly collapsed satisfies the second and
    # fails the first.
    boosts = {(e["from"], e["to"]) for e in graph["edges"] if e["rel"] == "boosts"}

    # Sources whose effect text names only the mult. None may reach the count.
    mult_only = {
        "singularity-zodiac-pisces",  # "Singularity Mult Boost"
        "singularity-tree-1",  # "Adds/increases a Singularity mult gain modifier"
        "singularity-milestone-self-synergism",
        "plague-stat-max-plg",
    }
    for source in mult_only:
        assert (source, "singularity-mult") in boosts, source
        assert (source, "singularity") not in boosts, source

    # And one that names both, to show the split is per-mention rather than a
    # blanket rewrite of everything pointing at the count.
    assert ("singularity-milestone-event-horizon-tax", "singularity-mult") in boosts
    assert ("singularity-milestone-event-horizon-tax", "singularity") in boosts


def test_a_numbered_row_got_a_readable_name(graph: dict):
    # Singularity's tree rows are named "1", "2", "3.1" on the page. Without
    # name_prefix the node is called "1" and nothing says what it is.
    node = next(n for n in graph["nodes"] if n["id"] == "singularity-tree-1")
    assert node["name"] == "Tree Node 1"


def test_the_sweep_prefixes_identify_swept_nodes_exactly():
    # `derived.yaml` records no provenance per node, so the test below infers it
    # from the manifest's id prefixes. That inference is only sound while the
    # prefixes and the `provisional` nodes are the same set — a parser minting an
    # id under a swept prefix, or a reader shipping a node at some other
    # confidence, would silently widen or narrow the assertion it feeds.
    manifest = _load_yaml("sweep.yaml")
    prefixes = tuple(page["id_prefix"] + "-" for page in manifest["pages"])
    derived = _load_yaml("derived.yaml")
    by_prefix = {n["id"] for n in derived["nodes"] if n["id"].startswith(prefixes)}
    provisional = {n["id"] for n in derived["nodes"] if n.get("confidence") == "provisional"}
    assert by_prefix == provisional


def test_every_swept_edge_is_uncertain(graph: dict):
    # The precision guard, asserted against the shipped artifact rather than
    # against the reader. Swept edges must carry `uncertain` confidence because
    # a generic column-heading reader has no structural basis for claiming more.
    #
    # The input is taken from `derived.yaml`, which holds extraction output only:
    # an edge out of a swept node there is swept by construction, with no appeal
    # to the property under assertion, so a reader emitting the wrong confidence
    # cannot satisfy this test by shrinking its own input. Curated overrides and
    # suppressions are removed by key because the merge replaces or deletes those
    # edges before they reach the artifact.
    manifest = _load_yaml("sweep.yaml")
    prefixes = tuple(page["id_prefix"] + "-" for page in manifest["pages"])
    derived = _load_yaml("derived.yaml")
    curated = _load_yaml("relationships.yaml")

    def key(edge: dict) -> tuple[str, str, str]:
        return edge["from"], edge["to"], edge["rel"]

    swept = {key(e) for e in derived["edges"] if e["from"].startswith(prefixes)}
    swept -= {key(e) for e in curated.get("edges") or []}
    swept -= {key(s) for s in curated.get("suppress") or []}

    assert len(swept) == 430, f"expected 430 swept edges, got {len(swept)}"
    shipped = {key(e): e for e in graph["edges"]}
    for edge in swept:
        assert edge in shipped, f"{edge} never reached the artifact"
        assert shipped[edge].get("confidence") == "uncertain", edge


def test_each_gem_keeps_the_spawn_effect_the_sweep_read_for_it(graph: dict):
    # The gems are the one place a curated node restates text the sweep already
    # produced. It has to: the sacrificed effects are documented in a table the
    # readers cannot reach, and a curated `effects` list replaces the derived one
    # wholesale rather than extending it. That makes the copy a masking risk of
    # exactly the kind the relic-name tests exist for — a wiki edit to a spawn
    # number would be silently overwritten by the stale curated line. Pinning the
    # two together turns that into a failure naming the gem to update.
    derived = {
        n["id"]: n
        for n in _load_yaml("derived.yaml")["nodes"]
        if n["id"].startswith("special-mineral-")
    }
    assert len(derived) == 10
    shipped = {n["id"]: n for n in graph["nodes"]}
    for gem_id, swept in derived.items():
        effects = [e["text"] for e in shipped[gem_id]["effects"]]
        assert effects[0] == swept["effects"][0]["text"], gem_id
        assert effects[1].startswith("Sacrificed: "), gem_id
        assert len(effects) == 2, gem_id


def test_a_zodiac_carries_all_four_of_its_bonuses(graph: dict):
    # Pins the multi-effect path end to end. With a single effect_column the
    # sweep would still produce a zodiac node and every other test here would
    # still pass.
    aries = next(n for n in graph["nodes"] if n["id"] == "zodiac-aries")
    assert len(aries["effects"]) == 4


def test_an_input_a_bonus_reads_points_at_the_bonus_not_away_from_it(graph: dict):
    # "Boosts IP gain based on challenge times" names two nodes doing opposite
    # jobs. Reading both as targets says the upgrade boosts the very quantity it
    # measures, which puts the stat downstream of the thing that consumes it and
    # breaks the upstream chain the viewer is built around.
    pairs = {(e["from"], e["to"]) for e in graph["edges"] if e["rel"] == "boosts"}
    for upgrade, stat in (
        ("infinity-upgrade-15-2-fast-ip-gain", "challenge-times"),
        ("infinity-upgrade-8-2-generator-power", "generator-power"),
        ("tarot-the-star", "stars"),
    ):
        assert (stat, upgrade) in pairs, f"{stat} should feed {upgrade}"
        assert (upgrade, stat) not in pairs, f"{upgrade} still points at {stat}"


def test_an_upgrade_that_grants_a_thing_still_points_at_it(graph: dict):
    # The guard on the test above: reversing everything would satisfy it too.
    # "A Falling Star" grants stars with no input marker in sight, so it must
    # keep running forwards.
    pairs = {(e["from"], e["to"]) for e in graph["edges"]}
    assert ("infinity-upgrade-21-1-a-falling-star", "stars") in pairs


def test_the_whole_eternity_zoo_is_present_and_priced(graph: dict):
    # The 81 Animals sit behind an unscraped {{AnimalGrid}} template, so they are
    # transcribed by hand and nothing regenerates them. 1,524 AP is the total the
    # Animals page states, which makes it the one arithmetic check that a dropped
    # or mistyped row cannot survive.
    animals = [
        n
        for n in graph["nodes"]
        if n["system"] == "eternity" and n["id"].startswith("animal-")
    ]
    assert len(animals) == 81
    assert sum(int(n["cost"].removesuffix(" AP")) for n in animals) == 1524


def test_the_plague_currency_never_resolves_to_the_animal_named_pig(graph: dict):
    # "PIG" is the Plague layer's currency and "Pig" is an animal, and the
    # vocabulary matches mixed-case surfaces without regard to case. Four
    # suppressions hold that line; without them the Eternity Zoo grows edges from
    # relics and refine nodes that have nothing to do with it.
    assert any(n["id"] == "animal-pig" for n in graph["nodes"])
    assert [e["from"] for e in graph["edges"] if e["to"] == "animal-pig"] == []


def test_a_tree_node_boosts_the_numbered_upgrade_it_names(graph: dict):
    # The tree node's effect reads "Dilation Upgrade 1 is 30% stronger". That
    # upgrade's name is derived, so it never enters the curated vocabulary and the
    # resolver can only see the bare word "Dilation" — which is the wrong target.
    pairs = {(e["from"], e["to"]) for e in graph["edges"]}
    for tree_node, upgrade in (("top-1", 1), ("middle-1", 2), ("bottom-1", 3)):
        assert (f"dilation-node-{tree_node}", f"dilation-upgrade-{upgrade}") in pairs
        assert (f"dilation-node-{tree_node}", "dilation") not in pairs


def test_a_dilation_node_kept_its_rowspan_name(graph: dict):
    # "Top 2" only exists if the rowspan carry-forward works: that row's own
    # cells are ["2", effect, per_level] with no axis of its own.
    assert any(n["id"] == "dilation-node-top-2" for n in graph["nodes"])


def test_attacks_hangs_off_unity(graph: dict):
    # The wiki files Attacks under Unity, and the sidebar reads its nesting
    # straight off this parent. Declared at the root it renders as a fifth
    # prestige layer beside Revolution, Infinity, Eternity and Unity.
    attacks = next(s for s in graph["systems"] if s["id"] == "attacks")
    assert attacks["parent"] == "unity"


def test_a_rune_claims_its_own_words_before_a_planet_can(graph: dict):
    # "Sun runes generation is 1.2x faster" and "Moon runes ..." are about runes,
    # but Sun and Moon are also Planets. The rune nodes exist so that the longer
    # surface claims the span first. Relic 34 is the one sentence this cannot
    # reach — it says "Sun and Moon runes", so "Sun runes" is never contiguous and
    # a suppression carries that case instead.
    pairs = {(e["from"], e["to"]) for e in graph["edges"]}
    assert ("refine-node-47", "rune-sun") in pairs
    assert ("refine-node-48", "rune-moon") in pairs
    assert ("refine-node-47", "planet-sun") not in pairs
    assert ("refine-node-48", "planet-moon") not in pairs
    assert ("relic-34", "rune-sun") in pairs
    assert ("relic-34", "planet-sun") not in pairs


def test_a_planet_shop_feature_does_not_capture_the_bare_gerund(graph: dict):
    # The shop's features are called Merging, Enhancing, Redistribution and
    # Sacrificing on the wiki. Nodes named that way also match "merging special
    # minerals" and "Sacrificing relics", which are unrelated mechanics, so each
    # node carries the qualified name the surrounding page implies.
    for node_id, name in (
        ("feature-merging", "Zodiac Merging"),
        ("feature-enhancing", "Zodiac Enhancing"),
        ("feature-redistribution", "Zodiac Redistribution"),
        ("feature-sacrificing", "Zodiac Sacrificing"),
    ):
        node = next(n for n in graph["nodes"] if n["id"] == node_id)
        assert node["name"] == name
    pairs = {(e["from"], e["to"]) for e in graph["edges"]}
    assert ("relic-45", "feature-merging") not in pairs
    assert ("refine-node-66", "feature-sacrificing") not in pairs


def test_every_planet_bonus_names_the_season_that_grants_it(graph: dict):
    # A Planet's four bonuses are one per Zodiac season, and the season lives only
    # in the column heading of the wiki's table. Dropped, each Planet states four
    # bonuses and nothing records which season earns which — so the season is
    # written into the effect text itself.
    seasons = ("(Spring)", "(Summer)", "(Autumn)", "(Winter)")
    planets = [
        n
        for n in graph["nodes"]
        if n["id"].startswith("planet-") and n["id"] != "planet-shop"
    ]
    assert len(planets) == 12
    for planet in planets:
        labelled = [
            e["text"] for e in planet["effects"] if e["text"].endswith(seasons)
        ]
        # Fortune Pars grants one bonus in every season rather than four.
        assert len(labelled) == 4 or planet["id"] == "planet-fortune-pars"


def test_the_attack_damage_formula_converges_on_one_node(graph: dict):
    # The Attacks page multiplies four separate stats into a single Total Attack
    # Base Damage. Each is a node in its own right because relics and tarot cards
    # boost them individually, so the convergence is the only place the graph
    # records that they are factors of one product.
    pairs = {(e["from"], e["to"]) for e in graph["edges"]}
    for factor in (
        "attack-mult",
        "score-damage-mult",
        "cumulative-mult",
        "attack-exponent",
    ):
        assert (factor, "attack-base-damage") in pairs
    assert ("attack-base-damage", "attack-level") in pairs


def test_an_unlock_is_curated_rather_than_left_to_the_vocabulary(graph: dict):
    # Every gate below is also stated in prose the vocabulary matcher can see
    # ("Unlocks Tarot", "Unlock magnets"), so dropping the curated edge does not
    # disconnect anything — it silently downgrades the gate to a `boosts` edge at
    # `uncertain`. Pinning the rel is what makes that regression visible: an
    # unlock and a boost read identically in the viewer but mean opposite things
    # about whether the target exists yet.
    rels = {(e["from"], e["to"]): e["rel"] for e in graph["edges"]}
    for source, target in (
        ("attack-level", "minerals"),
        ("mineral-level", "polish-points"),
        ("mineral-level", "refinement-points"),
        ("refine-node-5", "merge-level"),
        ("refine-node-18", "magnets"),
        ("refine-node-28", "polish-enhance"),
        ("refine-node-35", "runes"),
        ("refine-node-41", "special-minerals"),
        ("refine-node-55", "elements"),
        ("refine-node-70", "tarot"),
        ("refine-node-85", "sacrifice-dust"),
        ("refine-node-103", "plague"),
    ):
        assert rels.get((source, target)) == "unlocks", f"{source} -> {target}"


def test_each_polish_weapon_is_bought_with_one_currency_and_pays_a_different_stat(
    graph: dict,
):
    # The five weapons share a cost and nothing else: they are the one place the
    # Minerals layer reaches out to Attacks and to Gold. Written as a single
    # "Polish" node the fan-out collapses and every downstream chain through
    # Gold Gain or Attack Ascension Power loses its origin. The two rels differ
    # on purpose — spending Polish Points is a cost, the weapon's output is not.
    edges = {(e["from"], e["to"]): e["rel"] for e in graph["edges"]}
    payouts = {
        "polish-sword": "value-points",
        "polish-axe": "mineral-cost-exp",
        "polish-spear": "gold-gain",
        "polish-bow": "attack-ascension-power",
        "polish-knuckles": "mineral-local-speed",
    }
    assert len(set(payouts.values())) == 5
    for weapon, stat in payouts.items():
        assert edges.get(("polish-points", weapon)) == "requires"
        assert edges.get((weapon, stat)) == "boosts"
        assert edges.get(("polish-enhance", weapon)) == "boosts"


def test_the_attack_stat_claims_its_words_before_the_revolution_stat(graph: dict):
    # Relic 52 and the Two of Swords both say "Ascension Power from VP", but the
    # power they mean belongs to Attacks, not to the Revolution stat of nearly
    # the same name. The longer surface exists so it claims the span first; drop
    # the node and both edges land back on `ascension-power`, which is wrong in a
    # way nothing else in the graph would report.
    pairs = {(e["from"], e["to"]) for e in graph["edges"]}
    assert ("relic-52", "attack-ascension-power") in pairs
    assert ("relic-52", "ascension-power") not in pairs
    assert ("tarot-two-of-swords", "attack-ascension-power") in pairs


def test_runes_are_filed_where_they_are_earned(graph: dict):
    # Runes were first curated under Relics because Relic 34 is what named them,
    # but they are unlocked by Refine Node 35 and documented on the Minerals
    # page. The system decides which sidebar branch they render under, so the
    # wrong one hides them from the layer that actually produces them.
    by_id = {n["id"]: n for n in graph["nodes"]}
    for rune in ("runes", "rune-sun", "rune-moon"):
        assert by_id[rune]["system"] == "minerals"


def test_no_node_claims_a_bare_element_or_suit_name(graph: dict):
    # The load-bearing guard on a rejected design. build_vocabulary() hands a
    # node's `name` to the resolver unconditionally, so naming these nodes
    # "Fire" or "Wands" -- the obvious display choice -- silently turns them
    # into match surfaces, and a scan of the corpus showed what that costs:
    # "Wands 1 first effect mult x" is a positional reference to a sibling
    # card, "Earth Plague Stage" is a plague stage, "each Water Zodiac" is a
    # zodiac category, and "1e4600 Fire" is a challenge entry requirement.
    # That is roughly sixty wrong edges bought for eight right ones.
    #
    # The failure mode is silent: nothing else in the suite counts edges into
    # these nodes, so a rename would land as a large quiet regression. Aliases
    # are checked too -- an alias is a surface by exactly the same path.
    bare = {"fire", "earth", "wind", "water",
            "wands", "cups", "swords", "pentacles"}
    for node in graph["nodes"]:
        for surface in [node["name"], *(node.get("aliases") or [])]:
            assert surface.casefold() not in bare, (
                f"{node['id']} claims the bare surface {surface!r}; use the "
                f"multiword form ('Fire Generation', 'Wands Cards') instead"
            )


def test_every_element_upgrade_node_7_boosts_its_own_factor_2(graph: dict):
    # Curated, because "boosts its own factor 2" is a relative reference no
    # surface-form matcher can resolve. Four hand-written edges are exactly the
    # kind of thing a later bulk edit drops without noticing.
    pairs = {(e["from"], e["to"]) for e in graph["edges"]}
    for element in ("fire", "earth", "wind", "water"):
        assert (f"{element}-node-7", f"{element}-factor-2") in pairs


def test_each_tarot_suit_feeds_its_own_element_factor_1(graph: dict):
    # The suit-to-element mapping (wands->fire, pentacles->earth,
    # swords->wind, cups->water) is stated once per element in four separate
    # rows of the upgrades table. Nothing structural enforces it, so a
    # mis-paired curation would swap two suits and stay green everywhere else.
    pairs = {(e["from"], e["to"]) for e in graph["edges"]}
    for suit, element in (("wands", "fire"), ("pentacles", "earth"),
                          ("swords", "wind"), ("cups", "water")):
        assert (f"tarot-suit-{suit}", f"{element}-factor-1") in pairs
        # Direction guard: the factor is never the source.
        assert (f"{element}-factor-1", f"tarot-suit-{suit}") not in pairs


def test_the_plague_resource_chain_runs_end_to_end(graph: dict):
    # The Plague page states its economy entirely in prose, so no table backs
    # this chain up -- every link is curated, and a dropped link would silently
    # orphan everything downstream of it again.
    pairs = {(e["from"], e["to"]) for e in graph["edges"]}
    chain = ("plague", "plague-generators", "plague-points", "erp",
             "endoplasmic-reticula", "virus-essence", "virus-points")
    for source, target in zip(chain, chain[1:]):
        assert (source, target) in pairs, f"broken link: {source} -> {target}"


def test_every_er_upgrade_requires_virus_points(graph: dict):
    upgrades = {n["id"] for n in graph["nodes"]
                if n["id"].startswith("plague-er-")}
    assert len(upgrades) == 4
    spends = {e["to"] for e in graph["edges"]
              if e["from"] == "virus-points" and e["rel"] == "requires"}
    assert upgrades <= spends


def test_no_er_upgrade_boosts_the_resource_it_consumes(graph: dict):
    # A conversion sentence names its input and its output, and the matcher
    # resolves both. The input edges are suppressed; this pins that they stay
    # suppressed, because re-minting them would reverse four real flows.
    backwards = {
        ("plague-er-conversion-rate", "plague-points"),
        ("plague-er-dissolve-efficiency", "endoplasmic-reticula"),
        ("plague-er-essence-density", "virus-essence"),
        ("singularity-milestone-virusologist", "virus-essence"),
    }
    assert backwards & {(e["from"], e["to"]) for e in graph["edges"]} == set()
