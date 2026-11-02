// Waiting on you, right rail (MASTER_AGENT.md §7 Phase 3; FamilyOS.mp4 4:20,
// 4:30): To-dos · N open (a real checkbox, "by {date} · {owner} · on your
// calendar", the notice it came from), Worth doing (suggestions grounded in
// the data — nothing runs from here) and You will be told (notices that ask
// nothing). Ticking a to-do is a click and writes an audit row.
import { useState } from 'react';
import { Link } from 'react-router';
import clsx from 'clsx';
import { Check } from 'lucide-react';
import { colors } from '../../theme/tokens';
import { T } from '../../theme/typography';
import { useDesk } from '../../desk/store';
import type { Notice, Todo } from '../../desk/types';
import { DeskCard } from '../shell/DeskPage';
import { useDeskUI } from '../shell/useDeskUI';
import type { WorthItem } from './waitingModel';

const MAX_OPEN = 8;

interface TodoProps {
  open: Todo[];
  doneToday: Todo[];
  by: (t: Todo) => string;
  name: (id?: string) => string;
  text: (s: string) => string;
}

export function TodoCard({ open, doneToday, by, name, text }: TodoProps) {
  const [all, setAll] = useState(false);
  const shown = all ? open : open.slice(0, MAX_OPEN);
  return (
    <DeskCard title="To-dos" sub={`${open.length} open`} className="wt-todos">
      {open.length === 0 && doneToday.length === 0 ? <p className={T.small}>Nothing on the to-dos.</p> : null}
      <ul>
        {[...shown, ...doneToday].map((t) => (
          <TodoRow key={t.id} t={t} meta={`${by(t)} · ${name(t.ownerId)}${t.onCalendar ? ' · on your calendar' : ''}`} text={text} />
        ))}
      </ul>
      {open.length > MAX_OPEN ? (
        <button type="button" className="desk-link wt-more" aria-expanded={all} onClick={() => setAll((v) => !v)}>
          {all ? 'Show fewer' : `Show all ${open.length}`}
        </button>
      ) : null}
    </DeskCard>
  );
}

function TodoRow({ t, meta, text }: { t: Todo; meta: string; text: (s: string) => string }) {
  const toggle = useDesk((s) => s.toggleTodo);
  const flash = useDeskUI((s) => s.flash.includes(t.id));
  const title = text(t.title);
  const color = t.agent ? colors.agents[t.agent] : '#ffffff';
  return (
    <li className={clsx('wt-todo', t.done && 'is-done', flash && 'desk-flash')} data-desk-id={t.id} style={{ ['--desk-flash-color' as string]: color }}>
      <button type="button" role="checkbox" aria-checked={t.done} aria-label={`${title}: ${t.done ? 'done' : 'not done'}`} className="wt-todo__box" onClick={() => toggle(t.id)}>
        {t.done ? <Check size={12} strokeWidth={3} aria-hidden /> : null}
      </button>
      <span className="wt-todo__text">
        {t.noticeId ? (
          <Link to={`/inbox/${t.noticeId}`} className={clsx(T.smallStrong, 'wt-todo__title')}>
            {title}
          </Link>
        ) : (
          <span className={clsx(T.smallStrong, 'wt-todo__title')}>{title}</span>
        )}
        <span className={clsx(T.small, 'wt-todo__meta')}>{t.done ? 'done today' : meta}</span>
      </span>
    </li>
  );
}

export function WorthCard({ items, text }: { items: WorthItem[]; text: (s: string) => string }) {
  return (
    <DeskCard title="Worth doing" sub="suggestions" className="wt-worth">
      {items.length === 0 ? <p className={T.small}>Nothing to suggest right now.</p> : null}
      <ul>
        {items.map((w) => (
          <li key={w.id} className="wt-side-row">
            <Link to={w.to ?? `/inbox/${w.noticeId}`} className={T.smallStrong}>
              {text(w.title)}
            </Link>
            <span className={T.small}>
              {text(w.line)}
              {w.to && w.noticeId ? (
                <>
                  {' · '}
                  <Link to={`/inbox/${w.noticeId}`} className="wt-notice">
                    the notice
                  </Link>
                </>
              ) : null}
            </span>
          </li>
        ))}
      </ul>
    </DeskCard>
  );
}

export function ToldCard({ notices, ago, text }: { notices: Notice[]; ago: (i: string) => string; text: (s: string) => string }) {
  return (
    <DeskCard title="You will be told" sub="nothing to decide" className="wt-told">
      {notices.length === 0 ? <p className={T.small}>Nothing new that asks nothing.</p> : null}
      <ul>
        {notices.map((n) => (
          <li key={n.id} className="wt-side-row">
            <span className={clsx(T.small, 'wt-told__from')}>
              {n.sender} · {ago(n.receivedAt)}
            </span>
            <Link to={`/inbox/${n.id}`} className={T.smallStrong}>
              {text(n.title)}
            </Link>
            <span className={T.small}>{text(n.summary)}</span>
          </li>
        ))}
      </ul>
    </DeskCard>
  );
}
