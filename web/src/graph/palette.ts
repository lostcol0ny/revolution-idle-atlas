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
  animals: '#6b7a2b',
  // Darker parent shade, the convention refine-tree follows under minerals:
  // a nested tab reads as its parent rather than as an eighth sibling. Olive
  // rather than the green it was, because the parent it shades changed.
  'animals-milestones': '#4a5520',
  'eternity-challenges': '#2c5e4e',
  laboratory: '#3d7a63',
  supernova: '#7a6a1f',
  dilation: '#4a6b30',
  'dilation-tree': '#2e5220',
  unity: '#7d4f77',
  tarot: '#a83c3e',
  // Darker Tarot, the nested-tab convention again. Kept red rather than moved
  // off the hue: the cards and their challenges are the same subject and the
  // sidebar is what separates them.
  'tarot-challenges': '#7d2e30',
  singularity: '#6d5343',
  // The Milestones tab holds no nodes of its own, so this paints a sidebar row
  // and nothing on the canvas. That is why it sits 11 from `singularity` when
  // every other colour here clears 20: a grouping row should read as its layer,
  // and there is no node for it to be confused with.
  'singularity-milestones': '#73503a',
  'singularity-milestones-singularity': '#8a5f38',
  'singularity-milestones-atoms': '#5f5a35',
  'singularity-milestones-progression': '#7d4a38',
  'singularity-tree': '#4f3120',
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
// The two lightnesses swapped when the canvas went dark: the emphasised pair was
// near-black ink on white and is now near-white on slate, and `requires` moved the
// other way. The ordering is what carries the meaning, not the particular hexes.
export const REL_STYLE: Record<Rel, { stroke: string; dash?: string; width: number }> = {
  boosts: { stroke: '#e2e8f0', width: 2 },
  unlocks: { stroke: '#e2e8f0', dash: '6 4', width: 2 },
  requires: { stroke: '#64748b', dash: '2 4', width: 1.5 },
};

// Amber either way, but the light-canvas shade sat at 1.9:1 here. This one clears
// 7:1 and still reads as a warning rather than as a third relation.
export const BACK_EDGE_STYLE = { stroke: '#f59e0b', dash: '4 3', width: 2 };
