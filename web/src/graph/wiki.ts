export const WIKI_BASE = 'https://revolutionidle.wiki.gg/wiki/';

/**
 * Build a wiki URL from a page title that originated in hand-maintained YAML.
 *
 * The origin is a hardcoded constant and every path segment is individually
 * encoded, so a hostile value cannot produce a javascript: URL, redirect
 * off-site, or escape the /wiki/ prefix. The worst case is a dead link.
 */
export function wikiUrl(page: string | undefined): string | null {
  if (!page) return null;

  const hash = page.indexOf('#');
  const title = hash === -1 ? page : page.slice(0, hash);
  const anchor = hash === -1 ? '' : page.slice(hash + 1);

  const segments = title
    .trim()
    .replace(/ /g, '_')
    .split('/')
    .filter((segment) => segment.length > 0 && segment !== '.' && segment !== '..');

  if (segments.length === 0) return null;

  const path = segments.map(encodeURIComponent).join('/');
  const fragment = anchor ? `#${encodeURIComponent(anchor.replace(/ /g, '_'))}` : '';

  return `${WIKI_BASE}${path}${fragment}`;
}

export interface SourceLabel {
  text: string;
  href: string | null;
}

const WIKI_PREFIX = 'wiki:';

export function sourceLabel(source: string): SourceLabel {
  if (source.startsWith(WIKI_PREFIX)) {
    const page = source.slice(WIKI_PREFIX.length);
    return { text: page, href: wikiUrl(page) };
  }

  switch (source) {
    case 'observed':
      return { text: 'observed in game', href: null };
    case 'il2cpp':
      return { text: 'game binary', href: null };
    case 'discord':
      return { text: 'community report', href: null };
    default:
      return { text: source, href: null };
  }
}
