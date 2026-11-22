import type { GraphIndex } from './adjacency';
import type { GraphSystem } from '../types';

/**
 * Top-level systems whose direct children get their own overview node.
 * Unity holds most of the late game in a dozen loosely coupled subsystems, so
 * rolling it into one box would hide most of the cross-system links; the other
 * top-level systems are small enough to read as a single unit.
 */
export const EXPANDED_SYSTEMS: readonly string[] = ['unity'];

export interface OverviewSystem {
  id: string;
  name: string;
  /** Items in this system and every descendant rolled into it. */
  count: number;
}

export interface OverviewEdge {
  from: string;
  to: string;
  total: number;
  /** Links whose confidence is anything but `uncertain`. */
  established: number;
  uncertain: number;
}

export interface Overview {
  systems: OverviewSystem[];
  edges: OverviewEdge[];
}

/** Map every system id to the overview node it is drawn as. */
export function displayGroups(
  systems: readonly GraphSystem[],
  expanded: readonly string[] = EXPANDED_SYSTEMS,
): (system: string) => string {
  const parent = new Map<string, string>();
  for (const s of systems) if (s.parent !== undefined && s.parent !== s.id) parent.set(s.id, s.parent);
  const cache = new Map<string, string>();

  return (system) => {
    const hit = cache.get(system);
    if (hit !== undefined) return hit;
    const chain = [system];
    const seen = new Set(chain);
    for (let at = parent.get(system); at !== undefined && !seen.has(at); at = parent.get(at)) {
      chain.push(at);
      seen.add(at);
    }
    // chain ends at the root; a child of an expanded root stays its own group.
    const root = chain[chain.length - 1];
    const group = chain.length >= 2 && expanded.includes(root) ? chain[chain.length - 2] : root;
    cache.set(system, group);
    return group;
  };
}

export function buildOverview(index: GraphIndex, expanded: readonly string[] = EXPANDED_SYSTEMS): Overview {
  const groupOf = displayGroups(index.systems, expanded);
  const names = new Map(index.systems.map((s) => [s.id, s.name]));

  const counts = new Map<string, number>();
  const nodeGroup = new Map<string, string>();
  for (const id of index.order) {
    const node = index.nodes.get(id);
    if (node === undefined) continue;
    const group = groupOf(node.system);
    nodeGroup.set(id, group);
    counts.set(group, (counts.get(group) ?? 0) + 1);
  }

  const edges = new Map<string, OverviewEdge>();
  for (const list of index.outgoing.values()) {
    for (const edge of list) {
      const from = nodeGroup.get(edge.from);
      const to = nodeGroup.get(edge.to);
      if (edge.rel !== 'boosts' || from === undefined || to === undefined || from === to) continue;
      const key = `${from}\u0000${to}`;
      let agg = edges.get(key);
      if (agg === undefined) {
        agg = { from, to, total: 0, established: 0, uncertain: 0 };
        edges.set(key, agg);
      }
      agg.total += 1;
      if (edge.confidence === 'uncertain') agg.uncertain += 1;
      else agg.established += 1;
    }
  }

  // Declared order first so the cards follow game progression.
  const order = [...index.systems.map((s) => s.id), ...counts.keys()];
  const systems = [...new Set(order)]
    .filter((id) => counts.has(id))
    .map((id) => ({ id, name: names.get(id) ?? id, count: counts.get(id) ?? 0 }));

  return { systems, edges: [...edges.values()] };
}
