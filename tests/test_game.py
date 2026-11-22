import json

import pytest
import yaml

from atlas.cli import main
from atlas.game import (
    BUNDLE_DIR,
    CATALOG_REL_PATH,
    DEFAULT_INSTALL,
    ENGLISH_BUNDLE,
    STRINGS_REL_PATH,
    GameError,
    find_families,
    pair_tables,
    read_buildid,
    read_install,
    write_outputs,
)

SHARED = {
    11: {
        "m_Name": "menu Shared Data",
        "m_Entries": [
            {"m_Id": 1, "m_Key": "UNI_RELIC_NAME_0"},
            {"m_Id": 2, "m_Key": "UNI_RELIC_DESC_0"},
            # A key with no English text is simply absent from the output.
            {"m_Id": 3, "m_Key": "UNTRANSLATED"},
        ],
    },
    22: {
        "m_Name": "patch_note Shared Data",
        "m_Entries": [{"m_Id": 1, "m_Key": "PATCH_1"}],
    },
}


def _table(name, path_id, entries):
    return {
        "m_Name": name,
        "m_SharedData": {"m_FileID": 1, "m_PathID": path_id},
        "m_TableData": [
            {"m_Id": i, "m_Localized": text, "m_Metadata": {}} for i, text in entries
        ],
    }


MENU = _table("menu_en", 11, [(1, "Silver Coin"), (2, "Gain {0}x gold")])
PATCH = _table("patch_note_en", 22, [(1, "v1.0")])


def test_pair_tables_joins_ids_to_keys_per_table():
    # Entry ids repeat across tables; each table resolves through its own
    # shared data.
    assert pair_tables(SHARED, [MENU, PATCH]) == {
        "UNI_RELIC_NAME_0": "Silver Coin",
        "UNI_RELIC_DESC_0": "Gain {0}x gold",
        "PATCH_1": "v1.0",
    }


def test_pair_tables_rejects_unknown_shared_data():
    with pytest.raises(GameError, match="shared data 99"):
        pair_tables(SHARED, [_table("menu_en", 99, [(1, "x")])])


def test_pair_tables_rejects_entry_without_key():
    with pytest.raises(GameError, match="entry id 7"):
        pair_tables(SHARED, [_table("menu_en", 11, [(7, "x")])])


def test_pair_tables_rejects_key_in_two_tables():
    with pytest.raises(GameError, match="UNI_RELIC_NAME_0"):
        pair_tables(SHARED, [MENU, _table("menu_copy", 11, [(1, "again")])])


def test_find_families_pairs_name_and_desc_by_index():
    strings = {
        "UNI_RELIC_NAME_0": "Silver Coin",
        "UNI_RELIC_DESC_0": "a",
        "UNI_RELIC_NAME_2": "Third",
        "UNI_RELIC_DESC_2": "c",
        "UNI_RELIC_NAME_10": "Eleventh",
        "UNI_RELIC_DESC_10": "k",
        "UNI_RELIC_NAME_1": "No description",
        # NAME only: not a family.
        "INF_GEN_ITEM_NAME_0": "x",
        # DESC only: not a family.
        "HELP_UNI_TAROT_DESC_0": "y",
        # NAME and DESC under one prefix but never at the same index.
        "SPLIT_NAME_0": "n",
        "SPLIT_DESC_1": "d",
        # Not the numbered pattern.
        "SING_MILESTONES_NAME_SING_1": "z",
    }
    assert find_families(strings) == {
        "UNI_RELIC": [
            {"index": 0, "name": "Silver Coin", "desc": "a"},
            {"index": 1, "name": "No description", "desc": None},
            {"index": 2, "name": "Third", "desc": "c"},
            {"index": 10, "name": "Eleventh", "desc": "k"},
        ]
    }


def test_find_families_orders_prefixes():
    strings = {
        "B_NAME_0": "b",
        "B_DESC_0": "b",
        "A_NAME_0": "a",
        "A_DESC_0": "a",
    }
    assert list(find_families(strings)) == ["A", "B"]


def test_read_buildid_from_steam_manifest(tmp_path):
    install = tmp_path / "steamapps" / "common" / "Revolution Idle"
    install.mkdir(parents=True)
    assert read_buildid(install) is None
    (tmp_path / "steamapps" / "appmanifest_2763740.acf").write_text(
        '"AppState"\n{\n\t"appid"\t\t"2763740"\n\t"buildid"\t\t"123"\n}\n',
        encoding="utf-8",
    )
    assert read_buildid(install) == "123"


def test_read_install_rejects_missing_install(tmp_path):
    with pytest.raises(GameError, match="game install not found"):
        read_install(tmp_path / "nope")


def test_read_install_rejects_missing_bundle(tmp_path):
    with pytest.raises(GameError, match="localization bundle not found"):
        read_install(tmp_path)


def test_cli_reports_missing_install(tmp_path, capsys):
    code = main(["game", "--root", str(tmp_path), "--install", str(tmp_path / "x")])
    assert code == 1
    assert "game install not found" in capsys.readouterr().err
    assert not (tmp_path / "data").exists()


def test_write_outputs_is_stable_and_lf(tmp_path):
    dump = {
        "buildid": "1",
        "unity": "2022.3.62f3",
        "strings": {"B": "second\r\nline", "A": "Café {0}"},
    }
    families = find_families(
        {"UNI_RELIC_NAME_0": "Silver Coin", "UNI_RELIC_DESC_0": "Gain {0}x"}
    )
    write_outputs(tmp_path, dump, families)
    strings_bytes = (tmp_path / STRINGS_REL_PATH).read_bytes()
    catalog_bytes = (tmp_path / CATALOG_REL_PATH).read_bytes()

    for raw in (strings_bytes, catalog_bytes):
        assert b"\r\n" not in raw
        assert raw.endswith(b"\n")

    doc = json.loads(strings_bytes)
    assert doc == dump
    assert list(doc["strings"]) == ["A", "B"]

    catalog = yaml.safe_load(catalog_bytes)
    assert catalog["families"] == {
        "UNI_RELIC": [{"index": 0, "name": "Silver Coin", "desc": "Gain {0}x"}]
    }

    write_outputs(tmp_path, dump, families)
    assert (tmp_path / STRINGS_REL_PATH).read_bytes() == strings_bytes
    assert (tmp_path / CATALOG_REL_PATH).read_bytes() == catalog_bytes


@pytest.mark.skipif(
    not (DEFAULT_INSTALL / BUNDLE_DIR / ENGLISH_BUNDLE).is_file(),
    reason="Revolution Idle is not installed at the default Steam path",
)
def test_real_install(tmp_path):
    pytest.importorskip("UnityPy")
    assert main(["game", "--root", str(tmp_path)]) == 0
    strings = json.loads((tmp_path / STRINGS_REL_PATH).read_text(encoding="utf-8"))
    assert strings["strings"]["UNI_RELIC_NAME_0"] == "Silver Coin"
    catalog = yaml.safe_load((tmp_path / CATALOG_REL_PATH).read_text(encoding="utf-8"))
    relics = catalog["families"]["UNI_RELIC"]
    assert relics[0] == {
        "index": 0,
        "name": "Silver Coin",
        "desc": strings["strings"]["UNI_RELIC_DESC_0"],
    }
