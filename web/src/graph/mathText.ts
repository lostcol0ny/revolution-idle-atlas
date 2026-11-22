/**
 * Prose from graph.json carries inline math as `$LaTeX$`. Outside math a
 * backslash escapes the next character (`\$` a dollar, `\\` a backslash); see
 * escape_prose in the pipeline. Inside math the LaTeX is kept verbatim for the
 * typesetter, and `\$` there is LaTeX's own dollar, not the closing delimiter.
 */
export interface TextSegment {
  readonly math: boolean;
  readonly text: string;
}

export function splitMath(source: string): TextSegment[] {
  const segments: TextSegment[] = [];
  let prose = '';
  let at = 0;
  while (at < source.length) {
    const char = source[at];
    if (char === '\\' && at + 1 < source.length) {
      prose += source[at + 1];
      at += 2;
    } else if (char === '$') {
      const close = closingDollar(source, at + 1);
      // An unclosed `$` is not math; it stays in the prose as written.
      if (close === -1) {
        prose += char;
        at += 1;
        continue;
      }
      const latex = source.slice(at + 1, close).trim();
      if (latex.length > 0) {
        if (prose.length > 0) segments.push({ math: false, text: prose });
        prose = '';
        segments.push({ math: true, text: latex });
      }
      at = close + 1;
    } else {
      prose += char;
      at += 1;
    }
  }
  if (prose.length > 0) segments.push({ math: false, text: prose });
  return segments;
}

/** The text a reader can search: delimiters and escapes gone, LaTeX as written. */
export function readableText(source: string): string {
  return splitMath(source)
    .map((segment) => segment.text)
    .join('');
}

function closingDollar(source: string, from: number): number {
  for (let at = from; at < source.length; at += 1) {
    if (source[at] === '\\') at += 1;
    else if (source[at] === '$') return at;
  }
  return -1;
}
