import re
from pathlib import Path

from atlas.extract.refs import plain_text, resolve, template_fields
from atlas.extract.result import ExtractResult
from atlas.models import Edge, EdgeConfidence, Effect, Node

PAGE = "Minerals/Refine_Tree"
SOURCE = "wiki:Minerals/Refine_Tree"
SYSTEM = "refine-tree"
# RN1 declares "req = 0" to mean "this is the root". There is no node zero.
ROOT_SENTINEL = "0"

_TEMPLATE_RE = re.compile(r"\{\{RN\|(.*?)\}\}", re.DOTALL)
_NUMBER_RE = re.compile(r"\d+")


def parse(raw: str) -> ExtractResult:
    result = ExtractResult()
    for match in _TEMPLATE_RE.finditer(raw):
        body = match.group(1)
        number = body.split("|", 1)[0].strip()
        if not number.isdigit():
            continue
        fields = template_fields(body)

        node_id = f"refine-node-{int(number)}"
        text = plain_text(fields.get("effect", ""))
        result.nodes.append(
            Node(
                id=node_id,
                name=f"Refine Node {int(number)}",
                system=SYSTEM,
                kind="tree-node",
                wiki=PAGE,
                effects=[Effect(text=text)] if text else [],
            )
        )

        for parent in _NUMBER_RE.findall(fields.get("req", "")):
            if parent == ROOT_SENTINEL:
                continue
            result.edges.append(
                Edge(
                    **{
                        "from": node_id,
                        "to": f"refine-node-{int(parent)}",
                        "rel": "requires",
                        "source": SOURCE,
                        "confidence": EdgeConfidence.DOCUMENTED,
                    }
                )
            )

        for reference in resolve(text):
            if reference.target_id == node_id:
                continue
            result.edges.append(
                Edge(
                    **{
                        "from": node_id,
                        "to": reference.target_id,
                        "rel": "boosts",
                        "note": text,
                        "targets_effect": reference.targets_effect,
                        "source": SOURCE,
                        "confidence": EdgeConfidence.PROVISIONAL,
                    }
                )
            )
    return result


def extract(raw_dir: Path) -> ExtractResult:
    text = (raw_dir / "Minerals__Refine_Tree.wikitext").read_text(encoding="utf-8")
    return parse(text)
