import type { Kind, Rel, System } from '../types';

// One colour per System enum member, fixed up front. Only four systems appear
// in the data today; adding zodiac later must not re-shuffle existing colours.
// All are dark enough to carry white label text at >= 4.5:1 contrast, which
// palette.test.ts enforces rather than trusting this sentence.
const SYSTEM_COLOURS: Record<System, string> = {
  revolution: '#3d6a99',
  infinity: '#b0621c',
  eternity: '#3f7a37',
  unity: '#7d4f77',
  zodiac: '#8a6d12',
  mineral: '#2f7d78',
  tarot: '#a83c3e',
  singularity: '#6d5343',
  plague: '#a3505b',
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

export function systemColour(system: System): string {
  return SYSTEM_COLOURS[system];
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
