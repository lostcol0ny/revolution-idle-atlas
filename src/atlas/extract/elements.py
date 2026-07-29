import re
from pathlib import Path

from atlas.extract.refs import plain_text, resolve
from atlas.extract.result import ExtractResult
from atlas.models import Edge, EdgeConfidence, Effect, Node

PAGE = "Elements"
SOURCE = "wiki:Elements"
SYSTEM = "elements"
ELEMENTS = ("Fire", "Earth", "Wind", "Water")
NO_UNLOCK = "none"

_ROW_SPLIT_RE = re.compile(r"\n\|-\s*\n?")
_FACTOR_RE = re.compile(r"^!\s*Factor\s+(\d+)\s*$", re.MULTILINE)
_ELEMENT_HEADER_RE = re.compile(r"^!\s*rowspan=.*?\|\s*(\w+)\s*$", re.MULTILINE)


def _section(raw: str, heading: str, until: str | None) -> str:
    start = raw.find(heading)
    if start == -1:
        return ""
    end = raw.find(until, start + len(heading)) if until else -1
    return raw[start:] if end == -1 else raw[start:end]


def _table(section: str, after: int = 0) -> str:
    start = section.find("{|", after)
    end = section.find("|}", start)
    return section[start:end] if start != -1 and end != -1 else ""


def _node(node_id: str, name: str, kind: str, text: str) -> Node:
    return Node(
        id=node_id,
        name=name,
        system=SYSTEM,
        kind=kind,
        wiki=PAGE,
        effects=[Effect(text=text)] if text else [],
    )


def _boosts(source_id: str, text: str) -> list[Edge]:
    edges: list[Edge] = []
    for reference in resolve(text):
        if reference.target_id == source_id:
            continue
        edges.append(
            Edge(
                **{
                    "from": source_id,
                    "to": reference.target_id,
                    "rel": "boosts",
                    "note": text,
                    "targets_effect": reference.targets_effect,
                    "source": SOURCE,
                    "confidence": EdgeConfidence.PROVISIONAL,
                }
            )
        )
    return edges


def _parse_factors(raw: str) -> ExtractResult:
    result = ExtractResult()
    table = _table(_section(raw, "=== Element Factors ===", "=== Element Upgrades ==="))
    element = ""
    for row in _ROW_SPLIT_RE.split(table):
        header = _ELEMENT_HEADER_RE.search(row)
        if header is not None:
            element = header.group(1)
        factor = _FACTOR_RE.search(row)
        if factor is None or not element:
            continue
        # Data cells follow the two "!" header cells: description, then unlock.
        cells = [line[1:].strip() for line in row.splitlines() if line.startswith("|")]
        if len(cells) < 2:
            continue
        description, unlock = plain_text(cells[0]), plain_text(cells[1])

        node_id = f"{element.lower()}-factor-{int(factor.group(1))}"
        result.nodes.append(
            _node(node_id, f"{element} Factor {factor.group(1)}", "stat", description)
        )

        if unlock.strip().lower() == NO_UNLOCK:
            continue
        for reference in resolve(unlock):
            result.edges.append(
                Edge(
                    **{
                        "from": reference.target_id,
                        "to": node_id,
                        "rel": "unlocks",
                        "note": unlock,
                        "source": SOURCE,
                        "confidence": EdgeConfidence.DOCUMENTED,
                    }
                )
            )
    return result


def _parse_upgrades(raw: str) -> ExtractResult:
    result = ExtractResult()
    upgrades = _section(raw, "=== Element Upgrades ===", None)
    for index, element in enumerate(ELEMENTS):
        heading = f"==== {element} ===="
        following = ELEMENTS[index + 1] if index + 1 < len(ELEMENTS) else None
        block = _section(upgrades, heading, f"==== {following} ====" if following else None)
        for row in _ROW_SPLIT_RE.split(_table(block)):
            cells = [line[1:].strip() for line in row.splitlines() if line.startswith("|")]
            # The table opener's "|+" caption row survives the split as a stray
            # single cell; a real row is number, price, effect.
            if len(cells) < 3 or not cells[0].isdigit():
                continue
            number, _price, effect = cells[0], cells[1], "\n".join(cells[2:])
            node_id = f"{element.lower()}-node-{int(number)}"
            text = plain_text(effect)
            result.nodes.append(
                _node(node_id, f"{element} Node {int(number)}", "upgrade", text)
            )
            result.edges.extend(_boosts(node_id, text))
    return result


def parse(raw: str) -> ExtractResult:
    result = _parse_factors(raw)
    result.extend(_parse_upgrades(raw))
    return result


def extract(raw_dir: Path) -> ExtractResult:
    return parse((raw_dir / "Elements.wikitext").read_text(encoding="utf-8"))
