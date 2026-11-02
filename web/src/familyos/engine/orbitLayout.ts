// Where things sit on the Home stage (AGENT_WEB.md §7.1, §7.3, §8.0). Shared
// by the WebGL scene and the DOM overlays (labels, badges, hit areas) so they
// never drift apart.
//
// Phones (< 640 px) use the mobile app's formulas unchanged: positions are
// fractions of the screen. Wider screens keep the same composition by laying
// out a *virtual phone frame* (vw × vh, the mobile aspect) and fitting its
// constellation band (Finance at the top down to the Household / Grocery
// labels) between the top margin and the status block. The relative
// positions of gem and satellites are then exactly the phone's, the stage
// never stretches into an ellipse, and the background still fills the
// viewport.
import type { AgentId } from '../theme/tokens';
import { AGENT_IDS } from '../theme/tokens';

/** Length of the master ambient loop in seconds. The core spins 4× per loop. */
export const AMBIENT_LOOP = 72;

/** Satellite anchors as fractions of the (virtual) frame (from the video). */
export const SATELLITE_ANCHORS: Record<AgentId, [number, number]> = {
  finance: [0.5, 0.23],
  education: [0.87, 0.38],
  grocery: [0.73, 0.61],
  household: [0.3, 0.61],
  calendar: [0.12, 0.38],
};
const ANCHORS = AGENT_IDS.map((id) => SATELLITE_ANCHORS[id]);

/** Date, greeting and summary line (home.css), px. */
export const HEADER_H = 112;

/** Height / width of the reference phone (390 × 844). */
const PHONE_ASPECT = 844 / 390;

export type Breakpoint = 'phone' | 'tablet' | 'desktop' | 'large';

export function breakpointOf(w: number): Breakpoint {
  if (w < 640) return 'phone';
  if (w < 1024) return 'tablet';
  if (w < 1920) return 'desktop';
  return 'large';
}

export interface Stage {
  /** Viewport, CSS px. */
  W: number;
  H: number;
  bp: Breakpoint;
  /** Virtual frame and its top-left corner on screen. */
  vw: number;
  vh: number;
  ox: number;
  oy: number;
  /** Gem radius multiplier on larger screens (the hero reads a little bolder). */
  boost: number;
  /** Satellite labels hidden on very short viewports, where they would overlap. */
  labels: boolean;
  /** Where the gem shrinks to when the Dashboard is open. */
  dash: { x: number; y: number; r: number };
  /** Top of the Dashboard panel, px. */
  dashTop: number;
}

export function computeStage(W: number, H: number): Stage {
  const bp = breakpointOf(W);
  const phoneDash = { x: W * 0.5, y: Math.max(W * 0.1, H * 0.125), r: W * 0.085 };
  // A phone held upright (≥ 1.75 : 1, e.g. 390 × 844, 375 × 667): the mobile formulas as they are.
  if (bp === 'phone' && H / W >= 1.75) {
    return { W, H, bp, vw: W, vh: H, ox: 0, oy: 0, boost: 1, labels: H >= 560, dash: phoneDash, dashTop: H * 0.22 };
  }
  // Anything squarer or wider (tablets, desktops, a short phone-width window)
  // fits the phone composition into the space instead.
  // Constellation band in the virtual frame, as multiples of vw:
  //   top    = Finance's top      = 0.23·A − 0.056 (minus 4 px)
  //   bottom = lower labels' foot = 0.61·A + 0.056 (plus ~18 px of label)
  const A = PHONE_ASPECT;
  // Wide screens: the header sits beside Finance, so the band starts near the top.
  // Narrower ones: the greeting reaches the centre, so start below the header.
  const topPad = W < 720 ? HEADER_H : H < 600 ? 12 : 28;
  // Bottom column (home.css): bar 52 px at max(14, 7 % − 26) from the bottom,
  // the status block (~105 px) 10 px above it, and a 14 px gap.
  const statusTop = H - bottomBarOffset(H) - 52 - 10 - 105 - 14;
  const avail = Math.max(120, statusTop - topPad);
  // The band is 0.38·A·vw between the Finance and lower-satellite centres,
  // plus a satellite radius at each end and ~22 px of label. The radius is
  // clamped on wide screens (satRadiusFor), so solve for vw by iterating.
  const boost = bp === 'phone' ? 1 : bp === 'tablet' ? 1.05 : 1.1;
  let vw = (avail - 22) / ((0.61 - 0.23) * A + 0.112);
  for (let k = 0; k < 3; k++) vw = (avail - 30 - 2 * satRadiusFor(bp, H, vw)) / ((0.61 - 0.23) * A);
  // Never wider than the viewport, and the gem never wider than ~560 px (§7.1).
  vw = Math.max(60, Math.min(vw, W - 32, 560 / (0.43 * boost)));
  const vh = vw * A;
  const ox = (W - vw) / 2;
  // Finance's top at topPad, using the radius it will really be drawn at.
  const sr = satRadiusFor(bp, H, vw);
  const oy = topPad + 4 + sr - 0.23 * vh;
  const dashY = H < 600 ? 40 : 66;
  const dashR = H < 600 ? 22 : 32;
  return {
    W, H, bp, vw, vh, ox, oy, boost,
    labels: vw * 0.056 >= 17,
    // Phone widths keep the mobile Dashboard sheet (full width from 22 % of the height).
    dash: bp === 'phone' ? phoneDash : { x: W * 0.5, y: dashY, r: dashR },
    dashTop: bp === 'phone' ? H * 0.22 : dashY + dashR * 2.2,
  };
}

/** Distance of the Ask bar from the bottom edge on wider screens (§8.1.5: about 93 % of the height). */
export function bottomBarOffset(H: number) {
  return Math.max(14, H * 0.07 - 26);
}

/** Loop phase in [0, 2π) for a clock in seconds. */
export function loopPhase(clock: number) {
  return ((clock % AMBIENT_LOOP) / AMBIENT_LOOP) * Math.PI * 2;
}

export function gemHome(s: Stage) {
  return { x: s.ox + s.vw * 0.5, y: s.oy + s.vh * 0.43, r: s.vw * 0.215 * s.boost };
}

/** Gem centre and radius for a dashboard progress t ∈ [0, 1]. */
export function gemAt(s: Stage, t: number) {
  const a = gemHome(s);
  const b = s.dash;
  // Ease the radius faster than the position so the gem "lifts off".
  const tr = Math.min(1, t * 1.25);
  return { x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t, r: a.r + (b.r - a.r) * tr };
}

/** Satellite radius: 5.6 % of the frame width; 64–110 px across on wider screens (§7.3). */
function satRadiusFor(bp: Breakpoint, H: number, vw: number) {
  const r = vw * 0.056;
  return bp === 'phone' ? r : Math.min(55, Math.max(H < 600 ? 12 : 32, r));
}

export function satelliteRadius(s: Stage) {
  return satRadiusFor(s.bp, s.H, s.vw);
}

/** Satellite centre with its small Lissajous drift (±5 px, own phase each). */
export function satellitePos(s: Stage, i: number, ph: number) {
  const a = ANCHORS[i];
  return {
    x: s.ox + a[0] * s.vw + 5 * Math.sin((3 + i) * ph + i * 1.7),
    y: s.oy + a[1] * s.vh + 4 * Math.sin((4 + ((i * 2) % 5)) * ph + i * 0.9),
  };
}
