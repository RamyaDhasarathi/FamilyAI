// Ask, the common questions (MASTER_AGENT.md §7 Phase 3 "Ask", §3.3.4 "Worst
// first"; FamilyOS.mp4 4:40–5:40 suggestion chips, 7:20 palette prompts):
// what needs someone this week, what we pay every month, how money is doing,
// when we are all free, the weekend, tonight, tomorrow, today, school work,
// and what is still undecided. Each reads the desk data and cites it.
import type { AgendaItem, Day, Proposal } from '../../desk/types';
import { addDays, dayKey, dayOf, fmtRelDay, fmtTime, isDay, nextWeekday, weekday, zonedParts } from '../../desk/format';
import { isMissed, todayItems, waitingGroups } from '../../desk/selectors';
import type { Composer } from './askCompose';
import { memberOf, namedMembers, norm, whenAfter, whenPhrase } from './askSearch';

export interface Topic {
  id: string;
  test: RegExp;
  run(c: Composer, q: string): boolean;
}

const open = (p: Proposal) => p.state === 'proposed' || p.state === 'changed';
const today = (c: Composer) => dayKey(c.ctx.now, c.ctx.tz);
const dayWord = (day: Day, c: Composer) => {
  const w = fmtRelDay(day, today(c));
  return /^(Today|Tomorrow|Yesterday)$/.test(w) ? w.toLowerCase() : `on ${w}`;
};
const timedItem = (a: AgendaItem) => !isDay(a.when) && a.dueKind === 'time';
const people = (c: Composer, ids: string[] = []) => ids.map((id) => memberOf(c.d, id)).filter(Boolean).join(', ');

/** Calendar entries on a day (no reminders or agent updates), by time. */
function agendaOn(c: Composer, day: Day): AgendaItem[] {
  return c.d.agenda
    .filter((a) => a.kind !== 'reminder' && a.kind !== 'update' && dayOf(a.when, c.ctx.tz) === day)
    .sort((a, b) => (timedItem(a) ? a.when : `${a.when}~`).localeCompare(timedItem(b) ? b.when : `${b.when}~`));
}

/** "Mia’s recital at 2 pm, Riverside Hall (Mia, Sarah)" without repeating a time the title already says. */
function sayItem(c: Composer, a: AgendaItem, withPlace = false) {
  const title = a.title.replace(/\.$/, '');
  const time = timedItem(a) ? fmtTime(a.when, c.ctx.tz, true) : '';
  const t = time && !norm(title).includes(norm(time)) ? ` at ${time}` : '';
  const who = people(c, a.memberIds);
  c.say(`${title}${t}${withPlace && a.place ? `, ${a.place}` : ''}${who ? ` (${who})` : ''}`).cite(a.noticeId);
}

function sayProposals(c: Composer, label: string, list: Proposal[], max = 4) {
  if (!list.length) return;
  c.say(`${label}: `);
  list.slice(0, max).forEach((p, i) => c.say(`${i ? '; ' : ''}${p.title}${p.due ? `, ${whenAfter(p.title, p.due, p.dueKind, c.ctx)}` : ', no date'}`).cite(p.noticeId));
  c.say(list.length > max ? `; and ${list.length - max} more. ` : '. ');
}

/** "N things are still undecided: A, today, by end of day [r1]; B …". */
export function listUndecided(c: Composer, max: number) {
  const list = c.d.proposals.filter((p) => open(p) && !isMissed(p, c.ctx.now, c.ctx.tz)).sort((a, b) => (a.due ?? '9999').localeCompare(b.due ?? '9999'));
  if (!list.length) return void c.say('Nothing is undecided right now.');
  c.say(`${list.length === 1 ? 'One thing is' : `${list.length} things are`} still undecided: `);
  list.slice(0, max).forEach((p, i) => c.say(`${i ? '; ' : ''}${p.title}${p.due ? `, ${whenAfter(p.title, p.due, p.dueKind, c.ctx)}` : ', no date'}`).cite(p.noticeId));
  c.say(list.length > max ? `; and ${list.length - max} more on Waiting on you.` : '.');
  list.slice(0, 2).forEach((p) => c.offerAccept(p));
}

function monthly(c: Composer) {
  const list = c.d.recurring.filter((r) => r.cadence === 'monthly').sort((a, b) => b.amount - a.amount);
  if (!list.length) return void c.say('Nothing the household received shows a monthly charge.');
  const total = Math.round(list.reduce((s, r) => s + r.amount, 0) * 100) / 100;
  c.say(`You pay ${list.length} things every month, about ¤{${total}} in all. `);
  const part = (label: string, rs: typeof list) => {
    if (!rs.length) return;
    c.say(`${label}: `);
    rs.forEach((r, i) => c.say(`${i ? ', ' : ''}${r.merchant} ¤{${r.amount}}`).cite(r.noticeId));
    c.say('. ');
  };
  part('Bills, loans and insurance', list.filter((r) => r.kind !== 'subscription'));
  part('Subscriptions', list.filter((r) => r.kind === 'subscription'));
  const next = list.filter((r) => r.next >= today(c)).sort((a, b) => a.next.localeCompare(b.next))[0];
  if (next) c.say(`Next to charge: ${next.merchant}, ${dayWord(next.next, c)}`).cite(next.noticeId).say('. ');
  c.say('FamilyOS only reads these; it pays none of them.');
}

