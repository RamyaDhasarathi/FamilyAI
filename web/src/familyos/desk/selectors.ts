// Derived views over the desk store (MASTER_AGENT.md §7 Phase 1 "Data",
// Phase 2 item 4, Phase 3 Waiting on you). Pure functions of (data, now, tz):
// no copies are stored, so every view follows the one store.
import type { AgendaItem, AgentId, Conflict, DeskData, Day, Instant, Proposal, Todo, When } from './types';
import { addDays, dayKey, dayOf, fmtRelDay, fmtSlot, isDay, zoned } from './format';

export { fingerprint, approvalHolds } from './fingerprint';

/** Same-time ties on Today (Phase 1 "Data"). */
export const TIE_ORDER: AgentId[] = ['calendar', 'household', 'finance', 'education', 'grocery'];
/** Agent chip order on Today (Phase 1 left column). */
export const CHIP_ORDER: AgentId[] = ['household', 'finance', 'education', 'grocery', 'calendar'];

const tie = (a: AgentId) => TIE_ORDER.indexOf(a);
const ms = (i: Instant) => new Date(i).getTime();
const timed = (w: When | undefined, k?: string): w is Instant => !!w && !isDay(w) && (k === 'time' || k === undefined);

// ── Today ─────────────────────────────────────────────────────────────

export interface DayRow {
  id: string;
  source: 'agenda' | 'todo';
  agent: AgentId;
  title: string;
  /** e.g. "Reminder · tomorrow". */
  label?: string;
  timed: boolean;
  at?: Instant;
  end?: Instant;
  /** "4 pm" for timed rows, else "all day" / "EOD" / "not specified". */
  slot: string;
  kind: AgendaItem['kind'] | 'todo';
  short?: string;
  details: [string, string][];
  memberIds: string[];
  done: boolean;
  noticeId?: string;
  proposalId?: string;
}

/**
 * Everything happening today in the household timezone: agenda items dated
 * today, to-dos (with an agent) due today, and reminders created today (a
 * reminder about tomorrow is labelled "Reminder · tomorrow"; one created on
 * another day is left out). Timed rows first by time, ties Calendar,
 * Household, Finance, Education, Grocery; untimed rows ("Anytime today") after.
 */
export function todayItems(d: Pick<DeskData, 'agenda' | 'todos'>, now: Date, tz: string): DayRow[] {
  const today = dayKey(now, tz);
  const rows: DayRow[] = [];
  for (const a of d.agenda) {
    if (a.kind === 'reminder') {
      if (dayKey(a.createdAt, tz) !== today) continue;
    } else if (dayOf(a.when, tz) !== today) continue;
    const isTimed = a.kind !== 'reminder' && timed(a.when, a.dueKind);
    rows.push({
      id: a.id, source: 'agenda', agent: a.agent, title: a.title, kind: a.kind, short: a.short,
      label: a.kind === 'reminder' && a.remindsOf ? `Reminder · ${fmtRelDay(a.remindsOf, today).toLowerCase()}` : undefined,
      timed: isTimed, at: isTimed ? a.when : undefined, end: a.end, slot: isTimed ? fmtSlot(a.when, 'time', tz) : fmtSlot(a.when, a.dueKind, tz),
      details: a.details ?? [], memberIds: a.memberIds ?? [], done: !!a.done, noticeId: a.noticeId, proposalId: a.proposalId,
    });
  }
  for (const t of d.todos) {
    if (!t.agent || !t.due || dayOf(t.due, tz) !== today) continue;
    const isTimed = timed(t.due, t.dueKind);
    rows.push({
      id: t.id, source: 'todo', agent: t.agent, title: t.title, kind: 'todo', timed: isTimed, at: isTimed ? t.due : undefined,
      slot: isTimed ? fmtSlot(t.due, 'time', tz) : fmtSlot(t.due, t.dueKind ?? 'allDay', tz), details: [], memberIds: [t.ownerId], done: t.done, noticeId: t.noticeId, proposalId: t.proposalId,
    });
  }
  return rows.sort((a, b) => {
    if (a.timed !== b.timed) return a.timed ? -1 : 1;
    if (a.timed && b.timed) return ms(a.at!) - ms(b.at!) || tie(a.agent) - tie(b.agent);
    return tie(a.agent) - tie(b.agent) || a.title.localeCompare(b.title);
  });
}

