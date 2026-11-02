// Family orbit header (mobile screens/family/FamilyOrbit.tsx): the mini
// crystal with one glowing dot per member on a tilted ring, in each member's
// stage colour (the owner's a little larger). New members fly in from the
// edge; removed ones dissolve into particles. With only the owner, dashed
// slots wait on the ring. Clicking the crystal gives the Home jelly.
// Drawn by the shared mini renderer: dust and crystal in WebGL, dots in 2D
// behind and in front of it.
import { useEffect, useMemo, useRef, useState, type MouseEvent } from 'react';
import type { FamilyMember } from '../../services/interfaces';
import { stageOf } from '../../family/model';
import { hexToRgb } from '../../theme/tokens';
import { paletteOf } from '../../theme/stateThemes';
import { qToMat } from '../../graphics/coreMotion';
import { createOrbitScene } from '../../engine/sceneState';
import { jellyAtGem, stepCore } from '../../engine/coreInput';
import { useReducedMotion } from '../../hooks/useReducedMotion';

type Dot = { id: string; c: number[]; owner: boolean; born: number; died: number; ang: number };

const ENTER = 0.9;
const LEAVE = 0.8;
const HEIGHT = 150;
const R = 26;

const rgba = (c: number[], a: number) => `rgba(${Math.round(c[0] * 255)},${Math.round(c[1] * 255)},${Math.round(c[2] * 255)},${a.toFixed(3)})`;

function drawDot(ctx: CanvasRenderingContext2D, x: number, y: number, r: number, col: number[], a: number) {
  if (r <= 0 || a <= 0) return;
  const disc = (rr: number, fill: string) => {
    ctx.fillStyle = fill;
    ctx.beginPath();
    ctx.arc(x, y, rr, 0, Math.PI * 2);
    ctx.fill();
  };
  disc(r * 2.6, rgba(col, 0.22 * a));
  disc(r * 1.5, rgba(col, 0.55 * a));
  disc(r, rgba([Math.min(1, col[0] * 0.5 + 0.55), Math.min(1, col[1] * 0.5 + 0.55), Math.min(1, col[2] * 0.5 + 0.55)], a));
}

