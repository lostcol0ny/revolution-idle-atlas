import { describe, expect, it } from 'vitest';
import type { GraphDocument, GraphEdge, GraphNode } from '../types';
import { buildIndex } from './adjacency';
import {
  buildRows,
  filterRows,
  findSystem,
  nextSort,
  sortRows,
  subtreeIds,
  systemTree,
  type TableRow,
} from './table';

function node(id: string, overrides: Partial<GraphNode> = {}): GraphNode {
  return { id, name: id, system: 'minerals', kind: 'stat', ...overrides };
}

function edge(from: string, to: string, overrides: Partial<GraphEdge> = {}): GraphEdge {
  return { from, to, rel: 'boosts', source: 'observed', ...overrides };
}

// Unity > Minerals > Refine Tree, with one node in each and one elsewhere.
const doc: GraphDocument = {
  version: 1,
  systems: [
    { id: 'unity', name: 'Unity' },
    { id: 'minerals', name: 'Minerals', parent: 'unity' },
    { id: 'refine-tree', name: 'Refine Tree', parent: 'minerals' },
    { id: 'relics', name: 'Relics' },
  ],
  nodes: [
    node('relic-10', { name: 'Relic 10', system: 'relics', kind: 'relic' }),
    node('refine-1', {
      name: 'Refine Node 1',
      system: 'refine-tree',
      kind: 'tree-node',
      effects: [{ text: 'Increases mineral base', per_level: '+1 per level' }],
    }),
    node('ore', { name: 'Ore', description: 'Dug from the ground' }),
    node('relic-9', { name: 'Relic 9', system: 'relics', kind: 'relic' }),
    node('unity-pts', { name: 'Unity Points', system: 'unity', kind: 'currency' }),
  ],
  edges: [
    edge('ore', 'refine-1', { confidence: 'uncertain' }),
    // A second edge to the same target under the same rel collapses into the link above.
    edge('ore', 'refine-1', { confidence: 'documented', targets_effect: 0 }),
    edge('ore', 'relic-9', { confidence: 'uncertain' }),
    edge('ore', 'unity-pts', { rel: 'unlocks' }),
    edge('refine-1', 'ore', { rel: 'requires' }),
    edge('relic-10', 'ore'),
  ],
};

const index = buildIndex(doc);
const tree = systemTree(index);
const names = new Map([...index.systems].map((s) => [s.id, s.name]));

function rowsFor(systemId: string): TableRow[] {
  const system = findSystem(tree, systemId);
  if (system === null) throw new Error(`no system ${systemId}`);
  return buildRows(index, subtreeIds(system), names);
}

const ids = (rows: readonly TableRow[]) => rows.map((row) => row.node.id);

describe('findSystem', () => {
  it('finds a nested system', () => {
    expect(findSystem(tree, 'refine-tree')?.name).toBe('Refine Tree');
  });

  it('returns null for an unknown system', () => {
    expect(findSystem(tree, 'nope')).toBeNull();
  });
});

describe('buildRows', () => {
  it('includes descendant systems in dataset order', () => {
    expect(ids(rowsFor('unity'))).toEqual(['refine-1', 'ore', 'unity-pts']);
    expect(ids(rowsFor('minerals'))).toEqual(['refine-1', 'ore']);
    expect(ids(rowsFor('refine-tree'))).toEqual(['refine-1']);
  });

  it('names each row by its own system, not the page it is shown on', () => {
    expect(rowsFor('minerals').map((row) => row.systemName)).toEqual(['Refine Tree', 'Minerals']);
  });

  it('groups outgoing links by rel, boosts first, deduplicated to the firmest confidence', () => {
    const ore = rowsFor('minerals').find((row) => row.node.id === 'ore')!;
    expect(ore.outgoing).toEqual([
      {
        rel: 'boosts',
        links: [
          { id: 'refine-1', name: 'Refine Node 1', system: 'refine-tree', confidence: 'documented' },
          { id: 'relic-9', name: 'Relic 9', system: 'relics', confidence: 'uncertain' },
        ],
      },
      {
        rel: 'unlocks',
        links: [{ id: 'unity-pts', name: 'Unity Points', system: 'unity', confidence: 'documented' }],
      },
    ]);
    expect(ore.outgoingCount).toBe(3);
  });

  it('lists incoming links from the other end of each edge', () => {
    const ore = rowsFor('minerals').find((row) => row.node.id === 'ore')!;
    expect(ore.incoming.map((g) => [g.rel, g.links.map((l) => l.id)])).toEqual([
      ['boosts', ['relic-10']],
      ['requires', ['refine-1']],
    ]);
    expect(ore.incomingCount).toBe(2);
  });
});

describe('filterRows', () => {
  const rows = rowsFor('unity');

  it('matches name, description, effect text and per-level text, case-insensitively', () => {
    expect(ids(filterRows(rows, 'UNITY'))).toEqual(['unity-pts']);
    expect(ids(filterRows(rows, 'ground'))).toEqual(['ore']);
    expect(ids(filterRows(rows, 'mineral base'))).toEqual(['refine-1']);
    expect(ids(filterRows(rows, 'per level'))).toEqual(['refine-1']);
  });

  it('requires every word, in any order', () => {
    expect(ids(filterRows(rows, 'base increases'))).toEqual(['refine-1']);
    expect(ids(filterRows(rows, 'base ground'))).toEqual([]);
  });

  it('returns everything for a blank query', () => {
    expect(filterRows(rows, '   ')).toBe(rows);
  });
});

describe('sortRows', () => {
  const relics = rowsFor('relics');
  const unity = rowsFor('unity');

  it('keeps dataset order when unsorted', () => {
    expect(ids(sortRows(relics, null))).toEqual(['relic-10', 'relic-9']);
  });

  it('sorts names numerically', () => {
    expect(ids(sortRows(relics, { key: 'name', dir: 'asc' }))).toEqual(['relic-9', 'relic-10']);
    expect(ids(sortRows(relics, { key: 'name', dir: 'desc' }))).toEqual(['relic-10', 'relic-9']);
  });

  it('sorts by link count, ties in dataset order', () => {
    // ore: 3 out; refine-1: 1 out; unity-pts: 0 out.
    expect(ids(sortRows(unity, { key: 'outgoing', dir: 'desc' }))).toEqual(['ore', 'refine-1', 'unity-pts']);
    // refine-1: 1 in, unity-pts: 1 in, ore: 2 in.
    expect(ids(sortRows(unity, { key: 'incoming', dir: 'asc' }))).toEqual(['refine-1', 'unity-pts', 'ore']);
    expect(ids(sortRows(unity, { key: 'incoming', dir: 'desc' }))).toEqual(['ore', 'refine-1', 'unity-pts']);
  });

  it('sorts by kind', () => {
    expect(ids(sortRows(unity, { key: 'kind', dir: 'asc' }))).toEqual(['unity-pts', 'ore', 'refine-1']);
  });
});

describe('nextSort', () => {
  it('cycles first direction, other direction, then dataset order', () => {
    expect(nextSort(null, 'name')).toEqual({ key: 'name', dir: 'asc' });
    expect(nextSort({ key: 'name', dir: 'asc' }, 'name')).toEqual({ key: 'name', dir: 'desc' });
    expect(nextSort({ key: 'name', dir: 'desc' }, 'name')).toBeNull();
  });

  it('opens link counts descending', () => {
    expect(nextSort({ key: 'name', dir: 'asc' }, 'outgoing')).toEqual({ key: 'outgoing', dir: 'desc' });
  });
});
