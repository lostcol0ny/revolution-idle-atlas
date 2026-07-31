import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { buildIndex } from './adjacency';
import { breakCycles } from './cycles';
import { ego } from './ego';
import { chainDoc, cycleDoc, diamondDoc } from './fixtures';
import { NODE_HEIGHT, layout } from './layout';
import { parseGraph } from './load';

describe('layout', () => {
  it('assigns a position to every node', () => {
    const { dag } = breakCycles(ego(buildIndex(chainDoc), 'c', 2));
    const positions = layout(dag);
    expect(positions.size).toBe(dag.nodes.length);
    for (const { node } of dag.nodes) {
      expect(positions.has(node.id)).toBe(true);
    }
  });

  it('produces finite coordinates', () => {
    const { dag } = breakCycles(ego(buildIndex(diamondDoc), 'a', 2));
    for (const position of layout(dag).values()) {
      expect(Number.isFinite(position.x)).toBe(true);
      expect(Number.isFinite(position.y)).toBe(true);
    }
  });

  it('places upstream columns left of the root and downstream right', () => {
    // chain a -> b -> c -> d rooted at c gives columns a:-2 b:-1 c:0 d:1
    const { dag } = breakCycles(ego(buildIndex(chainDoc), 'c', 2));
    const positions = layout(dag);
    const x = (id: string) => positions.get(id)?.x ?? Number.NaN;
    expect(x('a')).toBeLessThan(x('b'));
    expect(x('b')).toBeLessThan(x('c'));
    expect(x('c')).toBeLessThan(x('d'));
  });

  it('gives nodes in the same column the same x', () => {
    const { dag } = breakCycles(ego(buildIndex(diamondDoc), 'a', 2));
    const positions = layout(dag);
    const byColumn = new Map<number, number[]>();
    for (const { node, column } of dag.nodes) {
      const xs = byColumn.get(column) ?? [];
      xs.push(positions.get(node.id)?.x ?? Number.NaN);
      byColumn.set(column, xs);
    }
    for (const xs of byColumn.values()) {
      expect(new Set(xs).size).toBe(1);
    }
  });

  it('handles a graph whose cycle was broken', () => {
    const { dag } = breakCycles(ego(buildIndex(cycleDoc), 'a', 3));
    expect(layout(dag).size).toBe(3);
  });

  it('handles a single isolated root', () => {
    const { dag } = breakCycles(ego(buildIndex(chainDoc), 'lonely', 2));
    const positions = layout(dag);
    expect(positions.size).toBe(1);
    expect(Number.isFinite(positions.get('lonely')?.x)).toBe(true);
  });

  // Sweeps the shipped graph the way pipeline.test.ts does, so it takes that
  // test's declared budget for the same reason: the cost tracks the corpus, and
  // curating a few hundred more nodes should not turn this into a bare timeout
  // that reads as an overlap regression. It cleared the implicit 5s default
  // locally and missed it on a two-core runner, which is the worst version of
  // the failure -- green for whoever wrote the nodes, red for CI.
  it('never overlaps two nodes anywhere in the real graph', { timeout: 120_000 }, () => {
    const url = new URL('../../../public/graph.json', import.meta.url);
    const doc = parseGraph(JSON.parse(readFileSync(url, 'utf8')));
    const index = buildIndex(doc);
    const collisions: string[] = [];
    for (const id of index.order) {
      const { dag } = breakCycles(ego(index, id, 2));
      const placed = [...layout(dag)].map(([n, p]) => ({ n, ...p }));
      for (let i = 0; i < placed.length; i++) {
        for (let j = i + 1; j < placed.length; j++) {
          const a = placed[i]!,
            b = placed[j]!;
          if (a.x === b.x && Math.abs(a.y - b.y) < NODE_HEIGHT) {
            collisions.push(`root=${id}: ${a.n} vs ${b.n}`);
          }
        }
      }
    }
    expect(collisions).toEqual([]);
  });
});
