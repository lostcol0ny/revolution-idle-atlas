from typing import Any

from atlas.models import Dataset, Edge, Node
from atlas.problems import Problem

EdgeKey = tuple[str, str, str]


def _edge_key(edge: Any) -> EdgeKey:
    # Suppression carries the same three fields, deliberately, so one function
    # keys both and a suppression rule cannot drift from the edges it removes.
    return (edge.from_, edge.to, str(edge.rel))


def _overlay(base: Node, override: Node) -> Node:
    """Apply only the fields the override actually set.

    Pydantic defaults are indistinguishable from explicit values on the model
    itself, so `model_fields_set` is the only way to tell "the curated file
    said confidence: documented" from "the curated file said nothing". Without
    it every curated node would silently reset the derived node's confidence
    and wiki page to their defaults.
    """
    data = base.model_dump()
    for field in override.model_fields_set:
        data[field] = getattr(override, field)
    return Node.model_validate(data)


def merge(derived: Dataset, curated: Dataset) -> tuple[Dataset, list[Problem]]:
    """Combine the generated dataset with the curated one. Curated wins.

    `derived` is rewritten in full by every `atlas extract` run, so nothing in
    it is durable; `curated` survives, which is why it holds the last word on
    every field, and why `suppress` exists to delete generated edges outright.

    Returns the merged dataset and any problems the merge itself found. The
    only one it can find is a suppression that matched no edge.
    """
    nodes: dict[str, Node] = {}
    for node in derived.nodes:
        nodes[node.id] = node.model_copy(update={"line": None})
    for node in curated.nodes:
        existing = nodes.get(node.id)
        nodes[node.id] = _overlay(existing, node) if existing is not None else node

    edges: dict[EdgeKey, Edge] = {}
    for edge in derived.edges:
        edges[_edge_key(edge)] = edge.model_copy(update={"line": None})
    for edge in curated.edges:
        edges[_edge_key(edge)] = edge

    suppressed = {_edge_key(rule) for rule in curated.suppress}

    problems = [
        Problem(
            severity="warning",
            message=(
                f"suppress rule '{rule.from_}' -> '{rule.to}' ({rule.rel}) "
                f"matches no edge — extraction may have stopped producing it"
            ),
            line=rule.line,
        )
        for rule in curated.suppress
        if _edge_key(rule) not in edges
    ]

    dataset = Dataset(
        systems=curated.systems,
        nodes=list(nodes.values()),
        edges=[e for key, e in edges.items() if key not in suppressed],
    )
    return dataset, problems
