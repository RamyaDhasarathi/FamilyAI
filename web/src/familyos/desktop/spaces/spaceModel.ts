// Space template model (MASTER_AGENT.md §7 Phase 4, §3.2 2:20 Our family,
// 2:40–2:55 / 9:30–10:40 School, 3:00–3:20 Travel + Plan, 3:30 Money, 3:40
// Investments; §10 state lines). Pure functions of (data, scope, now, tz):
// nothing is copied, every view follows the one desk store, and every row
// keeps its noticeId / proposalId back-link.
import type { AgendaItem, AgentId, DeskData, Day, DueKind, Notice, Proposal, RecurringMerchant, SpaceId, Todo, When } from '../../desk/types';
import { addDays, dayKey, dayOf, fmtSlot, isDay, zoned } from '../../desk/format';
import { dateGone, isMissed, isUndecided, memberName, TIE_ORDER, toDecide } from '../../desk/selectors';

/** A space, or the whole family (Our family, Calendar, Finance). */
export type Scope = SpaceId | 'all';
const inScope = (scope: Scope, s?: SpaceId) => scope === 'all' || s === scope;
/** A plan's to-dos belong to Travel even when they carry no spaceId. */
const todoSpace = (t: Todo): SpaceId | undefined => t.spaceId ?? (t.planId ? 'travel' : undefined);

// ── Coming up / This week: one timeline with honest state lines ─────────

export type EntryTone = 'missed' | 'overdue' | 'changed' | 'clash' | 'proposed' | 'accepted' | 'scheduled' | 'gone' | 'done';

export interface TimelineEntry {
  /** Stable key (the proposal id, else the agenda / to-do id). */
  id: string;
  /** The record "Show me" can highlight (`data-desk-id`). */
  flashId: string;
  day: Day;
  slot: string;
  timed: boolean;
  sortMs: number;
  title: string;
  agent: AgentId;
  spaceId?: SpaceId;
  kind: Proposal['kind'] | AgendaItem['kind'] | 'todo';
  tone: EntryTone;
  /** MASTER §10: "the family accepted this, and the date has gone" … */
  line: string;
  gone: boolean;
  memberIds: string[];
  noticeId?: string;
  proposalId?: string;
}

/** Days around today to show: `from` (≤ 0, the recent past) to `to`. */
export interface Window {
  from: number;
  to: number;
}

type TimelineData = Pick<DeskData, 'proposals' | 'agenda' | 'todos' | 'conflicts' | 'members'>;

/** Sort key in real time: a timed When → its instant; a Day → its local start (EOD → 23:59). */
export function whenMs(w: When, kind: DueKind | undefined, tz: string): number {
  if (!isDay(w) && (kind === 'time' || kind === undefined)) return new Date(w).getTime();
  const day = dayOf(w, tz);
  return new Date(kind === 'eod' ? zoned(day, 23, 59, tz) : zoned(day, 0, 0, tz)).getTime();
}

const AGENDA_LINE: Record<AgendaItem['kind'], string> = {
  event: 'on the calendar', visit: 'a visit, on the calendar', delivery: 'a delivery', bill: 'a bill', update: 'an update', reminder: 'a reminder',
};

/**
 * Every dated thing in a space between today+from and today+to, oldest first:
 * proposals (with what accepting them created), plus calendar items and
 * to-dos that no proposal created. Each carries one honest state line.
 */
