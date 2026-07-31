import type { Kind, KnownSystem, Rel } from '../types';

// One colour per system known at the time the palette was fixed. Adding a
// system later must not re-shuffle these. All are dark enough to carry white
// label text at >= 4.5:1 contrast, which palette.test.ts enforces rather than
// trusting this sentence.
export const SYSTEM_COLOURS: Record<KnownSystem, string> = {
  revolution: '#3d6a99',
  infinity: '#b0621c',
  // Infinity's four tabs, kept in the layer's amber band for the same reason
  // Eternity's are kept in a green one.
  'infinity-upgrades': '#8a5a12',
  'infinity-challenges': '#9c4a12',
  generators: '#a06a35',
  // Pulled off gold and onto tan deliberately: the obvious choice sat 18 apart
  // from supernova, and two star-themed systems in the same yellow are the one
  // pair a reader would actually try to tell apart.
  stars: '#8a6f55',
  eternity: '#3f7a37',
  // Eternity's seven tabs. They stay inside a green/olive/teal band so the layer
  // reads as one block at a glance, which is the only cue the canvas gives —
  // the sidebar is where the exact system is named. Separation within the band
  // is tighter than across the wheel but no tighter than pairs the palette
  // already carries.
  'eternity-milestones': '#2f6b2a',
  // Darker parent shade, the convention refine-tree follows under minerals:
  // a nested tab reads as its parent rather than as an eighth sibling.
  'animals-milestones': '#1d451a',
  animals: '#6b7a2b',
  'eternity-challenges': '#2c5e4e',
  laboratory: '#3d7a63',
  supernova: '#7a6a1f',
  dilation: '#4a6b30',
  'dilation-tree': '#2e5220',
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
  // Darker Singularity, the way refine-tree is darker Minerals: a child system
  // reads as its parent's shade rather than competing with it.
  houses: '#574235',
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
// because `requires` is just over half of edges and the app's subject is the rest.
export const REL_STYLE: Record<Rel, { stroke: string; dash?: string; width: number }> = {
  boosts: { stroke: '#0f172a', width: 2 },
  unlocks: { stroke: '#0f172a', dash: '6 4', width: 2 },
  requires: { stroke: '#cbd5e1', dash: '2 4', width: 1.5 },
};

export const BACK_EDGE_STYLE = { stroke: '#b45309', dash: '4 3', width: 2 };
