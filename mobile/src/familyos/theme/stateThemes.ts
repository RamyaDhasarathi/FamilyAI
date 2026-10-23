// Scenario moods (AGENT.md §6.2). One value drives the core palette, halo,
// background tint, status dot/label and sheet tint. Colours are 0..1 RGB so
// worklets can interpolate them without parsing strings per frame.
import { hexToRgb } from './tokens';

export type Scenario = 'calm' | 'insight' | 'headsup' | 'urgent';
export const SCENARIOS: Scenario[] = ['calm', 'insight', 'headsup', 'urgent'];

type RGB = [number, number, number];

export interface ScenarioTheme {
  label: string;
  dot: string;
  /** Three-stop facet gradient for the crystal. */
  core: [RGB, RGB, RGB];
  /** How strongly the core palette overrides the natural iridescence (0..1). */
  tintAmount: number;
  halo: RGB;
  /** Large radial background tint behind the gem. */
  bgTint: RGB;
  /** Faint secondary glow from the top-left corner. */
  bgCorner: RGB;
  /** Halo breathing period in seconds. */
  pulsePeriod: number;
  /** Gem tremble amplitude in px (urgent only). */
  tremble: number;
  /** Sheet tint gradient (top → bottom). */
  sheetTint: [string, string];
}

export const scenarioThemes: Record<Scenario, ScenarioTheme> = {
  calm: {
    label: 'CALM',
    dot: '#4DFF8C',
    core: [hexToRgb('#3CEBDF'), hexToRgb('#EE86DA'), hexToRgb('#6F8DFF')],
    tintAmount: 0.6,
    halo: hexToRgb('#2CD9C0'),
    bgTint: [0.04, 0.2, 0.21],
    bgCorner: [0.05, 0.08, 0.16],
    pulsePeriod: 4,
    tremble: 0,
    sheetTint: ['rgba(40,140,150,0.16)', 'rgba(70,90,190,0.10)'],
  },
  insight: {
    label: 'INSIGHT',
    dot: '#A98BFF',
    core: [hexToRgb('#D2BEFF'), hexToRgb('#9270FF'), hexToRgb('#4C3BD0')],
    tintAmount: 0.72,
    halo: hexToRgb('#A98BFF'),
    bgTint: [0.17, 0.1, 0.34],
    bgCorner: [0.1, 0.06, 0.2],
    pulsePeriod: 4,
    tremble: 0,
    sheetTint: ['rgba(140,110,255,0.18)', 'rgba(80,60,180,0.10)'],
  },
  headsup: {
    label: 'HEADS-UP',
    dot: '#FFB23F',
    core: [hexToRgb('#FFD56E'), hexToRgb('#FF9C2A'), hexToRgb('#FFF0D2')],
    tintAmount: 0.78,
    halo: hexToRgb('#FFB23F'),
    bgTint: [0.3, 0.18, 0.04],
    bgCorner: [0.14, 0.09, 0.03],
    pulsePeriod: 3,
    tremble: 0,
    sheetTint: ['rgba(255,170,60,0.16)', 'rgba(150,90,30,0.10)'],
  },
  urgent: {
    label: 'URGENT',
    dot: '#FF4D5E',
    core: [hexToRgb('#E31E45'), hexToRgb('#FF4F72'), hexToRgb('#FFA2C6')],
    tintAmount: 0.82,
    halo: hexToRgb('#FF4D5E'),
    bgTint: [0.36, 0.04, 0.09],
    bgCorner: [0.16, 0.03, 0.06],
    pulsePeriod: 1.6,
    tremble: 1.5,
    sheetTint: ['rgba(255,60,90,0.20)', 'rgba(140,20,40,0.12)'],
  },
};

/** Flat numeric palette used on the UI thread (interpolated between scenarios). */
export function paletteOf(s: Scenario): number[] {
  const t = scenarioThemes[s];
  return [
    ...t.core[0], ...t.core[1], ...t.core[2], // 0..8
    t.tintAmount, // 9
    ...t.halo, // 10..12
    ...t.bgTint, // 13..15
    ...t.bgCorner, // 16..18
    t.pulsePeriod, // 19
    t.tremble, // 20
  ];
}
export const PALETTE_LEN = 21;
