import re
from dataclasses import dataclass

from atlas.models import Op

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_MATH_RE = re.compile(r"<math>.*?</math>", re.DOTALL)
_FILE_LINK_RE = re.compile(r"\[\[File:[^\]]*\]\]", re.IGNORECASE)
_TEMPLATE_RE = re.compile(r"\{\{([^{}]*)\}\}")
_PIPED_LINK_RE = re.compile(r"\[\[[^\]|]*\|([^\]|]*)\]\]")
_PLAIN_LINK_RE = re.compile(r"\[\[([^\]|]*)\]\]")
_HTML_TAG_RE = re.compile(
    r"</?(?:br|sup|sub|ref|small|big|span|div|center)[^>]*>", re.IGNORECASE
)


def slugify(text: str) -> str:
    return _SLUG_RE.sub("-", text.lower()).strip("-")


def normalise_space(text: str) -> str:
    return " ".join(text.split())


def _unwrap_template(match: re.Match[str]) -> str:
    parts = match.group(1).split("|")
    name = parts[0].strip().lower()
    # Named arguments (link=Achievements) are presentation, not content.
    positional = [p.strip() for p in parts[1:] if "=" not in p]
    if name == "keyword" and positional:
        # {{Keyword|<type>|<label>}} — the label is the readable text, and it
        # is also what the resolver matches on, so it must survive.
        return positional[-1]
    # Everything else on these four pages is decoration: icons and banners.
    return ""


def plain_text(raw: str) -> str:
    """Wiki markup in, readable plain text out.

    The output goes into graph.json and from there straight into React as a
    text node. It must never carry markup, because the frontend is forbidden
    from rendering HTML and would otherwise show the braces to the reader.
    """
    text = _COMMENT_RE.sub("", raw)
    text = _MATH_RE.sub("", text)
    text = _FILE_LINK_RE.sub("", text)
    # _TEMPLATE_RE only matches an innermost {{...}} pair, so nested templates
    # need repeated passes. Five is far beyond the observed depth of two, and
    # bounding it means malformed markup cannot spin here.
    for _ in range(5):
        unwrapped = _TEMPLATE_RE.sub(_unwrap_template, text)
        if unwrapped == text:
            break
        text = unwrapped
    text = _PIPED_LINK_RE.sub(r"\1", text)
    text = _PLAIN_LINK_RE.sub(r"\1", text)
    text = _HTML_TAG_RE.sub("", text)
    text = text.replace("'''", "").replace("''", "")
    return normalise_space(text)


def split_fields(body: str) -> list[str]:
    """Split a template body on its own field separators.

    A naive `body.split("|")` cuts {{Keyword|ach|Ach 232}} into three pieces
    and destroys the effect text around it, so pipes inside a nested template
    or link have to be held together.
    """
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    index = 0
    while index < len(body):
        pair = body[index : index + 2]
        if pair in ("{{", "[["):
            depth += 1
            current.append(pair)
            index += 2
        elif pair in ("}}", "]]"):
            depth = max(depth - 1, 0)
            current.append(pair)
            index += 2
        elif body[index] == "|" and depth == 0:
            parts.append("".join(current))
            current = []
            index += 1
        else:
            current.append(body[index])
            index += 1
    parts.append("".join(current))
    return parts


def template_fields(body: str) -> dict[str, str]:
    """Read `name = value` pairs out of a template body, lowercasing names."""
    fields: dict[str, str] = {}
    for chunk in split_fields(body):
        if "=" not in chunk:
            continue
        # Partition on the *first* "=": one refine-tree effect reads
        # "they become Fire= 0.5, Earth= 3.50" and must survive intact.
        name, _, value = chunk.partition("=")
        fields[normalise_space(name).lower()] = value.strip()
    return fields


# Longest first: "+^" must be tested before "+", "*^" before "*". Matching is
# case-sensitive on purpose — "x1.02" is a multiplier, but "X = +0.11 & Y = ..."
# is a two-variable note the wiki has not reduced to one operator.
_OP_PREFIXES: tuple[tuple[str, Op], ...] = (
    ("+^", Op.EXP),
    ("-^", Op.EXP),
    ("^^", Op.EXP),
    ("*^", Op.MULT),
    ("x^", Op.MULT),
    ("^", Op.EXP),
    ("x", Op.MULT),
    ("*", Op.MULT),
    ("/", Op.MULT),
    ("+", Op.ADD),
    ("-", Op.ADD),
)


