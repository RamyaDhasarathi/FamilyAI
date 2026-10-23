// Particle morph: gem → agent icon → next icon → gem (AGENT.md §7.4).
//
// Every particle i owns one target point in every shape (the gem's
// silhouette and each icon), so a morph is a straight interpolation between
// two point clouds. To make it feel organic rather than mechanical:
//   • stagger: particle i starts after delay[i] ∈ [0, 0.35] of the morph and
//     finishes in the remaining 0.65, so the cloud peels off progressively;
//   • easing: ease-in-out cubic on each particle's own local progress;
//   • curl: mid-flight, each particle swings sideways (perpendicular to its
//     path) by sin(π·local), which is 0 at both ends, so targets stay exact;
//   • shimmer: at rest, a tiny whole-number-frequency wobble keeps it alive.
import { PaintStyle, PointMode, Skia, StrokeCap, type SkCanvas } from '@shopify/react-native-skia';
import { AGENT_IDS } from '../theme/tokens';
import { sampleGem, sampleIcon } from './iconPoints';
import { seededRandom } from './crystalGeometry';

export const MORPH_PARTICLES = 1200;
export const MORPH_PARTICLES_LOW = 420;
/** Icon half-size in gem radii (the finance ring sits just outside the gem). */
const ICON_SCALE = 1.2;
const GEM_SCALE = 0.95;

export interface MorphData {
  n: number;
  /** shapes[0] = gem silhouette; shapes[1 + k] = icon of AGENT_IDS[k]. Flat xy. */
  shapes: number[][];
  delay: number[];
  sway: number[];
  phase: number[];
}

/** Built once on the JS thread at start-up (Skia path sampling). */
export function buildMorphData(n = MORPH_PARTICLES): MorphData {
  const rand = seededRandom(99);
  const shapes = [sampleGem(n), ...AGENT_IDS.map((id) => sampleIcon(id, n))];
  const delay: number[] = [];
  const sway: number[] = [];
  const phase: number[] = [];
  for (let i = 0; i < n; i++) {
    delay.push(rand() * 0.35);
    sway.push((rand() - 0.5) * 2);
    phase.push(rand() * Math.PI * 2);
  }
  return { n, shapes, delay, sway, phase };
}

export interface MorphState {
  /** Shape indices: 0 = gem, 1..5 = icons (AGENT_IDS order). */
  from: number;
  to: number;
  t: number;
  alpha: number;
  /** RGB 0..1 of the source and target colour. */
  colFrom: number[];
  colTo: number[];
  cx: number;
  cy: number;
  R: number;
  ph: number;
  lowPower: boolean;
}

function easeInOutCubic(x: number) {
  'worklet';
  return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2;
}

