from pathlib import Path

import pytest
import yaml

from atlas.loader import SchemaError, load_dataset
from atlas.models import EdgeConfidence, Kind, Rel

FIXTURES = Path(__file__).parent / "fixtures"


def test_loads_nodes_and_edges():
    ds = load_dataset(FIXTURES / "minimal.yaml")
    assert len(ds.nodes) == 2
    assert len(ds.edges) == 1
    assert ds.nodes[0].id == "refine-node-121"
    assert ds.nodes[0].system == "mineral"
    assert ds.nodes[0].kind is Kind.TREE_NODE


def test_edge_from_is_aliased():
    ds = load_dataset(FIXTURES / "minimal.yaml")
    edge = ds.edges[0]
    assert edge.from_ == "refine-node-121"
    assert edge.to == "singularity"
    assert edge.rel is Rel.UNLOCKS
    assert edge.confidence is EdgeConfidence.PROVISIONAL
    assert edge.op is None


def test_line_numbers_are_attached():
    ds = load_dataset(FIXTURES / "minimal.yaml")
    assert ds.nodes[0].line == 2
    # Index 1 as well as 0: a loop that only ever attaches the first line number
    # passes an index-0-only assertion.
    assert ds.nodes[1].line == 8
    assert ds.edges[0].line == 16


def test_bad_enum_raises_schema_error(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "nodes:\n"
        "  - id: x\n"
        "    name: X\n"
        "    system: unity\n"
        "    kind: not-a-kind\n"
        "edges: []\n"
    )
    with pytest.raises(SchemaError) as exc:
        load_dataset(bad)
    assert any("kind" in p for p in exc.value.problems)


def test_non_mapping_root_raises_schema_error_not_attribute_error(tmp_path):
    bad = tmp_path / "list_root.yaml"
    bad.write_text("- a\n- b\n")
    with pytest.raises(SchemaError) as exc:
        load_dataset(bad)
    assert exc.value.problems[0] == "top level must be a mapping with 'nodes' and 'edges' keys"


@pytest.mark.parametrize(
    "payload",
    [
        "nodes: !!python/object/apply:os.system ['echo pwned']\n",
        "nodes: !!python/object/new:os.system ['echo pwned']\n",
        "nodes: !!python/name:os.system\n",
    ],
)
def test_python_object_tags_are_rejected(tmp_path, payload):
    """The line-tracking loader must not widen SafeLoader's constructor set."""
    evil = tmp_path / "evil.yaml"
    evil.write_text(payload)
    with pytest.raises(yaml.YAMLError):
        load_dataset(evil)


def test_nested_effect_mappings_do_not_leak_line_markers(tmp_path):
    path = tmp_path / "effects.yaml"
    path.write_text(
        "nodes:\n"
        "  - id: relic-38\n"
        "    name: Smart Man\n"
        "    system: relics\n"
        "    kind: relic\n"
        "    effects:\n"
        "      - text: Adds base to Refine Node 2\n"
        "        per_level: '+1.00'\n"
        "edges: []\n"
    )
    ds = load_dataset(path)
    assert ds.nodes[0].effects[0].per_level == "+1.00"


def test_systems_and_suppress_sections_load_with_line_numbers(tmp_path):
    path = tmp_path / "systems.yaml"
    path.write_text(
        "systems:\n"
        "  - id: unity\n"
        "    name: Unity\n"
        "  - id: relics\n"
        "    name: Relics\n"
        "    parent: unity\n"
        "nodes: []\n"
        "edges: []\n"
        "suppress:\n"
        "  - from: a\n"
        "    to: b\n"
        "    rel: requires\n"
        "    reason: the wiki table lists this row twice\n"
    )
    ds = load_dataset(path)
    assert [s.id for s in ds.systems] == ["unity", "relics"]
    assert ds.systems[0].line == 2
    assert ds.systems[1].line == 4
    assert ds.suppress[0].from_ == "a"
    assert ds.suppress[0].line == 10
