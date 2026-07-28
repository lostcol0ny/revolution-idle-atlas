from pathlib import Path

from atlas.models import Dataset, NodeConfidence
from atlas.problems import Problem

NEW_CONTENT_MARKER = "{{New Content}}"


def raw_filename(wiki: str) -> str:
    page = wiki.split("#", 1)[0]
    return page.replace("/", "__") + ".wikitext"


def check_against_raw(ds: Dataset, raw_dir: Path) -> list[Problem]:
    if not raw_dir.is_dir():
        return []

    problems: list[Problem] = []
    for node in ds.nodes:
        if node.wiki is None:
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
        if NEW_CONTENT_MARKER in text and node.confidence is not NodeConfidence.PROVISIONAL:
            problems.append(
                Problem(
                    severity="warning",
                    message=(
                        f"node '{node.id}' sources from a {NEW_CONTENT_MARKER} page "
                        f"but confidence is '{node.confidence}' — expected 'provisional'"
                    ),
                    line=node.line,
                )
            )

    return problems
