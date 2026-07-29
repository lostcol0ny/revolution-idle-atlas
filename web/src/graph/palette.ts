import type { Kind, KnownSystem, Rel } from '../types';

// One colour per system known at the time the palette was fixed. Adding a
// system later must not re-shuffle these. All are dark enough to carry white
// label text at >= 4.5:1 contrast, which palette.test.ts enforces rather than
// trusting this sentence.
const SYSTEM_COLOURS: Record<KnownSystem, string> = {
  revolution: '#3d6a99',
  infinity: '#b0621c',
  eternity: '#3f7a37',
  unity: '#7d4f77',
  tarot: '#a83c3e',
  singularity: '#6d5343',
  plague: '#a3505b',
  attacks: '#8c3f2a',
  astrology: '#4a4f8a',
  trials: '#6b4a2f',
  relics: '#7d4f77',
  minerals: '#2f7d78',
  'refine-tree': '#2a6560',
  elements: '#2b6b8a',
};

const KIND_BADGES: Record<Kind, string> = {
  relic: 'R',
  stat: 'S',
  'tree-node': 'N',
  currency: '$',
  'tarot-card': 'T',
  upgrade: 'U',
  group: 'G',
};

// System ids come from the dataset, not from this file, so a node can legally
// carry one nobody has picked a colour for. Rendering it grey is a worse
// outcome than a bespoke colour and a far better one than `undefined`, which
// reaches the DOM as a missing fill and makes the node invisible.
const UNKNOWN_SYSTEM_COLOUR = '#4b5563';

export function systemColour(system: string): string {
  return SYSTEM_COLOURS[system as KnownSystem] ?? UNKNOWN_SYSTEM_COLOUR;
}

export function kindBadge(kind: Kind): string {
  return KIND_BADGES[kind];
}

// `rel` gets two channels — line style and lightness. Style separates the
// categories; lightness separates signal from background. Both are needed
// because `requires` is 97% of edges and the app's subject is the other 3%.
export const REL_STYLE: Record<Rel, { stroke: string; dash?: string; width: number }> = {
  boosts: { stroke: '#0f172a', width: 2 },
  unlocks: { stroke: '#0f172a', dash: '6 4', width: 2 },
  requires: { stroke: '#cbd5e1', dash: '2 4', width: 1.5 },
};

export const BACK_EDGE_STYLE = { stroke: '#b45309', dash: '4 3', width: 2 };
