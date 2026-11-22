from atlas.merge import merge
from atlas.models import (
    Dataset,
    Edge,
    Effect,
    GameData,
    GameNode,
    Kind,
    Node,
    NodeConfidence,
    Op,
    Rel,
    Suppression,
    SystemDef,
)


def _derived() -> Dataset:
    return Dataset(
        nodes=[
            Node(
                id="relic-38",
                name="Relic 38",
                system="relics",
                kind=Kind.RELIC,
                wiki="Relics",
                effects=[Effect(text="Adds base to Refine Node 2", per_level="+1.00")],
                line=7,
            ),
            # `wiki` is set here and deliberately NOT set on the curated
            # relic-39 in the overlay test below. It is the only field that
            # differs between the two, so it is the only thing that can tell a
            # field-by-field overlay from a wholesale replacement.
            Node(
                id="relic-39",
                name="Relic 39",
                system="relics",
                kind=Kind.RELIC,
                wiki="Relics",
                line=14,
            ),
        ],
        edges=[
            Edge(
                from_="relic-38",
                to="refine-node-2",
                rel=Rel.BOOSTS,
                source="Relics",
                targets_effect=0,
                line=21,
            ),
            Edge(from_="relic-39", to="refine-node-3", rel=Rel.BOOSTS, source="Relics", line=25),
        ],
    )


def test_curated_node_overlays_field_by_field():
    curated = Dataset(
        nodes=[Node(id="relic-39", name="Windmill Pendant", system="relics", kind=Kind.RELIC)]
    )
    merged, _ = merge(_derived(), curated)

    node = next(n for n in merged.nodes if n.id == "relic-39")
    # The curated node sets `wiki` to nothing, so only a field-by-field overlay
    # can leave the derived "Relics" in place. Wholesale replacement yields
    # None here, which is what makes this assertion the load-bearing one.
    assert node.wiki == "Relics"
    assert node.name == "Windmill Pendant"
    assert node.system == "relics"
    assert node.kind is Kind.RELIC


def test_curated_node_overlay_keeps_derived_fields_it_does_not_mention():
    curated = Dataset(
        nodes=[
            Node(
                id="relic-38",
                name="Smart Man",
                system="relics",
                kind=Kind.RELIC,
                confidence=NodeConfidence.PROVISIONAL,
            )
        ]
    )
    merged, _ = merge(_derived(), curated)

    node = next(n for n in merged.nodes if n.id == "relic-38")
    assert node.confidence is NodeConfidence.PROVISIONAL
    assert node.wiki == "Relics"
    assert node.effects[0].per_level == "+1.00"


def test_curated_node_that_is_new_is_appended_after_the_derived_ones():
    curated = Dataset(
        nodes=[Node(id="singularity", name="Singularity", system="unity", kind=Kind.CURRENCY)]
    )
    merged, _ = merge(_derived(), curated)
    assert [n.id for n in merged.nodes] == ["relic-38", "relic-39", "singularity"]


def test_a_generated_note_follows_a_curated_rewording_of_its_effect():
    # Parsers copy the effect an edge was read from into its note, from the
    # source's effects or the target's.
    derived = Dataset(
        nodes=[
            Node(
                id="refine-node-10",
                name="Refine Node 10",
                system="refine",
                kind=Kind.TREE_NODE,
                effects=[Effect(text="PP gain ^(1 + 0.1*lvl)")],
            )
        ],
        edges=[
            Edge(
                from_="refine-node-10",
                to="polish-points",
                rel=Rel.BOOSTS,
                source="wiki:Refine",
                note="PP gain ^(1 + 0.1*lvl)",
            ),
            Edge(
                from_="refinement-points",
                to="refine-node-10",
                rel=Rel.BOOSTS,
                source="wiki:Refine",
                note="PP gain ^(1 + 0.1*lvl)",
            ),
            Edge(
                from_="refine-node-10",
                to="gold",
                rel=Rel.BOOSTS,
                source="wiki:Refine",
                note="Some other wording",
            ),
        ],
    )
    typeset = r"PP gain $^{1 + 0.1 \times \text{lvl}}$"
    curated = Dataset(
        nodes=[
            Node(
                id="refine-node-10",
                name="Refine Node 10",
                system="refine",
                kind=Kind.TREE_NODE,
                effects=[Effect(text=typeset)],
            )
        ]
    )
    merged, _ = merge(derived, curated)

    assert [e.note for e in merged.edges] == [typeset, typeset, "Some other wording"]


def _refine_node_40(*effects: str) -> Node:
    return Node(
        id="refine-node-40",
        name="Refine Node 40",
        system="refine",
        kind=Kind.TREE_NODE,
        effects=[Effect(text=text) for text in effects],
    )


