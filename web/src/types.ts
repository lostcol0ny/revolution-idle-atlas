// The systems declared in data/relationships.yaml. This is a colour and
// ordering hint, not a closed vocabulary: `system` is a free string in the
// dataset, and graph.json may carry ids that are not listed here.
//
// Keep this list minimal — an id nobody declares is dead weight that the
// sidebar tree orders on and TypeScript cannot flag, because
// `Record<KnownSystem, string>` checks that the colour map covers the union,
// not that the union is minimal.
export const KNOWN_SYSTEMS = [
  'revolution',
  'infinity',
  'eternity',
  'unity',
  'tarot',
  'singularity',
  'plague',
  'attacks',
  'astrology',
  'trials',
  'relics',
  'minerals',
  'refine-tree',
  'elements',
  'houses',
] as const;
export type KnownSystem = (typeof KNOWN_SYSTEMS)[number];
export type System = string;

export const KINDS = [
  'relic',
  'stat',
  'tree-node',
  'currency',
  'tarot-card',
  'upgrade',
  'group',
] as const;
export type Kind = (typeof KINDS)[number];

export type Rel = 'boosts' | 'unlocks' | 'requires';
export type Op = 'add' | 'mult' | 'exp';

// These two vocabularies differ deliberately and must never be merged.
// A node's `unknown` means "placeholder, nothing curated yet".
// An edge's `uncertain` means "believed to exist, mechanism not established".
export type NodeConfidence = 'documented' | 'provisional' | 'unknown';
export type EdgeConfidence = 'documented' | 'provisional' | 'uncertain';

export interface GraphEffect {
  text: string;
  per_level?: string;
  op?: Op;
}

export interface GraphSystem {
  id: string;
  name: string;
  parent?: string;
}

export interface GraphNode {
  id: string;
  name: string;
  system: System;
  kind: Kind;
  wiki?: string;
  confidence?: NodeConfidence;
  effects?: GraphEffect[];
}

export interface GraphEdge {
  from: string;
  to: string;
  rel: Rel;
  op?: Op;
  note?: string;
  targets_effect?: number;
  source: string;
  confidence?: EdgeConfidence;
}

export interface GraphDocument {
  version: number;
  nodes: GraphNode[];
  edges: GraphEdge[];
  systems?: GraphSystem[];
}
