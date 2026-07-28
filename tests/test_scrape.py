import httpx
import pytest

from atlas.scrape import USER_AGENT, ScrapeError, fetch_pages, write_raw

PAGE_ONE = {
    "query": {
        "pages": {
            "1": {
                "title": "Relics",
                "revisions": [{"slots": {"main": {"*": "relic text"}}}],
            }
        }
    },
    "continue": {"gapcontinue": "Singularity", "continue": "gapcontinue||"},
}

PAGE_TWO = {
    "query": {
        "pages": {
            "2": {
                "title": "Minerals/Refine Tree",
                "revisions": [{"slots": {"main": {"*": "refine text"}}}],
            }
        }
    }
}


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_sends_descriptive_user_agent():
    seen = {}

    def handler(request):
        seen["ua"] = request.headers["user-agent"]
        return httpx.Response(200, json=PAGE_TWO)

    fetch_pages(_client(handler))
    assert seen["ua"] == USER_AGENT
    assert "revolution-idle-atlas" in USER_AGENT


def test_follows_continuation():
    responses = [PAGE_ONE, PAGE_TWO]

    def handler(request):
        return httpx.Response(200, json=responses.pop(0))

    pages = fetch_pages(_client(handler))
    assert pages == {"Relics": "relic text", "Minerals/Refine Tree": "refine text"}


def test_non_200_raises():
    def handler(request):
        return httpx.Response(403, text="forbidden")

    with pytest.raises(ScrapeError, match="403"):
        fetch_pages(_client(handler))


def test_empty_result_raises():
    def handler(request):
        return httpx.Response(200, json={"query": {"pages": {}}})

    with pytest.raises(ScrapeError, match="no pages"):
        fetch_pages(_client(handler))


def test_api_level_error_with_http_200_raises():
    # MediaWiki answers readonly/maxlag with HTTP 200 and an error body. Without
    # an explicit check the loop exits normally with a partial page set.
    def handler(request):
        return httpx.Response(
            200,
            json={"error": {"code": "readonly", "info": "The wiki is in read-only mode."}},
        )

    with pytest.raises(ScrapeError, match="readonly"):
        fetch_pages(_client(handler))


def test_api_error_after_a_successful_page_still_raises():
    # The dangerous shape: page 1 succeeds, page 2 errors. The result is a
    # non-empty dict, so the `if not pages` guard passes it straight through.
    responses = [PAGE_ONE, {"error": {"code": "maxlag", "info": "Waiting for a database"}}]

    def handler(request):
        return httpx.Response(200, json=responses.pop(0))

    with pytest.raises(ScrapeError, match="maxlag"):
        fetch_pages(_client(handler))


def _fill_raw(raw_dir, count: int) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    for i in range(count):
        (raw_dir / f"Page{i}.wikitext").write_text("old", encoding="utf-8")


def test_write_raw_refuses_a_scrape_below_the_reap_floor(tmp_path):
    raw = tmp_path / "raw"
    _fill_raw(raw, 10)
    # 7 of 10 is below the 80% floor.
    pages = {f"Page{i}": "new" for i in range(7)}

    with pytest.raises(ScrapeError, match="refusing to reap"):
        write_raw(pages, raw)

    # Nothing was written and nothing was reaped.
    assert len(list(raw.glob("*.wikitext"))) == 10
    assert (raw / "Page9.wikitext").read_text() == "old"


def test_write_raw_proceeds_exactly_at_the_reap_floor(tmp_path):
    raw = tmp_path / "raw"
    _fill_raw(raw, 10)
    # 8 of 10 is exactly the floor, which must be allowed through.
    pages = {f"Page{i}": "new" for i in range(8)}

    assert write_raw(pages, raw) == 8
    assert len(list(raw.glob("*.wikitext"))) == 8
    assert (raw / "Page0.wikitext").read_text() == "new"
    assert not (raw / "Page9.wikitext").exists()


def test_write_raw_reap_floor_ignores_an_empty_directory(tmp_path):
    # A first-ever scrape has nothing on disk to compare against.
    raw = tmp_path / "raw"
    assert write_raw({"Relics": "text"}, raw) == 1


def test_write_raw_flattens_subpage_titles(tmp_path):
    count = write_raw({"Minerals/Refine Tree": "text"}, tmp_path)
    assert count == 1
    assert (tmp_path / "Minerals__Refine_Tree.wikitext").read_text() == "text"


def test_write_raw_removes_stale_files(tmp_path):
    (tmp_path / "Deleted.wikitext").write_text("old")
    write_raw({"Relics": "text"}, tmp_path)
    assert not (tmp_path / "Deleted.wikitext").exists()
    assert (tmp_path / "Relics.wikitext").exists()


def test_write_raw_refuses_empty_mapping(tmp_path):
    with pytest.raises(ScrapeError, match="refusing"):
        write_raw({}, tmp_path)


def test_caller_supplied_user_agent_is_respected():
    seen = {}

    def handler(request):
        seen["ua"] = request.headers["user-agent"]
        return httpx.Response(200, json=PAGE_TWO)

    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        headers={"User-Agent": "my-deliberate-ua/9"},
    )
    fetch_pages(client)
    assert seen["ua"] == "my-deliberate-ua/9"


def test_write_raw_leaves_disk_untouched_when_a_title_is_unusable(tmp_path):
    # Filename derivation must happen before any disk mutation, so a bad title
    # cannot leave data/raw/ half-written with stale files not yet reaped.
    (tmp_path / "Existing.wikitext").write_text("original")
    pages = {"Relics": "new text", "Bad\x00Title": "boom"}

    with pytest.raises(ScrapeError, match="unusable filename"):
        write_raw(pages, tmp_path)

    assert (tmp_path / "Existing.wikitext").read_text() == "original"
    assert not (tmp_path / "Relics.wikitext").exists()


def test_write_raw_normalises_spaces_via_raw_filename(tmp_path):
    count = write_raw({"Attacks Strategy": "text"}, tmp_path)
    assert count == 1
    assert (tmp_path / "Attacks_Strategy.wikitext").read_text() == "text"


def test_path_traversal_stays_inside_raw_dir(tmp_path):
    # A hostile wiki title like "../../etc/passwd" must not write outside tmp_path.
    # raw_filename replaces "/" with "__", so "../.." becomes "..__.."; the result
    # is a flat filename with no directory separator, which Path.__truediv__ keeps
    # inside raw_dir.
    hostile_title = "../../etc/passwd"
    count = write_raw({hostile_title: "malicious"}, tmp_path)
    assert count == 1
    written = list(tmp_path.glob("*.wikitext"))
    assert len(written) == 1
    # The file must be directly inside tmp_path, not a parent directory.
    assert written[0].parent == tmp_path
