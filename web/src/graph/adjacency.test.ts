import { describe, expect, it, vi } from 'vitest';
import { buildIndex } from './adjacency';
import { chainDoc } from './fixtures';
import type { GraphDocument } from '../types';

describe('buildIndex', () => {
  it('maps every node by id', () => {
    const index = buildIndex(chainDoc);
    expect(index.nodes.size).toBe(5);
    expect(index.nodes.get('b')?.name).toBe('b');
  });

  it('records outgoing edges', () => {
    const index = buildIndex(chainDoc);
    expect(index.outgoing.get('b')?.map((e) => e.to)).toEqual(['c']);
  });

  it('records incoming edges', () => {
    const index = buildIndex(chainDoc);
    expect(index.incoming.get('c')?.map((e) => e.from)).toEqual(['b']);
  });

  it('gives an edgeless node empty lists rather than omitting it', () => {
    const index = buildIndex(chainDoc);
    expect(index.incoming.get('lonely')).toEqual([]);
    expect(index.outgoing.get('lonely')).toEqual([]);
  });

  it('preserves document node order', () => {
    const index = buildIndex(chainDoc);
    expect(index.order).toEqual(['a', 'b', 'c', 'd', 'lonely']);
  });

  it('warns about and drops an edge with an unknown endpoint', () => {
    // Deliberately local rather than in fixtures.ts: the shared fixtures are
    // imported by later tasks and must stay referentially valid.
    const danglingDoc: GraphDocument = {
      version: 1,
      nodes: [{ id: 'a', name: 'a', system: 'unity', kind: 'stat' }],
      edges: [{ from: 'a', to: 'ghost', rel: 'boosts', source: 'observed' }],
    };

    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    try {
      const index = buildIndex(danglingDoc);
      expect(index.outgoing.get('a')).toEqual([]);
      expect(index.nodes.has('ghost')).toBe(false);
      expect(warn).toHaveBeenCalled();
    } finally {
      warn.mockRestore();
    }
  });
});
