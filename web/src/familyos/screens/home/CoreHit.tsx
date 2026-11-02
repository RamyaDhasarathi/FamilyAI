// Pointer and keyboard handling for the Home crystal (AGENT_CORE_AND_FAMILY.md
// §3.2 on mobile; AGENT_WEB.md §7.1). Handlers only queue input; the loop
// applies it once per frame.
//
//   click / tap ......... jelly wobble from the pointer (or stops a walkthrough)
//   drag ................ trackball rotation, the surface under the pointer follows
//   flick ............... momentum spin with friction, then back to the idle spin
//   press and hold ...... today's summary (mobile long-press)
//   Enter / Space ....... today's summary, or stop it
//   hover (mouse) ....... the gem tilts towards the cursor, up to 6°
//
// The hit area is the circle of radius R + 12 px over the crystal, following
// it as the Dashboard shrinks it.
//
// Desktop (`pressMode="navigate"`, MASTER_AGENT.md §7 Phase 1): a click —
// under 6 px and 500 ms, no wobble — or Enter / Space opens today's dashboard
// (`onOpen`); drag still spins and press-and-hold still plays the summary.
// A tooltip names what is happening today.
import { useRef, type KeyboardEvent, type PointerEvent } from 'react';
import clsx from 'clsx';
import { durations } from '../../theme/motion';
import { webCopy } from '../../mocks/webData';
import { MAX_SPIN } from '../../graphics/coreMotion';
import { gemAt } from '../../engine/orbitLayout';
import { beginDrag, endDrag, queueDrag, queueTap } from '../../engine/coreInput';
import { useEngine, useFrame } from './engineContext';

const HIT_MARGIN = 12;
const MAX_TILT = (6 * Math.PI) / 180;

interface Props {
  walking: boolean;
  onHold: () => void;
  onStop: () => void;
  /** 'navigate' on desktop: click / Enter calls onOpen instead of wobbling / playing. */
  pressMode?: 'summary' | 'navigate';
  onOpen?: () => void;
  /** Desktop tooltip (two lines) and accessible name. */
  tip?: { title: string; hint: string; label: string };
}

