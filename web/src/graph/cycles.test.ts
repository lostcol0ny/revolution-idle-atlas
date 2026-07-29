import { describe, expect, it } from 'vitest';
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
});
