import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import type { GraphDocument } from '../types';
import { buildIndex } from './adjacency';
import { AUTO_DEPTH_MAX_NODES, autoDepth, ego, FOLD_MIN_MEMBERS, fold, UnknownNodeError } from './ego';
import { chainDoc, cycleDoc, diamondDoc } from './fixtures';
import { parseGraph } from './load';

const columnsOf = (graph: { nodes: { node: { id: string }; column: number }[] }) =>
  Object.fromEntries(graph.nodes.map((n) => [n.node.id, n.column]));

describe('ego', () => {
  it('places the root at column 0', () => {
    const graph = ego(buildIndex(chainDoc), 'b', 1);
    expect(columnsOf(graph)['b']).toBe(0);
  });

  it('gives upstream nodes negative columns and downstream positive', () => {
    // chain is a -> b -> c -> d, rooted at c
    const graph = ego(buildIndex(chainDoc), 'c', 2);
    expect(columnsOf(graph)).toEqual({ a: -2, b: -1, c: 0, d: 1 });
  });

  it('respects the depth boundary', () => {
    const graph = ego(buildIndex(chainDoc), 'c', 1);
    expect(columnsOf(graph)).toEqual({ b: -1, c: 0, d: 1 });
  });

  it('excludes nodes with no path to the root', () => {
    const graph = ego(buildIndex(chainDoc), 'a', 3);
    expect(columnsOf(graph)).not.toHaveProperty('lonely');
  });

  it('breaks ties toward upstream when a node is reachable both ways', () => {
    // In cycleDoc (a -> b -> c -> a) rooted at a, b is downstream at 1 hop
    // and upstream at 2 hops; c is upstream at 1 hop and downstream at 2.
    const graph = ego(buildIndex(cycleDoc), 'a', 2);
    expect(columnsOf(graph)).toEqual({ a: 0, b: 1, c: -1 });
  });

  it('breaks ties toward upstream for an equidistant node', () => {
    // The cycleDoc case above is settled by one direction being strictly
    // shorter, so it never evaluates the equal-distance branch. Here a and b
    // point at each other: rooted at a, b sits at hop 1 both ways, so only the
    // deliberate upstream-wins rule can decide it. Guards against someone
    // swapping the order of the two walk() calls in ego().
    const biDoc: GraphDocument = {
      version: 1,
      nodes: [
        { id: 'a', name: 'a', system: 'unity', kind: 'stat' },
        { id: 'b', name: 'b', system: 'unity', kind: 'stat' },
      ],
      edges: [
        { from: 'a', to: 'b', rel: 'boosts', source: 'observed' },
        { from: 'b', to: 'a', rel: 'boosts', source: 'observed' },
      ],
    };
    const graph = ego(buildIndex(biDoc), 'a', 1);
    expect(columnsOf(graph)).toEqual({ a: 0, b: -1 });
  });

  it('terminates on a cycle', () => {
    const graph = ego(buildIndex(cycleDoc), 'a', 10);
    expect(graph.nodes).toHaveLength(3);
  });

  it('returns the induced subgraph, not a spanning tree', () => {
    // diamondDoc rooted at a, depth 2, reaches a, b, c, d. The b -> c edge is
    // never traversed by BFS but both endpoints are present, so it must appear.
    const graph = ego(buildIndex(diamondDoc), 'a', 2);
    const pairs = graph.edges.map((e) => `${e.from}->${e.to}`);
    expect(pairs).toContain('b->c');
    expect(pairs).toHaveLength(5);
  });

  it('excludes edges with an endpoint outside the subgraph', () => {
    const graph = ego(buildIndex(chainDoc), 'a', 1);
    const pairs = graph.edges.map((e) => `${e.from}->${e.to}`);
    expect(pairs).toEqual(['a->b']);
  });

  it('throws a named error for an unknown root', () => {
    expect(() => ego(buildIndex(chainDoc), 'nope', 2)).toThrow(UnknownNodeError);
  });
});

describe('ego against the real committed artifact', () => {
  // Contract test. The Python pipeline and this frontend agree on a schema that
  // nothing enforces across the language boundary; loading the real file is
  // what catches drift. Reads from disk — never the network.
  const url = new URL('../../../public/graph.json', import.meta.url);
  const doc = parseGraph(JSON.parse(readFileSync(url, 'utf-8')));

  it('produces a non-empty ego graph for damage-mult at depth 2', () => {
    const graph = ego(buildIndex(doc), 'damage-mult', 2);
    expect(graph.nodes.length).toBeGreaterThan(1);
    expect(graph.edges.length).toBeGreaterThan(0);
    expect(graph.nodes.some((n) => n.column < 0)).toBe(true);
  });

  it('falls back to depth 1 for damage-mult, whose depth-2 graph is a wall of nodes', () => {
    expect(ego(buildIndex(doc), 'damage-mult', 2).nodes.length).toBeGreaterThan(AUTO_DEPTH_MAX_NODES);
    expect(autoDepth(buildIndex(doc), 'damage-mult')).toBe(1);
  });
});

