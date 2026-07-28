from pathlib import Path

import pytest
import yaml

from atlas.loader import SchemaError, load_dataset
from atlas.models import EdgeConfidence, Kind, Rel, System

FIXTURES = Path(__file__).parent / "fixtures"


def test_loads_nodes_and_edges():
    ds = load_dataset(FIXTURES / "minimal.yaml")
    assert len(ds.nodes) == 2
    assert len(ds.edges) == 1
    assert ds.nodes[0].id == "refine-node-121"
    assert ds.nodes[0].system is System.MINERAL
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
    assert ds.edges[0].line == 16


def test_bad_enum_raises_schema_error(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "nodes:\n"
        "  - id: x\n"
        "    name: X\n"
        "    system: not-a-system\n"
        "    kind: relic\n"
        "edges: []\n"
    )
    with pytest.raises(SchemaError) as exc:
        load_dataset(bad)
    assert any("system" in p for p in exc.value.problems)


def test_non_mapping_root_raises_schema_error_not_attribute_error(tmp_path):
    bad = tmp_path / "list_root.yaml"
    bad.write_text("- a\n- b\n")
    with pytest.raises(SchemaError) as exc:
        load_dataset(bad)
    assert exc.value.problems[0] == "top level must be a mapping with 'nodes' and 'edges' keys"


def test_python_object_tags_are_rejected(tmp_path):
    """The line-tracking loader must not widen SafeLoader's constructor set."""
    evil = tmp_path / "evil.yaml"
    evil.write_text("nodes: !!python/object/apply:os.system ['echo pwned']\n")
    with pytest.raises(yaml.YAMLError):
        load_dataset(evil)
