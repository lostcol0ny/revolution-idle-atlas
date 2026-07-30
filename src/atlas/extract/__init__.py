from pathlib import Path

from atlas.extract import elements, refine_tree, relics, sweep, tarot
from atlas.extract.manifest import Manifest
from atlas.extract.refs import Vocabulary
from atlas.extract.result import ExtractResult, prune_dangling


class ExtractError(Exception):
    """A source produced nothing, so its page or its parser has broken."""


def run_all(
    raw_dir: Path,
    vocabulary: Vocabulary = Vocabulary.EMPTY,
    external_ids: frozenset[str] = frozenset(),
    manifest: Manifest | None = None,
) -> ExtractResult:
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

    `vocabulary` is the curated node set's names and aliases (see
    extract/vocab.py). It is what lets an effect naming a stat produce an edge,
    and it means `data/derived.yaml` is a function of `data/relationships.yaml`
    as well as `data/raw/` — a curated stat edit needs `atlas extract`, not just
    `atlas build`.

    `external_ids` are node ids the curated dataset already defines, so pruning
    keeps vocabulary-matched edges that point at them rather than treating them
    as typos.

    The manifest-driven sweep runs last and is held to a different standard: a
    page it cannot read is a warning on the result, not an exception. The four
    parsers above cover pages known to hold data, so zero nodes means something
    broke. A manifest entry is a guess about a page's shape, and one wrong guess
    must not block every build. Running last also means the four parsers' ids
    win `to_yaml`'s first-wins dedup wherever a swept name collides with one.
    """
    combined = ExtractResult()
    for module in (relics, refine_tree, tarot, elements):
        result = module.extract(raw_dir, vocabulary)
        if not result.nodes:
            name = module.__name__.rsplit(".", 1)[-1]
            raise ExtractError(f"{name} produced no nodes — its source page changed shape")
        combined.extend(result)
    combined.extend(sweep.extract(raw_dir, manifest or Manifest(), vocabulary))
    return prune_dangling(combined, external_ids)
