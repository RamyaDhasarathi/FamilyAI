// Shared values that drive the Home canvas. They live on the UI thread; the
// React tree only writes targets (withTiming / withSpring) and never
// re-renders per frame.
import { createContext, useContext, useMemo } from 'react';
import { makeMutable, type SharedValue } from 'react-native-reanimated';
import { paletteOf, PALETTE_LEN, type Scenario } from '../theme/stateThemes';
import { buildMorphData, type MorphData } from './ParticleMorph';

export interface OrbitScene {
  /** Seconds of animation time (stops while paused). */
  clock: SharedValue<number>;
  paletteFrom: SharedValue<number[]>;
  paletteTo: SharedValue<number[]>;
  paletteT: SharedValue<number>;
  /** 0 = Home, 1 = Dashboard open (gem shrunk to the mini gem at the top). */
  dashT: SharedValue<number>;
  /** Tap squash, 1 at rest. */
  squash: SharedValue<number>;
  /** Gem shatter for the particle morph, 0..1. */
  explode: SharedValue<number>;
  morphFrom: SharedValue<number>;
  morphTo: SharedValue<number>;
  morphT: SharedValue<number>;
  morphAlpha: SharedValue<number>;
  morphColFrom: SharedValue<number[]>;
  morphColTo: SharedValue<number[]>;
  /** Satellite highlighted during a walkthrough (AGENT_IDS index), -1 none. */
  satHighlight: SharedValue<number>;
  /** Fake audio level while listening, 0..1. */
  listen: SharedValue<number>;
  /** App-open choreography, 0..1. */
  intro: SharedValue<number>;
  /** Backdrop dim under sheets, 0..1. */
  backdrop: SharedValue<number>;
  /** Celebratory burst when the needs-you list empties, 0..1. */
  burst: SharedValue<number>;
  lowPower: SharedValue<boolean>;
  morph: SharedValue<MorphData>;
}

export function createOrbitScene(initial: Scenario): OrbitScene {
  const pal = paletteOf(initial);
  return {
    clock: makeMutable(0),
    paletteFrom: makeMutable(pal),
    paletteTo: makeMutable(pal),
    paletteT: makeMutable(1),
    dashT: makeMutable(0),
    squash: makeMutable(1),
    explode: makeMutable(0),
    morphFrom: makeMutable(0),
    morphTo: makeMutable(0),
    morphT: makeMutable(0),
    morphAlpha: makeMutable(0),
    morphColFrom: makeMutable([0.7, 0.9, 1]),
    morphColTo: makeMutable([0.7, 0.9, 1]),
    satHighlight: makeMutable(-1),
    listen: makeMutable(0),
    intro: makeMutable(0),
    backdrop: makeMutable(0),
    burst: makeMutable(0),
    lowPower: makeMutable(false),
    morph: makeMutable<MorphData>({ n: 0, shapes: [], delay: [], sway: [], phase: [] }),
  };
}

/** Current palette, blended between the previous and next scenario. */
export function currentPalette(s: OrbitScene): number[] {
  'worklet';
  const a = s.paletteFrom.value;
  const b = s.paletteTo.value;
  const t = s.paletteT.value;
  if (t >= 1) return b;
  const out = new Array(PALETTE_LEN);
  for (let i = 0; i < PALETTE_LEN; i++) out[i] = a[i] + (b[i] - a[i]) * t;
  return out;
}

let morphCache: MorphData | null = null;
/**
 * Sample the icon point clouds once (JS thread, Skia paths), cache them, and
 * hand them to this scene's UI-thread value. Every new scene (remount, Fast
 * Refresh) gets the cached clouds.
 */
export function ensureMorphData(s: OrbitScene, n?: number) {
  if (!morphCache) morphCache = buildMorphData(n);
  if (s.morph.value.n === 0) s.morph.value = morphCache;
}

export const OrbitSceneContext = createContext<OrbitScene | null>(null);

export function useOrbitScene(): OrbitScene {
  const s = useContext(OrbitSceneContext);
  if (!s) throw new Error('useOrbitScene must be used inside OrbitSceneContext');
  return s;
}

export function useCreateOrbitScene(initial: Scenario) {
  // eslint-disable-next-line react-hooks/exhaustive-deps
  return useMemo(() => createOrbitScene(initial), []);
}
