from atlas.coverage import analyse, load_inventory, render_markdown
from atlas.models import Dataset, Edge, Node


def _node(node_id: str, system: str = "unity", confidence: str = "documented") -> Node:
    return Node(id=node_id, name=node_id, system=system, kind="relic",
                confidence=confidence)


def _edge(src: str, dst: str) -> Edge:
    return Edge(**{"from": src, "to": dst, "rel": "boosts", "source": "observed"})


def test_orphans_are_nodes_with_no_edges():
    ds = Dataset(
        nodes=[_node("a"), _node("b"), _node("lonely")],
        edges=[_edge("a", "b")],
    )
    assert analyse(ds).orphans == ["lonely"]


def test_orphan_detection_counts_incoming_edges():
    ds = Dataset(nodes=[_node("a"), _node("b")], edges=[_edge("a", "b")])
    assert analyse(ds).orphans == []


def test_feedback_loop_is_reported_as_a_cycle():
    ds = Dataset(
        nodes=[_node("gold"), _node("upgrade")],
        edges=[_edge("gold", "upgrade"), _edge("upgrade", "gold")],
    )
    cycles = analyse(ds).cycles
    assert len(cycles) == 1
    assert sorted(cycles[0]) == ["gold", "upgrade"]


def test_acyclic_graph_reports_no_cycles():
    ds = Dataset(nodes=[_node("a"), _node("b")], edges=[_edge("a", "b")])
    assert analyse(ds).cycles == []


def test_per_system_counts_connected_and_total():
    ds = Dataset(
        nodes=[_node("a", "unity"), _node("b", "unity"), _node("c", "tarot")],
        edges=[_edge("a", "b")],
    )
    per_system = analyse(ds).per_system
    assert per_system["unity"] == (2, 2)
    assert per_system["tarot"] == (0, 1)


def test_stub_count_counts_unknown_confidence():
    ds = Dataset(
        nodes=[_node("a"), _node("b", confidence="unknown")],
        edges=[],
    )
    assert analyse(ds).stub_count == 1


def test_markdown_mentions_orphans_and_cycles():
    ds = Dataset(
        nodes=[_node("gold"), _node("upgrade"), _node("lonely")],
        edges=[_edge("gold", "upgrade"), _edge("upgrade", "gold")],
    )
    md = render_markdown(analyse(ds))
    assert "lonely" in md
    assert "Feedback loops" in md
    assert "Orphan nodes" in md


def test_inventory_entities_absent_from_yaml_are_reported():
    ds = Dataset(nodes=[_node("relic-1", "unity")], edges=[])
    inventory = {"unity": ["relic-1", "relic-2"], "tarot": ["the-fool"]}
    missing = analyse(ds, inventory=inventory).missing_entities
    assert missing == {"unity": ["relic-2"], "tarot": ["the-fool"]}


def test_fully_covered_system_is_absent_from_missing_entities():
    ds = Dataset(nodes=[_node("relic-1", "unity")], edges=[])
    inventory = {"unity": ["relic-1"]}
    assert analyse(ds, inventory=inventory).missing_entities == {}


def test_missing_entities_empty_without_inventory():
    ds = Dataset(nodes=[_node("relic-1", "unity")], edges=[])
    assert analyse(ds).missing_entities == {}


def test_markdown_omits_known_unknowns_section_without_inventory():
    md = render_markdown(analyse(Dataset(nodes=[_node("a")], edges=[])))
    assert "Known unknowns" not in md


def test_markdown_lists_known_unknowns_when_inventory_given():
    ds = Dataset(nodes=[_node("relic-1", "unity")], edges=[])
    md = render_markdown(analyse(ds, inventory={"unity": ["relic-1", "relic-2"]}))
    assert "Known unknowns" in md
    assert "relic-2" in md


def test_load_inventory_returns_none_when_file_absent(tmp_path):
    assert load_inventory(tmp_path / "nope.yaml") is None


def test_load_inventory_reads_system_to_ids_mapping(tmp_path):
    path = tmp_path / "inventory.yaml"
    path.write_text("unity:\n  - relic-1\n  - relic-2\n")
    assert load_inventory(path) == {"unity": ["relic-1", "relic-2"]}
