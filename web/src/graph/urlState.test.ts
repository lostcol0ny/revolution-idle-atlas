import { describe, expect, it } from 'vitest';
import { DEFAULT_DEPTH, parseUrlState, toSearch } from './urlState';

describe('parseUrlState', () => {
  it('reads a node and depth', () => {
    expect(parseUrlState('?node=attack-power&depth=3')).toEqual({
      nodeId: 'attack-power',
      depth: 3,
    });
  });

  it('defaults depth when absent', () => {
    expect(parseUrlState('?node=gold')).toEqual({
      nodeId: 'gold',
      depth: DEFAULT_DEPTH,
    });
  });

  it('defaults depth when out of range or not a number', () => {
    expect(parseUrlState('?depth=99').depth).toBe(DEFAULT_DEPTH);
    expect(parseUrlState('?depth=0').depth).toBe(DEFAULT_DEPTH);
    expect(parseUrlState('?depth=banana').depth).toBe(DEFAULT_DEPTH);
  });

  it('returns a null node for an empty search string', () => {
    expect(parseUrlState('')).toEqual({ nodeId: null, depth: DEFAULT_DEPTH });
    expect(parseUrlState('?node=')).toEqual({ nodeId: null, depth: DEFAULT_DEPTH });
  });

  it('decodes a percent-encoded node id', () => {
    expect(parseUrlState('?node=refine%20node').nodeId).toBe('refine node');
  });
});

describe('toSearch', () => {
  it('serialises node and depth', () => {
    expect(toSearch({ nodeId: 'attack-power', depth: 2 })).toBe(
      '?node=attack-power&depth=2',
    );
  });

  it('omits the node when there is no selection', () => {
    expect(toSearch({ nodeId: null, depth: 1 })).toBe('?depth=1');
  });

  it('round-trips', () => {
    const state = { nodeId: 'relic-3', depth: 3 } as const;
    expect(parseUrlState(toSearch(state))).toEqual(state);
  });

  it('round-trips an id containing characters the query string uses', () => {
    // Every id in today's graph.json is kebab-case ASCII, but ids come from a
    // hand-maintained YAML and nothing enforces that. Pin the property, not the
    // current data.
    const state = { nodeId: 'a b&c=d#e+f%g', depth: 2 } as const;
    expect(parseUrlState(toSearch(state))).toEqual(state);
  });
});

describe('parseUrlState with a repeated key', () => {
  it('takes the first value', () => {
    // The app only ever writes these via toSearch, so a repeat can arrive only
    // from a hand-edited URL. First-wins is what URLSearchParams does; assert it
    // so a later rewrite cannot quietly make a trailing ?depth=999 the winner.
    expect(parseUrlState('?depth=2&depth=999').depth).toBe(2);
    expect(parseUrlState('?node=a&node=b').nodeId).toBe('a');
  });
});
