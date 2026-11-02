// DOM layer for the five satellites (AGENT_WEB.md §7.3): an invisible 72 px
// button, the label and the badge for each, following the WebGL satellites'
// drift every frame (same orbitLayout maths, style writes only).
//   click / tap / Enter ........ that agent's walkthrough (mobile tap, video 0:26)
//   press and hold / Shift+Enter  open its Deep Layer page (mobile long-press)
//   hover ....................... satellite grows 1.12×, tooltip with its status
// Desktop (`pressMode="navigate"`, MASTER_AGENT.md §7 Phase 1): a click —
// under 6 px of movement and 500 ms — or Enter / Space opens the agent's
// dashboard instead; hold, Shift+Enter and hover stay the same.
import { useEffect, useRef, useState, type KeyboardEvent, type MouseEvent, type PointerEvent } from 'react';
import clsx from 'clsx';
import type { AgentId } from '../../theme/tokens';
import { AGENT_IDS } from '../../theme/tokens';
import { durations } from '../../theme/motion';
import { T } from '../../theme/typography';
import { agentNames } from '../../mocks/data';
import { webCopy } from '../../mocks/webData';
import { deskCopy } from '../../desktop/copy';
import type { AgentCard, NeedsItem } from '../../services/interfaces';
import { loopPhase, satellitePos, satelliteRadius } from '../../engine/orbitLayout';
import { setHover as setSatHover } from '../../engine/coreInput';
import { Badge } from '../../components/Labels';
import { agentBadges } from '../homeLogic';
import { useEngine, useFrame } from './engineContext';

const HIT = 72;

interface Props {
  needs: NeedsItem[];
  cards: AgentCard[];
  onTap: (agent: AgentId) => void;
  onOpen: (agent: AgentId, x: number, y: number) => void;
  /** 'navigate' on desktop: a click opens the dashboard (onTap) with its own hint and label. */
  pressMode?: 'summary' | 'navigate';
}

export function SatelliteLayer({ needs, cards, onTap, onOpen, pressMode = 'summary' }: Props) {
  const engine = useEngine();
  const els = useRef<(HTMLDivElement | null)[]>([]);
  const badges = agentBadges(needs);
  const [hover, setHover] = useState(-1);
  const [, force] = useState(0);
  // Re-render on resize so label offsets follow the satellite radius.
  useEffect(() => engine.subscribe(() => force((n) => n + 1)), [engine]);

  useFrame(engine, (e) => {
    const s = e.scene;
    const ph = s.still ? 0 : loopPhase(s.clock);
    const hl = s.satHighlight;
    for (let i = 0; i < 5; i++) {
      const el = els.current[i];
      if (!el) continue;
      const p = satellitePos(e.stage, i, ph);
      const pop = Math.min(1, Math.max(0, s.v.intro * 6 - i * 0.6 - 0.4));
      const a = (1 - s.v.dashT) * pop * (hl >= 0 && hl !== i ? 0.6 : 1);
      el.style.transform = `translate3d(${(p.x + s.parallax[0] - HIT / 2).toFixed(1)}px, ${(p.y + s.parallax[1] - HIT / 2).toFixed(1)}px, 0)`;
      el.style.opacity = a.toFixed(3);
      el.style.visibility = a < 0.02 ? 'hidden' : 'visible';
    }
  });

  const stage = engine.stage;
  const sr = satelliteRadius(stage);
  return (
    <div className="sat-layer">
      {AGENT_IDS.map((id, i) => (
        <Satellite
          key={id}
          id={id}
          i={i}
          sr={sr}
          labels={stage.labels}
          badge={badges[id]}
          status={cards.find((c) => c.agent === id)?.status}
          hovered={hover === i}
          navigate={pressMode === 'navigate'}
          setRef={(el) => (els.current[i] = el)}
          onHover={(h) => {
            setHover(h ? i : -1);
            setSatHover(engine.scene, h ? i : -1);
          }}
          onTap={() => onTap(id)}
          onOpen={() => {
            const p = satellitePos(engine.stage, i, engine.scene.still ? 0 : loopPhase(engine.scene.clock));
            onOpen(id, p.x, p.y);
          }}
        />
      ))}
    </div>
  );
}

