import type { GraphEdge, GraphNode } from '../types';
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

export class UnknownNodeError extends Error {
  constructor(id: string) {
    super(`unknown node id: ${id}`);
    this.name = 'UnknownNodeError';
  }
}

export function ego(index: GraphIndex, rootId: string, depth: number): EgoGraph {
  if (!index.nodes.has(rootId)) {
    throw new UnknownNodeError(rootId);
  }

  const columns = new Map<string, number>([[rootId, 0]]);

  // Upstream first, so an equal-distance tie resolves in its favour below.
  walk(index, rootId, depth, columns, 'upstream');
  walk(index, rootId, depth, columns, 'downstream');

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
      if (columns.has(edge.to)) {
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