/** Done / remaining and the next timed row (Today hero ring). */
export function dayProgress(rows: DayRow[], now: Date) {
  const isDone = (r: DayRow) => r.done || (r.timed && ms(r.end ?? r.at!) <= now.getTime());
  const done = rows.filter(isDone).length;
  const next = rows.find((r) => r.timed && !r.done && ms(r.at!) >= now.getTime());
  return { done, remaining: rows.length - done, total: rows.length, next };
}

/** Agent chips on Today: Calendar and Education as counts, the others their most pressing row. */
export function agentChips(rows: DayRow[]): { agent: AgentId; text: string; count: number }[] {
  const rank: Record<DayRow['kind'], number> = { bill: 0, visit: 1, delivery: 2, event: 3, todo: 4, reminder: 5, update: 6 };
  return CHIP_ORDER.map((agent) => {
    const mine = rows.filter((r) => r.agent === agent);
    const n = mine.length;
    let text: string;
    if (agent === 'calendar') text = n ? `${n} ${n === 1 ? 'event' : 'events'}` : 'Nothing today';
    else if (agent === 'education') text = n ? `${n} ${n === 1 ? 'update' : 'updates'}` : 'Nothing today';
    else {
      const top = [...mine].sort((a, b) => rank[a.kind] - rank[b.kind])[0];
      text = top ? (top.short ?? top.title) : 'Nothing today';
    }
    return { agent, text, count: n };
  });
}

// ── Proposals: undecided, missed, Waiting on you ──────────────────────

export const isUndecided = (p: Proposal) => p.state === 'proposed' || p.state === 'changed';

/** The proposal's date has passed (a timed one: its time; otherwise: its day). */
export function dateGone(p: { due?: When; dueKind?: string }, now: Date, tz: string): boolean {
  if (!p.due) return false;
  if (timed(p.due, p.dueKind)) return ms(p.due) < now.getTime();
  return dayOf(p.due, tz) < dayKey(now, tz);
}

/**
 * Missed: nobody accepted or dismissed it and the date has gone, for things
 * that only matter on their date (calendar entries, reminders) — or marked
 * missed already. A task or payment past its date is "overdue" instead: it
 * can still be done.
 */
export function isMissed(p: Proposal, now: Date, tz: string): boolean {
  if (p.state === 'missed') return true;
  return p.state === 'proposed' && (p.kind === 'calendar' || p.kind === 'reminder') && dateGone(p, now, tz);
}

export type WaitGroupId = 'overdue' | 'thisWeek' | 'later' | 'noDate';
export const WAIT_GROUP_LABELS: Record<WaitGroupId, string> = { overdue: 'Overdue', thisWeek: 'This week', later: 'Later', noDate: 'No date' };

export interface WaitingView {
  missed: Proposal[];
  groups: { id: WaitGroupId; label: string; items: Proposal[] }[];
  count: number;
}

/** Waiting on you: undecided proposals grouped Overdue / This week (today + 6 days) / Later / No date; missed ones apart. */
export function waitingGroups(d: Pick<DeskData, 'proposals'>, now: Date, tz: string): WaitingView {
  const today = dayKey(now, tz);
  const weekEnd = addDays(today, 6);
  const missed: Proposal[] = [];
  const by: Record<WaitGroupId, Proposal[]> = { overdue: [], thisWeek: [], later: [], noDate: [] };
  for (const p of d.proposals) {
    if (isMissed(p, now, tz)) {
      missed.push(p);
      continue;
    }
    if (!isUndecided(p)) continue;
    if (!p.due) by.noDate.push(p);
    else if (dateGone(p, now, tz)) by.overdue.push(p);
    else if (dayOf(p.due, tz) <= weekEnd) by.thisWeek.push(p);
    else by.later.push(p);
  }
  const byDue = (a: Proposal, b: Proposal) => dueMs(a, tz) - dueMs(b, tz);
  (['overdue', 'thisWeek', 'later'] as const).forEach((k) => by[k].sort(byDue));
  by.noDate.sort((a, b) => ms(b.createdAt) - ms(a.createdAt));
  missed.sort(byDue);
  const groups = (Object.keys(by) as WaitGroupId[]).map((id) => ({ id, label: WAIT_GROUP_LABELS[id], items: by[id] }));
  return { missed, groups, count: missed.length + groups.reduce((n, g) => n + g.items.length, 0) };
}

