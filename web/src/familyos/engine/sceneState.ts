// State that drives the Home stage (the web counterpart of the mobile app's
// graphics/sceneState.ts shared values). Plain mutable data: React only
// writes targets through `scene.tw` and never re-renders per frame; the
// render loop reads everything once per frame.
import { paletteOf, PALETTE_LEN, type Scenario } from '../theme/stateThemes';
import { START_ORIENT } from '../graphics/coreMotion';
import { Tweens } from './tween';
import type { MorphData } from './morphData';

/** Every animatable number of the stage. */
export interface SceneNums {
  /** 0 = Home, 1 = Dashboard open (gem shrunk to the mini gem at the top). */
  dashT: number;
  /** Tap squash, 1 at rest. */
  squash: number;
  /** Gem shatter for the particle morph, 0..1. */
  explode: number;
  morphT: number;
  morphAlpha: number;
  /** Fake audio level while listening, 0..1. */
  listen: number;
  /** App-open choreography, 0..1. */
  intro: number;
  /** Celebratory burst when the needs-you list empties, 1 → 0. */
  burst: number;
  paletteT: number;
  /** Jelly squash amount (spring → 0). */
  jelly: number;
  /** Stretch while dragging (0..0.06). */
  stretch: number;
  /** Dust pushed outward after a tap, px (spring → 0). */
  dustPush: number;
  /** Short halo/edge pulse after a tap, 0..1. */
  coreFlash: number;
  /** Uniform scale pulse (reduced-motion tap feedback), 1 at rest. */
  corePulse: number;
  /** Hover tilt towards the cursor (web only, §7.1), radians about x and y. */
  tiltX: number;
  tiltY: number;
  /** Background dim under panels, 0..1 (web: the canvas fades rather than blurs per frame). */
  backdrop: number;
}

export interface OrbitScene {
  v: SceneNums;
  tw: Tweens<keyof SceneNums>;
  /** Seconds of animation time. */
  clock: number;
  paletteFrom: number[];
  paletteTo: number[];
  morphFrom: number;
  morphTo: number;
  morphColFrom: number[];
  morphColTo: number[];
  /** Satellite highlighted during a walkthrough (AGENT_IDS index), -1 none. */
  satHighlight: number;
  /** Satellite under the mouse (web hover, §7.3), -1 none. */
  satHover: number;
  lowPower: boolean;
  /** Reduced motion: no ambient rotation or drift (§6.5). */
  still: boolean;
  morph: MorphData | null;

  // Interactive core (AGENT_CORE_AND_FAMILY.md §3), see graphics/coreMotion.ts.
  orient: number[];
  spin: number[];
  idleBlend: number;
  dragging: boolean;
  ripples: number[];
  jellyDir: number[];
  stretchDir: number[];
  dustPushDir: number[];
  parallax: number[];
  settling: boolean;
  /** Touch input waiting for the next frame: [dx, dy, vx, vy, tx, ty, moved]. */
  dragInput: number[];
  /** Taps waiting for the next frame: [x, y] pairs in stage px. */
  tapInput: number[];
}

export function createOrbitScene(initial: Scenario): OrbitScene {
  const pal = paletteOf(initial);
  const v: SceneNums = {
    dashT: 0, squash: 1, explode: 0, morphT: 0, morphAlpha: 0, listen: 0, intro: 0, burst: 0, paletteT: 1,
    jelly: 0, stretch: 0, dustPush: 0, coreFlash: 0, corePulse: 1, tiltX: 0, tiltY: 0, backdrop: 0,
  };
  return {
    v,
    tw: new Tweens(v as unknown as Record<keyof SceneNums, number>),
    clock: 0,
    paletteFrom: pal,
    paletteTo: pal,
    morphFrom: 0,
    morphTo: 0,
    morphColFrom: [0.7, 0.9, 1],
    morphColTo: [0.7, 0.9, 1],
    satHighlight: -1,
    satHover: -1,
    lowPower: false,
    still: false,
    morph: null,
    orient: START_ORIENT.slice(),
    spin: [0, 0, 0],
    idleBlend: 1,
    dragging: false,
    ripples: [],
    jellyDir: [0, 0, 1],
    stretchDir: [1, 0],
    dustPushDir: [1, 0],
    parallax: [0, 0],
    settling: false,
    dragInput: [0, 0, 0, 0, 0, 0, 0],
    tapInput: [],
  };
}

/** Current palette, blended between the previous and next scenario. */
export function currentPalette(s: OrbitScene, out?: number[]): number[] {
  const a = s.paletteFrom;
  const b = s.paletteTo;
  const t = s.v.paletteT;
  if (t >= 1) return b;
  const o = out ?? new Array(PALETTE_LEN);
  for (let i = 0; i < PALETTE_LEN; i++) o[i] = a[i] + (b[i] - a[i]) * t;
  return o;
}
