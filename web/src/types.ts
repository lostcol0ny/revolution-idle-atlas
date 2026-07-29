export const SYSTEMS = [
  'revolution',
  'infinity',
  'eternity',
  'unity',
  'zodiac',
  'mineral',
  'tarot',
  'singularity',
  'plague',
] as const;
export type System = (typeof SYSTEMS)[number];

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

export interface GraphNode {
  id: string;
  name: string;
  system: System;
  kind: Kind;
  wiki?: string;
  confidence?: NodeConfidence;
}

export interface GraphEdge {
  from: string;
  to: string;
  rel: Rel;
  op?: Op;
  note?: string;
  source: string;
  confidence?: EdgeConfidence;
}

export interface GraphDocument {
  version: number;
  nodes: GraphNode[];
  edges: GraphEdge[];
}
