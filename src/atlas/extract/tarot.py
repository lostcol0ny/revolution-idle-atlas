import re
from pathlib import Path

from atlas.extract.refs import plain_text, resolve, slugify, template_fields
from atlas.extract.result import ExtractResult
from atlas.models import Edge, EdgeConfidence, Effect, Node

PAGE = "Tarot"
SOURCE = "wiki:Tarot"
SYSTEM = "tarot"

# The templates always close on their own line, which is what lets a nested
# {{Keyword|...}} inside an effect keep its own braces without ending the match.
_TEMPLATE_RE = re.compile(
    r"\{\{Tarot Cards(/Arcans)?\s*\|(.*?)\n\}\}", re.DOTALL
)

# Suit cards declare two effects under effect1/effect2; Arcans declare one
# under the bare "effect" key. Ordering matters: `targets_effect` is an index
# into the effects list, and that list is assembled in this order.
_EFFECT_FIELDS = ("effect", "effect1", "effect2")

# "Swords Knight first effect mult x" — Suit + rank/number, then "first effect".
# The resolver in refs.py handles `rank of suit` prose but not this compact
# suit-internal shorthand; the parser handles it here where the card names
# themselves are in hand to validate against.
_SUITS = ("swords", "wands", "pentacles", "cups")
_NUMBER_TO_RANK: dict[str, str] = {
    "1": "ace",
    "2": "two",
    "3": "three",
    "4": "four",
    "5": "five",
    "6": "six",
    "7": "seven",
    "8": "eight",
    "9": "nine",
    "10": "ten",
}
# Named ranks that appear literally in the shorthand (e.g. "Swords Page").
_NAMED_RANKS = ("ace", "page", "knight", "queen", "king")

# Matches: {suit} {number_or_rank} first effect
# Group 1 = suit, Group 2 = number or rank token, Group 3 = "first"
_SUIT_REF_RE = re.compile(
    rf"\b({'|'.join(_SUITS)})\s+(\d{{1,2}}|{'|'.join(_NAMED_RANKS)})\s+(first)\s+effect\b",
    re.IGNORECASE,
)


def _suit_ref_to_id(suit: str, token: str) -> str | None:
    """Resolve a suit-internal shorthand reference to a tarot node id.

    "Swords Knight" → "tarot-knight-of-swords"
    "Swords 1" → "tarot-ace-of-swords"
    Returns None when the token is unrecognised (guards against stale patterns).
    """
    suit_lc = suit.lower()
    token_lc = token.lower()
    rank = _NUMBER_TO_RANK.get(token_lc, token_lc if token_lc in _NAMED_RANKS else None)
    if rank is None:
        return None
    return f"tarot-{rank}-of-{suit_lc}"


def _resolve_suit_refs(text: str) -> list[tuple[str, int]]:
    """Return (target_id, targets_effect) pairs found by the suit-internal RE.

    `targets_effect` is always 0 because the shorthand always ends with
    "first effect" — there is no "second effect" variant in the source data.
    """
    hits: list[tuple[str, int]] = []
    seen: set[str] = set()
    for match in _SUIT_REF_RE.finditer(text):
        target_id = _suit_ref_to_id(match.group(1), match.group(2))
        if target_id is None or target_id in seen:
            continue
        seen.add(target_id)
        hits.append((target_id, 0))
    return hits


def parse(raw: str) -> ExtractResult:
    """Parse the Tarot wiki page into nodes and edges.

    Each suit card produces one node with two effects; each Arcan produces one
    node with one effect. Suit-internal "Swords Knight first effect mult x"
    references become edges. Cross-system references (relic-N, refine-node-N,
    element-node-N) are delegated to the shared `resolve()` function.
    """
    result = ExtractResult()
    for match in _TEMPLATE_RE.finditer(raw):
        fields = template_fields("|" + match.group(2))
        name = plain_text(fields.get("card_name", ""))
        if not name:
            continue

        node_id = f"{SYSTEM}-{slugify(name)}"
        effects = [
            Effect(text=plain_text(fields[field]))
            for field in _EFFECT_FIELDS
            if fields.get(field, "").strip()
        ]
        result.nodes.append(
            Node(
                id=node_id,
                name=name,
                system=SYSTEM,
                kind="tarot-card",
                wiki=PAGE,
                effects=effects,
            )
        )

        for effect in effects:
            # Suit-internal references: "Swords Knight first effect mult x"
            for target_id, targets_effect in _resolve_suit_refs(effect.text):
                if target_id == node_id:
                    continue
                result.edges.append(
                    Edge(
                        **{
                            "from": node_id,
                            "to": target_id,
                            "rel": "boosts",
                            "note": effect.text,
                            "targets_effect": targets_effect,
                            "source": SOURCE,
                            "confidence": EdgeConfidence.PROVISIONAL,
                        }
                    )
                )

            # Cross-system references: relic-N, refine-node-N, element-node-N,
            # and rank-of-suit tarot cards (handled by refs.resolve).
            for reference in resolve(effect.text):
                if reference.target_id == node_id:
                    continue
                result.edges.append(
                    Edge(
                        **{
                            "from": node_id,
                            "to": reference.target_id,
                            "rel": "boosts",
                            "note": effect.text,
                            "targets_effect": reference.targets_effect,
                            "source": SOURCE,
                            "confidence": EdgeConfidence.PROVISIONAL,
                        }
                    )
                )

    return result


def extract(raw_dir: Path) -> ExtractResult:
    """Extract tarot cards from the raw Tarot wiki page."""
    return parse((raw_dir / "Tarot.wikitext").read_text(encoding="utf-8"))
