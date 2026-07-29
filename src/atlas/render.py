from typing import Any

from atlas.models import Dataset

GRAPH_SCHEMA_VERSION = 1


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
        "nodes": [_clean(n.model_dump(mode="json", by_alias=True)) for n in ds.nodes],
        "edges": [_clean(e.model_dump(mode="json", by_alias=True)) for e in ds.edges],
    }
    # Appended last so a document without systems is byte-identical to a v1
    # document. `load.ts` ignores unknown keys, so this stays version 1.
    systems = [_clean(s.model_dump(mode="json")) for s in ds.systems]
    if systems:
        doc["systems"] = systems
    return doc
