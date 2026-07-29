from atlas.models import Dataset, Edge, Node, Suppression
from atlas.problems import Problem

EdgeKey = tuple[str, str, str]


def _edge_key(edge: Edge | Suppression) -> EdgeKey:
    # Suppression carries the same three fields, deliberately, so one function
    # keys both and a suppression rule cannot drift from the edges it removes.
    #
    # str() is not redundant despite Rel being a StrEnum: it normalises the enum
    # member to a plain str so the key's runtime type matches EdgeKey. A member
    # hashes identically, so this changes no behaviour — it keeps the dict's
    # keys one uniform type when they are printed or inspected.
    return (edge.from_, edge.to, str(edge.rel))


def _duplicate_node_problems(nodes: list[Node]) -> list[Problem]:
    """Report a node id that repeats within a single input file.

    `validate_dataset` has this same check, but `_build` merges before it
    validates and `merge` collapses nodes into a dict keyed by id — so by the
    time `validate_dataset` runs the duplicate is already gone and one of the
    two records has been silently discarded. Merging ahead of validation is
    what makes this check `merge`'s job rather than a redundant copy of one.

    This is why `merge` reports errors and not only warnings: the brief scoped
    it to warnings because it did not anticipate that merging first would
    swallow an existing error check.

    Scoped to node ids deliberately. A repeated `(from, to, rel)` across the
    two files is the intended override mechanism, not an error, and
    `validate_dataset` never checked for duplicate edges in the first place.
    """
    problems: list[Problem] = []
    seen: set[str] = set()
    for node in nodes:
        if node.id in seen:
            problems.append(
                Problem(
                    severity="error",
                    message=f"duplicate node id '{node.id}'",
                    line=node.line,
                )
            )
        seen.add(node.id)
    return problems


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

    Returns the merged dataset and any problems the merge itself found: a node
    id repeated within one file (error), and a suppression that matched no edge
    (warning).
    """
    # Collected before the dicts below collapse each id to one record.
    problems = _duplicate_node_problems(derived.nodes) + _duplicate_node_problems(
        curated.nodes
    )

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

    problems += [
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
