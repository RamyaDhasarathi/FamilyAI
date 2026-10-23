// Low-poly gem geometry, computed once on the JS thread and handed to the UI
// thread as plain number arrays.
//
// Method (mirrors FACETS in familyos_3d.py, but as real polygons):
//   1. Spread N points evenly over the unit sphere with the Fibonacci spiral
//      (golden-angle steps in longitude, uniform steps in z), then nudge each
//      by a small seeded random offset so the cut looks hand-made, not regular.
//   2. Scale each point's radius by ±`radiusJitter` so the silhouette is
//      irregular (AGENT.md §7.1 asks for ±6–10 %).
//   3. Take the 3D convex hull. A hull is always convex, so every triangle
//      either faces the camera or faces away: back-face culling is exact and
//      front faces never overlap on screen, so no per-frame depth sort is
//      needed. Points pushed inward by the jitter simply fall inside the hull.
//   4. Faces are wound counter-clockwise seen from outside, so the cross
//      product (b - a) × (c - a) is the outward normal.

export interface CrystalMesh {
  /** Vertex positions, xyz per vertex, unit-ish radius. */
  v: number[];
  /** Triangles, three vertex indices each (outward CCW winding). */
  f: number[];
  /** Unique edges: [a, b, faceL, faceR] per edge. */
  e: number[];
  /** Per-face random 0..1 (frost variation, hue offset, shard speed). */
  fr: number[];
  /** Per-face centroid in model space, xyz (drives the flowing interior hue). */
  fc: number[];
  nv: number;
  nf: number;
  ne: number;
}

/** mulberry32: tiny seeded PRNG so the gem is identical on every launch. */
export function seededRandom(seed: number) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

type V3 = [number, number, number];
const sub = (a: V3, b: V3): V3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const cross = (a: V3, b: V3): V3 => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const dot = (a: V3, b: V3) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];

function fibonacciSphere(n: number, jitter: number, rand: () => number): V3[] {
  const pts: V3[] = [];
  const golden = Math.PI * (1 + Math.sqrt(5));
  for (let i = 0; i < n; i++) {
    const k = i + 0.5;
    const phi = Math.acos(1 - (2 * k) / n);
    const th = golden * k;
    let x = Math.cos(th) * Math.sin(phi) + (rand() - 0.5) * 2 * jitter;
    let y = Math.cos(phi) + (rand() - 0.5) * 2 * jitter;
    let z = Math.sin(th) * Math.sin(phi) + (rand() - 0.5) * 2 * jitter;
    const len = Math.hypot(x, y, z);
    x /= len;
    y /= len;
    z /= len;
    pts.push([x, y, z]);
  }
  return pts;
}

/**
 * Incremental 3D convex hull, O(n²). Fine for the ≤ 120 points used here and
 * run once at start-up. Returns CCW (outward) triangles over `pts` indices.
 */