export function CoreHit({ walking, onHold, onStop, pressMode = 'summary', onOpen, tip }: Props) {
  const engine = useEngine();
  const el = useRef<HTMLButtonElement>(null);
  const tilt = useRef<[number, number]>([0, 0]);
  const p = useRef({ down: false, dragging: false, held: false, x: 0, y: 0, sx: 0, sy: 0, t: 0, t0: 0, vx: 0, vy: 0, id: -1 });
  const nav = pressMode === 'navigate' && !!onOpen;
  const holdTimer = useRef<number | null>(null);

  useFrame(engine, (e, dt) => {
    const b = el.current;
    if (!b) return;
    const g = gemAt(e.stage, e.scene.v.dashT);
    const hr = g.r + HIT_MARGIN;
    b.style.transform = `translate3d(${(g.x - hr).toFixed(1)}px, ${(g.y - hr).toFixed(1)}px, 0)`;
    b.style.width = b.style.height = `${(hr * 2).toFixed(1)}px`;
    b.style.visibility = e.scene.v.dashT > 0.98 ? 'hidden' : 'visible';
    // Ease the hover tilt (never stored in the orientation).
    const k = 1 - Math.exp(-dt * 8);
    const v = e.scene.v;
    if (Math.abs(tilt.current[0] - v.tiltX) > 1e-4 || Math.abs(tilt.current[1] - v.tiltY) > 1e-4) {
      e.scene.tw.set('tiltX', v.tiltX + (tilt.current[0] - v.tiltX) * k);
      e.scene.tw.set('tiltY', v.tiltY + (tilt.current[1] - v.tiltY) * k);
    }
  });

  const clearHold = () => {
    if (holdTimer.current) window.clearTimeout(holdTimer.current);
    holdTimer.current = null;
  };

  const down = (e: PointerEvent<HTMLButtonElement>) => {
    if (e.button !== 0) return;
    const s = p.current;
    Object.assign(s, { down: true, dragging: false, held: false, x: e.clientX, y: e.clientY, sx: e.clientX, sy: e.clientY, t: performance.now(), t0: performance.now(), vx: 0, vy: 0, id: e.pointerId });
    e.currentTarget.setPointerCapture(e.pointerId);
    tilt.current = [0, 0];
    if (!walking) {
      holdTimer.current = window.setTimeout(() => {
        if (!s.dragging) {
          s.held = true;
          onHold();
        }
      }, durations.hold + 20);
    }
  };

  const move = (e: PointerEvent<HTMLButtonElement>) => {
    const s = p.current;
    const scene = engine.scene;
    if (!s.down) {
      // Hover tilt towards the cursor (mouse only).
      if (e.pointerType !== 'mouse' || engine.reduced) return;
      const g = gemAt(engine.stage, scene.v.dashT);
      const nx = Math.max(-1, Math.min(1, (e.clientX - g.x) / g.r));
      const ny = Math.max(-1, Math.min(1, (e.clientY - g.y) / g.r));
      tilt.current = [ny * MAX_TILT, nx * MAX_TILT];
      engine.kick();
      return;
    }
    const now = performance.now();
    const dt = Math.max(1, now - s.t) / 1000;
    const dx = e.clientX - s.x;
    const dy = e.clientY - s.y;
    // Smoothed velocity in px/s for the flick.
    s.vx = s.vx * 0.6 + (dx / dt) * 0.4;
    s.vy = s.vy * 0.6 + (dy / dt) * 0.4;
    s.x = e.clientX;
    s.y = e.clientY;
    s.t = now;
    if (!s.dragging) {
      if (walking || s.held || Math.hypot(e.clientX - s.sx, e.clientY - s.sy) < 6) return;
      s.dragging = true;
      clearHold();
      beginDrag(scene);
    }
    queueDrag(scene, dx, dy, s.vx, s.vy, e.clientX - s.sx, e.clientY - s.sy);
    engine.kick();
  };

  const up = (e: PointerEvent<HTMLButtonElement>) => {
    const s = p.current;
    if (!s.down) return;
    s.down = false;
    clearHold();
    const scene = engine.scene;
    if (e.currentTarget.hasPointerCapture(s.id)) e.currentTarget.releasePointerCapture(s.id);
    if (s.dragging) {
      s.dragging = false;
      const stale = performance.now() - s.t > 80;
      endDrag(scene, stale ? 0 : s.vx, stale ? 0 : s.vy, gemAt(engine.stage, scene.v.dashT).r, MAX_SPIN, engine.reduced);
      return;
    }
    if (s.held || e.type === 'pointercancel') return;
    if (nav) {
      if (Math.hypot(e.clientX - s.sx, e.clientY - s.sy) < 6 && performance.now() - s.t0 < 500) onOpen!();
      return;
    }
    if (walking) onStop();
    else queueTap(scene, e.clientX, e.clientY);
    engine.kick();
  };

  const onKey = (e: KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      if (nav) onOpen!();
      else if (walking) onStop();
      else onHold();
    }
  };

  return (
    <button
      ref={el}
      type="button"
      className={clsx('core-hit', nav && 'core-hit--nav')}
      aria-label={nav && tip ? tip.label : walking ? webCopy.core.stopLabel : webCopy.core.label}
      aria-describedby={nav && tip ? 'core-tip' : undefined}
      onPointerDown={down}
      onPointerMove={move}
      onPointerUp={up}
      onPointerCancel={up}
      onPointerLeave={(e) => {
        if (e.pointerType === 'mouse' && !p.current.down) tilt.current = [0, 0];
      }}
      onKeyDown={onKey}
      onContextMenu={(e) => e.preventDefault()}
    >
      {nav && tip ? (
        <span id="core-tip" role="tooltip" className="core-hit__tip">
          <span className="t-small-strong">{tip.title}</span>
          <span className="sat__tip-hint">{tip.hint}</span>
        </span>
      ) : null}
    </button>
  );
}
