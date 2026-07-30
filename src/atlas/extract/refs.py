import re
from collections.abc import Iterable
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
    # True when a Vocabulary surface form produced this, rather than one of the
    # four entity regexes. Callers stamp `confidence: uncertain` on these: prose
    # matching is weaker evidence than a structural table cell, and a flat
    # per-call-site confidence cannot express the difference.
    from_vocabulary: bool = False


_RELIC_RE = re.compile(
    r"\brelics?\s+(\d+(?:\s*(?:,|and|&)\s*\d+)*)", re.IGNORECASE
)
_REFINE_RE = re.compile(r"\brefine(?:\s+tree)?\s+node\s+(\d+)", re.IGNORECASE)
_ELEMENT_RE = re.compile(r"\b(fire|earth|wind|water)\s+node\s+(\d+)", re.IGNORECASE)
RANKS = (
    "ace", "two", "three", "four", "five", "six", "seven",
    "eight", "nine", "ten", "page", "knight", "queen", "king",
)
SUITS = ("swords", "wands", "pentacles", "cups")
# Minor Arcana only, and deliberately so. The 22 Major Arcana ("The Fool",
# "The Devil", ...) are bare title-case noun phrases with no structural marker
# dividing them from ordinary prose, so matching them here would take a
# hardcoded name list and would still fire on any sentence that merely used the
# words. They are resolved through a Vocabulary instead, by the caller that has
# the card names actually parsed off the page in hand and can therefore check a
# candidate match against them. With no vocabulary supplied,
# `resolve("Multiplies The Devil's base effect") == []` is the designed
# outcome, not a bug.
_TAROT_RE = re.compile(
    rf"\b({'|'.join(RANKS)})\s+of\s+({'|'.join(SUITS)})\b", re.IGNORECASE
)
_NUMBER_RE = re.compile(r"\d+")

ORDINALS = {"first": 0, "second": 1, "third": 2}
_EFFECT_POINTER_RE = re.compile(
    rf"^(?:'s)?\s+({'|'.join(ORDINALS)})\s+effect\b", re.IGNORECASE
)


def _effect_index(text: str, after: int) -> int | None:
    match = _EFFECT_POINTER_RE.match(text[after:])
    return ORDINALS[match.group(1).lower()] if match else None


# 3 characters, or 2 when the surface form is ALL-UPPERCASE. The floor exists to
# stop short forms firing inside ordinary words; for an abbreviation,
# case-sensitivity already does that job, and AP/EP/IP/DP/RP/TF are the wiki's
# most-used currency names. A flat floor of 3 would discard exactly those.
_MIN_SURFACE_LENGTH = 3
_MIN_UPPERCASE_SURFACE_LENGTH = 2


class SurfaceFormCollision(ValueError):
    """Two distinct nodes claim the same surface form.

    Fatal rather than resolved in favour of one side, for the reason
    `build_vocabulary` sets out: the loser becomes unreachable and text spelled
    for it silently resolves to the winner.

    Subclasses ValueError so callers that only care that the input was bad keep
    working; the distinct type is what lets the CLI tell a curation error apart
    from an ordinary ValueError raised while parsing a wiki page.
    """


@dataclass(frozen=True)
class _Term:
    pattern: re.Pattern[str]
    target_id: str


