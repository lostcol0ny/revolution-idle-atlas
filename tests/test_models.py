import pytest
from pydantic import ValidationError

from atlas.models import Dataset, Edge, Effect, Kind, Node, Op, Suppression, SystemDef


def test_system_is_a_free_string():
    node = Node(id="x", name="X", system="refine-tree", kind="tree-node")
    assert node.system == "refine-tree"


def test_node_effects_default_to_empty_and_accept_effects():
    bare = Node(id="x", name="X", system="relics", kind="relic")
    assert bare.effects == []

    loaded = Node(
        id="relic-38",
        name="Smart Man",
        system="relics",
        kind="relic",
        effects=[{"text": "Adds base to Refine Node 2", "per_level": "+1.00", "op": "add"}],
    )
    assert loaded.effects[0].text == "Adds base to Refine Node 2"
    assert loaded.effects[0].per_level == "+1.00"
    assert loaded.effects[0].op is Op.ADD


def test_effect_per_level_and_op_are_optional():
    effect = Effect(text="Unlocks the Singularity")
    assert effect.per_level is None
    assert effect.op is None


def test_effect_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        Effect(text="x", magnitude="huge")


def test_edge_targets_effect_defaults_to_none_and_accepts_an_index():
    plain = Edge(**{"from": "a", "to": "b", "rel": "boosts", "source": "wiki:Relics"})
    assert plain.targets_effect is None

    pointed = Edge(
        **{
            "from": "relic-66",
            "to": "relic-62",
            "rel": "boosts",
            "source": "wiki:Relics",
            "targets_effect": 0,
        }
    )
    assert pointed.targets_effect == 0


def test_system_def_parent_is_optional():
    root = SystemDef(id="unity", name="Unity")
    assert root.parent is None
    child = SystemDef(id="relics", name="Relics", parent="unity")
    assert child.parent == "unity"


def test_suppression_uses_the_from_alias():
    suppression = Suppression(
        **{"from": "a", "to": "b", "rel": "requires", "reason": "duplicated wiki row"}
    )
    assert suppression.from_ == "a"


def test_dataset_systems_and_suppress_default_to_empty():
    ds = Dataset()
    assert ds.systems == []
    assert ds.suppress == []


def test_a_node_may_carry_aliases():
    node = Node(
        id="special-minerals-merge-factor",
        name="Special Minerals Merge Factor",
        system="minerals",
        kind=Kind.STAT,
        aliases=["SMMF"],
    )
    assert node.aliases == ["SMMF"]


def test_aliases_default_to_empty_and_are_not_shared_between_instances():
    # A bare `aliases: list[str] = []` on a Pydantic model is safe, but a plain
    # dataclass default would alias one list across every node. Pin the
    # behaviour so a future refactor away from Pydantic cannot regress it
    # silently.
    a = Node(id="a", name="A", system="unity", kind=Kind.STAT)
    b = Node(id="b", name="B", system="unity", kind=Kind.STAT)
    a.aliases.append("X")
    assert b.aliases == []