const n = (id: string, system = 'unity'): GraphDocument['nodes'][number] => ({
  id,
  name: id,
  system,
  kind: 'stat',
});
const e = (
  from: string,
  to: string,
  confidence?: 'documented' | 'provisional' | 'uncertain',
): GraphDocument['edges'][number] => ({ from, to, rel: 'boosts', source: 'observed', confidence });

describe('ego without guessed links', () => {
  // a -> r is documented; b -> r is a guess and c reaches r only through b.
  // e reaches r directly by a guess and, one hop further, through a.
  const doc: GraphDocument = {
    version: 1,
    nodes: [n('r'), n('a'), n('b'), n('c'), n('e')],
    edges: [e('a', 'r'), e('b', 'r', 'uncertain'), e('c', 'b'), e('e', 'r', 'uncertain'), e('e', 'a')],
  };
  const index = buildIndex(doc);

  it('keeps guessed links and what they reach by default', () => {
    expect(columnsOf(ego(index, 'r', 2))).toEqual({ r: 0, a: -1, b: -1, c: -2, e: -1 });
  });

  it('drops guessed links and nodes reachable only through them', () => {
    const graph = ego(index, 'r', 2, { includeUncertain: false });
    expect(columnsOf(graph)).toEqual({ r: 0, a: -1, e: -2 });
    expect(graph.edges.map((edge) => `${edge.from}->${edge.to}`)).toEqual(['a->r', 'e->a']);
  });
});

describe('autoDepth', () => {
  // `fan` upstream neighbours of r, each with one more node upstream of it, so
  // the depth-2 graph has 1 + 2 * fan nodes.
  const fanDoc = (fan: number, confidence?: 'uncertain'): GraphDocument => {
    const doc: GraphDocument = { version: 1, nodes: [n('r')], edges: [] };
    for (let i = 0; i < fan; i++) {
      doc.nodes.push(n(`near${i}`), n(`far${i}`));
      doc.edges.push(e(`near${i}`, 'r', i === 0 ? undefined : confidence), e(`far${i}`, `near${i}`));
    }
    return doc;
  };

  it(`picks 2 while the depth-2 graph has at most ${AUTO_DEPTH_MAX_NODES} nodes`, () => {
    expect(autoDepth(buildIndex(fanDoc(7)), 'r')).toBe(2);
  });

  it('drops to 1 once the depth-2 graph is larger', () => {
    expect(autoDepth(buildIndex(fanDoc(8)), 'r')).toBe(1);
  });

  it('counts only what is shown when guessed links are hidden', () => {
    const index = buildIndex(fanDoc(8, 'uncertain'));
    expect(autoDepth(index, 'r')).toBe(1);
    expect(autoDepth(index, 'r', { includeUncertain: false })).toBe(2);
  });
});

describe('fold', () => {
  // Five relics and four tarot cards feed r; two relics hang off it downstream.
  const relics = ['r1', 'r2', 'r3', 'r4', 'r5'];
  const tarot = ['t1', 't2', 't3', 't4'];
  const doc: GraphDocument = {
    version: 1,
    nodes: [
      n('r'),
      ...relics.map((id) => n(id, 'relics')),
      ...tarot.map((id) => n(id, 'tarot')),
      n('d1', 'relics'),
      n('d2', 'relics'),
    ],
    edges: [
      ...relics.map((id) => e(id, 'r', id === 'r3' ? undefined : 'uncertain')),
      ...tarot.map((id) => e(id, 'r')),
      e('r1', 'r2'),
      e('t1', 'r4'),
      e('r', 'd1'),
      e('r', 'd2'),
    ],
  };
  const graph = ego(buildIndex(doc), 'r', 1);
  const pairs = (g: { edges: { from: string; to: string }[] }) =>
    g.edges.map((edge) => `${edge.from}->${edge.to}`).sort();

  it(`folds a column's system once it reaches ${FOLD_MIN_MEMBERS} members, per side`, () => {
    const folded = fold(graph, new Set());
    expect([...folded.groups.values()].map((g) => [g.system, g.column, g.members.length])).toEqual([
      ['relics', -1, 5],
    ]);
    // r, the relic group, four tarot cards, two downstream relics.
    expect(folded.nodes).toHaveLength(8);
    expect(folded.nodes.map((entry) => entry.node.id)).not.toContain('r1');
  });

  it('redirects member edges to the group, merging duplicates and dropping internal ones', () => {
    const folded = fold(graph, new Set());
    const [group] = folded.groups.keys();
    expect(pairs(folded)).toEqual(
      [`${group}->r`, `t1->${group}`, 'r->d1', 'r->d2', 't1->r', 't2->r', 't3->r', 't4->r'].sort(),
    );
    // One of the five merged edges is documented, so the merged edge is too.
    expect(folded.edges.find((edge) => edge.from === group)?.confidence).toBe('documented');
  });

  it('leaves an expanded group unfolded', () => {
    const [group] = fold(graph, new Set()).groups.keys();
    const folded = fold(graph, new Set([group!]));
    expect(folded.groups.size).toBe(0);
    expect(folded.unfolded).toEqual([group]);
    expect(folded.nodes).toHaveLength(graph.nodes.length);
    expect(pairs(folded)).toEqual(pairs(graph));
  });
});
