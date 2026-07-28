from atlas.models import Dataset, Node
from atlas.rawcheck import check_against_raw, raw_filename


def _node(node_id: str, wiki: str | None, confidence: str = "documented") -> Node:
    return Node(
        id=node_id, name=node_id, system="unity", kind="relic",
        wiki=wiki, confidence=confidence, line=3,
    )


def test_raw_filename_flattens_subpages():
    assert raw_filename("Minerals/Refine_Tree") == "Minerals__Refine_Tree.wikitext"


def test_raw_filename_drops_section_anchor():
    assert raw_filename("Relics#Relic_3") == "Relics.wikitext"


def test_raw_filename_handles_slash_and_anchor():
    assert raw_filename("Minerals/Refine_Tree#Section") == "Minerals__Refine_Tree.wikitext"


def test_raw_filename_normalises_spaces_to_underscores():
    assert raw_filename("Attacks Strategy") == "Attacks_Strategy.wikitext"


def test_raw_filename_spaced_and_underscored_titles_agree():
    # MediaWiki treats spaces and underscores as the same character in a title.
    # The scraper and rawcheck must therefore derive one filename for both forms,
    # or a dataset author writing "Attacks Strategy" gets a spurious missing-page
    # warning against a file the scraper wrote as "Attacks_Strategy.wikitext".
    assert raw_filename("Attacks Strategy") == raw_filename("Attacks_Strategy")
    assert raw_filename("Minerals/Refine Tree") == raw_filename("Minerals/Refine_Tree")


def test_spaced_wiki_reference_matches_scraped_file(tmp_path):
    (tmp_path / "Attacks_Strategy.wikitext").write_text("stuff")
    ds = Dataset(nodes=[_node("atk", "Attacks Strategy")], edges=[])
    assert check_against_raw(ds, tmp_path) == []


def test_missing_raw_dir_yields_no_warnings(tmp_path):
    ds = Dataset(nodes=[_node("a", "Relics")], edges=[])
    assert check_against_raw(ds, tmp_path / "absent") == []


def test_new_content_page_without_provisional_warns(tmp_path):
    (tmp_path / "Singularity.wikitext").write_text("{{New Content}}\nSingularity is...")
    ds = Dataset(nodes=[_node("singularity", "Singularity", "documented")], edges=[])
    problems = check_against_raw(ds, tmp_path)
    assert len(problems) == 1
    assert problems[0].severity == "warning"
    assert "{{New Content}}" in problems[0].message
    assert problems[0].line == 3


def test_new_content_page_with_provisional_is_quiet(tmp_path):
    (tmp_path / "Singularity.wikitext").write_text("{{New Content}}\nSingularity is...")
    ds = Dataset(nodes=[_node("singularity", "Singularity", "provisional")], edges=[])
    assert check_against_raw(ds, tmp_path) == []


def test_missing_page_warns(tmp_path):
    (tmp_path / "Relics.wikitext").write_text("stuff")
    ds = Dataset(nodes=[_node("gone", "DeletedPage")], edges=[])
    problems = check_against_raw(ds, tmp_path)
    assert len(problems) == 1
    assert "DeletedPage" in problems[0].message
    assert "no longer exists" in problems[0].message


def test_node_without_wiki_is_skipped(tmp_path):
    (tmp_path / "Relics.wikitext").write_text("stuff")
    ds = Dataset(nodes=[_node("stub", None, "unknown")], edges=[])
    assert check_against_raw(ds, tmp_path) == []


def test_node_with_empty_wiki_is_skipped(tmp_path):
    (tmp_path / "Relics.wikitext").write_text("stuff")
    ds = Dataset(nodes=[_node("stub", "", "unknown")], edges=[])
    assert check_against_raw(ds, tmp_path) == []