function convexHull(pts: V3[]): number[][] {
  const EPS = 1e-9;
  // Initial tetrahedron from four non-coplanar points.
  const i0 = 0;
  let i1 = 1;
  let best = 0;
  for (let i = 1; i < pts.length; i++) {
    const d = dot(sub(pts[i], pts[i0]), sub(pts[i], pts[i0]));
    if (d > best) {
      best = d;
      i1 = i;
    }
  }
  let i2 = -1;
  best = 0;
  for (let i = 0; i < pts.length; i++) {
    const c = cross(sub(pts[i1], pts[i0]), sub(pts[i], pts[i0]));
    const d = dot(c, c);
    if (d > best) {
      best = d;
      i2 = i;
    }
  }
  let i3 = -1;
  best = 0;
  const n012 = cross(sub(pts[i1], pts[i0]), sub(pts[i2], pts[i0]));
  for (let i = 0; i < pts.length; i++) {
    const d = Math.abs(dot(n012, sub(pts[i], pts[i0])));
    if (d > best) {
      best = d;
      i3 = i;
    }
  }
  const faces: number[][] = [];
  const centroid: V3 = [0, 0, 0];
  for (const i of [i0, i1, i2, i3]) {
    centroid[0] += pts[i][0] / 4;
    centroid[1] += pts[i][1] / 4;
    centroid[2] += pts[i][2] / 4;
  }
  const addFace = (a: number, b: number, c: number) => {
    // Orient so the normal points away from the interior centroid.
    const n = cross(sub(pts[b], pts[a]), sub(pts[c], pts[a]));
    if (dot(n, sub(pts[a], centroid)) < 0) faces.push([a, c, b]);
    else faces.push([a, b, c]);
  };
  addFace(i0, i1, i2);
  addFace(i0, i1, i3);
  addFace(i0, i2, i3);
  addFace(i1, i2, i3);

  const used = new Set([i0, i1, i2, i3]);
  for (let p = 0; p < pts.length; p++) {
    if (used.has(p)) continue;
    const visible: boolean[] = faces.map(([a, b, c]) => {
      const n = cross(sub(pts[b], pts[a]), sub(pts[c], pts[a]));
      return dot(n, sub(pts[p], pts[a])) > EPS;
    });
    if (!visible.some(Boolean)) continue; // inside the hull
    // Horizon = directed edges of visible faces whose twin is not visible.
    const visEdges = new Set<string>();
    faces.forEach((fc, i) => {
      if (!visible[i]) return;
      visEdges.add(`${fc[0]},${fc[1]}`);
      visEdges.add(`${fc[1]},${fc[2]}`);
      visEdges.add(`${fc[2]},${fc[0]}`);
    });
    const horizon: [number, number][] = [];
    faces.forEach((fc, i) => {
      if (!visible[i]) return;
      for (const [a, b] of [
        [fc[0], fc[1]],
        [fc[1], fc[2]],
        [fc[2], fc[0]],
      ]) {
        if (!visEdges.has(`${b},${a}`)) horizon.push([a, b]);
      }
    });
    const kept = faces.filter((_, i) => !visible[i]);
    faces.length = 0;
    faces.push(...kept);
    // Each horizon edge keeps its winding, so [a, b, p] is outward.
    for (const [a, b] of horizon) faces.push([a, b, p]);
  }
  return faces;
}

export function buildCrystal(opts: { points: number; jitter: number; radiusJitter: number; seed: number }): CrystalMesh {
  const rand = seededRandom(opts.seed);
  const raw = fibonacciSphere(opts.points, opts.jitter, rand).map((p) => {
    const r = 1 - opts.radiusJitter + rand() * opts.radiusJitter * 2;
    return [p[0] * r, p[1] * r, p[2] * r] as V3;
  });
  const hull = convexHull(raw);

  // Re-index to only the vertices on the hull.
  const remap = new Map<number, number>();
  const v: number[] = [];
  const f: number[] = [];
  for (const tri of hull) {
    for (const idx of tri) {
      if (!remap.has(idx)) {
        remap.set(idx, remap.size);
        v.push(raw[idx][0], raw[idx][1], raw[idx][2]);
      }
      f.push(remap.get(idx)!);
    }
  }
  const nf = f.length / 3;

  // Unique edges with the two faces that share them.
  const edgeMap = new Map<string, number[]>();
  for (let i = 0; i < nf; i++) {
    const tri = [f[i * 3], f[i * 3 + 1], f[i * 3 + 2]];
    for (let k = 0; k < 3; k++) {
      const a = tri[k];
      const b = tri[(k + 1) % 3];
      const key = a < b ? `${a},${b}` : `${b},${a}`;
      const rec = edgeMap.get(key);
      if (rec) rec[3] = i;
      else edgeMap.set(key, [Math.min(a, b), Math.max(a, b), i, i]);
    }
  }
  const e: number[] = [];
  edgeMap.forEach((rec) => e.push(...rec));

  const fr: number[] = [];
  const fc: number[] = [];
  for (let i = 0; i < nf; i++) {
    fr.push(rand());
    const a = f[i * 3] * 3;
    const b = f[i * 3 + 1] * 3;
    const c = f[i * 3 + 2] * 3;
    fc.push((v[a] + v[b] + v[c]) / 3, (v[a + 1] + v[b + 1] + v[c + 1]) / 3, (v[a + 2] + v[b + 2] + v[c + 2]) / 3);
  }
  return { v, f, e, fr, fc, nv: v.length / 3, nf, ne: e.length / 4 };
}

// The gem and the satellites. ~96 points → ~190 faces; ~26 → ~48 faces.
export const coreMesh = buildCrystal({ points: 68, jitter: 0.08, radiusJitter: 0.1, seed: 5 });
export const coreMeshLow = buildCrystal({ points: 44, jitter: 0.07, radiusJitter: 0.08, seed: 5 });
export const satelliteMeshes = [11, 23, 37, 41, 53].map((seed) =>
  buildCrystal({ points: 24, jitter: 0.12, radiusJitter: 0.1, seed })
);
