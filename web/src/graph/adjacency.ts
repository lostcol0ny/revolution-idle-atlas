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

  // The pipeline rejects unresolvable references, so an edge endpoint that is
  // not in the node map cannot occur in a valid document. Optional chaining
  // makes a malformed one drop out silently rather than crash the app.
  for (const edge of doc.edges) {
    outgoing.get(edge.from)?.push(edge);
    incoming.get(edge.to)?.push(edge);
  }

  return { nodes, incoming, outgoing, order };
}