def _magnet_notes(curated_effects: tuple[str, ...], derived_effects: tuple[str, ...]) -> list:
    derived = Dataset(
        nodes=[_refine_node_40(*derived_effects)],
        edges=[
            Edge(
                from_="refine-node-40",
                to=target,
                rel=Rel.BOOSTS,
                source="wiki:Refine",
                note=note,
            )
            for target, note in zip(("value-points", "polish-points"), derived_effects)
        ],
    )
    merged, _ = merge(derived, Dataset(nodes=[_refine_node_40(*curated_effects)]))
    return [e.note for e in merged.edges]


def test_a_curated_list_that_prepends_an_effect_rewrites_no_note():
    # Pairing by position would read every derived effect as reworded into the
    # one now ahead of it, and stamp the wrong text on each note.
    derived = ("Magnet upgrades are powered to ^(1.1*lvl)", "VP gain ^2")
    curated = ("A new leading effect", *derived)
    assert _magnet_notes(curated, derived) == list(derived)


def test_a_curated_list_that_rewords_two_effects_rewrites_no_note():
    derived = ("Magnet upgrades are powered to ^(1.1*lvl)", "VP gain ^2")
    curated = (r"Magnet upgrades are powered to $^{1.1 \times \text{lvl}}$", "VP gain $^2$")
    assert _magnet_notes(curated, derived) == list(derived)


def test_curated_edge_replaces_the_derived_one_wholesale():
    curated = Dataset(
        edges=[
            Edge(
                from_="relic-38",
                to="refine-node-2",
                rel=Rel.BOOSTS,
                op=Op.ADD,
                note="confirmed in game at level 3",
                source="in-game",
            )
        ]
    )
    merged, _ = merge(_derived(), curated)

    edge = next(e for e in merged.edges if e.from_ == "relic-38")
    # This assertion is the whole point of the test, and it must come first.
    # The derived edge set `targets_effect=0`; the curated one does not mention
    # it. Under a field-by-field overlay the derived 0 would survive, so this is
    # the ONLY assertion here that can tell wholesale replacement from overlay —
    # every other field below is set by the curated edge and would therefore be
    # applied under either implementation.
    assert edge.targets_effect is None
    assert edge.op is Op.ADD
    assert edge.note == "confirmed in game at level 3"
    assert edge.source == "in-game"
    assert len(merged.edges) == 2


def test_suppress_removes_a_derived_edge():
    curated = Dataset(
        suppress=[
            Suppression(
                from_="relic-39",
                to="refine-node-3",
                rel=Rel.BOOSTS,
                reason="the wiki sentence names refine node 3 as a comparison",
            )
        ]
    )
    merged, problems = merge(_derived(), curated)
    assert [(e.from_, e.to) for e in merged.edges] == [("relic-38", "refine-node-2")]
    assert problems == []


def test_suppress_removes_a_curated_edge_too():
    # Suppression is applied to the merged result, not to the derived half, so
    # a rule cannot silently stop working when the edge migrates between files.
    curated = Dataset(
        edges=[Edge(from_="a", to="b", rel=Rel.UNLOCKS, source="wiki")],
        suppress=[Suppression(from_="a", to="b", rel=Rel.UNLOCKS, reason="wrong")],
    )
    merged, _ = merge(Dataset(), curated)
    assert merged.edges == []


def test_suppression_that_matches_nothing_is_reported_as_a_warning():
    curated = Dataset(
        suppress=[
            Suppression(
                from_="relic-1", to="relic-2", rel=Rel.BOOSTS, reason="no longer real", line=9
            )
        ]
    )
    _, problems = merge(_derived(), curated)
    assert len(problems) == 1
    assert problems[0].severity == "warning"
    assert "relic-1" in problems[0].message
    assert problems[0].line == 9


def test_derived_line_numbers_are_cleared_and_curated_ones_survive():
    curated = Dataset(
        nodes=[Node(id="relic-39", name="Windmill Pendant", system="relics", kind=Kind.RELIC, line=3)]
    )
    merged, _ = merge(_derived(), curated)

    assert next(n for n in merged.nodes if n.id == "relic-38").line is None
    assert next(n for n in merged.nodes if n.id == "relic-39").line == 3
    assert all(e.line is None for e in merged.edges)


def test_systems_come_from_the_curated_file_only():
    # The derived side carries a system of its own. Nothing may carry it into
    # the result — without it, `systems=curated.systems + derived.systems`
    # would pass this test unchanged.
    derived = _derived()
    derived.systems = [SystemDef(id="ghost", name="Ghost")]
    curated = Dataset(systems=[SystemDef(id="unity", name="Unity")])

    merged, _ = merge(derived, curated)

    assert "ghost" not in [s.id for s in merged.systems]
    assert [s.id for s in merged.systems] == ["unity"]


