export const DEPTHS = [1, 2, 3] as const;
export type Depth = (typeof DEPTHS)[number];
export const DEFAULT_DEPTH: Depth = 2;

export interface UrlState {
  nodeId: string | null;
  depth: Depth;
}

function isDepth(value: number): value is Depth {
  return (DEPTHS as readonly number[]).includes(value);
}

export function parseUrlState(search: string): UrlState {
  const params = new URLSearchParams(search);

  const rawNode = params.get('node');
  const nodeId = rawNode !== null && rawNode.length > 0 ? rawNode : null;

  const rawDepth = Number(params.get('depth'));
  const depth = isDepth(rawDepth) ? rawDepth : DEFAULT_DEPTH;

  return { nodeId, depth };
}

export function toSearch(state: UrlState): string {
  const params = new URLSearchParams();
  if (state.nodeId !== null) {
    params.set('node', state.nodeId);
  }
  params.set('depth', String(state.depth));
  return `?${params.toString()}`;
}
