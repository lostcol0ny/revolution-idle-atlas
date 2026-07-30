from atlas.coverage import SystemRollup, analyse, load_inventory, render_markdown
from atlas.models import Dataset, Edge, Effect, Kind, Node, Rel, SystemDef


def test_orphans_are_nodes_with_no_edges(node, edge):
    ds = Dataset(
        nodes=[node("a"), node("b"), node("lonely")],
        edges=[edge("a", "b")],
    )
    assert analyse(ds).orphans == ["lonely"]


def test_orphan_detection_counts_incoming_edges(node, edge):
    ds = Dataset(nodes=[node("a"), node("b")], edges=[edge("a", "b")])
    assert analyse(ds).orphans == []


def test_feedback_loop_is_reported_as_a_cycle(node, edge):
    ds = Dataset(
        nodes=[node("gold"), node("upgrade")],
        edges=[edge("gold", "upgrade"), edge("upgrade", "gold")],
    )
    cycles = analyse(ds).cycles
    assert len(cycles) == 1
    assert sorted(cycles[0]) == ["gold", "upgrade"]


def test_acyclic_graph_reports_no_cycles(node, edge):
    ds = Dataset(nodes=[node("a"), node("b")], edges=[edge("a", "b")])
    assert analyse(ds).cycles == []


def test_cycles_are_ordered_largest_first_then_alphabetically(node, edge):
    # Two independent components: a 2-cycle whose first id sorts before every id
    # in the 3-cycle, so only the size term of the (-len, component[0]) sort key
    # can put the 3-cycle first. Dropping the key would order them the other way.
    ds = Dataset(
        nodes=[node(n) for n in ("aa", "ab", "xa", "xb", "xc")],
        edges=[
            edge("aa", "ab"),
            edge("ab", "aa"),
            edge("xa", "xb"),
            edge("xb", "xc"),
            edge("xc", "xa"),
        ],
    )
    assert analyse(ds).cycles == [["xa", "xb", "xc"], ["aa", "ab"]]


def test_equal_sized_cycles_are_ordered_by_first_member(node, edge):
    ds = Dataset(
        nodes=[node(n) for n in ("m", "n", "b", "c")],
        edges=[edge("m", "n"), edge("n", "m"), edge("b", "c"), edge("c", "b")],
    )
    assert analyse(ds).cycles == [["b", "c"], ["m", "n"]]


def test_per_system_counts_connected_and_total(node, edge):
    ds = Dataset(
        nodes=[node("a", "unity"), node("b", "unity"), node("c", "tarot")],
        edges=[edge("a", "b")],
    )
    per_system = analyse(ds).per_system
    assert per_system["unity"] == (2, 2)
    assert per_system["tarot"] == (0, 1)


def test_stub_count_counts_unknown_confidence(node):
    ds = Dataset(
        nodes=[node("a"), node("b", confidence="unknown")],
        edges=[],
    )
    assert analyse(ds).stub_count == 1


def test_markdown_mentions_orphans_and_cycles(node, edge):
    ds = Dataset(
        nodes=[node("gold"), node("upgrade"), node("lonely")],
        edges=[edge("gold", "upgrade"), edge("upgrade", "gold")],
    )
    md = render_markdown(analyse(ds))
    assert "lonely" in md
    assert "Feedback loops" in md
    assert "Orphan nodes" in md


def test_inventory_entities_absent_from_yaml_are_reported(node):
    ds = Dataset(nodes=[node("relic-1", "unity")], edges=[])
    inventory = {"unity": ["relic-1", "relic-2"], "tarot": ["the-fool"]}
    missing = analyse(ds, inventory=inventory).missing_entities
    assert missing == {"unity": ["relic-2"], "tarot": ["the-fool"]}


def test_fully_covered_system_is_absent_from_missing_entities(node):
    ds = Dataset(nodes=[node("relic-1", "unity")], edges=[])
    inventory = {"unity": ["relic-1"]}
    assert analyse(ds, inventory=inventory).missing_entities == {}


def test_missing_entities_empty_without_inventory(node):
    ds = Dataset(nodes=[node("relic-1", "unity")], edges=[])
    assert analyse(ds).missing_entities == {}


def test_markdown_omits_known_unknowns_section_without_inventory(node):
    md = render_markdown(analyse(Dataset(nodes=[node("a")], edges=[])))
    assert "Known unknowns" not in md


def test_markdown_lists_known_unknowns_when_inventory_given(node):
    ds = Dataset(nodes=[node("relic-1", "unity")], edges=[])
    md = render_markdown(analyse(ds, inventory={"unity": ["relic-1", "relic-2"]}))
    assert "Known unknowns" in md
    assert "relic-2" in md


