from atlas.extract.result import DroppedEdge, ExtractResult, prune_dangling
from atlas.models import Edge, Kind, Node, Rel


def node(node_id: str) -> Node:
    return Node(id=node_id, name=node_id, system="relics", kind=Kind.RELIC)


def edge(from_id: str, to_id: str) -> Edge:
    return Edge(from_=from_id, to=to_id, rel=Rel.BOOSTS, source="test")


def test_extend_merges_nodes_edges_and_dropped():
    first = ExtractResult(
        nodes=[node("relic-1")],
        edges=[edge("relic-1", "relic-2")],
        dropped=[DroppedEdge("relic-1", "relic-9", "earlier drop")],
    )
    second = ExtractResult(
        nodes=[node("relic-2")],
        edges=[edge("relic-2", "relic-1")],
        dropped=[DroppedEdge("relic-2", "relic-8", "later drop")],
    )

    first.extend(second)

    assert [n.id for n in first.nodes] == ["relic-1", "relic-2"]
    assert [(e.from_, e.to) for e in first.edges] == [
        ("relic-1", "relic-2"),
        ("relic-2", "relic-1"),
    ]
    assert [d.reason for d in first.dropped] == ["earlier drop", "later drop"]
    # extend mutates the receiver only; the donor must be left alone so a
    # parser's own result stays valid after it is merged into an accumulator.
    assert [n.id for n in second.nodes] == ["relic-2"]
    assert len(second.edges) == 1
    assert len(second.dropped) == 1


def test_prune_dangling_drops_unknown_endpoints_but_never_drops_a_node():
    # relic-3 is deliberately isolated: its only edge points at an unknown id
    # and is pruned, leaving it with no surviving edge at all. That is the node
    # a "tidy up orphans too" implementation would quietly delete, so it has to
    # be in the fixture for the node assertion below to mean anything.
    result = ExtractResult(
        nodes=[node("relic-1"), node("relic-2"), node("relic-3")],
        edges=[
            edge("relic-1", "relic-2"),
            edge("relic-1", "relic-99"),
            edge("relic-98", "relic-2"),
            edge("relic-3", "relic-97"),
        ],
    )

    pruned = prune_dangling(result)

    assert [(e.from_, e.to) for e in pruned.edges] == [("relic-1", "relic-2")]
    # The point of the function is to prune edges. Nodes are the record of what
    # the wiki actually documents, so losing one here would silently shrink the
    # graph rather than just disconnect it.
    assert [n.id for n in pruned.nodes] == ["relic-1", "relic-2", "relic-3"]
    assert len(pruned.nodes) == len(result.nodes)

    # Every loss must be diagnosable from the record alone: both endpoints and
    # a reason naming the id that was missing.
    assert len(pruned.dropped) == 3
    outbound, inbound, isolated = pruned.dropped
    assert (outbound.from_id, outbound.to_id) == ("relic-1", "relic-99")
    assert "relic-99" in outbound.reason
    assert (inbound.from_id, inbound.to_id) == ("relic-98", "relic-2")
    assert "relic-98" in inbound.reason
    assert (isolated.from_id, isolated.to_id) == ("relic-3", "relic-97")
    assert "relic-97" in isolated.reason


def test_prune_dangling_preserves_dropped_entries_already_on_the_input():
    earlier = DroppedEdge("relic-1", "relic-77", "suppressed by curation")
    result = ExtractResult(
        nodes=[node("relic-1")],
        edges=[edge("relic-1", "relic-99")],
        dropped=[earlier],
    )

    pruned = prune_dangling(result)

    # Appended to, not replaced — a parser that already recorded a drop must
    # not have that record erased by a later pruning pass.
    assert pruned.dropped[0] == earlier
    assert len(pruned.dropped) == 2
    assert pruned.dropped[1].to_id == "relic-99"
    # The input is not mutated; pruning returns a new result.
    assert result.dropped == [earlier]
    assert len(result.edges) == 1


def test_prune_dangling_keeps_every_edge_when_all_endpoints_are_known():
    result = ExtractResult(
        nodes=[node("relic-1"), node("relic-2")],
        edges=[edge("relic-1", "relic-2"), edge("relic-2", "relic-1")],
    )

    pruned = prune_dangling(result)

    assert len(pruned.edges) == 2
    assert pruned.dropped == []
