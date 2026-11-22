import { useCallback, useEffect, useMemo, useState, type MouseEvent, type ReactNode } from 'react';
import { buildIndex, type GraphIndex } from '../graph/adjacency';
import { GraphFetchError, GraphFormatError, loadGraph } from '../graph/load';
import { systemIcon } from '../graph/palette';
import { toSearch, viewOf, type UrlState } from '../graph/urlState';
import { useUrlState } from './useUrlState';
import {
  FetchErrorScreen,
  FormatErrorScreen,
  LoadingScreen,
  UnknownIdBanner,
} from './Screens';
import { Sidebar } from './Sidebar';
import { GraphView } from './GraphView';
import { NodeCard } from './NodeCard';
import { SystemTable } from './SystemTable';
import { Overview } from './Overview';

type LoadState =
  | { status: 'loading' }
  | { status: 'ready'; index: GraphIndex }
  | { status: 'fetch-error'; message: string }
  | { status: 'format-error'; message: string };

const SITE_TITLE = 'Revolution Idle Atlas';
const HOME: UrlState = { nodeId: null, systemId: null, depth: null };

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
          // Neither load error type. buildIndex warns-and-continues only for
          // dangling edges; a malformed element still throws, because parseGraph
          // checks that nodes/edges are arrays but never checks the elements.
          // Retry is the wrong affordance for that, but a dedicated screen is
          // more machinery than it earns — log it so it stays diagnosable.
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

  // Depth only means something on the item graph, so it follows the reader from
  // item to item but is dropped on leaving for a table or the overview.
  const selectNode = useCallback(
    (nodeId: string) => setUrlState({ nodeId, systemId: null }),
    [setUrlState],
  );
  const selectSystem = useCallback(
    (systemId: string) => setUrlState({ ...HOME, systemId }),
    [setUrlState],
  );

  const index = load.status === 'ready' ? load.index : null;
  const systems = useMemo(() => (index === null ? null : describeSystems(index)), [index]);

  const node = index !== null && urlState.nodeId !== null ? index.nodes.get(urlState.nodeId) : undefined;
  const missingNode = index !== null && urlState.nodeId !== null && node === undefined;
  const missingSystem =
    systems !== null && urlState.systemId !== null && !systems.has(urlState.systemId);
  // An id that resolves to nothing falls through to the next view down rather
  // than rendering an empty one: a stale link still lands somewhere useful.
  const view = viewOf({
    ...urlState,
    nodeId: missingNode ? null : urlState.nodeId,
    systemId: missingSystem ? null : urlState.systemId,
  });

  const trailEnd =
    view.kind === 'item' ? node?.system : view.kind === 'system' ? view.systemId : undefined;
  const trail = systems === null || trailEnd === undefined ? [] : systemTrail(systems, trailEnd);

  const pageName = node?.name ?? trail.at(-1)?.name;
  useEffect(() => {
    document.title = pageName === undefined ? SITE_TITLE : `${pageName} · ${SITE_TITLE}`;
  }, [pageName]);

  if (load.status === 'loading') return <LoadingScreen />;
  if (load.status === 'format-error') return <FormatErrorScreen message={load.message} />;
  if (load.status === 'fetch-error') {
    return (
      <FetchErrorScreen message={load.message} onRetry={() => setAttempt((n) => n + 1)} />
    );
  }

  const ready = load.index;

  return (
    <div className="app">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className="topbar">
        <NavLink className="brand" target={HOME} navigate={setUrlState}>
          <span className="brand__mark" aria-hidden="true">
            ✦
          </span>
          {SITE_TITLE}
        </NavLink>
        <nav className="crumbs" aria-label="Breadcrumb">
          <ol>
            <li>
              {view.kind === 'overview' ? (
                <span aria-current="page">Home</span>
              ) : (
                <NavLink target={HOME} navigate={setUrlState}>
                  Home
                </NavLink>
              )}
            </li>
            {trail.map((system, position) => (
              <li key={system.id}>
                {view.kind === 'system' && position === trail.length - 1 ? (
                  <span aria-current="page">
                    <span aria-hidden="true">{systemIcon(system.id)} </span>
                    {system.name}
                  </span>
                ) : (
                  <NavLink
                    target={{ ...HOME, systemId: system.id }}
                    navigate={setUrlState}
                  >
                    <span aria-hidden="true">{systemIcon(system.id)} </span>
                    {system.name}
                  </NavLink>
                )}
              </li>
            ))}
            {view.kind === 'item' && node !== undefined && (
              <li>
                <span aria-current="page">{node.name}</span>
              </li>
            )}
          </ol>
        </nav>
      </header>

      <div className="layout">
        {/* Two complementary landmarks on one page are indistinguishable to a
            screen reader without names — both announce as "complementary". */}
        <aside className="sidebar" aria-label="Browse systems and items">
          <Sidebar
            index={ready}
            selectedId={view.kind === 'item' ? view.nodeId : null}
            selectedSystemId={view.kind === 'system' ? view.systemId : null}
            onSelect={selectNode}
            onSelectSystem={selectSystem}
          />
        </aside>
        <main
          id="main"
          tabIndex={-1}
          className={view.kind === 'item' ? 'canvas canvas--graph' : 'canvas'}
        >
          {missingNode && urlState.nodeId !== null && (
            <UnknownIdBanner what="item" id={urlState.nodeId} />
          )}
          {missingSystem && urlState.systemId !== null && (
            <UnknownIdBanner what="system" id={urlState.systemId} />
          )}
          {view.kind === 'item' && node !== undefined ? (
            <GraphView
              index={ready}
              rootId={node.id}
              depth={urlState.depth}
              onSelect={selectNode}
              onDepthChange={(depth) => setUrlState({ depth })}
            />
          ) : view.kind === 'system' ? (
            <SystemTable
              index={ready}
              systemId={view.systemId}
              onSelectNode={selectNode}
              onSelectSystem={selectSystem}
            />
          ) : (
            <Overview index={ready} onSelectSystem={selectSystem} />
          )}
        </main>
        {view.kind === 'item' && node !== undefined && (
          <aside className="detail" aria-label="Item detail">
            <NodeCard index={ready} node={node} onSelect={selectNode} />
          </aside>
        )}
      </div>
    </div>
  );
}

