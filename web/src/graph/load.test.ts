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
