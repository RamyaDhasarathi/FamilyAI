// "WHAT I DID" entry (AGENT_WEB.md §8.7). Click expands in place: the height
// animates, the chevron rotates, key/value rows fade in with Undo and
// "Ask about this". Undone entries are struck through.
import { useId, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { ChevronDown } from 'lucide-react';
import clsx from 'clsx';
import type { TimelineEntry } from '../services/interfaces';
import { copy } from '../mocks/data';
import { GlowDot } from '../graphics/GlowDot';
import { colors } from '../theme/tokens';
import { T } from '../theme/typography';
import { useReducedMotion } from '../hooks/useReducedMotion';
import { PillButton } from './Pills';

interface Props {
  entry: TimelineEntry;
  color: string;
  undone: boolean;
  onUndo: () => void;
  onAsk: () => void;
}

export function TimelineItem({ entry, color, undone, onUndo, onAsk }: Props) {
  const [open, setOpen] = useState(false);
  const reduced = useReducedMotion();
  const panelId = useId();
  const canUndo = !!entry.undoable && !undone;
  return (
    <div className="timeline-item">
      <button
        type="button"
        className="timeline-item__head"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-controls={panelId}
      >
        <span className="timeline-item__meta">
          <span className="timeline-item__dot">
            <GlowDot color={undone ? colors.dim : color} size={7} />
          </span>
          <span className={clsx(T.small, 'timeline-item__when')}>{entry.when}</span>
          <span className={T.smallStrong} style={{ color, opacity: undone ? 0.5 : 1 }}>
            {undone ? copy.undone : canUndo ? copy.undo : copy.details}
          </span>
          {!canUndo && !undone ? (
            <motion.span className="timeline-item__chev" animate={{ rotate: open ? 180 : 0 }} transition={{ duration: 0.22 }} style={{ color }}>
              <ChevronDown size={13} aria-hidden />
            </motion.span>
          ) : null}
        </span>
        <span className={clsx(T.bodyStrong, 'timeline-item__title', undone && 'is-struck')}>{entry.title}</span>
        <span className={clsx(T.small, 'timeline-item__desc')}>{entry.description}</span>
      </button>
      <AnimatePresence initial={false}>
        {open ? (
          <motion.div
            id={panelId}
            key="rows"
            className="timeline-item__expanded"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: reduced ? 0.12 : 0.26, ease: [0.33, 1, 0.68, 1] }}
          >
            <dl className="timeline-item__rows">
              {entry.rows?.map(([k, v]) => (
                <div key={k} className="timeline-item__row">
                  <dt className={T.small}>{k}</dt>
                  <dd className={T.smallStrong}>{v}</dd>
                </div>
              ))}
            </dl>
            <div className="timeline-item__pills">
              {canUndo ? <PillButton label={copy.undo} variant="primary" onClick={onUndo} /> : null}
              <PillButton label={copy.askAboutThis} onClick={onAsk} />
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
