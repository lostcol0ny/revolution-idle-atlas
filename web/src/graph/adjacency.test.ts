import { describe, expect, it } from 'vitest';
import { buildIndex } from './adjacency';
import { chainDoc } from './fixtures';

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
});
