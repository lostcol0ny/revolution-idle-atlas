from collections.abc import Callable

import pytest

from atlas.models import Edge, Node

# Shared model factories. These live here rather than in a test module because
# importing one test module from another re-runs its collection-time code and
# ties the two modules' lifetimes together.


@pytest.fixture
def node() -> Callable[..., Node]:
    def make(
        node_id: str, system: str = "unity", confidence: str = "documented"
    ) -> Node:
        return Node(
            id=node_id,
            name=node_id,
            system=system,
            kind="relic",
            confidence=confidence,
        )

    return make


@pytest.fixture
def edge() -> Callable[[str, str], Edge]:
    def make(src: str, dst: str) -> Edge:
        return Edge(**{"from": src, "to": dst, "rel": "boosts", "source": "observed"})

    return make
