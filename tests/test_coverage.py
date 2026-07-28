from atlas.coverage import analyse, load_inventory, render_markdown
from atlas.models import Dataset


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
