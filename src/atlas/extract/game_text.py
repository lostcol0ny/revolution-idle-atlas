"""Edges from data/game.yaml, the game's own text, which `atlas game` commits.

Read by `atlas extract` rather than by `atlas game`, so the edges follow the
current vocabulary and CI rebuilds them without a game install.

Two kinds of edge come out:

- Every member of a Particles family is joined to the node it hangs off
  (`particles.MEMBER_LINKS`). The game's help text states these plainly, so they
  are `documented`.
- The description of a node only the game describes — one `atlas game`
  created, carrying `system` — is matched like wiki effect prose. A node a wiki
  page already describes keeps the wiki's effects as its only matched text, so
  one entity is never matched twice in two wordings.
"""

import re
from dataclasses import replace

from atlas.extract.refs import Reference, Vocabulary, resolve
from atlas.extract.result import ExtractResult
from atlas.models import Edge, EdgeConfidence, GameData, Rel
from atlas.particles import GRADES, MEMBER_LINKS, grade_node

SOURCE = "game"

_SENTENCE_BREAK = re.compile(r"(?<=\.)\s+")
# "Refinement node 141 improves this bonus." The node named improves the
# bonus, so it is upstream of it, not something the bonus changes.
_IMPROVES_THIS = re.compile(r"\bimproves this\b", re.IGNORECASE)
# "α generator base ×(β + 1)^0.2 (improved by refinement node 147)."
_IMPROVED_BY = re.compile(r"\(\s*improved by\b([^()]*)\)", re.IGNORECASE)
# A grade bonus reads its grade ("+0.01 per rank", "Particle Rank boosts
# Luck"); it never changes it. The grade's own `requires` edge already says
# the bonus depends on it.
_GRADE_IDS = frozenset(grade_node(grade) for grade in GRADES)


def _as_input(reference: Reference) -> Reference:
    return replace(reference, is_input=True, targets_effect=None)


def _references(text: str, vocabulary: Vocabulary) -> list[Reference]:
    """Every node a game description names, with the improvers marked as inputs.

    `resolve` already reverses what follows "based on". The game adds a second
    phrasing for an input, the improver: "X improves this bonus", or
    "(improved by X)".
    """
    found: list[Reference] = []
    for sentence in _SENTENCE_BREAK.split(text):
        if _IMPROVES_THIS.search(sentence):
            found += [_as_input(r) for r in resolve(sentence, vocabulary)]
            continue
        for match in _IMPROVED_BY.finditer(sentence):
            found += [_as_input(r) for r in resolve(match.group(1), vocabulary)]
        found += resolve(_IMPROVED_BY.sub("", sentence), vocabulary)
    return found


def extract(game: GameData, vocabulary: Vocabulary) -> ExtractResult:
    edges: list[Edge] = []
    for entry in game.nodes:
        for prefix, parent, rel in MEMBER_LINKS:
            if entry.id.startswith(prefix):
                edges.append(Edge(from_=parent, to=entry.id, rel=rel, source=SOURCE))
        if entry.system is None or entry.description is None:
            continue
        seen: set[tuple[str, str]] = set()
        for reference in _references(entry.description, vocabulary):
            if reference.target_id in _GRADE_IDS or reference.target_id == entry.id:
                continue
            origin, target = reference.endpoints(entry.id)
            if (origin, target) in seen:
                continue
            seen.add((origin, target))
            edges.append(
                Edge(
                    from_=origin,
                    to=target,
                    # Always `boosts` and `uncertain`, as for swept wiki prose:
                    # a name spotted in a sentence says a relationship exists,
                    # not what kind.
                    rel=Rel.BOOSTS,
                    targets_effect=reference.targets_effect,
                    source=SOURCE,
                    confidence=EdgeConfidence.UNCERTAIN,
                )
            )
    return ExtractResult(edges=edges)
