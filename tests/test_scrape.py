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
