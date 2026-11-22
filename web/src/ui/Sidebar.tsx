import { useEffect, useMemo, useState } from 'react';
import type { GraphIndex } from '../graph/adjacency';
import { systemColour, systemIcon } from '../graph/palette';
import { buildSystemTree, type SystemTreeNode } from '../graph/systems';
import type { GraphNode, System } from '../types';

export function Sidebar({
  index,
  selectedId,
  selectedSystemId,
  onSelect,
  onSelectSystem,
}: {
  index: GraphIndex;
  selectedId: string | null;
  selectedSystemId: string | null;
  onSelect: (id: string) => void;
  onSelectSystem: (id: string) => void;
}) {
  const [filter, setFilter] = useState('');
  const [open, setOpen] = useState<Set<System>>(() => new Set());

  const { bySystem, tree } = useMemo(() => {
    const groups = new Map<System, GraphNode[]>();
    for (const id of index.order) {
      const node = index.nodes.get(id);
      if (!node) continue;
      const group = groups.get(node.system) ?? [];
      group.push(node);
      groups.set(node.system, group);
    }
    const counts = new Map([...groups].map(([system, nodes]) => [system, nodes.length]));
    return { bySystem: groups, tree: buildSystemTree(index.systems, counts) };
  }, [index]);

  // Opening a system or item from elsewhere (the overview, a table, the graph,
  // a shared link) unfolds the tree down to it, so the sidebar always shows
  // where the reader is.
  const revealed =
    selectedSystemId ?? (selectedId !== null ? index.nodes.get(selectedId)?.system : undefined);
  useEffect(() => {
    if (revealed === undefined) return;
    const path = pathTo(tree, revealed);
    // A system view lists its items in the main pane; unfolding the selected
    // system itself would only duplicate them here.
    if (selectedSystemId !== null) path.pop();
    setOpen((current) =>
      path.every((id) => current.has(id)) ? current : new Set([...current, ...path]),
    );
  }, [tree, revealed, selectedSystemId]);

  const needle = filter.trim().toLowerCase();

  const matches = useMemo(() => {
    if (needle.length === 0) return null;
    return index.order
      .map((id) => index.nodes.get(id))
      .filter((node): node is GraphNode => node !== undefined)
      .filter((node) => node.name.toLowerCase().includes(needle));
  }, [index, needle]);

  const toggle = (system: System) =>
    setOpen((current) => {
      const next = new Set(current);
      if (next.has(system)) next.delete(system);
      else next.add(system);
      return next;
    });

  return (
    <>
      <label className="filter-label" htmlFor="item-filter">
        Find an item
      </label>
      <input
        id="item-filter"
        className="filter"
        type="search"
        placeholder="e.g. Gold, Tarot…"
        autoComplete="off"
        autoCorrect="off"
        autoCapitalize="none"
        spellCheck={false}
        value={filter}
        onChange={(event) => setFilter(event.target.value)}
      />

      {/* Always mounted: a live region inserted together with its first
          message is usually not announced. */}
      <p className="muted filter-count" role="status">
        {matches === null ? '' : matches.length === 1 ? '1 match' : `${matches.length} matches`}
      </p>
      {matches !== null ? (
        <ul className="node-list node-list--flat" role="list">
          {matches.map((node) => (
            <NodeRow
              key={node.id}
              node={node}
              selected={node.id === selectedId}
              onSelect={onSelect}
              showIcon
            />
          ))}
        </ul>
      ) : (
        <nav aria-label="Systems">
          {tree.map((system) => (
            <SystemSection
              key={system.id}
              system={system}
              depth={0}
              bySystem={bySystem}
              open={open}
              toggle={toggle}
              selectedId={selectedId}
              selectedSystemId={selectedSystemId}
              onSelect={onSelect}
              onSelectSystem={onSelectSystem}
            />
          ))}
        </nav>
      )}
    </>
  );
}

/** Ids from the root down to `id`, or empty when the tree does not hold it. */
function pathTo(tree: readonly SystemTreeNode[], id: System): System[] {
  for (const system of tree) {
    if (system.id === id) return [id];
    const below = pathTo(system.children, id);
    if (below.length > 0) return [system.id, ...below];
  }
  return [];
}

function SystemSection({
  system,
  depth,
  bySystem,
  open,
  toggle,
  selectedId,
  selectedSystemId,
  onSelect,
  onSelectSystem,
}: {
  system: SystemTreeNode;
  depth: number;
  bySystem: Map<System, GraphNode[]>;
  open: Set<System>;
  toggle: (system: System) => void;
  selectedId: string | null;
  selectedSystemId: string | null;
  onSelect: (id: string) => void;
  onSelectSystem: (id: string) => void;
}) {
  const expanded = open.has(system.id);
  const nodes = bySystem.get(system.id) ?? [];
  const current = system.id === selectedSystemId;
  // The count is the rolled-up total, so a parent reads as the size of the
  // branch rather than of whatever happens to sit directly on it. The title
  // carries the split for the cases where those differ.
  const countLabel =
    system.direct === system.total
      ? `${system.total} items`
      : `${system.total} items, ${system.direct} directly`;

  return (
    <section>
      <div
        className={current ? 'group-header selected' : 'group-header'}
        style={{ paddingLeft: depth * 14 }}
      >
        <button
          type="button"
          className="caret"
          aria-expanded={expanded}
          aria-label={`${system.name} items`}
          onClick={() => toggle(system.id)}
        >
          <span aria-hidden="true">{expanded ? '▾' : '▸'}</span>
        </button>
        <button
          type="button"
          className="group-name"
          aria-current={current ? 'page' : undefined}
          title={`Open the ${system.name} table (${countLabel})`}
          onClick={() => onSelectSystem(system.id)}
        >
          <span
            className="system-icon"
            style={{ borderColor: systemColour(system.id) }}
            aria-hidden="true"
          >
            {systemIcon(system.id)}
          </span>
          <span className="group-name__text">{system.name}</span>
          <span className="count">
            {system.total}
            <span className="visually-hidden"> items</span>
          </span>
        </button>
      </div>
      {expanded && (
        <>
          {nodes.length > 0 && (
            <ul className="node-list" style={{ paddingLeft: 22 + depth * 14 }}>
              {nodes.map((node) => (
                <NodeRow
                  key={node.id}
                  node={node}
                  selected={node.id === selectedId}
                  onSelect={onSelect}
                />
              ))}
            </ul>
          )}
          {system.children.map((child) => (
            <SystemSection
              key={child.id}
              system={child}
              depth={depth + 1}
              bySystem={bySystem}
              open={open}
              toggle={toggle}
              selectedId={selectedId}
              selectedSystemId={selectedSystemId}
              onSelect={onSelect}
              onSelectSystem={onSelectSystem}
            />
          ))}
        </>
      )}
    </section>
  );
}

function NodeRow({
  node,
  selected,
  onSelect,
  showIcon = false,
}: {
  node: GraphNode;
  selected: boolean;
  onSelect: (id: string) => void;
  /** Search results mix systems, so each row carries its system's glyph. */
  showIcon?: boolean;
}) {
  return (
    <li>
      <button
        type="button"
        className={selected ? 'node-row selected' : 'node-row'}
        aria-current={selected ? 'page' : undefined}
        title={showIcon ? `${node.name} (${node.system})` : undefined}
        onClick={() => onSelect(node.id)}
      >
        {showIcon && (
          <span className="node-row__icon" aria-hidden="true">
            {systemIcon(node.system)}
          </span>
        )}
        {node.name}
      </button>
    </li>
  );
}
