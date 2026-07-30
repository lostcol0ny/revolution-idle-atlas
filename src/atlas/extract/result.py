from dataclasses import dataclass, field

from atlas.models import Edge, Node


@dataclass(frozen=True)
class DroppedEdge:
    from_id: str
    to_id: str
    reason: str


@dataclass
class ExtractResult:
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    dropped: list[DroppedEdge] = field(default_factory=list)

    def extend(self, other: "ExtractResult") -> None:
        self.nodes.extend(other.nodes)
        self.edges.extend(other.edges)
        self.dropped.extend(other.dropped)


def prune_dangling(
    result: ExtractResult,
    external_ids: frozenset[str] = frozenset(),
) -> ExtractResult:
    """Drop edges whose endpoints no parser produced (and no curated node covers).

    The resolver matches on prose, so it happily produces `relic-99` from a
    typo. Emitting that edge would make `atlas build` fail on an unknown node
    id, turning a wiki typo into a broken build. Dropping it and reporting it
    keeps the failure visible without making it fatal.

    `external_ids` is the set of node ids from the curated dataset. Vocabulary
    edges name stats and currencies that parsers never mint, but those nodes do
    exist — as curated records. An edge to `luck` is valid as long as
    `relationships.yaml` defines that node, and it will be after the merge step.
    """
    known = {node.id for node in result.nodes} | external_ids
    kept: list[Edge] = []
    dropped = list(result.dropped)
    for edge in result.edges:
        missing = [end for end in (edge.from_, edge.to) if end not in known]
        if missing:
            dropped.append(
                DroppedEdge(
                    from_id=edge.from_,
                    to_id=edge.to,
                    reason=f"no extracted node with id {' or '.join(missing)}",
                )
            )
            continue
        kept.append(edge)
    return ExtractResult(nodes=result.nodes, edges=kept, dropped=dropped)
