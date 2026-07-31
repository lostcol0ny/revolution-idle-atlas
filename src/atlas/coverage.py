from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx
import yaml

from atlas.models import Dataset, NodeConfidence, Rel


@dataclass(frozen=True)
class SystemRollup:
    id: str
    name: str
    depth: int
    direct: int
    total: int
    connected: int


@dataclass
class CoverageReport:
    orphans: list[str] = field(default_factory=list)
    cycles: list[list[str]] = field(default_factory=list)
    per_system: dict[str, tuple[int, int]] = field(default_factory=dict)
    stub_count: int = 0
    node_count: int = 0
    edge_count: int = 0
    missing_entities: dict[str, list[str]] = field(default_factory=dict)
    has_inventory: bool = False
    unresolved: list[str] = field(default_factory=list)
    rollup: list[SystemRollup] = field(default_factory=list)
    # (page title, byte size), largest first. Empty when analyse was called
    # without raw_pages, which is what keeps the section out of the document
    # rather than rendering it as "None".
    not_swept: list[tuple[str, int]] = field(default_factory=list)


def load_inventory(path: Path) -> dict[str, list[str]] | None:
    """Read the optional IL2CPP entity inventory. None when the file is absent."""
    if not path.is_file():
        return None
    # An empty or non-mapping file is treated as no inventory at all. `or {}`
    # would report it as present, so the coverage report would claim "every
    # inventoried entity has a node" against zero entities; a list-shaped root
    # would reach .items() in analyse and surface as an AttributeError traceback.
    result = yaml.safe_load(path.read_text(encoding="utf-8"))
    return result if isinstance(result, dict) else None


def page_title(filename: str) -> str:
    """Turn a data/raw/ filename back into the wiki page title it came from.

    Not a strict inverse of `rawcheck.raw_filename`, and it cannot be: that
    function maps both "Dilation Tree" and "Dilation_Tree" onto the same file,
    so the spelling that was written is not recoverable. This returns the
    underscored form, which is what every `wiki:` value in this repo already
    uses and what MediaWiki treats as equivalent to the spaced one in a URL.

    The two must nonetheless agree on the `/` <-> `__` mapping, because they are
    compared against each other to decide whether a page has been read — a
    divergence there reports a swept page as unswept.
    """
    return filename.removesuffix(".wikitext").replace("__", "/")


def _build_graph(ds: Dataset) -> nx.DiGraph:
    graph = nx.DiGraph()
    graph.add_nodes_from(n.id for n in ds.nodes)
    known = ds.node_ids()
    for edge in ds.edges:
        if edge.from_ in known and edge.to in known:
            graph.add_edge(edge.from_, edge.to)
    return graph


def _unresolved(ds: Dataset) -> list[str]:
    """Nodes that state an effect but point at nothing.

    `requires` describes tree structure, not an effect, so an edge of that kind
    does not count as having resolved anything. This list is the extraction's
    accuracy gap made visible: it shrinks as the resolver improves and as
    corrections land in relationships.yaml. It has a non-zero floor, though —
    an effect that modifies a stat rather than a node has no node-to-node edge
    to resolve to — so it is a search space to work through, not a list to
    drive to empty.
    """
    resolved = {e.from_ for e in ds.edges if e.rel is not Rel.REQUIRES}
    return sorted(n.id for n in ds.nodes if n.effects and n.id not in resolved)


def _rollup(ds: Dataset, graph: nx.DiGraph) -> list[SystemRollup]:
    if not ds.systems:
        return []

    direct: dict[str, int] = {s.id: 0 for s in ds.systems}
    connected: dict[str, int] = {s.id: 0 for s in ds.systems}
    for node in ds.nodes:
        if node.system not in direct:
            continue
        direct[node.system] += 1
        connected[node.system] += int(graph.degree(node.id) > 0)

    children: dict[str | None, list[str]] = {}
    known = {s.id for s in ds.systems}
    for system in ds.systems:
        # A parent that is not itself declared cannot be climbed to, so the
        # system is treated as a root rather than dropped from the report.
        parent = system.parent if system.parent in known else None
        children.setdefault(parent, []).append(system.id)

    by_id = {s.id: s for s in ds.systems}

    def walk(system_id: str, depth: int) -> list[SystemRollup]:
        rows: list[SystemRollup] = []
        for child in children.get(system_id, []):
            rows.extend(walk(child, depth + 1))
        system = by_id[system_id]
        return [
            SystemRollup(
                id=system_id,
                name=system.name,
                depth=depth,
                direct=direct[system_id],
                total=direct[system_id] + sum(r.total for r in rows if r.depth == depth + 1),
                connected=connected[system_id]
                + sum(r.connected for r in rows if r.depth == depth + 1),
            )
        ] + rows

    ordered: list[SystemRollup] = []
    for root in children.get(None, []):
        ordered.extend(walk(root, 0))

    # `walk` needs no cycle guard, and this loop is the reason. A system has one
    # parent, so every member of a parent cycle has its parent inside that cycle
    # — which means no cycle member is ever a child of a root, and `walk`, which
    # only ever starts from `children[None]`, cannot reach one. Cycle members
    # therefore fall through to here. Report them flat rather than silently
    # dropping their nodes out of the totals.
    placed = {r.id for r in ordered}
    for system in ds.systems:
        if system.id not in placed:
            ordered.append(
                SystemRollup(
                    id=system.id,
                    name=system.name,
                    depth=0,
                    direct=direct[system.id],
                    total=direct[system.id],
                    connected=connected[system.id],
                )
            )
    return ordered


