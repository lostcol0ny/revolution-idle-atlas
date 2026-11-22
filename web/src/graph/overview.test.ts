import { describe, expect, it } from 'vitest';
import { buildIndex } from './adjacency';
import { buildOverview } from './overview';
import type { EdgeConfidence, GraphDocument, Rel } from '../types';

const node = (id: string, system: string) => ({ id, name: id, system, kind: 'upgrade' }) as GraphDocument['nodes'][number];
const edge = (from: string, to: string, confidence?: EdgeConfidence, rel: Rel = 'boosts') =>
  ({ from, to, rel, source: 'test', confidence }) as GraphDocument['edges'][number];

const doc: GraphDocument = {
  version: 1,
  systems: [
    { id: 'infinity', name: 'Infinity' },
    { id: 'stars', name: 'Stars', parent: 'infinity' },
    { id: 'unity', name: 'Unity' },
    { id: 'tarot', name: 'Tarot', parent: 'unity' },
    { id: 'tarot-artifacts', name: 'Artifacts', parent: 'tarot' },
  ],
  nodes: [
    node('i1', 'infinity'),
    node('s1', 'stars'),
    node('u1', 'unity'),
    node('t1', 'tarot'),
    node('a1', 'tarot-artifacts'),
  ],
  edges: [
    edge('s1', 'i1', 'documented'), // intra after roll-up
    edge('a1', 't1'), // intra after roll-up
    edge('s1', 't1', 'documented'),
    edge('i1', 'a1', 'uncertain'),
    edge('i1', 't1', 'provisional'),
    edge('t1', 'u1', 'uncertain'),
    // Not boosts: must neither add to an existing line nor create a new one.
    edge('i1', 't1', 'documented', 'requires'),
    edge('u1', 'i1', 'documented', 'unlocks'),
  ],
};

const overview = buildOverview(buildIndex(doc));

describe('buildOverview', () => {
  it('rolls non-Unity subsystems into their root and deeper Unity ones into the subsystem', () => {
    expect(overview.systems).toEqual([
      { id: 'infinity', name: 'Infinity', count: 2 },
      { id: 'unity', name: 'Unity', count: 1 },
      { id: 'tarot', name: 'Tarot', count: 2 },
    ]);
  });

  it('drops edges within one displayed system and counts only cross-system boosts by confidence', () => {
    const byKey = Object.fromEntries(overview.edges.map((e) => [`${e.from}>${e.to}`, e]));
    expect(Object.keys(byKey).sort()).toEqual(['infinity>tarot', 'tarot>unity']);
    expect(byKey['infinity>tarot']).toMatchObject({ total: 3, established: 2, uncertain: 1 });
    expect(byKey['tarot>unity']).toMatchObject({ total: 1, established: 0, uncertain: 1 });
  });
});
