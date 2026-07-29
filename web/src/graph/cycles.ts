import type { GraphEdge } from '../types';
import type { EgoGraph } from './ego';

export interface BrokenGraph {
  /** The same graph with back-edges removed, safe to hand to dagre. */
  dag: EgoGraph;
  /** The removed edges, for the caller to render with distinct styling. */
  backEdges: GraphEdge[];
}

type Colour = 'white' | 'grey' | 'black';

export function breakCycles(graph: EgoGraph): BrokenGraph {
  const outgoing = new Map<string, GraphEdge[]>();
  const colour = new Map<string, Colour>();

  for (const { node } of graph.nodes) {
    outgoing.set(node.id, []);
    colour.set(node.id, 'white');
  }
  for (const edge of graph.edges) {
    outgoing.get(edge.from)?.push(edge);
  }

  const backEdges: GraphEdge[] = [];

  // An edge into a grey (currently on the DFS stack) node closes a cycle.
  // Ego graphs top out around 20 nodes, so recursion depth is not a concern.
  const visit = (id: string): void => {
    colour.set(id, 'grey');
    for (const edge of outgoing.get(id) ?? []) {
      const next = colour.get(edge.to);
      if (next === 'grey') {
        backEdges.push(edge);
      } else if (next === 'white') {
        visit(edge.to);
      }
    }
    colour.set(id, 'black');
  };

  for (const { node } of graph.nodes) {
    if (colour.get(node.id) === 'white') {
      visit(node.id);
    }
  }

  const removed = new Set(backEdges);
  return {
    dag: { ...graph, edges: graph.edges.filter((edge) => !removed.has(edge)) },
    backEdges,
  };
}
