import * as dagre from '@dagrejs/dagre';
import type { EgoGraph } from './ego';

export interface Position {
  x: number;
  y: number;
}

export const NODE_WIDTH = 180;
export const NODE_HEIGHT = 56;
const COLUMN_GAP = 120;
const ROW_GAP = 24;

export function layout(dag: EgoGraph): Map<string, Position> {
  const graph = new dagre.graphlib.Graph();
  graph.setGraph({
    rankdir: 'LR',
    nodesep: ROW_GAP,
    ranksep: COLUMN_GAP,
    marginx: 24,
    marginy: 24,
  });
  graph.setDefaultEdgeLabel(() => ({}));

  for (const { node } of dag.nodes) {
    graph.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  }
  for (const edge of dag.edges) {
    graph.setEdge(edge.from, edge.to);
  }

  dagre.layout(graph);

  // x comes from the column value so upstream/downstream semantics are
  // guaranteed; y comes from dagre, which is doing the crossing minimisation.
  const columns = [...new Set(dag.nodes.map((n) => n.column))].sort((a, b) => a - b);
  const xByColumn = new Map<number, number>(
    columns.map((column, position) => [column, position * (NODE_WIDTH + COLUMN_GAP)]),
  );

  const positions = new Map<string, Position>();
  for (const { node, column } of dag.nodes) {
    const laid = graph.node(node.id) as { x?: number; y?: number } | undefined;
    const y = typeof laid?.y === 'number' && Number.isFinite(laid.y) ? laid.y : 0;
    positions.set(node.id, {
      x: xByColumn.get(column) ?? 0,
      y: y - NODE_HEIGHT / 2,
    });
  }

  return positions;
}
