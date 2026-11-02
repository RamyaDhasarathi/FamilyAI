// Per-frame crystal shading, ported line for line from the mobile app's
// graphics/crystalRenderV2.ts (the v2 "refreshed stones"). The maths is
// identical; only the output differs: instead of Skia vertex batches it
// fills typed arrays that engine/glScene.ts uploads to WebGL each frame
// (a few hundred vertices, well under a millisecond).
//
// Core gem
//   • light pools at the lower right and the colour sweeps across the gem
//     (palette stop 0 bottom-right → stop 2 on the left), fixed to the
//     screen like a light source, so facets change colour as they turn;
//   • facets facing the viewer near the top are clear, so the far wall and
//     its faint edges show through the glass;
//   • thin, crisp edges with a soft glow; an inner glow; a star glint on the
//     brightest facet and a few twinkling glints on the corners.
// Satellites ("uncut stones")
//   • rough, uneven shapes with a dark heart and a bright rim, glowing
//     agent-coloured edges, faint inner edges, glitter that twinkles.
//
// Facet edges are drawn inside each triangle by the fragment shader from
// barycentric coordinates (corners (0,0), (1,0), (0,1)): min(b) is a pixel's
// distance to the nearest edge as a fraction of the triangle, so no lines are
// stroked. Widths are given in px and converted with the average triangle
// height `triH`, exactly as on mobile.
import type { CrystalMesh } from '../graphics/crystalGeometry';

export interface CrystalParams {
  cx: number;
  cy: number;
  /** Model radius in px. */
  R: number;
  rotY: number;
  tiltX: number;
  /** Loop phase in radians (whole-number multiples only, so loops are seamless). */
  phase: number;
  /** Interpolated scenario palette (stateThemes.paletteOf); ignored for satellites. */
  palette: number[];
  /** Satellite colour (0..1 RGB); null = core shading. */
  agent: number[] | null;
  alpha: number;
  /** 0 = whole gem, 1 = fully shattered into shards (particle morph). */
  explode: number;
  /** Extra brightness for highlighted satellites. */
  glow: number;
  /** Horizontal / vertical squash (tap feedback). */
  sx: number;
  sy: number;
  lowPower: boolean;
  /** Orientation as a row-major 3×3 matrix, view = rot · model. Overrides rotY/tiltX. */
  rot?: number[];
  /** Jelly ripples, [modelX, modelY, modelZ, ageSeconds] each. */
  ripples?: number[];
  /** Squash [axisX, axisY, axisZ, s] in view space. */
  squash?: number[];
  /** Stretch [dirX, dirY, m] in screen space (y down). */
  stretch?: number[];
  /** 0..1 extra edge brightness after a tap. */
  flash?: number;
}

// Jelly ripple (§3.3): d = −A·e^(−θ²/σ²)·e^(−λt)·cos(ωt) + B·e^(−λt)·sin(ωt − kθ),
// θ = angle between a corner's direction and the touch direction. The first
// term is the dent under the finger, the second a ripple running outwards.
const RIP_A = 0.14;
const RIP_B = 0.035;
const RIP_SIGMA2 = 0.7 * 0.7;
const RIP_LAMBDA = 4.5;
const RIP_OMEGA = 22;
const RIP_K = 3;
/** A ripple is invisible after this many seconds (e^(−4.5·1.4) ≈ 0.2 %). */
export const RIPPLE_LIFE = 1.4;

const TAU = Math.PI * 2;
// Lights in view space (y up, +z towards the viewer).
const LK = [-0.55 / 1.0464, 0.7 / 1.0464, 0.55 / 1.0464];
const LF = [0.65 / 0.9518, -0.35 / 0.9518, 0.6 / 0.9518];
const HK = (() => {
  const l = Math.hypot(LK[0], LK[1], LK[2] + 1);
  return [LK[0] / l, LK[1] / l, (LK[2] + 1) / l];
})();
/** Camera distance in model radii (perspective: s = CAM / (CAM − z)). */
const CAM = 4.2;

// ── Output buffers ────────────────────────────────────────────────────────

