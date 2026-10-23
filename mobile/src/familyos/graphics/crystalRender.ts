// Per-frame crystal drawing, run on the UI thread inside a Skia picture.
//
// Pipeline per frame (AGENT.md §7.1):
//   rotate vertices (spin about Y, tilt about X) → perspective project →
//   per face: outward normal, front/back test against the camera →
//   shade → emit three coloured corners into one SkVertices batch →
//   edges in three passes (back, front, silhouette rim).
// Shading follows familyos_3d.py's quantum_core(): a cosine-palette
// iridescence `irid()` driven by a flowing interior pattern, Lambert key/fill
// lights, a Fresnel rim (edge-on faces glow) and a Blinn sparkle.
import {
  BlendMode,
  Skia,
  VertexMode,
  TileMode,
  type SkCanvas,
  type SkColor,
} from '@shopify/react-native-skia';
import type { CrystalMesh } from './crystalGeometry';

const TAU = Math.PI * 2;
// Lights in view space (y up, +z towards the viewer), as in the renderer.
const LK = [-0.55 / 1.0464, 0.7 / 1.0464, 0.55 / 1.0464];
const LF = [0.65 / 0.9518, -0.35 / 0.9518, 0.6 / 0.9518];
// Half-vector of key light and view (0,0,1), for the specular sparkle.
const HK = (() => {
  const x = LK[0];
  const y = LK[1];
  const z = LK[2] + 1;
  const l = Math.hypot(x, y, z);
  return [x / l, y / l, z / l];
})();
/** Camera distance in model radii. Larger = flatter perspective. */
const CAM = 4.2;

/**
 * Facet edges drawn inside the triangle batch. Each triangle's corners get
 * texture coordinates (0,0), (1,0), (0,1); Skia interpolates them, so `p` is
 * the pixel's barycentric position and min(b) is its distance to the nearest
 * edge, as a fraction of the triangle. Pixels near an edge get `col` added on
 * top of the vertex colour (drawVertices with BlendMode.Plus). No paths are
 * stroked, so edges cost nothing extra per frame. Edge width scales with each
 * triangle's size (SkSL has no screen-space derivatives), which reads fine
 * because the facets are of similar size.
 */
const edgeEffect = Skia.RuntimeEffect.Make(`
uniform float w;
uniform float4 col;
half4 main(float2 p) {
  float e = min(min(p.x, p.y), 1.0 - p.x - p.y);
  float k = 1.0 - smoothstep(w * 0.25, w, e);
  return half4(col * k);
}`)!;
const BARY = [
  { x: 0, y: 0 },
  { x: 1, y: 0 },
  { x: 0, y: 1 },
];

export interface CrystalParams {
  cx: number;
  cy: number;
  /** Model radius in px. */
  R: number;
  rotY: number;
  tiltX: number;
  /** Loop phase in radians (whole-number multiples only, so loops are seamless). */
  phase: number;
  /** Interpolated scenario palette (see stateThemes.paletteOf); ignored for satellites. */
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
  /** Fewer passes on low-power devices. */
  lowPower: boolean;
}

/** One decimal place is plenty for path coordinates and keeps strings short. */
function r1(x: number) {
  'worklet';
  return Math.round(x * 10) / 10;
}

function clamp01(x: number) {
  'worklet';
  return x < 0 ? 0 : x > 1 ? 1 : x;
}

/** Cyclic three-stop gradient through palette[0..8] at u ∈ [0,1). */
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

/** The flowing three-wave interior pattern from quantum_core(), at a model-space point. */
function flowField(qx: number, qy: number, qz: number, phase: number) {
  'worklet';
  return Math.sin(5 * qx + phase) + Math.sin(4 * qy - 2 * phase) + Math.sin(4 * qz + 3 * qx + phase);
}

/**
 * Base glass colour at a point of the flow field: the renderer's irid()
 * cosine rainbow (periodic in h, desaturated to 85 %), pulled towards the
 * scenario's three-stop palette by `tintAmt`.
 */
