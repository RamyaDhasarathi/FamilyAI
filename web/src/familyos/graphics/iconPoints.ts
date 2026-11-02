// Agent icons for the particle morph (AGENT_WEB.md §7.4): the same SVG path
// strings as the mobile app's graphics/iconPoints.ts (100×100 box), sampled
// ONCE into point clouds.
//
// Sampling: ~80 % of the points fill the shape (a jittered grid tested with
// the canvas's isPointInPath / isPointInStroke, then randomly thinned to the
// exact count) and ~20 % sit on the outlines (evenly spaced by arc length
// with SVGPathElement.getPointAtLength; for stroked shapes, offset to either
// side of the centre line so both edges of the stroke read crisp). Output
// coordinates are normalised to [-1, 1] around the box centre.
import type { AgentId } from '../theme/tokens';
import { seededRandom } from './crystalGeometry';

interface Shape {
  d: string;
  /** Stroke width; omitted = filled shape. */
  w?: number;
  /** Subtract from the fill (door, basket slats). */
  hole?: boolean;
}

export const ICONS: Record<AgentId, Shape[]> = {
  // Dollar sign inside a ring.
  finance: [
    { d: 'M50 4 A46 46 0 1 1 49.99 4 Z', w: 4.5 },
    { d: 'M63 33 C59 26 41 25 37.5 34.5 C34 44 47 47.5 51 49 C58 51.5 66 55 62.5 65 C59 74 41 74.5 35.5 66', w: 8.5 },
    { d: 'M50 20 L50 80', w: 6 },
  ],
  // Graduation cap: board, crown, tassel.
  education: [
    { d: 'M50 18 L95 38 L50 58 L5 38 Z' },
    { d: 'M24 49 L24 67 C24 79 76 79 76 67 L76 49 L50 61 Z' },
    { d: 'M86 42 L86 68', w: 3.2 },
    { d: 'M86 66 m-4 0 a4 5 0 1 0 8 0 a4 5 0 1 0 -8 0' },
  ],
  // House with chimney and a door cut out.
  household: [
    { d: 'M50 10 L92 46 L82 46 L82 90 L18 90 L18 46 L8 46 Z' },
    { d: 'M66 16 L76 16 L76 32 L66 24 Z' },
    { d: 'M42 64 L58 64 L58 90 L42 90 Z', hole: true },
  ],
  // Calendar: frame, header bar, binder rings, day grid.
  calendar: [
    { d: 'M18 24 L82 24 Q88 24 88 30 L88 84 Q88 90 82 90 L18 90 Q12 90 12 84 L12 30 Q12 24 18 24 Z', w: 4.5 },
    { d: 'M12 24 L88 24 L88 38 L12 38 Z' },
    { d: 'M29 12 L36 12 L36 30 L29 30 Z' },
    { d: 'M64 12 L71 12 L71 30 L64 30 Z' },
    ...[0, 1, 2].flatMap((row) =>
      [0, 1, 2, 3].map((col) => {
        const x = 21 + col * 16;
        const y = 46 + row * 13.5;
        return { d: `M${x} ${y} L${x + 10} ${y} L${x + 10} ${y + 8.5} L${x} ${y + 8.5} Z` };
      })
    ),
  ],
  // Basket: handle, rim, tapered body with slats.
  grocery: [
    { d: 'M27 46 C27 12 73 12 73 46', w: 5 },
    { d: 'M8 42 L92 42 L92 53 L8 53 Z' },
    { d: 'M13 56 L87 56 L78 90 L22 90 Z' },
    ...[0, 1, 2, 3, 4].map((i) => {
      const x = 27 + i * 11;
      return { d: `M${x} 61 L${x + 4.5} 61 L${x + 3.5} 84 L${x + 1} 84 Z`, hole: true };
    }),
  ],
};

let ctx2d: CanvasRenderingContext2D | null = null;
function ctx(): CanvasRenderingContext2D {
  if (!ctx2d) {
    const c = document.createElement('canvas');
    c.width = 4;
    c.height = 4;
    ctx2d = c.getContext('2d')!;
    ctx2d.lineCap = 'round';
    ctx2d.lineJoin = 'round';
  }
  return ctx2d;
}

interface Compiled {
  shapes: { path: Path2D; w?: number; hole?: boolean; d: string }[];
}