def analyse(
    ds: Dataset,
    inventory: dict[str, list[str]] | None = None,
    raw_pages: dict[str, int] | None = None,
) -> CoverageReport:
    graph = _build_graph(ds)

    orphans = sorted(n for n in graph.nodes if graph.degree(n) == 0)

    cycles = sorted(
        (sorted(component) for component in nx.strongly_connected_components(graph)
         if len(component) > 1),
        key=lambda component: (-len(component), component[0]),
    )

    per_system: dict[str, tuple[int, int]] = {}
    for node in ds.nodes:
        connected, total = per_system.get(node.system, (0, 0))
        is_connected = graph.degree(node.id) > 0
        per_system[node.system] = (connected + int(is_connected), total + 1)

    stub_count = sum(
        1 for n in ds.nodes if n.confidence is NodeConfidence.UNKNOWN
    )

    known = ds.node_ids()
    missing_entities = {}
    for system, entity_ids in (inventory or {}).items():
        absent = sorted(e for e in entity_ids if e not in known)
        if absent:
            missing_entities[system] = absent

    # A page counts as read when some node points at it — which covers the four
    # hand-written parsers, every sweep manifest entry and any hand-curated
    # node through one rule. The anchor is stripped because node.wiki carries
    # "Tarot#Major_Arcana" on some curated nodes.
    covered = {n.wiki.split("#", 1)[0] for n in ds.nodes if n.wiki}
    not_swept = sorted(
        ((page, size) for page, size in (raw_pages or {}).items() if page not in covered),
        # Largest first: this is a work queue, and 38 of the 88 files are
        # sub-200-byte redirect stubs that must not sit above Achievements.
        # The name breaks ties so the generated file is byte-stable.
        key=lambda item: (-item[1], item[0]),
    )

    return CoverageReport(
        orphans=orphans,
        cycles=cycles,
        per_system=per_system,
        stub_count=stub_count,
        node_count=len(ds.nodes),
        edge_count=len(ds.edges),
        missing_entities=missing_entities,
        has_inventory=inventory is not None,
        unresolved=_unresolved(ds),
        rollup=_rollup(ds, graph),
        not_swept=not_swept,
    )


def render_markdown(report: CoverageReport) -> str:
    lines = [
        "# Coverage report",
        "",
        "Generated by `atlas build`. Do not edit by hand.",
        "",
        f"- Nodes: {report.node_count}",
        f"- Edges: {report.edge_count}",
        f"- Stubs (confidence `unknown`): {report.stub_count}",
        "",
        "## Per-system coverage",
        "",
        "| System | Connected | Total | Coverage |",
        "|---|---|---|---|",
    ]
    for system in sorted(report.per_system):
        connected, total = report.per_system[system]
        pct = (100 * connected // total) if total else 0
        lines.append(f"| {system} | {connected} | {total} | {pct}% |")

    if report.rollup:
        lines += ["", "## System hierarchy", ""]
        lines.append("Node counts rolled up through each system's parent.")
        lines.append("")
        for row in report.rollup:
            indent = "  " * row.depth
            detail = f"{row.total} nodes, {row.connected} connected"
            if row.direct != row.total:
                detail += f" ({row.direct} directly)"
            lines.append(f"{indent}- **{row.name}** — {detail}")

    lines += ["", "## Unresolved effects", ""]
    if report.unresolved:
        lines.append(
            "Nodes that describe an effect but point at no other node."
        )
        lines.append("")
        lines.append(
            "Some are resolver gaps, or edges waiting to be written into "
            "`data/relationships.yaml`. Others never will be: an effect that "
            "modifies a stat rather than a node — \"a flat boost to Damage "
            "Mult\" — has no node-to-node edge to resolve to. This is a search "
            "space, not a checklist."
        )
        lines.append("")
        lines += [f"- `{node_id}`" for node_id in report.unresolved]
    else:
        lines.append("None — every stated effect resolves to at least one edge.")

    lines += ["", "## Orphan nodes", ""]
    if report.orphans:
        lines.append("Nodes with no edges in either direction.")
        lines.append("")
        lines += [f"- `{node_id}`" for node_id in report.orphans]
    else:
        lines.append("None.")

    lines += ["", "## Feedback loops", ""]
    if report.cycles:
        lines.append("Strongly connected components. These are real game mechanics, not errors.")
        lines.append("")
        for component in report.cycles:
            lines.append("- " + " → ".join(f"`{n}`" for n in component))
    else:
        lines.append("None.")

    if report.not_swept:
        lines += ["", "## Not swept", ""]
        lines.append(
            "Pages in `data/raw/` that no node points at. Largest first, "
            "because this is a work queue: adding one is an entry in "
            "`data/sweep.yaml`, not a new parser."
        )
        lines.append("")
        lines.append(
            "The tail is redirect stubs of a few dozen bytes. They sort to the "
            "bottom on their own rather than being filtered by a size "
            "threshold nobody could justify."
        )
        lines.append("")
        lines += ["| Page | Bytes |", "|---|---|"]
        lines += [f"| `{page}` | {size} |" for page, size in report.not_swept]

    if report.has_inventory:
        lines += ["", "## Known unknowns", ""]
        if report.missing_entities:
            lines.append(
                "Entities the game's enums prove exist but which have no node yet."
            )
            lines.append("")
            for system in sorted(report.missing_entities):
                lines.append(f"### {system}")
                lines.append("")
                lines += [f"- `{e}`" for e in report.missing_entities[system]]
                lines.append("")
            lines.pop()
        else:
            lines.append("None — every inventoried entity has a node.")

    return "\n".join(lines) + "\n"
