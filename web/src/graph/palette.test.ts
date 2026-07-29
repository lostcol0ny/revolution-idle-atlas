import { describe, expect, it } from 'vitest';
import { systemColour } from './palette';
import { SYSTEMS } from '../types';

// palette.ts asserts in prose that every system colour carries white label text
// at >= 4.5:1. AtlasNode renders exactly that — white 13px text on the system
// colour — so the claim is load-bearing, and prose does not fail a build. It was
// already false once: #b5651d gave infinity 4.34:1.
const WCAG_AA_NORMAL_TEXT = 4.5;

function relativeLuminance(hex: string): number {
  const channels = [1, 3, 5].map((offset) => parseInt(hex.slice(offset, offset + 2), 16) / 255);
  const [r, g, b] = channels.map((c) =>
    c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4,
  );
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrastWithWhite(hex: string): number {
  return 1.05 / (relativeLuminance(hex) + 0.05);
}

describe('system colours', () => {
  it.each(SYSTEMS)('carries white label text at AA contrast: %s', (system) => {
    const colour = systemColour(system);
    expect(colour).toMatch(/^#[0-9a-f]{6}$/);
    expect(contrastWithWhite(colour)).toBeGreaterThanOrEqual(WCAG_AA_NORMAL_TEXT);
  });
});
