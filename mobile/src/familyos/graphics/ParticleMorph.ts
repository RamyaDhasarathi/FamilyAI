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
//
// Cost: particles are split into three buckets (i mod 3), each recorded as its
// own picture. In flight all three are re-recorded every frame; once settled,
// one bucket per frame (shimmer and twinkle then update at 20 Hz per bucket).
// The per-particle trig is precomputed (sin/cos of each particle's phase), so
// a frame only does multiply-adds.
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
  sinP: number[];
  cosP: number[];
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
  return { n, shapes, delay, sway, phase, sinP: phase.map(Math.sin), cosP: phase.map(Math.cos) };
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

/** Particle colour for the current progress, lifted towards white so dots glow (0..255). */
function morphColour(s: MorphState) {
  'worklet';
  const t = s.t;
  const r = s.colFrom[0] + (s.colTo[0] - s.colFrom[0]) * t;
  const g = s.colFrom[1] + (s.colTo[1] - s.colFrom[1]) * t;
  const b = s.colFrom[2] + (s.colTo[2] - s.colFrom[2]) * t;
  return [Math.min(1, r * 0.85 + 0.2), Math.min(1, g * 0.85 + 0.2), Math.min(1, b * 0.85 + 0.2)];
}

/** Faint circular outline behind an icon, as in the video. */
export function drawMorphRing(canvas: SkCanvas, s: MorphState) {
  'worklet';
  if (s.alpha <= 0.01 || (s.to === 0 && s.from === 0)) return;
  const [r, g, b] = morphColour(s);
  const ringA = s.alpha * (s.to === 0 ? 1 - s.t : s.from === 0 ? s.t : 1) * 0.14;
  const paint = Skia.Paint();
  paint.setStyle(PaintStyle.Stroke);
  paint.setAntiAlias(true);
  paint.setStrokeWidth(1);
  paint.setColor(Skia.Color([r, g, b, ringA]));
  canvas.drawCircle(s.cx, s.cy, s.R * 1.62, paint);
}

/** True while particles are still travelling (every bucket must be redrawn each frame). */
export function morphInFlight(s: MorphState) {
  'worklet';
  return s.t < 1;
}

/** Draw bucket k (particles i ≡ k mod 3) at the current progress. */
export function drawMorphBucket(canvas: SkCanvas, d: MorphData, s: MorphState, k: number) {
  'worklet';
  if (s.alpha <= 0.01 || d.n === 0) return;
  const n = s.lowPower ? Math.min(MORPH_PARTICLES_LOW, d.n) : d.n;
  const A = d.shapes[s.from];
  const B = d.shapes[s.to];
  const sa = s.from === 0 ? GEM_SCALE : ICON_SCALE;
  const sb = s.to === 0 ? GEM_SCALE : ICON_SCALE;
  const R = s.R;
  // Shimmer = 0.006·sin(12ph + φᵢ) and 0.006·cos(10ph + φᵢ), expanded with
  // the angle-sum identities so only the global angles need trig.
  const s12 = 0.006 * Math.sin(12 * s.ph);
  const c12 = 0.006 * Math.cos(12 * s.ph);
  const s10 = 0.006 * Math.sin(10 * s.ph);
  const c10 = 0.006 * Math.cos(10 * s.ph);
  const pts: { x: number; y: number }[] = [];
  const settled = s.t >= 1;
  for (let i = k; i < n; i += 3) {
    let x: number;
    let y: number;
    const bx = B[i * 2] * sb;
    const by = B[i * 2 + 1] * sb;
    if (settled) {
      x = bx;
      y = by;
    } else {
      const local = Math.min(1, Math.max(0, (s.t - d.delay[i]) / 0.65));
      const e = easeInOutCubic(local);
      const ax = A[i * 2] * sa;
      const ay = A[i * 2 + 1] * sa;
      const dx = bx - ax;
      const dy = by - ay;
      x = ax + dx * e;
      y = ay + dy * e;
      const len2 = dx * dx + dy * dy;
      if (len2 > 1e-8) {
        // Sideways swing, 0 at both ends: 4l(1−l) is a cheap stand-in for sin(πl).
        const curl = (4 * local * (1 - local) * 0.3 * d.sway[i]) / Math.sqrt(len2);
        x -= dy * curl;
        y += dx * curl;
      }
    }
    const sp = d.sinP[i];
    const cp = d.cosP[i];
    pts.push({ x: s.cx + (x + s12 * cp + c12 * sp) * R, y: s.cy + (y + c10 * cp - s10 * sp) * R });
  }
  if (pts.length === 0) return;
  const [r, g, b] = morphColour(s);
  const tw = 0.7 + 0.3 * Math.sin(9 * s.ph + k * 2.1);
  const paint = Skia.Paint();
  paint.setStyle(PaintStyle.Stroke);
  paint.setStrokeCap(StrokeCap.Round);
  paint.setAntiAlias(true);
  paint.setStrokeWidth(2.4);
  paint.setColor(Skia.Color([r, g, b, Math.min(1, tw * s.alpha)]));
  canvas.drawPoints(PointMode.Points, pts, paint);
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
