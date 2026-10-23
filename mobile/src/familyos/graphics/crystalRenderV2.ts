// v2 stone design (see stoneStyle.ts; v1 is crystalRender.ts, kept unchanged).
//
// Same pipeline and the same per-frame budget as v1 (one coloured triangle
// batch for the front, edges drawn by a shader inside the batch, no stroked
// paths), with a look closer to the video:
//
// Core gem
//   • light pools at the lower right and the colour sweeps across the gem
//     (palette stop 0 bottom-right → stop 2 on the left), fixed to the
//     screen like a light source, so facets change colour as they turn;
//   • facets facing the viewer near the top are clear, so the far wall and
//     its faint edges show through the glass;
//   • thinner, crisper edges with a soft glow; an inner glow; a star glint
//     on the brightest facet and a few twinkling glints on the corners.
// Satellites ("uncut stones")
//   • rough, uneven shapes (stoneGeometryV2.ts) with a dark heart and a
//     bright rim, glowing agent-coloured edges, faint inner edges, glitter
//     that twinkles, and a soft halo.
import {
  BlendMode,
  PaintStyle,
  PointMode,
  Skia,
  StrokeCap,
  TileMode,
  VertexMode,
  type SkCanvas,
  type SkColor,
  type SkPoint,
} from '@shopify/react-native-skia';
import type { CrystalMesh } from './crystalGeometry';
import type { CrystalParams } from './crystalRender';