def test_load_inventory_returns_none_when_file_absent(tmp_path):
    assert load_inventory(tmp_path / "nope.yaml") is None


def test_load_inventory_reads_system_to_ids_mapping(tmp_path):
    path = tmp_path / "inventory.yaml"
    path.write_text("unity:\n  - relic-1\n  - relic-2\n")
    assert load_inventory(path) == {"unity": ["relic-1", "relic-2"]}


def test_load_inventory_treats_an_empty_file_as_absent(tmp_path):
    # `or {}` would make this an empty-but-present inventory, and the report
    # would then claim "every inventoried entity has a node" against no entities.
    path = tmp_path / "inventory.yaml"
    path.write_text("")
    assert load_inventory(path) is None


def test_load_inventory_treats_a_non_mapping_root_as_absent(tmp_path):
    # A list-shaped file used to reach .items() in analyse and raise AttributeError.
    path = tmp_path / "inventory.yaml"
    path.write_text("- relic-1\n- relic-2\n")
    assert load_inventory(path) is None


def test_empty_inventory_file_omits_the_known_unknowns_section(node, tmp_path):
    path = tmp_path / "inventory.yaml"
    path.write_text("")
    md = render_markdown(
        analyse(Dataset(nodes=[node("a")], edges=[]), inventory=load_inventory(path))
    )
    assert "Known unknowns" not in md


def _ds() -> Dataset:
    return Dataset(
        systems=[
            SystemDef(id="unity", name="Unity"),
            SystemDef(id="relics", name="Relics", parent="unity"),
            SystemDef(id="refine-tree", name="Refine Tree", parent="minerals"),
            SystemDef(id="minerals", name="Minerals", parent="unity"),
        ],
        nodes=[
            Node(
                id="relic-38",
                name="Smart Man",
                system="relics",
                kind=Kind.RELIC,
                effects=[Effect(text="Adds base to Refine Node 2")],
            ),
            Node(
                id="relic-39",
                name="Windmill Pendant",
                system="relics",
                kind=Kind.RELIC,
                effects=[Effect(text="Boosts something we could not resolve")],
            ),
            Node(id="refine-node-2", name="Refine Node 2", system="refine-tree", kind=Kind.TREE_NODE),
            # Carries an effect AND an outgoing edge, but that edge is `requires`.
            # This node is the only reason the `rel is not Rel.REQUIRES` filter is
            # testable: without it, dropping the filter changes no expected value.
            Node(
                id="refine-node-3",
                name="Refine Node 3",
                system="refine-tree",
                kind=Kind.TREE_NODE,
                effects=[Effect(text="Multiplies something we could not resolve")],
            ),
            Node(id="singularity", name="Singularity", system="unity", kind=Kind.CURRENCY),
        ],
        edges=[
            Edge(from_="relic-38", to="refine-node-2", rel=Rel.BOOSTS, source="Relics"),
            Edge(from_="refine-node-3", to="refine-node-2", rel=Rel.REQUIRES, source="Refine Tree"),
        ],
    )


def test_unresolved_lists_nodes_whose_effects_produced_no_effect_edge():
    report = analyse(_ds())
    # relic-38's effect became a `boosts` edge, so it resolved. relic-39 states
    # an effect and has no outgoing edge at all. refine-node-3 states an effect
    # and DOES have an outgoing edge, but `requires` is tree structure rather
    # than an effect — so it is still unresolved. That last case is what makes
    # this test able to fail: drop the `requires` filter and refine-node-3
    # disappears from this list.
    assert report.unresolved == ["refine-node-3", "relic-39"]


def test_a_requires_edge_alone_does_not_resolve_an_effect():
    # The same property stated as its own assertion, so a future edit to the
    # list above cannot quietly take the `requires` filter's coverage with it.
    ds = _ds()
    ds.edges = [Edge(from_="relic-39", to="relic-38", rel=Rel.REQUIRES, source="x")]
    assert "relic-39" in analyse(ds).unresolved


def test_rollup_totals_climb_the_parent_chain():
    rollup = {r.id: r for r in analyse(_ds()).rollup}
    assert rollup["relics"].direct == 2
    assert rollup["relics"].total == 2
    assert rollup["minerals"].direct == 0
    assert rollup["minerals"].total == 2
    assert rollup["unity"].direct == 1
    assert rollup["unity"].total == 5


