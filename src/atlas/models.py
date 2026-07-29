from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


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


# These two vocabularies differ deliberately and must never be merged.
# A node's `unknown` means "placeholder, nothing curated yet".
# An edge's `uncertain` means "believed to exist, mechanism not established".
class NodeConfidence(StrEnum):
    DOCUMENTED = "documented"
    PROVISIONAL = "provisional"
    UNKNOWN = "unknown"


class EdgeConfidence(StrEnum):
    DOCUMENTED = "documented"
    PROVISIONAL = "provisional"
    UNCERTAIN = "uncertain"


# The system taxonomy is data, not an enum. It was an enum, and the same nine
# names had to be written again in web/src/types.ts and again in the README —
# they drifted, and a value present in one and absent in another rendered a
# blank canvas. One list, loaded from the dataset, cannot drift from itself.
class SystemDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    parent: str | None = None
    line: int | None = Field(default=None, exclude=True)


class Effect(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    # Kept exactly as the wiki writes it, including "(?)" and "*^". The wiki's
    # own notation carries information no parsed number can: "+(?)" means the
    # operator is known and the coefficient is not.
    per_level: str | None = None
    op: Op | None = None


class Node(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    system: str
    kind: Kind
    wiki: str | None = None
    confidence: NodeConfidence = NodeConfidence.DOCUMENTED
    effects: list[Effect] = Field(default_factory=list)
    # Other names the wiki uses for the same entity. Read by
    # extract/vocab.py to build the resolver's vocabulary, which is the only
    # consumer — an alias is matching input, not display text.
    aliases: list[str] = Field(default_factory=list)
    line: int | None = Field(default=None, exclude=True)


class Edge(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_: str = Field(alias="from")
    to: str
    rel: Rel
    op: Op | None = None
    note: str | None = None
    # 0-based index into the *target* node's `effects`. Set when the source
    # modifies one specific effect rather than the node as a whole — "Relic 66
    # multiplies Relic 62's effect" is second-order and the endpoints alone
    # cannot say which effect it lands on.
    targets_effect: int | None = None
    source: str
    confidence: EdgeConfidence = EdgeConfidence.DOCUMENTED
    line: int | None = Field(default=None, exclude=True)


class Suppression(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_: str = Field(alias="from")
    to: str
    rel: Rel
    # Required, not optional. A suppression deletes a generated edge, so the
    # only record of why it was deleted is this string — the edge it removes
    # will not be in the merged output for anyone to reason about later.
    reason: str
    line: int | None = Field(default=None, exclude=True)


class Dataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    systems: list[SystemDef] = Field(default_factory=list)
    nodes: list[Node] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)
    suppress: list[Suppression] = Field(default_factory=list)

    def node_ids(self) -> set[str]:
        return {n.id for n in self.nodes}

    def system_ids(self) -> set[str]:
        return {s.id for s in self.systems}
