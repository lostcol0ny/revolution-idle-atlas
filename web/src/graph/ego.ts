import type { EdgeConfidence, GraphEdge, GraphNode } from '../types';
import type { GraphIndex } from './adjacency';

export interface EgoNode {
  node: GraphNode;
  /** Negative upstream, 0 for the root, positive downstream. */
  column: number;
}

export interface EgoGraph {
  rootId: string;
  nodes: EgoNode[];
  edges: GraphEdge[];
}

export interface EgoOptions {
  /**
   * When false, `uncertain` edges are neither walked nor drawn, so a node
   * reachable only through them drops out too. Defaults to true.
   */
  includeUncertain?: boolean;
}

export class UnknownNodeError extends Error {
  constructor(id: string) {
    super(`unknown node id: ${id}`);
    this.name = 'UnknownNodeError';
  }
}

/** Matches the pipeline: an absent edge confidence means `documented`. */
export function edgeConfidence(edge: GraphEdge): EdgeConfidence {
  return edge.confidence ?? 'documented';
}

export function ego(
  index: GraphIndex,
  rootId: string,
  depth: number,
  options: EgoOptions = {},
): EgoGraph {
  if (!index.nodes.has(rootId)) {
    throw new UnknownNodeError(rootId);
  }

  const keep =
    options.includeUncertain === false
      ? (edge: GraphEdge) => edgeConfidence(edge) !== 'uncertain'
      : () => true;
  const columns = new Map<string, number>([[rootId, 0]]);

  // Upstream first, so an equal-distance tie resolves in its favour below.
  walk(index, rootId, depth, columns, 'upstream', keep);
  walk(index, rootId, depth, columns, 'downstream', keep);

  const nodes: EgoNode[] = [];
  for (const id of index.order) {
    const column = columns.get(id);
    const node = index.nodes.get(id);
    if (column !== undefined && node !== undefined) {
      nodes.push({ node, column });
    }
  }

  // Induced subgraph: every edge whose endpoints are both present, not merely
  // the edges the BFS traversed. Those extra edges are shared dependencies,
  // which are the structure worth seeing.
  const edges: GraphEdge[] = [];
  for (const { node } of nodes) {
    for (const edge of index.outgoing.get(node.id) ?? []) {
      if (columns.has(edge.to) && keep(edge)) {
        edges.push(edge);
      }
    }
  }

  return { rootId, nodes, edges };
}

function walk(
  index: GraphIndex,
  rootId: string,
  depth: number,
  columns: Map<string, number>,
  direction: 'upstream' | 'downstream',
  keep: (edge: GraphEdge) => boolean,
): void {
  const sign = direction === 'upstream' ? -1 : 1;
  const edgesOf = (id: string): GraphEdge[] =>
    (direction === 'upstream' ? index.incoming.get(id) : index.outgoing.get(id)) ?? [];
  const otherEnd = (edge: GraphEdge): string =>
    direction === 'upstream' ? edge.from : edge.to;

  // Per-walk visited set. The graph is not a DAG; without this a feedback loop
  // never terminates.
  const seen = new Set<string>([rootId]);
  let frontier: string[] = [rootId];

  for (let hop = 1; hop <= depth; hop++) {
    const next: string[] = [];
    for (const id of frontier) {
      for (const edge of edgesOf(id)) {
        if (!keep(edge)) continue;
        const other = otherEnd(edge);
        if (seen.has(other)) continue;
        seen.add(other);
        next.push(other);

        const candidate = sign * hop;
        const existing = columns.get(other);
        if (existing === undefined || Math.abs(candidate) < Math.abs(existing)) {
          columns.set(other, candidate);
        }
      }
    }
    frontier = next;
  }
}

/** Above this many nodes a depth-2 view stops being readable at fit zoom. */
export const AUTO_DEPTH_MAX_NODES = 15;

/** The depth to show when the reader has not picked one. */
export function autoDepth(index: GraphIndex, rootId: string, options: EgoOptions = {}): 1 | 2 {
  return ego(index, rootId, 2, options).nodes.length <= AUTO_DEPTH_MAX_NODES ? 2 : 1;
}

/** A column-and-system bucket with more members than this folds into one node. */
export const FOLD_MIN_MEMBERS = 5;

export interface FoldGroup {
  id: string;
  system: string;
  column: number;
  members: GraphNode[];
}

export interface FoldedGraph extends EgoGraph {
  /**
   * Folded groups by id. Each also appears in `nodes` as a stand-in node with
   * that id and kind `group`, so the folded graph lays out like any ego graph.
   */
  groups: Map<string, FoldGroup>;
  /** Ids from `expanded` that name a group this graph would otherwise fold. */
  unfolded: string[];
}

const CONFIDENCE_RANK: Record<EdgeConfidence, number> = {
  documented: 0,
  provisional: 1,
  uncertain: 2,
};

/**
 * Collapse each column's nodes of one system into a single stand-in once there
 * are at least FOLD_MIN_MEMBERS of them, unless that group's id is in
 * `expanded`. The root never folds.
 *
 * Edges touching a folded member are redirected to its group; edges inside one
 * group vanish; redirected duplicates merge into one edge per (from, to, rel)
 * carrying the most certain confidence among them.
 */
export function fold(graph: EgoGraph, expanded: ReadonlySet<string>): FoldedGraph {
  const buckets = new Map<string, FoldGroup>();
  for (const { node, column } of graph.nodes) {
    if (column === 0) continue;
    const id = `fold:${column}:${node.system}`;
    const bucket = buckets.get(id) ?? { id, system: node.system, column, members: [] };
    bucket.members.push(node);
    buckets.set(id, bucket);
  }

  const groups = new Map<string, FoldGroup>();
  const unfolded: string[] = [];
  const groupOf = new Map<string, string>();
  for (const bucket of buckets.values()) {
    if (bucket.members.length < FOLD_MIN_MEMBERS) continue;
    if (expanded.has(bucket.id)) {
      unfolded.push(bucket.id);
      continue;
    }
    groups.set(bucket.id, bucket);
    for (const member of bucket.members) groupOf.set(member.id, bucket.id);
  }

  const nodes: EgoNode[] = [];
  const placed = new Set<string>();
  for (const entry of graph.nodes) {
    const groupId = groupOf.get(entry.node.id);
    if (groupId === undefined) {
      nodes.push(entry);
    } else if (!placed.has(groupId)) {
      placed.add(groupId);
      const group = groups.get(groupId)!;
      nodes.push({
        node: { id: groupId, name: group.system, system: group.system, kind: 'group' },
        column: group.column,
      });
    }
  }

  const merged = new Map<string, GraphEdge>();
  const edges: GraphEdge[] = [];
  for (const edge of graph.edges) {
    const fromGroup = groupOf.get(edge.from);
    const toGroup = groupOf.get(edge.to);
    if (fromGroup === undefined && toGroup === undefined) {
      edges.push(edge);
      continue;
    }
    const from = fromGroup ?? edge.from;
    const to = toGroup ?? edge.to;
    if (from === to) continue;
    const key = `${from}|${to}|${edge.rel}`;
    const existing = merged.get(key);
    if (existing === undefined) {
      const redirected = { ...edge, from, to };
      merged.set(key, redirected);
      edges.push(redirected);
    } else if (
      CONFIDENCE_RANK[edgeConfidence(edge)] < CONFIDENCE_RANK[edgeConfidence(existing)]
    ) {
      existing.confidence = edgeConfidence(edge);
    }
  }

  return { rootId: graph.rootId, nodes, edges, groups, unfolded };
}
