// v2 stone shapes (see stoneStyle.ts). The video's satellites are rough,
// uncut crystals rather than tidy polyhedra, so each one gets more facets,
// stronger radius jitter and its own uneven proportions.
//
// The proportions are an axis-aligned scale applied after the hull is built.
// Scaling is affine, so a convex hull stays a convex hull with the same faces
// and edges: only the vertex positions and face centroids need updating.
import { buildCrystal, seededRandom, type CrystalMesh } from './crystalGeometry';

function stretch(m: CrystalMesh, sx: number, sy: number, sz: number): CrystalMesh {
  const v = m.v.slice();
  for (let i = 0; i < m.nv; i++) {
    v[i * 3] *= sx;
    v[i * 3 + 1] *= sy;
    v[i * 3 + 2] *= sz;
  }
  // Keep the largest extent at 1 so the stone still fits its slot.
  let r = 0;
  for (let i = 0; i < m.nv; i++) r = Math.max(r, Math.hypot(v[i * 3], v[i * 3 + 1], v[i * 3 + 2]));
  for (let i = 0; i < v.length; i++) v[i] /= r;
  const fc: number[] = [];
  for (let k = 0; k < m.nf; k++) {
    const a = m.f[k * 3] * 3;
    const b = m.f[k * 3 + 1] * 3;
    const c = m.f[k * 3 + 2] * 3;
    fc.push((v[a] + v[b] + v[c]) / 3, (v[a + 1] + v[b + 1] + v[c + 1]) / 3, (v[a + 2] + v[b + 2] + v[c + 2]) / 3);
  }
  return { ...m, v, fc };
}

/**
 * The v2 core gem: fewer, larger facets than v1 (52 points instead of 68),
 * closer to the video's gem and cheaper per frame, which pays for v2's
 * see-through back wall.
 */
export const coreMeshV2: CrystalMesh = buildCrystal({ points: 52, jitter: 0.08, radiusJitter: 0.1, seed: 5 });

/** Five rough stones, one per agent (AGENT_IDS order), stable across launches. */
export const satelliteMeshesV2: CrystalMesh[] = [11, 23, 37, 41, 53].map((seed) => {
  const rand = seededRandom(seed * 7 + 1);
  const mesh = buildCrystal({ points: 26, jitter: 0.16, radiusJitter: 0.2, seed });
  return stretch(mesh, 0.85 + rand() * 0.35, 0.78 + rand() * 0.3, 0.85 + rand() * 0.3);
});