def test_rollup_reports_every_field_in_parent_before_child_order():
    # Compared as whole SystemRollup values rather than field-by-field: this is
    # the only assertion pinning `connected`, and a tuple of (id, depth) leaves
    # the two count columns free to be anything. `connected` climbs the parent
    # chain the same way `total` does, so Minerals shows 2 while owning 0 nodes.
    assert analyse(_ds()).rollup == [
        SystemRollup(id="unity", name="Unity", depth=0, direct=1, total=5, connected=3),
        SystemRollup(id="relics", name="Relics", depth=1, direct=2, total=2, connected=1),
        SystemRollup(id="minerals", name="Minerals", depth=1, direct=0, total=2, connected=2),
        SystemRollup(
            id="refine-tree", name="Refine Tree", depth=2, direct=2, total=2, connected=2
        ),
    ]


def test_rollup_is_empty_when_the_dataset_declares_no_systems():
    ds = _ds()
    ds.systems = []
    assert analyse(ds).rollup == []


def test_a_parent_cycle_is_reported_flat_rather_than_dropped():
    ds = _ds()
    ds.systems = [
        SystemDef(id="a", name="A", parent="b"),
        SystemDef(id="b", name="B", parent="a"),
    ]
    ds.nodes = [Node(id="x", name="X", system="a", kind=Kind.CURRENCY)]
    # validate_dataset rejects a parent cycle before a real build reaches
    # analyse, but analyse is public. Neither system is a child of any root, so
    # both arrive via the unplaced-systems fallback: depth 0, no rollup.
    rollup = {r.id: r for r in analyse(ds).rollup}
    assert set(rollup) == {"a", "b"}
    assert rollup["a"].depth == 0 and rollup["b"].depth == 0
    # The node inside the cycle still counts. Dropping it is the actual failure
    # mode here — a silently-shrinking total is worse than a flat report.
    assert rollup["a"].direct == 1 and rollup["a"].total == 1
    assert rollup["a"].connected == 0  # node "x" has no edges


def test_render_markdown_includes_the_new_sections():
    text = render_markdown(analyse(_ds()))
    assert "## Unresolved effects" in text
    assert "`relic-39`" in text
    assert "## System hierarchy" in text
    assert "- **Unity** — 5 nodes, 3 connected (1 directly)" in text
    assert "  - **Relics** — 2 nodes, 1 connected" in text


def test_render_markdown_omits_the_hierarchy_when_there_is_none():
    ds = _ds()
    ds.systems = []
    assert "## System hierarchy" not in render_markdown(analyse(ds))


def test_page_title_inverts_raw_filename():
    from atlas.coverage import page_title
    from atlas.rawcheck import raw_filename

    # Underscored titles round-trip exactly; a spaced one comes back
    # underscored, which MediaWiki treats as the same page.
    for title in ("Relics", "Minerals/Refine_Tree", "Dilation_Tree"):
        assert page_title(raw_filename(title)) == title
    assert page_title(raw_filename("Dilation Tree")) == "Dilation_Tree"


def test_not_swept_lists_pages_no_node_points_at():
    ds = Dataset(
        systems=[SystemDef(id="relics", name="Relics")],
        nodes=[
            Node(id="a", name="A", system="relics", kind=Kind.RELIC, wiki="Relics"),
        ],
    )
    report = analyse(ds, raw_pages={"Relics": 100, "Achievements": 5000})
    assert report.not_swept == [("Achievements", 5000)]


def test_not_swept_is_largest_first():
    # The section is a work queue, so the ordering is the feature. Sorted by
    # name instead, 38 sub-200-byte redirect stubs sit above Achievements.
    report = analyse(Dataset(), raw_pages={"Small": 20, "Huge": 90000, "Mid": 500})
    assert [name for name, _ in report.not_swept] == ["Huge", "Mid", "Small"]


def test_a_wiki_anchor_still_counts_as_covering_the_page():
    # node.wiki carries "Tarot#Major_Arcana" on some curated nodes. Compared
    # whole, the page reads as unswept while its nodes sit in the graph.
    ds = Dataset(
        systems=[SystemDef(id="tarot", name="Tarot")],
        nodes=[
            Node(
                id="a",
                name="A",
                system="tarot",
                kind=Kind.TAROT_CARD,
                wiki="Tarot#Major_Arcana",
            )
        ],
    )
    assert analyse(ds, raw_pages={"Tarot": 100}).not_swept == []


def test_the_section_is_absent_when_no_raw_pages_are_given():
    # Same contract as `has_inventory`: analyse must stay callable with a
    # dataset alone, which every existing test and tests/fixtures rely on.
    assert analyse(Dataset()).not_swept == []
    assert "Not swept" not in render_markdown(analyse(Dataset()))


def test_the_section_renders_the_pages_it_found():
    report = analyse(Dataset(), raw_pages={"Achievements": 101707})
    rendered = render_markdown(report)
    assert "## Not swept" in rendered
    assert "Achievements" in rendered
    assert "101707" in rendered
