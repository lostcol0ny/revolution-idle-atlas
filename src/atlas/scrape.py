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

# write_raw deletes any raw file the incoming scrape did not produce. A scrape
# holding fewer than this fraction of what is already on disk is treated as
# truncated rather than as a genuine shrink, and refuses to write.
REAP_FLOOR_RATIO = 0.8


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
        # MediaWiki reports API-level failures (readonly, maxlag, throttling)
        # with HTTP 200 and an "error" body. Such a response carries no
        # "continue" key, so without this the loop exits *normally* holding a
        # partial page set — which write_raw would then treat as the whole wiki.
        if "error" in payload:
            error = payload["error"]
            code = error.get("code", "unknown") if isinstance(error, dict) else "unknown"
            info = error.get("info", error) if isinstance(error, dict) else error
            raise ScrapeError(f"wiki API error [{code}]: {info}")

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

    # A truncated scrape looks exactly like a wiki that shrank, and the reap
    # below cannot tell them apart. Refuse rather than guess: the cost of a
    # false positive is a human re-running one command, the cost of a false
    # negative is destroying the committed corpus in an unattended PR.
    existing = {p.name for p in raw_dir.glob("*.wikitext")}
    if existing and len(by_filename) < len(existing) * REAP_FLOOR_RATIO:
        raise ScrapeError(
            f"scrape returned {len(by_filename)} pages against {len(existing)} "
            f"already in {raw_dir} — refusing to reap. Re-run the scrape; if the "
            f"wiki genuinely shrank this much, delete the stale files by hand."
        )

    raw_dir.mkdir(parents=True, exist_ok=True)

    for filename, content in by_filename.items():
        (raw_dir / filename).write_text(content, encoding="utf-8")

    for existing in raw_dir.glob("*.wikitext"):
        if existing.name not in by_filename:
            existing.unlink()

    return len(pages)
