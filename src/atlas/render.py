import re
from typing import Any

from atlas.models import Dataset, Kind, Node

GRAPH_SCHEMA_VERSION = 1

_RELIC_ID_RE = re.compile(r"^relic-(\d+)$")


def _relic_label(node: Node) -> str:
    """Compose "Relic 18 (Mythical Rune)" — players still refer to relics by number.

    Applied to the merged dataset rather than in the parser: a name can arrive
    from either dataset file, so composing at extraction time would be bypassed
    by any curated `name` override.

    Keyed on kind AND the `relic-<n>` id shape, so a stat named "Relic 4
    Booster" and a group node like `relics-tier-3` both pass through untouched.
    """
    match = _RELIC_ID_RE.match(node.id)
    if node.kind is not Kind.RELIC or match is None:
        return node.name
    bare = f"Relic {int(match.group(1))}"
    name = node.name.strip()
    # Without this guard a stale placeholder named "Relic 3" renders as
    # "Relic 3 (Relic 3)". Degrading to the bare label keeps that
    # unrepresentable regardless of which file supplied the name.
    if not name or name == bare:
        return bare
    return f"{bare} ({name})"


def _clean(payload: dict[str, Any]) -> dict[str, Any]:
    # Empty lists are dropped alongside None. Without this, adding an optional
    # list field to a model would rewrite every node in graph.json with a
    # `"field": []` line and fail CI's artifact diff — an absent optional field
    # and an empty one carry the same meaning, so only one form should ship.
    return {
        k: v
        for k, v in sorted(payload.items())
        if v is not None and v != []
    }


def to_graph(ds: Dataset) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "version": GRAPH_SCHEMA_VERSION,
        # model_copy rather than mutating: the CLI hands the same Dataset to
        # coverage analysis, which must not see a different name than it did
        # before render ran.
        "nodes": [
            _clean(
                n.model_copy(update={"name": _relic_label(n)}).model_dump(
                    mode="json", by_alias=True, exclude_none=True
                )
            )
            for n in ds.nodes
        ],
        "edges": [_clean(e.model_dump(mode="json", by_alias=True, exclude_none=True)) for e in ds.edges],
    }
    # Appended last so a document without systems is byte-identical to a v1
    # document. `load.ts` ignores unknown keys, so this stays version 1.
    systems = [_clean(s.model_dump(mode="json")) for s in ds.systems]
    if systems:
        doc["systems"] = systems
    return doc
