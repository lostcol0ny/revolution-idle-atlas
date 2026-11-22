import { memo, useDeferredValue, useMemo, useState, type JSX } from 'react';
import type { GraphIndex } from '../graph/adjacency';
import { systemColour, systemIcon } from '../graph/palette';
import {
  buildRows,
  filterRows,
  findSystem,
  nextSort,
  sortRows,
  subtreeIds,
  systemTree,
  type LinkGroup,
  type Sort,
  type SortKey,
  type TableRow,
} from '../graph/table';
import { wikiUrl } from '../graph/wiki';
import type { Rel } from '../types';
import './table.css';

// `requires` points prerequisite -> dependant, so its verb reads backwards
// from the arrow: an outgoing `requires` edge means "required by".
const OUT_LABELS: Record<Rel, string | null> = { boosts: null, unlocks: 'Unlocks', requires: 'Required by' };
const IN_LABELS: Record<Rel, string | null> = { boosts: null, unlocks: 'Unlocked by', requires: 'Requires' };

const COLLAPSED_LINKS = 6;
// Hiding one or two links behind a button costs more than it saves.
const COLLAPSE_SLACK = 2;

const CONFIDENCE_TITLE = {
  documented: 'Documented: confirmed by a source',
  provisional: 'Provisional: from a source, not yet confirmed',
  unknown: 'Unknown: placeholder, nothing curated yet',
} as const;