def test_merging_into_an_empty_curated_file_is_the_derived_dataset():
    merged, _ = merge(_derived(), Dataset())
    assert [n.id for n in merged.nodes] == ["relic-38", "relic-39"]
    assert len(merged.edges) == 2


def test_a_node_id_repeated_in_the_curated_file_is_an_error():
    # merge() collapses nodes into a dict keyed by id, so validate_dataset can
    # no longer see this duplicate by the time it runs. Without merge reporting
    # it, one of the two curated records is discarded with no output at all.
    curated = Dataset(
        nodes=[
            Node(id="relic-1", name="One", system="relics", kind=Kind.RELIC, line=4),
            Node(id="relic-1", name="Other", system="relics", kind=Kind.RELIC, line=9),
        ]
    )
    _, problems = merge(Dataset(), curated)

    assert len(problems) == 1
    assert problems[0].severity == "error"
    assert "duplicate node id 'relic-1'" in problems[0].message
    # The losing record is the second one, so its line is the useful one.
    assert problems[0].line == 9


def test_a_node_id_repeated_in_the_derived_file_is_an_error():
    derived = Dataset(
        nodes=[
            Node(id="relic-1", name="One", system="relics", kind=Kind.RELIC),
            Node(id="relic-1", name="Other", system="relics", kind=Kind.RELIC),
        ]
    )
    _, problems = merge(derived, Dataset())

    assert len(problems) == 1
    assert problems[0].severity == "error"
    assert "duplicate node id 'relic-1'" in problems[0].message


def test_a_duplicate_carries_the_path_of_the_file_it_was_found_in():
    """Each side must be labelled with its own file, not one shared path.

    A duplicate is found before the merge nulls derived line numbers, so it is
    the one problem that still knows its provenance — and the one that renders
    against the wrong file if it does not carry it.
    """
    def _dupes() -> list[Node]:
        return [
            Node(id="x", name="A", system="relics", kind=Kind.RELIC),
            Node(id="x", name="B", system="relics", kind=Kind.RELIC),
        ]

    _, problems = merge(
        Dataset(nodes=_dupes()),
        Dataset(nodes=_dupes()),
        derived_path="data/derived.yaml",
        curated_path="data/relationships.yaml",
    )

    # Both sides duplicate the same id, so a single shared path would still
    # produce two problems — only the paths tell the implementations apart.
    assert [p.path for p in problems] == [
        "data/derived.yaml",
        "data/relationships.yaml",
    ]


def test_a_duplicate_has_no_path_when_the_caller_names_no_files():
    # The path arguments are optional, so a caller that omits them must still
    # get the problem — just with nothing to render it under.
    derived = Dataset(
        nodes=[
            Node(id="x", name="A", system="relics", kind=Kind.RELIC),
            Node(id="x", name="B", system="relics", kind=Kind.RELIC),
        ]
    )
    _, problems = merge(derived, Dataset())
    assert problems[0].path is None


def test_the_same_id_in_both_files_is_an_override_not_a_duplicate():
    # This is the whole point of the merge and must never be reported. The
    # check is per-file, so an id present once on each side is fine.
    curated = Dataset(
        nodes=[Node(id="relic-38", name="Smart Man", system="relics", kind=Kind.RELIC)]
    )
    merged, problems = merge(_derived(), curated)

    assert problems == []
    assert [n.id for n in merged.nodes] == ["relic-38", "relic-39"]


def test_an_edge_repeated_across_both_files_is_not_reported():
    # Edge override is the documented mechanism, and validate_dataset never
    # checked for duplicate edges. Only node ids are scoped into this check.
    curated = Dataset(
        edges=[
            Edge(
                from_="relic-38",
                to="refine-node-2",
                rel=Rel.BOOSTS,
                source="in-game",
            )
        ]
    )
    _, problems = merge(_derived(), curated)
    assert problems == []