/** Coloured triangles (front faces and shards): xy, barycentric, rgba (straight alpha). */
export class TriBatch {
  pos: Float32Array;
  bary: Float32Array;
  col: Float32Array;
  n = 0;
  constructor(cap: number) {
    this.pos = new Float32Array(cap * 2);
    this.bary = new Float32Array(cap * 2);
    this.col = new Float32Array(cap * 4);
  }
}

/** Uncoloured triangles (the far wall): xy and barycentric only. */
export class WallBatch {
  pos: Float32Array;
  bary: Float32Array;
  n = 0;
  constructor(cap: number) {
    this.pos = new Float32Array(cap * 2);
    this.bary = new Float32Array(cap * 2);
  }
}

/** Round points (glitter): xy, diameter px, rgba (straight alpha). */
export class PointBatch {
  pos: Float32Array;
  size: Float32Array;
  col: Float32Array;
  n = 0;
  constructor(cap: number) {
    this.pos = new Float32Array(cap * 2);
    this.size = new Float32Array(cap);
    this.col = new Float32Array(cap * 4);
  }
  push(x: number, y: number, d: number, r: number, g: number, b: number, a: number) {
    if (this.n >= this.size.length) return;
    const i = this.n++;
    this.pos[i * 2] = x;
    this.pos[i * 2 + 1] = y;
    this.size[i] = d;
    this.col[i * 4] = r;
    this.col[i * 4 + 1] = g;
    this.col[i * 4 + 2] = b;
    this.col[i * 4 + 3] = a;
  }
}

/** Everything one crystal draws in a frame. */
export interface CrystalOut {
  front: TriBatch;
  back: WallBatch;
  /** Edge shader for the front batch: [w, g, gk, r, g, b, a] (premultiplied colour). */
  frontU: number[];
  /** Far wall shader: [w, fill rgba (premultiplied), edge rgba (premultiplied)]. */
  backU: number[];
  /** Inner glow, additive radial gradient: [cx, cy, r, r, g, b, a] (premultiplied); r = 0 when off. */
  glow: number[];
  /** Star glint on the brightest facet: [x, y, L, strength]; strength = 0 when off. */
  star: number[];
}

export function crystalOut(m: CrystalMesh): CrystalOut {
  return {
    front: new TriBatch(m.nf * 3),
    back: new WallBatch(m.nf * 3),
    frontU: [0, 0, 0, 0, 0, 0, 0],
    backU: [0, 0, 0, 0, 0, 0, 0, 0, 0],
    glow: [0, 0, 0, 0, 0, 0, 0],
    star: [0, 0, 0, 0],
  };
}

// ── Shading helpers (identical to mobile) ─────────────────────────────────

/** Volume-preserving scale along unit axis a: ×(1 − s) along, ×(1 + s/2) across. */
function axisScale(x: number, y: number, z: number, ax: number, ay: number, az: number, s: number, out: number[]) {
  const d = x * ax + y * ay + z * az;
  const k = 1 + s / 2;
  const along = d * (1 - s);
  out[0] = (x - d * ax) * k + ax * along;
  out[1] = (y - d * ay) * k + ay * along;
  out[2] = (z - d * az) * k + az * along;
}

function clamp01(x: number) {
  return x < 0 ? 0 : x > 1 ? 1 : x;
}

/** Cyclic three-stop gradient through palette[0..8] at u. */
function paletteAt(pal: number[], u: number, out: number[]) {
  const s = (u - Math.floor(u)) * 3;
  const i = Math.floor(s);
  const t = s - i;
  const a = (i % 3) * 3;
  const b = ((i + 1) % 3) * 3;
  out[0] = pal[a] + (pal[b] - pal[a]) * t;
  out[1] = pal[a + 1] + (pal[b + 1] - pal[a + 1]) * t;
  out[2] = pal[a + 2] + (pal[b + 2] - pal[a + 2]) * t;
}

function flowField(qx: number, qy: number, qz: number, phase: number) {
  return Math.sin(5 * qx + phase) + Math.sin(4 * qy - 2 * phase) + Math.sin(4 * qz + 3 * qx + phase);
}

/**
 * Glass colour at a view-space position (x, y) with flow value vv: the
 * palette is swept across the screen (lower right → stop 0, left → stop 2),
 * mixed with familyos_3d.py's irid() rainbow, then re-saturated.
 */
