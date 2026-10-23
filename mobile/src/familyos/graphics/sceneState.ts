// Shared values that drive the Home canvas. They live on the UI thread; the
// React tree only writes targets (withTiming / withSpring) and never
// re-renders per frame.
import { createContext, useContext, useMemo } from 'react';
import { makeMutable, type SharedValue } from 'react-native-reanimated';
import { paletteOf, PALETTE_LEN, type Scenario } from '../theme/stateThemes';
import { buildMorphData, type MorphData } from './ParticleMorph';
import { START_ORIENT } from './coreMotion';

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
  /** Dev-only profiling: 1 = skip ambient shader, 2 = skip satellites, 4 = skip core. */
  debugMask: SharedValue<number>;
  /** Dev-only profiling: ms spent per section [satRecord, satDraw, core, morph, picture, uniforms]. */
  prof: SharedValue<number[]>;
  /** Dev-only profiling: worst single-call ms per section, and call counts (indices 6..11). */
  profMax: SharedValue<number[]>;
  morph: SharedValue<MorphData>;

  // Interactive core (AGENT_CORE_AND_FAMILY.md §3), see coreMotion.ts.
  /** Crystal orientation, unit quaternion [w, x, y, z] (model → view). */
  orient: SharedValue<number[]>;
  /** Momentum after a flick: view-space angular velocity [x, y, z] in rad/s. */
  spin: SharedValue<number[]>;
  /** 0..1: how much of the idle rotation is applied (blends back in after a flick). */
  idleBlend: SharedValue<number>;
  /** A finger is rotating the crystal. */
  dragging: SharedValue<boolean>;
  /** Up to 3 jelly ripples: [modelX, modelY, modelZ, startClock] each. */
  ripples: SharedValue<number[]>;
  /** Jelly squash amount s (spring → 0) and its view-space axis. */
  jelly: SharedValue<number>;
  jellyDir: SharedValue<number[]>;
  /** Stretch while dragging (0..0.06) and its screen direction. */
  stretch: SharedValue<number>;
  stretchDir: SharedValue<number[]>;
  /** Dust pushed outward after a tap: px (spring → 0) and screen direction. */
  dustPush: SharedValue<number>;
  dustPushDir: SharedValue<number[]>;
  /** Satellites' parallax shift while dragging, px [x, y]. */
  parallax: SharedValue<number[]>;
  /** Short halo/edge pulse after a tap, 0..1. */
  coreFlash: SharedValue<number>;
  /** Spin haptics: [angle since last tick, ticks this spin]. */
  spinTicks: SharedValue<number[]>;
  /** A flick is slowing down; when it reaches idle speed the crystal wobbles once. */
  settling: SharedValue<boolean>;
  /** Uniform scale pulse (Reduce Motion tap feedback), 1 at rest. */
  corePulse: SharedValue<number>;
  /**
   * Touch input waiting for the next frame: [dx, dy, vx, vy, tx, ty, moved].
   * Gesture handlers only write here (nothing draws from it); the frame
   * callback applies it once per frame. Writing the drawn values straight
   * from touch events made the crystal redraw twice in some frames.
   */
  dragInput: SharedValue<number[]>;
  /** Taps waiting for the next frame: [canvasX, canvasY] pairs. */
  tapInput: SharedValue<number[]>;
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
    debugMask: makeMutable(0),
    prof: makeMutable([0, 0, 0, 0, 0, 0]),
    profMax: makeMutable([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]),
    morph: makeMutable<MorphData>({ n: 0, shapes: [], delay: [], sway: [], phase: [], sinP: [], cosP: [] }),
    orient: makeMutable(START_ORIENT.slice()),
    spin: makeMutable([0, 0, 0]),
    idleBlend: makeMutable(1),
    dragging: makeMutable(false),
    ripples: makeMutable<number[]>([]),
    jelly: makeMutable(0),
    jellyDir: makeMutable([0, 0, 1]),
    stretch: makeMutable(0),
    stretchDir: makeMutable([1, 0]),
    dustPush: makeMutable(0),
    dustPushDir: makeMutable([1, 0]),
    parallax: makeMutable([0, 0]),
    coreFlash: makeMutable(0),
    spinTicks: makeMutable([0, 0]),
    settling: makeMutable(false),
    corePulse: makeMutable(1),
    dragInput: makeMutable([0, 0, 0, 0, 0, 0, 0]),
    tapInput: makeMutable<number[]>([]),
  };
}

/** Current palette, blended between the previous and next scenario. */
/** Dev profiling: add elapsed ms to one section (no-op cost outside dev). */
export function profAdd(s: OrbitScene, k: number, t0: number) {
  'worklet';
  if (!__DEV__) return;
  const dt = performance.now() - t0;
  s.prof.modify((a) => {
    'worklet';
    a[k] += dt;
    return a;
  }, false);
  s.profMax.modify((a) => {
    'worklet';
    if (dt > a[k]) a[k] = dt;
    a[6 + k] += 1;
    return a;
  }, false);
}

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
