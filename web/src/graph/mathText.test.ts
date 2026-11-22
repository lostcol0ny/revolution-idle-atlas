import { describe, expect, it } from 'vitest';
import { readableText, splitMath } from './mathText';

describe('splitMath', () => {
  it('leaves text without math as one prose segment', () => {
    expect(splitMath('Raises DP Gain to a power (^)')).toEqual([
      { math: false, text: 'Raises DP Gain to a power (^)' },
    ]);
    expect(splitMath('')).toEqual([]);
  });

  it('cuts inline math out of the sentence around it', () => {
    expect(splitMath('Formula is: $1 + \\frac {(x-3600)^2}{100}$ per level')).toEqual([
      { math: false, text: 'Formula is: ' },
      { math: true, text: '1 + \\frac {(x-3600)^2}{100}' },
      { math: false, text: ' per level' },
    ]);
    expect(splitMath('$a$$b$')).toEqual([
      { math: true, text: 'a' },
      { math: true, text: 'b' },
    ]);
  });

  it('reads escapes outside math as literal characters', () => {
    expect(splitMath('Costs \\$5, then $x$')).toEqual([
      { math: false, text: 'Costs $5, then ' },
      { math: true, text: 'x' },
    ]);
    // An escaped backslash must not escape the delimiter after it.
    expect(splitMath('C:\\\\$x$')).toEqual([
      { math: false, text: 'C:\\' },
      { math: true, text: 'x' },
    ]);
  });

  it('keeps LaTeX escapes inside math and does not close on them', () => {
    expect(splitMath('$a \\$ b \\\\$ c')).toEqual([
      { math: true, text: 'a \\$ b \\\\' },
      { math: false, text: ' c' },
    ]);
  });

  it('treats an unclosed or empty delimiter as prose', () => {
    expect(splitMath('costs $5')).toEqual([{ math: false, text: 'costs $5' }]);
    expect(splitMath('a $ $ b')).toEqual([{ math: false, text: 'a  b' }]);
  });
});

describe('readableText', () => {
  it('drops delimiters and escapes so a filter matches what is shown', () => {
    expect(readableText('Formula is: $1 + x^2$ (\\$)')).toBe('Formula is: 1 + x^2 ($)');
  });
});
