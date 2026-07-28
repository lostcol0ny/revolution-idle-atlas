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

    return problems
