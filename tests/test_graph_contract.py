import json
import re
from pathlib import Path

import pytest

GRAPH_PATH = Path(__file__).resolve().parents[1] / "public" / "graph.json"


@pytest.fixture(scope="module")
def graph() -> dict:
    return json.loads(GRAPH_PATH.read_text(encoding="utf-8"))


def test_no_relic_name_is_doubled(graph: dict):
    # The guard in render._relic_label is the only thing standing between a
    # stale curated placeholder and a "Relic 3 (Relic 3)" label reaching the
    # UI. Assert it on the real artifact, not just on a fixture.
    doubled = re.compile(r"^Relic \d+ \(Relic \d+\)$")
    offenders = [n["id"] for n in graph["nodes"] if doubled.match(n["name"])]
    assert offenders == []


def test_every_relic_node_is_labelled_with_its_number(graph: dict):
    numbered = re.compile(r"^Relic (\d+)(?: \(.+\))?$")
    for node in graph["nodes"]:
        if node["kind"] != "relic" or not re.match(r"^relic-\d+$", node["id"]):
            continue
        match = numbered.match(node["name"])
        assert match is not None, f"{node['id']} has uncomposed name {node['name']!r}"
        assert match.group(1) == node["id"].removeprefix("relic-")


def test_relic_18_carries_its_real_name(graph: dict):
    # relic-18 has no curated name override, so derived wins and composes correctly.
    # relic-3 and relic-69 still carry stale curated placeholder names ("Relic 3",
    # "Relic 69") that mask the derived real names — those two assertions require
    # Step 5 (deleting name: from relationships.yaml), which is blocked because the
    # loader validates the curated file standalone and Node.name is a required field.
    # See task-2-report.md for details. This test covers the composition for a node
    # that does not have a blocking curated override.
    names = {n["id"]: n["name"] for n in graph["nodes"]}
    assert names["relic-18"] == "Relic 18 (Mythical Rune)"
