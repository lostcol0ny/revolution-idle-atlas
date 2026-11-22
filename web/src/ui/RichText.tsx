import type KatexModule from 'katex';
import { useEffect, useMemo, useState } from 'react';
import { splitMath } from '../graph/mathText';
import './richText.css';

type Katex = typeof KatexModule;

// KaTeX is ~270 kB minified and only a handful of strings carry math, so it is
// fetched on first use instead of riding in the main bundle.
let katexLoad: Promise<Katex> | undefined;
const rendered = new Map<string, string | null>();

function renderMath(katex: Katex, latex: string): string | null {
  try {
    // KaTeX escapes everything it emits and `trust` is off by default, so the
    // markup is safe to inject even though the LaTeX comes from a public wiki.
    return katex.renderToString(latex, { throwOnError: false, errorColor: 'var(--muted)' });
  } catch {
    return null;
  }
}

function MathSpan({ latex }: { latex: string }) {
  const [html, setHtml] = useState(() => rendered.get(latex));
  useEffect(() => {
    if (rendered.has(latex)) return;
    let live = true;
    katexLoad ??= Promise.all([import('katex'), import('katex/dist/katex.min.css')]).then(
      ([module]) => module.default,
    );
    // A failed load leaves the LaTeX source showing, which is the fallback.
    katexLoad.then(
      (katex) => {
        rendered.set(latex, renderMath(katex, latex));
        if (live) setHtml(rendered.get(latex));
      },
      () => {},
    );
    return () => {
      live = false;
    };
  }, [latex]);

  // Until KaTeX arrives, and for good if it cannot typeset this, the reader
  // sees the LaTeX source rather than nothing.
  if (html === undefined || html === null) return <code className="richtext__math">{latex}</code>;
  return <span className="richtext__math" dangerouslySetInnerHTML={{ __html: html }} />;
}

/** Prose from graph.json, with its `$…$` segments typeset as inline math. */
export function RichText({ text }: { text: string }) {
  const segments = useMemo(() => splitMath(text), [text]);
  return segments.map((segment, position) =>
    segment.math ? <MathSpan key={position} latex={segment.text} /> : segment.text,
  );
}
