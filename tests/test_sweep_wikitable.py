from atlas.extract.manifest import WikitableEntry
from atlas.extract.sweep import read_wikitable

# Verbatim from data/raw/Zodiacs.wikitext. Exercises three things at once:
# `!!`-joined headers carrying attributes, a `|+` caption line, and cells whose
# entire content is a template.
ZODIACS = """{| class="wikitable sortable"
|+ Zodiac Types and Bonus
|-
! class="sortinitialorder" | Zodiac !! class="unsortable" | Icon !! Element !! Season !! class="unsortable" | Bonus 1 !! class="unsortable" | Bonus 2 !! class="unsortable" | Bonus 3 !! class="unsortable" | Bonus 4
|-
| data-sort-value=1 | {{ZodiacBadge|Aries}}
| [[File:Aries.png|25px|center|link=Zodiacs]]
| data-sort-value=11 | {{ZodiacBadge|Fire}}
| data-sort-value=1 | Spring
| Mult Gain x
| Promotions Power x
| Ascension Power x
| Common Exp. Power x
|-
| data-sort-value=11 | {{ZodiacBadge|Taurus}}
| [[File:Tau.png|25px|center|link=Zodiacs]]
| data-sort-value=21 | {{ZodiacBadge|Earth}}
| data-sort-value=1 | Spring
| IP Gain ^
| Infinity Gain x
| Gen. Exponent x
| Mult/bought Gen x
|}"""

# Verbatim from data/raw/Trials.wikitext. Row 1 carries rowspan="6"; rows 2 and
# 3 are one cell short because of it.
TRIALS = """{| class="wikitable" style="text-align:center;  font-size: 1rem"
!Trial
!Goal
!Handicap
!Reward
|-
|Easy Trial 1
| rowspan="6" |Reach Infinity
|You can only buy the first 6 colors
|x1.4 to zodiac quality
|-
|Easy Trial 2
|You can't buy promotion 3 and 4
|Unlocks Trials exp factor
|-
|Easy Trial 3
|Common exponent is multiplied by 0.6
|Common exponent multiplied by 1.05
|}"""

# Verbatim from data/raw/Plague.wikitext. A colspan header row above the real
# one, and a second colspan header row in the middle of the data.
PLAGUE = """{| class="wikitable mw-collapsible"
! colspan="4" |Plague Stages
|-
!Stage
!Name
!Population
!PlG Reward
|-
! colspan="4" |Level 1 Plague Stages - Houses (1-x)
|-
|1-1
|Tent
|5
|1 PlG
|-
|1-2
|Shack
|7
|2 PlG
|}"""

# Verbatim from data/raw/Dilation_Tree.wikitext. The caption row comes BEFORE
# the header row, and the rowspan column is the one the name is built from.
DILATION = """{| class="wikitable mw-collapsible mw-collapsed" style="text-align:center; width: 60%; font-size: 1rem"
|colspan="4"|'''Dilation Tree Upgrades (DTU)'''
|-
!Axis
!Index
!Effect
!Increase per level
|-
|Center
|1
|Each unspent {{Keyword|ap|AP}} boosts {{Keyword|dp|DP}} gain by 0.1%
| +0.05%
|-
| rowspan="4" |Top
|1
|Dilation Upgrade 1 is 30% stronger
| +15%
|-
|2
|Eternities ^2.00 boost {{Keyword|dp|DP}} gain
| +^0.25
|}"""


def _entry(**overrides) -> WikitableEntry:
    fields = {
        "reader": "wikitable",
        "page": "Zodiacs",
        "system": "astrology",
        "kind": "upgrade",
        "id_prefix": "zodiac",
        "name_columns": ["Zodiac"],
        "effect_columns": ["Bonus 1", "Bonus 2", "Bonus 3", "Bonus 4"],
    }
    fields.update(overrides)
    return WikitableEntry.model_validate(fields)


def test_a_templated_name_cell_reads_through_its_attributes():
    records = read_wikitable(ZODIACS, _entry())
    assert [r.name for r in records] == ["Aries", "Taurus"]


