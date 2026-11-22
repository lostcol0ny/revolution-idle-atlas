"""Edges from data/game.yaml, the game's own text, which `atlas game` commits.

Read by `atlas extract` rather than by `atlas game`, so the edges follow the
current vocabulary and CI rebuilds them without a game install.

Three kinds of edge come out:

- Every member of a Particles family is joined to the node it hangs off
  (`particles.MEMBER_LINKS`). The game's help text states these plainly, so they
  are `documented`.
- The description of a node only the game describes — one `atlas game`
  created, carrying `system` — is matched like wiki effect prose. A node a wiki
  page already describes keeps the wiki's effects as its only matched text, so
  one entity is never matched twice in two wordings. When the entry carries
  effects (an achievement's reward), those are matched instead.
- An entry with effects has a description that says what it asks of the
  player. A goal that is a plain threshold ("Reach 5 Infinities") makes what
  it names a `requires` of the entry.
"""

import re
from dataclasses import replace

from atlas.extract.refs import Reference, Vocabulary, resolve
from atlas.extract.result import ExtractResult
from atlas.extract.sweep import is_plain_threshold
from atlas.models import Edge, EdgeConfidence, GameData, Kind, Rel
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
# "Reach 5 Infinities", "Have 2,025+ Luck": the verb goes, and what is left
# must pass the sweep's plain-threshold rule, so "Reach a score of e5e10 in
# Dilation" and "Have Sparks of all 10 colors" make no edge.
_GOAL_VERB = re.compile(r"^(?:reach|have)\s+(?:at least\s+)?", re.IGNORECASE)
# "Unlocks macro block for Dilation": a macro block scripts what it names for
# the player's macros, and changes nothing about it.
_MACRO_BLOCK = re.compile(r"\bmacro blocks?\b", re.IGNORECASE)


def _threshold(goal: str) -> str | None:
    verb = _GOAL_VERB.match(goal)
    if verb is None:
        return None
    rest = goal[verb.end() :]
    return rest if is_plain_threshold(rest) else None


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
        if entry.system is None:
            continue
        # An achievement's description is its goal ("Reach 5 Infinities"), which
        # the achievement never raises; only its reward may boost anything.
        goal_only = entry.kind == Kind.ACHIEVEMENT or bool(entry.effects)
        if goal_only:
            texts = [
                sentence
                for effect in entry.effects
                for sentence in _SENTENCE_BREAK.split(effect)
                if not _MACRO_BLOCK.search(sentence)
            ]
        else:
            texts = [entry.description] if entry.description else []
        seen: set[tuple[str, str]] = set()
        for reference in (r for text in texts for r in _references(text, vocabulary)):
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
        goal = _threshold(entry.description) if goal_only and entry.description else None
        if goal is None:
            continue
        # A grade is a fine prerequisite ("Reach Tetr 1+"); it is excluded
        # above only because a grade bonus reads its grade.
        prerequisites = dict.fromkeys(r.target_id for r in resolve(goal, vocabulary))
        prerequisites.pop(entry.id, None)
        edges += [
            Edge(
                from_=prerequisite,
                to=entry.id,
                rel=Rel.REQUIRES,
                source=SOURCE,
                confidence=EdgeConfidence.UNCERTAIN,
            )
            for prerequisite in prerequisites
        ]
    return ExtractResult(edges=edges)
