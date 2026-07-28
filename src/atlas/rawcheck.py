from pathlib import Path

from atlas.models import Dataset, NodeConfidence
from atlas.problems import Problem

NEW_CONTENT_MARKER = "{{New Content}}"

# The check's purpose is "do not claim documented confidence for content the
# wiki itself flags as in flux". 'unknown' claims strictly less confidence than
# 'provisional', so it under-claims rather than over-claims and must be accepted
# too — warning on it is a false positive, and one that pushes stub nodes into
# 'provisional' and quietly zeroes the coverage report's stub count.
ACCEPTED_ON_WIP = frozenset({NodeConfidence.PROVISIONAL, NodeConfidence.UNKNOWN})


def raw_filename(wiki: str) -> str:
    # MediaWiki treats spaces and underscores as equivalent in a page title, so
    # both forms must collapse to one filename here. This is the single source of
    # truth shared by the scraper (which writes) and check_against_raw (which
    # reads); normalising at a call site instead lets the two drift apart.
    page = wiki.split("#", 1)[0]
    return page.replace(" ", "_").replace("/", "__") + ".wikitext"


def check_against_raw(ds: Dataset, raw_dir: Path) -> list[Problem]:
    if not raw_dir.is_dir():
        return []

    problems: list[Problem] = []
    for node in ds.nodes:
        if node.wiki is None or not node.wiki.strip():
            continue

        page_file = raw_dir / raw_filename(node.wiki)
        if not page_file.is_file():
            problems.append(
                Problem(
                    severity="warning",
                    message=(
                        f"node '{node.id}' points at wiki page "
                        f"'{node.wiki}' which no longer exists in data/raw/"
                    ),
                    line=node.line,
                )
            )
            continue

        text = page_file.read_text(encoding="utf-8")
        if NEW_CONTENT_MARKER in text and node.confidence not in ACCEPTED_ON_WIP:
            problems.append(
                Problem(
                    severity="warning",
                    message=(
                        f"node '{node.id}' sources from a {NEW_CONTENT_MARKER} page "
                        f"but confidence is '{node.confidence}' — expected "
                        f"'provisional' or 'unknown'"
                    ),
                    line=node.line,
                )
            )

    return problems
