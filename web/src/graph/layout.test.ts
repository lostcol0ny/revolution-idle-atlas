import { describe, expect, it } from 'vitest';
import { buildIndex } from './adjacency';
import { breakCycles } from './cycles';
import { ego } from './ego';
import { chainDoc, cycleDoc, diamondDoc } from './fixtures';
import { layout } from './layout';

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
});