export function spaceTimeline(d: TimelineData, scope: Scope, now: Date, tz: string, win: Window = { from: -7, to: 60 }): TimelineEntry[] {
  const today = dayKey(now, tz);
  const first = addDays(today, win.from);
  const last = addDays(today, win.to);
  const names = (ids: string[]) => ids.map((id) => memberName(d, id)).filter(Boolean).join(', ');
  const agendaById = new Map(d.agenda.map((a) => [a.id, a]));
  const todoById = new Map(d.todos.map((t) => [t.id, t]));
  const proposalIds = new Set(d.proposals.map((p) => p.id));
  const linked = new Set<string>();
  for (const p of d.proposals) {
    if (p.created?.agendaId) linked.add(p.created.agendaId);
    if (p.created?.todoId) linked.add(p.created.todoId);
  }
  const clashWith = (agendaId: string) => {
    const c = d.conflicts.find((x) => !x.resolvedAt && (x.aId === agendaId || x.bId === agendaId));
    return c ? agendaById.get(c.aId === agendaId ? c.bId : c.aId)?.title : undefined;
  };
  const out: TimelineEntry[] = [];
  const push = (base: Omit<TimelineEntry, 'day' | 'slot' | 'timed' | 'sortMs' | 'gone' | 'tone' | 'line'>, when: When, kind: DueKind | undefined, state: (gone: boolean) => [EntryTone, string]) => {
    const day = dayOf(when, tz);
    if (day < first || day > last) return;
    const gone = dateGone({ due: when, dueKind: kind }, now, tz);
    const [tone, line] = state(gone);
    out.push({ ...base, day, slot: fmtSlot(when, kind, tz), timed: !isDay(when) && (kind === 'time' || kind === undefined), sortMs: whenMs(when, kind, tz), gone, tone, line });
  };

  for (const p of d.proposals) {
    if (!p.due || p.state === 'dismissed' || !inScope(scope, p.spaceId)) continue;
    const ag = p.created?.agendaId ? agendaById.get(p.created.agendaId) : undefined;
    const td = p.created?.todoId ? todoById.get(p.created.todoId) : undefined;
    const base = { id: p.id, proposalId: p.id, noticeId: p.noticeId, agent: p.agent, spaceId: p.spaceId, kind: p.kind };
    const forWho = p.forMemberId ? [p.forMemberId] : [];
    if (p.state === 'accepted') {
      const members = ag?.memberIds?.length ? ag.memberIds : td ? [td.ownerId] : forWho;
      push({ ...base, flashId: ag?.id ?? td?.id ?? p.id, title: ag?.title ?? td?.title ?? p.title, memberIds: members }, ag?.when ?? td?.due ?? p.due, ag?.dueKind ?? td?.dueKind ?? p.dueKind, (gone) => {
        if (td?.done || ag?.done) return ['done', ['done', names(td ? [td.ownerId] : members)].filter(Boolean).join(' · ')];
        if (gone) return [td ? 'overdue' : 'gone', 'the family accepted this, and the date has gone'];
        const clash = ag && clashWith(ag.id);
        if (clash) return ['clash', `clashes with ${clash} — move one?`];
        return ['accepted', ['accepted', td ? 'on the to-dos' : 'on the calendar', names(members)].filter(Boolean).join(' · ')];
      });
    } else if (p.state === 'changed') {
      const was = p.changedFrom?.due ? fmtSlot(p.changedFrom.due, p.changedFrom.dueKind, tz) : 'before';
      push({ ...base, flashId: ag?.id ?? p.id, title: p.title, memberIds: forWho }, p.due, p.dueKind, () => ['changed', `the notice changed: was ${was}, now ${fmtSlot(p.due!, p.dueKind, tz)} — accept the new time?`]);
    } else {
      const missed = isMissed(p, now, tz);
      push({ ...base, flashId: p.id, title: p.title, memberIds: forWho }, p.due, p.dueKind, (gone) => {
        if (missed) return ['missed', 'nobody accepted or dismissed this, and the date has gone'];
        if (gone) return ['overdue', 'nobody has accepted this yet, and the date has gone'];
        return ['proposed', ['nobody has accepted this yet', p.forMemberId ? `for ${names(forWho)}` : ''].filter(Boolean).join(' · ')];
      });
    }
  }

  for (const a of d.agenda) {
    if (a.kind === 'reminder' || a.kind === 'update' || linked.has(a.id) || (a.proposalId && proposalIds.has(a.proposalId)) || !inScope(scope, a.spaceId)) continue;
    const clash = clashWith(a.id);
    push({ id: a.id, flashId: a.id, title: a.title, agent: a.agent, spaceId: a.spaceId, kind: a.kind, memberIds: a.memberIds ?? [], noticeId: a.noticeId }, a.when, a.dueKind, (gone) => {
      if (a.done) return ['done', 'done'];
      if (gone) return ['gone', `${AGENDA_LINE[a.kind]}, and the date has gone`];
      if (clash) return ['clash', `clashes with ${clash} — move one?`];
      return ['scheduled', [AGENDA_LINE[a.kind], names(a.memberIds ?? [])].filter(Boolean).join(' · ')];
    });
  }

  for (const t of d.todos) {
    if (!t.due || linked.has(t.id) || (t.proposalId && proposalIds.has(t.proposalId)) || !inScope(scope, todoSpace(t))) continue;
    const owner = names([t.ownerId]);
    push({ id: t.id, flashId: t.id, title: t.title, agent: t.agent ?? 'household', spaceId: todoSpace(t), kind: 'todo', memberIds: [t.ownerId], noticeId: t.noticeId }, t.due, t.dueKind ?? 'allDay', (gone) => {
      if (t.done) return ['done', `done · ${owner}`];
      if (gone) return ['overdue', `on the to-dos, and the date has gone · ${owner}`];
      return ['accepted', `on the to-dos · ${owner}`];
    });
  }

  const tie = (a: AgentId) => TIE_ORDER.indexOf(a);
  return out.sort((a, b) => a.sortMs - b.sortMs || tie(a.agent) - tie(b.agent) || a.title.localeCompare(b.title));
}

/** Entries still ahead (not gone), for "N upcoming". */
export const upcoming = (entries: TimelineEntry[]) => entries.filter((e) => !e.gone && e.tone !== 'done');

// ── Header counts and What arrived ────────────────────────────────────

/** "{n} notices · {m} dated": notices in the space, and how many of them carry a date. */
export function spaceCounts(d: Pick<DeskData, 'notices' | 'proposals' | 'agenda' | 'todos'>, space: SpaceId): { notices: number; dated: number } {
  const notices = d.notices.filter((n) => !n.quarantined && n.spaceId === space);
  const datedIds = new Set<string>();
  for (const p of d.proposals) if (p.due) datedIds.add(p.noticeId);
  for (const a of d.agenda) if (a.noticeId && a.kind !== 'update') datedIds.add(a.noticeId);
  for (const t of d.todos) if (t.due && t.noticeId) datedIds.add(t.noticeId);
  return { notices: notices.length, dated: notices.filter((n) => datedIds.has(n.id)).length };
}

