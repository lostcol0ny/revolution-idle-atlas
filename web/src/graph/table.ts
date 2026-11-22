import type { GraphIndex } from './adjacency';
import { buildSystemTree, type SystemTreeNode } from './systems';
import type { EdgeConfidence, GraphEdge, GraphNode, Rel, System } from '../types';

export interface LinkItem {
  id: string;
  name: string;
  system: System;
  confidence: EdgeConfidence;
}

export interface LinkGroup {
  rel: Rel;
  links: LinkItem[];
}

export interface TableRow {
  node: GraphNode;
  /** Position in dataset order, the default sort and every tie-break. */
  position: number;
  systemName: string;
  outgoing: LinkGroup[];
  incoming: LinkGroup[];
  outgoingCount: number;
  incomingCount: number;
  /** Lower-cased name, description and effect text, precomputed for filtering. */
  haystack: string;
}

export type SortKey = 'name' | 'kind' | 'outgoing' | 'incoming';
export type SortDir = 'asc' | 'desc';
export interface Sort {
  key: SortKey;
  dir: SortDir;
}

export function systemTree(index: GraphIndex): SystemTreeNode[] {
  const counts = new Map<System, number>();
  for (const node of index.nodes.values()) counts.set(node.system, (counts.get(node.system) ?? 0) + 1);
  return buildSystemTree(index.systems, counts);
}

export function findSystem(tree: readonly SystemTreeNode[], id: System): SystemTreeNode | null {
  for (const node of tree) {
    if (node.id === id) return node;
    const found = findSystem(node.children, id);
    if (found !== null) return found;
  }
  return null;
}

export function subtreeIds(system: SystemTreeNode): Set<System> {
  const ids = new Set<System>();
  const walk = (node: SystemTreeNode) => {
    ids.add(node.id);
    node.children.forEach(walk);
  };
  walk(system);
  return ids;
}

const REL_ORDER: readonly Rel[] = ['boosts', 'unlocks', 'requires'];
const CONFIDENCE_RANK: Record<EdgeConfidence, number> = { documented: 0, provisional: 1, uncertain: 2 };

// Several edges can join the same pair under one rel, one per targeted effect.
// The table lists neighbours, not edges, so those collapse to one link carrying
// the firmest confidence among them.
function groupLinks(
  edges: readonly GraphEdge[],
  otherEnd: (edge: GraphEdge) => string,
  index: GraphIndex,
): { groups: LinkGroup[]; count: number } {
  const byRel = new Map<Rel, Map<string, LinkItem>>();
  for (const edge of edges) {
    const id = otherEnd(edge);
    const confidence = edge.confidence ?? 'documented';
    const links = byRel.get(edge.rel) ?? new Map<string, LinkItem>();
    byRel.set(edge.rel, links);
    const existing = links.get(id);
    if (existing !== undefined) {
      if (CONFIDENCE_RANK[confidence] < CONFIDENCE_RANK[existing.confidence]) existing.confidence = confidence;
      continue;
    }
    const other = index.nodes.get(id);
    links.set(id, { id, name: other?.name ?? id, system: other?.system ?? '', confidence });
  }
  const groups: LinkGroup[] = [];
  let count = 0;
  for (const rel of REL_ORDER) {
    const links = byRel.get(rel);
    if (links === undefined) continue;
    groups.push({ rel, links: [...links.values()] });
    count += links.size;
  }
  return { groups, count };
}

export function buildRows(
  index: GraphIndex,
  systems: ReadonlySet<System>,
  systemNames: ReadonlyMap<System, string>,
): TableRow[] {
  const rows: TableRow[] = [];
  index.order.forEach((id, position) => {
    const node = index.nodes.get(id);
    if (node === undefined || !systems.has(node.system)) return;
    const out = groupLinks(index.outgoing.get(id) ?? [], (edge) => edge.to, index);
    const inc = groupLinks(index.incoming.get(id) ?? [], (edge) => edge.from, index);
    const text = [node.name, node.description ?? ''];
    for (const effect of node.effects ?? []) text.push(effect.text, effect.per_level ?? '');
    rows.push({
      node,
      position,
      systemName: systemNames.get(node.system) ?? node.system,
      outgoing: out.groups,
      incoming: inc.groups,
      outgoingCount: out.count,
      incomingCount: inc.count,
      haystack: text.join('\n').toLowerCase(),
    });
  });
  return rows;
}

/** Every whitespace-separated word must appear, in any order. */
export function filterRows(rows: readonly TableRow[], query: string): readonly TableRow[] {
  const words = query.toLowerCase().split(/\s+/).filter((word) => word.length > 0);
  if (words.length === 0) return rows;
  return rows.filter((row) => words.every((word) => row.haystack.includes(word)));
}

// Numeric collation so "Relic 10" follows "Relic 9" rather than "Relic 1".
const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' });

const COMPARE: Record<SortKey, (a: TableRow, b: TableRow) => number> = {
  name: (a, b) => collator.compare(a.node.name, b.node.name),
  kind: (a, b) => collator.compare(a.node.kind, b.node.kind),
  outgoing: (a, b) => a.outgoingCount - b.outgoingCount,
  incoming: (a, b) => a.incomingCount - b.incomingCount,
};

/** `null` is dataset order. Ties always fall back to dataset order, whatever the direction. */
export function sortRows(rows: readonly TableRow[], sort: Sort | null): readonly TableRow[] {
  if (sort === null) return rows;
  const compare = COMPARE[sort.key];
  const sign = sort.dir === 'asc' ? 1 : -1;
  return [...rows].sort((a, b) => sign * compare(a, b) || a.position - b.position);
}

/**
 * Header click cycle: first direction, then the other, then back to dataset
 * order. Counts open descending because "most connected" is the useful question.
 */
export function nextSort(current: Sort | null, key: SortKey): Sort | null {
  const first: SortDir = key === 'outgoing' || key === 'incoming' ? 'desc' : 'asc';
  if (current === null || current.key !== key) return { key, dir: first };
  if (current.dir === first) return { key, dir: first === 'asc' ? 'desc' : 'asc' };
  return null;
}
