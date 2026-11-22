import { useCallback, useEffect, useState } from 'react';
import type { UrlState } from '../graph/urlState';
import { parseUrlState, toSearch } from '../graph/urlState';

/**
 * The URL is the state. Moving to another node or system pushes a history
 * entry so Back retraces the route; a depth change on the same view replaces
 * it, so flicking through depths does not cost a back press each.
 *
 * The third value is true when the current state arrived by Back/Forward, so
 * the caller can restore that entry's scroll instead of starting at the top.
 */
export function useUrlState(): [UrlState, (next: Partial<UrlState>) => void, boolean] {
  const [state, setState] = useState(() => ({
    url: parseUrlState(window.location.search),
    fromHistory: false,
  }));

  useEffect(() => {
    const onPop = () =>
      setState({ url: parseUrlState(window.location.search), fromHistory: true });
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
    setState({ url: merged, fromHistory: false });
  }, []);

  return [state.url, update, state.fromHistory];
}
