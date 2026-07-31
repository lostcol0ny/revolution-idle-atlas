import difflib
from collections.abc import Iterable

from atlas.models import Dataset
from atlas.problems import Problem


def suggest(unknown: str, known: Iterable[str]) -> str | None:
    matches = difflib.get_close_matches(unknown, list(known), n=1, cutoff=0.6)
    return matches[0] if matches else None


def _unknown_ref(field: str, ref: str, known: Iterable[str], line: int | None) -> Problem:
    message = f"edge {field} references unknown node id '{ref}'"
    hint = suggest(ref, known)
    if hint is not None:
        message += f" — did you mean '{hint}'?"
    return Problem(severity="error", message=message, line=line)


def _check_systems(ds: Dataset) -> list[Problem]:
    problems: list[Problem] = []

    seen: set[str] = set()
    for system in ds.systems:
        if system.id in seen:
            problems.append(
                Problem(
                    severity="error",
                    message=f"duplicate system id '{system.id}'",
                    line=system.line,
                )
            )
        seen.add(system.id)

    for system in ds.systems:
        if system.parent is not None and system.parent not in seen:
            message = f"system '{system.id}' has unknown parent '{system.parent}'"
            hint = suggest(system.parent, seen)
            if hint is not None:
                message += f" — did you mean '{hint}'?"
            problems.append(Problem(severity="error", message=message, line=system.line))

    parents = {s.id: s.parent for s in ds.systems}
    for system in ds.systems:
        walked: set[str] = set()
        current = system.id
        while current is not None and current not in walked:
            walked.add(current)
            current = parents.get(current)
        if current is not None:
            problems.append(
                Problem(
                    severity="error",
                    message=f"system '{system.id}' is in a parent cycle",
                    line=system.line,
                )
            )

    # An empty systems block means the taxonomy is not being declared yet, not
    # that every node's system is wrong. Absent optional input degrades quietly.
    if not seen:
        return problems

    for node in ds.nodes:
        if node.system not in seen:
            message = f"node '{node.id}' has undeclared system '{node.system}'"
            hint = suggest(node.system, seen)
            if hint is not None:
                message += f" — did you mean '{hint}'?"
            problems.append(Problem(severity="error", message=message, line=node.line))

    return problems


def _check_effect_pointers(ds: Dataset) -> list[Problem]:
    effect_counts = {n.id: len(n.effects) for n in ds.nodes}
    problems: list[Problem] = []
    for edge in ds.edges:
        if edge.targets_effect is None:
            continue
        available = effect_counts.get(edge.to)
        if available is None:
            # The unknown-endpoint check already reported this edge.
            continue
        if not 0 <= edge.targets_effect < available:
            problems.append(
                Problem(
                    severity="error",
                    message=(
                        f"edge to '{edge.to}' sets targets_effect "
                        f"{edge.targets_effect} but that node has "
                        f"{available} effect(s)"
                    ),
                    line=edge.line,
                )
            )
    return problems


def validate_dataset(ds: Dataset) -> list[Problem]:
    problems: list[Problem] = []

    seen: set[str] = set()
    for node in ds.nodes:
        if node.id in seen:
            problems.append(
                Problem(
                    severity="error",
                    message=f"duplicate node id '{node.id}'",
                    line=node.line,
                )
            )
        seen.add(node.id)

    known = ds.node_ids()
    for edge in ds.edges:
        if edge.from_ not in known:
            problems.append(_unknown_ref("from", edge.from_, known, edge.line))
        if edge.to not in known:
            problems.append(_unknown_ref("to", edge.to, known, edge.line))
        if edge.from_ == edge.to:
            problems.append(
                Problem(
                    severity="error",
                    message=f"self-edge on '{edge.from_}'",
                    line=edge.line,
                )
            )

    problems.extend(_check_systems(ds))
    problems.extend(_check_effect_pointers(ds))

    return problems
