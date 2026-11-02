// Needs-you card (AGENT_WEB.md §8.4).
//   Touch: swipe right = Done (green), swipe left = Later (amber), release
//          past 35 % of the width.
//   Mouse: the white pill completes with that action, "Later" snoozes; hover
//          reveals the green / amber hints on the card edges.
//   Keyboard: the card is focusable; Enter = main action, L = Later (J / K
//          move between cards, handled by the list).
// A small pill confirms, then the row collapses.
import { useRef, useState, type KeyboardEvent } from 'react';
import { animate, motion, useMotionValue, useTransform } from 'framer-motion';
import { useDrag } from '@use-gesture/react';
import clsx from 'clsx';
import type { NeedsItem } from '../services/interfaces';
import { agentNames, copy } from '../mocks/data';
import { colors } from '../theme/tokens';
import { fm } from '../theme/motion';
import { T } from '../theme/typography';
import { KeyHint, MetaRow } from './Labels';
import { PillButton } from './Pills';

const SEVERITY_WORD = { urgent: 'URGENT', headsup: 'HEADS-UP', insight: 'INSIGHT' } as const;

interface Props {
  item: NeedsItem;
  onDone: (id: string) => void;
  onLater: (id: string) => void;
  /** Show J/K/Enter/L hints (desktop list). */
  hints?: boolean;
}

export function SwipeCard({ item, onDone, onLater, hints }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const x = useMotionValue(0);
  const [result, setResult] = useState<'done' | 'later' | null>(null);
  const sev = colors.severity[item.severity];
  const width = () => ref.current?.offsetWidth ?? 320;
  const green = useTransform(x, (v) => Math.min(0.55, Math.max(0, v / (width() * 0.4)) * 0.55));
  const amber = useTransform(x, (v) => Math.min(0.55, Math.max(0, -v / (width() * 0.4)) * 0.55));
  const doneBg = useTransform(x, (v) => (v > 2 ? 1 : 0));
  const laterBg = useTransform(x, (v) => (v < -2 ? 1 : 0));

  const finish = (kind: 'done' | 'later') => {
    setResult(kind);
    setTimeout(() => (kind === 'done' ? onDone(item.id) : onLater(item.id)), 650);
  };
  const fling = (dir: 1 | -1) => {
    if (result) return;
    void animate(x, dir * width() * 1.15, { duration: 0.24, ease: [0.33, 1, 0.68, 1] }).then(() => finish(dir === 1 ? 'done' : 'later'));
  };

  const bind = useDrag(
    ({ movement: [mx], velocity: [vx], direction: [dx], last, event }) => {
      if ((event as PointerEvent).pointerType === 'mouse' || result) return;
      if (!last) {
        x.set(mx);
        return;
      }
      const projected = mx + vx * dx * 80;
      const W = width();
      if (projected > W * 0.35) fling(1);
      else if (projected < -W * 0.35) fling(-1);
      else animate(x, 0, fm.snappy);
    },
    { axis: 'x', filterTaps: true, pointer: { touch: true } }
  );

  const onKey = (e: KeyboardEvent) => {
    if (e.target !== e.currentTarget) return;
    if (e.key === 'Enter') {
      e.preventDefault();
      fling(1);
    } else if (e.key === 'l' || e.key === 'L') {
      e.preventDefault();
      fling(-1);
    }
  };

  if (result) {
    return (
      <motion.div className="swipe-result" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.15 }} role="status">
        <span className="swipe-result__pill">{result === 'done' ? copy.done : copy.snoozed}</span>
      </motion.div>
    );
  }

  const label = `${agentNames[item.agent].toUpperCase()} · ${SEVERITY_WORD[item.severity]}`;
  return (
    <div className="swipe-wrap" ref={ref}>
      <motion.div className="swipe-reveal swipe-reveal--done" style={{ opacity: doneBg }} aria-hidden>
        <span className={T.meta}>{copy.doneSwipe}</span>
      </motion.div>
      <motion.div className="swipe-reveal swipe-reveal--later" style={{ opacity: laterBg }} aria-hidden>
        <span className={T.meta}>{copy.laterSwipe}</span>
      </motion.div>
      <motion.div
        {...(bind() as object)}
        className="swipe-card"
        style={{ x, touchAction: 'pan-y' }}
        tabIndex={0}
        role="group"
        aria-label={`${label}. ${item.text}. Enter: ${item.action.label}. L: ${copy.later}.`}
        onKeyDown={onKey}
        data-swipe-card
      >
        <motion.span className="swipe-card__tint" style={{ background: colors.done, opacity: green }} aria-hidden />
        <motion.span className="swipe-card__tint" style={{ background: colors.later, opacity: amber }} aria-hidden />
        <span className="swipe-card__hint swipe-card__hint--done" aria-hidden />
        <span className="swipe-card__hint swipe-card__hint--later" aria-hidden />
        <span className="swipe-card__accent" style={{ background: sev, boxShadow: `0 0 8px ${sev}` }} aria-hidden />
        <div className="swipe-card__body">
          <MetaRow left={label} right={item.time} />
          <p className={clsx(T.body, 'swipe-card__text')}>{item.text}</p>
          <div className="swipe-card__actions">
            <PillButton label={item.action.label} variant="primary" onClick={() => fling(1)} />
            <PillButton label={copy.later} onClick={() => fling(-1)} />
            {hints ? <KeyHint keys={['↵', 'L']} className="swipe-card__keys" /> : null}
          </div>
        </div>
      </motion.div>
    </div>
  );
}