function baseColour(pal: number[], tintAmt: number, vv: number, qy: number, rnd: number, phase: number, out: number[]) {
  'worklet';
  const h = 0.12 * vv + 0.32 * qy + 0.25 * rnd + phase / TAU;
  let ir = 0.5 + 0.5 * Math.cos(TAU * h);
  let ig = 0.5 + 0.5 * Math.cos(TAU * (h + 0.33));
  let ib = 0.5 + 0.5 * Math.cos(TAU * (h + 0.67));
  const il = (ir + ig + ib) / 3;
  ir = il + (ir - il) * 0.85;
  ig = il + (ig - il) * 0.85;
  ib = il + (ib - il) * 0.85;
  paletteAt(pal, 0.5 + 0.16 * vv + 0.3 * qy + 0.2 * rnd, out);
  const r = ir + (out[0] - ir) * tintAmt;
  const g = ig + (out[1] - ig) * tintAmt;
  const b = ib + (out[2] - ib) * tintAmt;
  // Mixing two hues greys them out; push saturation back up so the glass glows.
  const l = (r + g + b) / 3;
  out[0] = clamp01(l + (r - l) * 1.75);
  out[1] = clamp01(l + (g - l) * 1.75);
  out[2] = clamp01(l + (b - l) * 1.75);
}