function money(c: Composer) {
  const upd = c.d.agenda.filter((a) => a.agent === 'finance' && a.kind === 'update').sort((a, b) => b.createdAt.localeCompare(a.createdAt))[0];
  if (upd) {
    c.say(upd.title.replace(/\.$/, '')).cite(upd.noticeId).say('. ');
    const spend = upd.details?.find(([k]) => /spending/i.test(k));
    if (spend) c.say(`Card spending this month: ${spend[1]}`).cite(upd.noticeId).say('. ');
  }
  const end = addDays(today(c), 7);
  const bills = c.d.agenda.filter((a) => a.kind === 'bill' && !a.done && dayOf(a.when, c.ctx.tz) >= today(c) && dayOf(a.when, c.ctx.tz) <= end);
  bills.forEach((b) => c.say(b.title.replace(/\.$/, '')).cite(b.noticeId).say('. '));
  const undecided = c.d.proposals.filter((p) => p.agent === 'finance' && open(p) && !isMissed(p, c.ctx.now, c.ctx.tz));
  sayProposals(c, 'Still undecided', undecided);
  undecided.slice(0, 1).forEach((p) => c.offerAccept(p));
  const subs = c.d.recurring.filter((r) => r.kind === 'subscription' && r.cadence === 'monthly');
  if (subs.length) {
    c.say(`Subscriptions come to about ¤{${Math.round(subs.reduce((s, r) => s + r.amount, 0) * 100) / 100}} a month`);
    [...new Set(subs.map((r) => r.noticeId))].forEach((id) => c.cite(id));
    c.say('.');
  }
  if (!upd && !bills.length && !undecided.length && !subs.length) c.say('No statement or bill has arrived yet, so there is nothing to say about money.');
}

function week(c: Composer) {
  const v = waitingGroups(c.d, c.ctx.now, c.ctx.tz);
  const g = Object.fromEntries(v.groups.map((x) => [x.id, x.items]));
  if (!v.count) return void c.say('Nothing needs anyone this week.');
  sayProposals(c, `${v.missed.length === 1 ? 'One thing was' : `${v.missed.length} things were`} missed (nobody decided before the date)`, v.missed);
  sayProposals(c, 'Overdue', g.overdue);
  sayProposals(c, 'This week', g.thisWeek);
  const rest = g.later.length + g.noDate.length;
  if (rest) c.say(`${rest} more ${rest === 1 ? 'is' : 'are'} later or have no date; they are on Waiting on you.`);
  [...g.overdue, ...g.thisWeek].slice(0, 2).forEach((p) => c.offerAccept(p));
}

function free(c: Composer) {
  const days = [0, 1, 2, 3, 4, 5, 6].map((i) => addDays(today(c), i));
  const busy = days.map((day) => ({ day, items: agendaOn(c, day).filter(timedItem) }));
  const empty = busy.filter((b) => !b.items.length).map((b) => dayWord(b.day, c));
  c.say(empty.length ? `Nothing with a time is on the family calendar ${empty.join(', ').replace(/, ([^,]*)$/, ' or $1')}. ` : 'Every day this week has something with a time on it. ');
  const full = busy.filter((b) => b.items.length);
  if (full.length) c.say('The busy days: ');
  full.slice(0, 3).forEach((b, i) => {
    c.say(`${i ? '; ' : ''}${fmtRelDay(b.day, today(c))}: `);
    b.items.slice(0, 3).forEach((a, j) => {
      if (j) c.say(', ');
      sayItem(c, a);
    });
    if (b.items.length > 3) c.say(` and ${b.items.length - 3} more`);
  });
  if (full.length) c.say('.');
}

