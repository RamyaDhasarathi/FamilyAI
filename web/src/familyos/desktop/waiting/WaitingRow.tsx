// Waiting on you, rows (MASTER_AGENT.md §7 Phase 3; FamilyOS.mp4 4:20–4:40):
// kind icon, title, "kind · Due … · for {person} · the notice", honest state
// lines, Accept (our white primary pill) and ✕. The missed card at the top
// lists what nobody decided before its date; there the only choice left is
// to let it go (✕). Nothing changes without a click; Undo is in the toast.
import { Link } from 'react-router';
import clsx from 'clsx';
import { Bell, CalendarDays, ListTodo, Receipt, ShoppingCart, X, type LucideIcon } from 'lucide-react';
import { colors } from '../../theme/tokens';
import { T } from '../../theme/typography';
import { PillButton } from '../../components/Pills';
import type { Proposal, ProposalKind } from '../../desk/types';
import { StatusChip } from '../shell/DeskPage';
import { useDeskUI } from '../shell/useDeskUI';
import { acceptWithUndo, dismissWithUndo } from './decide';
import './waiting.css';

const KIND_ICON: Record<ProposalKind, LucideIcon> = { task: ListTodo, calendar: CalendarDays, reminder: Bell, payment: Receipt, errand: ShoppingCart };

export function KindIcon({ kind, agent, size = 16 }: { kind: ProposalKind; agent: Proposal['agent']; size?: number }) {
  const Icon = KIND_ICON[kind];
  const c = colors.agents[agent];
  return (
    <span className="wt-icon" style={{ color: c, background: `color-mix(in srgb, ${c} 14%, transparent)` }} aria-hidden>
      <Icon size={size} strokeWidth={1.9} />
    </span>
  );
}

/** ✕ as an icon button with a real label (§8 aria-labels on icon buttons). */
export function DismissButton({ label, onClick, className }: { label: string; onClick: () => void; className?: string }) {
  return (
    <button type="button" className={clsx('wt-x', className)} aria-label={label} title={label} onClick={onClick}>
      <X size={15} strokeWidth={2.2} aria-hidden />
    </button>
  );
}

interface RowProps {
  p: Proposal;
  title: string;
  meta: string;
  person?: string;
  lines: string[];
}

export function WaitingRow({ p, title, meta, person, lines }: RowProps) {
  const flash = useDeskUI((s) => s.flash.includes(p.id));
  return (
    <li className={clsx('wt-row card', flash && 'desk-flash')} data-desk-id={p.id} style={{ ['--desk-flash-color' as string]: colors.agents[p.agent] }}>
      <KindIcon kind={p.kind} agent={p.agent} />
      <div className="wt-row__main">
        <p className={clsx(T.bodyStrong, 'wt-row__title')}>
          {title}
          {p.state === 'changed' ? <StatusChip tone="changed">Changed</StatusChip> : null}
        </p>
        <p className={clsx(T.small, 'wt-row__meta')}>
          {meta}
          {person ? ` · for ${person}` : ''} ·{' '}
          <Link to={`/inbox/${p.noticeId}`} className="wt-notice" aria-label={`The notice ${title} came from`}>
            the notice
          </Link>
        </p>
        {lines.map((l) => (
          <p key={l} className={clsx(T.small, 'wt-row__line')}>
            {l}
          </p>
        ))}
      </div>
      <div className="wt-row__actions">
        <PillButton label="Accept" variant="primary" aria-label={`Accept ${title}`} onClick={() => acceptWithUndo(p.id)} />
        <DismissButton label={`Dismiss ${title}`} onClick={() => dismissWithUndo(p.id)} />
      </div>
    </li>
  );
}

export interface MissedRow {
  p: Proposal;
  title: string;
  when: string;
}

export function MissedCard({ rows, more }: { rows: MissedRow[]; more: number }) {
  const shown = rows.slice(0, 4);
  return (
    <section className="wt-missed card" aria-labelledby="wt-missed-title">
      <div className="wt-missed__head">
        <h2 id="wt-missed-title" className={T.bodyStrong}>
          {rows.length === 1 ? 'One thing was missed' : `${rows.length} things were missed`}
        </h2>
        <span className={T.small}>nobody decided before the date</span>
      </div>
      <ul>
        {shown.map(({ p, title, when }) => (
          <li key={p.id} className="wt-missed__row" data-desk-id={p.id}>
            <KindIcon kind={p.kind} agent={p.agent} size={14} />
            <div className="wt-row__main">
              <p className={clsx(T.smallStrong, 'wt-row__title')}>
                {title} <StatusChip tone="missed">Missed</StatusChip>
              </p>
              <p className={clsx(T.small, 'wt-row__line')}>
                nobody accepted or dismissed this, and the date has gone · {when} ·{' '}
                <Link to={`/inbox/${p.noticeId}`} className="wt-notice" aria-label={`The notice ${title} came from`}>
                  the notice
                </Link>
              </p>
            </div>
            <DismissButton label={`Let “${title}” go (dismiss)`} onClick={() => dismissWithUndo(p.id)} />
          </li>
        ))}
      </ul>
      {rows.length > shown.length || more ? (
        <p className={clsx(T.small, 'wt-missed__more')}>
          {rows.length > shown.length ? `${rows.length - shown.length} more missed · ` : ''}
          {more ? `and ${more} more below` : ''}
        </p>
      ) : null}
    </section>
  );
}