function compile(shapes: Shape[]): Compiled {
  return { shapes: shapes.map((s) => ({ path: new Path2D(s.d), w: s.w, hole: s.hole, d: s.d })) };
}

function inShape(c: CanvasRenderingContext2D, s: Compiled['shapes'][number], x: number, y: number) {
  if (s.w !== undefined) {
    c.lineWidth = s.w;
    return c.isPointInStroke(s.path, x, y);
  }
  return c.isPointInPath(s.path, x, y);
}

function inside(cp: Compiled, x: number, y: number) {
  const c = ctx();
  if (cp.shapes.some((s) => s.hole && inShape(c, s, x, y))) return false;
  return cp.shapes.some((s) => !s.hole && inShape(c, s, x, y));
}

/** Sample `n` points of one icon → flat [x0, y0, x1, y1, …] in [-1, 1]. */
export function sampleIcon(id: AgentId, n: number, seed = 7): number[] {
  const rand = seededRandom(seed + id.length * 101);
  const cp = compile(ICONS[id]);
  const hasHoles = cp.shapes.some((s) => s.hole);
  const nOutline = Math.round(n * 0.2);
  const nFill = n - nOutline;

  // Fill: jittered grid, then thin to exactly nFill.
  const fill: number[][] = [];
  for (let step = 1.6; fill.length < nFill && step > 0.35; step *= 0.8) {
    fill.length = 0;
    for (let y = 0; y < 100; y += step) {
      for (let x = 0; x < 100; x += step) {
        const jx = x + rand() * step;
        const jy = y + rand() * step;
        if (inside(cp, jx, jy)) fill.push([jx, jy]);
      }
    }
  }
  for (let i = fill.length - 1; i > 0; i--) {
    const j = Math.floor(rand() * (i + 1));
    [fill[i], fill[j]] = [fill[j], fill[i]];
  }
  const out: number[] = [];
  for (let i = 0; i < nFill; i++) {
    const p = fill[i % Math.max(1, fill.length)] ?? [50, 50];
    out.push((p[0] - 50) / 50, (p[1] - 50) / 50);
  }

  // Outline: evenly spaced by arc length over every shape's path.
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('width', '0');
  svg.setAttribute('height', '0');
  svg.style.position = 'absolute';
  document.body.appendChild(svg);
  const contours = cp.shapes.map((s) => {
    const el = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    el.setAttribute('d', s.d);
    svg.appendChild(el);
    return { el, len: el.getTotalLength(), w: s.w };
  });
  const total = contours.reduce((s, k) => s + k.len, 0) || 1;
  for (let i = 0; i < nOutline; i++) {
    let d = ((i + rand() * 0.5) / nOutline) * total;
    let k = 0;
    while (k < contours.length - 1 && d > contours[k].len) {
      d -= contours[k].len;
      k++;
    }
    const c = contours[k];
    const at = Math.min(d, c.len);
    const p = c.el.getPointAtLength(at);
    let x = p.x;
    let y = p.y;
    if (c.w !== undefined) {
      // Stroked shape: put the point on one edge of the stroke.
      const q = c.el.getPointAtLength(Math.min(c.len, at + 0.5));
      const tx = q.x - p.x;
      const ty = q.y - p.y;
      const tl = Math.hypot(tx, ty) || 1;
      const side = i % 2 === 0 ? 1 : -1;
      x += (-ty / tl) * side * c.w * 0.45;
      y += (tx / tl) * side * c.w * 0.45;
    }
    if (inside(cp, x, y) || !hasHoles) out.push((x - 50) / 50, (y - 50) / 50);
    else out.push(out[(i * 2) % Math.max(2, out.length)], out[(i * 2 + 1) % Math.max(2, out.length)]);
  }
  svg.remove();
  return out;
}

/** Random points inside the gem's silhouette (unit disk, slightly flattened). */
export function sampleGem(n: number, seed = 3): number[] {
  const rand = seededRandom(seed);
  const out: number[] = [];
  for (let i = 0; i < n; i++) {
    const r = Math.sqrt(rand()) * 0.92;
    const a = rand() * Math.PI * 2;
    out.push(Math.cos(a) * r, Math.sin(a) * r * 0.96);
  }
  return out;
}