def derive_op(per_level: str | None) -> Op | None:
    if per_level is None:
        return None
    token = normalise_space(per_level)
    for prefix, op in _OP_PREFIXES:
        if token.startswith(prefix):
            return op
    return None


def is_uncertain(*texts: str | None) -> bool:
    """True when the wiki itself hedges. "(?)" and a trailing "?" both count."""
    return any("?" in text for text in texts if text)


@dataclass(frozen=True)
class Reference:
    target_id: str
    targets_effect: int | None = None


_RELIC_RE = re.compile(
    r"\brelics?\s+(\d+(?:\s*(?:,|and|&)\s*\d+)*)", re.IGNORECASE
)
_REFINE_RE = re.compile(r"\brefine(?:\s+tree)?\s+node\s+(\d+)", re.IGNORECASE)
_ELEMENT_RE = re.compile(r"\b(fire|earth|wind|water)\s+node\s+(\d+)", re.IGNORECASE)
_RANKS = (
    "ace", "two", "three", "four", "five", "six", "seven",
    "eight", "nine", "ten", "page", "knight", "queen", "king",
)
_SUITS = ("swords", "wands", "pentacles", "cups")
# Minor Arcana only, and deliberately so. The 22 Major Arcana ("The Fool",
# "The Devil", ...) are bare title-case noun phrases with no structural marker
# dividing them from ordinary prose, so matching them here would take a
# hardcoded name list and would still fire on any sentence that merely used the
# words. Task 7 resolves them instead, where the card names actually parsed off
# the page are in hand and a candidate match can be checked against them.
# Until then `resolve("Multiplies The Devil's base effect") == []` is the
# designed outcome, not a bug.
_TAROT_RE = re.compile(
    rf"\b({'|'.join(_RANKS)})\s+of\s+({'|'.join(_SUITS)})\b", re.IGNORECASE
)
_NUMBER_RE = re.compile(r"\d+")

_ORDINALS = {"first": 0, "second": 1, "third": 2}
_EFFECT_POINTER_RE = re.compile(
    rf"^(?:'s)?\s+({'|'.join(_ORDINALS)})\s+effect\b", re.IGNORECASE
)


def _effect_index(text: str, after: int) -> int | None:
    match = _EFFECT_POINTER_RE.match(text[after:])
    return _ORDINALS[match.group(1).lower()] if match else None


def resolve(text: str) -> list[Reference]:
    """Find the node ids a sentence names.

    Precision over recall throughout. A bare "Node 4" is not matched: inside
    Elements it means an element node and inside Minerals a refine node, and a
    wrong edge is worse than a missing one — a missing one shows up in the
    coverage report, a wrong one just looks true.
    """
    hits: list[tuple[int, str, int]] = []

    for match in _RELIC_RE.finditer(text):
        for number in _NUMBER_RE.findall(match.group(1)):
            hits.append((match.start(), f"relic-{int(number)}", match.end()))
    for match in _REFINE_RE.finditer(text):
        hits.append((match.start(), f"refine-node-{int(match.group(1))}", match.end()))
    for match in _ELEMENT_RE.finditer(text):
        element = match.group(1).lower()
        hits.append(
            (match.start(), f"{element}-node-{int(match.group(2))}", match.end())
        )
    for match in _TAROT_RE.finditer(text):
        card = slugify(f"{match.group(1)} of {match.group(2)}")
        hits.append((match.start(), f"tarot-{card}", match.end()))

    references: list[Reference] = []
    seen: set[tuple[str, int | None]] = set()
    for _, target_id, end in sorted(hits, key=lambda hit: hit[0]):
        reference = Reference(target_id, _effect_index(text, end))
        key = (reference.target_id, reference.targets_effect)
        if key in seen:
            continue
        seen.add(key)
        references.append(reference)
    return references
