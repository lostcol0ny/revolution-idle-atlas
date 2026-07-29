import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { buildIndex } from './adjacency';
import { ego, UnknownNodeError } from './ego';
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

  it('produces a non-empty ego graph for attack-power at depth 2', () => {
    const graph = ego(buildIndex(doc), 'attack-power', 2);
    expect(graph.nodes.length).toBeGreaterThan(1);
    expect(graph.edges.length).toBeGreaterThan(0);
    expect(graph.nodes.some((n) => n.column < 0)).toBe(true);
  });
});
