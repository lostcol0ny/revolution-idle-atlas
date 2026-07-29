import { useCallback, useState } from 'react';
import type { UrlState } from '../graph/urlState';
import { parseUrlState, toSearch } from '../graph/urlState';

/**
 * The URL is the state. Uses replaceState rather than pushState: the graph is
 * the navigation surface, so a six-node exploration should not cost six back
 * presses to escape. The URL stays shareable either way.
 */
export function useUrlState(): [UrlState, (next: Partial<UrlState>) => void] {
  const [state, setState] = useState<UrlState>(() =>
    parseUrlState(window.location.search),
  );

  const update = useCallback((next: Partial<UrlState>) => {
    setState((current) => {
      const merged = { ...current, ...next };
      window.history.replaceState(null, '', toSearch(merged));
      return merged;
    });
  }, []);

  return [state, update];
}
