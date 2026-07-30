import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

import { parseGraph } from './load';
import { SYSTEM_COLOURS } from './palette';
import { buildSystemTree } from './systems';
import type { GraphDocument } from '../types';

// Reads the committed artifact off disk rather than over the network. The
// producer is Python and the consumer is TypeScript; nothing else in either
// suite would catch the two drifting apart.
const GRAPH_PATH = new URL('../../../public/graph.json', import.meta.url);

function rawGraph(): unknown {
  return JSON.parse(readFileSync(GRAPH_PATH, 'utf-8'));
}

function realGraph(): GraphDocument {
  return parseGraph(rawGraph());
}

describe('the committed graph.json', () => {
  it('parses under the version this build expects', () => {
    expect(realGraph().version).toBe(1);
  });

  it('declares a system hierarchy with at least one nested system', () => {
    const systems = realGraph().systems ?? [];
    expect(systems.length).toBeGreaterThan(0);
    expect(systems.some((s) => s.parent !== undefined)).toBe(true);
  });

  it('gives every node a system that the hierarchy declares', () => {
    const doc = realGraph();
    const declared = new Set((doc.systems ?? []).map((s) => s.id));
    const undeclared = [...new Set(doc.nodes.map((n) => n.system))].filter(
      (s) => !declared.has(s),
    );
    expect(undeclared).toEqual([]);
  });

  it('carries effect text on the relics', () => {
    const relics = realGraph().nodes.filter((n) => n.id.startsWith('relic-'));
    expect(relics.length).toBeGreaterThan(60);
    expect(relics.filter((n) => (n.effects ?? []).length > 0).length).toBeGreaterThan(60);
  });

  it('has more than the four effect edges v1 shipped with', () => {
    const effectEdges = realGraph().edges.filter((e) => e.rel !== 'requires');
    expect(effectEdges.length).toBeGreaterThan(50);
  });

  // The consumer-side half of the renderer's promise to omit an unset field
  // rather than write null. `types.ts` declares `op?: Op`, so a `null` in the
  // artifact is a value the app's own types claim cannot occur.
  //
  // This reads the RAW json, not the parsed document, and that is not an
  // arbitrary choice: `GraphEffect.op` is `Op | undefined`, so TypeScript
  // rejects `parsed.op === null` outright as a comparison between types with
  // no overlap, and `npm run typecheck` would fail. The mismatch being tested
  // is between the declared type and the bytes on disk, so the bytes on disk
  // are what the test has to look at.
  it('never carries a null where an optional effect field is unset', () => {
    const raw = rawGraph() as { nodes: { effects?: Record<string, unknown>[] }[] };
    const effects = raw.nodes.flatMap((n) => n.effects ?? []);
    expect(effects.length).toBeGreaterThan(300);
    expect(effects.filter((e) => Object.values(e).includes(null))).toEqual([]);
  });

  it('never points targets_effect past the end of a target node effects list', () => {
    const doc = realGraph();
    const effectCount = new Map(doc.nodes.map((n) => [n.id, (n.effects ?? []).length]));
    const bad = doc.edges.filter(
      (e) => e.targets_effect !== undefined && e.targets_effect >= (effectCount.get(e.to) ?? 0),
    );
    expect(bad).toEqual([]);
  });

  // Every distinct system value in graph.json must have a palette entry. A grey
  // swatch in the UI means a missing one, and that is checkable from disk
  // without a browser.
  // The failure message names the offending system ids rather than just
  // saying `false !== true`.
  // The sidebar nests on `parent`, so a hierarchy that flattens — every system
  // declaring no parent — would render correctly and still be wrong. Pinning one
  // known chain catches that, and `data/relationships.yaml` is where it breaks.
  it('nests Refine Tree under Minerals under Unity', () => {
    const doc = realGraph();
    const counts = new Map<string, number>();
    for (const node of doc.nodes) counts.set(node.system, (counts.get(node.system) ?? 0) + 1);
    const tree = buildSystemTree(doc.systems ?? [], counts);

    const unity = tree.find((s) => s.id === 'unity');
    const minerals = unity?.children.find((s) => s.id === 'minerals');
    const refineTree = minerals?.children.find((s) => s.id === 'refine-tree');
    expect(refineTree?.name).toBe('Refine Tree');
    // A parent's roll-up must exceed the child's, or the count is not rolling up.
    expect(minerals!.total).toBeGreaterThan(refineTree!.total);
    expect(unity!.total).toBeGreaterThan(minerals!.total);
  });

  it('every system id in the graph has a colour in SYSTEM_COLOURS', () => {
    const doc = realGraph();
    const systemIds = [...new Set(doc.nodes.map((n) => n.system))];
    const missing = systemIds.filter((id) => !(id in SYSTEM_COLOURS));
    expect(missing).toEqual([]);
  });
});
