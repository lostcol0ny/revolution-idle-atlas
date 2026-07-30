import { describe, expect, it } from 'vitest';
import type { GraphDocument } from '../types';
import { buildIndex } from './adjacency';
import { breakCycles } from './cycles';
import { ego } from './ego';
import { chainDoc, cycleDoc, diamondDoc } from './fixtures';

describe('breakCycles', () => {
  it('finds no back-edges in an acyclic graph', () => {
    const graph = ego(buildIndex(chainDoc), 'a', 3);
    const { dag, backEdges } = breakCycles(graph);
    expect(backEdges).toEqual([]);
    expect(dag.edges).toHaveLength(graph.edges.length);
  });

  it('finds no back-edges in a diamond', () => {
    const graph = ego(buildIndex(diamondDoc), 'a', 2);
    expect(breakCycles(graph).backEdges).toEqual([]);
  });

  it('removes exactly one edge from a three-node cycle', () => {
    const graph = ego(buildIndex(cycleDoc), 'a', 3);
    const { dag, backEdges } = breakCycles(graph);
    expect(backEdges).toHaveLength(1);
    expect(dag.edges).toHaveLength(graph.edges.length - 1);
  });

  it('leaves the resulting graph acyclic', () => {
    const graph = ego(buildIndex(cycleDoc), 'a', 3);
    const { dag } = breakCycles(graph);
    expect(breakCycles(dag).backEdges).toEqual([]);
  });

  it('preserves nodes and the root', () => {
    const graph = ego(buildIndex(cycleDoc), 'a', 3);
    const { dag } = breakCycles(graph);
    expect(dag.nodes).toEqual(graph.nodes);
    expect(dag.rootId).toBe('a');
  });

  it('preserves object identity of back-edges', () => {
    const graph = ego(buildIndex(cycleDoc), 'a', 3);
    const { backEdges } = breakCycles(graph);
    expect(backEdges).toHaveLength(1);
    // The renderer styles back-edges via new Set(backEdges).has(edge), an
    // identity lookup, so this must be the same object and not an equal one.
    expect(graph.edges).toContain(backEdges[0]);
  });

  it('classifies a self-loop as a back-edge', () => {
    const selfDoc: GraphDocument = {
      version: 1,
      nodes: [{ id: 'a', name: 'a', system: 'unity', kind: 'stat' }],
      edges: [{ from: 'a', to: 'a', rel: 'boosts', source: 'observed' }],
    };
    const graph = ego(buildIndex(selfDoc), 'a', 1);
    const { dag, backEdges } = breakCycles(graph);
    expect(backEdges).toHaveLength(1);
    expect(dag.edges).toHaveLength(0);
  });
});
