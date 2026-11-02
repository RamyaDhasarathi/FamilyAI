// Space template parts (MASTER_AGENT.md §7 Phase 4; FamilyOS.mp4 2:40–2:55
// and 9:30–10:40 School, 3:00 Travel, 3:40 Investments): the "Coming up"
// timeline (date · dot · space icon · title · honest state line), "What
// arrived" (source, time ago, person chips, "N to decide"), the Money ↔
// Investments tabs and the small "What this is" explainer card. Every row
// links to the notice it came from; nothing here changes anything.
import type { ReactNode } from 'react';
import { Link } from 'react-router';
import clsx from 'clsx';
import { colors } from '../../theme/tokens';
import { T } from '../../theme/typography';
import { Dot } from '../../components/Labels';
import { useDesk } from '../../desk/store';
import { useDeskFormat } from '../../desk/hooks';
import { memberName } from '../../desk/selectors';
import { DeskCard, StatusChip, type ChipTone } from '../shell/DeskPage';
import { useDeskUI } from '../shell/useDeskUI';
import { sourceLabel, type Arrival, type EntryTone, type TimelineEntry } from './spaceModel';
import { SOURCE_ICONS, SPACE_COLORS, SPACE_ICONS } from './spaceIcons';
import { extrasCopy, spaceCopy } from './copy';
import './spaces.css';

const C = spaceCopy;
const CHIP: Partial<Record<EntryTone, ChipTone>> = { missed: 'missed', overdue: 'overdue', changed: 'changed', clash: 'overdue', done: 'done' };

/** Coming up / This week: one row per dated thing, oldest first. */
export function Timeline({ entries, now, empty, label, max }: { entries: TimelineEntry[]; now: Date; empty: string; label: string; max?: number }) {
  const f = useDeskFormat(now);
  const flash = useDeskUI((s) => s.flash);
  if (!entries.length) return <p className={clsx(T.small, 'desk-empty')}>{empty}</p>;
  return (
    <ol className="sp-tl" aria-label={label}>
      {entries.slice(0, max).map((e) => {
        const space = e.spaceId ?? e.agent;
        const Icon = SPACE_ICONS[space];
        const color = colors.agents[e.agent];
        const tone = CHIP[e.tone];
        const inner = (
          <>
            <span className="sp-tl__when">
              <span className={T.smallStrong}>{f.day(e.day)}</span>
              <span className={clsx(T.small, 'sp-tl__slot')}>{e.slot}</span>
            </span>
            <Dot color={color} size={7} className="sp-tl__dot" style={{ boxShadow: `0 0 8px ${color}` }} />
            <span className="sp-icon" style={{ color: SPACE_COLORS[space] }} aria-hidden>
              <Icon size={14} strokeWidth={1.9} />
            </span>
            <span className="sp-tl__text">
              <span className={clsx(T.smallStrong, 'sp-tl__title', e.gone && 'is-gone')}>{f.text(e.title)}</span>
              <span className={clsx(T.small, 'sp-tl__line')}>
                {tone ? <StatusChip tone={tone}>{C.tone[e.tone]}</StatusChip> : null}
                <span>{e.line}</span>
              </span>
            </span>
          </>
        );
        return (
          <li key={e.id} data-desk-id={e.flashId} className={clsx('sp-tl__row', flash.includes(e.flashId) && 'desk-flash')} style={{ ['--desk-flash-color' as string]: color }}>
            {e.noticeId ? (
              <Link to={`/inbox/${e.noticeId}`} className="sp-row-link sp-tl__grid">
                {inner}
                <span className="sr-only">, opens the notice</span>
              </Link>
            ) : (
              <div className="sp-tl__grid">{inner}</div>
            )}
          </li>
        );
      })}
    </ol>
  );
}

/** What arrived: notices newest first, each opening its drawer at /inbox/:noticeId. */
export function WhatArrived({ items, now, empty, max, compact }: { items: Arrival[]; now: Date; empty: string; max?: number; compact?: boolean }) {
  const f = useDeskFormat(now);
  const members = useDesk((s) => s.members);
  if (!items.length) return <p className={clsx(T.small, 'desk-empty')}>{empty}</p>;
  return (
    <ul className={clsx('sp-arrived', compact && 'sp-arrived--compact')}>
      {items.slice(0, max).map(({ notice: n, toDecide }) => {
        const Icon = SOURCE_ICONS[n.source];
        return (
          <li key={n.id}>
            <Link to={`/inbox/${n.id}`} className="sp-row-link sp-arrived__row">
              <span className="sp-icon sp-icon--source" aria-hidden>
                <Icon size={15} strokeWidth={1.9} />
              </span>
              <span className="sp-arrived__text">
                <span className={clsx(T.small, 'sp-arrived__meta')}>
                  <span>
                    {sourceLabel(n)} · {f.ago(n.receivedAt)}
                  </span>
                  {(n.memberIds ?? []).map((id) => (
                    <StatusChip key={id} tone="neutral">
                      {memberName({ members }, id)}
                    </StatusChip>
                  ))}
                  {toDecide ? <StatusChip tone="proposed">{C.toDecide(toDecide)}</StatusChip> : null}
                  {n.attachments && !compact ? <span>· {C.attachments(n.attachments)}</span> : null}
                </span>
                <span className={clsx(T.smallStrong, 'sp-arrived__title')}>{f.text(n.title)}</span>
                {compact ? null : <span className={clsx(T.small, 'sp-arrived__sum')}>{f.text(n.summary)}</span>}
              </span>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

/** Money ↔ Investments: Investments is a sub-tab of Finance (§4). */
export function MoneyTabs({ current }: { current: 'money' | 'investments' }) {
  const tabs = [
    { id: 'money', to: '/agents/finance', label: extrasCopy.tabs.money },
    { id: 'investments', to: '/agents/finance/investments', label: extrasCopy.tabs.investments },
  ] as const;
  return (
    <nav className="sp-tabs" aria-label={extrasCopy.tabsLabel}>
      {tabs.map((t) => (
        <Link key={t.id} to={t.to} className={clsx('sp-tab', current === t.id && 'is-on')} aria-current={current === t.id ? 'page' : undefined}>
          {t.label}
        </Link>
      ))}
    </nav>
  );
}

/** A short "What this is" card: what the section is, and what it never does. */
export function Explainer({ title, children }: { title: string; children: ReactNode }) {
  return (
    <DeskCard title={title} className="sp-explain">
      <div className="sp-explain__body">{children}</div>
    </DeskCard>
  );
}

/** Section card with the space header pattern (title + small sub + optional action). */
export function Section({ title, sub, action, children, className }: { title: string; sub?: ReactNode; action?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <DeskCard title={title} sub={sub} action={action} className={clsx('sp-section', className)}>
      {children}
    </DeskCard>
  );
}

/** Dashboard extras layout: content column + right rail (≈300 px), like DeskPage. */
export function ExtrasLayout({ head, main, rail }: { head?: ReactNode; main: ReactNode; rail?: ReactNode }) {
  return (
    <>
      {head ? <div className="sp-x__head">{head}</div> : null}
      <div className={clsx('sp-x__body', rail ? 'sp-x__body--rail' : null)}>
        <div className="sp-x__main">{main}</div>
        {rail ? <div className="sp-x__rail">{rail}</div> : null}
      </div>
    </>
  );
}
