// Inbox, the logic (MASTER_AGENT.md §7 Phase 3; FamilyOS.mp4 3:50–4:20 and
// 9:30, frames f_047–f_052, f_114). Pure functions of the desk data:
//  • status of a notice: To do (something on it is undecided), Done (all
//    decided), Nothing asked (no proposals);
//  • the filter chips with counts — each chip counts what you would see if
//    you picked it, given the other filters;
//  • promotions and newsletters that ask nothing are kept out of the way
//    under "Everything" (and counted, so nothing is hidden silently);
//  • Dates spotted (undecided proposals by date) and Handling (open notices
//    per person who can handle them, plus "Nobody yet").
// Quarantined notices and notices the actor may not see never appear.
import type { DeskData, Member, Notice, NoticeCategory, NoticeSource, Proposal, When } from '../../desk/types';
import { dayOf, isDay } from '../../desk/format';
import { dateGone, isMissed } from '../../desk/selectors';
import { handlerOf } from '../../desk/ext/phase3';

export type NoticeStatus = 'todo' | 'done' | 'nothing';
export type StatusFilter = NoticeStatus | 'all';
export type CategoryFilter = 'everything' | NoticeCategory;
/** A member id, or 'nobody' for open notices nobody has taken on. */
export type WhoFilter = string | null;

export const STATUS_ORDER: StatusFilter[] = ['todo', 'done', 'nothing', 'all'];
export const STATUS_LABELS: Record<StatusFilter, string> = { todo: 'To do', done: 'Done', nothing: 'Nothing asked', all: 'All' };
export const CATEGORY_ORDER: NoticeCategory[] = ['school', 'bills', 'health', 'home', 'family', 'travel', 'shopping', 'subscription', 'trading', 'receipt', 'promo', 'newsletter'];
export const CATEGORY_LABELS: Record<NoticeCategory, string> = {
  school: 'School', bills: 'Bills', health: 'Health', home: 'Home', family: 'Family', travel: 'Travel', shopping: 'Shopping',
  subscription: 'Subscription', trading: 'Trading', receipt: 'Receipts', promo: 'Promo', newsletter: 'Newsletter',
};
const QUIET: NoticeCategory[] = ['promo', 'newsletter'];
const SOURCE_WORD: Record<NoticeSource, string> = { email: 'email', phone: 'your phone', telegram: 'Telegram', whatsapp: 'WhatsApp', paste: 'pasted', site: 'a site' };
/** "via email", "via your phone"… */
export const sourceWord = (s: NoticeSource) => SOURCE_WORD[s];

/** Still needs a person: proposed, changed after it was accepted, or missed (only ✕ is left). */
export const isOpen = (p: Proposal) => p.state === 'proposed' || p.state === 'changed' || p.state === 'missed';

/** Notices the actor can see: not held in Quarantine, and not restricted to others. */
export const canSee = (n: Notice, actor: string) => !n.quarantined && (!n.visibleTo || n.visibleTo.includes(actor));

export function statusOf(proposals: Proposal[]): NoticeStatus {
  if (!proposals.length) return 'nothing';
  return proposals.some(isOpen) ? 'todo' : 'done';
}

export interface NoticeRowData {
  notice: Notice;
  status: NoticeStatus;
  /** "N to decide". */
  open: number;
  /** The earliest date on what is still open (the row's right-hand date). */
  firstDue?: { due: When; dueKind?: Proposal['dueKind'] };
  handler: string | null;
  quiet: boolean;
}

export interface InboxQuery {
  show: StatusFilter;
  cat: CategoryFilter;
  who?: WhoFilter;
}

export interface InboxView {
  rows: NoticeRowData[];
  statusCounts: Record<StatusFilter, number>;
  categories: { id: NoticeCategory; label: string; count: number }[];
  /** Promotions and newsletters that ask nothing, left out under "Everything". */
  kept: number;
  total: number;
}

const startMs = (w: When) => (isDay(w) ? Date.parse(`${w}T00:00:00Z`) : Date.parse(w));

/** One row per visible notice, newest first. */
export function noticeRows(d: Pick<DeskData, 'notices' | 'proposals'>, actor: string): NoticeRowData[] {
  const byNotice = new Map<string, Proposal[]>();
  for (const p of d.proposals) byNotice.set(p.noticeId, [...(byNotice.get(p.noticeId) ?? []), p]);
  return d.notices
    .filter((n) => canSee(n, actor))
    .map((n) => {
      const ps = byNotice.get(n.id) ?? [];
      const open = ps.filter(isOpen);
      const dated = open.filter((p) => p.due).sort((a, b) => startMs(a.due!) - startMs(b.due!));
      const status = statusOf(ps);
      return {
        notice: n, status, open: open.length, handler: handlerOf(n),
        firstDue: dated[0] ? { due: dated[0].due!, dueKind: dated[0].dueKind } : undefined,
        quiet: QUIET.includes(n.category) && status !== 'todo',
      };
    })
    .sort((a, b) => b.notice.receivedAt.localeCompare(a.notice.receivedAt));
}

const whoMatch = (r: NoticeRowData, who?: WhoFilter) => !who || (who === 'nobody' ? r.handler === null : r.handler === who);
const showMatch = (r: NoticeRowData, show: StatusFilter) => show === 'all' || r.status === show;
const catMatch = (r: NoticeRowData, cat: CategoryFilter) => (cat === 'everything' ? !r.quiet : r.notice.category === cat);

