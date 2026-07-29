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
});
