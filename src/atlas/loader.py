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


def _strip_nested_lines(value: Any) -> None:
    """Remove line markers from mappings below a section item.

    Only section items get a line number; anything deeper would collide with
    the models' `extra="forbid"`. The recursion is over parsed YAML, so the
    only container types it can meet are dict and list.
    """
    if isinstance(value, dict):
        value.pop(LINE_KEY, None)
        for nested in value.values():
            _strip_nested_lines(nested)
    elif isinstance(value, list):
        for nested in value:
            _strip_nested_lines(nested)


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
    if not isinstance(raw, dict):
        raise SchemaError(
            ["top level must be a mapping with 'nodes' and 'edges' keys"]
        )
    raw.pop(LINE_KEY, None)

    sections = ("systems", "nodes", "edges", "suppress")
    lines: dict[str, list[int | None]] = {}
    for section in sections:
        items = raw.get(section) or []
        section_lines: list[int | None] = []
        for item in items:
            if isinstance(item, dict):
                section_lines.append(item.pop(LINE_KEY, None))
                for value in item.values():
                    _strip_nested_lines(value)
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

    for section in sections:
        for item, line in zip(getattr(dataset, section), lines[section], strict=True):
            item.line = line

    return dataset