function sweepColour(pal: number[], tintAmt: number, x: number, y: number, vv: number, rnd: number, phase: number, out: number[]) {
  const h = 0.12 * vv + 0.3 * y + 0.2 * rnd + phase / TAU;
  let ir = 0.5 + 0.5 * Math.cos(TAU * h);
  let ig = 0.5 + 0.5 * Math.cos(TAU * (h + 0.33));
  let ib = 0.5 + 0.5 * Math.cos(TAU * (h + 0.67));
  const il = (ir + ig + ib) / 3;
  ir = il + (ir - il) * 0.85;
  ig = il + (ig - il) * 0.85;
  ib = il + (ib - il) * 0.85;
  paletteAt(pal, 0.34 - 0.3 * x + 0.12 * y + 0.06 * vv + 0.06 * rnd, out);
  const k = Math.min(1, tintAmt + 0.15);
  const r = ir + (out[0] - ir) * k;
  const g = ig + (out[1] - ig) * k;
  const b = ib + (out[2] - ib) * k;
  const l = (r + g + b) / 3;
  out[0] = clamp01(l + (r - l) * 1.8);
  out[1] = clamp01(l + (g - l) * 1.8);
  out[2] = clamp01(l + (b - l) * 1.8);
}

/** How much the light pools at the lower right of the gem (0..1), view space y-up. */
function poolAt(x: number, y: number) {
  return clamp01(0.5 + 0.5 * (0.55 * x - 0.85 * y));
}

/** Smooth 0..1 twinkle, sharpened so glints flash briefly rather than glow. */
function twinkle(phase: number, k: number, seed: number) {
  const s = 0.5 + 0.5 * Math.sin(k * phase + seed * 12.9898);
  return s * s * s * s;
}

// Scratch arrays, grown on demand and reused every frame (no per-frame garbage).
let cap = 0;
let rx = new Float64Array(0);
let ry = rx, rz = rx, px = rx, py = rx, vb = rx, vfr = rx, vpo = rx;
let fcap = 0;
let depth = new Float64Array(0);
let fnx = depth, fny = depth, spec = depth, fb = depth, fl = depth, fw = depth, fa = depth, ff2 = depth, flm = depth;
let front = new Uint8Array(0);
let order: number[] = [];
function ensure(nv: number, nf: number) {
  if (nv > cap) {
    cap = nv;
    [rx, ry, rz, px, py, vfr, vpo] = Array.from({ length: 7 }, () => new Float64Array(nv));
    vb = new Float64Array(nv * 3);
  }
  if (nf > fcap) {
    fcap = nf;
    [depth, fnx, fny, spec, fl, fw, fa, ff2, flm] = Array.from({ length: 9 }, () => new Float64Array(nf));
    fb = new Float64Array(nf * 3);
    front = new Uint8Array(nf);
    order = new Array(nf);
  }
}

const tmp = [0, 0, 0];
const pc = [0, 0, 0];

/**
 * Shade one crystal into `out` (and its glitter into `glitter`). Returns false
 * when nothing is drawn.
 */
