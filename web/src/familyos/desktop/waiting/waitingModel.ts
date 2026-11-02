// Waiting on you, the logic (MASTER_AGENT.md §7 Phase 3, §3.3.3 "Honest state
// lines", §10; FamilyOS.mp4 4:20–4:40): the due text and state lines under
// each row, clashes ("clashes with X — move one?"), and the right rail's
// To-dos, Worth doing and You will be told. Pure functions of (data, now, tz).
import type { AgendaItem, DeskData, Day, Instant, Proposal, Todo, When } from '../../desk/types';
import { addDays, dayKey, dayOf, fmtRelDay, fmtSlot, isDay } from '../../desk/format';
import { dateGone, isMissed, isUndecided } from '../../desk/selectors';

const HOUR = 3600000;
const timedWhen = (w: When | undefined, k?: string): w is Instant => !!w && !isDay(w) && (k === 'time' || k === undefined);

/** "Due Today · EOD", "Due Friday", "Due Tomorrow · 2 pm", "No date". */
export function dueText(p: { due?: When; dueKind?: Proposal['dueKind'] }, tz: string, today: Day): string {
  if (!p.due) return 'No date';
  const day = fmtRelDay(dayOf(p.due, tz), today);
  const slot = fmtSlot(p.due, p.dueKind, tz);
  return slot === 'all day' ? `Due ${day}` : `Due ${day} · ${slot}`;
}

/** "Due Friday" → "by Friday" for to-dos; overdue ones say when they were due. */
export function byText(t: Pick<Todo, 'due' | 'dueKind'>, now: Date, tz: string): string {
  if (!t.due) return 'no date';
  const today = dayKey(now, tz);
  const day = fmtRelDay(dayOf(t.due, tz), today);
  const slot = fmtSlot(t.due, t.dueKind, tz);
  const when = slot === 'all day' ? day : `${day} ${slot}`;
  return dateGone(t, now, tz) ? `was due ${/^(Today|Tomorrow|Yesterday)$/.test(day) ? when.toLowerCase() : when}` : `by ${when}`;
}

// ── Clashes ───────────────────────────────────────────────────────────

export interface Clash {
  proposalId: string;
  /** Titles of what it clashes with (the first is named; "and more" for the rest). */
  others: { id: string; title: string; noticeId?: string }[];
  /** Same-day deadlines ("Friday is tight") rather than overlapping times. */
  sameDay: boolean;
  day: Day;
}

interface Slot {
  id: string;
  title: string;
  people: string[];
  noticeId?: string;
  timed: boolean;
  start: number;
  end: number;
  day: Day;
  /** Something to do by a date (a task or to-do), not an event at a time. */
  deadline: boolean;
}

const share = (a: string[], b: string[]) => a.some((x) => b.includes(x));

function agendaSlot(a: AgendaItem, tz: string): Slot | null {
  if (a.kind === 'reminder' || a.kind === 'update' || a.done) return null;
  const t = timedWhen(a.when, a.dueKind);
  const start = t ? new Date(a.when).getTime() : 0;
  return { id: a.id, title: a.title, people: a.memberIds ?? [], noticeId: a.noticeId, timed: t, start, end: t ? (a.end ? new Date(a.end).getTime() : start + HOUR) : 0, day: dayOf(a.when, tz), deadline: false };
}

/**
 * An undecided proposal clashes when it overlaps a timed event or another
 * undecided proposal for the same person, or — for things due by a date —
 * when the same person has another task or to-do due that day.
 */
export function findClashes(d: Pick<DeskData, 'proposals' | 'agenda' | 'todos'>, now: Date, tz: string): Map<string, Clash> {
  const forOf = new Map(d.proposals.map((p) => [p.id, p.forMemberId]));
  const slots: Slot[] = [];
  for (const a of d.agenda) {
    const s = agendaSlot(a, tz);
    if (s) slots.push(s);
  }
  for (const t of d.todos) {
    if (t.done || !t.due) continue;
    const people = [t.ownerId, t.proposalId ? forOf.get(t.proposalId) : undefined].filter((x): x is string => !!x);
    slots.push({ id: t.id, title: t.title, people, noticeId: t.noticeId, timed: false, start: 0, end: 0, day: dayOf(t.due, tz), deadline: true });
  }
  const open = d.proposals.filter((p) => isUndecided(p) && p.due && !isMissed(p, now, tz) && !dateGone(p, now, tz));
  for (const p of open) {
    const t = timedWhen(p.due, p.dueKind);
    const start = t ? new Date(p.due!).getTime() : 0;
    slots.push({ id: p.id, title: p.title, people: p.forMemberId ? [p.forMemberId] : [], noticeId: p.noticeId, timed: t, start, end: start + HOUR, day: dayOf(p.due!, tz), deadline: p.kind === 'task' || p.kind === 'payment' });
  }
  const out = new Map<string, Clash>();
  for (const p of open) {
    const me = slots.find((s) => s.id === p.id)!;
    if (!me.people.length) continue;
    const skip = new Set([p.id, p.created?.agendaId, p.created?.todoId]);
    const hits = slots.filter((o) => {
      if (skip.has(o.id) || !share(me.people, o.people)) return false;
      if (me.timed && o.timed) return o.start < me.end && me.start < o.end;
      return !me.timed && me.deadline && o.deadline && !o.timed && o.day === me.day;
    });
    if (hits.length) out.set(p.id, { proposalId: p.id, others: hits.map((h) => ({ id: h.id, title: h.title, noticeId: h.noticeId })), sameDay: !me.timed, day: me.day });
  }
  return out;
}

