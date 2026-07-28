from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from atlas.models import Dataset

LINE_KEY = "__line__"


class SchemaError(Exception):
    """Raised when relationships.yaml does not match the schema."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("\n".join(problems))


# Subclasses SafeLoader, so it inherits SafeLoader's constructor whitelist and
# cannot instantiate arbitrary Python types. The only override is the plain
# mapping constructor, which attaches a source line number for error messages.
class _LineLoader(yaml.SafeLoader):
    """SafeLoader that records the source line of every mapping."""


def _construct_mapping(loader: _LineLoader, node: yaml.MappingNode) -> dict[str, Any]:
    loader.flatten_mapping(node)
    mapping = dict(loader.construct_pairs(node, deep=True))
    mapping[LINE_KEY] = node.start_mark.line + 1
    return mapping


_LineLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
)


def load_dataset(path: Path) -> Dataset:
    # Equivalent to yaml.load(..., Loader=_LineLoader), spelled out so the
    # SafeLoader lineage is the only thing a reader has to verify.
    loader = _LineLoader(path.read_text(encoding="utf-8"))
    try:
        raw = loader.get_single_data()
    finally:
        loader.dispose()
    if raw is None:
        raw = {}
    raw.pop(LINE_KEY, None)

    lines: dict[str, list[int | None]] = {}
    for section in ("nodes", "edges"):
        items = raw.get(section) or []
        section_lines: list[int | None] = []
        for item in items:
            if isinstance(item, dict):
                section_lines.append(item.pop(LINE_KEY, None))
            else:
                section_lines.append(None)
        lines[section] = section_lines

    try:
        dataset = Dataset.model_validate(raw)
    except ValidationError as exc:
        problems = [
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}"
            for err in exc.errors()
        ]
        raise SchemaError(problems) from exc

    for node, line in zip(dataset.nodes, lines["nodes"], strict=True):
        node.line = line
    for edge, line in zip(dataset.edges, lines["edges"], strict=True):
        edge.line = line

    return dataset