export function drawCrystal(out: CrystalOut, glitter: PointBatch, m: CrystalMesh, p: CrystalParams): boolean {
  out.front.n = 0;
  out.back.n = 0;
  out.glow[2] = 0;
  out.star[3] = 0;
  if (p.alpha <= 0.01) return false;
  const { v, f, fr, fc, nv, nf } = m;
  ensure(nv, nf);
  const cY = Math.cos(p.rotY);
  const sY = Math.sin(p.rotY);
  const cX = Math.cos(p.tiltX);
  const sX = Math.sin(p.tiltX);
  const ex = p.explode;
  const isSat = p.agent !== null;
  const intact = ex <= 0.001;

  // 1. Rotate + project.
  const M = p.rot;
  const rip = !p.lowPower && p.ripples && p.ripples.length > 0 ? p.ripples : null;
  const sq = p.squash && Math.abs(p.squash[3]) > 1e-4 ? p.squash : null;
  const st = p.stretch && p.stretch[2] > 1e-4 ? p.stretch : null;
  for (let i = 0; i < nv; i++) {
    let x = v[i * 3];
    let y = v[i * 3 + 1];
    let z = v[i * 3 + 2];
    if (rip) {
      // Jelly: move the corner along its (near-radial) normal.
      const len = Math.hypot(x, y, z) || 1;
      let disp = 0;
      for (let r = 0; r < rip.length; r += 4) {
        const t = rip[r + 3];
        if (t < 0 || t > RIPPLE_LIFE) continue;
        const c = (x * rip[r] + y * rip[r + 1] + z * rip[r + 2]) / len;
        const th = Math.acos(c < -1 ? -1 : c > 1 ? 1 : c);
        const e = Math.exp(-RIP_LAMBDA * t);
        disp += -RIP_A * Math.exp(-(th * th) / RIP_SIGMA2) * e * Math.cos(RIP_OMEGA * t) + RIP_B * e * Math.sin(RIP_OMEGA * t - RIP_K * th);
      }
      const k = 1 + disp;
      x *= k;
      y *= k;
      z *= k;
    }
    let x1: number;
    let y2: number;
    let z2: number;
    if (M) {
      x1 = M[0] * x + M[1] * y + M[2] * z;
      y2 = M[3] * x + M[4] * y + M[5] * z;
      z2 = M[6] * x + M[7] * y + M[8] * z;
    } else {
      x1 = x * cY + z * sY;
      const z1 = -x * sY + z * cY;
      y2 = y * cX - z1 * sX;
      z2 = y * sX + z1 * cX;
    }
    if (sq) {
      axisScale(x1, y2, z2, sq[0], sq[1], sq[2], sq[3], tmp);
      x1 = tmp[0];
      y2 = tmp[1];
      z2 = tmp[2];
    }
    if (st) {
      axisScale(x1, y2, z2, st[0], -st[1], 0, -st[2], tmp);
      x1 = tmp[0];
      y2 = tmp[1];
      z2 = tmp[2];
    }
    rx[i] = x1;
    ry[i] = y2;
    rz[i] = z2;
    const s = CAM / (CAM - z2);
    px[i] = p.cx + x1 * p.R * s * p.sx;
    py[i] = p.cy - y2 * p.R * s * p.sy;
  }

  // 2a. Core: colour, Fresnel and light pool per vertex (smooth gradients
  // across facets, continuous over shared corners).
  const pal = p.palette;
  const tintAmt = isSat ? 0 : pal[9];
  if (!isSat) {
    for (let i = 0; i < nv; i++) {
      const vv = flowField(v[i * 3], v[i * 3 + 1], v[i * 3 + 2], p.phase);
      sweepColour(pal, tintAmt, rx[i], ry[i], vv, 0.5, p.phase, pc);
      vb[i * 3] = pc[0];
      vb[i * 3 + 1] = pc[1];
      vb[i * 3 + 2] = pc[2];
      const len = Math.hypot(rx[i], ry[i], rz[i]) || 1;
      vfr[i] = Math.pow(1 - clamp01(rz[i] / len), 1.5);
      vpo[i] = poolAt(rx[i] / len, ry[i] / len);
    }
  }

  // 2b. Faces.
  const fade = ex > 0 ? Math.pow(1 - ex, 1.4) : 1;
  for (let fi = 0; fi < nf; fi++) {
    const a = f[fi * 3];
    const b = f[fi * 3 + 1];
    const c = f[fi * 3 + 2];
    const ux = rx[b] - rx[a];
    const uy = ry[b] - ry[a];
    const uz = rz[b] - rz[a];
    const wx = rx[c] - rx[a];
    const wy = ry[c] - ry[a];
    const wz = rz[c] - rz[a];
    let nx = uy * wz - uz * wy;
    let ny = uz * wx - ux * wz;
    let nz = ux * wy - uy * wx;
    const nl = Math.hypot(nx, ny, nz) || 1;
    nx /= nl;
    ny /= nl;
    nz /= nl;
    const mx = (rx[a] + rx[b] + rx[c]) / 3;
    const my = (ry[a] + ry[b] + ry[c]) / 3;
    const mz = (rz[a] + rz[b] + rz[c]) / 3;
    let vx = -mx;
    let vy = -my;
    let vz = CAM - mz;
    const vl = Math.hypot(vx, vy, vz);
    vx /= vl;
    vy /= vl;
    vz /= vl;
    const ndv = nx * vx + ny * vy + nz * vz;
    const isFront = ndv > 0;
    front[fi] = isFront ? 1 : 0;
    depth[fi] = mz;
    fnx[fi] = nx;
    fny[fi] = ny;
    order[fi] = fi;
    const nvw = clamp01(ndv);
    const lam = clamp01(nx * LK[0] + ny * LK[1] + nz * LK[2]);
    const fil = clamp01(nx * LF[0] + ny * LF[1] + nz * LF[2]);
    const sp = Math.pow(clamp01(nx * HK[0] + ny * HK[1] + nz * HK[2]), isSat ? 20 : 60);
    spec[fi] = isFront ? sp : 0;
    flm[fi] = lam;
    if (isSat) {
      // Uncut stone: dark heart, bright rim, a little key light on top.
      const ag = p.agent!;
      const fres = Math.pow(1 - nvw, 1.6);
      fb[fi * 3] = ag[0];
      fb[fi * 3 + 1] = ag[1];
      fb[fi * 3 + 2] = ag[2];
      fl[fi] = 0.12 + 0.95 * fres + 0.35 * lam + 0.15 * fil + 0.35 * p.glow;
      fw[fi] = sp * 0.75 + 0.08 * fres;
      fa[fi] = isFront ? 0.5 + 0.35 * fres : 0;
      ff2[fi] = 0;
    } else {
      const vv = flowField(fc[fi * 3], fc[fi * 3 + 1], fc[fi * 3 + 2], p.phase);
      sweepColour(pal, tintAmt, mx, my, vv, fr[fi], p.phase, pc);
      fb[fi * 3] = pc[0];
      fb[fi * 3 + 1] = pc[1];
      fb[fi * 3 + 2] = pc[2];
      const flow = 0.5 + 0.5 * Math.sin(2 * vv + p.phase);
      const f2 = flow * flow;
      ff2[fi] = f2;
      const fres = Math.pow(1 - nvw, 1.5);
      const ml = Math.hypot(mx, my, mz) || 1;
      const pool = poolAt(mx / ml, my / ml);
      // A soft light runs with the ripple front across the facets.
      let frontGlow = 0;
      if (rip) {
        for (let r = 0; r < rip.length; r += 4) {
          const t = rip[r + 3];
          if (t < 0 || t > RIPPLE_LIFE) continue;
          const cl = Math.hypot(fc[fi * 3], fc[fi * 3 + 1], fc[fi * 3 + 2]) || 1;
          const cc = (fc[fi * 3] * rip[r] + fc[fi * 3 + 1] * rip[r + 1] + fc[fi * 3 + 2] * rip[r + 2]) / cl;
          const th = Math.acos(cc < -1 ? -1 : cc > 1 ? 1 : cc);
          const crest = (RIP_OMEGA * t - Math.PI / 2) / RIP_K;
          const dd = (th - crest) / 0.28;
          frontGlow += 0.45 * Math.exp(-RIP_LAMBDA * t) * Math.exp(-dd * dd);
        }
      }
      if (isFront) {
        fl[fi] = 0.08 + 1.0 * fres + (0.2 + 1.75 * pool) * (0.4 + 0.6 * f2) * (0.5 + 0.5 * lam) + 0.1 * fil;
        fw[fi] = sp * 0.9 + 0.05 * fres * (0.4 + lam) + frontGlow;
        // Clear where the glass faces you near the top; denser where light pools.
        fa[fi] = clamp01(0.13 + 0.5 * fres + 0.8 * pool * (0.45 + 0.55 * f2));
      } else {
        fl[fi] = 0.2 + 0.25 * flow;
        fw[fi] = 0.015;
        fa[fi] = 0.34;
      }
    }
    fa[fi] *= p.alpha * fade;
  }

  const ord = order.length === nf ? order : order.slice(0, nf);
  if (!intact) ord.sort((i, j) => depth[i] - depth[j]);
  else ord.sort((i, j) => (front[i] === front[j] ? 0 : front[i] ? 1 : -1));

  // Average triangle height in px, to turn widths in px into barycentric units.
  const triH = p.R * Math.sqrt((4 * Math.PI) / nf) * 0.95;
  const edgeFade = ex > 0 ? Math.max(0, 1 - ex * 2.5) : 1;
  const A = p.alpha * edgeFade;
  const ag = p.agent;

  // 4. The far wall (intact only), seen through the clear front facets; and
  // the coloured front faces (or every shard while shattered).
  const back = out.back;
  const fr0 = out.front;
  for (let k = 0; k < nf; k++) {
    const fi = ord[k];
    const a = f[fi * 3];
    const b = f[fi * 3 + 1];
    const c = f[fi * 3 + 2];
    if (intact && !front[fi]) {
      let j = back.n * 2;
      back.pos[j] = px[a]; back.pos[j + 1] = py[a]; back.bary[j] = 0; back.bary[j + 1] = 0; j += 2;
      back.pos[j] = px[b]; back.pos[j + 1] = py[b]; back.bary[j] = 1; back.bary[j + 1] = 0; j += 2;
      back.pos[j] = px[c]; back.pos[j + 1] = py[c]; back.bary[j] = 0; back.bary[j + 1] = 1;
      back.n += 3;
      continue;
    }
    const a0 = fa[fi];
    if (a0 <= 0.003) continue;
    let ax = px[a];
    let ay = py[a];
    let bx = px[b];
    let by = py[b];
    let cx = px[c];
    let cy = py[c];
    if (ex > 0) {
      // Shatter (particle morph): shards fly out along their normals and shrink.
      const off = ex * p.R * (0.5 + 1.3 * fr[fi]);
      const ox = fnx[fi] * off;
      const oy = -fny[fi] * off;
      const gx = (ax + bx + cx) / 3;
      const gy = (ay + by + cy) / 3;
      const sh = 1 - 0.55 * ex;
      ax = gx + (ax - gx) * sh + ox;
      ay = gy + (ay - gy) * sh + oy;
      bx = gx + (bx - gx) * sh + ox;
      by = gy + (by - gy) * sh + oy;
      cx = gx + (cx - gx) * sh + ox;
      cy = gy + (cy - gy) * sh + oy;
    }
    const lf = fl[fi];
    const wf = fw[fi];
    for (let q = 0; q < 3; q++) {
      const vi = q === 0 ? a : q === 1 ? b : c;
      let r0 = fb[fi * 3];
      let g0 = fb[fi * 3 + 1];
      let b0 = fb[fi * 3 + 2];
      let li = lf;
      if (!isSat) {
        r0 = 0.5 * r0 + 0.5 * vb[vi * 3];
        g0 = 0.5 * g0 + 0.5 * vb[vi * 3 + 1];
        b0 = 0.5 * b0 + 0.5 * vb[vi * 3 + 2];
        if (front[fi]) {
          const lv = 0.08 + 1.0 * vfr[vi] + (0.2 + 1.75 * vpo[vi]) * (0.4 + 0.6 * ff2[fi]) * (0.5 + 0.5 * flm[fi]);
          li = 0.5 * lf + 0.5 * lv;
        }
      }
      const n = fr0.n;
      fr0.pos[n * 2] = q === 0 ? ax : q === 1 ? bx : cx;
      fr0.pos[n * 2 + 1] = q === 0 ? ay : q === 1 ? by : cy;
      fr0.bary[n * 2] = q === 1 ? 1 : 0;
      fr0.bary[n * 2 + 1] = q === 2 ? 1 : 0;
      fr0.col[n * 4] = clamp01(r0 * li + wf);
      fr0.col[n * 4 + 1] = clamp01(g0 * li + wf);
      fr0.col[n * 4 + 2] = clamp01(b0 * li + wf * 1.05);
      fr0.col[n * 4 + 3] = a0;
      fr0.n = n + 1;
    }
  }

  // Far-wall shader values.
  const bu = out.backU;
  if (isSat) {
    // Inner edges only: the crumpled facets seen through the stone.
    bu[0] = Math.min(0.45, 0.8 / triH);
    bu[1] = bu[2] = bu[3] = bu[4] = 0;
    bu[5] = ag![0] * 0.4 * A;
    bu[6] = ag![1] * 0.4 * A;
    bu[7] = ag![2] * 0.4 * A;
    bu[8] = 0.4 * A;
  } else {
    const fa0 = 0.55 * p.alpha;
    const ea0 = 0.11 * A;
    bu[0] = Math.min(0.45, 0.4 / triH);
    bu[1] = ((pal[0] + pal[3]) * 0.09 + 0.015) * fa0;
    bu[2] = ((pal[1] + pal[4]) * 0.09 + 0.02) * fa0;
    bu[3] = ((pal[2] + pal[5]) * 0.1 + 0.035) * fa0;
    bu[4] = fa0;
    bu[5] = 0.8 * ea0;
    bu[6] = 0.9 * ea0;
    bu[7] = ea0;
    bu[8] = ea0;
  }

  // 5. Core: inner light, pooled low and to the right, inside the glass.
  if (!isSat && intact) {
    const ia = 0.4 * p.alpha;
    const g = out.glow;
    g[0] = p.cx + p.R * 0.2;
    g[1] = p.cy + p.R * 0.28;
    g[2] = p.R * 0.95;
    g[3] = pal[0] * ia;
    g[4] = pal[1] * ia;
    g[5] = pal[2] * ia;
    g[6] = ia;
  }

  // 6. Edge shader values for the front batch.
  {
    let er = 1;
    let eg = 1;
    let eb = 1;
    let ea = 0.42 * A * (1 + 0.5 * (p.flash ?? 0));
    let wpx = 0.32;
    let gpx = 2.2;
    let gk = 0.1;
    if (isSat) {
      er = Math.min(1, ag![0] * 0.5 + 0.55);
      eg = Math.min(1, ag![1] * 0.5 + 0.55);
      eb = Math.min(1, ag![2] * 0.5 + 0.55);
      ea = (0.8 + 0.2 * p.glow) * A;
      wpx = 0.45;
      gpx = 2.6;
      gk = 0.3;
    }
    const u = out.frontU;
    u[0] = Math.min(0.45, wpx / triH);
    u[1] = Math.min(0.5, gpx / triH);
    u[2] = gk;
    u[3] = er * ea;
    u[4] = eg * ea;
    u[5] = eb * ea;
    u[6] = ea;
  }
  if (edgeFade <= 0.01 || !intact) return true;

  // 7. Glitter on corners that face the viewer: satellites carry a faint
  // always-on sparkle on every front corner plus brief bright flashes; the
  // core only flashes, so its glass stays clean.
  if (!(p.lowPower && !isSat)) {
    const step = isSat ? 1 : 3;
    const tr = isSat ? Math.min(1, ag![0] * 0.3 + 0.75) : 1;
    const tg = isSat ? Math.min(1, ag![1] * 0.3 + 0.75) : 1;
    const tb = isSat ? Math.min(1, ag![2] * 0.3 + 0.75) : 1;
    for (let i = 0; i < nv; i += step) {
      if (rz[i] < 0.2) continue;
      const t = twinkle(p.phase, isSat ? 7 + (i % 5) : 5 + (i % 7), i);
      if (t > 0.3) glitter.push(px[i], py[i], isSat ? 2 : 2.2, tr, tg, tb, 0.95 * A);
      else if (isSat) glitter.push(px[i], py[i], 1.4, tr, tg, tb, 0.45 * A);
    }
  }

  // 8. Core: a four-point star on the facet that catches the key light most.
  if (!isSat) {
    let best = -1;
    for (let fi = 0; fi < nf; fi++) if (spec[fi] > 0.4 && (best < 0 || spec[fi] > spec[best])) best = fi;
    if (best >= 0) {
      const a = f[best * 3];
      const b = f[best * 3 + 1];
      const c = f[best * 3 + 2];
      const s = spec[best] * A;
      const st2 = out.star;
      st2[0] = (px[a] + px[b] + px[c]) / 3;
      st2[1] = (py[a] + py[b] + py[c]) / 3;
      st2[2] = p.R * 0.16 * (0.7 + 0.3 * s);
      st2[3] = s;
    }
  }
  return true;
}
