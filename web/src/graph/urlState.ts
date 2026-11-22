export const DEPTHS = [1, 2, 3] as const;
export type Depth = (typeof DEPTHS)[number];

export interface UrlState {
  nodeId: string | null;
  systemId: string | null;
  /** `null` means auto: the graph view picks a depth for the node. */
  depth: Depth | null;
}

export type View =
  | { kind: 'item'; nodeId: string }
  | { kind: 'system'; systemId: string }
  | { kind: 'overview' };

function isDepth(value: number): value is Depth {
  return (DEPTHS as readonly number[]).includes(value);
}

export function parseUrlState(search: string): UrlState {
  const params = new URLSearchParams(search);
  const node = params.get('node');
  const system = params.get('system');
  // A missing param reads as 0, which is not a depth, so it lands on auto too.
  const depth = Number(params.get('depth'));
  return {
    nodeId: node !== null && node.length > 0 ? node : null,
    systemId: system !== null && system.length > 0 ? system : null,
    depth: isDepth(depth) ? depth : null,
  };
}

export function toSearch(state: UrlState): string {
  const params = new URLSearchParams();
  if (state.nodeId !== null) params.set('node', state.nodeId);
  if (state.systemId !== null) params.set('system', state.systemId);
  if (state.depth !== null) params.set('depth', String(state.depth));
  const query = params.toString();
  return query.length > 0 ? `?${query}` : '';
}

/** A node wins over a system, which wins over the overview. */
export function viewOf(state: UrlState): View {
  if (state.nodeId !== null) return { kind: 'item', nodeId: state.nodeId };
  if (state.systemId !== null) return { kind: 'system', systemId: state.systemId };
  return { kind: 'overview' };
}
