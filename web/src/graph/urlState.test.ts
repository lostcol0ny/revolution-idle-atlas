import { describe, expect, it } from 'vitest';
import { parseUrlState, toSearch, viewOf, type UrlState } from './urlState';

const EMPTY: UrlState = { nodeId: null, systemId: null, depth: null };

describe('parseUrlState', () => {
  it('reads a node, a system and a depth', () => {
    expect(parseUrlState('?node=attack-power&system=unity&depth=3')).toEqual({
      nodeId: 'attack-power',
      systemId: 'unity',
      depth: 3,
    });
  });

  it('reads an absent depth as auto', () => {
    expect(parseUrlState('?node=gold').depth).toBeNull();
  });

  it('reads an out-of-range or non-numeric depth as auto', () => {
    expect(parseUrlState('?depth=99').depth).toBeNull();
    expect(parseUrlState('?depth=0').depth).toBeNull();
    expect(parseUrlState('?depth=').depth).toBeNull();
    expect(parseUrlState('?depth=banana').depth).toBeNull();
  });

  it('reads empty values as unset', () => {
    expect(parseUrlState('')).toEqual(EMPTY);
    expect(parseUrlState('?node=&system=')).toEqual(EMPTY);
  });

  it('decodes percent-encoded ids', () => {
    expect(parseUrlState('?node=refine%20node&system=tarot%2Dchallenges')).toMatchObject({
      nodeId: 'refine node',
      systemId: 'tarot-challenges',
    });
  });

  it('takes the first value of a repeated key', () => {
    // The app only ever writes these via toSearch, so a repeat can arrive only
    // from a hand-edited URL. First-wins is what URLSearchParams does; assert it
    // so a later rewrite cannot quietly make a trailing ?depth=999 the winner.
    expect(parseUrlState('?depth=2&depth=999').depth).toBe(2);
    expect(parseUrlState('?node=a&node=b').nodeId).toBe('a');
  });
});

describe('toSearch', () => {
  it('omits every unset param', () => {
    expect(toSearch(EMPTY)).toBe('');
    expect(toSearch({ ...EMPTY, systemId: 'unity' })).toBe('?system=unity');
    expect(toSearch({ ...EMPTY, nodeId: 'gold' })).toBe('?node=gold');
  });

  it('writes an explicit depth and leaves auto out', () => {
    expect(toSearch({ ...EMPTY, nodeId: 'gold', depth: 3 })).toBe('?node=gold&depth=3');
    expect(toSearch({ ...EMPTY, nodeId: 'gold', depth: null })).not.toContain('depth');
  });

  it.each<UrlState>([
    EMPTY,
    { nodeId: 'relic-3', systemId: null, depth: 3 },
    { nodeId: null, systemId: 'tarot', depth: null },
    { nodeId: 'gold', systemId: 'revolution', depth: 1 },
    // Every id in today's graph.json is kebab-case ASCII, but ids come from a
    // hand-maintained YAML and nothing enforces that. Pin the property, not the
    // current data.
    { nodeId: 'a b&c=d#e+f%g', systemId: 'x?y/z', depth: null },
  ])('round-trips %o', (state) => {
    expect(parseUrlState(toSearch(state))).toEqual(state);
  });
});

describe('viewOf', () => {
  it('shows the overview when nothing is selected', () => {
    expect(viewOf(EMPTY)).toEqual({ kind: 'overview' });
  });

  it('shows a system table when only a system is selected', () => {
    expect(viewOf({ ...EMPTY, systemId: 'tarot' })).toEqual({ kind: 'system', systemId: 'tarot' });
  });

  it('shows the item graph when a node is selected, even alongside a system', () => {
    expect(viewOf({ ...EMPTY, nodeId: 'gold' })).toEqual({ kind: 'item', nodeId: 'gold' });
    expect(viewOf({ nodeId: 'gold', systemId: 'tarot', depth: 2 })).toEqual({
      kind: 'item',
      nodeId: 'gold',
    });
  });
});
