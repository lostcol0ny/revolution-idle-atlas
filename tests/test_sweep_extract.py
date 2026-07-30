from pathlib import Path

import pytest

from atlas.extract import ExtractError, run_all
from atlas.extract.manifest import Manifest
from atlas.extract.refs import Vocabulary
from atlas.extract.sweep import extract
from atlas.models import EdgeConfidence, Kind, NodeConfidence

TABLE = """{| class="wikitable"
!Name
!Effect
|-
|Red Gem
|3.00x Attack Power gain
|-
|Blue Gem
|Boosts Gold gain
|}"""


def _manifest(**overrides) -> Manifest:
    entry = {
        "reader": "wikitable",
        "page": "Minerals",
        "system": "minerals",
        "kind": "upgrade",
        "id_prefix": "special-mineral",
        "name_columns": ["Name"],
        "effect_columns": ["Effect"],
    }
    entry.update(overrides)
    return Manifest.model_validate({"pages": [entry]})


def _raw(tmp_path: Path, name: str = "Minerals.wikitext", body: str = TABLE) -> Path:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / name).write_text(body, encoding="utf-8")
    return raw_dir


# The curated nodes these tests resolve against. Built here rather than read
# from data/relationships.yaml so the test does not fail when curation changes.
VOCABULARY = Vocabulary(
    [("Attack Power", "attack-power"), ("Gold", "gold")]
)


def test_a_swept_node_carries_the_manifest_metadata(tmp_path: Path):
    result = extract(_raw(tmp_path), _manifest(), VOCABULARY)

    node = result.nodes[0]
    assert node.id == "special-mineral-red-gem"
    assert node.name == "Red Gem"
    assert node.system == "minerals"
    assert node.kind is Kind.UPGRADE
    # The manifest's `page` is the wiki TITLE, so it doubles as node.wiki and
    # rawcheck can resolve it back to the file it was read from.
    assert node.wiki == "Minerals"
    assert node.confidence is NodeConfidence.PROVISIONAL
    assert [e.text for e in node.effects] == ["3.00x Attack Power gain"]


def test_a_swept_edge_is_uncertain(tmp_path: Path):
    # This is the load-bearing assertion of the whole sweep: prose matching is
    # weaker evidence than a table cell, and a wrong edge is worse than a
    # missing one. Without it the sweep asserts hundreds of guesses as fact.
    result = extract(_raw(tmp_path), _manifest(), VOCABULARY)
    assert [e.confidence for e in result.edges] == [
        EdgeConfidence.UNCERTAIN,
        EdgeConfidence.UNCERTAIN,
    ]


def test_a_swept_edge_runs_from_the_swept_node_to_what_it_boosts(tmp_path: Path):
    # Direction is flow, not grammar: `from` is the actor, `to` is what it acts
    # on. A Red Gem boosts Attack Power, so the edge leaves the gem.
    result = extract(_raw(tmp_path), _manifest(), VOCABULARY)
    assert [(e.from_, e.to, e.rel.value) for e in result.edges] == [
        ("special-mineral-red-gem", "attack-power", "boosts"),
        ("special-mineral-blue-gem", "gold", "boosts"),
    ]


def test_the_source_names_the_page_it_was_read_from(tmp_path: Path):
    result = extract(_raw(tmp_path), _manifest(), VOCABULARY)
    assert {e.source for e in result.edges} == {"wiki:Minerals"}


def test_a_self_reference_is_not_an_edge(tmp_path: Path):
    # "Red Gem doubles Red Gem" is how the wiki writes a self-scaling effect.
    # validate_dataset rejects a self-edge as an error, so emitting one here
    # would turn a normal wiki phrasing into a broken build.
    #
    # The fixture gives Blue Gem a valid effect (Gold) so the resolver runs and
    # produces at least one edge. Asserting the full edge list by value proves
    # in one assertion that the resolver ran (the Gold edge is present) and that
    # the self-edge was dropped (it is absent) — a vacuous assertion over an
    # empty list would survive a completely broken extract with no edges at all.
    body = TABLE.replace("|3.00x Attack Power gain", "|Red Gem gain is doubled")
    vocabulary = VOCABULARY.with_terms([("Red Gem", "special-mineral-red-gem")])
    result = extract(
        _raw(tmp_path, body=body),
        _manifest(),
        vocabulary,
    )
    # Exactly one edge: Blue Gem -> Gold. The Red Gem -> Red Gem self-edge is
    # dropped. If extract returns no edges at all the assertion also fails,
    # which prevents a vacuous pass from a broken implementation.
    assert [(e.from_, e.to) for e in result.edges] == [
        ("special-mineral-blue-gem", "gold"),
    ]


def test_a_manifest_page_with_no_raw_file_is_a_warning(tmp_path: Path):
    result = extract(_raw(tmp_path), _manifest(page="Nonexistent"), VOCABULARY)
    assert result.nodes == []
    assert len(result.warnings) == 1
    assert "Nonexistent" in result.warnings[0]


