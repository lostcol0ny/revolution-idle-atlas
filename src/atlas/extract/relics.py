import re
from pathlib import Path

from atlas.extract.refs import Vocabulary, derive_op, is_uncertain, plain_text, resolve
from atlas.extract.result import ExtractResult
from atlas.models import Edge, EdgeConfidence, Effect, Node

PAGE = "Relics"
SOURCE = "wiki:Relics"
SYSTEM = "relics"
EXPECTED_COLUMNS = 6

_ROW_SPLIT_RE = re.compile(r"\n\|-\s*\n")


def _table(raw: str) -> str:
    start = raw.find("{|")
    end = raw.find("|}", start)
    return raw[start:end] if start != -1 and end != -1 else ""


def _cells(row: str) -> list[str]:
    # Cells are separated by a newline-then-pipe, not a bare pipe: relic names
    # wrap across two lines and [[File:...|128px|link=]] contains pipes of its
    # own, and both must stay inside one cell.
    cells = [cell.strip() for cell in row.split("\n|")]
    cells[0] = cells[0].lstrip("|").strip()
    return cells


def parse(raw: str, vocabulary: Vocabulary = Vocabulary.EMPTY) -> ExtractResult:
    result = ExtractResult()
    # [0] is the table opener, [1] the column headers; the rest are relics.
    for row in _ROW_SPLIT_RE.split(_table(raw))[2:]:
        cells = _cells(row)
        if len(cells) != EXPECTED_COLUMNS:
            continue
        number, name, _icon, effect, per_level, _unlock = cells
        if not number.isdigit():
            continue

        node_id = f"relic-{int(number)}"
        text = plain_text(effect)
        coefficient = plain_text(per_level) or None
        op = derive_op(coefficient)

        result.nodes.append(
            Node(
                id=node_id,
                name=plain_text(name),
                system=SYSTEM,
                kind="relic",
                wiki=PAGE,
                effects=[Effect(text=text, per_level=coefficient, op=op)],
            )
        )

        confidence = (
            EdgeConfidence.UNCERTAIN
            if is_uncertain(coefficient)
            else EdgeConfidence.PROVISIONAL
        )
        for reference in resolve(text, vocabulary):
            if reference.target_id == node_id:
                continue
            result.edges.append(
                Edge(
                    **{
                        "from": node_id,
                        "to": reference.target_id,
                        "rel": "boosts",
                        "op": op,
                        "note": text,
                        "targets_effect": reference.targets_effect,
                        "source": SOURCE,
                        # The hedge reading is only the floor for a structural
                        # match; a vocabulary hit is uncertain either way.
                        "confidence": reference.confidence(confidence),
                    }
                )
            )
    return result


def extract(raw_dir: Path, vocabulary: Vocabulary = Vocabulary.EMPTY) -> ExtractResult:
    return parse((raw_dir / "Relics.wikitext").read_text(encoding="utf-8"), vocabulary)
