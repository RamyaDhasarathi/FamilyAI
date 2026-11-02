// Time context for the seed: every date in the desk dataset is built
// relative to the moment the app loads, in the household's timezone, so the
// demo always has a "today" (MASTER_AGENT.md §9).
import { addDays, dayDiff, dayKey, nextWeekday, zoned } from '../format';
import type { Day, Instant } from '../types';

export interface SeedCtx {
  now: Date;
  tz: string;
  today: Day;
  /** Day `n` days from today. */
  day(n: number): Day;
  /** Instant at hh:mm on the day `n` days from today. */
  at(n: number, hh: number, mm?: number): Instant;
  /** Instant `mins` minutes before now. */
  ago(mins: number): Instant;
  /**
   * A moment in the family's history: like `at`, but today's history is
   * compressed into [midnight, now) when the app loads early, so nothing that
   * "already happened" lands in the future and the order is kept.
   */
  past(n: number, hh: number, mm?: number): Instant;
  /** Next Saturday / Friday strictly after today (the recital, the project). */
  saturday: Day;
  friday: Day;
  /** Offset in days of a Day from today. */
  offset(day: Day): number;
}

/** The latest wall-clock time used for today's seeded history (11:15 am). */
const HISTORY_END_MIN = 11 * 60 + 15;

export function makeCtx(now: Date, tz: string): SeedCtx {
  const today = dayKey(now, tz);
  const day = (n: number) => addDays(today, n);
  const saturday = nextWeekday(today, 6);
  const friday = nextWeekday(today, 5);
  const at = (n: number, hh: number, mm = 0) => zoned(day(n), hh, mm, tz);
  const midnight = new Date(at(0, 0)).getTime();
  const nowMin = (now.getTime() - midnight) / 60000;
  const squeeze = Math.max(0, Math.min(1, (nowMin - 1) / HISTORY_END_MIN));
  return {
    now,
    tz,
    today,
    day,
    at,
    ago: (mins) => new Date(now.getTime() - mins * 60000).toISOString(),
    saturday,
    friday,
    offset: (d) => dayDiff(today, d),
    past: (n, hh, mm = 0) => (n !== 0 ? at(n, hh, mm) : new Date(midnight + (hh * 60 + mm) * squeeze * 60000).toISOString()),
  };
}
