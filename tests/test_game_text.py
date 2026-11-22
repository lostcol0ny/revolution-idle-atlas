import types

import atlas.extract as extract_module
from atlas.extract import game_text
from atlas.extract.refs import Vocabulary, resolve
from atlas.extract.result import ExtractResult
from atlas.models import EdgeConfidence, GameData, GameNode, Kind, Node, Rel

VOCAB = Vocabulary(
    [
        ("α generator", "particle-generators"),
        ("Particle Rank", "particles-rank"),
        ("Luck", "luck"),
        ("Singularity", "singularity"),
    ]
)


def _bonus(node_id: str, description: str) -> GameNode:
    return GameNode(
        id=node_id,
        name=node_id,
        description=description,
        system="particles-grades",
        kind=Kind.UPGRADE,
    )


def _edges(*entries: GameNode) -> set[tuple[str, str, str, str]]:
    result = game_text.extract(GameData(nodes=list(entries)), VOCAB)
    return {(e.from_, e.to, str(e.rel), str(e.confidence)) for e in result.edges}


def test_an_improver_is_upstream_of_the_bonus_it_improves():
    edges = _edges(
        _bonus(
            "particles-rank-bonus-3",
            "α generator base ×(1 + 0.1 × generator level). "
            "Refinement node 141 improves this bonus.",
        )
    )
    assert ("particles-rank-bonus-3", "refine-node-141", "boosts", "uncertain") not in edges
    assert edges == {
        ("particles-rank", "particles-rank-bonus-3", "requires", "documented"),
        ("particles-rank-bonus-3", "particle-generators", "boosts", "uncertain"),
        ("refine-node-141", "particles-rank-bonus-3", "boosts", "uncertain"),
    }


def test_an_improved_by_parenthetical_is_an_input():
    edges = _edges(
        _bonus(
            "particles-tier-bonus-1",
            "α generator base ×(β + 1)^0.2 (improved by refinement node 147).",
        )
    )
    assert ("refine-node-147", "particles-tier-bonus-1", "boosts", "uncertain") in edges
    assert ("particles-tier-bonus-1", "particle-generators", "boosts", "uncertain") in edges


def test_a_grade_is_read_by_a_bonus_never_boosted_by_it():
    edges = _edges(
        _bonus("particles-rank-bonus-8", "Particle Rank boosts Luck by a value")
    )
    assert edges == {
        ("particles-rank", "particles-rank-bonus-8", "requires", "documented"),
        ("particles-rank-bonus-8", "luck", "boosts", "uncertain"),
    }


def test_a_matched_node_gets_its_member_link_but_not_its_description_matched():
    # A spark the wiki already describes: its wiki effect is what is matched.
    spark = GameNode(
        id="particles-spark-green", name="Green Spark", description="Luck: an exponent"
    )
    assert _edges(spark) == {
        ("particles-sparks", "particles-spark-green", "unlocks", "documented"),
    }


def test_game_edges_are_boosts_from_the_game():
    result = game_text.extract(
        GameData(nodes=[_bonus("particles-pent-bonus-9", "Luck ^2")]), VOCAB
    )
    boost = next(e for e in result.edges if e.rel == Rel.BOOSTS)
    assert boost.source == "game"
    assert boost.confidence == EdgeConfidence.UNCERTAIN


def test_singularity_tree_nodes_resolve_by_number():
    refs = resolve(
        "The base effects of Singularity Tree nodes 3.1 and 3.2 are multiplied", VOCAB
    )
    # The tree claims its span, so "Singularity" does not also land on the count.
    assert [r.target_id for r in refs] == ["singularity-tree-3-1", "singularity-tree-3-2"]


def _run_with(monkeypatch, tmp_path, game: GameData):
    filler = ExtractResult(
        nodes=[Node(id="relic-1", name="One", system="relics", kind=Kind.RELIC)]
    )
    stub = types.SimpleNamespace(
        extract=lambda _raw_dir, _vocab=None: filler,
        extract_challenge_rewards=lambda _raw_dir, _nodes: ExtractResult(),
    )
    for name in ("relics", "refine_tree", "tarot", "elements"):
        monkeypatch.setattr(extract_module, name, stub)
    return extract_module.run_all(
        tmp_path,
        VOCAB,
        frozenset({"particles-rank", "particles-sparks"}),
        game=game,
    )


def test_run_all_keeps_edges_to_nodes_only_the_game_creates(tmp_path, monkeypatch):
    game = GameData(nodes=[_bonus("particles-rank-bonus-1", "Relic 1 effect ×rank.")])
    result = _run_with(monkeypatch, tmp_path, game)
    assert {(e.from_, e.to) for e in result.edges} == {
        ("particles-rank", "particles-rank-bonus-1"),
        ("particles-rank-bonus-1", "relic-1"),
    }
    assert result.dropped == []


def test_run_all_drops_edges_to_a_matched_node_the_wiki_lost(tmp_path, monkeypatch):
    # An entry without system and kind only overlays a wiki node. Once that node
    # is gone the build creates nothing for it, so its edges must not survive.
    game = GameData(nodes=[GameNode(id="particles-spark-green", name="Green Spark")])
    result = _run_with(monkeypatch, tmp_path, game)
    assert result.edges == []
    assert [(d.from_id, d.to_id) for d in result.dropped] == [
        ("particles-sparks", "particles-spark-green")
    ]


ACHIEVEMENT_VOCAB = Vocabulary(
    [("Infinities", "infinities"), ("IP", "infinity-points"), ("Dilation", "dilation")]
)


def _achievement(description: str, *effects: str) -> GameNode:
    return GameNode(
        id="achievement-36",
        name="Achievement 36 (Many of Them)",
        description=description,
        effects=list(effects),
        system="achievements",
        kind=Kind.ACHIEVEMENT,
    )


def _achievement_edges(entry: GameNode) -> set[tuple[str, str, str]]:
    result = game_text.extract(GameData(nodes=[entry]), ACHIEVEMENT_VOCAB)
    return {(e.from_, e.to, str(e.rel)) for e in result.edges}


def test_an_achievement_boosts_from_its_reward_and_requires_its_threshold():
    edges = _achievement_edges(_achievement("Reach 5 Infinities", "x2 IP gain"))
    assert edges == {
        ("achievement-36", "infinity-points", "boosts"),
        ("infinities", "achievement-36", "requires"),
    }


def test_an_achievement_goal_never_boosts_what_it_names():
    # The goal is what the player must reach, as a Tarot challenge's penalty is
    # what it restricts; matching it would claim the achievement raises it.
    # Without a reward there is no text an outgoing boost may come from.
    for entry in (
        _achievement("Reach 5 Infinities"),
        _achievement("Reach a score of e5e10 in Dilation"),
        _achievement("Reach a score of e5e10 in Dilation", "Faster optimization"),
    ):
        assert not any(rel == "boosts" for _, _, rel in _achievement_edges(entry))


def test_an_achievement_goal_that_is_no_plain_threshold_requires_nothing():
    edges = _achievement_edges(
        _achievement("Reach a score of e5e10 in Dilation", "x2 IP gain")
    )
    assert edges == {("achievement-36", "infinity-points", "boosts")}


def test_a_macro_block_reward_names_what_the_block_runs():
    edges = _achievement_edges(
        _achievement("Unite", "Unlocks macro block for Dilation. x2 IP gain")
    )
    assert edges == {("achievement-36", "infinity-points", "boosts")}
