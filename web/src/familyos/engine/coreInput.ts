// Interactive core (AGENT_CORE_AND_FAMILY.md §3), ported from the mobile
// app's graphics/coreInput.ts and the stepCore() of OrbitScene.tsx. Pointer
// handlers only QUEUE input; applyCoreInput turns it into rotation, stretch,
// parallax and jelly once per frame, so the crystal is drawn exactly once per
// frame however many pointer events arrive.
import { AGENT_IDS, colors, hexToRgb } from '../theme/tokens';
import { springs } from '../theme/motion';
import { paletteOf, PALETTE_LEN, type Scenario } from '../theme/stateThemes';
import {
  FRICTION,
  FRICTION_REDUCED,
  IDLE_AXIS,
  IDLE_SPEED,
  JELLY_SPRING,
  hitCrystal,
  qRotateView,
  qToMat,
} from '../graphics/coreMotion';
import { ease, spring, timing } from './tween';
import { currentPalette, type OrbitScene } from './sceneState';
import { gemAt, type Stage } from './orbitLayout';
import { RIPPLE_LIFE } from './crystalRender';

/** Max stretch along the drag (§3.4.3). */
const MAX_STRETCH = 0.06;
const AGENT_RGB = AGENT_IDS.map((id) => hexToRgb(colors.agents[id]));

export function queueDrag(scene: OrbitScene, dx: number, dy: number, vx: number, vy: number, tx: number, ty: number) {
  const a = scene.dragInput;
  a[0] += dx;
  a[1] += dy;
  a[2] = vx;
  a[3] = vy;
  a[4] = tx;
  a[5] = ty;
  a[6] = 1;
}

export function queueTap(scene: OrbitScene, x: number, y: number) {
  scene.tapInput.push(x, y);
}

/** The jelly for a crystal centred at (gx, gy) with radius R (Home core, Family header). */
export function jellyAtGem(scene: OrbitScene, gx: number, gy: number, R: number, sx: number, sy: number, reduced: boolean) {
  if (reduced) {
    // Reduced motion: a gentle 0.96 pulse only.
    scene.tw.seq('corePulse', [timing(0.96, 90, ease.outCubic), timing(1, 220, ease.outCubic)]);
    return;
  }
  const hit = hitCrystal(sx, sy, gx, gy, R, qToMat(scene.orient));
  // Keep at most 3 ripples; each starts at the current scene clock.
  const rp = scene.ripples;
  const next = rp.length >= 12 ? rp.slice(4) : rp.slice();
  next.push(hit.model[0], hit.model[1], hit.model[2], scene.clock);
  scene.ripples = next;
  // Squash along the tap direction; repeated taps add up, clamped so the shape never inverts.
  scene.jellyDir = hit.view;
  scene.tw.set('jelly', Math.min(0.2, Math.max(0, scene.v.jelly) + 0.12));
  scene.tw.to('jelly', spring(0, JELLY_SPRING));
  scene.tw.set('coreFlash', 1);
  scene.tw.to('coreFlash', timing(0, 700, ease.linear));
  const dx = sx - gx;
  const dy = sy - gy;
  const dl = Math.hypot(dx, dy) || 1;
  scene.dustPushDir = [dx / dl, dy / dl];
  scene.tw.set('dustPush', 10);
  scene.tw.to('dustPush', spring(0, { damping: 9, stiffness: 110, mass: 1 }));
}

/** Tap at stage point (sx, sy): dent + ripple, squash, halo pulse, dust puff (§3.3). */
export function jellyAt(scene: OrbitScene, stage: Stage, sx: number, sy: number, reduced: boolean) {
  // No jelly while the crystal is broken into an agent icon.
  if (scene.v.morphAlpha > 0.01 || scene.v.explode > 0.01) return;
  const g = gemAt(stage, scene.v.dashT);
  jellyAtGem(scene, g.x, g.y, g.r * (0.85 + 0.15 * scene.v.intro), sx, sy, reduced);
}

