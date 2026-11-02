// Dashboard — "Your agents" (AGENT_WEB.md §8.3). Its position is driven by
// scene.v.dashT, the same value that shrinks the gem into the mini gem above
// it, so pointer, panel and gem move as one. Phone: a full-width sheet from
// 22 % of the height. Wider: a centred panel (max 960 px) under the mini gem,
// with the four small agents in a row of three on desktop.
import { useEffect, useRef } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { useDrag } from '@use-gesture/react';
import { ChevronRight } from 'lucide-react';
import clsx from 'clsx';
import type { AgentId } from '../../theme/tokens';
import { colors } from '../../theme/tokens';
import { T } from '../../theme/typography';
import { agentNames, copy } from '../../mocks/data';
import { summaryCount } from '../../mocks/scenarios';
import { useFamilyOS, useMood } from '../../store/useFamilyOS';
import { useWebUI } from '../../store/useWebUI';
import { useEscape } from '../../hooks/useEscape';
import { useFocusTrap } from '../../hooks/useFocusTrap';
import { useViewport } from '../../hooks/useBreakpoint';
import { settleDash } from '../../engine/coreInput';
import { AskBar } from '../../components/AskBar';
import { Badge, Dot, SectionLabel } from '../../components/Labels';
import { Pressable } from '../../components/Pressable';
import { SwipeCard } from '../../components/SwipeCard';
import { formatLongDate, greetingFor } from '../homeText';
import { agentBadges } from '../homeLogic';
import { useEngine, useFrame } from './engineContext';

interface Props {
  onOpenAgent: (agent: AgentId) => void;
  onOpenSummary: () => void;
  onAsk: () => void;
  onMic: () => void;
  listening: boolean;
}

function AgentCardView({ agent, status, badge, wide, onPress }: { agent: AgentId; status: string; badge?: { n: number; color: string }; wide?: boolean; onPress: () => void }) {
  return (
    <Pressable
      onClick={onPress}
      pressScale={0.97}
      className={clsx('dash-card card hoverable', wide && 'dash-card--wide')}
      aria-label={`${agentNames[agent]}: ${status}${badge ? `, ${badge.n} need you` : ''}`}
    >
      <span className="dash-card__head">
        <Dot color={colors.agents[agent]} size={7} style={{ boxShadow: `0 0 8px ${colors.agents[agent]}` }} />
        <span className={clsx(T.bodyStrong, 'dash-card__title')}>{agentNames[agent]}</span>
        {badge ? <Badge count={badge.n} color={badge.color} /> : null}
      </span>
      <span className={clsx(T.small, 'dash-card__status')}>{status}</span>
    </Pressable>
  );
}

