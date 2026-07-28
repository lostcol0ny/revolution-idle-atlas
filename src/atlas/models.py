from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class System(StrEnum):
    REVOLUTION = "revolution"
    INFINITY = "infinity"
    ETERNITY = "eternity"
    UNITY = "unity"
    ZODIAC = "zodiac"
    MINERAL = "mineral"
    TAROT = "tarot"
    SINGULARITY = "singularity"
    PLAGUE = "plague"


class Kind(StrEnum):
    RELIC = "relic"
    STAT = "stat"
    TREE_NODE = "tree-node"
    CURRENCY = "currency"
    TAROT_CARD = "tarot-card"
    UPGRADE = "upgrade"
    GROUP = "group"


class Rel(StrEnum):
    BOOSTS = "boosts"
    UNLOCKS = "unlocks"
    REQUIRES = "requires"


class Op(StrEnum):
    ADD = "add"
    MULT = "mult"
    EXP = "exp"


class NodeConfidence(StrEnum):
    DOCUMENTED = "documented"
    PROVISIONAL = "provisional"
    UNKNOWN = "unknown"


class EdgeConfidence(StrEnum):
    DOCUMENTED = "documented"
    PROVISIONAL = "provisional"
    UNCERTAIN = "uncertain"


class Node(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    system: System
    kind: Kind
    wiki: str | None = None
    confidence: NodeConfidence = NodeConfidence.DOCUMENTED
    line: int | None = Field(default=None, exclude=True)


class Edge(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_: str = Field(alias="from")
    to: str
    rel: Rel
    op: Op | None = None
    note: str | None = None
    source: str
    confidence: EdgeConfidence = EdgeConfidence.DOCUMENTED
    line: int | None = Field(default=None, exclude=True)


class Dataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nodes: list[Node] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)

    def node_ids(self) -> set[str]:
        return {n.id for n in self.nodes}
