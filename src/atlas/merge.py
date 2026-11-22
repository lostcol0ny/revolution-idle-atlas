from collections.abc import Sequence
from typing import Any

from atlas.models import Dataset, Edge, Effect, GameData, GameNode, Node, Suppression
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


def _duplicate_node_problems(
    nodes: Sequence[Node | GameNode], path: str | None
) -> list[Problem]:
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


def _reworded_effect(derived: Sequence[Effect], curated: Sequence[Effect]) -> dict[str, str]:
    """The one effect a curated list rewords, as {derived text: curated text}.

    Only an unambiguous rewording counts: both lists the same length, exactly
    one position whose text differs, and the derived text gone from the
    curated list. A list that adds, drops or reorders effects pairs nothing,
    because position no longer says which curated effect a derived one became.
    """
    if len(derived) != len(curated):
        return {}
    changed = [(old.text, new.text) for old, new in zip(derived, curated) if old.text != new.text]
    if len(changed) != 1:
        return {}
    old, new = changed[0]
    if any(effect.text == old for effect in curated):
        return {}
    return {old: new}


def _game_layer(
    game: GameData,
    fields: dict[str, dict[str, Any]],
    curated_ids: set[str],
    game_path: str | None,
) -> tuple[dict[str, dict[str, Any]], list[Problem]]:
    """Overlay the game's names, descriptions and effects onto `fields` in place.

    A game entity no generated node has is created here when the entry names
    its system and kind. One that only a curated node has is returned instead,
    to be applied under that node, so a curated-only node keeps its place in
    the curated file's order.
    """
    under_curated: dict[str, dict[str, Any]] = {}
    problems: list[Problem] = []
    for entry in game.nodes:
        data = fields.get(entry.id)
        if data is None and entry.system is not None and entry.kind is not None:
            data = fields[entry.id] = {
                "id": entry.id,
                "system": entry.system,
                "kind": entry.kind,
            }
        elif data is None and entry.id in curated_ids:
            data = under_curated[entry.id] = {}
        elif data is None:
            problems.append(Problem(
                severity="warning",
                message=(
                    f"game entry '{entry.id}' matches no node and names no "
                    f"system and kind to create one — rerun `atlas game`"
                ),
                line=entry.line,
                path=game_path,
            ))
            continue
        if entry.name is not None:
            data["name"] = entry.name
        if entry.description is not None:
            data["description"] = entry.description
        if entry.effects:
            data["effects"] = [{"text": text} for text in entry.effects]
    return under_curated, problems


def merge(
    derived: Dataset,
    curated: Dataset,
    derived_path: str | None = None,
    curated_path: str | None = None,
    game: GameData | None = None,
    game_path: str | None = None,
) -> tuple[Dataset, list[Problem]]:
    """Combine the generated dataset, the game's facts and the curated dataset.

    Precedence is derived < game < curated. `derived` is rewritten in full by
    every `atlas extract` run, so nothing in it is durable; `curated` survives,
    which is why it holds the last word on every field, and why `suppress`
    exists to delete generated edges outright. `game` sits between: it is the
    game's own text, so it corrects a wiki name, but a curator still wins.
    It carries nodes only, never edges.

    Nodes merge field by field. Pydantic defaults are indistinguishable from
    explicit values on the model itself, so a curated node contributes only
    its `model_fields_set` — the only way to tell "the curated file said
    confidence: documented" from "the curated file said nothing". Without it
    every curated node would silently reset the derived node's confidence and
    wiki page to their defaults.

    `derived_path`, `curated_path` and `game_path` name the files the inputs
    were read from. They are only used to label problems, so they are optional
    — a caller that omits them gets problems with no path and leaves the choice
    to whoever renders them.

    Returns the merged dataset and any problems the merge itself found: a node
    id repeated within one file (error), a suppression that matched no edge
    (warning), and a game entry that matched no node (warning).
    """
    # Collected before the dicts below collapse each id to one record, which is
    # also the last moment at which the inputs can still be told apart.
    problems = (
        _duplicate_node_problems(derived.nodes, derived_path)
        + _duplicate_node_problems(curated.nodes, curated_path)
        + _duplicate_node_problems(game.nodes if game else [], game_path)
    )

    # model_dump drops `line`, so a generated record never keeps a line number.
    fields = {node.id: node.model_dump() for node in derived.nodes}
    under_curated: dict[str, dict[str, Any]] = {}
    if game is not None:
        under_curated, game_problems = _game_layer(
            game, fields, curated.node_ids(), game_path
        )
        problems += game_problems
    derived_effects = {node.id: node.effects for node in derived.nodes}
    reworded: dict[str, dict[str, str]] = {}
    for node in curated.nodes:
        data = fields.setdefault(node.id, under_curated.pop(node.id, {}))
        data.update({name: getattr(node, name) for name in node.model_fields_set})
        if "effects" in node.model_fields_set:
            reworded[node.id] = _reworded_effect(
                derived_effects.get(node.id, []), node.effects
            )
    nodes = [Node.model_validate(data) for data in fields.values()]

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
        # A parser copies the effect an edge was read from into its `note`, so
        # a curated rewording of that effect reaches the copy too; otherwise a
        # node card shows one effect in two wordings.
        update: dict[str, Any] = {"line": None}
        for end in (edge.from_, edge.to):
            if edge.note in reworded.get(end, {}):
                update["note"] = reworded[end][edge.note]
        edges[key] = edge.model_copy(update=update)
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
        nodes=nodes,
        edges=[e for key, e in edges.items() if key not in suppressed],
    )
    return dataset, problems
