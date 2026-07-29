import type { GraphDocument, GraphEdge, GraphNode } from '../types';

export interface GraphIndex {
  nodes: Map<string, GraphNode>;
  incoming: Map<string, GraphEdge[]>;
  outgoing: Map<string, GraphEdge[]>;
  /** Node ids in document order, which the pipeline emits deterministically. */
  order: string[];
}

export function buildIndex(doc: GraphDocument): GraphIndex {
  const nodes = new Map<string, GraphNode>();
  const incoming = new Map<string, GraphEdge[]>();
  const outgoing = new Map<string, GraphEdge[]>();
  const order: string[] = [];

  for (const node of doc.nodes) {
    nodes.set(node.id, node);
    incoming.set(node.id, []);
    outgoing.set(node.id, []);
    order.push(node.id);
  }

  // The pipeline guarantees referential integrity, but that guarantee is
  // enforced outside this codebase — in a different language's CI job — and
  // nothing on the TypeScript path from fetch through parseGraph validates
  // edge endpoints. So a violation is warned about rather than assumed away.
  // Warn and continue: one bad edge should not take down the whole viewer.
  for (const edge of doc.edges) {
    const out = outgoing.get(edge.from);
    const inc = incoming.get(edge.to);
    if (out === undefined || inc === undefined) {
      console.warn(`buildIndex: ignoring edge with unknown endpoint: ${edge.from} -> ${edge.to}`);
      continue;
    }
    out.push(edge);
    inc.push(edge);
  }

  return { nodes, incoming, outgoing, order };
}
