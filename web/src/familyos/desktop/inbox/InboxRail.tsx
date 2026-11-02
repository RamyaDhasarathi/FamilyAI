// Inbox, right rail (MASTER_AGENT.md §7 Phase 3; FamilyOS.mp4 3:50–4:20,
// frames f_051, f_114): "Dates spotted · N to decide" — date, title, what it
// is and for whom, ✓ accept / ✕ dismiss (each a click, each with Undo) — and
// "Handling · open notices" per person who can handle them, plus "Nobody
// yet". Picking a person filters the list to their open notices.
import { Link } from 'react-router';
import clsx from 'clsx';
import { Check } from 'lucide-react';
import { T } from '../../theme/typography';
import type { Proposal } from '../../desk/types';
import { DeskCard } from '../shell/DeskPage';
import { useDeskUI } from '../shell/useDeskUI';
import { DismissButton } from '../waiting/WaitingRow';
import { acceptWithUndo, dismissWithUndo } from '../waiting/decide';
import type { HandlingRow } from './inboxModel';

interface SpottedProps {
  items: Proposal[];
  text: (s: string) => string;
  day: (w: string) => string;
  slot: (w: string, k?: Proposal['dueKind']) => string;
  line: (p: Proposal) => string;
}

export function DatesSpotted({ items, text, day, slot, line }: SpottedProps) {
  const flash = useDeskUI((s) => s.flash);
  return (
    <DeskCard title="Dates spotted" sub={`${items.length} to decide`} className="ib-spotted">
      {items.length === 0 ? <p className={T.small}>Every date the family received has been decided.</p> : null}
      <ul>
        {items.map((p) => {
          const title = text(p.title);
          const s = p.due ? slot(p.due, p.dueKind) : '';
          return (
            <li key={p.id} className={clsx('ib-spot', flash.includes(p.id) && 'desk-flash')} data-desk-id={p.id}>
              <span className="ib-spot__date">
                <span className={T.smallStrong}>{p.due ? day(p.due) : '—'}</span>
                <span className={T.small}>{p.due ? (s === 'all day' ? '' : s) : 'no date'}</span>
              </span>
              <span className="ib-spot__text">
                <Link to={`/inbox/${p.noticeId}`} className={clsx(T.smallStrong, 'ib-spot__title')}>
                  {title}
                </Link>
                <span className={clsx(T.small, 'ib-spot__sub')}>{line(p)}</span>
              </span>
              <span className="ib-spot__actions">
                <button type="button" className="wt-x ib-ok" aria-label={`Accept ${title}`} title={`Accept ${title}`} onClick={() => acceptWithUndo(p.id)}>
                  <Check size={15} strokeWidth={2.4} aria-hidden />
                </button>
                <DismissButton label={`Dismiss ${title}`} onClick={() => dismissWithUndo(p.id)} />
              </span>
            </li>
          );
        })}
      </ul>
    </DeskCard>
  );
}

export function Handling({ rows, who, onPick }: { rows: HandlingRow[]; who: string | null; onPick: (id: string | null) => void }) {
  return (
    <DeskCard title="Handling" sub="open notices" className="ib-handling">
      <ul className="ib-hand">
        {rows.map((r) => {
          const key = r.id ?? 'nobody';
          const on = who === key;
          return (
            <li key={key}>
              <button
                type="button"
                className={clsx('ib-hand__row', on && 'is-on')}
                aria-pressed={on}
                aria-label={`${r.name}: ${r.count} open ${r.count === 1 ? 'notice' : 'notices'}. ${on ? 'Showing them; press to show everyone' : 'Show only these'}`}
                onClick={() => onPick(on ? null : key)}
              >
                <span className={clsx('ib-hand__avatar', !r.id && 'is-nobody')} aria-hidden>
                  {r.initial}
                </span>
                <span className={clsx(T.smallStrong, 'ib-hand__name')}>{r.name}</span>
                <span className={clsx(T.smallStrong, 'ib-hand__count')}>{r.count}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </DeskCard>
  );
}
