// Onboarding / secondary-page background (design.md §13.1, AGENT_WEB.md
// §8.8): OLED black, a faint violet glow from the top and a teal glow from
// the bottom, slowly drifting dust. The glows are CSS; the dust is a 2D
// canvas (the mobile SkSL hash field on a 30 px grid), so these pages stay
// light and never open a WebGL context.
import { useEffect, useRef } from 'react';
import { loopPhase } from '../engine/orbitLayout';
import { useReducedMotion } from '../hooks/useReducedMotion';

const CELL = 30;

function hash(x: number, y: number) {
  let px = (x * 123.34) % 1;
  let py = (y * 456.21) % 1;
  if (px < 0) px += 1;
  if (py < 0) py += 1;
  const d = px * (px + 45.32) + py * (py + 45.32);
  px += d;
  py += d;
  const r = (px * py) % 1;
  return r < 0 ? r + 1 : r;
}

export function OnboardingBackdrop({ glow = 'violet' }: { glow?: 'violet' | 'none' }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const reduced = useReducedMotion();
  useEffect(() => {
    const c = ref.current;
    if (!c) return;
    const ctx = c.getContext('2d');
    if (!ctx) return;
    let raf = 0;
    let clock = 0;
    let last = 0;
    let W = 0;
    let H = 0;
    const size = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      W = window.innerWidth;
      H = window.innerHeight;
      c.width = Math.round(W * dpr);
      c.height = Math.round(H * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    const draw = (now: number) => {
      const dt = last ? Math.min(now - last, 50) / 1000 : 0;
      last = now;
      if (!reduced) clock += dt;
      const ph = loopPhase(clock);
      ctx.clearRect(0, 0, W, H);
      const ox = Math.cos(ph) * 14;
      const oy = Math.sin(2 * ph) * 14;
      for (let cy = Math.floor(oy / CELL) - 1; cy * CELL < H + oy + CELL; cy++) {
        for (let cx = Math.floor(ox / CELL) - 1; cx * CELL < W + ox + CELL; cx++) {
          const r = hash(cx, cy);
          if (r <= 0.55) continue;
          const x = (cx + 0.2 + 0.6 * hash(cx + 1.3, cy + 1.3)) * CELL - ox;
          const y = (cy + 0.2 + 0.6 * hash(cx + 7.1, cy + 7.1)) * CELL - oy;
          const tw = 0.5 + 0.5 * Math.sin(Math.floor(4 + 18 * r) * ph + r * 50);
          ctx.fillStyle = `rgba(191,209,255,${(tw * 0.5).toFixed(3)})`;
          ctx.beginPath();
          ctx.arc(x, y, 0.75, 0, Math.PI * 2);
          ctx.fill();
        }
      }
      if (!reduced && !document.hidden) raf = requestAnimationFrame(draw);
    };
    const onVis = () => {
      if (!document.hidden && !raf) {
        last = 0;
        raf = requestAnimationFrame(draw);
      }
    };
    size();
    raf = requestAnimationFrame(draw);
    const onResize = () => {
      size();
      if (reduced) raf = requestAnimationFrame(draw);
    };
    window.addEventListener('resize', onResize);
    document.addEventListener('visibilitychange', onVis);
    return () => {
      cancelAnimationFrame(raf);
      raf = 0;
      window.removeEventListener('resize', onResize);
      document.removeEventListener('visibilitychange', onVis);
    };
  }, [reduced]);
  return (
    <div className={`backdrop backdrop--${glow}`} aria-hidden>
      <canvas ref={ref} className="backdrop__dust" />
    </div>
  );
}
