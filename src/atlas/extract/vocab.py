from collections.abc import Iterable

from atlas.extract.refs import Vocabulary
from atlas.models import Node


def build_vocabulary(nodes: Iterable[Node]) -> Vocabulary:
    """Turn nodes into the surface forms a parser should recognise.

    A node's `name` and every entry in its `aliases` are handed over verbatim.
    Nothing is filtered here: `Vocabulary` owns the length floor and the case
    rules, and duplicating that judgement in a second place is how the two
    drift apart.

    Every node participates, not only alias-bearing ones. Most stats have no
    abbreviation the wiki uses, so an alias-only rule would drop them.

    Raises:
        ValueError: If two distinct nodes claim the same surface form, after
            case-folding. This surfaces a curation error that validate_dataset
            cannot detect (it checks only for duplicate ids), and a wrong edge
            produced by a silently-resolved collision is worse than an exception.
    """
    terms: list[tuple[str, str]] = []
    for node in nodes:
        terms.append((node.name, node.id))
        terms.extend((alias, node.id) for alias in node.aliases)
    return Vocabulary(terms)
