import type { GraphDocument, GraphEdge, GraphNode } from '../types';

function node(id: string, overrides: Partial<GraphNode> = {}): GraphNode {
  return { id, name: id, system: 'unity', kind: 'stat', ...overrides };
}

function edge(from: string, to: string, overrides: Partial<GraphEdge> = {}): GraphEdge {
  return { from, to, rel: 'boosts', source: 'observed', ...overrides };
}

/** a -> b -> c -> d, plus an unconnected node `lonely`. */
export const chainDoc: GraphDocument = {
  version: 1,
  nodes: [node('a'), node('b'), node('c'), node('d'), node('lonely')],
  edges: [edge('a', 'b'), edge('b', 'c'), edge('c', 'd')],
};

/** a -> b -> c -> a, a two-plus length feedback loop. */
export const cycleDoc: GraphDocument = {
  version: 1,
  nodes: [node('a'), node('b'), node('c')],
  edges: [edge('a', 'b'), edge('b', 'c'), edge('c', 'a')],
};

/**
 * a -> b, a -> c, b -> d, c -> d, and additionally b -> c.
 * The b -> c edge is the one a spanning tree would drop but an induced
 * subgraph must keep.
 */
export const diamondDoc: GraphDocument = {
  version: 1,
  nodes: [node('a'), node('b'), node('c'), node('d')],
  edges: [
    edge('a', 'b'),
    edge('a', 'c'),
    edge('b', 'd'),
    edge('c', 'd'),
    edge('b', 'c'),
  ],
};
