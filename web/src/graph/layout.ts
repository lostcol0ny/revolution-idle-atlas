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
const ROW_PITCH = NODE_HEIGHT + ROW_GAP;

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
  // guaranteed rather than hoped for.
  const columns = [...new Set(dag.nodes.map((n) => n.column))].sort((a, b) => a - b);
  const xByColumn = new Map<number, number>(
    columns.map((column, position) => [column, position * (NODE_WIDTH + COLUMN_GAP)]),
  );

  // dagre's y is used only to ORDER nodes within a column, never as a coordinate.
  // Its non-overlap guarantee is a property of the x/y pair it assigns: it
  // separates nodes vertically precisely because it placed them at the same x.
  // Overriding x with the ego column voids that guarantee, because dagre's rank
  // partition is not the ego column partition — two nodes sharing a column but
  // sitting in different ranks each get an independent within-rank y, and nothing
  // reconciles them. Assigning y here at a fixed pitch makes non-overlap
  // structural instead of something we hope dagre avoided.
  const byColumn = new Map<number, { id: string; sort: number; seq: number }[]>();
  dag.nodes.forEach(({ node, column }, seq) => {
    const laid = graph.node(node.id) as { y?: number } | undefined;
    // NaN would make the comparator's ordering undefined; it can no longer reach
    // an output coordinate, but it must still be kept out of the sort key.
    const sort = typeof laid?.y === 'number' && Number.isFinite(laid.y) ? laid.y : 0;
    const bucket = byColumn.get(column) ?? [];
    bucket.push({ id: node.id, sort, seq });
    byColumn.set(column, bucket);
  });

  const positions = new Map<string, Position>();
  for (const [column, bucket] of byColumn) {
    // seq breaks ties so the layout is deterministic across re-renders.
    bucket.sort((a, b) => a.sort - b.sort || a.seq - b.seq);
    const offset = ((bucket.length - 1) * ROW_PITCH) / 2;
    bucket.forEach(({ id }, row) => {
      positions.set(id, {
        x: xByColumn.get(column) ?? 0,
        y: row * ROW_PITCH - offset,
      });
    });
  }

  return positions;
}
