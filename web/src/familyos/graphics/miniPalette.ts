// Mini-gem palettes (mobile graphics/MiniGem.tsx).
import { hexToRgb } from '../theme/tokens';
import { paletteOf } from '../theme/stateThemes';

/** Palette derived from one agent colour: light → agent → deep, mostly tinted. */
export function agentPalette(hex: string): number[] {
  const [r, g, b] = hexToRgb(hex);
  const base = paletteOf('calm');
  const light = [Math.min(1, r * 0.6 + 0.45), Math.min(1, g * 0.6 + 0.45), Math.min(1, b * 0.6 + 0.45)];
  const deep = [r * 0.55 + 0.1, g * 0.4 + 0.08, b * 0.7 + 0.25];
  return [...light, r, g, b, ...deep, 0.62, r, g, b, ...base.slice(13)];
}