def test_two_derived_edges_with_same_key_but_distinct_payload_warn():
    # Two generated edges sharing (from, to, rel) but differing in targets_effect
    # or note represent distinct claims — the first being silently discarded
    # deletes evidence. The merge must warn so the collision is visible.
    derived = Dataset(
        nodes=[],
        edges=[
            Edge(
                from_="relic-38",
                to="refine-node-2",
                rel=Rel.BOOSTS,
                source="Relics",
                targets_effect=0,
            ),
            Edge(
                from_="relic-38",
                to="refine-node-2",
                rel=Rel.BOOSTS,
                source="Relics",
                targets_effect=1,
            ),
        ],
    )
    merged, problems = merge(derived, Dataset(), derived_path="data/derived.yaml")

    assert len(problems) == 1
    assert problems[0].severity == "warning"
    # Both endpoints must be named so the reader can find the collision without
    # knowing which parser produced it.
    assert "relic-38" in problems[0].message
    assert "refine-node-2" in problems[0].message
    # The message tells a curator the earlier edge is the one that was lost, so
    # something has to pin which one actually survives. Without this the message
    # could be re-inverted and the suite would stay green.
    assert [e.targets_effect for e in merged.edges] == [1]


def _game(*nodes: GameNode) -> GameData:
    return GameData(buildid="1", nodes=list(nodes))


def test_game_name_overlays_derived_and_curated_overlays_game():
    game = _game(
        GameNode(id="relic-38", name="Smart Man", description="Adds base to RN2"),
        GameNode(id="relic-39", name="Windmill Pendant", description="Boosts wind"),
    )
    curated = Dataset(
        nodes=[
            Node(
                id="relic-39",
                name="Curated Pendant",
                system="relics",
                kind=Kind.RELIC,
                description="Curated text",
            )
        ]
    )
    merged, problems = merge(_derived(), curated, game=game)

    by_id = {n.id: n for n in merged.nodes}
    assert problems == []
    # derived < game: the game's name and description land, and every field the
    # game does not carry is still the derived one.
    assert by_id["relic-38"].name == "Smart Man"
    assert by_id["relic-38"].description == "Adds base to RN2"
    assert by_id["relic-38"].effects[0].per_level == "+1.00"
    assert by_id["relic-38"].wiki == "Relics"
    # game < curated, field by field.
    assert by_id["relic-39"].name == "Curated Pendant"
    assert by_id["relic-39"].description == "Curated text"
    assert by_id["relic-39"].wiki == "Relics"


def test_game_entity_with_no_node_is_created_between_derived_and_curated():
    game = _game(
        GameNode(id="relic-76", name="New Relic", system="relics", kind=Kind.RELIC)
    )
    curated = Dataset(
        nodes=[Node(id="singularity", name="Singularity", system="unity", kind=Kind.CURRENCY)]
    )
    merged, problems = merge(_derived(), curated, game=game)

    assert problems == []
    assert [n.id for n in merged.nodes] == ["relic-38", "relic-39", "relic-76", "singularity"]
    added = merged.nodes[2]
    assert added.name == "New Relic"
    assert added.system == "relics"
    assert added.kind is Kind.RELIC
    assert added.confidence is NodeConfidence.DOCUMENTED
    assert added.line is None


def test_game_entry_for_a_curated_only_node_sits_under_it():
    game = _game(GameNode(id="lab", name="Laboratory (game)", description="Makes LP"))
    curated = Dataset(
        nodes=[
            Node(id="first", name="First", system="unity", kind=Kind.STAT),
            Node(id="lab", name="Lab", system="unity", kind=Kind.GROUP, line=9),
        ]
    )
    merged, _ = merge(_derived(), curated, game=game)

    # Keeps its place in the curated order, takes the game's description, and
    # the curated name still wins.
    assert [n.id for n in merged.nodes][-2:] == ["first", "lab"]
    lab = merged.nodes[-1]
    assert (lab.name, lab.description, lab.line) == ("Lab", "Makes LP", 9)


def test_game_entry_matching_nothing_is_a_warning_not_a_node():
    game = GameData(nodes=[GameNode(id="relic-99", name="Ghost", line=4)])
    merged, problems = merge(_derived(), Dataset(), game=game, game_path="data/game.yaml")

    assert "relic-99" not in merged.node_ids()
    assert [(p.severity, p.path, p.line) for p in problems] == [
        ("warning", "data/game.yaml", 4)
    ]
    assert "relic-99" in problems[0].message


def test_duplicate_game_entry_is_an_error():
    game = _game(
        GameNode(id="relic-38", name="A", line=1),
        GameNode(id="relic-38", name="B", line=2),
    )
    _, problems = merge(_derived(), Dataset(), game=game, game_path="data/game.yaml")
    assert [(p.severity, p.path, p.line) for p in problems] == [
        ("error", "data/game.yaml", 2)
    ]


def test_no_game_file_merges_exactly_as_without_one():
    curated = Dataset(
        nodes=[Node(id="relic-39", name="Windmill Pendant", system="relics", kind=Kind.RELIC)]
    )
    without, _ = merge(_derived(), curated)
    empty, _ = merge(_derived(), curated, game=GameData())
    assert without == empty
