import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { buildIndex } from './adjacency';
import { breakCycles } from './cycles';
import { ego } from './ego';
import { layout } from './layout';
import type { GraphDocument } from '../types';

// GraphView renders `subgraph.nodes` but takes coordinates from `layout(dag)`,
// so those two node sets must agree. Nothing else pins that: each of Tasks 3-6
// tests its own module, and neither `breakCycles` nor `layout` can see the
// mismatch from the inside. A node present in one set and absent from the other
// does not throw — it silently collapses onto GraphView's `?? { x: 0, y: 0 }`
// fallback and renders stacked at the origin.
//
// Falsified both ways: dropping a node from `breakCycles`'s returned `dag.nodes`
// fails this test. Skipping a node when populating dagre's graph does NOT, and
// should not — `layout` derives its output by iterating `dag.nodes` and uses
// dagre only for the within-column sort key, so coverage of `dag` is structural.
const doc = JSON.parse(
  readFileSync(new URL('../../../public/graph.json', import.meta.url), 'utf8'),
) as GraphDocument;
const index = buildIndex(doc);

describe('ego -> breakCycles -> layout', () => {
  it('positions every node of every ego graph at every selectable depth', () => {
    for (const rootId of index.order) {
      for (const depth of [1, 2, 3]) {
        const subgraph = ego(index, rootId, depth);
        const { dag } = breakCycles(subgraph);
        const positions = layout(dag);
        for (const { node } of subgraph.nodes) {
          expect(positions.has(node.id), `${rootId}@${depth} missing ${node.id}`).toBe(true);
        }
      }
    }
  });
});