export function FamilyOrbit({ members }: { members: FamilyMember[] }) {
  const reduced = useReducedMotion();
  const wrap = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [width, setWidth] = useState(340);
  const scene = useMemo(() => createOrbitScene('calm'), []);
  const pal = useMemo(() => paletteOf('calm'), []);
  const dots = useRef<Dot[]>([]);
  const first = useRef(true);

  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.min(380, Math.max(240, Math.round(e.contentRect.width)))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Diff members → dots: new ids fly in, missing ids dissolve; colours follow stage changes.
  useEffect(() => {
    const now = scene.clock;
    const ids = new Set(members.map((m) => m.id));
    const cur = dots.current;
    const next: Dot[] = cur.map((d) => (!ids.has(d.id) && d.died < 0 ? { ...d, died: now } : d));
    for (const m of members) {
      const c = hexToRgb(stageOf(m).accent);
      const live = next.find((d) => d.id === m.id && d.died < 0);
      if (live) {
        live.c = c;
        continue;
      }
      const dot: Dot = { id: m.id, c, owner: m.isOwner, born: first.current ? -10 : now, died: -1, ang: 0 };
      const revived = next.findIndex((d) => d.id === m.id);
      if (revived >= 0) next[revived] = dot;
      else next.push(dot);
    }
    first.current = false;
    dots.current = next;
  }, [members, scene]);

  useEffect(() => {
    const c = canvas.current;
    if (!c) return;
    let alive = true;
    let off = () => {};
    const cx = width / 2;
    const cy = HEIGHT / 2;
    const rx = Math.min(width * 0.4, 170);
    const ry = HEIGHT * 0.28;
    const place = (d: Dot, now: number) => {
      let x = cx + Math.cos(d.ang) * rx;
      let y = cy + Math.sin(d.ang) * ry;
      const enter = Math.min(1, (now - d.born) / ENTER);
      if (enter < 1) {
        // Fly in from the right edge on an ease-out curve.
        const e = 1 - Math.pow(1 - enter, 3);
        x = width + 24 + (x - width - 24) * e;
        y = cy - 30 + (y - cy + 30) * e;
      }
      return { x, y, front: Math.sin(d.ang) > 0 };
    };
    const drawDots = (ctx: CanvasRenderingContext2D, front: boolean) => {
      const now = scene.clock;
      const live = dots.current.filter((d) => d.died < 0);
      if (!front && live.length <= 1) {
        // Empty state: dashed slots on the ring.
        ctx.save();
        ctx.setLineDash([3, 4]);
        ctx.strokeStyle = 'rgba(255,255,255,0.28)';
        for (let i = 1; i < 5; i++) {
          const a = (i / 5) * Math.PI * 2 + 0.5;
          ctx.beginPath();
          ctx.arc(cx + Math.cos(a) * rx, cy + Math.sin(a) * ry, 7, 0, Math.PI * 2);
          ctx.stroke();
        }
        ctx.restore();
      }
      for (const d of dots.current) {
        const p = place(d, now);
        if (p.front !== front) continue;
        const r = (d.owner ? 5.5 : 4) * (p.front ? 1 : 0.8);
        if (d.died >= 0) {
          // Dissolve: the dot fades while particles fly outward.
          const t = Math.min(1, (now - d.died) / LEAVE);
          drawDot(ctx, p.x, p.y, r * (1 - t), d.c, 1 - t);
          ctx.fillStyle = rgba(d.c, 1 - t);
          for (let k = 0; k < 10; k++) {
            const a = (k / 10) * Math.PI * 2 + d.ang;
            ctx.beginPath();
            ctx.arc(p.x + Math.cos(a) * t * 22, p.y + Math.sin(a) * t * 22, 1.3, 0, Math.PI * 2);
            ctx.fill();
          }
        } else drawDot(ctx, p.x, p.y, r, d.c, Math.min(1, (now - d.born) / 0.3));
      }
    };
    void import('../../engine/miniRenderer').then((m) => {
      if (!alive || m.miniFailed()) return;
      off = m.register({
        canvas: c,
        visible: true,
        frame(dt) {
          scene.clock += dt;
          scene.tw.step(dt);
          stepCore(scene, dt, reduced);
          const now = scene.clock;
          // Ease each dot towards its evenly spaced slot; drop finished dissolves.
          const live = dots.current.filter((d) => d.died < 0);
          dots.current = dots.current.filter((d) => d.died < 0 || now - d.died <= LEAVE);
          live.forEach((d, k) => {
            const target = (k / Math.max(1, live.length)) * Math.PI * 2 + now * (reduced ? 0 : 0.18);
            let diff = target - d.ang;
            diff -= Math.round(diff / (Math.PI * 2)) * Math.PI * 2;
            d.ang += diff * Math.min(1, dt * 4);
          });
          const rp = scene.ripples;
          const ripples: number[] = [];
          for (let k = 0; k < rp.length; k += 4) ripples.push(rp[k], rp[k + 1], rp[k + 2], now - rp[k + 3]);
          const jd = scene.jellyDir;
          return {
            w: width,
            h: HEIGHT,
            ambient: {
              ph: ((now / 72) * Math.PI * 2) % (Math.PI * 2),
              center: [cx, cy],
              radius: R,
              halo: [pal[10], pal[11], pal[12]],
              haloAmt: 0.7 + 0.5 * scene.v.coreFlash,
              dustAmt: 1.3,
              dustCol: [0.75, 0.84, 1],
              pushDir: scene.dustPushDir,
              pushAmt: scene.v.dustPush * 0.6,
            },
            gem: {
              mesh: 'low',
              params: {
                cx, cy, R: R * scene.v.corePulse, rotY: 0, tiltX: 0.35, phase: reduced ? 0 : ((now / 18) * Math.PI * 2) % (Math.PI * 2),
                palette: pal, agent: null, alpha: 1, explode: 0, glow: 0, sx: 1, sy: 1, lowPower: false,
                rot: qToMat(scene.orient), ripples, squash: [jd[0], jd[1], jd[2], scene.v.jelly], flash: scene.v.coreFlash,
              },
            },
          };
        },
        before: (ctx) => drawDots(ctx, false),
        after: (ctx) => drawDots(ctx, true),
      });
    });
    return () => {
      alive = false;
      off();
    };
  }, [width, scene, pal, reduced]);

  const jelly = (e: MouseEvent<HTMLButtonElement>) => {
    const r = canvas.current?.getBoundingClientRect();
    const x = r && e.clientX ? e.clientX - r.left : width / 2;
    const y = r && e.clientY ? e.clientY - r.top : HEIGHT / 2;
    jellyAtGem(scene, width / 2, HEIGHT / 2, R, x, y, reduced);
  };

  return (
    <div ref={wrap} className="family-orbit" role="group" aria-label={`Your family: ${members.length} ${members.length === 1 ? 'member' : 'members'}`}>
      <div className="family-orbit__stage" style={{ width, height: HEIGHT }}>
        <canvas ref={canvas} style={{ width, height: HEIGHT }} aria-hidden />
        <button type="button" className="family-orbit__core" style={{ left: width / 2 - R - 14, top: HEIGHT / 2 - R - 14, width: (R + 14) * 2, height: (R + 14) * 2 }} onClick={jelly} aria-label="Family crystal. Click to wobble" />
      </div>
    </div>
  );
}
