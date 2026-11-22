import { useCallback, useEffect, useState } from 'react';
import type { UrlState } from '../graph/urlState';
import { parseUrlState, toSearch } from '../graph/urlState';

/**
 * The URL is the state. Moving to another node or system pushes a history
 * entry so Back retraces the route; a depth change on the same view replaces
 * it, so flicking through depths does not cost a back press each.
 */
export function useUrlState(): [UrlState, (next: Partial<UrlState>) => void] {
  const [state, setState] = useState<UrlState>(() => parseUrlState(window.location.search));

  useEffect(() => {
    const onPop = () => setState(parseUrlState(window.location.search));
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);

  // Reads the current state from the URL rather than from a setState updater:
  // updaters run twice under StrictMode, which would push every entry twice.
  const update = useCallback((next: Partial<UrlState>) => {
    const current = parseUrlState(window.location.search);
    const merged = { ...current, ...next };
    const search = toSearch(merged);
    if (search === toSearch(current)) return;
    const url = `${window.location.pathname}${search}${window.location.hash}`;
    if (merged.nodeId === current.nodeId && merged.systemId === current.systemId) {
      window.history.replaceState(null, '', url);
    } else {
      window.history.pushState(null, '', url);
    }
    setState(merged);
  }, []);

  return [state, update];
}
