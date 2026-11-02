// A plan's Bookings and To-dos (MASTER_AGENT.md §7 Phase 4 "Travel + Plans";
// FamilyOS.mp4 3:00–3:20). Bookings: option, provider, est. cost, the source
// snippet with its page, "watching · not read yet", Open to book ↗ (the
// provider's own page in a new tab — FamilyOS books nothing) and Booked (a
// person saying they booked it; audited, with Undo). To-dos: checkbox, due,
// owner, Add — the plan's to-dos live in the one store (todos with planId).
import { useMemo, useState, type FormEvent } from 'react';
import { Link } from 'react-router';
import clsx from 'clsx';
import { ArrowUpRight, Check } from 'lucide-react';
import { T } from '../../theme/typography';
import { useFamilyOS } from '../../store/useFamilyOS';
import { useDesk } from '../../desk/store';
import { useDeskFormat } from '../../desk/hooks';
import { fmtShortDay } from '../../desk/format';
import { memberName } from '../../desk/selectors';
import type { Booking, Plan } from '../../desk/types';
import { DeskCard } from '../shell/DeskPage';
import { useDeskUI } from '../shell/useDeskUI';
import { Section } from './SpaceParts';
import { hostOf, planTodoOrder } from './listModels';
import { planCopy, spaceCopy } from './copy';

const P = planCopy;

export function Bookings({ plan, now }: { plan: Plan; now: Date }) {
  const f = useDeskFormat(now);
  const toBook = plan.bookings.filter((b) => !b.booked);
  const booked = plan.bookings.filter((b) => b.booked);
  const sum = (xs: Booking[]) => f.money(xs.reduce((s, b) => s + b.estCost, 0));
  return (
    <Section title={P.bookings} sub={P.bookingsSub(booked.length, plan.bookings.length)} className="sp-bookings">
      {[
        { key: 'open', label: P.toBook(sum(toBook)), items: toBook },
        { key: 'booked', label: P.bookedGroup(sum(booked)), items: booked },
      ].map((g) =>
        g.items.length ? (
          <div key={g.key} className="sp-bookings__group">
            <p className={clsx(T.section, 'sp-group-label')}>{g.label}</p>
            <ul>
              {g.items.map((b) => (
                <BookingRow key={b.id} plan={plan} b={b} money={f.money} />
              ))}
            </ul>
          </div>
        ) : null
      )}
    </Section>
  );
}

function BookingRow({ plan, b, money }: { plan: Plan; b: Booking; money: (n: number) => string }) {
  const mark = useDesk((s) => s.markBooked);
  const flash = useDeskUI((s) => s.flash.includes(b.id));
  const toggle = () => {
    const next = !b.booked;
    mark(plan.id, b.id, next);
    useFamilyOS.getState().toast(next ? P.bookedToast(b.option) : P.unbookedToast(b.option), { action: { label: spaceCopy.undo, onPress: () => mark(plan.id, b.id, !next) }, duration: 5000 });
  };
  return (
    <li className={clsx('sp-booking', flash && 'desk-flash')} data-desk-id={b.id}>
      <div className="sp-booking__main">
        <p className="sp-booking__head">
          <span className={T.bodyStrong}>{b.option}</span>
          <span className={T.small}>
            {b.provider} · {P.est(money(b.estCost))}
          </span>
        </p>
        <blockquote className="sp-snippet">
          <a className="sp-snippet__src" href={b.sourceUrl} target="_blank" rel="noopener noreferrer">
            {P.source(hostOf(b.sourceUrl))}
          </a>
          <span className={T.small}>“{b.sourceSnippet}”</span>
        </blockquote>
        <p className={clsx(T.small, 'sp-booking__watch')}>
          {b.watch}
          {b.noticeId ? (
            <>
              {' · '}
              <Link to={`/inbox/${b.noticeId}`} className="desk-link">
                {spaceCopy.theNotice} ›
              </Link>
            </>
          ) : null}
        </p>
      </div>
      <div className="sp-booking__actions">
        <a className="pill pill--secondary sp-pill-sm" href={b.sourceUrl} target="_blank" rel="noopener noreferrer" aria-label={P.openToBookLabel(b.option, b.provider)}>
          {P.openToBook}
          <ArrowUpRight size={13} aria-hidden />
        </a>
        <button
          type="button"
          className={clsx('pill sp-pill-sm', b.booked ? 'pill--primary' : 'pill--secondary')}
          aria-pressed={b.booked}
          aria-label={P.bookedLabel(b.option, b.booked)}
          disabled={plan.status === 'dropped'}
          onClick={toggle}
        >
          {b.booked ? <Check size={13} strokeWidth={2.6} aria-hidden /> : null}
          {P.booked}
        </button>
      </div>
    </li>
  );
}