interface SystemInfo {
  name: string;
  parent: string | undefined;
}

/** Every system the atlas can show: the declared ones plus any a node names. */
function describeSystems(index: GraphIndex): Map<string, SystemInfo> {
  const systems = new Map<string, SystemInfo>();
  for (const system of index.systems) {
    systems.set(system.id, { name: system.name, parent: system.parent });
  }
  for (const node of index.nodes.values()) {
    if (!systems.has(node.system)) systems.set(node.system, { name: node.system, parent: undefined });
  }
  return systems;
}

/** Root-first ancestry of a system, stopping at a repeat so a parent cycle cannot hang. */
function systemTrail(
  systems: Map<string, SystemInfo>,
  systemId: string,
): { id: string; name: string }[] {
  const trail: { id: string; name: string }[] = [];
  const seen = new Set<string>();
  for (let id: string | undefined = systemId; id !== undefined && !seen.has(id); ) {
    seen.add(id);
    const info = systems.get(id);
    if (info === undefined) break;
    trail.unshift({ id, name: info.name });
    id = info.parent;
  }
  return trail;
}

/**
 * A real link, so the URL shows on hover and middle-click opens a new tab, that
 * navigates in place on a plain click.
 */
function NavLink({
  target,
  navigate,
  className,
  children,
}: {
  target: UrlState;
  navigate: (next: UrlState) => void;
  className?: string;
  children: ReactNode;
}) {
  const onClick = (event: MouseEvent<HTMLAnchorElement>) => {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
      return;
    }
    event.preventDefault();
    navigate(target);
  };
  return (
    <a className={className} href={`${window.location.pathname}${toSearch(target)}`} onClick={onClick}>
      {children}
    </a>
  );
}