export function SystemTable({
  index,
  systemId,
  onSelectNode,
  onSelectSystem,
}: {
  index: GraphIndex;
  systemId: string;
  onSelectNode: (id: string) => void;
  onSelectSystem: (id: string) => void;
}): JSX.Element {
  const tree = useMemo(() => systemTree(index), [index]);
  const system = useMemo(() => findSystem(tree, systemId), [tree, systemId]);
  const rows = useMemo(() => {
    if (system === null) return [];
    const names = new Map(index.systems.map((declared) => [declared.id, declared.name]));
    return buildRows(index, subtreeIds(system), names);
  }, [index, system]);

  const [query, setQuery] = useState('');
  const [sort, setSort] = useState<Sort | null>(null);
  // A new system is a new page: the old filter would silently hide its rows.
  const [shownId, setShownId] = useState(systemId);
  if (shownId !== systemId) {
    setShownId(systemId);
    setQuery('');
    setSort(null);
  }

  // Typing stays immediate while the 236-row Minerals table re-renders behind it.
  const deferredQuery = useDeferredValue(query);
  const visible = useMemo(() => sortRows(filterRows(rows, deferredQuery), sort), [rows, deferredQuery, sort]);

  if (system === null) {
    return (
      <section className="stable">
        <h1 className="stable__title">Unknown system</h1>
        <p className="stable__muted">
          No system is called <code>{systemId}</code>. Pick one from the sidebar.
        </p>
      </section>
    );
  }

  const nested = system.children.length > 0;

  const sortHeader = (key: SortKey, label: string) => {
    const active = sort?.key === key ? sort.dir : null;
    return (
      <th scope="col" aria-sort={active === null ? undefined : active === 'asc' ? 'ascending' : 'descending'}>
        <button type="button" className="stable__sort" onClick={() => setSort(nextSort(sort, key))}>
          {label}
          <span className="stable__arrow" aria-hidden="true">
            {active === 'asc' ? '▲' : active === 'desc' ? '▼' : '↕'}
          </span>
        </button>
      </th>
    );
  };

  return (
    <section className="stable" aria-labelledby="stable-title">
      <header className="stable__header" style={{ borderColor: systemColour(system.id) }}>
        {/* Ancestors are the app header's breadcrumb, so this page starts at its own name. */}
        <h1 id="stable-title" className="stable__title">
          <span className="stable__icon" aria-hidden="true">
            {systemIcon(system.id)}
          </span>
          {system.name}
        </h1>
        <p className="stable__muted">
          {system.total} {system.total === 1 ? 'entry' : 'entries'}
          {nested && `, ${system.direct} here and the rest in ${system.children.length} sub-${system.children.length === 1 ? 'system' : 'systems'}`}
        </p>
        {nested && (
          <ul className="stable__chips" aria-label="Sub-systems">
            {system.children.map((child) => (
              <li key={child.id}>
                <button
                  type="button"
                  className="stable__chip"
                  style={{ borderLeftColor: systemColour(child.id) }}
                  onClick={() => onSelectSystem(child.id)}
                >
                  <span aria-hidden="true">{systemIcon(child.id)}</span> {child.name}
                  <span className="stable__muted"> {child.total}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </header>

      <div className="stable__toolbar">
        <input
          className="stable__filter"
          type="search"
          aria-label={`Filter ${system.name} by name, description or effect`}
          placeholder="Filter by name, description or effect…"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <span className="stable__muted" role="status">
          {visible.length === rows.length ? `${rows.length} shown` : `${visible.length} of ${rows.length} shown`}
        </span>
      </div>

      <table className="stable__table">
        <caption className="stable__sr">
          Everything in {system.name}. Column headers with arrows sort the table; links open an item.
        </caption>
        <thead>
          <tr>
            {sortHeader('name', 'Name')}
            {sortHeader('kind', 'Kind')}
            <th scope="col" className="stable__unsortable">Description</th>
            <th scope="col" className="stable__unsortable">Effects</th>
            {sortHeader('outgoing', 'Boosts')}
            {sortHeader('incoming', 'Boosted by')}
          </tr>
        </thead>
        <tbody>
          {visible.length === 0 ? (
            <tr>
              <td colSpan={6} className="stable__muted">
                Nothing matches “{deferredQuery.trim()}”.
              </td>
            </tr>
          ) : (
            visible.map((row) => (
              <Row
                key={row.node.id}
                row={row}
                showSystem={nested}
                onSelectNode={onSelectNode}
                onSelectSystem={onSelectSystem}
              />
            ))
          )}
        </tbody>
      </table>
    </section>
  );
}

// Memoised so re-sorting reorders existing rows and filtering only unmounts
// the misses, instead of re-rendering every link cell on each keystroke.
const Row = memo(function Row({
  row,
  showSystem,
  onSelectNode,
  onSelectSystem,
}: {
  row: TableRow;
  showSystem: boolean;
  onSelectNode: (id: string) => void;
  onSelectSystem: (id: string) => void;
}) {
  const { node } = row;
  // Absent means documented: the pipeline's default, and NodeCard's reading too.
  const confidence = node.confidence ?? 'documented';
  const href = wikiUrl(node.wiki);

  return (
    <tr>
      <th scope="row">
        <button type="button" className="stable__link stable__name" onClick={() => onSelectNode(node.id)}>
          {node.name}
        </button>
        <div className="stable__meta">
          <span className={`stable__badge stable__badge--${confidence}`} title={CONFIDENCE_TITLE[confidence]}>
            {confidence}
          </span>
          {showSystem && (
            <button type="button" className="stable__link stable__sub" onClick={() => onSelectSystem(node.system)}>
              {row.systemName}
            </button>
          )}
          {href !== null && (
            <a className="stable__link stable__sub" href={href} target="_blank" rel="noreferrer noopener">
              wiki<span className="stable__sr"> page for {node.name} (opens in a new tab)</span>
            </a>
          )}
        </div>
      </th>
      <td data-label="Kind">{node.kind.replace('-', ' ')}</td>
      <td data-label="Description">
        {node.description ?? <span className="stable__muted">—</span>}
      </td>
      <td data-label="Effects">
        {node.effects === undefined || node.effects.length === 0 ? (
          <span className="stable__muted">—</span>
        ) : (
          <ul className="stable__effects">
            {node.effects.map((effect, position) => (
              <li key={position}>
                {effect.text}
                {effect.per_level !== undefined && <span className="stable__per-level"> {effect.per_level}</span>}
              </li>
            ))}
          </ul>
        )}
      </td>
      <td data-label="Boosts">
        <Links groups={row.outgoing} labels={OUT_LABELS} onSelectNode={onSelectNode} />
      </td>
      <td data-label="Boosted by">
        <Links groups={row.incoming} labels={IN_LABELS} onSelectNode={onSelectNode} />
      </td>
    </tr>
  );
});

function Links({
  groups,
  labels,
  onSelectNode,
}: {
  groups: LinkGroup[];
  labels: Record<Rel, string | null>;
  onSelectNode: (id: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  if (groups.length === 0) return <span className="stable__muted">—</span>;

  // The budget is shared across groups so a hub's cell stays one screen tall
  // until asked, whichever rels its links happen to fall under.
  const total = groups.reduce((sum, group) => sum + group.links.length, 0);
  const collapsible = total > COLLAPSED_LINKS + COLLAPSE_SLACK;
  let budget = expanded || !collapsible ? Infinity : COLLAPSED_LINKS;

  return (
    <div className="stable__links">
      {groups.map((group) => {
        if (budget <= 0) return null;
        const links = group.links.slice(0, budget);
        budget -= links.length;
        const label = labels[group.rel];
        return (
          <div key={group.rel}>
            {label !== null && <span className="stable__rel">{label}: </span>}
            <ul className="stable__linklist">
              {links.map((link) => (
                <li key={link.id}>
                  <button
                    type="button"
                    className={`stable__link${link.confidence === 'uncertain' ? ' stable__link--uncertain' : ''}`}
                    title={link.confidence === 'uncertain' ? 'Uncertain: believed to exist, mechanism not established' : undefined}
                    onClick={() => onSelectNode(link.id)}
                  >
                    {link.name}
                    {link.confidence === 'uncertain' && (
                      <>
                        <span className="stable__uncertain" aria-hidden="true">?</span>
                        <span className="stable__sr"> (uncertain)</span>
                      </>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
      {collapsible && (
        <button type="button" className="stable__more" aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>
          {expanded ? 'Show fewer' : `Show ${total - COLLAPSED_LINKS} more`}
        </button>
      )}
    </div>
  );
}
