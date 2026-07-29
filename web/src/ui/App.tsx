import { useCallback, useEffect, useState } from 'react';
import { buildIndex, type GraphIndex } from '../graph/adjacency';
import { GraphFetchError, GraphFormatError, loadGraph } from '../graph/load';
import { useUrlState } from './useUrlState';
import {
  EmptyScreen,
  FetchErrorScreen,
  FormatErrorScreen,
  LoadingScreen,
  UnknownNodeBanner,
} from './Screens';

type LoadState =
  | { status: 'loading' }
  | { status: 'ready'; index: GraphIndex }
  | { status: 'fetch-error'; message: string }
  | { status: 'format-error'; message: string };

const SUGGESTED_IDS = ['attack-power', 'gold'];

export default function App() {
  const [load, setLoad] = useState<LoadState>({ status: 'loading' });
  const [urlState, setUrlState] = useUrlState();
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoad({ status: 'loading' });

    loadGraph()
      .then((doc) => {
        if (!cancelled) setLoad({ status: 'ready', index: buildIndex(doc) });
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        if (error instanceof GraphFormatError) {
          setLoad({ status: 'format-error', message: error.message });
        } else if (error instanceof GraphFetchError) {
          setLoad({ status: 'fetch-error', message: error.message });
        } else {
          // Neither load error type, so the throw came from somewhere that does
          // not currently throw (buildIndex warns and continues). Offering Retry
          // is wrong for such an error, but a screen for a path that cannot yet
          // be reached is worse — log it so it is diagnosable if it ever is.
          console.error('Unexpected error while loading the graph', error);
          setLoad({
            status: 'fetch-error',
            message: error instanceof Error ? error.message : String(error),
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const select = useCallback(
    (nodeId: string) => setUrlState({ nodeId }),
    [setUrlState],
  );

  if (load.status === 'loading') return <LoadingScreen />;
  if (load.status === 'format-error') return <FormatErrorScreen message={load.message} />;
  if (load.status === 'fetch-error') {
    return (
      <FetchErrorScreen
        message={load.message}
        onRetry={() => setAttempt((n) => n + 1)}
      />
    );
  }

  const { index } = load;
  const selected = urlState.nodeId !== null ? index.nodes.get(urlState.nodeId) : undefined;
  const missing = urlState.nodeId !== null && selected === undefined;

  const suggestions = SUGGESTED_IDS.flatMap((id) => {
    const node = index.nodes.get(id);
    return node ? [{ id: node.id, name: node.name }] : [];
  });

  return (
    <div className="layout">
      <aside className="sidebar">
        <p className="muted">{index.order.length} nodes</p>
      </aside>
      <main className="canvas">
        {missing && urlState.nodeId !== null && (
          <UnknownNodeBanner nodeId={urlState.nodeId} />
        )}
        {selected === undefined ? (
          <EmptyScreen suggestions={suggestions} onPick={select} />
        ) : (
          <p className="muted">Selected: {selected.name}</p>
        )}
      </main>
    </div>
  );
}
