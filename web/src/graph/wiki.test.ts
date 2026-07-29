import { describe, expect, it } from 'vitest';
import { sourceLabel, WIKI_BASE, wikiUrl } from './wiki';

describe('wikiUrl', () => {
  it('builds a page URL', () => {
    expect(wikiUrl('Relics')).toBe(`${WIKI_BASE}Relics`);
  });

  it('converts spaces to underscores', () => {
    expect(wikiUrl('Attacks Strategy')).toBe(`${WIKI_BASE}Attacks_Strategy`);
  });

  it('preserves a section anchor', () => {
    expect(wikiUrl('Unity#Attacks')).toBe(`${WIKI_BASE}Unity#Attacks`);
  });

  it('keeps subpage separators as path segments', () => {
    expect(wikiUrl('Minerals/Refine Tree')).toBe(`${WIKI_BASE}Minerals/Refine_Tree`);
  });

  it('returns null for absent or empty input', () => {
    expect(wikiUrl(undefined)).toBeNull();
    expect(wikiUrl('')).toBeNull();
    expect(wikiUrl('   ')).toBeNull();
  });

  it('cannot produce a javascript: URL', () => {
    const url = wikiUrl('javascript:alert(1)');
    expect(url?.startsWith(WIKI_BASE)).toBe(true);
    // Pinned to the exact encoded output rather than the absence of a payload:
    // an absence assertion passes against raw concatenation for any payload
    // whose only encodable character is the colon.
    expect(url).toBe(`${WIKI_BASE}javascript%3Aalert(1)`);
  });

  it('cannot escape the wiki path with traversal segments', () => {
    const url = wikiUrl('../../etc/passwd');
    expect(url).toBe(`${WIKI_BASE}etc/passwd`);
  });

  it('cannot redirect off-site with a protocol-relative title', () => {
    const url = wikiUrl('//evil.example.com/x');
    expect(url?.startsWith(WIKI_BASE)).toBe(true);
    expect(url).toBe(`${WIKI_BASE}evil.example.com/x`);
  });

  it('encodes characters that would otherwise change the URL structure', () => {
    expect(wikiUrl('A?b=c')).toBe(`${WIKI_BASE}A%3Fb%3Dc`);
  });

  it('degrades to no link instead of throwing on an unencodable title', () => {
    // A lone surrogate survives JSON.parse, so it can arrive from graph.json.
    expect(() => wikiUrl('\uD800')).not.toThrow();
    expect(wikiUrl('\uD800')).toBeNull();
    expect(() => wikiUrl('Unity#\uDFFF')).not.toThrow();
    expect(wikiUrl('Unity#\uDFFF')).toBeNull();
  });

  it('still links a title containing a well-formed astral character', () => {
    expect(wikiUrl('Relic 😀')).toBe(`${WIKI_BASE}Relic_%F0%9F%98%80`);
  });
});

describe('sourceLabel', () => {
  it('links a wiki source', () => {
    expect(sourceLabel('wiki:Relics')).toEqual({
      text: 'Relics',
      href: `${WIKI_BASE}Relics`,
    });
  });

  it('labels non-wiki sources without a link', () => {
    expect(sourceLabel('observed')).toEqual({ text: 'observed in game', href: null });
    expect(sourceLabel('il2cpp')).toEqual({ text: 'game binary', href: null });
    expect(sourceLabel('discord')).toEqual({ text: 'community report', href: null });
  });

  it('passes an unrecognised source through as plain text', () => {
    expect(sourceLabel('mystery')).toEqual({ text: 'mystery', href: null });
  });
});