def test_every_effect_column_becomes_its_own_effect():
    # Four columns, four effects — not one concatenated string. A zodiac really
    # does have four independent bonuses, which is the same reason `effects` is
    # a list on the model.
    records = read_wikitable(ZODIACS, _entry())
    assert records[0].effects == [
        "Mult Gain x",
        "Promotions Power x",
        "Ascension Power x",
        "Common Exp. Power x",
    ]


def test_a_caption_line_is_not_a_record():
    # `|+ Zodiac Types and Bonus` starts with a pipe like a data cell does. If
    # it were read as one, the first record would be named "Zodiac Types and
    # Bonus" and every later row would shift by one.
    records = read_wikitable(ZODIACS, _entry())
    assert len(records) == 2


def test_a_rowspan_cell_carries_into_the_rows_below_it():
    # Rows 2 and 3 have three cells against four headers. Skipping them loses
    # two thirds of this table; carrying "Reach Infinity" down is what the
    # rendered HTML page actually shows.
    records = read_wikitable(
        TRIALS,
        _entry(
            page="Trials",
            system="trials",
            id_prefix="trial",
            name_columns=["Trial"],
            effect_columns=["Reward"],
        ),
    )
    assert [r.name for r in records] == [
        "Easy Trial 1",
        "Easy Trial 2",
        "Easy Trial 3",
    ]
    assert records[2].effects == ["Common exponent multiplied by 1.05"]


def test_a_colspan_header_cell_is_not_a_column():
    # `! colspan="4" |Plague Stages` is a caption. Counted as a column the table
    # is five wide, every four-cell row is rejected, and the page sweeps empty.
    records = read_wikitable(
        PLAGUE,
        _entry(
            page="Plague",
            system="plague",
            id_prefix="plague",
            name_columns=["Name"],
            effect_columns=["PlG Reward"],
        ),
    )
    assert [(r.name, r.effects) for r in records] == [
        ("Tent", ["1 PlG"]),
        ("Shack", ["2 PlG"]),
    ]


def test_a_colspan_row_in_the_middle_of_the_data_is_not_a_record():
    # The same Plague table repeats a colspan header between data rows. Read as
    # data it is a one-cell row; read as a header it would redefine the columns.
    records = read_wikitable(
        PLAGUE,
        _entry(
            page="Plague",
            system="plague",
            id_prefix="plague",
            name_columns=["Name"],
            effect_columns=["PlG Reward"],
        ),
    )
    assert all("Level 1" not in r.name for r in records)


def test_headers_are_found_when_a_caption_row_precedes_them():
    # Dilation_Tree opens with `|colspan="4"|'''...'''` — a data-shaped line
    # above the header row. Treating "the first pipe line" as data and giving up
    # on headers after it finds no columns at all here.
    records = read_wikitable(
        DILATION,
        _entry(
            page="Dilation_Tree",
            system="eternity",
            kind="tree-node",
            id_prefix="dilation-node",
            name_columns=["Axis", "Index"],
            effect_columns=["Effect"],
            per_level_column="Increase per level",
        ),
    )
    # Two name columns joined by a space — neither Axis nor Index alone
    # identifies a row.
    assert [r.name for r in records] == ["Center 1", "Top 1", "Top 2"]


def test_the_per_level_column_is_kept_off_the_effect_text():
    records = read_wikitable(
        DILATION,
        _entry(
            page="Dilation_Tree",
            system="eternity",
            kind="tree-node",
            id_prefix="dilation-node",
            name_columns=["Axis", "Index"],
            effect_columns=["Effect"],
            per_level_column="Increase per level",
        ),
    )
    assert records[0].effects == ["Each unspent AP boosts DP gain by 0.1%"]
    assert records[0].per_level == "+0.05%"


def test_a_table_without_the_name_column_is_skipped():
    # Zodiacs has six tables. An entry naming a column no table has must sweep
    # nothing rather than fall back to column 0.
    assert read_wikitable(ZODIACS, _entry(name_columns=["Constellation"])) == []


def test_a_table_without_any_effect_column_is_skipped():
    assert read_wikitable(ZODIACS, _entry(effect_columns=["Penalty"])) == []