interface SatProps {
  id: AgentId;
  i: number;
  sr: number;
  labels: boolean;
  badge?: { n: number; color: string };
  status?: string;
  hovered: boolean;
  navigate: boolean;
  setRef: (el: HTMLDivElement | null) => void;
  onHover: (h: boolean) => void;
  onTap: () => void;
  onOpen: () => void;
}

function Satellite({ id, sr, labels, badge, status, hovered, navigate, setRef, onHover, onTap, onOpen }: SatProps) {
  const hold = useRef<number | null>(null);
  const held = useRef(false);
  const press = useRef({ x: 0, y: 0, t: 0 });
  const [holding, setHolding] = useState(false);
  const name = agentNames[id];
  const clearHold = () => {
    if (hold.current) window.clearTimeout(hold.current);
    hold.current = null;
    setHolding(false);
  };
  const down = (e: PointerEvent) => {
    if (e.button !== 0) return;
    held.current = false;
    press.current = { x: e.clientX, y: e.clientY, t: performance.now() };
    setHolding(true);
    hold.current = window.setTimeout(() => {
      held.current = true;
      setHolding(false);
      onOpen();
    }, durations.hold);
  };
  const onKey = (e: KeyboardEvent) => {
    if (e.key === 'Enter' && e.shiftKey) {
      e.preventDefault();
      onOpen();
    }
  };
  const tipId = `sat-tip-${id}`;
  return (
    <div ref={setRef} className={clsx('sat', hovered && 'sat--hover', holding && 'sat--holding')} style={{ opacity: 0 }}>
      <button
        type="button"
        className="sat__hit"
        aria-label={navigate ? deskCopy.stones.open(id) : webCopy.satellite.a11y(name, badge?.n ?? 0)}
        aria-describedby={tipId}
        onPointerDown={down}
        onPointerUp={clearHold}
        onPointerCancel={clearHold}
        onPointerLeave={(e) => {
          clearHold();
          if (e.pointerType === 'mouse') onHover(false);
        }}
        onPointerEnter={(e) => e.pointerType === 'mouse' && onHover(true)}
        onFocus={() => onHover(true)}
        onBlur={() => onHover(false)}
        onKeyDown={onKey}
        onContextMenu={(e) => e.preventDefault()}
        onClick={(e: MouseEvent) => {
          if (held.current) {
            held.current = false;
            return;
          }
          // Desktop: only a short, still press counts as a click (keyboard clicks have detail 0).
          if (navigate && e.detail > 0) {
            const p = press.current;
            if (Math.hypot(e.clientX - p.x, e.clientY - p.y) >= 6 || performance.now() - p.t >= 500) return;
          }
          onTap();
        }}
      >
        <span className="sat__hold" style={{ width: sr * 2 + 14, height: sr * 2 + 14 }} aria-hidden />
      </button>
      {labels ? (
        <span className={clsx(T.satLabel, 'sat__label')} style={{ top: HIT / 2 + sr + 4 }} aria-hidden>
          {name}
        </span>
      ) : null}
      {badge ? (
        <span className="sat__badge" style={{ left: HIT / 2 + sr * 0.55, top: HIT / 2 - sr - 6 }} aria-hidden>
          <Badge count={badge.n} color={badge.color} />
        </span>
      ) : null}
      <span id={tipId} role="tooltip" className={clsx('sat__tip', id === 'finance' && 'sat__tip--below')} style={id === 'finance' ? { top: HIT / 2 + sr + 22 } : { bottom: HIT / 2 + sr + 10 }}>
        <span className="t-small-strong">
          {name}
          {status ? ` · ${status}` : ''}
        </span>
        <span className="sat__tip-hint">{navigate ? deskCopy.stones.hint : webCopy.satellite.hint}</span>
      </span>
    </div>
  );
}