export function PlanTodos({ plan, now }: { plan: Plan; now: Date }) {
  const all = useDesk((s) => s.todos);
  const members = useDesk((s) => s.members);
  const actor = useDesk((s) => s.actor);
  const tz = useDesk((s) => s.settings.timezone);
  const toggle = useDesk((s) => s.toggleTodo);
  const add = useDesk((s) => s.addTodo);
  const flash = useDeskUI((s) => s.flash);
  const f = useDeskFormat(now);
  const [draft, setDraft] = useState('');
  const todos = useMemo(() => planTodoOrder(all.filter((t) => t.planId === plan.id), tz), [all, plan.id, tz]);
  const open = todos.filter((t) => !t.done).length;
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const title = draft.trim();
    if (!title) return;
    add({ title, ownerId: actor, planId: plan.id, noticeId: plan.noticeIds[0] });
    setDraft('');
    useFamilyOS.getState().toast(P.added(title));
  };
  return (
    <DeskCard title={P.todos} sub={P.todosSub(open)} className="sp-todos">
      {todos.length ? (
        <ul>
          {todos.map((t) => (
            <li key={t.id} className={clsx('sp-todo', flash.includes(t.id) && 'desk-flash')} data-desk-id={t.id}>
              <label className="sp-todo__label">
                <input type="checkbox" className="sp-check" checked={t.done} onChange={() => toggle(t.id)} />
                <span className="sp-todo__text">
                  <span className={clsx(T.smallStrong, t.done && 'is-done')}>{t.title}</span>
                  <span className={T.small}>
                    {t.due ? P.todoBy(f.day(t.due)) : P.noDate} · {memberName({ members }, t.ownerId)}
                  </span>
                </span>
              </label>
              {t.noticeId ? (
                <Link to={`/inbox/${t.noticeId}`} className="desk-link sp-todo__src" aria-label={`${spaceCopy.theNotice} for “${t.title}”`}>
                  {P.notice} ›
                </Link>
              ) : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className={T.small}>{P.todosEmpty}</p>
      )}
      <form className="sp-add" onSubmit={submit}>
        <input className="sp-input" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder={P.addPlaceholder} aria-label={P.addLabel} maxLength={140} />
        <button type="submit" className="pill pill--secondary sp-pill-sm" disabled={!draft.trim()}>
          {P.add}
        </button>
      </form>
    </DeskCard>
  );
}

/** "Day 1 · Nov 25" rows. */
export function Itinerary({ plan }: { plan: Plan }) {
  return (
    <Section title={P.itinerary} sub={spaceCopy.plural(plan.itinerary.length, 'day')}>
      <ol className="sp-itin">
        {plan.itinerary.map((d) => (
          <li key={d.day} className="sp-itin__row">
            <span className="sp-itin__day">
              <span className={T.smallStrong}>{P.day(d.day)}</span>
              <span className={T.small}>{fmtShortDay(d.date)}</span>
            </span>
            <span className="sp-itin__text">
              <span className={T.bodyStrong}>{d.title}</span>
              <span className={T.small}>{d.text}</span>
            </span>
          </li>
        ))}
      </ol>
    </Section>
  );
}
