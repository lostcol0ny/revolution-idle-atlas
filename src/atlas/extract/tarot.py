import re
from pathlib import Path

from atlas.extract.refs import (
    ORDINALS,
    RANKS,
    SUITS,
    SurfaceFormCollision,
    Vocabulary,
    plain_text,
    resolve,
    slugify,
    template_fields,
)
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
#
# The Arcans template also carries `duration` and `cooldown`, which are read by
# template_fields and then deliberately discarded: they describe an activated
# skill's timing, and neither Node nor Effect has a field for it. They are the
# only information the Arcans schema carries that the suit schema does not, so
# their absence downstream is a modelling gap, not a parsing oversight.
_EFFECT_FIELDS = ("effect", "effect1", "effect2")

# "Swords Knight first effect mult x" — suit first, then rank or number. The
# resolver in refs.py handles `rank of suit` prose but not this compact
# suit-internal shorthand; the parser handles it here where the card names
# themselves are in hand to validate against.
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
# Ranks the compact shorthand spells as a word rather than a digit. The wiki
# writes "Swords 2", never "Swords Two", so the number-word ranks reach the
# parser only through _NUMBER_TO_RANK above; "ace" is written both ways and so
# belongs in both. Yields ("ace", "page", "knight", "queen", "king").
#
# Derived from RANKS rather than written out, because the two must not drift: a
# literal tuple could keep _SUIT_REF_RE matching a rank that RANKS no longer
# contains, and the id built from it would name a card the parser never mints.
# That failure deletes suit-internal edges while leaving every test green.
_DIGIT_ONLY_RANKS = frozenset(_NUMBER_TO_RANK.values()) - {"ace"}
_NAMED_RANKS = tuple(rank for rank in RANKS if rank not in _DIGIT_ONLY_RANKS)

# Matches: {suit} {number_or_rank}['s] [{ordinal}] effect
# Group 1 = suit, Group 2 = number or rank token, Group 3 = ordinal or None.
#
# The ordinal is optional and the possessive is allowed because Ten of Pentacles
# writes "Makes Pentacles 8's effect +x stronger" — the one card in the deck
# that boosts a non-adjacent sibling, and the one place the page drops both the
# ordinal and the plain "N first effect" shape. refs._EFFECT_POINTER_RE already
# anticipates the possessive, so this is a known form on the wiki, not an oddity.
_SUIT_REF_RE = re.compile(
    rf"\b({'|'.join(SUITS)})\s+(\d{{1,2}}|{'|'.join(_NAMED_RANKS)})"
    rf"(?:'s)?\s+(?:({'|'.join(ORDINALS)})\s+)?effect\b",
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


def _resolve_suit_refs(text: str) -> list[tuple[str, int | None]]:
    """Return (target_id, targets_effect) pairs found by the suit-internal RE.

    `targets_effect` comes from the ordinal the wiki actually wrote, so almost
    every hit is 0 ("... first effect mult x"). When the ordinal is absent —
    "Makes Pentacles 8's effect +x stronger" — the value is None rather than 0:
    the source does not say which of that card's two effects it means, and
    guessing 0 would fabricate a precision the wiki does not have.
    """
    hits: list[tuple[str, int | None]] = []
    # Keyed on the pair, matching refs.resolve: the same card named twice with
    # two different ordinals is two distinct claims, not one repeated.
    seen: set[tuple[str, int | None]] = set()
    for match in _SUIT_REF_RE.finditer(text):
        target_id = _suit_ref_to_id(match.group(1), match.group(2))
        if target_id is None:
            continue
        ordinal = match.group(3)
        targets_effect = ORDINALS[ordinal.lower()] if ordinal else None
        key = (target_id, targets_effect)
        if key in seen:
            continue
        seen.add(key)
        hits.append(key)
    return hits


def _card_terms(raw: str) -> list[tuple[str, str]]:
    """Every card name on the page, paired with the id `parse` mints for it.

    A pre-pass rather than accumulation inside the main loop: a card's effect
    text names cards defined further down the page, and the page is not ordered
    by who references whom.

    This is the promise `_TAROT_RE` in refs.py makes. The 22 Major Arcana are
    bare title-case noun phrases ("The Devil", "Strength") with no structural
    marker dividing them from ordinary prose, so a hardcoded regex would fire on
    any sentence using the words. Matching only the names actually parsed off
    this page, and only within this page's own effect text, is the containment
    that makes them safe to match at all — which is also why these terms are not
    added to the shared curated vocabulary.
    """
    terms: list[tuple[str, str]] = []
    for match in _TEMPLATE_RE.finditer(raw):
        name = plain_text(template_fields("|" + match.group(2)).get("card_name", ""))
        if name:
            terms.append((name, f"{SYSTEM}-{slugify(name)}"))
    return terms


def _with_cards(
    vocabulary: Vocabulary, raw: str
) -> tuple[Vocabulary, list[str]]:
    """Add this page's card names to `vocabulary`, dropping the ones that clash.

    A card name is read off a page volunteers edit, so it can arrive already
    claimed by a curated node — rename the card "Luck" and it contests the stat
    of that name. `with_terms` refuses the whole union in that case, which would
    turn one wiki edit into a failed extraction and take CI's artifact check down
    with it. The offending card is dropped and reported instead, exactly as the
    sweep reports a page it cannot read: the cost is the edges that one card
    would have produced, and the report says which card and which node.

    The union is tried in bulk first so the ordinary run pays for one build. Only
    when it is refused does each term go in on its own, which is what isolates
    the term at fault from the ones that were fine.
    """
    terms = _card_terms(raw)
    try:
        return vocabulary.with_terms(terms), []
    except SurfaceFormCollision:
        pass

    warnings: list[str] = []
    for term in terms:
        try:
            vocabulary = vocabulary.with_terms([term])
        except SurfaceFormCollision as exc:
            warnings.append(
                f"tarot page '{PAGE}': card {term[0]!r} is not matched in effect "
                f"prose — {exc}"
            )
    return vocabulary, warnings


def parse(raw: str, vocabulary: Vocabulary = Vocabulary.EMPTY) -> ExtractResult:
    """Parse the Tarot wiki page into nodes and edges.

    Each suit card produces one node with two effects; each Arcan produces one
    node with one effect. Suit-internal "Swords Knight first effect mult x"
    references become edges. Cross-system references (relic-N, refine-node-N,
    element-node-N) are delegated to the shared `resolve()` function.

    `vocabulary` is extended with every card name found on this page before the
    main loop runs, so an effect text can reference a card defined below it. A
    card name another node already claims is dropped with a warning rather than
    raising, so one wiki rename cannot fail every extraction.
    """
    vocabulary, warnings = _with_cards(vocabulary, raw)
    result = ExtractResult(warnings=warnings)
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
            # rank-of-suit tarot cards, and curated stat/currency names
            # (all handled by refs.resolve with the extended vocabulary).
            for reference in resolve(effect.text, vocabulary):
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
                            "confidence": (
                                EdgeConfidence.UNCERTAIN
                                if reference.from_vocabulary
                                else EdgeConfidence.PROVISIONAL
                            ),
                        }
                    )
                )

    return result


def extract(raw_dir: Path, vocabulary: Vocabulary = Vocabulary.EMPTY) -> ExtractResult:
    """Extract tarot cards from the raw Tarot wiki page."""
    return parse((raw_dir / "Tarot.wikitext").read_text(encoding="utf-8"), vocabulary)