export function inboxView(d: Pick<DeskData, 'notices' | 'proposals'>, qy: InboxQuery, actor: string): InboxView {
  const all = noticeRows(d, actor).filter((r) => whoMatch(r, qy.who));
  const inCat = all.filter((r) => catMatch(r, qy.cat));
  const statusCounts = Object.fromEntries(STATUS_ORDER.map((s) => [s, inCat.filter((r) => showMatch(r, s)).length])) as Record<StatusFilter, number>;
  const inShow = all.filter((r) => showMatch(r, qy.show));
  const present = new Set(noticeRows(d, actor).map((r) => r.notice.category));
  const categories = CATEGORY_ORDER.filter((c) => present.has(c)).map((c) => ({ id: c, label: CATEGORY_LABELS[c], count: inShow.filter((r) => r.notice.category === c).length }));
  const kept = qy.cat === 'everything' ? inShow.filter((r) => r.quiet).length : 0;
  return { rows: inShow.filter((r) => catMatch(r, qy.cat)), statusCounts, categories, kept, total: all.length };
}

/** Read the filters from the URL (?show=todo&cat=school&who=m_sarah); unknown values fall back to the defaults. */
export function parseQuery(params: URLSearchParams): InboxQuery {
  const show = params.get('show') as StatusFilter | null;
  const cat = params.get('cat') as CategoryFilter | null;
  return {
    show: show && STATUS_ORDER.includes(show) ? show : 'todo',
    cat: cat && (cat === 'everything' || CATEGORY_ORDER.includes(cat as NoticeCategory)) ? cat : 'everything',
    who: params.get('who') || null,
  };
}

/** Dates spotted: undecided proposals on visible notices by date (no date last); missed ones live on Waiting on you. */
export function datesSpotted(d: Pick<DeskData, 'notices' | 'proposals'>, now: Date, tz: string, actor: string): Proposal[] {
  const seen = new Set(d.notices.filter((n) => canSee(n, actor)).map((n) => n.id));
  return d.proposals
    .filter((p) => (p.state === 'proposed' || p.state === 'changed') && seen.has(p.noticeId) && !isMissed(p, now, tz))
    .sort((a, b) => {
      if (!a.due !== !b.due) return a.due ? -1 : 1;
      if (!a.due || !b.due) return a.createdAt.localeCompare(b.createdAt);
      return dayOf(a.due, tz).localeCompare(dayOf(b.due, tz)) || startMs(a.due) - startMs(b.due);
    });
}

/** The Dates spotted sub-line: what it is and whether its date has gone. */
export function spottedLine(p: Proposal, person: string, now: Date, tz: string): string {
  const what = { task: 'to do', calendar: 'event', reminder: 'reminder', payment: 'pay · nothing here pays', errand: 'errand' }[p.kind];
  return [what, person, p.state === 'changed' ? 'changed' : dateGone(p, now, tz) ? 'date gone' : ''].filter(Boolean).join(' · ');
}

export interface HandlingRow {
  /** Member id, or null for "Nobody yet". */
  id: string | null;
  name: string;
  initial: string;
  count: number;
}

/** Handling · open notices: everyone with an account (children cannot handle), then "Nobody yet". */
export function handling(d: Pick<DeskData, 'notices' | 'proposals'> & { members: Member[] }, actor: string): HandlingRow[] {
  const open = noticeRows(d, actor).filter((r) => r.status === 'todo');
  const people = d.members.filter((m) => m.hasAccount);
  const rows: HandlingRow[] = people.map((m) => ({ id: m.id, name: m.name, initial: m.initial, count: open.filter((r) => r.handler === m.id).length }));
  rows.push({ id: null, name: 'Nobody yet', initial: '?', count: open.filter((r) => r.handler === null).length });
  return rows;
}

export interface BodySeg {
  text: string;
  /** The claim number this span was read into (absent = plain text). */
  n?: number;
}

/**
 * "Read from this notice": split the notice text into plain and highlighted
 * spans, one per claim whose quote is found in it (first occurrence; a quote
 * overlapping an earlier one is not marked twice). Quotes not in the text
 * are reported as `missing`, so the drawer can say "check before relying on it".
 */
export function markQuotes(body: string, quotes: { n: number; quote?: string }[]): { segs: BodySeg[]; found: Map<number, [number, number]>; missing: number[] } {
  const found = new Map<number, [number, number]>();
  const missing: number[] = [];
  for (const { n, quote } of quotes) {
    const at = quote ? body.indexOf(quote) : -1;
    if (!quote || at < 0) missing.push(n);
    else found.set(n, [at, at + quote.length]);
  }
  const spans = [...found.entries()].sort((a, b) => a[1][0] - b[1][0]);
  const segs: BodySeg[] = [];
  let pos = 0;
  for (const [n, [a, b]] of spans) {
    if (a < pos) continue;
    if (a > pos) segs.push({ text: body.slice(pos, a) });
    segs.push({ text: body.slice(a, b), n });
    pos = b;
  }
  if (pos < body.length) segs.push({ text: body.slice(pos) });
  return { segs, found, missing };
}
