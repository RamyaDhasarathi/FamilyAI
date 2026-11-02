// Agent hero charts (AGENT_WEB.md §7.6), the mobile Charts.tsx in SVG.
import { useEffect, useId, useMemo, useRef, useState, type ReactNode } from 'react';
import { motion } from 'framer-motion';
import { durations, easings } from '../theme/motion';
import { withAlpha } from '../theme/tokens';
import { useReducedMotion } from '../hooks/useReducedMotion';

/**
 * Smooth curve through the points: Catmull-Rom converted to cubic Béziers.
 * For segment p1→p2 with neighbours p0, p3 the control points are
 * p1 + (p2 − p0)/6 and p2 − (p3 − p1)/6 (uniform Catmull-Rom, tension ½).
 */
function catmullRom(pts: [number, number][]) {
  let d = `M${pts[0][0]} ${pts[0][1]}`;
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[Math.max(0, i - 1)];
    const p1 = pts[i];
    const p2 = pts[i + 1];
    const p3 = pts[Math.min(pts.length - 1, i + 2)];
    const c1x = p1[0] + (p2[0] - p0[0]) / 6;
    const c1y = p1[1] + (p2[1] - p0[1]) / 6;
    const c2x = p2[0] - (p3[0] - p1[0]) / 6;
    const c2y = p2[1] - (p3[1] - p1[1]) / 6;
    d += ` C${c1x.toFixed(2)} ${c1y.toFixed(2)} ${c2x.toFixed(2)} ${c2y.toFixed(2)} ${p2[0].toFixed(2)} ${p2[1].toFixed(2)}`;
  }
  return d;
}

/** Sparkline: 2 px line in the agent colour, gradient fill, glowing end dot; draws in over 900 ms. */
export function Sparkline({ series, color, height = 92 }: { series: number[]; color: string; height?: number }) {
  const id = useId().replace(/:/g, '');
  const reduced = useReducedMotion();
  const wrap = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(320);
  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(120, Math.round(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const { line, fill, end } = useMemo(() => {
    const min = Math.min(...series);
    const max = Math.max(...series);
    const pad = 8;
    const pts = series.map((v, i): [number, number] => [
      pad + (i / (series.length - 1)) * (width - pad * 2),
      pad + (1 - (v - min) / (max - min || 1)) * (height - pad * 2),
    ]);
    const d = catmullRom(pts);
    const last = pts[pts.length - 1];
    return { line: d, fill: `${d} L${last[0]} ${height} L${pts[0][0]} ${height} Z`, end: last };
  }, [series, width, height]);
  const t = { duration: reduced ? 0 : durations.sparkline / 1000, ease: easings.inOutCubic };
  return (
    <div ref={wrap} className="sparkline">
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden>
        <defs>
          <linearGradient id={`sf${id}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor={withAlpha(color, 0.28)} />
            <stop offset="1" stopColor={withAlpha(color, 0)} />
          </linearGradient>
          <filter id={`sg${id}`} x="-100%" y="-100%" width="300%" height="300%">
            <feGaussianBlur stdDeviation="3" />
          </filter>
        </defs>
        <motion.path d={fill} fill={`url(#sf${id})`} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={t} />
        <motion.path
          d={line}
          fill="none"
          stroke={color}
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
          initial={{ pathLength: reduced ? 1 : 0 }}
          animate={{ pathLength: 1 }}
          transition={t}
        />
        <motion.g initial={{ opacity: reduced ? 1 : 0 }} animate={{ opacity: 1 }} transition={{ delay: reduced ? 0 : t.duration * 0.95, duration: 0.2 }}>
          <circle cx={end[0]} cy={end[1]} r={9} fill={withAlpha(color, 0.45)} filter={`url(#sg${id})`} />
          <circle cx={end[0]} cy={end[1]} r={4} fill={color} />
        </motion.g>
      </svg>
    </div>
  );
}

/** Seven rounded bars; today's in the agent colour, the rest muted blue-grey; grow with stagger. */
export function WeekBars({ bars, todayIndex, color, height = 72 }: { bars: number[]; todayIndex: number; color: string; height?: number }) {
  const reduced = useReducedMotion();
  return (
    <div className="week-bars" style={{ height }} aria-hidden>
      {bars.map((b, i) => (
        <motion.span
          key={i}
          className="week-bars__bar"
          style={{ background: i === todayIndex ? color : 'rgba(120,140,170,0.42)', height: Math.max(8, b * height), originY: 1 }}
          initial={{ scaleY: reduced ? 1 : 0 }}
          animate={{ scaleY: 1 }}
          transition={{ delay: reduced ? 0 : i * 0.06, duration: reduced ? 0 : 0.52, ease: easings.outCubic }}
        />
      ))}
    </div>
  );
}

export function ProgressBars({ items, color, renderLabel }: { items: { name: string; pct: number }[]; color: string; renderLabel: (name: string, pct: number) => ReactNode }) {
  const reduced = useReducedMotion();
  return (
    <div>
      {items.map((it, i) => (
        <div key={it.name} className="progress-item">
          {renderLabel(it.name, it.pct)}
          <div className="progress-track" role="progressbar" aria-label={it.name} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(it.pct * 100)}>
            <motion.span
              className="progress-fill"
              style={{ background: color }}
              initial={{ width: reduced ? `${it.pct * 100}%` : '0%' }}
              animate={{ width: `${it.pct * 100}%` }}
              transition={{ delay: reduced ? 0 : i * 0.09, duration: reduced ? 0 : 0.7, ease: easings.outCubic }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

/** Task ring that sweeps to `pct` on mount. */
export function TaskRing({ pct, color, size = 84, stroke = 6, children }: { pct: number; color: string; size?: number; stroke?: number; children?: ReactNode }) {
  const reduced = useReducedMotion();
  const r = size / 2 - stroke;
  return (
    <span className="task-ring" style={{ width: size, height: size }}>
      <svg width={size} height={size} aria-hidden>
        <circle cx={size / 2} cy={size / 2} r={r} stroke="rgba(255,255,255,0.08)" strokeWidth={stroke} fill="none" />
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          fill="none"
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
          initial={{ pathLength: reduced ? pct : 0 }}
          animate={{ pathLength: pct }}
          transition={{ duration: reduced ? 0 : 0.9, ease: easings.inOutCubic }}
        />
      </svg>
      {children ? <span className="task-ring__label">{children}</span> : null}
    </span>
  );
}

/** Count-up for stat tiles (600 ms on mount); the final value at once under reduced motion. */
export function useCountUp(target: number, duration = durations.countUp) {
  const reduced = useReducedMotion();
  const [v, setV] = useState(0);
  useEffect(() => {
    if (reduced) return;
    let raf = 0;
    const t0 = performance.now();
    const tick = () => {
      const k = Math.min(1, (performance.now() - t0) / duration);
      setV(target * (1 - Math.pow(1 - k, 3)));
      if (k < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, duration, reduced]);
  return reduced ? target : v;
}
