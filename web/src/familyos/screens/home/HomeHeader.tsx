// Home header (date, greeting, summary line, avatar pill) and status block
// (status label, headline, "+N more"). AGENT_WEB.md §8.1.1–8.1.4.
import { forwardRef, useRef } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { ChevronDown, ChevronRight } from 'lucide-react';
import clsx from 'clsx';
import type { Profile } from '../../services/interfaces';
import { copy } from '../../mocks/data';
import { T } from '../../theme/typography';
import { durations } from '../../theme/motion';
import { Dot, StatusLine } from '../../components/Labels';
import { Pressable } from '../../components/Pressable';
import { useFitText } from '../../hooks/useFitText';
import { formatLongDate, greetingFor } from '../homeText';

interface HeaderProps {
  profile: Profile;
  summaryWord: string;
  summaryDot: string;
  onSummary: () => void;
  onAvatar: () => void;
  avatarOpen: boolean;
  /** Dev-only scenario switcher: click and hold the date for 600 ms. */
  onDateHold?: () => void;
  /** Desktop passes false: no avatar pill (the sidebar has the profile). Default: shown. */
  showAvatar?: boolean;
  /** Desktop passes false: no "Today's summary" line (no right-side summary panel). Default: shown. */
  showSummary?: boolean;
}

export const HomeHeader = forwardRef<HTMLButtonElement, HeaderProps>(function HomeHeader(
  { profile, summaryWord, summaryDot, onSummary, onAvatar, avatarOpen, onDateHold, showAvatar = true, showSummary = true },
  avatarRef
) {
  const now = new Date();
  const greeting = greetingFor(now, profile.name);
  const greetRef = useRef<HTMLHeadingElement>(null);
  useFitText(greetRef, greeting);
  const hold = useRef<number | null>(null);
  const holdProps = onDateHold
    ? {
        onPointerDown: () => {
          hold.current = window.setTimeout(onDateHold, 600);
        },
        onPointerUp: () => hold.current && window.clearTimeout(hold.current),
        onPointerLeave: () => hold.current && window.clearTimeout(hold.current),
        title: 'Developer: hold to change the demo scenario (or Shift+S)',
      }
    : {};
  return (
    <header className="home-head">
      <div className="home-head__text">
        <p className={clsx(T.date, 'home-head__date')} {...holdProps}>
          {formatLongDate(now)}
        </p>
        <h1 ref={greetRef} className={clsx(T.greeting, 'home-head__greeting')}>
          {greeting}
        </h1>
        {showSummary ? (
          <Pressable className="home-head__summary" onClick={onSummary} pressScale={0.97} aria-label={`${copy.summaryPrefix}: ${summaryWord}. Opens today's summary`}>
            <Dot color={summaryDot} size={6} style={{ boxShadow: `0 0 8px ${summaryDot}`, transition: 'background-color 700ms' }} />
            <span className={T.summary}>{copy.summaryPrefix} · </span>
            <span className={T.summaryStrong}>{summaryWord}</span>
            <ChevronRight size={12} className="home-head__chev" aria-hidden />
          </Pressable>
        ) : null}
      </div>
      {showAvatar ? (
        <Pressable
          ref={avatarRef}
          className="avatar-pill"
          onClick={onAvatar}
          aria-label={`${profile.name}, open the profile menu`}
          aria-haspopup="dialog"
          aria-expanded={avatarOpen}
        >
          <span className="avatar-pill__circle t-chip">{profile.initial}</span>
          <ChevronDown size={14} className="avatar-pill__chev" aria-hidden />
        </Pressable>
      ) : null}
    </header>
  );
});

interface StatusProps {
  label: string;
  color: string;
  headline: string;
  calm: boolean;
  more?: string;
  onMore?: () => void;
  /** Label only (the single remaining item is shown as a card below it). */
  compact?: boolean;
}

export function StatusBlock({ label, color, headline, calm, more, onMore, compact }: StatusProps) {
  return (
    <section className="home-status" aria-label="Status">
      <StatusLine label={label} color={color} />
      {compact ? null : (
        <>
          <div className="home-status__headline" aria-live="polite">
            <AnimatePresence mode="popLayout" initial={false}>
              <motion.p
                key={headline}
                className={clsx(T.headline, 'home-status__text')}
                style={{ color: calm ? 'var(--muted)' : 'var(--ink-strong)' }}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, transition: { duration: 0.16 } }}
                transition={{ duration: durations.headline / 1000 }}
              >
                {headline}
              </motion.p>
            </AnimatePresence>
          </div>
          <div className="home-status__more">
            {more ? (
              <Pressable className="chip chip--small home-status__more-pill" onClick={onMore} aria-label={`${more}, open everything that needs you`}>
                {more}
              </Pressable>
            ) : null}
          </div>
        </>
      )}
    </section>
  );
}
