// Timezone-aware date helpers and currency formatting for the desk data
// (MASTER_AGENT.md §9 rules). Every "is this today?" question goes through
// `dayOf(when, tz)`, computed with Intl in the household's IANA timezone, so
// 23:59 and 00:01 land on the right side of midnight wherever the browser is.
// Amounts follow one household setting: `currency` (USD by default; 'INR'
// switches symbols and digit grouping everywhere).
import type { Day, DueKind, Instant, When } from './types';

// ── Days and instants ─────────────────────────────────────────────────

export function localTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  } catch {
    return 'UTC';
  }
}

const partFmt = new Map<string, Intl.DateTimeFormat>();
function fmtFor(tz: string) {
  let f = partFmt.get(tz);
  if (!f) {
    f = new Intl.DateTimeFormat('en-US', {
      timeZone: tz, hourCycle: 'h23', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit',
    });
    partFmt.set(tz, f);
  }
  return f;
}

/** Wall-clock parts of an instant in a timezone. */
export function zonedParts(at: Date | Instant, tz: string) {
  const d = typeof at === 'string' ? new Date(at) : at;
  const p: Record<string, number> = {};
  for (const x of fmtFor(tz).formatToParts(d)) if (x.type !== 'literal') p[x.type] = Number(x.value);
  return { y: p.year, mo: p.month, d: p.day, h: p.hour === 24 ? 0 : p.hour, mi: p.minute, s: p.second };
}

const pad = (n: number) => String(n).padStart(2, '0');
const splitDay = (day: Day) => day.split('-').map(Number) as [number, number, number];

export const isDay = (w: string): boolean => /^\d{4}-\d{2}-\d{2}$/.test(w);

/** The calendar day of an instant in a timezone. */
export function dayKey(at: Date | Instant, tz: string): Day {
  const p = zonedParts(at, tz);
  return `${p.y}-${pad(p.mo)}-${pad(p.d)}`;
}

/** The household-local Day of any When. */
export const dayOf = (w: When, tz: string): Day => (isDay(w) ? w : dayKey(w, tz));

export function addDays(day: Day, n: number): Day {
  const [y, m, d] = splitDay(day);
  const t = new Date(Date.UTC(y, m - 1, d + n));
  return `${t.getUTCFullYear()}-${pad(t.getUTCMonth() + 1)}-${pad(t.getUTCDate())}`;
}

/** Whole days from a to b (b − a). */
export function dayDiff(a: Day, b: Day): number {
  const [y1, m1, d1] = splitDay(a);
  const [y2, m2, d2] = splitDay(b);
  return Math.round((Date.UTC(y2, m2 - 1, d2) - Date.UTC(y1, m1 - 1, d1)) / 86400000);
}

/** 0 = Sunday … 6 = Saturday. */
export function weekday(day: Day): number {
  const [y, m, d] = splitDay(day);
  return new Date(Date.UTC(y, m - 1, d)).getUTCDay();
}

/** The next given weekday strictly after `day`. */
export function nextWeekday(day: Day, wd: number): Day {
  const k = (wd - weekday(day) + 7) % 7 || 7;
  return addDays(day, k);
}

/** The instant at hh:mm wall-clock time on `day` in `tz` (DST-safe). */
export function zoned(day: Day, hh: number, mm: number, tz: string): Instant {
  const [y, m, d] = splitDay(day);
  const wall = Date.UTC(y, m - 1, d, hh, mm);
  const offset = (ms: number) => {
    const p = zonedParts(new Date(ms), tz);
    return Date.UTC(p.y, p.mo - 1, p.d, p.h, p.mi, p.s) - Math.floor(ms / 1000) * 1000;
  };
  let t = wall - offset(wall);
  const o2 = offset(t);
  if (wall - o2 !== t) t = wall - o2;
  return new Date(t).toISOString();
}

/** Minutes since local midnight (sorting timed items within a day). */
export function minuteOfDay(at: Instant, tz: string): number {
  const p = zonedParts(at, tz);
  return p.h * 60 + p.mi;
}