def test_a_manifest_page_that_yields_no_records_is_a_warning(tmp_path: Path):
    # The whole point of the warning channel. A wrong column name in the
    # manifest is a guess that did not pay off, not a broken build.
    result = extract(_raw(tmp_path), _manifest(name_columns=["Title"]), VOCABULARY)
    assert result.nodes == []
    assert len(result.warnings) == 1
    assert "Minerals" in result.warnings[0]


def test_a_page_that_yields_records_produces_no_warning(tmp_path: Path):
    result = extract(_raw(tmp_path), _manifest(), VOCABULARY)
    # Two nodes must have been produced, or the no-warning assertion proves nothing:
    # a silently empty extract also has no warnings.
    assert len(result.nodes) == 2
    assert result.warnings == []


def test_per_level_reaches_the_effect(tmp_path: Path):
    body = """{| class="wikitable"
!Name
!Effect
!Increase per level
|-
|Red Gem
|Boosts Gold gain
| +0.05%
|}"""
    result = extract(
        _raw(tmp_path, body=body),
        _manifest(per_level_column="Increase per level"),
        VOCABULARY,
    )
    effect = result.nodes[0].effects[0]
    assert effect.per_level == "+0.05%"
    # derive_op reads the leading operator off per_level, exactly as relics.py
    # does with its coefficient column.
    assert effect.op is not None


def test_the_record_template_reader_is_dispatched_too(tmp_path: Path):
    body = "{{Gem|gem_name=Cyan Gem|gem_effect=Boosts Gold gain}}"
    manifest = Manifest.model_validate(
        {
            "pages": [
                {
                    "reader": "record_template",
                    "page": "Minerals",
                    "template": "Gem",
                    "system": "minerals",
                    "kind": "upgrade",
                    "id_prefix": "special-mineral",
                    "name_field": "gem_name",
                    "effect_fields": ["gem_effect"],
                }
            ]
        }
    )
    result = extract(_raw(tmp_path, body=body), manifest, VOCABULARY)
    assert [n.id for n in result.nodes] == ["special-mineral-cyan-gem"]


def test_name_prefix_reaches_the_name_and_the_id(tmp_path: Path):
    # Singularity's tree table names its rows "1", "2", "3.1". Without the
    # prefix the node is called "1" and its id says nothing about what it is.
    result = extract(_raw(tmp_path), _manifest(name_prefix="Gem"), VOCABULARY)
    assert (result.nodes[0].id, result.nodes[0].name) == (
        "special-mineral-gem-red-gem",
        "Gem Red Gem",
    )


def test_two_entries_minting_the_same_id_is_a_warning(tmp_path: Path):
    # Minerals reads its ten Special Minerals twice — once as templates, once in
    # a later table with different effect wording. to_yaml's node dedup is
    # first-wins, so the second reading would disappear with nothing to say it
    # had. This is the only place that can still see both.
    manifest = Manifest.model_validate(
        {"pages": [_manifest().pages[0].model_dump(), _manifest().pages[0].model_dump()]}
    )
    result = extract(_raw(tmp_path), manifest, VOCABULARY)
    assert [n.id for n in result.nodes] == [
        "special-mineral-red-gem",
        "special-mineral-blue-gem",
    ]
    assert len(result.warnings) == 2
    assert "already" in result.warnings[0]


def test_an_empty_manifest_sweeps_nothing_and_warns_about_nothing(tmp_path: Path):
    result = extract(_raw(tmp_path), Manifest(), VOCABULARY)
    assert (result.nodes, result.edges, result.warnings) == ([], [], [])


def test_run_all_does_not_raise_when_only_the_sweep_is_empty(tmp_path: Path):
    # The four hand-written parsers still raise on zero nodes. The sweep must
    # not, or one bad manifest guess blocks every build and the CI artifact
    # guard with it.
    raw_dir = Path("data/raw")
    result = run_all(
        raw_dir, Vocabulary.EMPTY, manifest=_manifest(page="Nonexistent")
    )
    assert result.nodes  # the four parsers still ran
    assert any("Nonexistent" in w for w in result.warnings)


def test_run_all_still_raises_when_a_real_parser_is_empty(tmp_path: Path):
    # Pinning the asymmetry from the other side. Without this test the sweep's
    # warning behaviour could be applied to the four parsers too and the suite
    # would stay green.
    #
    # Files must exist so the parsers try to read them rather than raising
    # FileNotFoundError before returning. An empty file produces zero nodes,
    # which is the condition run_all is meant to hard-fail on.
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    for name in ("Relics.wikitext", "Minerals__Refine_Tree.wikitext", "Tarot.wikitext", "Elements.wikitext"):
        (raw_dir / name).write_text("", encoding="utf-8")
    with pytest.raises(ExtractError):
        run_all(raw_dir, Vocabulary.EMPTY, manifest=Manifest())
