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


def _duplicate_node_problems(nodes: list[Node], path: str | None) -> list[Problem]:
    """Report a node id that repeats within a single input file.

    `path` names the file being scanned and is carried on each Problem. These
    are the only problems raised while the two inputs are still separable: once
    the merge finishes, a derived record is indistinguishable from a curated
    one, and its line number points into a file the reporter cannot name.

    `validate_dataset` has this same check, but `_build` merges before it
    validates and `merge` collapses nodes into a dict keyed by id — so by the
    time `validate_dataset` runs the duplicate is already gone and one of the
    two records has been silently discarded. Merging ahead of validation is
    what makes this check `merge`'s job rather than a redundant copy of one.

    This is also why `merge` reports errors at all and not only warnings.
    Everything else it has to say is advisory, so an advisory-only channel looks
    sufficient right up until it silently downgrades a check that was already
    fatal.

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
                    path=path,
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


def merge(
    derived: Dataset,
    curated: Dataset,
    derived_path: str | None = None,
    curated_path: str | None = None,
) -> tuple[Dataset, list[Problem]]:
    """Combine the generated dataset with the curated one. Curated wins.

    `derived` is rewritten in full by every `atlas extract` run, so nothing in
    it is durable; `curated` survives, which is why it holds the last word on
    every field, and why `suppress` exists to delete generated edges outright.

    `derived_path` and `curated_path` name the files the two datasets were read
    from. They are only used to label problems, so they are optional — a caller
    that omits them gets problems with no path and leaves the choice to whoever
    renders them.

    Returns the merged dataset and any problems the merge itself found: a node
    id repeated within one file (error), and a suppression that matched no edge
    (warning).
    """
    # Collected before the dicts below collapse each id to one record, which is
    # also the last moment at which the two inputs can still be told apart.
    problems = _duplicate_node_problems(
        derived.nodes, derived_path
    ) + _duplicate_node_problems(curated.nodes, curated_path)

    nodes: dict[str, Node] = {}
    for node in derived.nodes:
        nodes[node.id] = node.model_copy(update={"line": None})
    for node in curated.nodes:
        existing = nodes.get(node.id)
        nodes[node.id] = _overlay(existing, node) if existing is not None else node

    edges: dict[EdgeKey, Edge] = {}
    for edge in derived.edges:
        key = _edge_key(edge)
        if key in edges:
            # Two generated edges share (from, to, rel) but differ in payload
            # (e.g. targets_effect or note). The emit layer preserves both, but
            # a dict keyed on (from, to, rel) can only keep one — report rather
            # than silently discarding evidence.
            problems.append(Problem(
                severity="warning",
                message=(
                    f"generated edge '{edge.from_}' -> '{edge.to}' ({edge.rel}) "
                    f"collides with an earlier one on (from, to, rel); the "
                    f"earlier one was discarded"
                ),
                path=derived_path,
            ))
        edges[key] = edge.model_copy(update={"line": None})
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
