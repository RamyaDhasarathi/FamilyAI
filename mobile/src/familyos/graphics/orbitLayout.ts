// Where things sit on the Home canvas (AGENT.md §7.1, §7.3), shared by the
// Skia scene and the React overlays (labels, badges, hit areas) so they never
// drift apart. All functions are worklets.
import type { AgentId } from '../theme/tokens';
import { AGENT_IDS } from '../theme/tokens';
import { AMBIENT_LOOP } from './ambientShader';

/** Satellite anchors as fractions of screen width / height (from the video). */
export const SATELLITE_ANCHORS: Record<AgentId, [number, number]> = {
  finance: [0.5, 0.23],
  education: [0.87, 0.38],
  grocery: [0.73, 0.61],
  household: [0.3, 0.61],
  calendar: [0.12, 0.38],
};
const ANCHORS = AGENT_IDS.map((id) => SATELLITE_ANCHORS[id]);

export interface Frame {
  W: number;
  H: number;
  top: number;
}

/** Loop phase in [0, 2π) for a clock in seconds. */
export function loopPhase(clock: number) {
  'worklet';
  return ((clock % AMBIENT_LOOP) / AMBIENT_LOOP) * Math.PI * 2;
}

export function gemHome(f: Frame) {
  'worklet';
  return { x: f.W * 0.5, y: f.H * 0.43, r: f.W * 0.215 };
}

/** Mini gem above the Dashboard sheet. */
export function gemDash(f: Frame) {
  'worklet';
  return { x: f.W * 0.5, y: Math.max(f.top + f.W * 0.1, f.H * 0.125), r: f.W * 0.085 };
}

/** Gem centre and radius for a dashboard progress t ∈ [0, 1]. */
export function gemAt(f: Frame, t: number) {
  'worklet';
  const a = gemHome(f);
  const b = gemDash(f);
  // Ease the radius faster than the position so the gem "lifts off".
  const tr = Math.min(1, t * 1.25);
  return { x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t, r: a.r + (b.r - a.r) * tr };
}

export function satelliteRadius(f: Frame) {
  'worklet';
  return f.W * 0.056;
}

/** Satellite centre with its small Lissajous drift (±5 px, own phase each). */
export function satellitePos(f: Frame, i: number, ph: number) {
  'worklet';
  const a = ANCHORS[i];
  return {
    x: a[0] * f.W + 5 * Math.sin((3 + i) * ph + i * 1.7),
    y: a[1] * f.H + 4 * Math.sin((4 + ((i * 2) % 5)) * ph + i * 0.9),
  };
}