/** Sort key in real time: timed → the instant; a Day → its local start (EOD → 23:59). */
function dueMs(p: { due?: When; dueKind?: string }, tz: string): number {
  if (!p.due) return Number.MAX_SAFE_INTEGER;
  if (timed(p.due, p.dueKind)) return ms(p.due);
  const day = dayOf(p.due, tz);
  return ms(p.dueKind === 'eod' ? zoned(day, 23, 59, tz) : zoned(day, 0, 0, tz));
}

// ── Needs someone · worst first ───────────────────────────────────────

export type NeedTone = 'missed' | 'overdue' | 'today' | 'changed';
export const NEED_ORDER: NeedTone[] = ['missed', 'overdue', 'today', 'changed'];
export const NEED_LABELS: Record<NeedTone, string> = { missed: 'Missed', overdue: 'Overdue', today: 'Today', changed: 'Changed' };

export interface NeedCard {
  id: string;
  tone: NeedTone;
  title: string;
  /** Honest state line (MASTER §10). */
  line: string;
  due?: When;
  dueKind?: Proposal['dueKind'];
  memberId?: string;
  agent: AgentId;
  noticeId: string;
  proposalId?: string;
  todoId?: string;
}

/** Things that need a person, worst first: Missed → Overdue → Today → Changed (then by date). */
export function needsSomeone(d: Pick<DeskData, 'proposals' | 'todos'>, now: Date, tz: string): NeedCard[] {
  const today = dayKey(now, tz);
  const cards: NeedCard[] = [];
  const base = (p: Proposal) => ({ id: p.id, title: p.title, due: p.due, dueKind: p.dueKind, memberId: p.forMemberId, agent: p.agent, noticeId: p.noticeId, proposalId: p.id });
  for (const p of d.proposals) {
    if (isMissed(p, now, tz)) cards.push({ ...base(p), tone: 'missed', line: 'nobody accepted or dismissed this, and the date has gone' });
    else if (p.state === 'changed') {
      const was = p.changedFrom?.due ? fmtSlot(p.changedFrom.due, p.changedFrom.dueKind, tz) : 'before';
      const now2 = p.due ? fmtSlot(p.due, p.dueKind, tz) : 'no date';
      cards.push({ ...base(p), tone: 'changed', line: `the notice changed after it was accepted: was ${was}, now ${now2}` });
    } else if (p.state === 'proposed' && dateGone(p, now, tz)) cards.push({ ...base(p), tone: 'overdue', line: 'nobody has accepted this yet, and the date has gone' });
    else if (p.state === 'proposed' && p.due && dayOf(p.due, tz) === today) cards.push({ ...base(p), tone: 'today', line: 'due today · nobody has accepted it yet' });
  }
  for (const t of d.todos) {
    if (t.done || !t.due || !t.noticeId || !dateGone(t, now, tz)) continue;
    cards.push({ id: t.id, tone: 'overdue', title: t.title, line: 'the family accepted this, and the date has gone', due: t.due, dueKind: t.dueKind, memberId: t.ownerId, agent: t.agent ?? 'household', noticeId: t.noticeId, proposalId: t.proposalId, todoId: t.id });
  }
  return cards.sort((a, b) => NEED_ORDER.indexOf(a.tone) - NEED_ORDER.indexOf(b.tone) || dueMs(a, tz) - dueMs(b, tz));
}

// ── Coming up (grouped by day) ────────────────────────────────────────

export interface ComingEntry {
  id: string;
  source: 'agenda' | 'proposal' | 'todo';
  agent: AgentId;
  title: string;
  slot: string;
  /** Has a clock time (else all day / EOD / not specified). */
  timed: boolean;
  sortMs: number;
  memberIds: string[];
  undecided: boolean;
  noticeId?: string;
  proposalId?: string;
}

