// The gem at small sizes (Dashboard on wide screens, agent pages, Loading,
// Log in, placeholders; AGENT_WEB.md §7.1). Same geometry and shading as the
// Home core, its own clock, drawn by the shared mini renderer. three.js loads
// after first paint; until then (and if WebGL is missing) a soft glow and the
// stage-7 still stand in.
import { useEffect, useMemo, useRef, useState } from 'react';
import clsx from 'clsx';
import { paletteOf, type Scenario } from '../theme/stateThemes';
import { agentPalette } from '../graphics/miniPalette';
import { AVATAR_STAGES } from '../graphics/avatars';
import { loopPhase } from '../engine/orbitLayout';
import { useReducedMotion } from '../hooks/useReducedMotion';

interface Props {
  size: number;
  scenario?: Scenario;
  agentColor?: string;
  className?: string;
  /**
   * Light pages (log in, sign up, placeholders, 404) show a still of the
   * calm gem rendered by the same engine, floating gently, so they never
   * load three.js (AGENT_WEB.md §11.2).
   */
  still?: boolean;
}

const STILL_SRC = `${import.meta.env.BASE_URL}familyos/gem-still.webp`;

export function MiniGem({ still, ...props }: Props) {
  if (still) {
    return (
      <span className={clsx('mini-gem mini-gem--still', props.className)} style={{ width: props.size, height: props.size }} aria-hidden>
        <img src={STILL_SRC} alt="" width={props.size} height={props.size} decoding="async" />
      </span>
    );
  }
  return <LiveGem {...props} />;
}

function LiveGem({ size, scenario = 'calm', agentColor, className }: Omit<Props, 'still'>) {
  const ref = useRef<HTMLCanvasElement>(null);
  const reduced = useReducedMotion();
  const [state, setState] = useState<'loading' | 'ready' | 'failed'>('loading');
  const pal = useMemo(() => (agentColor ? agentPalette(agentColor) : paletteOf(scenario)), [agentColor, scenario]);
  const halo = `rgb(${Math.round(pal[10] * 255)},${Math.round(pal[11] * 255)},${Math.round(pal[12] * 255)})`;

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    let alive = true;
    let off = () => {};
    let io: IntersectionObserver | null = null;
    void import('../engine/miniRenderer').then((m) => {
      if (!alive) return;
      if (m.miniFailed()) {
        setState('failed');
        return;
      }
      let clock = 0;
      const R = size * 0.27;
      const inst = {
        canvas,
        visible: true,
        frame(dt: number) {
          if (!reduced) clock += dt;
          const ph = loopPhase(clock);
          return {
            w: size,
            h: size,
            ambient: { ph, center: [size / 2, size / 2] as [number, number], radius: R, halo: [pal[10], pal[11], pal[12]], haloAmt: 0.55, dustAmt: 1.2, dustCol: [0.75, 0.84, 1] },
            gem: {
              mesh: 'low' as const,
              params: { cx: size / 2, cy: size / 2, R, rotY: 4 * ph, tiltX: 0.35, phase: 4 * ph, palette: pal, agent: null, alpha: 1, explode: 0, glow: 0, sx: 1, sy: 1, lowPower: true },
            },
          };
        },
      };
      off = m.register(inst);
      io = new IntersectionObserver(([e]) => {
        inst.visible = e.isIntersecting;
      });
      io.observe(canvas);
      setState('ready');
    });
    return () => {
      alive = false;
      off();
      io?.disconnect();
    };
  }, [size, pal, reduced]);

  return (
    <span className={clsx('mini-gem', className)} style={{ width: size, height: size }} aria-hidden>
      {state !== 'ready' ? <span className="mini-gem__glow" style={{ background: `radial-gradient(circle, ${halo}66 0%, ${halo}22 38%, transparent 66%)` }} /> : null}
      {state === 'failed' ? <img className="mini-gem__still" src={AVATAR_STAGES[6].png} alt="" width={size} height={size} /> : null}
      <canvas ref={ref} style={{ width: size, height: size }} />
    </span>
  );
}