class Vocabulary:
    """Surface forms to match in effect prose, longest form first.

    Built from the node set's names and aliases, so teaching the resolver a new
    stat is a YAML entry rather than a code change.

    Every guard here exists because a wrong edge is worse than a missing one: a
    missing one shows up in the coverage report, a wrong one just looks true.
    Callers therefore stamp `confidence: uncertain` on anything this produces —
    prose is weaker evidence than a structural table cell.
    """

    EMPTY: "Vocabulary"

    def __init__(self, terms: Iterable[tuple[str, str]]) -> None:
        accepted: list[tuple[str, str]] = []
        # Keyed on the case-folded surface, because two spellings that differ
        # only in case still collide at match time: at least one of any such
        # pair is non-uppercase (two ALL-UPPERCASE strings that fold alike are
        # identical), and a non-uppercase surface compiles case-insensitively,
        # so it matches the other spelling too. Keying on the exact string would
        # let that pair through to fight over the same spans.
        claims: dict[str, tuple[str, str]] = {}
        seen_pairs: set[tuple[str, str]] = set()
        for surface, target_id in terms:
            surface = normalise_space(surface)
            # The 2-character floor is for letter abbreviations only. isalpha()
            # excludes "A1", "2X" and "A-": their digits and punctuation give
            # case-sensitivity nothing to grip on, so they get no exemption.
            # isupper() is already False for "SMMF Factor" (mixed) and for "",
            # both of which should take the stricter floor.
            floor = (
                _MIN_UPPERCASE_SURFACE_LENGTH
                if surface.isupper() and surface.isalpha()
                else _MIN_SURFACE_LENGTH
            )
            if len(surface) < floor:
                continue
            if (surface, target_id) in seen_pairs:
                # The same pair twice is harmless — one node listing an alias
                # that is also its name, or a union that overlaps. Dedupe it.
                continue
            claimed = claims.get(surface.casefold())
            if claimed is not None and claimed[1] != target_id:
                # One phrase cannot mean two nodes. Only one of the two would
                # ever claim a span; the loser becomes unreachable and can never
                # produce an edge, while text the curator spelled for it resolves
                # to the winner instead — a wrong edge indistinguishable from a
                # true one, decided by sort order rather than by meaning. This is
                # a data conflict for a curator to resolve, so say so loudly.
                prior_surface, prior_target = claimed
                spelling = (
                    repr(surface)
                    if prior_surface == surface
                    else f"{prior_surface!r}/{surface!r}"
                )
                raise SurfaceFormCollision(
                    f"surface form {spelling} is claimed by two nodes: "
                    f"{prior_target!r} and {target_id!r}"
                )
            # Two case spellings of one node's name are not a conflict, just an
            # alias spelled twice, so both are kept: the exact-pair dedupe above
            # is the only thing that drops a term. Their match spans coincide,
            # which hits() and resolve()'s dedup already collapse to one edge.
            seen_pairs.add((surface, target_id))
            claims.setdefault(surface.casefold(), (surface, target_id))
            accepted.append((surface, target_id))

        # Longest first so "Special Minerals Merge Factor" claims the span
        # before "Merge Factor" can. Ties broken alphabetically so the term
        # order — and therefore the emitted edge order — is deterministic
        # across runs; graph.json is a committed artifact diffed by CI.
        accepted.sort(key=lambda item: (-len(item[0]), item[0]))

        # Kept so with_terms() can re-sort across the union. Storing the
        # accepted pairs rather than the input means a term rejected by the
        # length floor stays rejected through any number of extensions.
        self._pairs = tuple(accepted)

        self._terms = tuple(
            _Term(
                # re.escape because a surface form is data: "Zodiac Exp. Factor"
                # contains a dot, and an unescaped one both over-matches and
                # risks re.error on a malformed alias.
                #
                # Lookarounds rather than \b, because \b is a boundary *between*
                # a word and a non-word character and so asserts nothing when
                # the surface itself starts or ends with punctuation: r"\bZodiac
                # Exp.\b" can never match "Zodiac Exp." at all. These behave
                # identically on word-character edges and correctly on the rest.
                re.compile(
                    rf"(?<!\w){re.escape(surface)}(?!\w)",
                    0 if surface.isupper() else re.IGNORECASE,
                ),
                target_id,
            )
            for surface, target_id in accepted
        )

    def __len__(self) -> int:
        return len(self._terms)

    def with_terms(self, terms: Iterable[tuple[str, str]]) -> "Vocabulary":
        """A new vocabulary over the union of this one's terms and `terms`.

        Returns a new instance rather than mutating: the curated vocabulary is
        built once and every parser shares it, so an in-place extend in
        tarot.py would leak the Major Arcana into every other parser.

        Constructing a fresh Vocabulary re-sorts longest-first across both sets,
        which is the whole point. Appending would let a short curated form claim
        a span a longer added form should have taken. Routing through __init__
        also re-runs the conflicting-claim check over the union, so an added
        term cannot quietly contest a surface form the receiver already owns.

        Raises SurfaceFormCollision if it does.
        """
        return Vocabulary([*self._pairs, *terms])

    def hits(
        self, text: str, claimed: list[tuple[int, int]]
    ) -> list[tuple[int, str, int]]:
        """Find (start, target_id, end) triples, skipping already-claimed spans.

        `claimed` carries the spans the entity regexes matched. A stat aliased
        "Refine Node 2" must not produce a second reference for a phrase the
        refine-tree regex already resolved — one phrase, one edge.
        """
        taken = list(claimed)
        found: list[tuple[int, str, int]] = []
        for term in self._terms:
            for match in term.pattern.finditer(text):
                start, end = match.span()
                if any(
                    start < other_end and other_start < end
                    for other_start, other_end in taken
                ):
                    continue
                taken.append((start, end))
                found.append((start, term.target_id, end))
        return found


Vocabulary.EMPTY = Vocabulary(())  # type: ignore[attr-defined]


def resolve(text: str, vocabulary: Vocabulary | None = None) -> list[Reference]:
    """Find the node ids a sentence names.

    Precision over recall throughout. A bare "Node 4" is not matched: inside
    Elements it means an element node and inside Minerals a refine node, and a
    wrong edge is worse than a missing one — a missing one shows up in the
    coverage report, a wrong one just looks true.

    `vocabulary` is optional and defaulted so the four hardcoded entity regexes
    remain the whole behaviour for a caller that passes nothing. When supplied,
    its surface forms are matched after the regexes and never over a span a
    regex already claimed, and the references it produces carry
    `from_vocabulary=True` so a caller can weaken their confidence.
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

    # A 4-tuple rather than a flag threaded separately, so position ordering and
    # provenance stay in one sortable record. Entity hits are marked first, and
    # the claimed spans handed to the vocabulary are exactly theirs.
    marked: list[tuple[int, str, int, bool]] = [
        (start, target_id, end, False) for start, target_id, end in hits
    ]
    if vocabulary is not None:
        claimed = [(start, end) for start, _, end in hits]
        marked += [
            (start, target_id, end, True)
            for start, target_id, end in vocabulary.hits(text, claimed)
        ]

    references: list[Reference] = []
    seen: set[tuple[str, int | None]] = set()
    for _, target_id, end, from_vocabulary in sorted(marked, key=lambda hit: hit[0]):
        reference = Reference(target_id, _effect_index(text, end), from_vocabulary)
        key = (reference.target_id, reference.targets_effect)
        if key in seen:
            continue
        seen.add(key)
        references.append(reference)
    return references
