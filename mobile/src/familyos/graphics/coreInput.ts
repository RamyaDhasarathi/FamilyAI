// Touch input for the interactive core (AGENT_CORE_AND_FAMILY.md §3), as
// worklets. Gesture handlers only QUEUE input; `applyCoreInput` turns it into
// rotation, stretch, parallax and jelly once per frame, inside the frame
// callback, so the crystal is drawn exactly once per frame however many touch
// events arrive.
import { withSequence, withSpring, withTiming } from 'react-native-reanimated';
import type { OrbitScene } from './sceneState';
import { gemAt, type Frame } from './orbitLayout';
import { hitCrystal, JELLY_SPRING, qRotateView, qToMat } from './coreMotion';

/** Max stretch along the drag (§3.4.3). */
const MAX_STRETCH = 0.06;

export function queueDrag(scene: OrbitScene, dx: number, dy: number, vx: number, vy: number, tx: number, ty: number) {
  'worklet';
  scene.dragInput.modify((a) => {
    'worklet';
    a[0] += dx;
    a[1] += dy;
    a[2] = vx;
    a[3] = vy;
    a[4] = tx;
    a[5] = ty;
    a[6] = 1;
    return a;
  }, false);
}

export function queueTap(scene: OrbitScene, x: number, y: number) {
  'worklet';
  scene.tapInput.modify((a) => {
    'worklet';
    a.push(x, y);
    return a;
  }, false);
}

/** The jelly for a crystal centred at (gx, gy) with radius R (Home core, Family header).
 *  Declared before jellyAt: a worklet captures what it calls when the module
 *  loads, so a callee declared later would be undefined on the UI thread. */
export function jellyAtGem(scene: OrbitScene, gx: number, gy: number, R: number, sx: number, sy: number, reduced: boolean) {
  'worklet';
  if (reduced) {
    // Reduce Motion: a gentle 0.96 pulse only.
    scene.corePulse.set(withSequence(withTiming(0.96, { duration: 90 }), withTiming(1, { duration: 220 })));
    return;
  }
  const g = { x: gx, y: gy };
  const hit = hitCrystal(sx, sy, gx, gy, R, qToMat(scene.orient.get()));
  // Keep at most 3 ripples; each starts at the current scene clock.
  const rp = scene.ripples.get();
  const next = rp.length >= 12 ? rp.slice(4) : rp.slice();
  next.push(hit.model[0], hit.model[1], hit.model[2], scene.clock.get());
  scene.ripples.set(next);
  // Squash along the tap direction; repeated taps add up, clamped so the shape never inverts.
  scene.jellyDir.set(hit.view);
  scene.jelly.set(Math.min(0.2, Math.max(0, scene.jelly.get()) + 0.12));
  scene.jelly.set(withSpring(0, JELLY_SPRING));
  scene.coreFlash.set(1);
  scene.coreFlash.set(withTiming(0, { duration: 700 }));
  const dx = sx - g.x;
  const dy = sy - g.y;
  const dl = Math.hypot(dx, dy) || 1;
  scene.dustPushDir.set([dx / dl, dy / dl]);
  scene.dustPush.set(10);
  scene.dustPush.set(withSpring(0, { damping: 9, stiffness: 110, mass: 1 }));
}

/** Tap at canvas point (sx, sy): dent + ripple, squash, halo pulse, dust puff (§3.3). */
export function jellyAt(scene: OrbitScene, frame: Frame, sx: number, sy: number, reduced: boolean) {
  'worklet';
  // No jelly while the crystal is broken into an agent icon.
  if (scene.morphAlpha.get() > 0.01 || scene.explode.get() > 0.01) return;
  const g = gemAt(frame, scene.dashT.get());
  jellyAtGem(scene, g.x, g.y, g.r * (0.85 + 0.15 * scene.intro.get()), sx, sy, reduced);
}

/** Apply queued drag and taps. Called from the frame callback, before stepCore. */
export function applyCoreInput(scene: OrbitScene, frame: Frame, reduced: boolean) {
  'worklet';
  const d = scene.dragInput.get();
  if (d[6] === 1) {
    const R = gemAt(frame, scene.dashT.get()).r;
    const dist = Math.hypot(d[0], d[1]);
    // Trackball: rotate about the screen axis perpendicular to the movement by
    // distance / radius. Right → about +y, down → about +x (view space), so the
    // surface under the finger moves with the finger.
    if (dist > 0) scene.orient.set(qRotateView(scene.orient.get(), d[1], d[0], 0, dist / R));
    const sp = Math.hypot(d[2], d[3]);
    const target = reduced ? 0 : MAX_STRETCH * Math.min(1, sp / 2500);
    scene.stretch.set(scene.stretch.get() * 0.75 + target * 0.25);
    if (sp > 1) scene.stretchDir.set([d[2] / sp, d[3] / sp]);
    // Satellites shift 2–3 px with the drag.
    scene.parallax.set([Math.max(-3, Math.min(3, d[4] * 0.02)), Math.max(-3, Math.min(3, d[5] * 0.02))]);
    scene.dragInput.set([0, 0, 0, 0, 0, 0, 0]);
  }
  const taps = scene.tapInput.get();
  if (taps.length > 0) {
    scene.tapInput.set([]);
    for (let i = 0; i < taps.length; i += 2) jellyAt(scene, frame, taps[i], taps[i + 1], reduced);
  }
}
