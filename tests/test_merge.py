from atlas.merge import merge
from atlas.models import (
    Dataset,
    Edge,
    Effect,
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