/** v2 extras for the interactive core (AGENT_CORE_AND_FAMILY.md §3). v1 ignores them. */
export interface CrystalParamsV2 extends CrystalParams {
  /** Orientation as a row-major 3×3 matrix, view = rot · model. Overrides rotY/tiltX. */
  rot?: number[];
  /** Jelly ripples, [modelX, modelY, modelZ, ageSeconds] each (model-space unit touch direction). */
  ripples?: number[];
  /** Squash [axisX, axisY, axisZ, s] in view space: shrink along the axis by s, grow across it by s/2. */
  squash?: number[];
  /** Stretch [dirX, dirY, m] in screen space (y down): grow along the drag by m, shrink across by m/2. */
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

/** Volume-preserving scale along unit axis a: ×(1 − s) along, ×(1 + s/2) across. */
function axisScale(x: number, y: number, z: number, ax: number, ay: number, az: number, s: number, out: number[]) {
  'worklet';
  const d = x * ax + y * ay + z * az;
  const k = 1 + s / 2;
  const along = d * (1 - s);
  out[0] = (x - d * ax) * k + ax * along;
  out[1] = (y - d * ay) * k + ay * along;
  out[2] = (z - d * az) * k + az * along;
}

const TAU = Math.PI * 2;
// Lights in view space (y up, +z towards the viewer), as in the renderer.
const LK = [-0.55 / 1.0464, 0.7 / 1.0464, 0.55 / 1.0464];
const LF = [0.65 / 0.9518, -0.35 / 0.9518, 0.6 / 0.9518];
const HK = (() => {
  const l = Math.hypot(LK[0], LK[1], LK[2] + 1);
  return [LK[0] / l, LK[1] / l, (LK[2] + 1) / l];
})();
const CAM = 4.2;

/**
 * Front-face edges inside the triangle batch (barycentric texcoords, see v1):
 * a crisp line of half-width `w` plus a soft glow reaching `g`, both as a
 * fraction of the triangle, added onto the vertex colours (BlendMode.Plus).
 */
const edgeGlowEffect = Skia.RuntimeEffect.Make(`
uniform float w;
uniform float g;
uniform float gk;
uniform float4 col;
half4 main(float2 p) {
  float e = min(min(p.x, p.y), 1.0 - p.x - p.y);
  float line = 1.0 - smoothstep(w * 0.3, w, e);
  float glow = 1.0 - smoothstep(0.0, g, e);
  return half4(col * min(1.0, line + gk * glow * glow));
}`)!;

/** The far wall: a flat tint plus faint edges, for uncoloured vertices. */
const backWallEffect = Skia.RuntimeEffect.Make(`
uniform float w;
uniform float4 fill;
uniform float4 edge;
half4 main(float2 p) {
  float e = min(min(p.x, p.y), 1.0 - p.x - p.y);
  float line = 1.0 - smoothstep(w * 0.3, w, e);
  return half4(fill + edge * line);
}`)!;

/**
 * The three barycentric corners as native Skia points, created once per UI
 * runtime. Native points cross into C++ without property lookups; plain
 * {x, y} objects cost two string-keyed lookups each, which dominated the
 * frame (measured on a Snapdragon 778G).
 */
function bary(): SkPoint[] {
  'worklet';
  const g = globalThis as unknown as { __fosBary?: SkPoint[] };
  if (!g.__fosBary) g.__fosBary = [Skia.Point(0, 0), Skia.Point(1, 0), Skia.Point(0, 1)];
  return g.__fosBary;
}

function clamp01(x: number) {
  'worklet';
  return x < 0 ? 0 : x > 1 ? 1 : x;
}

function r1(x: number) {
  'worklet';
  return Math.round(x * 10) / 10;
}

/** Cyclic three-stop gradient through palette[0..8] at u. */
function paletteAt(pal: number[], u: number, out: number[]) {
  'worklet';
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
  'worklet';
  return Math.sin(5 * qx + phase) + Math.sin(4 * qy - 2 * phase) + Math.sin(4 * qz + 3 * qx + phase);
}

/**
 * Glass colour at a view-space position (x, y) with flow value vv: the
 * palette is swept across the screen (lower right → stop 0, left → stop 2),
 * mixed with the renderer's irid() rainbow, then re-saturated.
 */
function sweepColour(pal: number[], tintAmt: number, x: number, y: number, vv: number, rnd: number, phase: number, out: number[]) {
  'worklet';
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
  'worklet';
  return clamp01(0.5 + 0.5 * (0.55 * x - 0.85 * y));
}

/** Smooth 0..1 twinkle; sharpened so glints flash briefly rather than glow. */
function twinkle(phase: number, k: number, seed: number) {
  'worklet';
  const s = 0.5 + 0.5 * Math.sin(k * phase + seed * 12.9898);
  return s * s * s * s;
}

export function drawCrystalV2(canvas: SkCanvas, m: CrystalMesh, p: CrystalParamsV2) {
  'worklet';
  if (p.alpha <= 0.01) return;
  const { v, f, fr, fc, nv, nf } = m;
  const cY = Math.cos(p.rotY);
  const sY = Math.sin(p.rotY);
  const cX = Math.cos(p.tiltX);
  const sX = Math.sin(p.tiltX);
  const ex = p.explode;
  const isSat = p.agent !== null;
  const intact = ex <= 0.001;

  // 1. Rotate + project.
  const rx: number[] = new Array(nv);
  const ry: number[] = new Array(nv);
  const rz: number[] = new Array(nv);
  const px: number[] = new Array(nv);
  const py: number[] = new Array(nv);
  // One point object per corner, shared by every face that uses it (fewer
  // allocations on the UI thread than three new objects per face).
  // Plain objects: creating native points per frame costs more than it saves.
  const pt: { x: number; y: number }[] = new Array(nv);
  const BARY = bary();
  const M = p.rot;
  const rip = !p.lowPower && p.ripples && p.ripples.length > 0 ? p.ripples : null;
  const sq = p.squash && Math.abs(p.squash[3]) > 1e-4 ? p.squash : null;
  // Stretch axis in view space (screen y points down, view y up).
  const st = p.stretch && p.stretch[2] > 1e-4 ? p.stretch : null;
  const tmp = [0, 0, 0];
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
    pt[i] = { x: px[i], y: py[i] };
  }

  // 2a. Core: colour, Fresnel and light pool per vertex (smooth gradients
  // across facets, continuous over shared corners).
  const pal = p.palette;
  const tintAmt = isSat ? 0 : pal[9];
  const pc = [0, 0, 0];
  const vb: number[] = isSat ? [] : new Array(nv * 3);
  const vfr: number[] = isSat ? [] : new Array(nv);
  const vpo: number[] = isSat ? [] : new Array(nv);
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
  const front: boolean[] = new Array(nf);
  const order: number[] = [];
  const depth: number[] = new Array(nf);
  const fnx: number[] = new Array(nf);
  const fny: number[] = new Array(nf);
  const spec: number[] = new Array(nf);
  const fb: number[] = new Array(nf * 3);
  const fl: number[] = new Array(nf);
  const fw: number[] = new Array(nf);
  const fa: number[] = new Array(nf);
  const ff2: number[] = new Array(nf);
  const flm: number[] = new Array(nf);
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
    front[fi] = isFront;
    depth[fi] = mz;
    fnx[fi] = nx;
    fny[fi] = ny;
    order.push(fi);
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
          const c = (fc[fi * 3] * rip[r] + fc[fi * 3 + 1] * rip[r + 1] + fc[fi * 3 + 2] * rip[r + 2]) / cl;
          const th = Math.acos(c < -1 ? -1 : c > 1 ? 1 : c);
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

