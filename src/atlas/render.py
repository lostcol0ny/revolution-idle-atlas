from typing import Any

from atlas.models import Dataset

GRAPH_SCHEMA_VERSION = 1


def _clean(payload: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in sorted(payload.items()) if v is not None}


def to_graph(ds: Dataset) -> dict[str, Any]:
    return {
        "version": GRAPH_SCHEMA_VERSION,
        # by_alias on both models even though Node has no aliases today: the two
        # sides of the output contract should not serialise by different rules.
        "nodes": [_clean(n.model_dump(mode="json", by_alias=True)) for n in ds.nodes],
        "edges": [_clean(e.model_dump(mode="json", by_alias=True)) for e in ds.edges],
    }
