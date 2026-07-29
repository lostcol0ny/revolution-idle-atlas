import pytest

from atlas.extract.refs import resolve
from atlas.extract.vocab import build_vocabulary
from atlas.models import Kind, Node


def _stat(node_id: str, name: str, aliases: list[str] | None = None) -> Node:
    return Node(
        id=node_id,
        name=name,
        system="minerals",
        kind=Kind.STAT,
        aliases=aliases or [],
    )


def test_a_node_name_becomes_a_surface_form():
    vocab = build_vocabulary([_stat("sms-factor", "SMS Factor")])
    assert [r.target_id for r in resolve("Multiplies SMS Factor", vocab)] == ["sms-factor"]


def test_an_alias_becomes_a_surface_form_alongside_the_name():
    vocab = build_vocabulary(
        [_stat("special-minerals-merge-factor", "Special Minerals Merge Factor", ["SMMF"])]
    )
    assert len(vocab) == 2
    assert [r.target_id for r in resolve("Boosts SMMF", vocab)] == [
        "special-minerals-merge-factor"
    ]


def test_every_node_participates_not_only_the_ones_with_aliases():
    # A node with no aliases must still be matchable by its name. Scoping the
    # vocabulary to alias-bearing nodes would silently drop most stats, which
    # have no abbreviation the wiki uses.
    vocab = build_vocabulary(
        [_stat("mineral-cost-exp", "Mineral Cost Exp"), _stat("luck", "Luck", ["LK"])]
    )
    assert len(vocab) == 3


def test_a_name_too_short_to_be_safe_is_dropped_by_the_vocabulary_not_by_the_builder():
    # The builder hands everything over; Vocabulary owns the length floor. Two
    # places enforcing it means two places to get it wrong.
    #
    # Both names are two characters, so a length filter inside the builder would
    # drop both and yield 0. Only Vocabulary separates them: "OK" is ALL-UPPERCASE
    # and alphabetic, so it clears the relaxed two-character floor that exists for
    # abbreviations, while lowercase "xp" takes the strict floor of three. Getting
    # exactly one term back is reachable only if the builder submitted both and
    # left the decision to Vocabulary.
    vocab = build_vocabulary([_stat("xp", "xp"), _stat("ok", "OK")])
    assert len(vocab) == 1


def test_no_nodes_yields_an_empty_vocabulary():
    # `atlas extract` has to survive a curated file with no nodes in it, and an
    # empty Vocabulary is inert rather than a special case at every call site.
    assert len(build_vocabulary([])) == 0


def test_two_nodes_claiming_the_same_surface_form_raises():
    # Two nodes with the same name are a curation error: validate_dataset only
    # checks for duplicate ids, so this ValueError is the only thing that catches
    # a duplicate name. Letting it through would produce a wrong edge that looks
    # true — Vocabulary would resolve the surface to whichever node won the sort,
    # with no indication the other node ever competed for that span.
    #
    # The pattern pins both ids rather than the whole message. Naming which two
    # nodes collided is what lets a curator find them, so rewording the prefix
    # should leave this test passing while dropping the ids must fail it.
    with pytest.raises(ValueError, match=r"'a'.*'b'"):
        build_vocabulary([_stat("a", "Merge Factor"), _stat("b", "Merge Factor")])


def test_exact_duplicate_pair_dedupes_silently():
    # A node whose alias happens to equal its own name (or a union that overlaps)
    # must not blow up the build. Vocabulary dedupes identical (surface, id) pairs
    # before the conflict check, so one term is emitted and no error is raised.
    vocab = build_vocabulary([_stat("luck", "Luck", ["Luck"])])
    assert len(vocab) == 1