export interface Arrival {
  notice: Notice;
  /** "N to decide": undecided proposals read from it. */
  toDecide: number;
}

/** Notices in the scope (Quarantine excluded), newest first. */
export function whatArrived(d: Pick<DeskData, 'notices' | 'proposals'>, scope: Scope): Arrival[] {
  return d.notices
    .filter((n) => !n.quarantined && inScope(scope, n.spaceId))
    .sort((a, b) => b.receivedAt.localeCompare(a.receivedAt))
    .map((notice) => ({ notice, toDecide: toDecide(d, notice.id) }));
}

const VIA: Record<Notice['source'], string> = { email: 'email', phone: 'phone', whatsapp: 'WhatsApp', telegram: 'Telegram', paste: 'pasted', site: 'a site' };

/** "your phone", "Lakeside Dental · email", "Coach Daniels · WhatsApp". */
export function sourceLabel(n: Pick<Notice, 'source' | 'sender'>): string {
  if (n.source === 'phone') return /phone/i.test(n.sender) ? n.sender : `${n.sender} · your phone`;
  if (n.source === 'paste') return n.sender;
  return `${n.sender} · ${VIA[n.source]}`;
}

// ── Money: spent here, charges again, due soon, bills ─────────────────

export interface Charges {
  rows: RecurringMerchant[];
  total: number;
  count: number;
}

/** Charges mail saw in the scope over the last `days` days (newest first). */
export function spentHere(recurring: RecurringMerchant[], scope: Scope, now: Date, tz: string, days = 30): Charges {
  const today = dayKey(now, tz);
  const from = addDays(today, -days);
  const rows = recurring.filter((r) => inScope(scope, r.spaceId) && r.last >= from && r.last <= today).sort((a, b) => b.last.localeCompare(a.last) || b.amount - a.amount);
  return { rows, total: round2(rows.reduce((s, r) => s + r.amount, 0)), count: rows.length };
}

/** Merchants that charge again, soonest next charge first (from today on). */
export function chargesAgain(recurring: RecurringMerchant[], scope: Scope, now: Date, tz: string): RecurringMerchant[] {
  const today = dayKey(now, tz);
  return recurring.filter((r) => inScope(scope, r.spaceId) && r.next >= today).sort((a, b) => a.next.localeCompare(b.next) || b.amount - a.amount);
}

/** Next charges within `days` days (today included). */
export function dueSoon(recurring: RecurringMerchant[], now: Date, tz: string, days = 14): RecurringMerchant[] {
  const end = addDays(dayKey(now, tz), days);
  return chargesAgain(recurring, 'all', now, tz).filter((r) => r.next <= end);
}

/** Bills, loans and insurance (not subscriptions) charging in the next `days` days ("N bills"). */
export function upcomingBills(recurring: RecurringMerchant[], now: Date, tz: string, days = 30): RecurringMerchant[] {
  const end = addDays(dayKey(now, tz), days);
  return chargesAgain(recurring, 'all', now, tz).filter((r) => r.kind !== 'subscription' && r.next <= end);
}

/** Bills and payments dated this week (today + 6), from the family timeline. */
export const billsThisWeek = (week: TimelineEntry[]) => week.filter((e) => e.kind === 'payment' || e.kind === 'bill');

export interface MoneyStats {
  spent: Charges;
  subscriptionsNext: number;
  subscriptions: number;
}

export function moneyStats(recurring: RecurringMerchant[], now: Date, tz: string): MoneyStats {
  const subs = recurring.filter((r) => r.kind === 'subscription');
  return { spent: spentHere(recurring, 'all', now, tz), subscriptionsNext: round2(subs.reduce((s, r) => s + r.amount, 0)), subscriptions: subs.length };
}

export const round2 = (n: number) => Math.round(n * 100) / 100;

// ── To decide (Dates spotted, Health) ─────────────────────────────────

/** Undecided proposals still worth deciding (missed ones excluded), soonest first; no date last. */
export function decideList(d: Pick<DeskData, 'proposals'>, opts: { scope?: Scope; datedOnly?: boolean }, now: Date, tz: string): Proposal[] {
  const scope = opts.scope ?? 'all';
  const key = (p: Proposal) => (p.due ? whenMs(p.due, p.dueKind, tz) : Number.MAX_SAFE_INTEGER);
  return d.proposals
    .filter((p) => isUndecided(p) && !isMissed(p, now, tz) && inScope(scope, p.spaceId) && (!opts.datedOnly || !!p.due))
    .sort((a, b) => key(a) - key(b) || a.title.localeCompare(b.title));
}

/** Dated proposals that went by with nobody deciding (they wait on Waiting on you). */
export const missedCount = (d: Pick<DeskData, 'proposals'>, now: Date, tz: string, scope: Scope = 'all') =>
  d.proposals.filter((p) => isMissed(p, now, tz) && inScope(scope, p.spaceId)).length;
