import { useMemo, useState } from 'react';
import type { GraphIndex } from '../graph/adjacency';
import { systemColour } from '../graph/palette';
import { buildSystemTree, type SystemTreeNode } from '../graph/systems';
import type { GraphNode, System } from '../types';

export function Sidebar({
  index,
  selectedId,
  onSelect,
}: {
  index: GraphIndex;
  selectedId: string | null;
  onSelect: (id: string) => void;
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
      <input
        className="filter"
        type="search"
        placeholder="Filter nodes…"
        value={filter}
        onChange={(event) => setFilter(event.target.value)}
      />

      {matches !== null ? (
        <ul className="node-list">
          {matches.length === 0 && <li className="muted">No matches</li>}
          {matches.map((node) => (
            <NodeRow
              key={node.id}
              node={node}
              selected={node.id === selectedId}
              onSelect={onSelect}
            />
          ))}
        </ul>
      ) : (
        tree.map((system) => (
          <SystemSection
            key={system.id}
            system={system}
            depth={0}
            bySystem={bySystem}
            open={open}
            toggle={toggle}
            selectedId={selectedId}
            onSelect={onSelect}
          />
        ))
      )}
    </>
  );
}

function SystemSection({
  system,
  depth,
  bySystem,
  open,
  toggle,
  selectedId,
  onSelect,
}: {
  system: SystemTreeNode;
  depth: number;
  bySystem: Map<System, GraphNode[]>;
  open: Set<System>;
  toggle: (system: System) => void;
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const expanded = open.has(system.id);
  const nodes = bySystem.get(system.id) ?? [];
  // The count is the rolled-up total, so a parent reads as the size of the
  // branch rather than of whatever happens to sit directly on it. The title
  // carries the split for the cases where those differ.
  const label =
    system.direct === system.total
      ? `${system.total} nodes`
      : `${system.total} nodes, ${system.direct} directly`;

  return (
    <section>
      <button
        type="button"
        className="group-header"
        style={{ paddingLeft: 4 + depth * 14 }}
        aria-expanded={expanded}
        title={label}
        onClick={() => toggle(system.id)}
      >
        <span className="caret" aria-hidden="true">
          {expanded ? '▾' : '▸'}
        </span>
        <span className="swatch" style={{ background: systemColour(system.id) }} />
        <span>{system.name}</span>
        <span className="count">{system.total}</span>
      </button>
      {expanded && (
        <>
          {nodes.length > 0 && (
            <ul className="node-list" style={{ paddingLeft: 18 + depth * 14 }}>
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
              onSelect={onSelect}
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
}: {
  node: GraphNode;
  selected: boolean;
  onSelect: (id: string) => void;
}) {
  return (
    <li>
      <button
        type="button"
        className={selected ? 'node-row selected' : 'node-row'}
        onClick={() => onSelect(node.id)}
      >
        {node.name}
      </button>
    </li>
  );
}
