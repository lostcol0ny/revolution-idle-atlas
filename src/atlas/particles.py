"""Particles node ids shared by `atlas game` (gamemap) and `atlas extract` (game_text).

A leaf module: gamemap imports the extract package and the extract package
imports game_text, so neither can hold what the other needs.
"""

from atlas.models import Rel

GRADES = ("rank", "tier", "tetr", "pent")


def grade_node(grade: str) -> str:
    return f"particles-{grade}"


def grade_bonus_prefix(grade: str) -> str:
    return f"particles-{grade}-bonus-"


# The node every member of a Particles family hangs off, and how. Grades unlock
# their bonuses (HELP_UNI_PARTICLES_GRADES_DESC_1). Tree nodes and spark
# colours belong to curated group nodes, the way attack-circles holds its
# circles: the game buys tree nodes with ETP (HELP_UNI_PARTICLES_TREE_DESC_1)
# and creates sparks from Epsilon (HELP_UNI_PARTICLES_SPARKS_DESC_1), and those
# edges attach once, to the group. `atlas extract` turns these into edges from
# data/game.yaml, so CI needs no game to rebuild them.
MEMBER_LINKS: tuple[tuple[str, str, Rel], ...] = (
    *((grade_bonus_prefix(g), grade_node(g), Rel.REQUIRES) for g in GRADES),
    ("epsilon-tree-node-", "epsilon-tree", Rel.UNLOCKS),
    ("particles-spark-", "particles-sparks", Rel.UNLOCKS),
)