export function drawCrystal(canvas: SkCanvas, m: CrystalMesh, p: CrystalParams) {
  'worklet';
  if (p.alpha <= 0.01) return;
  const { v, f, fr, fc, nv, nf } = m;
  const cY = Math.cos(p.rotY);
  const sY = Math.sin(p.rotY);
  const cX = Math.cos(p.tiltX);
  const sX = Math.sin(p.tiltX);
  const ex = p.explode;
  const isSat = p.agent !== null;

  // 1. Rotate + project every vertex once.
  const rx: number[] = new Array(nv);
  const ry: number[] = new Array(nv);
  const rz: number[] = new Array(nv);
  const px: number[] = new Array(nv);
  const py: number[] = new Array(nv);
  for (let i = 0; i < nv; i++) {
    const x = v[i * 3];
    const y = v[i * 3 + 1];
    const z = v[i * 3 + 2];
    const x1 = x * cY + z * sY;
    const z1 = -x * sY + z * cY;
    const y2 = y * cX - z1 * sX;
    const z2 = y * sX + z1 * cX;
    rx[i] = x1;
    ry[i] = y2;
    rz[i] = z2;
    const s = CAM / (CAM - z2);
    px[i] = p.cx + x1 * p.R * s * p.sx;
    py[i] = p.cy - y2 * p.R * s * p.sy;
  }


  // 2a. Core only: the colour field sampled at every vertex, plus a vertex
  // Fresnel term. The gem is nearly spherical, so the rotated vertex direction
  // stands in for a smooth normal. Blending these into each face's corners
  // gives the soft gradients inside facets seen in the video.
  const pal = p.palette;
  const tintAmt = isSat ? 0 : pal[9];
  const pc = [0, 0, 0];
  const vb: number[] = isSat ? [] : new Array(nv * 3);
  const vfr: number[] = isSat ? [] : new Array(nv);
  if (!isSat) {
    for (let i = 0; i < nv; i++) {
      const qx = v[i * 3];
      const qy = v[i * 3 + 1];
      const qz = v[i * 3 + 2];
      const vv = flowField(qx, qy, qz, p.phase);
      baseColour(pal, tintAmt, vv, qy, 0.5, p.phase, pc);
      vb[i * 3] = pc[0];
      vb[i * 3 + 1] = pc[1];
      vb[i * 3 + 2] = pc[2];
      const len = Math.hypot(rx[i], ry[i], rz[i]) || 1;
      vfr[i] = Math.pow(1 - clamp01(rz[i] / len), 1.5);
    }
  }

  // 2b. Faces: normal, facing, glass shading.
  const front: boolean[] = new Array(nf);
  const order: number[] = [];
  const depth: number[] = new Array(nf);
  const fnx: number[] = new Array(nf);
  const fny: number[] = new Array(nf);
  const spec: number[] = new Array(nf);
  // Per face: base rgb, light multiplier, additive white, alpha, flow, key-light.
  const fb: number[] = new Array(nf * 3);
  const fl: number[] = new Array(nf);
  const fw: number[] = new Array(nf);
  const fa: number[] = new Array(nf);
  const ffl: number[] = new Array(nf);
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
    // View vector from the face to the camera at (0, 0, CAM).
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
    const sp = Math.pow(clamp01(nx * HK[0] + ny * HK[1] + nz * HK[2]), isSat ? 24 : 56);
    spec[fi] = isFront ? sp : 0;
    flm[fi] = lam;
    if (isSat) {
      const ag = p.agent!;
      const fres = (1 - nvw) * (1 - nvw);
      fb[fi * 3] = ag[0];
      fb[fi * 3 + 1] = ag[1];
      fb[fi * 3 + 2] = ag[2];
      fl[fi] = 0.3 + 0.8 * lam + 0.3 * fil + p.glow * 0.4 + fres * 0.35;
      fw[fi] = sp * 0.7;
      fa[fi] = isFront ? 0.16 + 0.34 * lam + 0.3 * fres : 0.07;
      ffl[fi] = 0;
    } else {
      // Glass: faces looking straight at the viewer are dark and see-through
      // (the back edges show through), faces at grazing angles glow (Fresnel),
      // and the flowing interior lights some facets from within.
      const qx = fc[fi * 3];
      const qy = fc[fi * 3 + 1];
      const qz = fc[fi * 3 + 2];
      const vv = flowField(qx, qy, qz, p.phase);
      baseColour(pal, tintAmt, vv, qy, fr[fi], p.phase, pc);
      fb[fi * 3] = pc[0];
      fb[fi * 3 + 1] = pc[1];
      fb[fi * 3 + 2] = pc[2];
      const flow = 0.5 + 0.5 * Math.sin(2 * vv + p.phase);
      ffl[fi] = flow;
      const fres = Math.pow(1 - nvw, 1.5);
      if (isFront) {
        const f2 = flow * flow;
        fl[fi] = 0.08 + 1.05 * fres + 1.6 * f2 * (0.45 + 0.55 * lam) + 0.1 * fil;
        fw[fi] = sp * 0.95 + 0.06 * fres * (0.4 + lam) + 0.05 * f2 * flow * lam;
        fa[fi] = clamp01(0.22 + 0.6 * fres + 0.45 * f2 * (0.3 + 0.7 * lam));
      } else {
        // The inside of the far wall, seen through the dark front facets.
        fl[fi] = 0.2 + 0.25 * flow;
        fw[fi] = 0.015;
        fa[fi] = 0.34;
      }
    }
    fa[fi] *= p.alpha * fade;
  }

  // 3. Draw order. Intact hull: back faces first, then front (no overlaps
  // within each group). Shattered: shards fly apart and can overlap, so sort
  // everything far → near.
  //
  // Cost note: every point and colour handed to Skia crosses JSI as an object,
  // which dominates the frame (measured: ~3 ms for 130 coloured faces, ~2 ms
  // for edges via drawPoints). So while the gem is intact, its back faces are
  // drawn as ONE gradient-filled path and all edges as SVG path strings (one
  // JSI call each); only front faces keep per-corner colours.
  const intact = ex <= 0.001;
  if (!intact) order.sort((i, j) => depth[i] - depth[j]);
  else order.sort((i, j) => (front[i] === front[j] ? 0 : front[i] ? 1 : -1));

  const pos: { x: number; y: number }[] = [];
  const tex: { x: number; y: number }[] = [];
  const cols: number[][] = [];
  let backPath = '';
  for (let k = 0; k < order.length; k++) {
    const fi = order[k];
    if (intact && !front[fi]) {
      // Satellites show their back only through edges; the core's back wall
      // becomes one silhouette path (union of back triangles).
      if (!isSat) {
        const a = f[fi * 3];
        const b = f[fi * 3 + 1];
        const c = f[fi * 3 + 2];
        backPath += `M${r1(px[a])} ${r1(py[a])}L${r1(px[b])} ${r1(py[b])}L${r1(px[c])} ${r1(py[c])}Z`;
      }
      continue;
    }
    const a0 = fa[fi];
    if (a0 <= 0.003) continue;
    const a = f[fi * 3];
    const b = f[fi * 3 + 1];
    const c = f[fi * 3 + 2];
    let ax = px[a];
    let ay = py[a];
    let bx = px[b];
    let by = py[b];
    let cx = px[c];
    let cy = py[c];
    if (ex > 0) {
      // Shatter: push each shard out along its normal and shrink it towards
      // its own centre, faster for shards with a higher random seed.
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
    pos.push({ x: ax, y: ay }, { x: bx, y: by }, { x: cx, y: cy });
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
        // Blend the face colour with the vertex colour field, and the face
        // light with the vertex Fresnel, for smooth gradients across facets.
        r0 = 0.55 * r0 + 0.45 * vb[vi * 3];
        g0 = 0.55 * g0 + 0.45 * vb[vi * 3 + 1];
        b0 = 0.55 * b0 + 0.45 * vb[vi * 3 + 2];
        if (front[fi]) {
          const lv = 0.08 + 1.05 * vfr[vi] + 1.6 * ffl[fi] * ffl[fi] * (0.45 + 0.55 * flm[fi]);
          li = 0.55 * lf + 0.45 * lv;
        }
      }
      cols.push([clamp01(r0 * li + wf), clamp01(g0 * li + wf), clamp01(b0 * li + wf * 1.05), a0]);
    }
  }
  if (backPath) {
    // The far wall of the glass: dim, palette-tinted, darker towards the rim.
    const bp = Skia.Path.MakeFromSVGString(backPath);
    if (bp) {
      const mid = [pal[3] * 0.3 + 0.03, pal[4] * 0.3 + 0.03, pal[5] * 0.3 + 0.05];
      const rim = [pal[6] * 0.22 + 0.02, pal[7] * 0.22 + 0.02, pal[8] * 0.26 + 0.04];
      const bgp = Skia.Paint();
      bgp.setAntiAlias(true);
      bgp.setShader(
        Skia.Shader.MakeRadialGradient(
          { x: p.cx - p.R * 0.25, y: p.cy - p.R * 0.3 },
          p.R * 1.25,
          [Skia.Color([mid[0], mid[1], mid[2], 0.55 * p.alpha]), Skia.Color([rim[0], rim[1], rim[2], 0.48 * p.alpha])],
          null,
          TileMode.Clamp
        )
      );
      canvas.drawPath(bp, bgp);
    }
  }
  // 4. Faces + their edges in one draw. Edge brightness: white for the core,
  // a lifted agent colour for satellites; fades out as the gem shatters.
  const edgeFade = ex > 0 ? Math.max(0, 1 - ex * 2.5) : 1;
  const A = p.alpha * edgeFade;
  if (pos.length > 0) {
    // Native MakeVertices accepts plain [r, g, b, a] arrays (JsiSkColor::fromValue),
    // which avoids allocating a Float32Array per corner; the TS type only lists SkColor.
    const verts = Skia.MakeVertices(VertexMode.Triangles, pos, tex, cols as unknown as SkColor[]);
    // Average triangle height in px, to turn an edge width in px into a
    // barycentric threshold.
    const triH = p.R * Math.sqrt((4 * Math.PI) / nf) * 0.95;
    let er = 1;
    let eg = 1;
    let eb = 1;
    let ea = 0.34 * A;
    let wpx = 0.85;
    if (isSat) {
      const ag = p.agent!;
      er = Math.min(1, ag[0] * 0.55 + 0.5);
      eg = Math.min(1, ag[1] * 0.55 + 0.5);
      eb = Math.min(1, ag[2] * 0.55 + 0.5);
      ea = (0.75 + 0.25 * p.glow) * A;
      wpx = 1.2;
    }
    const paint = Skia.Paint();
    paint.setShader(edgeEffect.makeShader([Math.min(0.45, wpx / triH), er * ea, eg * ea, eb * ea, ea]));
    canvas.drawVertices(verts, BlendMode.Plus, paint);
  }
  if (edgeFade <= 0.01) return;
  if (!isSat) {
    // Specular sparkle on up to three faces that face the key light.
    const glint = Skia.Paint();
    glint.setAntiAlias(true);
    let shown = 0;
    for (let fi = 0; fi < nf && shown < 3; fi++) {
      if (spec[fi] < 0.55 || ex > 0) continue;
      const a = f[fi * 3];
      const b = f[fi * 3 + 1];
      const c = f[fi * 3 + 2];
      const gx = (px[a] + px[b] + px[c]) / 3;
      const gy = (py[a] + py[b] + py[c]) / 3;
      const s = spec[fi] * A;
      glint.setColor(Skia.Color(`rgba(255,255,255,${0.85 * s})`));
      canvas.drawCircle(gx, gy, 1.4, glint);
      glint.setColor(Skia.Color(`rgba(255,255,255,${0.18 * s})`));
      canvas.drawCircle(gx, gy, 4.5, glint);
      shown++;
    }
  }
}