def test_every_matching_table_on_the_page_is_swept():
    # Trials repeats the same four columns for each difficulty tier. Reading
    # only the first table would sweep the easy trials and silently drop the
    # rest, so all matching tables are read.
    page = TRIALS + "\n\n" + TRIALS.replace("Easy Trial", "Hard Trial")
    records = read_wikitable(
        page,
        _entry(
            page="Trials",
            system="trials",
            id_prefix="trial",
            name_columns=["Trial"],
            effect_columns=["Reward"],
        ),
    )
    assert [r.name for r in records][:4] == [
        "Easy Trial 1",
        "Easy Trial 2",
        "Easy Trial 3",
        "Hard Trial 1",
    ]


def test_a_row_whose_effect_cells_are_all_blank_is_not_a_record():
    # A named row with nothing in any effect column produces no edges and no
    # effect text, so it would be a node asserting only that a name exists.
    page = TRIALS.replace("|x1.4 to zodiac quality", "|")
    records = read_wikitable(
        page,
        _entry(
            page="Trials",
            system="trials",
            id_prefix="trial",
            name_columns=["Trial"],
            effect_columns=["Reward"],
        ),
    )
    assert "Easy Trial 1" not in [r.name for r in records]


def test_a_table_with_the_wanted_column_twice_is_skipped():
    # Verbatim shape from data/raw/Minerals.wikitext, which lays two independent
    # upgrade tables side by side inside one wikitable. Read positionally, only
    # the right-hand half survives and the left half vanishes with no sign.
    page = """{| class="wikitable"
!Upgrade
!Effects
!Upgrade
!Effects
|-
|Left One
|Boosts Gold gain
|Right One
|Boosts Luck
|}"""
    records = read_wikitable(
        page,
        _entry(
            page="Minerals",
            system="minerals",
            id_prefix="mineral-upgrade",
            name_columns=["Upgrade"],
            effect_columns=["Effects"],
        ),
    )
    assert records == []


def test_a_cell_continued_on_the_next_line_is_kept_whole():
    # elements.py already had to handle this: a long effect is wrapped across
    # source lines with no leading pipe. Dropping the continuation truncates the
    # effect text mid-sentence.
    page = TRIALS.replace(
        "|x1.4 to zodiac quality",
        "|x1.4 to zodiac quality\nand x2 to luck",
    )
    records = read_wikitable(
        page,
        _entry(
            page="Trials",
            system="trials",
            id_prefix="trial",
            name_columns=["Trial"],
            effect_columns=["Reward"],
        ),
    )
    assert records[0].effects == ["x1.4 to zodiac quality and x2 to luck"]


def test_a_line_break_inside_a_cell_becomes_a_space():
    # Verbatim from data/raw/Singularity.wikitext. plain_text strips <br/> to
    # nothing, which welds the two sentences into "Unlock Milestones TabSMS
    # Factor is locked at 0" — a word that exists in no game and matches no
    # vocabulary term.
    page = """{| class="wikitable"
|+Singularity Milestones
!Name
! width=120px| Requirement
!Reward
|-
|First Collapse
|1 Singularity
|Unlock Milestones Tab<br/>SMS Factor is locked at 0
|}"""
    records = read_wikitable(
        page,
        _entry(
            page="Singularity",
            system="singularity",
            id_prefix="singularity",
            name_columns=["Name"],
            effect_columns=["Reward"],
        ),
    )
    assert records[0].effects == [
        "Unlock Milestones Tab SMS Factor is locked at 0"
    ]


def test_an_effect_cell_with_no_letters_is_not_an_effect():
    # Verbatim from data/raw/Plague.wikitext: the ER Upgrades table writes "<=="
    # in the Effect column to mean "see the Name column". Swept as-is it becomes
    # three nodes whose only stated effect is an arrow. Letter-free text can
    # also never carry a resolvable reference, so dropping it costs nothing.
    page = """{| class="wikitable mw-collapsible"
! colspan="6" |ER Upgrades
|-
!#
!Name
!Effect
!Effect Scaling
!Base Cost
!Cost Scaling
|-
|1
|Base Spread Power
|<==
| + 0.025/level
|1000
|x2/level
|-
|4
|Conversion Rate
|Increases PlP to ERP conversion rate
| + 0.5%/level
|1000
|x2/level
|}"""
    records = read_wikitable(
        page,
        _entry(
            page="Plague",
            system="plague",
            id_prefix="plague",
            name_columns=["Name"],
            effect_columns=["Effect"],
        ),
    )
    assert [r.name for r in records] == ["Conversion Rate"]
