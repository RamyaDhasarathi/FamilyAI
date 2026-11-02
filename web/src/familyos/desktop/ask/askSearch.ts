// Ask, finding things (MASTER_AGENT.md §7 Phase 3 "Ask"): plain keyword
// matching over what the asker can see — notices (never Quarantine, never one
// restricted to someone else), proposals, calendar items, to-dos and
// recurring charges — plus the phrases the answers use for dates and state.
// No model: every answer is built from these records, so it can cite them.
import type { AgendaItem, DeskData, Member, Notice, Proposal, RecurringMerchant, Todo, When } from '../../desk/types';
import { dayKey, dayOf, fmtRelDay, fmtSlot } from '../../desk/format';
import { dateGone, isMissed } from '../../desk/selectors';

export type AskData = Pick<DeskData, 'notices' | 'proposals' | 'agenda' | 'todos' | 'recurring' | 'members' | 'plans' | 'conflicts'>;
export interface AskCtx {
  now: Date;
  tz: string;
  actor: string;
}

const STOP = new Set(
  'the a an and or of to for in on at by is are was were be been it its this that these those what whats when whens where who whom which how much many do does did we our us you your me my i can could should would will about tell more any anything some there here have has had with from please show give list need needs get got come came last next'.split(' '),
);

export const norm = (s: string) =>
  s.toLowerCase().replace(/[’‘]/g, "'").replace(/'s\b/g, '').replace(/¤\{[\d.-]+\}/g, ' ').replace(/[^a-z0-9]+/g, ' ').trim();

const stem = (w: string) => (w.length > 4 && w.endsWith('s') && !w.endsWith('ss') ? w.slice(0, -1) : w);

/** Content words of a question or a text (stop words dropped, light plural stemming). */
export function words(s: string): string[] {
  return norm(s).split(' ').filter((w) => w.length >= 3 && !STOP.has(w)).map(stem);
}

/** How many of `q` appear in `text` (a word or the start of one). */
export function overlap(q: string[], text: string): number {
  if (!q.length) return 0;
  const t = words(text);
  return q.filter((w) => t.some((x) => x === w || (w.length >= 4 && x.startsWith(w)) || (x.length >= 4 && w.startsWith(x)))).length;
}

/** Members named in the question ("Mia", "Ethan's"). */
export function namedMembers(q: string, members: Member[]): Member[] {
  const n = ` ${norm(q)} `;
  return members.filter((m) => n.includes(` ${m.name.toLowerCase()} `));
}

/** Only what the asker can see: Quarantine and notices restricted to others are out, with everything read from them. */
export function visibleData(d: AskData, actor: string): AskData {
  const notices = d.notices.filter((n) => !n.quarantined && (!n.visibleTo || n.visibleTo.includes(actor)));
  const ok = new Set(notices.map((n) => n.id));
  const fine = (x: { noticeId?: string }) => !x.noticeId || ok.has(x.noticeId);
  return { ...d, notices, proposals: d.proposals.filter(fine), agenda: d.agenda.filter(fine), todos: d.todos.filter(fine), recurring: d.recurring.filter(fine) };
}

export type Hit =
  | { type: 'proposal'; score: number; item: Proposal; noticeId: string }
  | { type: 'agenda'; score: number; item: AgendaItem; noticeId?: string }
  | { type: 'todo'; score: number; item: Todo; noticeId?: string }
  | { type: 'recurring'; score: number; item: RecurringMerchant; noticeId: string }
  | { type: 'notice'; score: number; item: Notice; noticeId: string };

/** Title match: 3 per word, plus up to 2 for how much of the title the words cover (specific beats long). */
function titleScore(q: string[], title: string, names: Set<string> = new Set()): number {
  const n = overlap(q, title);
  return n ? n * 3 + (2 * n) / Math.max(1, words(title).filter((w) => !names.has(w)).length) : 0;
}

/** Everything that matches the question's words, best first (people named in it add weight). */
export function search(d: AskData, q: string): Hit[] {
  const named = namedMembers(q, d.members);
  const nameWords = new Set(d.members.map((m) => stem(m.name.toLowerCase())));
  const asked = new Set(named.map((m) => stem(m.name.toLowerCase())));
  const topic = words(q).filter((w) => !asked.has(w));
  if (!topic.length) return [];
  const who = (ids: (string | undefined)[]) => (named.some((m) => ids.includes(m.id)) ? 2 : 0);
  const hits: Hit[] = [];
  for (const p of d.proposals) {
    const s = titleScore(topic, p.title, nameWords) + overlap(topic, p.quote ?? '');
    if (s) hits.push({ type: 'proposal', score: s + who([p.forMemberId]), item: p, noticeId: p.noticeId });
  }
  for (const a of d.agenda) {
    if (a.kind === 'reminder') continue;
    const s = titleScore(topic, a.title, nameWords) + overlap(topic, `${a.place ?? ''} ${(a.details ?? []).map(([, v]) => v).join(' ')}`);
    if (s) hits.push({ type: 'agenda', score: s + who(a.memberIds ?? []), item: a, noticeId: a.noticeId });
  }
  for (const t of d.todos) {
    const s = titleScore(topic, t.title, nameWords);
    if (s) hits.push({ type: 'todo', score: s + who([t.ownerId]), item: t, noticeId: t.noticeId });
  }
  for (const r of d.recurring) {
    const s = titleScore(topic, r.merchant);
    if (s) hits.push({ type: 'recurring', score: s, item: r, noticeId: r.noticeId });
  }
  for (const n of d.notices) {
    const s = titleScore(topic, n.title, nameWords) + overlap(topic, n.summary) * 2 + overlap(topic, n.sender) * 2 + overlap(topic, n.body);
    if (s) hits.push({ type: 'notice', score: s + who(n.memberIds ?? []), item: n, noticeId: n.id });
  }
  const rank = { proposal: 0, agenda: 1, todo: 2, recurring: 3, notice: 4 };
  return hits.sort((a, b) => b.score - a.score || rank[a.type] - rank[b.type]);
}

// ── Phrases ───────────────────────────────────────────────────────────

/** "today at 4 pm", "tomorrow at 2 pm", "on Saturday at 2 pm", "on Nov 9", "today, by end of day". */
export function whenPhrase(w: When, kind: Proposal['dueKind'] | undefined, ctx: AskCtx): string {
  const day = fmtRelDay(dayOf(w, ctx.tz), dayKey(ctx.now, ctx.tz));
  const d = /^(Today|Tomorrow|Yesterday)$/.test(day) ? day.toLowerCase() : `on ${day}`;
  const slot = fmtSlot(w, kind, ctx.tz);
  if (slot === 'EOD') return `${d}, by end of day`;
  if (slot === 'all day' || slot === 'not specified') return d;
  return `${d} at ${slot}`;
}

/** whenPhrase after a title, without repeating a time the title already says ("…starts at 5:30 pm, today"). */
export function whenAfter(title: string, w: When, kind: Proposal['dueKind'] | undefined, ctx: AskCtx): string {
  const phrase = whenPhrase(w, kind, ctx);
  const slot = fmtSlot(w, kind, ctx.tz);
  return norm(title).includes(norm(slot)) ? phrase.replace(` at ${slot}`, '') : phrase;
}

/** Where a proposal stands, in the honest words of MASTER §10. */
export function statePhrase(p: Proposal, ctx: AskCtx, d: AskData): string {
  if (isMissed(p, ctx.now, ctx.tz)) return 'nobody accepted or dismissed it, and the date has gone';
  if (p.state === 'changed') return 'the notice changed after it was accepted, so it needs a look';
  if (p.state === 'dismissed') return 'it was dismissed';
  if (p.state === 'accepted') {
    const todo = p.created?.todoId ? d.todos.find((t) => t.id === p.created!.todoId) : undefined;
    return todo ? `it is accepted and on the to-dos${todo.done ? ', done' : ''}` : 'it is accepted and on the calendar';
  }
  return dateGone(p, ctx.now, ctx.tz) ? 'nobody has accepted it yet, and the date has gone' : 'it is still undecided';
}

export const memberOf = (d: AskData, id?: string) => (id ? d.members.find((m) => m.id === id)?.name ?? '' : '');
