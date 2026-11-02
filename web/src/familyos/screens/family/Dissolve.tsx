// Particle dissolve (and its reverse) for removing / restoring a member and
// for a new avatar stage (mobile Dissolve.tsx): points leave the shape
// radially with a little curl and fade; `reverse` gathers them back in.
import { useEffect, useRef } from 'react';
import { seededRandom } from '../../graphics/crystalGeometry';
import { useReducedMotion } from '../../hooks/useReducedMotion';

const N = 90;
const R = seededRandom(7);
const SEEDS = Array.from({ length: N }, () => ({ a: R() * Math.PI * 2, d: Math.sqrt(R()) * 26, s: 0.6 + R() * 0.9, c: (R() - 0.5) * 1.4 }));

/** Centred on (cx, cy) inside a box of `size`; the canvas overflows the box by 20 px each side. */
export function Dissolve({ color, reverse, size = 80 }: { color: string; reverse?: boolean; size?: number }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const reduced = useReducedMotion();
  useEffect(() => {
    const c = ref.current;
    const ctx = c?.getContext('2d');
    if (!c || !ctx || reduced) return;
    const W = size + 40;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    c.width = W * dpr;
    c.height = W * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const scale = size / 80;
    const t0 = performance.now();
    let raf = 0;
    const draw = (now: number) => {
      const t = Math.min(1, (now - t0) / 650);
      const e = 1 - Math.pow(1 - t, 3);
      const k = reverse ? 1 - e : e;
      ctx.clearRect(0, 0, W, W);
      ctx.globalAlpha = reverse ? e : 1 - e;
      ctx.fillStyle = color;
      for (const p of SEEDS) {
        const r = (p.d + k * 46 * p.s) * scale;
        const a = p.a + k * p.c;
        ctx.beginPath();
        ctx.arc(W / 2 + Math.cos(a) * r, W / 2 + Math.sin(a) * r, 1.2, 0, Math.PI * 2);
        ctx.fill();
      }
      if (t < 1) raf = requestAnimationFrame(draw);
      else ctx.clearRect(0, 0, W, W);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [color, reverse, size, reduced]);
  return <canvas ref={ref} className="dissolve" style={{ width: size + 40, height: size + 40 }} aria-hidden />;
}
