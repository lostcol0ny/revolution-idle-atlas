import { describe, expect, it } from 'vitest';
import { GraphFormatError, parseGraph } from './load';

const valid = { version: 1, nodes: [], edges: [] };

describe('parseGraph', () => {
  it('accepts a version 1 document', () => {
    expect(parseGraph(valid)).toEqual(valid);
  });

  it('rejects a future version with a readable message', () => {
    expect(() => parseGraph({ ...valid, version: 2 })).toThrow(GraphFormatError);
    expect(() => parseGraph({ ...valid, version: 2 })).toThrow(
      'this build expects graph format v1, got v2',
    );
  });

  it('rejects a document with no version', () => {
    expect(() => parseGraph({ nodes: [], edges: [] })).toThrow(GraphFormatError);
  });

  it('rejects a non-object', () => {
    expect(() => parseGraph('nope')).toThrow(GraphFormatError);
    expect(() => parseGraph(null)).toThrow(GraphFormatError);
  });

  it('rejects a document missing nodes or edges', () => {
    expect(() => parseGraph({ version: 1, nodes: [] })).toThrow(GraphFormatError);
    expect(() => parseGraph({ version: 1, edges: [] })).toThrow(GraphFormatError);
  });
});

it('preserves the optional systems array', () => {
  const doc = parseGraph({
    version: 1,
    nodes: [],
    edges: [],
    systems: [{ id: 'unity', name: 'Unity' }],
  });
  expect(doc.systems).toEqual([{ id: 'unity', name: 'Unity' }]);
});

// `toBeUndefined()` would be unfalsifiable here: it passes both when the key is
// absent and when it is present-and-undefined, so a plain `systems: doc.systems`
// passthrough would satisfy it. `in` is the only form that pins key absence, and
// key absence is what the conditional spread in Step 3 exists to produce.
it('leaves systems off the returned object entirely when the document omits it', () => {
  expect('systems' in parseGraph({ version: 1, nodes: [], edges: [] })).toBe(false);
});

it('rejects a systems field that is not an array', () => {
  expect(() => parseGraph({ version: 1, nodes: [], edges: [], systems: {} })).toThrow(
    GraphFormatError,
  );
});
