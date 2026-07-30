from atlas.extract.manifest import RecordTemplateEntry
from atlas.extract.sweep import read_record_template

MINERALS = """{| class="wikitable center"
|-
{{Minerals/Special_Minerals
| icon = Special_mineral_red.png
| mineral_name = Red Gem
| description = A cool shining red gem. It will boost your VP gains!
| mineral_base_boost = 3.00x VP Gain
}}
{{Minerals/Special_Minerals
| icon = Special_mineral_blue.png
| mineral_name = Blue Gem
| description = Deep blue special gem is great for making mineral cost increase slower
| mineral_base_boost = Cost Increase is powered to ^0.99
}}
|-
{{Minerals/Special_Minerals
| icon = Special_mineral_pink.png
| mineral_name = Pink Gem
| description = Pink gem takes us back to astrology! Get zodiacs with better luck and quality!
| mineral_base_boost = Luck and Quality Bonus +0.05
}}
|}"""


def _entry(**overrides) -> RecordTemplateEntry:
    fields = {
        "reader": "record_template",
        "page": "Minerals",
        "template": "Minerals/Special_Minerals",
        "system": "minerals",
        "kind": "upgrade",
        "id_prefix": "special-mineral",
        "name_field": "mineral_name",
        "effect_fields": ["mineral_base_boost"],
    }
    fields.update(overrides)
    return RecordTemplateEntry.model_validate(fields)


def test_every_instance_of_the_template_is_read():
    records = read_record_template(MINERALS, _entry())
    assert [r.name for r in records] == ["Red Gem", "Blue Gem", "Pink Gem"]


def test_the_effect_field_is_read_and_trimmed():
    records = read_record_template(MINERALS, _entry())
    assert records[1].effects == ["Cost Increase is powered to ^0.99"]


def test_fields_the_entry_does_not_name_are_ignored():
    # `description` is flavour text, not an effect. Sweeping it would put prose
    # like "Pink gem takes us back to astrology!" through the resolver, where
    # "astrology" is a declared system name and a wrong edge is the result.
    records = read_record_template(MINERALS, _entry())
    assert all("astrology" not in effect for r in records for effect in r.effects)


def test_a_template_the_page_does_not_use_yields_nothing():
    assert read_record_template(MINERALS, _entry(template="Minerals/Ores")) == []


def test_an_instance_missing_the_name_field_is_skipped():
    page = MINERALS.replace("| mineral_name = Red Gem\n", "")
    records = read_record_template(page, _entry())
    assert [r.name for r in records] == ["Blue Gem", "Pink Gem"]


def test_an_instance_with_no_effect_field_is_skipped():
    page = MINERALS.replace("| mineral_base_boost = 3.00x VP Gain\n", "")
    records = read_record_template(page, _entry())
    assert [r.name for r in records] == ["Blue Gem", "Pink Gem"]


def test_a_nested_template_does_not_end_the_instance():
    # An effect containing {{Keyword|vp|VP}} has its own braces. A scanner that
    # stopped at the first "}}" would truncate the record and then read the rest
    # of the instance as page text.
    page = MINERALS.replace(
        "| mineral_base_boost = 3.00x VP Gain",
        "| mineral_base_boost = 3.00x {{Keyword|vp|VP}} Gain",
    )
    records = read_record_template(page, _entry())
    assert records[0].effects == ["3.00x VP Gain"]
    assert [r.name for r in records] == ["Red Gem", "Blue Gem", "Pink Gem"]


def test_an_inline_instance_is_read_too():
    # tarot.py can rely on its templates closing on their own line; this reader
    # cannot, because a template written inline would otherwise sweep zero
    # records and Task 10 reports zero records as a warning — a quiet failure
    # that reads like "the page has no data".
    page = "{{Minerals/Special_Minerals|mineral_name=Cyan Gem|mineral_base_boost=x2 Luck}}"
    records = read_record_template(page, _entry())
    assert [(r.name, r.effects) for r in records] == [("Cyan Gem", ["x2 Luck"])]


def test_a_longer_template_name_is_not_a_match():
    # "{{Minerals/Special_MineralsV2" starts with the name being looked for. A
    # plain prefix search would read its fields as if they were this template's.
    page = MINERALS.replace(
        "{{Minerals/Special_Minerals\n| icon = Special_mineral_red.png",
        "{{Minerals/Special_MineralsV2\n| icon = Special_mineral_red.png",
    )
    records = read_record_template(page, _entry())
    assert [r.name for r in records] == ["Blue Gem", "Pink Gem"]


def test_an_unterminated_instance_does_not_hang_or_invent_a_record():
    # Both fields are present so the only reason to get [] is the depth guard
    # detecting that the template never closed — not the name/effects guard.
    page = "{{Minerals/Special_Minerals\n| mineral_name = Broken Gem\n| mineral_base_boost = x2 VP Gain\n"
    assert read_record_template(page, _entry()) == []


def test_the_per_level_field_is_kept_off_the_effect_text():
    page = MINERALS.replace(
        "| mineral_base_boost = 3.00x VP Gain",
        "| mineral_base_boost = 3.00x VP Gain\n| scaling = +0.25",
    )
    records = read_record_template(page, _entry(per_level_field="scaling"))
    assert records[0].effects == ["3.00x VP Gain"]
    assert records[0].per_level == "+0.25"
