import pytest

from atlas.extract.refs import (
    Reference,
    Vocabulary,
    derive_op,
    is_uncertain,
    normalise_space,
    plain_text,
    resolve,
    slugify,
    split_fields,
    split_outside,
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
    assert plain_text("1e5,200<!-- prior to ach.: 1e21,250 -->") == "1e5,200"
    assert plain_text("A Simple (''flat'') Boost") == "A Simple (flat) Boost"
    assert plain_text("takes your soul (''-1 {{keyword|soul|Soul}} {{Icon|soul_icon}}'')") == (
        "takes your soul (-1 Soul )"
    )


def test_plain_text_keeps_math_content_so_the_surrounding_sentence_survives():
    # The second case is the one that matters: deleting the formula used to take
    # the subject of the sentence with it and leave "(Only the is divided by
    # 100)". LaTeX is passed through verbatim rather than rendered, so these
    # assertions are also the record of what a reader is shown.
    assert plain_text("Formula is: <math>1 + \\frac {x}{100}</math>") == (
        "Formula is: 1 + \\frac {x}{100}"
    )
    assert plain_text("(Only the <math>(x-308)^2\n</math> is divided by 100)") == (
        "(Only the (x-308)^2 is divided by 100)"
    )


def test_split_fields_ignores_pipes_inside_templates_and_links():
    body = "| effect1 = A|B\n| effect2 = {{Keyword|ach|Ach 232|link=Achievements}} reward\n"
    assert split_fields(body) == [
        "",
        " effect1 = A",
        "B\n",
        " effect2 = {{Keyword|ach|Ach 232|link=Achievements}} reward\n",
    ]


def test_split_outside_holds_a_multi_character_separator_inside_markup():
    # The reason `split_fields` and the wikitable reader's header split share one
    # implementation. `!!` separates header cells, and a `{{Keyword|...}}` in one
    # of them must not be cut open — nor may the two callers disagree about that.
    row = 'class="x" | Zodiac !! Icon !! {{Keyword|el|Element !! Season}} !! Bonus 1'
    assert split_outside(row, "!!") == [
        'class="x" | Zodiac ',
        " Icon ",
        " {{Keyword|el|Element !! Season}} ",
        " Bonus 1",
    ]
    # And the pipe split is that same function, not a second copy of it.
    assert split_fields("a|{{T|b|c}}|d") == split_outside("a|{{T|b|c}}|d", "|")


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


def _vocab() -> Vocabulary:
    # "Merge Factor" is listed BEFORE the longer form it is a substring of, on
    # purpose: with the specific form first, plain input-order iteration would
    # pass the longest-first test by luck and the sort could be deleted without
    # any test noticing.
    return Vocabulary(
        [
            ("Merge Factor", "merge-factor"),
            ("Special Minerals Merge Factor", "special-minerals-merge-factor"),
            ("SMMF", "special-minerals-merge-factor"),
            ("Attack Exponent", "attack-exponent"),
            ("AP", "animal-points"),
            ("Luck", "luck"),
        ]
    )


def test_the_longest_surface_form_claims_the_span():
    # Both "Special Minerals Merge Factor" and "Merge Factor" match this text.
    # Only longest-first ordering picks the specific node, and picking the
    # generic one would file the edge under the wrong stat entirely.
    refs = resolve("Boosts Special Minerals Merge Factor by 2x", _vocab())
    assert [r.target_id for r in refs] == ["special-minerals-merge-factor"]


def test_a_shorter_form_still_matches_when_the_longer_one_is_absent():
    # The counterpart to the test above: longest-first must not suppress the
    # generic node when the specific phrase is not present.
    refs = resolve("Boosts Merge Factor by 2x", _vocab())
    assert [r.target_id for r in refs] == ["merge-factor"]


def test_an_uppercase_alias_resolves_when_the_case_matches():
    # The positive half only. The rule that uppercase forms are matched
    # case-*sensitively* is carried by the next test, which is where a
    # regression would show.
    assert [r.target_id for r in resolve("Grants 3 AP per lap", _vocab())] == ["animal-points"]


def test_an_uppercase_alias_does_not_fire_inside_an_ordinary_word():
    # This single rule is what makes two-character abbreviations usable at all.
    # Case-insensitive matching would fire on both of these.
    assert resolve("Appears after the first reset", _vocab()) == []
    assert resolve("A different Approach to scaling", _vocab()) == []
    assert resolve("appears and approach", _vocab()) == []


def test_a_full_name_matches_case_insensitively():
    assert [r.target_id for r in resolve("raises attack exponent", _vocab())] == [
        "attack-exponent"
    ]


def test_matching_is_word_boundary_anchored():
    # "Luck" inside "Lucky" and "Potluck" is not a reference to the Luck stat.
    assert resolve("Lucky draws happen more often", _vocab()) == []
    assert resolve("A Potluck of bonuses", _vocab()) == []
    assert [r.target_id for r in resolve("Increases Luck", _vocab())] == ["luck"]


def test_a_two_character_lowercase_alias_is_rejected():
    # The length floor. "gs" would fire inside "gsub", "logs", "bags".
    vocab = Vocabulary([("gs", "game-speed")])
    assert len(vocab) == 0
    assert resolve("bags of logs", vocab) == []


def test_a_two_character_uppercase_alias_is_accepted():
    # Case-sensitivity supplies the precision the length floor otherwise would,
    # and AP/EP/IP/DP/RP/TF are the wiki's most-used currency names — a flat
    # floor of 3 would discard exactly those.
    vocab = Vocabulary([("EP", "eternity-points")])
    assert len(vocab) == 1
    assert [r.target_id for r in resolve("Grants 4 EP", vocab)] == ["eternity-points"]


def test_a_one_character_uppercase_alias_is_rejected():
    assert len(Vocabulary([("E", "eternity-points")])) == 0


def test_the_two_character_exemption_requires_letters_only():
    # str.isupper() is True for "A1", "2X" and "A-", none of which are the
    # letter abbreviations the exemption was written for: a digit or a dash
    # gives case-sensitivity nothing to grip on, so these take the floor of 3.
    assert len(Vocabulary([("A1", "some-stat")])) == 0
    assert len(Vocabulary([("2X", "some-stat")])) == 0
    assert len(Vocabulary([("A-", "some-stat")])) == 0
    # Only the floor is affected; a 3-character form with a digit is still fine.
    assert len(Vocabulary([("A1B", "some-stat")])) == 1


def test_a_vocabulary_match_does_not_overlap_an_entity_regex_match():
    # A stat unluckily aliased "Refine Node 2" must not produce a second
    # reference for text the refine-tree regex already resolved. One phrase,
    # one edge.
    vocab = Vocabulary([("Refine Node 2", "some-stat")])
    refs = resolve("Adds base to Refine Node 2", vocab)
    assert [r.target_id for r in refs] == ["refine-node-2"]


def test_a_vocabulary_match_overlapping_an_entity_span_only_partially_is_dropped():
    # The test above shares a start offset with the entity span, so a check as
    # weak as `start == other_start` would satisfy it. Here the surface form
    # begins mid-span and runs past the end, so only a real interval-overlap
    # test rejects it. An off-by-one at either edge double-counts the phrase.
    vocab = Vocabulary([("Node 2 boost", "some-stat")])
    refs = resolve("Adds base to Refine Node 2 boost", vocab)
    assert [r.target_id for r in refs] == ["refine-node-2"]


def test_resolve_with_no_vocabulary_behaves_exactly_as_before():
    # Regression guard on the defaulted parameter. Every existing parser calls
    # resolve(text) with one argument and must be unaffected.
    text = "Boosts Relic 38 and Refine Node 2 and the Ace of Swords"
    assert resolve(text) == resolve(text, None)
    assert [r.target_id for r in resolve(text)] == [
        "relic-38",
        "refine-node-2",
        "tarot-ace-of-swords",
    ]


def test_the_empty_vocabulary_is_inert():
    text = "Boosts Relic 38"
    assert resolve(text, Vocabulary.EMPTY) == resolve(text)


def test_a_repeated_surface_form_yields_one_reference():
    # resolve() already dedups on (target_id, targets_effect); the vocabulary
    # pass must not bypass that.
    refs = resolve("Luck up, then Luck again", _vocab())
    assert [r.target_id for r in refs] == ["luck"]


def test_references_are_ordered_by_position_in_the_text():
    # resolve() sorts by match start so an effect's note reads in the same
    # order as its edges. A vocabulary hit must take part in that ordering
    # rather than being appended at the end.
    vocab = Vocabulary([("Luck", "luck")])
    refs = resolve("Increases Luck and boosts Relic 38", vocab)
    assert [r.target_id for r in refs] == ["luck", "relic-38"]


def test_a_vocabulary_hit_can_carry_an_effect_pointer():
    # "<stat>'s first effect" must resolve to targets_effect=0 exactly as an
    # entity match does, so the two paths cannot drift.
    vocab = Vocabulary([("Windmill Pendant", "relic-39")])
    refs = resolve("Multiplies Windmill Pendant's first effect", vocab)
    assert refs[0].target_id == "relic-39"
    assert refs[0].targets_effect == 0


def test_a_surface_form_with_regex_metacharacters_is_matched_literally():
    # "Zodiac Exp. Factor" contains a dot. Unescaped it matches "Zodiac ExpX
    # Factor"; worse, a malformed alias could raise re.error at build time.
    vocab = Vocabulary([("Zodiac Exp. Factor", "zodiac-exp-factor")])
    assert [r.target_id for r in resolve("Raises Zodiac Exp. Factor", vocab)] == [
        "zodiac-exp-factor"
    ]
    assert resolve("Raises Zodiac ExpX Factor", vocab) == []


def test_a_surface_form_ending_in_punctuation_can_still_match():
    # r"\b" asserts a transition between a word and a non-word character, so it
    # asserts nothing at all when the surface itself ends in punctuation:
    # r"\bZodiac Exp\.\b" can never match "Zodiac Exp." anywhere. A mis-shaped
    # alias would then match nothing, silently, with no warning to the curator.
    vocab = Vocabulary([("Zodiac Exp.", "zodiac-exp")])
    assert [r.target_id for r in resolve("Raises Zodiac Exp.", vocab)] == ["zodiac-exp"]
    assert [r.target_id for r in resolve("Raises Zodiac Exp. by 2x", vocab)] == [
        "zodiac-exp"
    ]
    # The trailing guard still holds: this is not a reference to the stat.
    assert resolve("Raises Zodiac Exp.tra", vocab) == []


def test_a_surface_form_wrapped_in_punctuation_can_still_match():
    vocab = Vocabulary([("(Fire)", "fire")])
    assert [r.target_id for r in resolve("Boosts (Fire) output", vocab)] == ["fire"]


def test_a_vocabulary_reference_is_flagged_and_an_entity_one_is_not():
    # This flag is the only thing that lets a parser stamp `uncertain` on prose
    # matches while leaving a structural match's confidence alone. Without it
    # every edge from a call site would share one confidence value.
    vocab = Vocabulary([("Luck", "luck")])
    refs = resolve("Relic 38 increases Luck", vocab)
    by_id = {r.target_id: r for r in refs}
    assert by_id["relic-38"].from_vocabulary is False
    assert by_id["luck"].from_vocabulary is True


def test_from_vocabulary_defaults_to_false_so_existing_construction_is_unchanged():
    assert Reference("relic-38").from_vocabulary is False


def test_a_reference_after_based_on_is_an_input_not_a_target():
    # "Boosts X based on Y" names two nodes doing opposite jobs: X is changed,
    # Y is only read. Treating both as targets says the upgrade boosts the very
    # quantity it measures, which points the edge backwards.
    vocab = Vocabulary([("Gen 1", "generator-1"), ("Gen Power", "generator-power")])
    refs = {r.target_id: r for r in resolve("Boosts Gen 1 based on Gen Power", vocab)}
    assert refs["generator-1"].is_input is False
    assert refs["generator-power"].is_input is True


def test_by_amount_of_marks_an_input_too():
    vocab = Vocabulary([("Luck", "luck"), ("stars", "stars")])
    refs = {
        r.target_id: r
        for r in resolve("Multiplies Your Luck by amount of stars you have", vocab)
    }
    assert refs["luck"].is_input is False
    assert refs["stars"].is_input is True


def test_a_parenthesised_based_on_releases_the_text_after_the_closing_bracket():
    # "Adds a Singularity Effect (Based on Singularities) that boosts Spread
    # Speed" puts the marker inside brackets and the real target after them.
    # Running the input span to the end of the string would reverse that target
    # as well, turning one backwards edge into two.
    vocab = Vocabulary([("Singularities", "singularity"), ("Spread Speed", "spread")])
    refs = {
        r.target_id: r
        for r in resolve(
            "Adds a Singularity Effect (Based on Singularities) that boosts "
            "Spread Speed",
            vocab,
        )
    }
    assert refs["singularity"].is_input is True
    assert refs["spread"].is_input is False


def test_an_input_reference_carries_no_effect_pointer():
    # `targets_effect` indexes into the effects of the edge's `to` node. An
    # input reference becomes the `from` end, so an index read off it would
    # point into the wrong node's list.
    vocab = Vocabulary([("Luck", "luck")])
    refs = resolve("Grows based on Relic 38's second effect", vocab)
    assert [(r.target_id, r.is_input, r.targets_effect) for r in refs] == [
        ("relic-38", True, None)
    ]


def test_the_same_node_named_on_both_sides_of_the_marker_yields_both_directions():
    vocab = Vocabulary([("Luck", "luck")])
    refs = resolve("Boosts Luck based on Luck", vocab)
    assert [(r.target_id, r.is_input) for r in refs] == [("luck", False), ("luck", True)]


def test_endpoints_swaps_only_for_an_input_reference():
    assert Reference("luck").endpoints("relic-38") == ("relic-38", "luck")
    assert Reference("luck", is_input=True).endpoints("relic-38") == ("luck", "relic-38")


def test_is_input_defaults_to_false_so_existing_construction_is_unchanged():
    assert Reference("relic-38").is_input is False


def test_with_terms_returns_a_new_vocabulary_over_the_union():
    base = Vocabulary([("Luck", "luck")])
    extended = base.with_terms([("The Devil", "tarot-the-devil")])
    assert len(base) == 1, "with_terms must not mutate the receiver"
    assert len(extended) == 2
    assert [r.target_id for r in resolve("The Devil boosts Luck", extended)] == [
        "tarot-the-devil",
        "luck",
    ]


def test_with_terms_resorts_longest_first_across_both_sets():
    # The load-bearing assertion. If with_terms appended instead of re-sorting,
    # the short curated form would claim the span and the long added form would
    # never fire — which is exactly the Major Arcana case in tarot.py.
    base = Vocabulary([("Devil", "some-stat")])
    extended = base.with_terms([("The Devil", "tarot-the-devil")])
    assert [r.target_id for r in resolve("Draw The Devil", extended)] == [
        "tarot-the-devil"
    ]


def test_one_surface_form_claimed_by_two_nodes_is_a_hard_error():
    # Without this, the tie-break key (-len, surface) ignores target_id, so
    # whichever term happened to be listed first would claim the span and
    # suppress its rival — an edge decided by input order, indistinguishable
    # from a true one. A curator claiming one phrase for two stats is a data
    # conflict to fix in the YAML, so it must fail loudly rather than coin-flip.
    with pytest.raises(ValueError, match="Merge Factor"):
        Vocabulary(
            [("Merge Factor", "smmf"), ("Merge Factor", "zodiac-merge-factor")]
        )


def test_the_conflict_error_names_both_claimants():
    with pytest.raises(ValueError) as excinfo:
        Vocabulary([("Luck", "luck"), ("Luck", "luck-multiplier")])
    message = str(excinfo.value)
    assert "luck" in message and "luck-multiplier" in message


def test_with_terms_cannot_smuggle_in_a_conflicting_claim():
    # The check has to cover the union, not just a single constructor call,
    # or tarot.py could contest a curated surface form after the fact.
    base = Vocabulary([("Merge Factor", "smmf")])
    with pytest.raises(ValueError, match="Merge Factor"):
        base.with_terms([("Merge Factor", "zodiac-merge-factor")])


def test_two_case_spellings_claimed_by_two_nodes_is_also_a_hard_error():
    # Case variants reach the same collision by a different door. Two surfaces
    # that fold alike cannot both be ALL-UPPERCASE, so at least one compiles
    # case-insensitively and therefore matches the other's spelling too. Only
    # one can ever claim a span; the loser is unreachable, and prose the curator
    # spelled for it resolves to the winner. An exact-string key missed this.
    with pytest.raises(ValueError) as excinfo:
        Vocabulary([("Merge Factor", "smmf"), ("merge factor", "zodiac-mf")])
    message = str(excinfo.value)
    assert "smmf" in message and "zodiac-mf" in message
    # Both spellings are named, so a curator can find each entry in the YAML.
    assert "Merge Factor" in message and "merge factor" in message


def test_with_terms_cannot_smuggle_in_a_conflicting_case_variant():
    base = Vocabulary([("Merge Factor", "smmf")])
    with pytest.raises(ValueError, match="zodiac-mf"):
        base.with_terms([("merge factor", "zodiac-mf")])


def test_two_case_spellings_of_the_same_node_are_not_a_conflict():
    # One node spelled two ways is a legitimate use of aliases and must not
    # raise: the check compares target ids, not just folded surfaces.
    vocab = Vocabulary(
        [("Merge Factor", "merge-factor"), ("merge factor", "merge-factor")]
    )
    # Coinciding spans still yield one edge, not one per spelling.
    assert [r.target_id for r in resolve("Boosts Merge Factor", vocab)] == [
        "merge-factor"
    ]
    assert [r.target_id for r in resolve("Boosts merge factor", vocab)] == [
        "merge-factor"
    ]
    # And the same holds when the second spelling arrives through with_terms.
    extended = Vocabulary([("TF", "time-flux")]).with_terms([("Tf", "time-flux")])
    assert [r.target_id for r in resolve("Grants 2 TF", extended)] == ["time-flux"]


def test_an_identically_repeated_pair_is_deduped_rather_than_rejected():
    # Same surface, same target is not a conflict: a node whose alias repeats
    # its name, or a with_terms union that overlaps, is harmless.
    vocab = Vocabulary([("Luck", "luck"), ("Luck", "luck")])
    assert len(vocab) == 1
    assert [r.target_id for r in resolve("Increases Luck", vocab)] == ["luck"]
    assert len(vocab.with_terms([("Luck", "luck")])) == 1


def test_zodiacbadge_unwraps_to_its_content():
    # {{ZodiacBadge|Aries}} is the entire content of the Zodiac name column on
    # Zodiacs.wikitext. Without it in the content whitelist the column reads as
    # the empty string and every zodiac row is dropped for having no name.
    assert plain_text("{{ZodiacBadge|Aries}}") == "Aries"


def test_an_unlisted_template_is_still_decoration():
    # The whitelist must stay a whitelist: adding zodiacbadge may not turn every
    # template into content, or icons and banners start appearing in graph.json.
    assert plain_text("Gold {{Icon|gold}} gain") == "Gold gain"


def test_a_line_break_becomes_a_space_not_nothing():
    # A <br/> is a sentence boundary. Stripped to nothing it joins the last word
    # of one sentence to the first word of the next.
    assert plain_text("Unlock Tab<br/>SMS Factor is 0") == "Unlock Tab SMS Factor is 0"
    assert plain_text("a<br>b") == "a b"
    assert plain_text("a<BR />b") == "a b"
