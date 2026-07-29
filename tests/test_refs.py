from atlas.extract.refs import (
    Reference,
    derive_op,
    is_uncertain,
    normalise_space,
    plain_text,
    resolve,
    slugify,
    split_fields,
    template_fields,
)
from atlas.models import Op


def test_slugify_and_normalise_space():
    assert slugify("King of Wands") == "king-of-wands"
    assert slugify("Outdated \"Nice\" Gadget") == "outdated-nice-gadget"
    assert normalise_space("Copper Bunny \nStatuette") == "Copper Bunny Statuette"


def test_plain_text_unwraps_piped_and_plain_links():
    assert plain_text("Adds base to [[Minerals#Refinement|Refine]] Node 2") == (
        "Adds base to Refine Node 2"
    )
    assert plain_text("[[Zodiacs]] Level Sum (ZLM) Boost") == "Zodiacs Level Sum (ZLM) Boost"


def test_plain_text_unwraps_keyword_templates_including_named_arguments():
    assert plain_text("Fire adds base to {{Keyword|node|Refine Tree Node 60}}") == (
        "Fire adds base to Refine Tree Node 60"
    )
    assert plain_text("{{Keyword|ach|Ach 232|link=Achievements}} reward is multiplied") == (
        "Ach 232 reward is multiplied"
    )


def test_plain_text_drops_decoration_and_markup():
    assert plain_text("[[File:Relic 001.png|128px|link=]]A Boost") == "A Boost"
    assert plain_text("Formula is: <math>1 + \\frac {x}{100}</math>") == "Formula is:"
    assert plain_text("1e5,200<!-- prior to ach.: 1e21,250 -->") == "1e5,200"
    assert plain_text("A Simple (''flat'') Boost") == "A Simple (flat) Boost"
    assert plain_text("takes your soul (''-1 {{keyword|soul|Soul}} {{Icon|soul_icon}}'')") == (
        "takes your soul (-1 Soul )"
    )


def test_split_fields_ignores_pipes_inside_templates_and_links():
    body = "| effect1 = A|B\n| effect2 = {{Keyword|ach|Ach 232|link=Achievements}} reward\n"
    assert split_fields(body) == [
        "",
        " effect1 = A",
        "B\n",
        " effect2 = {{Keyword|ach|Ach 232|link=Achievements}} reward\n",
    ]


def test_template_fields_keeps_equals_signs_inside_values():
    body = "|59| max = 1 | effect = they become Fire= 0.5, Earth= 3.50 | req = 58 "
    fields = template_fields(body)
    assert fields["max"] == "1"
    assert fields["effect"] == "they become Fire= 0.5, Earth= 3.50"
    assert fields["req"] == "58"


def test_derive_op_reads_the_operator_off_the_coefficient_string():
    assert derive_op("+0.2") is Op.ADD
    assert derive_op("-^0.01") is Op.EXP
    assert derive_op("+^(?)") is Op.EXP
    assert derive_op("^^0.999") is Op.EXP
    assert derive_op("^1.05 (base)") is Op.EXP
    assert derive_op("*^0.013(?)") is Op.MULT
    assert derive_op("x1.02") is Op.MULT
    assert derive_op("/2.00") is Op.MULT
    assert derive_op(None) is None
    assert derive_op("(?)") is None
    assert derive_op("X = +0.11 & Y = +1.245") is None


def test_is_uncertain_spots_the_wikis_question_marks():
    assert is_uncertain("+1.31 (?)")
    assert is_uncertain("+0.2?")
    assert is_uncertain(None, "(?)")
    assert not is_uncertain("+0.2")
    assert not is_uncertain(None)


def test_resolve_finds_relics_refine_nodes_element_nodes_and_tarot_cards():
    assert resolve("Multiplies Relic 62 effect") == [Reference("relic-62")]
    assert resolve("Increases efficiency of relics 2 and 4") == [
        Reference("relic-2"),
        Reference("relic-4"),
    ]
    assert resolve("Adds base to Refine Node 2") == [Reference("refine-node-2")]
    assert resolve("Fire adds base to Refine Tree Node 60") == [Reference("refine-node-60")]
    assert resolve("unlocked by Fire Node 11") == [Reference("fire-node-11")]
    assert resolve("King of Wands card") == [Reference("tarot-king-of-wands")]


def test_resolve_reads_an_ordinal_effect_pointer():
    assert resolve("Relic 62's second effect is doubled") == [
        Reference("relic-62", targets_effect=1)
    ]
    assert resolve("Relic 12 first effect powered to ^128") == [
        Reference("relic-12", targets_effect=0)
    ]


def test_resolve_returns_references_in_order_of_appearance_without_duplicates():
    text = "Refine Node 5 boosts Relic 9, and Relic 9 boosts Refine Node 5"
    assert resolve(text) == [Reference("refine-node-5"), Reference("relic-9")]


def test_resolve_ignores_bare_node_references():
    # "Node 1" inside Elements means an element node, not a refine node. An
    # ambiguous match would manufacture a wrong edge, which is worse than none.
    # The first two inputs carry the guard: they contain the bare "Node <n>"
    # form, so they start failing the moment a pattern matches it. The third
    # has no digit at all and so can never fail — it is kept only to document
    # that prose naming "Node" without a number is inert too.
    assert resolve("Node 5 provides bonus") == []
    assert resolve("each Node 11 is boosted") == []
    assert resolve("Makes First Node of each element stronger") == []