export function drawMorph(canvas: SkCanvas, d: MorphData, s: MorphState) {
  'worklet';
  if (s.alpha <= 0.01 || d.n === 0) return;
  const n = s.lowPower ? Math.min(MORPH_PARTICLES_LOW, d.n) : d.n;
  const A = d.shapes[s.from];
  const B = d.shapes[s.to];
  const sa = s.from === 0 ? GEM_SCALE : ICON_SCALE;
  const sb = s.to === 0 ? GEM_SCALE : ICON_SCALE;
  const b0: { x: number; y: number }[] = [];
  const b1: { x: number; y: number }[] = [];
  const b2: { x: number; y: number }[] = [];
  const R = s.R;
  for (let i = 0; i < n; i++) {
    const local = Math.min(1, Math.max(0, (s.t - d.delay[i]) / 0.65));
    const e = easeInOutCubic(local);
    const ax = A[i * 2] * sa;
    const ay = A[i * 2 + 1] * sa;
    const bx = B[i * 2] * sb;
    const by = B[i * 2 + 1] * sb;
    let x = ax + (bx - ax) * e;
    let y = ay + (by - ay) * e;
    const dx = bx - ax;
    const dy = by - ay;
    const len = Math.hypot(dx, dy);
    if (len > 0.0001) {
      const curl = Math.sin(Math.PI * local) * 0.3 * d.sway[i];
      x += (-dy / len) * curl;
      y += (dx / len) * curl;
    }
    // Rest shimmer (~0.6 px), integer multiples of the loop phase.
    const sh = 0.006 * Math.sin(12 * s.ph + d.phase[i]);
    const px = s.cx + (x + sh) * R;
    const py = s.cy + (y + 0.006 * Math.cos(10 * s.ph + d.phase[i])) * R;
    const k = i % 3;
    (k === 0 ? b0 : k === 1 ? b1 : b2).push({ x: px, y: py });
  }
  const t = s.t;
  const r = s.colFrom[0] + (s.colTo[0] - s.colFrom[0]) * t;
  const g = s.colFrom[1] + (s.colTo[1] - s.colFrom[1]) * t;
  const b = s.colFrom[2] + (s.colTo[2] - s.colFrom[2]) * t;
  // Lift towards white so the dots glow.
  const lr = Math.round(Math.min(1, r * 0.85 + 0.2) * 255);
  const lg = Math.round(Math.min(1, g * 0.85 + 0.2) * 255);
  const lb = Math.round(Math.min(1, b * 0.85 + 0.2) * 255);
  const paint = Skia.Paint();
  paint.setStyle(PaintStyle.Stroke);
  paint.setStrokeCap(StrokeCap.Round);
  paint.setAntiAlias(true);

  // Faint circular outline behind an icon, as in the video.
  if (s.to !== 0 || s.from !== 0) {
    const ringA = s.alpha * (s.to === 0 ? 1 - t : s.from === 0 ? t : 1) * 0.14;
    paint.setStrokeWidth(1);
    paint.setColor(Skia.Color(`rgba(${lr},${lg},${lb},${ringA})`));
    canvas.drawCircle(s.cx, s.cy, R * 1.62, paint);
  }

  const buckets = [b0, b1, b2];
  if (!s.lowPower) {
    // Soft glow pass on one bucket.
    paint.setStrokeWidth(5.5);
    paint.setColor(Skia.Color(`rgba(${lr},${lg},${lb},${0.13 * s.alpha})`));
    canvas.drawPoints(PointMode.Points, b0, paint);
  }
  paint.setStrokeWidth(2.3);
  for (let k = 0; k < 3; k++) {
    const tw = 0.7 + 0.3 * Math.sin(9 * s.ph + k * 2.1);
    paint.setColor(Skia.Color(`rgba(${lr},${lg},${lb},${Math.min(1, tw * s.alpha)})`));
    canvas.drawPoints(PointMode.Points, buckets[k], paint);
  }
}

/**
 * Celebration burst when the needs-you list empties (AGENT.md §8.4): particles
 * leave the gem's rim radially and fade. `b` runs 1 → 0, so travel = 1 − b
 * with an ease-out, and alpha = b.
 */
export function drawBurst(canvas: SkCanvas, d: MorphData, b: number, cx: number, cy: number, R: number) {
  'worklet';
  if (b <= 0.01 || d.n === 0) return;
  const k = 1 - b;
  const travel = 1 - (1 - k) * (1 - k);
  const pts: { x: number; y: number }[] = [];
  const n = Math.min(320, d.n);
  for (let i = 0; i < n; i++) {
    const a = d.phase[i];
    const speed = 0.6 + 0.8 * d.delay[i] / 0.35;
    const r = R * (0.85 + 1.5 * travel * speed);
    pts.push({ x: cx + Math.cos(a) * r, y: cy + Math.sin(a) * r });
  }
  const paint = Skia.Paint();
  paint.setStyle(PaintStyle.Stroke);
  paint.setStrokeCap(StrokeCap.Round);
  paint.setAntiAlias(true);
  paint.setStrokeWidth(2.4);
  paint.setColor(Skia.Color(`rgba(170,255,210,${Math.min(1, b * 1.2)})`));
  canvas.drawPoints(PointMode.Points, pts, paint);
}
