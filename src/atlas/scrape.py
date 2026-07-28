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


# httpx always pre-populates User-Agent, so a plain dict setdefault can never
# distinguish "caller chose this" from "httpx filled it in". Comparing against
# httpx's own default is the only signal that tells the two apart.
HTTPX_DEFAULT_USER_AGENT = f"python-httpx/{httpx.__version__}"


class ScrapeError(Exception):
    """Raised when the wiki API misbehaves or returns nothing usable."""


def make_client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30.0)


def fetch_pages(client: httpx.Client) -> dict[str, str]:
    pages: dict[str, str] = {}
    params = dict(BASE_PARAMS)

    caller_ua = client.headers.get("User-Agent", HTTPX_DEFAULT_USER_AGENT)
    if caller_ua == HTTPX_DEFAULT_USER_AGENT:
        client.headers["User-Agent"] = USER_AGENT

    while True:
        response = client.get(API_URL, params=params)
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

    # Derive every filename before writing anything: a title that cannot produce
    # a usable path must fail while data/raw/ is still untouched, rather than
    # aborting midway and leaving a partial scrape that looks like a real diff.
    by_filename: dict[str, str] = {}
    for title, content in pages.items():
        filename = raw_filename(title)
        if "\x00" in filename:
            raise ScrapeError(f"wiki title {title!r} yields an unusable filename")
        by_filename[filename] = content

    raw_dir.mkdir(parents=True, exist_ok=True)

    for filename, content in by_filename.items():
        (raw_dir / filename).write_text(content, encoding="utf-8")

    for existing in raw_dir.glob("*.wikitext"):
        if existing.name not in by_filename:
            existing.unlink()

    return len(pages)
