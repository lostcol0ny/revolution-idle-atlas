import type { GraphDocument } from '../types';

export const GRAPH_VERSION = 1;
export const GRAPH_URL = '/graph.json';

/** The document was reachable but its shape or version is not usable. */
export class GraphFormatError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'GraphFormatError';
  }
}

/** The document could not be retrieved at all. */
export class GraphFetchError extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = 'GraphFetchError';
  }
}

export function parseGraph(data: unknown): GraphDocument {
  if (typeof data !== 'object' || data === null) {
    throw new GraphFormatError('graph.json is not a JSON object');
  }

  const doc = data as Partial<GraphDocument>;

  if (typeof doc.version !== 'number') {
    throw new GraphFormatError('graph.json has no numeric "version" field');
  }
  if (doc.version !== GRAPH_VERSION) {
    throw new GraphFormatError(
      `this build expects graph format v${GRAPH_VERSION}, got v${doc.version}`,
    );
  }
  if (!Array.isArray(doc.nodes) || !Array.isArray(doc.edges)) {
    throw new GraphFormatError('graph.json is missing "nodes" or "edges"');
  }

  if (doc.systems !== undefined && !Array.isArray(doc.systems)) {
    throw new GraphFormatError('graph.json has a non-array "systems" field');
  }

  // The returned object is rebuilt field by field rather than passed through,
  // so a future producer-side key cannot reach the app without a deliberate
  // change here. `systems` is spread conditionally to keep the key absent
  // rather than present-and-undefined, which the contract test asserts.
  return {
    version: doc.version,
    nodes: doc.nodes,
    edges: doc.edges,
    ...(doc.systems !== undefined ? { systems: doc.systems } : {}),
  };
}

export async function loadGraph(url: string = GRAPH_URL): Promise<GraphDocument> {
  let response: Response;
  try {
    response = await fetch(url);
  } catch (cause) {
    throw new GraphFetchError(`could not reach ${url}`, { cause });
  }

  if (!response.ok) {
    throw new GraphFetchError(`${url} returned HTTP ${response.status}`);
  }

  let data: unknown;
  try {
    data = await response.json();
  } catch {
    throw new GraphFormatError(`${url} is not valid JSON`);
  }

  return parseGraph(data);
}