function weekend(c: Composer) {
  const t = today(c);
  const wd = weekday(t);
  const days = wd === 0 ? [t] : [wd === 6 ? t : nextWeekday(t, 6)];
  if (wd !== 0) days.push(addDays(days[0], 1));
  days.forEach((day) => {
    const items = agendaOn(c, day);
    c.say(`${fmtRelDay(day, t)}: `);
    if (!items.length) c.say('nothing on the calendar yet');
    items.forEach((a, i) => {
      if (i) c.say('; ');
      sayItem(c, a, true);
    });
    c.say('. ');
  });
  const last = days[days.length - 1];
  // Only what bears on the weekend: things due on it, or read from the same notices as its plans.
  const weekendNotices = new Set(days.flatMap((day) => agendaOn(c, day).map((a) => a.noticeId)));
  const before = c.d.proposals.filter((p) => {
    if (!open(p) || isMissed(p, c.ctx.now, c.ctx.tz)) return false;
    const day = p.due ? dayOf(p.due, c.ctx.tz) : '';
    return (day >= days[0] && day <= last) || (weekendNotices.has(p.noticeId) && (!day || (day >= t && day <= last)));
  });
  sayProposals(c, 'Still to decide before then', before);
  const todos = c.d.todos.filter((x) => !x.done && x.due && dayOf(x.due, c.ctx.tz) >= t && dayOf(x.due, c.ctx.tz) <= last);
  if (todos.length) {
    c.say('On the to-dos: ');
    todos.forEach((x, i) => c.say(`${i ? '; ' : ''}${x.title}, ${whenPhrase(x.due!, x.dueKind, c.ctx)} (${memberOf(c.d, x.ownerId)})`).cite(x.noticeId));
    c.say('.');
  }
  before.slice(0, 2).forEach((p) => c.offerAccept(p));
}

function evening(c: Composer) {
  const now = c.ctx.now.getTime();
  // The rest of today from mid-afternoon on: anything that has not ended yet and starts at 3 pm or later.
  const items = agendaOn(c, today(c)).filter((a) => timedItem(a) && new Date(a.end ?? a.when).getTime() > now && zonedParts(a.when, c.ctx.tz).h >= 15);
  c.say('FamilyOS does not plan meals, but here is the evening. ');
  if (!items.length) return void c.say('Nothing with a time is on the calendar for the rest of today.');
  items.forEach((a, i) => {
    if (i) c.say('; ');
    sayItem(c, a);
  });
  const lastEnd = items.map((a) => a.end ?? a.when).sort().pop()!;
  c.say(`. The last of it ends at ${fmtTime(lastEnd, c.ctx.tz, true)}.`);
}

function tomorrow(c: Composer) {
  const day = addDays(today(c), 1);
  const items = agendaOn(c, day);
  if (!items.length) c.say('Nothing is on the calendar for tomorrow. ');
  else {
    c.say('Tomorrow: ');
    items.forEach((a, i) => {
      if (i) c.say('; ');
      sayItem(c, a);
    });
    c.say('. ');
  }
  const ids = new Set(items.map((a) => a.id));
  c.d.conflicts.filter((x) => !x.resolvedAt && (ids.has(x.aId) || ids.has(x.bId))).forEach((x) => {
    const a = c.d.agenda.find((y) => y.id === x.aId);
    const b = c.d.agenda.find((y) => y.id === x.bId);
    c.say(`FamilyOS noticed: ${x.message}`).cite(a?.noticeId).cite(b?.noticeId).say(' The fix on Today waits for someone to confirm it. ');
  });
  const due = c.d.proposals.filter((p) => open(p) && p.due && dayOf(p.due, c.ctx.tz) === day);
  sayProposals(c, 'Waiting on a decision', due);
  due.slice(0, 2).forEach((p) => c.offerAccept(p));
}

function todayTopic(c: Composer) {
  const rows = todayItems(c.d, c.ctx.now, c.ctx.tz);
  c.say(rows.length ? `Today has ${rows.length} ${rows.length === 1 ? 'thing' : 'things'}: ` : 'Nothing is scheduled for today. ');
  rows.slice(0, 6).forEach((r, i) => c.say(`${i ? '; ' : ''}${r.title.replace(/\.$/, '')}${r.timed && !norm(r.title).includes(norm(r.slot)) ? ` at ${r.slot}` : ''}`).cite(r.noticeId));
  if (rows.length) c.say(rows.length > 6 ? `; and ${rows.length - 6} more. ` : '. ');
  const t = today(c);
  const due = c.d.proposals.filter((p) => open(p) && p.due && dayOf(p.due, c.ctx.tz) <= t && !isMissed(p, c.ctx.now, c.ctx.tz));
  sayProposals(c, 'Waiting on you today', due);
  due.slice(0, 2).forEach((p) => c.offerAccept(p));
}

