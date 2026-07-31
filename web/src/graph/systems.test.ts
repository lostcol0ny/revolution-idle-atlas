import { describe, expect, it } from 'vitest';
import type { GraphSystem } from '../types';
import { buildSystemTree } from './systems';

// The shape the real document declares: Refine Tree sits under Minerals, which
// sits under Unity.
const NESTED: GraphSystem[] = [
  { id: 'unity', name: 'Unity' },
  { id: 'minerals', name: 'Minerals', parent: 'unity' },
  { id: 'refine-tree', name: 'Refine Tree', parent: 'minerals' },
];

function counts(entries: Record<string, number>): Map<string, number> {
  return new Map(Object.entries(entries));
}

describe('buildSystemTree', () => {
  it('nests a system under its declared parent', () => {
    const tree = buildSystemTree(NESTED, counts({ unity: 1, minerals: 1, 'refine-tree': 1 }));
    expect(tree.map((n) => n.id)).toEqual(['unity']);
    expect(tree[0].children.map((n) => n.id)).toEqual(['minerals']);
    expect(tree[0].children[0].children.map((n) => n.id)).toEqual(['refine-tree']);
  });

  it('rolls descendant counts up into every ancestor', () => {
    const tree = buildSystemTree(NESTED, counts({ unity: 4, minerals: 14, 'refine-tree': 136 }));
    const unity = tree[0];
    const minerals = unity.children[0];
    // Distinct at every level, so a roll-up that stops one level short, or that
    // reports the direct count, lands on a different number than the total.
    expect(unity.direct).toBe(4);
    expect(unity.total).toBe(154);
    expect(minerals.direct).toBe(14);
    expect(minerals.total).toBe(150);
    expect(minerals.children[0].total).toBe(136);
  });

  it('uses the declared display name', () => {
    const tree = buildSystemTree(NESTED, counts({ 'refine-tree': 1 }));
    expect(tree[0].children[0].children[0].name).toBe('Refine Tree');
  });

  it('falls back to the raw id when a system is never declared', () => {
    const tree = buildSystemTree([], counts({ 'refine-tree': 1 }));
    expect(tree.map((n) => [n.id, n.name])).toEqual([['refine-tree', 'refine-tree']]);
  });

  it('keeps an undeclared system reachable by rooting it', () => {
    const tree = buildSystemTree(NESTED, counts({ unity: 1, mystery: 2 }));
    expect(tree.map((n) => n.id).sort()).toEqual(['mystery', 'unity']);
  });

  it('drops a declared system that holds no nodes anywhere', () => {
    const tree = buildSystemTree(NESTED, counts({ unity: 1 }));
    expect(tree[0].children).toEqual([]);
  });

  it('keeps an empty parent whose descendants hold nodes', () => {
    // Unity itself has no direct nodes here. Dropping it on that basis would
    // take Minerals and Refine Tree with it.
    const tree = buildSystemTree(NESTED, counts({ 'refine-tree': 136 }));
    expect(tree.map((n) => n.id)).toEqual(['unity']);
    expect(tree[0].direct).toBe(0);
    expect(tree[0].total).toBe(136);
  });

  it('orders siblings by the declared order, not alphabetically', () => {
    // Alphabetically these reverse: `elements` precedes `tarot`, while the
    // declared order puts `tarot` first. A sort that ignores the declared order
    // cannot pass this.
    const systems: GraphSystem[] = [
      { id: 'unity', name: 'Unity' },
      { id: 'elements', name: 'Elements', parent: 'unity' },
      { id: 'tarot', name: 'Tarot', parent: 'unity' },
    ];
    const tree = buildSystemTree(systems, counts({ elements: 1, tarot: 1 }));
    expect(tree[0].children.map((n) => n.id)).toEqual(['tarot', 'elements']);
  });

  it('sorts undeclared systems after declared ones', () => {
    // `aaa` would come first under any alphabetical ordering.
    const tree = buildSystemTree(NESTED, counts({ unity: 1, aaa: 1 }));
    expect(tree.map((n) => n.id)).toEqual(['unity', 'aaa']);
  });

  it('terminates and keeps every system when a parent chain loops', () => {
    const looped: GraphSystem[] = [
      { id: 'a', name: 'A', parent: 'b' },
      { id: 'b', name: 'B', parent: 'a' },
    ];
    const tree = buildSystemTree(looped, counts({ a: 1, b: 1 }));
    expect(tree.map((n) => n.id).sort()).toEqual(['a', 'b']);
  });

  it('ignores a parent that is not itself a system', () => {
    const orphan: GraphSystem[] = [{ id: 'relics', name: 'Relics', parent: 'nonexistent' }];
    const tree = buildSystemTree(orphan, counts({ relics: 3 }));
    expect(tree.map((n) => [n.id, n.total])).toEqual([['relics', 3]]);
  });
});