export interface ComingDay {
  day: Day;
  label: string;
  entries: ComingEntry[];
}

/** Agenda, undecided proposals and open to-dos after today (or from today), grouped by day. */
export function comingUp(d: Pick<DeskData, 'agenda' | 'proposals' | 'todos'>, now: Date, tz: string, opts: { days?: number; includeToday?: boolean } = {}): ComingDay[] {
  const today = dayKey(now, tz);
  const first = opts.includeToday ? today : addDays(today, 1);
  const last = addDays(today, opts.days ?? 14);
  const inRange = (day: Day) => day >= first && day <= last;
  const slotMs = (w: When, k?: string) => dueMs({ due: w, dueKind: k }, tz);
  const out: (ComingEntry & { day: Day })[] = [];
  for (const a of d.agenda) {
    if (a.kind === 'reminder' || a.kind === 'update' || !inRange(dayOf(a.when, tz))) continue;
    out.push({ id: a.id, day: dayOf(a.when, tz), source: 'agenda', agent: a.agent, title: a.title, slot: fmtSlot(a.when, a.dueKind, tz), timed: timed(a.when, a.dueKind), sortMs: slotMs(a.when, a.dueKind), memberIds: a.memberIds ?? [], undecided: false, noticeId: a.noticeId, proposalId: a.proposalId });
  }
  for (const p of d.proposals) {
    if (p.state !== 'proposed' || !p.due || !inRange(dayOf(p.due, tz)) || dateGone(p, now, tz)) continue;
    out.push({ id: p.id, day: dayOf(p.due, tz), source: 'proposal', agent: p.agent, title: p.title, slot: fmtSlot(p.due, p.dueKind, tz), timed: timed(p.due, p.dueKind), sortMs: slotMs(p.due, p.dueKind), memberIds: p.forMemberId ? [p.forMemberId] : [], undecided: true, noticeId: p.noticeId, proposalId: p.id });
  }
  for (const t of d.todos) {
    if (t.done || !t.due || !inRange(dayOf(t.due, tz))) continue;
    out.push({ id: t.id, day: dayOf(t.due, tz), source: 'todo', agent: t.agent ?? 'household', title: t.title, slot: fmtSlot(t.due, t.dueKind, tz), timed: timed(t.due, t.dueKind), sortMs: slotMs(t.due, t.dueKind ?? 'allDay'), memberIds: [t.ownerId], undecided: false, noticeId: t.noticeId, proposalId: t.proposalId });
  }
  const days = [...new Set(out.map((e) => e.day))].sort();
  return days.map((day) => ({
    day,
    label: fmtRelDay(day, today),
    entries: out.filter((e) => e.day === day).sort((a, b) => a.sortMs - b.sortMs || tie(a.agent) - tie(b.agent)),
  }));
}

// ── Lookups ───────────────────────────────────────────────────────────

export const openConflicts = (d: Pick<DeskData, 'conflicts'>): Conflict[] => d.conflicts.filter((c) => !c.resolvedAt);
export const visibleNotices = (d: Pick<DeskData, 'notices'>) => d.notices.filter((n) => !n.quarantined);
export const proposalsFor = (d: Pick<DeskData, 'proposals'>, noticeId: string) => d.proposals.filter((p) => p.noticeId === noticeId);
/** "1 to decide" on a notice row. */
export const toDecide = (d: Pick<DeskData, 'proposals'>, noticeId: string) => d.proposals.filter((p) => p.noticeId === noticeId && isUndecided(p)).length;
export const planTodos = (d: Pick<DeskData, 'todos'>, planId: string): Todo[] => d.todos.filter((t) => t.planId === planId);
export const memberName = (d: Pick<DeskData, 'members'>, id?: string) => (id ? (d.members.find((x) => x.id === id)?.name ?? id) : '');
/** Audit actor chip text: a member's name, or "FamilyOS". */
export const actorName = (d: Pick<DeskData, 'members'>, actor: string) => (actor === 'FamilyOS' ? 'FamilyOS' : memberName(d, actor));
