// React helpers over the desk store: a ticking "now", the household's
// formatters (timezone + currency from settings), and memoised selector
// hooks that every desktop page shares.
import { useEffect, useMemo, useState } from 'react';
import { useDesk } from './store';
import { dayKey, fmtAgo, fmtMoney, fmtRelDay, fmtSlot, fmtText, fmtTime, fmtWhen, dayOf } from './format';
import { comingUp, needsSomeone, todayItems, waitingGroups } from './selectors';
import type { DueKind, Instant, When } from './types';

/** The current time, refreshed every `ms` (default one minute). */
export function useNow(ms = 60000): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), ms);
    return () => window.clearInterval(id);
  }, [ms]);
  return now;
}

/**
 * Household formatters. Render every desk string through `text()` (money
 * tokens) and every amount through `money()`, so the one currency setting
 * re-formats the whole app.
 */
export function useDeskFormat(now?: Date) {
  const currency = useDesk((s) => s.settings.currency);
  const tz = useDesk((s) => s.settings.timezone);
  const at = now ?? new Date();
  const today = dayKey(at, tz);
  return useMemo(
    () => ({
      tz,
      currency,
      today,
      money: (n: number) => fmtMoney(n, currency),
      text: (s: string) => fmtText(s, currency),
      time: (i: Instant, short = true) => fmtTime(i, tz, short),
      day: (w: When) => fmtRelDay(dayOf(w, tz), today),
      slot: (w: When, k?: DueKind) => fmtSlot(w, k, tz),
      when: (w: When, k?: DueKind) => fmtWhen(w, k, tz, today),
      ago: (i: Instant) => fmtAgo(i, at, tz),
    }),
    // `at` changes every render when no `now` is passed; `today` captures what matters.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [tz, currency, today, now]
  );
}

export function useTodayItems(now: Date) {
  const agenda = useDesk((s) => s.agenda);
  const todos = useDesk((s) => s.todos);
  const tz = useDesk((s) => s.settings.timezone);
  return useMemo(() => todayItems({ agenda, todos }, now, tz), [agenda, todos, now, tz]);
}

export function useNeedsSomeone(now: Date) {
  const proposals = useDesk((s) => s.proposals);
  const todos = useDesk((s) => s.todos);
  const tz = useDesk((s) => s.settings.timezone);
  return useMemo(() => needsSomeone({ proposals, todos }, now, tz), [proposals, todos, now, tz]);
}

export function useWaiting(now: Date) {
  const proposals = useDesk((s) => s.proposals);
  const tz = useDesk((s) => s.settings.timezone);
  return useMemo(() => waitingGroups({ proposals }, now, tz), [proposals, now, tz]);
}

export function useComingUp(now: Date, opts?: { days?: number; includeToday?: boolean }) {
  const agenda = useDesk((s) => s.agenda);
  const proposals = useDesk((s) => s.proposals);
  const todos = useDesk((s) => s.todos);
  const tz = useDesk((s) => s.settings.timezone);
  const days = opts?.days;
  const includeToday = opts?.includeToday;
  return useMemo(() => comingUp({ agenda, proposals, todos }, now, tz, { days, includeToday }), [agenda, proposals, todos, now, tz, days, includeToday]);
}