/** Apply queued drag and taps. Called by the loop, before stepCore. */
export function applyCoreInput(scene: OrbitScene, stage: Stage, reduced: boolean) {
  const d = scene.dragInput;
  if (d[6] === 1) {
    const R = gemAt(stage, scene.v.dashT).r;
    const dist = Math.hypot(d[0], d[1]);
    // Trackball: rotate about the screen axis perpendicular to the movement by
    // distance / radius. Right → about +y, down → about +x (view space), so the
    // surface under the pointer moves with it.
    if (dist > 0) scene.orient = qRotateView(scene.orient, d[1], d[0], 0, dist / R);
    const sp = Math.hypot(d[2], d[3]);
    const target = reduced ? 0 : MAX_STRETCH * Math.min(1, sp / 2500);
    scene.tw.set('stretch', scene.v.stretch * 0.75 + target * 0.25);
    if (sp > 1) scene.stretchDir = [d[2] / sp, d[3] / sp];
    // Satellites shift 2–3 px with the drag.
    scene.parallax = [Math.max(-3, Math.min(3, d[4] * 0.02)), Math.max(-3, Math.min(3, d[5] * 0.02))];
    scene.dragInput = [0, 0, 0, 0, 0, 0, 0];
  }
  const taps = scene.tapInput;
  if (taps.length > 0) {
    scene.tapInput = [];
    for (let i = 0; i < taps.length; i += 2) jellyAt(scene, stage, taps[i], taps[i + 1], reduced);
  }
}

/**
 * Integrate the crystal's orientation for one frame (§3.4): flick momentum
 * with friction, then the idle spin blended back in once the crystal is
 * slower than idle.
 */
export function stepCore(scene: OrbitScene, dt: number, reduced: boolean) {
  let q = scene.orient;
  const dragging = scene.dragging;
  const w = scene.spin;
  const wl = Math.hypot(w[0], w[1], w[2]);
  if (!dragging && wl > 1e-3) {
    q = qRotateView(q, w[0], w[1], w[2], wl * dt);
    const k = Math.exp(-(reduced ? FRICTION_REDUCED : FRICTION) * dt);
    scene.spin = wl * k < 1e-3 ? [0, 0, 0] : [w[0] * k, w[1] * k, w[2] * k];
  }
  // Idle rotation: off while dragging or spinning faster than idle, then
  // blended back in over 1.2 s, continuing from the current orientation.
  if (dragging || wl >= IDLE_SPEED) {
    scene.idleBlend = 0;
  } else {
    if (scene.settling) {
      // One small wobble as the flick settles, across the spin axis.
      scene.settling = false;
      if (!reduced && wl > 1e-3) {
        scene.jellyDir = [w[1] / wl, -w[0] / wl, 0];
        scene.tw.set('jelly', 0.04);
        scene.tw.to('jelly', spring(0, JELLY_SPRING));
      }
    }
    scene.idleBlend = Math.min(1, scene.idleBlend + dt / 1.2);
  }
  // Satellites' drag parallax eases back once the pointer lifts.
  if (!dragging) {
    const par = scene.parallax;
    if (par[0] !== 0 || par[1] !== 0) {
      const k = Math.exp(-10 * dt);
      scene.parallax = Math.abs(par[0]) + Math.abs(par[1]) < 0.05 ? [0, 0] : [par[0] * k, par[1] * k];
    }
  }
  const idle = reduced ? 0 : IDLE_SPEED * scene.idleBlend;
  if (idle > 0) q = qRotateView(q, IDLE_AXIS[0], IDLE_AXIS[1], IDLE_AXIS[2], idle * dt);
  scene.orient = q;
  // Forget ripples that have died out.
  const rp = scene.ripples;
  if (rp.length > 0 && scene.clock - rp[3] > RIPPLE_LIFE) scene.ripples = rp.slice(4);
}

