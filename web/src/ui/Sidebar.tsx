import { useMemo, useState } from 'react';
import type { GraphIndex } from '../graph/adjacency';
import { systemColour } from '../graph/palette';
import type { GraphNode, System } from '../types';
import { SYSTEMS } from '../types';

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

  const bySystem = useMemo(() => {
    const groups = new Map<System, GraphNode[]>();
    for (const id of index.order) {
      const node = index.nodes.get(id);
      if (!node) continue;
      const group = groups.get(node.system) ?? [];
      group.push(node);
      groups.set(node.system, group);
    }
    return groups;
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
        SYSTEMS.map((system) => {
          const nodes = bySystem.get(system);
          if (!nodes || nodes.length === 0) return null;
          const expanded = open.has(system);
          return (
            <section key={system}>
              <button
                type="button"
                className="group-header"
                aria-expanded={expanded}
                onClick={() => toggle(system)}
              >
                <span className="swatch" style={{ background: systemColour(system) }} />
                <span>{system}</span>
                <span className="count">{nodes.length}</span>
              </button>
              {expanded && (
                <ul className="node-list">
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
            </section>
          );
        })
      )}
    </>
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
