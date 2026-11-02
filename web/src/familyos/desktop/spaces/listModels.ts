// Travel, Investments, Errands and Grocery helpers for the Phase 4 pages
// (MASTER_AGENT.md §7 Phase 4; FamilyOS.mp4 3:00–3:20 Travel + Plan, 3:40
// Investments, 5:50 Errands, 1:50 Order again). Pure functions; the space
// timeline and money views live in spaceModel.ts.
import type { Errand, Plan, Statement, Todo } from '../../desk/types';
import { addDays, dayKey } from '../../desk/format';
import { round2, whenMs } from './spaceModel';

// ── Travel ─────────────────────────────────────────────────────────────

export interface TripView {
  toBook: number;
  booked: number;
  toDo: number;
  done: number;
  /** Estimated cost of what is still to book / already booked. */
  estToBook: number;
  estBooked: number;
}

export function tripView(plan: Plan, todos: Todo[]): TripView {
  const mine = todos.filter((t) => t.planId === plan.id);
  const open = plan.bookings.filter((b) => !b.booked);
  const sum = (xs: { estCost: number }[]) => xs.reduce((s, b) => s + b.estCost, 0);
  return {
    toBook: open.length, booked: plan.bookings.length - open.length, toDo: mine.filter((t) => !t.done).length, done: mine.filter((t) => t.done).length,
    estToBook: sum(open), estBooked: sum(plan.bookings.filter((b) => b.booked)),
  };
}

/** A plan's to-dos: open first (dated soonest, then undated), done last. */
export function planTodoOrder(todos: Todo[], tz: string): Todo[] {
  const key = (t: Todo) => (t.due ? whenMs(t.due, t.dueKind ?? 'allDay', tz) : Number.MAX_SAFE_INTEGER);
  return [...todos].sort((a, b) => Number(a.done) - Number(b.done) || key(a) - key(b) || a.createdAt.localeCompare(b.createdAt));
}

// ── Investments ───────────────────────────────────────────────────────

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

/** Statements newest first, grouped by month ("October 2026"). */
export function statementsByMonth(list: Statement[]): { key: string; label: string; items: Statement[] }[] {
  const sorted = [...list].sort((a, b) => b.date.localeCompare(a.date) || a.title.localeCompare(b.title));
  const groups: { key: string; label: string; items: Statement[] }[] = [];
  for (const s of sorted) {
    const key = s.date.slice(0, 7);
    let g = groups.find((x) => x.key === key);
    if (!g) {
      g = { key, label: `${MONTHS[Number(key.slice(5, 7)) - 1]} ${key.slice(0, 4)}`, items: [] };
      groups.push(g);
    }
    g.items.push(s);
  }
  return groups;
}

/** Bought (trades) and dividends paid over the last `days` days, from the statements. */
export function investActivity(list: Statement[], now: Date, tz: string, days = 90) {
  const from = addDays(dayKey(now, tz), -days);
  const recent = list.filter((s) => s.date >= from);
  const sum = (k: Statement['kind']) => round2(recent.filter((s) => s.kind === k).reduce((n, s) => n + (s.amount ?? 0), 0));
  return { bought: sum('trade'), dividends: sum('dividend'), statements: recent.filter((s) => s.kind === 'statement').length };
}

// ── Errands (Household) ───────────────────────────────────────────────

const ERRAND_ORDER: Errand['status'][] = ['proposed', 'approved', 'done', 'cancelled'];

/** Waiting for approval first, then approved, done, cancelled; newest first within each. */
export const sortErrands = (list: Errand[]) =>
  [...list].sort((a, b) => ERRAND_ORDER.indexOf(a.status) - ERRAND_ORDER.indexOf(b.status) || b.createdAt.localeCompare(a.createdAt));

// ── Grocery: a reorder written down as an errand (nothing is bought) ──

/** Host of a URL for "Where" lines ("freshcart.example"). */
export const hostOf = (url: string) => {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
};

/** The most a reorder may cost: the last price plus 15 %, rounded up to a whole amount. */
export const reorderCap = (price: number) => Math.ceil(price * 1.15);