  if (!intact) order.sort((i, j) => depth[i] - depth[j]);
  else order.sort((i, j) => (front[i] === front[j] ? 0 : front[i] ? 1 : -1));

  // Average triangle height in px, to turn widths in px into barycentric units.
  const triH = p.R * Math.sqrt((4 * Math.PI) / nf) * 0.95;
  const edgeFade = ex > 0 ? Math.max(0, 1 - ex * 2.5) : 1;
  const A = p.alpha * edgeFade;
  const ag = p.agent;

  // 3. (Satellite halos come from the ambient shader's satellite glow.)

  // 4. The far wall (intact only), seen through the clear front facets.
  const backPos: { x: number; y: number }[] = [];
  const backTex: SkPoint[] = [];
  let backPath = '';
  const pos: { x: number; y: number }[] = [];
  const tex: SkPoint[] = [];
  const cols: number[][] = [];
  for (let k = 0; k < order.length; k++) {
    const fi = order[k];
    const a = f[fi * 3];
    const b = f[fi * 3 + 1];
    const c = f[fi * 3 + 2];
    if (intact && !front[fi]) {
      if (isSat || !p.lowPower) {
        backPos.push(pt[a], pt[b], pt[c]);
        backTex.push(BARY[0], BARY[1], BARY[2]);
      } else {
        backPath += `M${r1(px[a])} ${r1(py[a])}L${r1(px[b])} ${r1(py[b])}L${r1(px[c])} ${r1(py[c])}Z`;
      }
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
    if (ex > 0) pos.push({ x: ax, y: ay }, { x: bx, y: by }, { x: cx, y: cy });
    else pos.push(pt[a], pt[b], pt[c]);
    tex.push(BARY[0], BARY[1], BARY[2]);
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
      cols.push([clamp01(r0 * li + wf), clamp01(g0 * li + wf), clamp01(b0 * li + wf * 1.05), a0]);
    }
  }

  if (backPos.length > 0) {
    const wall = Skia.Paint();
    if (isSat) {
      // Inner edges only: the crumpled facets seen through the stone.
      wall.setShader(
        backWallEffect.makeShader([Math.min(0.45, 0.8 / triH), 0, 0, 0, 0, ag![0] * 0.4 * A, ag![1] * 0.4 * A, ag![2] * 0.4 * A, 0.4 * A])
      );
    } else {
      const fr0 = (pal[0] + pal[3]) * 0.09 + 0.015;
      const fg0 = (pal[1] + pal[4]) * 0.09 + 0.02;
      const fb0 = (pal[2] + pal[5]) * 0.1 + 0.035;
      const fa0 = 0.55 * p.alpha;
      const ea0 = 0.11 * A;
      wall.setShader(
        backWallEffect.makeShader([
          Math.min(0.45, 0.4 / triH),
          fr0 * fa0, fg0 * fa0, fb0 * fa0, fa0,
          0.8 * ea0, 0.9 * ea0, ea0, ea0,
        ])
      );
    }
    canvas.drawVertices(Skia.MakeVertices(VertexMode.Triangles, backPos, backTex), BlendMode.Dst, wall);
  } else if (backPath) {
    // Low-power: the far wall as one gradient path, as in v1.
    const bp = Skia.Path.MakeFromSVGString(backPath);
    if (bp) {
      const bgp = Skia.Paint();
      bgp.setAntiAlias(true);
      bgp.setShader(
        Skia.Shader.MakeRadialGradient(
          { x: p.cx - p.R * 0.25, y: p.cy - p.R * 0.3 },
          p.R * 1.25,
          [
            Skia.Color([pal[3] * 0.3 + 0.03, pal[4] * 0.3 + 0.03, pal[5] * 0.3 + 0.05, 0.55 * p.alpha]),
            Skia.Color([pal[6] * 0.22 + 0.02, pal[7] * 0.22 + 0.02, pal[8] * 0.26 + 0.04, 0.48 * p.alpha]),
          ],
          null,
          TileMode.Clamp
        )
      );
      canvas.drawPath(bp, bgp);
    }
  }