function school(c: Composer, q: string) {
  const kids = c.d.members.filter((m) => m.role === 'child');
  const named = namedMembers(q, kids);
  const who = named.length ? named : kids;
  const ids = who.map((m) => m.id);
  const isSchool = (x: { agent?: string; spaceId?: string }) => x.agent === 'education' || x.spaceId === 'education';
  const forKid = (id?: string) => !!id && ids.includes(id);
  const t = today(c);
  c.say(`For ${who.map((m) => m.name).join(' and ')}: `);
  const props = c.d.proposals.filter((p) => isSchool(p) && forKid(p.forMemberId));
  const undecided = props.filter((p) => open(p) && !isMissed(p, c.ctx.now, c.ctx.tz));
  sayProposals(c, 'waiting on a decision', undecided);
  sayProposals(c, 'Missed', props.filter((p) => isMissed(p, c.ctx.now, c.ctx.tz)));
  const forOf = new Map(c.d.proposals.map((p) => [p.id, p.forMemberId]));
  const todos = c.d.todos.filter((x) => !x.done && isSchool(x) && (forKid(x.ownerId) || forKid(x.proposalId ? forOf.get(x.proposalId) : undefined)));
  if (todos.length) {
    c.say('On the to-dos: ');
    todos.forEach((x, i) => c.say(`${i ? '; ' : ''}${x.title}${x.due ? `, ${whenPhrase(x.due, x.dueKind, c.ctx)}` : ''} (${memberOf(c.d, x.ownerId)})`).cite(x.noticeId));
    c.say('. ');
  }
  const coming = c.d.agenda.filter((a) => isSchool(a) && a.kind === 'event' && (a.memberIds ?? []).some(forKid) && dayOf(a.when, c.ctx.tz) >= t && dayOf(a.when, c.ctx.tz) <= addDays(t, 14) && new Date(a.end ?? a.when).getTime() > c.ctx.now.getTime());
  if (coming.length) {
    c.say('Coming up: ');
    coming.slice(0, 4).forEach((a, i) => c.say(`${i ? '; ' : ''}${a.title}, ${whenPhrase(a.when, a.dueKind, c.ctx)}`).cite(a.noticeId));
    c.say('.');
  }
  if (!undecided.length && !todos.length && !coming.length) c.say('nothing is pending.');
  undecided.slice(0, 2).forEach((p) => c.offerAccept(p));
}


/** "What about Mia?": what is coming up for them this week, what waits on a decision, their to-dos. */
export function personSummary(c: Composer, m: { id: string; name: string }) {
  const t = today(c);
  const end = addDays(t, 7);
  const items = c.d.agenda.filter((a) => a.kind !== 'reminder' && a.kind !== 'update' && (a.memberIds ?? []).includes(m.id) && dayOf(a.when, c.ctx.tz) >= t && dayOf(a.when, c.ctx.tz) <= end && new Date(a.end ?? a.when).getTime() > c.ctx.now.getTime());
  c.say(`${m.name}, this week: `);
  if (!items.length) c.say('nothing on the calendar');
  items.slice(0, 5).forEach((a, i) => c.say(`${i ? '; ' : ''}${a.title.replace(/\.$/, '')}, ${whenPhrase(a.when, a.dueKind, c.ctx)}`).cite(a.noticeId));
  c.say('. ');
  const undecided = c.d.proposals.filter((p) => open(p) && p.forMemberId === m.id && !isMissed(p, c.ctx.now, c.ctx.tz));
  sayProposals(c, 'Waiting on a decision', undecided);
  const todos = c.d.todos.filter((x) => !x.done && x.ownerId === m.id);
  if (todos.length) {
    c.say('Their to-dos: ');
    todos.slice(0, 4).forEach((x, i) => c.say(`${i ? '; ' : ''}${x.title}${x.due ? `, ${whenPhrase(x.due, x.dueKind, c.ctx)}` : ''}`).cite(x.noticeId));
    c.say('.');
  }
  undecided.slice(0, 2).forEach((p) => c.offerAccept(p));
}

/** Tried in order; the first whose pattern matches answers. */
export const TOPICS: Topic[] = [
  { id: 'monthly', test: /every month|monthly|subscriptions?|recurring|what do we pay|charges? again/i, run: (c) => (monthly(c), true) },
  { id: 'money', test: /\b(money|reserve|balance|savings|spending|budget|how are we doing|finances?)\b/i, run: (c) => (money(c), true) },
  { id: 'free', test: /\b(free|available)\b/i, run: (c) => (free(c), true) },
  { id: 'weekend', test: /\bweekend\b/i, run: (c) => (weekend(c), true) },
  { id: 'evening', test: /\b(dinner|tonight|this evening)\b/i, run: (c) => (evening(c), true) },
  { id: 'tomorrow', test: /\btomorrow\b/i, run: (c) => (tomorrow(c), true) },
  { id: 'school', test: /\b(school|homework|assignments?|teachers?)\b/i, run: (c, q) => (school(c, q), true) },
  { id: 'undecided', test: /\b(undecided|still open|to decide|not decided|pending|unanswered)\b/i, run: (c) => (listUndecided(c, 6), true) },
  { id: 'today', test: /\b(today|needs me now)\b/i, run: (c) => (todayTopic(c), true) },
  { id: 'week', test: /\b(needs? (someone|me|us|anyone)|this week|due this week|what is due|what's due|waiting|overdue|missed|worst first)\b/i, run: (c) => (week(c), true) },
];
