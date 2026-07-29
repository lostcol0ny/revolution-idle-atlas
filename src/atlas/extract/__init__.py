from pathlib import Path

from atlas.extract import elements, refine_tree, relics, tarot
from atlas.extract.result import ExtractResult, prune_dangling


class ExtractError(Exception):
    """A source produced nothing, so its page or its parser has broken."""


def run_all(raw_dir: Path) -> ExtractResult:
    """Run every parser over data/raw/ and drop edges with no endpoint.

    Parser order fixes the order ids are minted in, and so the order of the
    emitted file. Each parser currently mints ids only for its own system, so
    no id is produced twice and `to_yaml`'s first-wins dedup never actually has
    to choose between two definitions — today this ordering governs the diff,
    not resolution. Were a later parser to name a node another one owns, the
    owner running first is what would make first-wins the correct rule.

    A parser that returns zero nodes raises rather than returning quietly. The
    wiki is edited by volunteers; a renamed heading or a restructured table
    turns a parser into a silent no-op, and the committed derived.yaml would
    then lose a whole system with nothing to say it had.
    """
    combined = ExtractResult()
    for module in (relics, refine_tree, tarot, elements):
        result = module.extract(raw_dir)
        if not result.nodes:
            name = module.__name__.rsplit(".", 1)[-1]
            raise ExtractError(f"{name} produced no nodes — its source page changed shape")
        combined.extend(result)
    return prune_dangling(combined)
