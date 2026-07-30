from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from atlas.extract.manifest import (
    Manifest,
    RecordTemplateEntry,
    WikitableEntry,
    load_manifest,
)
from atlas.models import Kind


def _wikitable(**overrides) -> dict:
    entry = {
        "reader": "wikitable",
        "page": "Zodiacs",
        "system": "astrology",
        "kind": "upgrade",
        "id_prefix": "zodiac",
        "name_columns": ["Zodiac"],
        "effect_columns": ["Bonus 1"],
    }
    entry.update(overrides)
    return entry


def test_the_reader_field_picks_the_entry_type():
    manifest = Manifest.model_validate(
        {
            "pages": [
                _wikitable(),
                {
                    "reader": "record_template",
                    "page": "Minerals",
                    "template": "Minerals/Special_Minerals",
                    "system": "minerals",
                    "kind": "upgrade",
                    "id_prefix": "special-mineral",
                    "name_field": "mineral_name",
                    "effect_fields": ["mineral_base_boost"],
                },
            ]
        }
    )
    assert isinstance(manifest.pages[0], WikitableEntry)
    assert isinstance(manifest.pages[1], RecordTemplateEntry)
    assert manifest.pages[0].kind is Kind.UPGRADE


def test_an_unknown_reader_is_rejected():
    # A typo in `reader` must not silently drop the page from the sweep. The
    # discriminated union is the only thing that makes this a load error rather
    # than a page that quietly produces nothing.
    with pytest.raises(ValidationError):
        Manifest.model_validate({"pages": [_wikitable(reader="wikitble")]})


def test_an_unknown_field_is_rejected():
    # extra="forbid" turns a misremembered key (`effect_column` singular) into a
    # load error instead of a default that sweeps the wrong column.
    with pytest.raises(ValidationError):
        Manifest.model_validate({"pages": [_wikitable(effect_column="Bonus 1")]})


def test_empty_name_columns_is_rejected():
    with pytest.raises(ValidationError):
        Manifest.model_validate({"pages": [_wikitable(name_columns=[])]})


def test_per_level_column_requires_exactly_one_effect_column():
    # per_level describes one effect's scaling. With two effect columns there is
    # no way to say which one it belongs to, so the ambiguity is rejected at
    # load time rather than resolved by a coin flip in the reader.
    with pytest.raises(ValidationError):
        Manifest.model_validate(
            {
                "pages": [
                    _wikitable(
                        effect_columns=["Bonus 1", "Bonus 2"],
                        per_level_column="Increase per level",
                    )
                ]
            }
        )

    ok = Manifest.model_validate(
        {
            "pages": [
                _wikitable(
                    effect_columns=["Effect"],
                    per_level_column="Increase per level",
                )
            ]
        }
    )
    assert ok.pages[0].per_level_column == "Increase per level"


def test_name_prefix_defaults_to_absent():
    manifest = Manifest.model_validate({"pages": [_wikitable()]})
    assert manifest.pages[0].name_prefix is None
    prefixed = Manifest.model_validate(
        {"pages": [_wikitable(name_prefix="Tree Node")]}
    )
    assert prefixed.pages[0].name_prefix == "Tree Node"


def test_load_manifest_reads_a_file(tmp_path: Path):
    path = tmp_path / "sweep.yaml"
    path.write_text(yaml.safe_dump({"pages": [_wikitable()]}), encoding="utf-8")
    manifest = load_manifest(path)
    assert [p.page for p in manifest.pages] == ["Zodiacs"]


def test_a_missing_manifest_is_an_empty_one(tmp_path: Path):
    # The sweep is additive. A checkout without data/sweep.yaml must still
    # extract the four original pages, so absence is silent, not fatal.
    assert load_manifest(tmp_path / "nope.yaml").pages == []


@pytest.mark.parametrize(
    "payload",
    [
        "pages: !!python/object/apply:os.system ['echo pwned']\n",
        "pages: !!python/object/new:os.system ['echo pwned']\n",
        # FullLoader rejects the two above but accepts this one, handing back a
        # live reference to os.system. Without it the guard proves only "not
        # UnsafeLoader" rather than "SafeLoader".
        "pages: !!python/name:os.system\n",
    ],
)
def test_python_object_tags_are_rejected(tmp_path: Path, payload: str):
    # The manifest is a data file like any other and must never be able to
    # construct a Python object.
    path = tmp_path / "sweep.yaml"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(yaml.YAMLError):
        load_manifest(path)