/** A pointer starts rotating the crystal: momentum and idle spin stop. */
export function beginDrag(scene: OrbitScene) {
  scene.dragging = true;
  scene.spin = [0, 0, 0];
  scene.idleBlend = 0;
  scene.settling = false;
}

/** The pointer lets go: flick momentum, then the stretch springs back. */
export function endDrag(scene: OrbitScene, vx: number, vy: number, R: number, maxSpin: number, reduced: boolean) {
  flick(scene, vx, vy, R, maxSpin);
  scene.dragging = false;
  scene.tw.to('stretch', reduced ? timing(0, 150) : spring(0, JELLY_SPRING));
}

/** Satellite ringed during a walkthrough (AGENT_IDS index, −1 = none). */
export function setHighlight(scene: OrbitScene, i: number) {
  scene.satHighlight = i;
}

/** Satellite under the mouse (−1 = none). */
export function setHover(scene: OrbitScene, i: number) {
  scene.satHover = i;
}

/** Start a flick from a pointer release (surface speed → angular velocity, ≤ 4 turns/s). */
export function flick(scene: OrbitScene, vx: number, vy: number, R: number, maxSpin: number) {
  const sp = Math.hypot(vx, vy);
  if (sp > 80) {
    const w = Math.min(maxSpin, sp / R);
    scene.spin = [(vy / sp) * w, (vx / sp) * w, 0];
    scene.settling = w > IDLE_SPEED;
  }
}

/** Morph the particle cloud to `shape` (0 = gem, 1..5 = agent icons). Mobile: useWalkthrough.morphScene. */
export function morphScene(scene: OrbitScene, shape: number) {
  const from = scene.morphTo;
  if (from === shape && scene.v.morphAlpha > 0.5) return;
  const pal = currentPalette(scene);
  const gemColour = [pal[10], pal[11], pal[12]];
  scene.morphFrom = from;
  scene.morphColFrom = from === 0 ? gemColour : scene.morphColTo;
  scene.morphColTo = shape === 0 ? gemColour : AGENT_RGB[shape - 1];
  scene.morphTo = shape;
  scene.tw.set('morphT', 0);
  scene.tw.to('morphT', timing(1, 900, ease.linear));
  if (shape !== 0) {
    scene.tw.to('morphAlpha', timing(1, 220, ease.inOutCubic));
    scene.tw.to('explode', timing(1, 650, ease.outCubic));
  } else {
    scene.tw.to('morphAlpha', timing(0, 380, ease.inOutCubic, 520));
    scene.tw.to('explode', timing(0, 700, ease.inOutCubic, 320));
  }
}

/** Every scenario change interpolates palette, halo and background together (700 ms). */
export function blendToScenario(scene: OrbitScene, mood: Scenario, instant = false) {
  const target = paletteOf(mood);
  if (instant) {
    scene.paletteFrom = target;
    scene.paletteTo = target;
    scene.tw.set('paletteT', 1);
    return;
  }
  // Start from wherever the blend currently is, so rapid changes never snap.
  const cur = currentPalette(scene, new Array(PALETTE_LEN)).slice();
  scene.paletteFrom = cur;
  scene.paletteTo = target;
  scene.tw.set('paletteT', 0);
  scene.tw.to('paletteT', timing(1, 700, ease.inOutSine));
}

/** When the last item is resolved: burst of particles and a squash (§8.4). */
export function celebrate(scene: OrbitScene) {
  scene.tw.set('burst', 1);
  scene.tw.to('burst', timing(0, 1500, ease.outCubic));
  scene.tw.seq('squash', [timing(0.9, 120, ease.outCubic), timing(1, 500, ease.outCubic)]);
}

/** Opening / closing the Dashboard follows the input, then settles with the soft spring. */
export function settleDash(scene: OrbitScene, open: boolean) {
  scene.tw.to('dashT', spring(open ? 1 : 0, springs.soft));
}