/** "clashes with X — move one?" / "Friday is tight: clashes with X and more — move one?" */
export function clashLine(c: Clash, today: Day): string {
  const names = `${c.others[0].title}${c.others.length > 1 ? ' and more' : ''}`;
  return c.sameDay ? `${fmtRelDay(c.day, today)} is tight: clashes with ${names} — move one?` : `clashes with ${names} — move one?`;
}

/** The honest state lines under a row (worst first). */
export function stateLines(p: Proposal, now: Date, tz: string, clash?: Clash): string[] {
  const lines: string[] = [];
  const today = dayKey(now, tz);
  if (isMissed(p, now, tz)) lines.push('nobody accepted or dismissed this, and the date has gone');
  else if (p.state === 'changed') {
    const was = p.changedFrom?.due ? fmtSlot(p.changedFrom.due, p.changedFrom.dueKind, tz) : 'before';
    lines.push(`the notice changed after it was accepted: was ${was}, now ${p.due ? fmtSlot(p.due, p.dueKind, tz) : 'no date'}`);
  } else if (dateGone(p, now, tz)) lines.push('nobody has accepted this yet, and the date has gone');
  if (clash) lines.push(clashLine(clash, today));
  if (p.kind === 'payment') lines.push('a reminder, nothing here pays');
  return lines;
}

// ── Right rail ────────────────────────────────────────────────────────

const dueSort = (tz: string) => (a: Todo, b: Todo) => {
  if (!a.due !== !b.due) return a.due ? -1 : 1;
  if (!a.due || !b.due) return a.title.localeCompare(b.title);
  return dayOf(a.due, tz).localeCompare(dayOf(b.due, tz)) || a.title.localeCompare(b.title);
};

/** Open to-dos by date (no date last), then the ones ticked today so a tick can be undone in place. */
export function todoRail(d: Pick<DeskData, 'todos'>, now: Date, tz: string): { open: Todo[]; doneToday: Todo[] } {
  const today = dayKey(now, tz);
  const open = d.todos.filter((t) => !t.done).sort(dueSort(tz));
  const doneToday = d.todos.filter((t) => t.done && t.doneAt && dayKey(t.doneAt, tz) === today);
  return { open, doneToday };
}

export interface WorthItem {
  id: string;
  title: string;
  line: string;
  noticeId?: string;
  /** A page to open instead of the notice (a plan). */
  to?: string;
}

/**
 * Worth doing: suggestions grounded in the data, never actions. A
 * subscription that charges again within 10 days ("still used?"), and a
 * watched booking page that changed and nobody read yet.
 */
export function worthDoing(d: Pick<DeskData, 'recurring' | 'plans'>, now: Date, tz: string): WorthItem[] {
  const today = dayKey(now, tz);
  const soon = addDays(today, 10);
  const out: WorthItem[] = [];
  for (const r of [...d.recurring].sort((a, b) => a.next.localeCompare(b.next))) {
    if (r.kind !== 'subscription' || r.next < today || r.next > soon) continue;
    out.push({ id: r.id, title: `Check you still use ${r.merchant}`, line: `charges ¤{${r.amount}} again ${fmtRelDay(r.next, today) === 'Tomorrow' ? 'tomorrow' : `on ${fmtRelDay(r.next, today)}`}`, noticeId: r.noticeId });
  }
  for (const p of d.plans) {
    if (p.status !== 'draft') continue;
    for (const b of p.bookings) {
      if (b.booked || b.watch !== 'watching · not read yet') continue;
      out.push({ id: b.id, title: `Look at the new ${b.provider} page`, line: `${p.title} · ${b.option}, about ¤{${b.estCost}} · changed, not read yet`, noticeId: b.noticeId, to: `/plans/${p.id}` });
    }
  }
  return out;
}

/** You will be told: recent notices that ask nothing of anyone (no proposals), newest first. */
export function toldItems(d: Pick<DeskData, 'notices' | 'proposals'>, now: Date, max = 5) {
  const asked = new Set(d.proposals.map((p) => p.noticeId));
  const since = now.getTime() - 14 * 24 * HOUR;
  return d.notices
    .filter((n) => !n.quarantined && !asked.has(n.id) && !['promo', 'newsletter', 'receipt'].includes(n.category) && new Date(n.receivedAt).getTime() >= since)
    .sort((a, b) => b.receivedAt.localeCompare(a.receivedAt))
    .slice(0, max);
}