  // 5. Core: inner light, pooled low and to the right, inside the glass.
  if (!isSat && intact) {
    const glow = Skia.Paint();
    glow.setBlendMode(BlendMode.Plus);
    const ia = 0.4 * p.alpha;
    glow.setShader(
      Skia.Shader.MakeRadialGradient(
        { x: p.cx + p.R * 0.2, y: p.cy + p.R * 0.28 },
        p.R * 0.95,
        [Skia.Color([pal[0] * ia, pal[1] * ia, pal[2] * ia, ia]), Skia.Color([0, 0, 0, 0])],
        null,
        TileMode.Clamp
      )
    );
    canvas.drawCircle(p.cx + p.R * 0.2, p.cy + p.R * 0.28, p.R * 0.95, glow);
  }

  // 6. Front faces + glowing edges, one batch.
  if (pos.length > 0) {
    const verts = Skia.MakeVertices(VertexMode.Triangles, pos, tex, cols as unknown as SkColor[]);
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
    const paint = Skia.Paint();
    paint.setShader(
      edgeGlowEffect.makeShader([Math.min(0.45, wpx / triH), Math.min(0.5, gpx / triH), gk, er * ea, eg * ea, eb * ea, ea])
    );
    canvas.drawVertices(verts, BlendMode.Plus, paint);
  }
  if (edgeFade <= 0.01 || !intact) return;

  // 7. Glitter on corners that face the viewer: satellites carry a faint
  // always-on sparkle on every front corner plus brief bright flashes; the
  // core only flashes, so its glass stays clean.
  if (!(p.lowPower && !isSat)) {
    const dim: { x: number; y: number }[] = [];
    const bright: { x: number; y: number }[] = [];
    const step = isSat ? 1 : 3;
    for (let i = 0; i < nv; i += step) {
      if (rz[i] < 0.2) continue;
      const t = twinkle(p.phase, isSat ? 7 + (i % 5) : 5 + (i % 7), i);
      if (t > 0.3) bright.push(pt[i]);
      else if (isSat) dim.push(pt[i]);
    }
    const gp = Skia.Paint();
    gp.setStyle(PaintStyle.Stroke);
    gp.setStrokeCap(StrokeCap.Round);
    gp.setAntiAlias(true);
    const tr = isSat ? Math.min(1, ag![0] * 0.3 + 0.75) : 1;
    const tg = isSat ? Math.min(1, ag![1] * 0.3 + 0.75) : 1;
    const tb = isSat ? Math.min(1, ag![2] * 0.3 + 0.75) : 1;
    if (dim.length > 0) {
      gp.setStrokeWidth(1.4);
      gp.setColor(Skia.Color([tr, tg, tb, 0.45 * A]));
      canvas.drawPoints(PointMode.Points, dim, gp);
    }
    if (bright.length > 0) {
      gp.setStrokeWidth(isSat ? 2 : 2.2);
      gp.setColor(Skia.Color([tr, tg, tb, 0.95 * A]));
      canvas.drawPoints(PointMode.Points, bright, gp);
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
      const gx = (px[a] + px[b] + px[c]) / 3;
      const gy = (py[a] + py[b] + py[c]) / 3;
      const s = spec[best] * A;
      const L = p.R * 0.16 * (0.7 + 0.3 * s);
      const soft = Skia.Paint();
      soft.setColor(Skia.Color([1, 1, 1, 0.22 * s]));
      canvas.drawCircle(gx, gy, 4.5, soft);
      const ray = Skia.Paint();
      ray.setShader(
        Skia.Shader.MakeLinearGradient(
          { x: gx - L, y: gy },
          { x: gx + L, y: gy },
          [Skia.Color([1, 1, 1, 0]), Skia.Color([1, 1, 1, 0.85 * s]), Skia.Color([1, 1, 1, 0])],
          null,
          TileMode.Clamp
        )
      );
      canvas.drawRect(Skia.XYWHRect(gx - L, gy - 0.6, L * 2, 1.2), ray);
      ray.setShader(
        Skia.Shader.MakeLinearGradient(
          { x: gx, y: gy - L },
          { x: gx, y: gy + L },
          [Skia.Color([1, 1, 1, 0]), Skia.Color([1, 1, 1, 0.85 * s]), Skia.Color([1, 1, 1, 0])],
          null,
          TileMode.Clamp
        )
      );
      canvas.drawRect(Skia.XYWHRect(gx - 0.6, gy - L, 1.2, L * 2), ray);
      const core = Skia.Paint();
      core.setColor(Skia.Color([1, 1, 1, 0.95 * s]));
      canvas.drawCircle(gx, gy, 1.5, core);
    }
  }
}
