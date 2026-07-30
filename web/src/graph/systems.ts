import { KNOWN_SYSTEMS, type GraphSystem, type System } from '../types';

export interface SystemTreeNode {
  id: System;
  /** The declared display name, falling back to the raw id when undeclared. */
  name: string;
  /** Nodes whose `system` is exactly this id. */
  direct: number;
  /** `direct` plus every descendant's, matching the coverage report's roll-up. */
  total: number;
  children: SystemTreeNode[];
}

// Declared systems keep their historical order so the sidebar does not
// re-shuffle when the dataset grows; anything undeclared sorts in after them.
function rank(id: System): number {
  const index = (KNOWN_SYSTEMS as readonly string[]).indexOf(id);
  return index === -1 ? KNOWN_SYSTEMS.length : index;
}

function compare(a: SystemTreeNode, b: SystemTreeNode): number {
  return rank(a.id) - rank(b.id) || a.id.localeCompare(b.id);
}

/**
 * Nest each system under its declared parent, rolling node counts upward.
 *
 * `counts` is keyed by the `system` field of the nodes themselves, so a system
 * that only ever appears there — never declared in the document — still gets a
 * row, at the root. The alternative is a node the sidebar cannot reach.
 *
 * Systems whose rolled-up total is zero are dropped, which is what keeps a
 * declared-but-empty branch from rendering as a dead end.
 */
export function buildSystemTree(
  systems: readonly GraphSystem[],
  counts: ReadonlyMap<System, number>,
): SystemTreeNode[] {
  const declared = new Map<System, GraphSystem>();
  for (const system of systems) declared.set(system.id, system);

  const nodes = new Map<System, SystemTreeNode>();
  for (const id of new Set([...declared.keys(), ...counts.keys()])) {
    nodes.set(id, {
      id,
      name: declared.get(id)?.name ?? id,
      direct: counts.get(id) ?? 0,
      total: 0,
      children: [],
    });
  }

  const parentOf = (id: System): System | undefined => {
    const parent = declared.get(id)?.parent;
    if (parent === undefined || parent === id || !nodes.has(parent)) return undefined;
    return parent;
  };

  // The build rejects a cycle in the parent chain, but that check runs in a
  // different language on the other side of the network. Were one to arrive,
  // attaching every member to its parent would leave the whole loop unreachable
  // from any root — silently vanishing from the sidebar. Entering members stay
  // at the root instead, so the nodes remain reachable.
  const inCycle = (id: System): boolean => {
    const seen = new Set<System>([id]);
    for (let at = parentOf(id); at !== undefined; at = parentOf(at)) {
      if (seen.has(at)) return true;
      seen.add(at);
    }
    return false;
  };

  const roots: SystemTreeNode[] = [];
  for (const node of nodes.values()) {
    const parent = parentOf(node.id);
    if (parent === undefined || inCycle(node.id)) roots.push(node);
    else nodes.get(parent)?.children.push(node);
  }

  const roll = (node: SystemTreeNode): number => {
    node.children.sort(compare);
    node.total = node.children.reduce((sum, child) => sum + roll(child), node.direct);
    return node.total;
  };
  for (const root of roots) roll(root);

  const prune = (list: SystemTreeNode[]): SystemTreeNode[] =>
    list.filter((node) => node.total > 0).map((node) => ({ ...node, children: prune(node.children) }));

  return prune(roots.sort(compare));
}
