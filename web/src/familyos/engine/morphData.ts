// Particle morph data: gem → agent icon → next icon → gem (AGENT_WEB.md §7.4),
// the same construction as the mobile app's graphics/ParticleMorph.ts.
//
// Every particle i owns one target point in every shape (the gem's
// silhouette and each icon), so a morph is a straight interpolation between
// two point clouds. The interpolation itself runs in the vertex shader
// (engine/glMaterials.ts); this module only builds the clouds and the
// per-particle randoms, once, after first paint:
//   • delay[i] ∈ [0, 0.35]: when particle i peels off (stagger);
//   • sway[i] ∈ [−1, 1]: how far it swings sideways mid-flight (curl);
//   • phase[i]: its shimmer phase at rest.
import { AGENT_IDS } from '../theme/tokens';
import { sampleGem, sampleIcon } from '../graphics/iconPoints';
import { seededRandom } from '../graphics/crystalGeometry';

export const MORPH_PARTICLES = 1200;
export const MORPH_PARTICLES_LOW = 420;
/** Icon half-size in gem radii (the finance ring sits just outside the gem). */
export const ICON_SCALE = 1.2;
export const GEM_SCALE = 0.95;

export interface MorphData {
  n: number;
  /** shapes[0] = gem silhouette; shapes[1 + k] = icon of AGENT_IDS[k]. Flat xy. */
  shapes: Float32Array[];
  delay: Float32Array;
  sway: Float32Array;
  phase: Float32Array;
}

let cache: MorphData | null = null;

/** Built once (canvas / SVG path sampling, ~30 ms) and cached for every scene. */
export function morphData(n = MORPH_PARTICLES): MorphData {
  if (cache) return cache;
  const rand = seededRandom(99);
  const shapes = [sampleGem(n), ...AGENT_IDS.map((id) => sampleIcon(id, n))].map((a) => Float32Array.from(a));
  const delay = new Float32Array(n);
  const sway = new Float32Array(n);
  const phase = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    delay[i] = rand() * 0.35;
    sway[i] = (rand() - 0.5) * 2;
    phase[i] = rand() * Math.PI * 2;
  }
  cache = { n, shapes, delay, sway, phase };
  return cache;
}
