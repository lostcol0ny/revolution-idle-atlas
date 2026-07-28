from pathlib import Path
from typing import Any

import httpx

from atlas.rawcheck import raw_filename

API_URL = "https://revolutionidle.wiki.gg/api.php"
USER_AGENT = (
    "revolution-idle-atlas/0.1 "
    "(+https://github.com/tobydillman/revolution-idle-atlas)"
)

BASE_PARAMS: dict[str, Any] = {
    "action": "query",
    "format": "json",
    "generator": "allpages",
    "gapnamespace": 0,
    "gaplimit": 50,
    "prop": "revisions",
    "rvprop": "content",
    "rvslots": "main",
}


class ScrapeError(Exception):
    """Raised when the wiki API misbehaves or returns nothing usable."""


def make_client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30.0)


def fetch_pages(client: httpx.Client) -> dict[str, str]:
    pages: dict[str, str] = {}
    params = dict(BASE_PARAMS)

    while True:
        response = client.get(API_URL, params=params, headers={"User-Agent": USER_AGENT})
        if response.status_code != 200:
            raise ScrapeError(
                f"wiki API returned {response.status_code} for {response.url}"
            )

        payload = response.json()
        for page in payload.get("query", {}).get("pages", {}).values():
            revisions = page.get("revisions") or []
            if not revisions:
                continue
            content = revisions[0].get("slots", {}).get("main", {}).get("*")
            if content is None:
                continue
            pages[page["title"]] = content

        cont = payload.get("continue")
        if not cont:
            break
        params = dict(BASE_PARAMS) | cont

    if not pages:
        raise ScrapeError("wiki API returned no pages — refusing to continue")

    return pages


def write_raw(pages: dict[str, str], raw_dir: Path) -> int:
    if not pages:
        raise ScrapeError("refusing to write an empty scrape into data/raw/")

    raw_dir.mkdir(parents=True, exist_ok=True)

    expected: set[str] = set()
    for title, content in pages.items():
        filename = raw_filename(title.replace(" ", "_"))
        expected.add(filename)
        (raw_dir / filename).write_text(content, encoding="utf-8")

    for existing in raw_dir.glob("*.wikitext"):
        if existing.name not in expected:
            existing.unlink()

    return len(pages)