// ── Display ───────────────────────────────────────────────────────────

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

/** "4:00 pm" (or "4 pm" with `short`), in the app's lower-case style. */
export function fmtTime(at: Instant, tz: string, short = false): string {
  const p = zonedParts(at, tz);
  const h = p.h % 12 || 12;
  const ap = p.h < 12 ? 'am' : 'pm';
  return short && p.mi === 0 ? `${h} ${ap}` : `${h}:${pad(p.mi)} ${ap}`;
}

export const fmtWeekday = (day: Day) => WEEKDAYS[weekday(day)];
/** "Wednesday, October 28". */
export const fmtLongDay = (day: Day) => `${fmtWeekday(day)}, ${MONTHS[splitDay(day)[1] - 1]} ${splitDay(day)[2]}`;
/** "Oct 28". */
export const fmtShortDay = (day: Day) => `${MONTHS[splitDay(day)[1] - 1].slice(0, 3)} ${splitDay(day)[2]}`;

/** "Today" · "Tomorrow" · "Yesterday" · "Friday" (within the week ahead) · "Nov 9". */
export function fmtRelDay(day: Day, today: Day): string {
  const k = dayDiff(today, day);
  if (k === 0) return 'Today';
  if (k === 1) return 'Tomorrow';
  if (k === -1) return 'Yesterday';
  if (k > 1 && k < 7) return fmtWeekday(day);
  return fmtShortDay(day);
}

/** Time column text: "4 pm", "all day", "EOD", "not specified". */
export function fmtSlot(w: When, kind: DueKind | undefined, tz: string): string {
  if (!isDay(w) && (kind === 'time' || kind === undefined)) return fmtTime(w, tz, true);
  if (kind === 'eod') return 'EOD';
  if (kind === 'notSpecified') return 'not specified';
  return 'all day';
}

/** "Today · 4 pm", "Tomorrow · all day", "Nov 9 · 10 am". */
export function fmtWhen(w: When, kind: DueKind | undefined, tz: string, today: Day): string {
  return `${fmtRelDay(dayOf(w, tz), today)} · ${fmtSlot(w, kind, tz)}`;
}

/** "just now", "12 min ago", "3 h ago", "yesterday", "3 days ago", "Oct 4". */
export function fmtAgo(at: Instant, now: Date, tz: string): string {
  const mins = Math.round((now.getTime() - new Date(at).getTime()) / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins} min ago`;
  const days = dayDiff(dayKey(at, tz), dayKey(now, tz));
  if (days === 0) return `${Math.floor(mins / 60)} h ago`;
  if (days === 1) return 'yesterday';
  if (days < 7) return `${days} days ago`;
  return fmtShortDay(dayKey(at, tz));
}

// ── Money ─────────────────────────────────────────────────────────────

const LOCALES: Record<string, string> = { USD: 'en-US', INR: 'en-IN', GBP: 'en-GB', EUR: 'en-IE', CAD: 'en-CA', AUD: 'en-AU' };
export const localeFor = (currency: string) => LOCALES[currency] ?? 'en-US';

/** "$12,450" · "$86.40" · "₹12,450" (whole amounts drop the cents). */
export function fmtMoney(n: number, currency: string): string {
  const whole = Math.abs(n % 1) < 1e-9;
  return new Intl.NumberFormat(localeFor(currency), {
    style: 'currency', currency, minimumFractionDigits: whole ? 0 : 2, maximumFractionDigits: 2,
  }).format(n);
}

/** Money token for prose in the seed data: `Reserve is ${m(12450)}` → "Reserve is ¤{12450}". */
export const m = (n: number) => `¤{${n}}`;

/** Render the money tokens in a desk string with the household currency. */
export function fmtText(s: string, currency: string): string {
  return s.includes('¤{') ? s.replace(/¤\{(-?[\d.]+)\}/g, (_, v: string) => fmtMoney(Number(v), currency)) : s;
}