export function DashboardPanel({ onOpenAgent, onOpenSummary, onAsk, onMic, listening }: Props) {
  const engine = useEngine();
  const { H } = useViewport();
  const panel = useRef<HTMLDivElement>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const open = useWebUI((s) => s.dashOpen);
  const setOpen = useWebUI((s) => s.setDashOpen);
  const profile = useFamilyOS((s) => s.profile);
  const cards = useFamilyOS((s) => s.dashboard);
  const needs = useFamilyOS((s) => s.needs);
  const resolve = useFamilyOS((s) => s.resolve);
  const snooze = useFamilyOS((s) => s.snooze);
  const mood = useMood();
  const top = engine.stage.dashTop;
  const travel = H - top;

  const close = () => {
    settleDash(engine.scene, false);
    engine.kick();
    setOpen(false);
  };
  useEscape(open, close);
  useFocusTrap(panel, open, { initial: panel });
  useEffect(() => {
    if (open) scroller.current?.scrollTo({ top: 0 });
  }, [open]);

  useFrame(engine, (e) => {
    const el = panel.current;
    if (!el) return;
    const t = Math.min(1, Math.max(0, e.scene.v.dashT));
    el.style.transform = `translate3d(0, ${((1 - t) * (e.stage.H - e.stage.dashTop)).toFixed(1)}px, 0)`;
    el.style.opacity = Math.min(1, t * 4).toFixed(3);
    el.style.visibility = t < 0.005 ? 'hidden' : 'visible';
  });

  // Drag the handle down to return Home (touch and pen).
  const bind = useDrag(
    ({ movement: [, my], velocity: [, vy], direction: [, dy], last, event }) => {
      if ((event as PointerEvent).pointerType === 'mouse') return;
      engine.scene.tw.set('dashT', Math.min(1, Math.max(0, 1 - my / travel)));
      engine.kick();
      if (!last) return;
      const shut = engine.scene.v.dashT < 0.7 || (vy > 0.7 && dy > 0);
      settleDash(engine.scene, !shut);
      setOpen(!shut);
    },
    { axis: 'y', filterTaps: true, pointer: { touch: true } }
  );

  if (!profile) return null;
  const { n, word } = summaryCount(needs);
  const badges = agentBadges(needs);
  const grid = cards.filter((c) => c.agent !== 'grocery');
  const grocery = cards.find((c) => c.agent === 'grocery');
  const summary = mood === 'calm' ? copy.summaryCardCalm : copy.summaryCardBusy(n, word);
  const now = new Date();
  return (
    <div
      ref={panel}
      className="dash glass glass--sheet tint-mood"
      style={{ top, ['--dash-h' as string]: `${travel}px`, visibility: 'hidden' }}
      role="dialog"
      aria-modal={open}
      aria-labelledby="dash-title"
      aria-hidden={!open}
      inert={!open}
      tabIndex={-1}
    >
      <div className="dash__grab" {...bind()}>
        <button type="button" className="dash__handle" onClick={close} aria-label="Back to Home (or drag down)">
          <span aria-hidden />
        </button>
        <p className={T.date}>{formatLongDate(now)}</p>
        <h2 id="dash-title" className={clsx(T.greeting, 'dash__greeting')}>
          {greetingFor(now, profile.name)}
        </h2>
      </div>
      <div ref={scroller} className="dash__body scroll-y" data-dash-scroller>
        <SectionLabel>{copy.yourAgents}</SectionLabel>
        <div className="dash__grid">
          {grid.map((c) => (
            <AgentCardView key={c.agent} agent={c.agent} status={c.status} badge={badges[c.agent]} onPress={() => onOpenAgent(c.agent)} />
          ))}
          {grocery ? <AgentCardView agent="grocery" status={grocery.status} badge={badges.grocery} wide onPress={() => onOpenAgent('grocery')} /> : null}
        </div>
        <Pressable onClick={onOpenSummary} pressScale={0.98} className="dash-summary card hoverable" aria-label={`${copy.todaysSummary}. ${summary}`}>
          <span className="dash-summary__text">
            <span className={T.bodyStrong} style={{ fontSize: '1.0625rem' }}>
              {copy.todaysSummary}
            </span>
            <span className={clsx(T.small, 'dash-card__status')}>{summary}</span>
          </span>
          <ChevronRight size={18} color={colors.muted} aria-hidden />
        </Pressable>
        {mood === 'urgent' ? (
          <section className="dash__needs" aria-label={copy.needsSection}>
            <div className="dash__needs-head">
              <span className={T.section}>{copy.needsSection}</span>
              <span className={T.section}>{copy.needsOpen(needs.length)}</span>
            </div>
            <AnimatePresence initial={false}>
              {needs.map((it) => (
                <motion.div key={it.id} layout exit={{ opacity: 0, height: 0, transition: { duration: 0.2 } }}>
                  <SwipeCard item={it} onDone={resolve} onLater={snooze} />
                </motion.div>
              ))}
            </AnimatePresence>
          </section>
        ) : null}
      </div>
      <div className="dash__ask">
        <AskBar placeholder={copy.askPlaceholder} icon="message" onPress={onAsk} onMic={onMic} listening={listening} />
      </div>
    </div>
  );
}
