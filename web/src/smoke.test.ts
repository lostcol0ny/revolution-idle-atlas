import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

describe('toolchain', () => {
  it('can read the committed graph artifact from disk', () => {
    const url = new URL('../../public/graph.json', import.meta.url);
    const doc: unknown = JSON.parse(readFileSync(url, 'utf-8'));
    expect(doc).toHaveProperty('version', 1);
  });
});
