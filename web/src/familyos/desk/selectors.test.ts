// MASTER_AGENT.md §11 "Tests to add": the Today selector (today-only, sort,
// tie order, Nov 9 / Saturday excluded, "Reminder · tomorrow", timezone edges
// at 23:59 / 00:01) and Waiting on you grouping with missed detection.
import { describe, expect, it } from 'vitest';
import { buildDeskData } from './data';
import { addDays, dayKey, zoned } from './format';
import { agentChips, comingUp, dayProgress, isMissed, needsSomeone, todayItems, waitingGroups } from './selectors';
import type { AgendaItem, AgentId, Proposal } from './types';

const TZ = 'America/New_York';
// The recording's date: Wednesday, October 28, 2026, 2:40 pm in New York.
const NOW = new Date(zoned('2026-10-28', 14, 40, TZ));
const D = buildDeskData(NOW, TZ);

const item = (id: string, agent: AgentId, when: string, extra: Partial<AgendaItem> = {}): AgendaItem => ({
  id, agent, kind: 'event', title: id, when, dueKind: 'time', createdAt: zoned('2026-10-20', 9, 0, TZ), ...extra,
});

describe('todayItems', () => {
  const rows = todayItems(D, NOW, TZ);
  const ids = rows.map((r) => r.id);

  it('lists only today’s items: timed by time, then “Anytime today”', () => {
    expect(ids).toEqual(['a_pt', 'a_rehearsal', 'a_electrician', 'a_soccer', 'a_delivery', 'a_reserve', 'a_mortgage', 'a_final_reminder']);
    expect(rows.filter((r) => r.timed).map((r) => r.slot)).toEqual(['9 am', '3:30 pm', '4 pm', '5 pm', '6 pm']);
    expect(rows.filter((r) => !r.timed).every((r) => r.at === undefined)).toBe(true);
  });

  it('includes the electrician, reserve, delivery, mortgage, today’s calendar and education items', () => {
    expect(ids).toEqual(expect.arrayContaining(['a_electrician', 'a_reserve', 'a_delivery', 'a_mortgage', 'a_pt', 'a_rehearsal', 'a_soccer', 'a_final_reminder']));
  });

  it('excludes the furnace service (12 days out), Saturday’s recital and tomorrow’s events', () => {
    for (const id of ['a_furnace', 'a_recital', 'a_dentist', 'a_final', 'a_client_call', 'a_conference']) expect(ids).not.toContain(id);
  });

  it('labels a reminder created today about tomorrow “Reminder · tomorrow”, and drops one created yesterday', () => {
    expect(rows.find((r) => r.id === 'a_final_reminder')?.label).toBe('Reminder · tomorrow');
    const stale = item('old_reminder', 'education', '2026-10-28', { kind: 'reminder', dueKind: 'allDay', remindsOf: '2026-10-29', createdAt: zoned('2026-10-27', 18, 0, TZ) });
    expect(todayItems({ agenda: [stale], todos: [] }, NOW, TZ)).toEqual([]);
  });

  it('breaks same-time ties Calendar, Household, Finance, Education, Grocery', () => {
    const at = zoned('2026-10-28', 16, 0, TZ);
    const agenda = (['grocery', 'education', 'finance', 'household', 'calendar'] as AgentId[]).map((a) => item(`x_${a}`, a, at));
    expect(todayItems({ agenda, todos: [] }, NOW, TZ).map((r) => r.agent)).toEqual(['calendar', 'household', 'finance', 'education', 'grocery']);
    const untimed = agenda.map((a) => ({ ...a, when: '2026-10-28', dueKind: 'allDay' as const }));
    expect(todayItems({ agenda: untimed, todos: [] }, NOW, TZ).map((r) => r.agent)).toEqual(['calendar', 'household', 'finance', 'education', 'grocery']);
  });

  it('decides “today” in the household timezone at 23:59 and 00:01', () => {
    const tz = 'America/Los_Angeles';
    const now = new Date(zoned('2026-10-28', 12, 0, tz));
    const agenda = [
      item('yesterday_2359', 'calendar', zoned('2026-10-27', 23, 59, tz)),
      item('today_0001', 'calendar', zoned('2026-10-28', 0, 1, tz)),
      item('today_2359', 'calendar', zoned('2026-10-28', 23, 59, tz)),
      item('tomorrow_0001', 'calendar', zoned('2026-10-29', 0, 1, tz)),
    ];
    expect(todayItems({ agenda, todos: [] }, now, tz).map((r) => r.id)).toEqual(['today_0001', 'today_2359']);
    // The same instants seen from UTC fall on other days.
    expect(dayKey(zoned('2026-10-28', 23, 59, tz), 'UTC')).toBe('2026-10-29');
    // And "now" itself at the edges of the local day.
    for (const [hh, mm] of [[0, 1], [23, 59]]) {
      const edge = new Date(zoned('2026-10-28', hh, mm, tz));
      expect(todayItems({ agenda, todos: [] }, edge, tz).map((r) => r.id)).toEqual(['today_0001', 'today_2359']);
    }
  });

  it('shows the empty state when nothing is dated today', () => {
    expect(todayItems({ agenda: [], todos: [] }, NOW, TZ)).toEqual([]);
  });

  it('feeds the hero: chips, done / remaining and the next item', () => {
    expect(agentChips(rows).map((c) => `${c.agent}:${c.text}`)).toEqual([
      'household:Electrician 4 pm', 'finance:Mortgage due', 'education:1 update', 'grocery:Delivery 6 pm', 'calendar:3 events',
    ]);
    const p = dayProgress(rows, NOW);
    expect(p).toMatchObject({ done: 1, remaining: 7, total: 8 });
    expect(p.next?.id).toBe('a_rehearsal');
  });
});

describe('waitingGroups', () => {
  const v = waitingGroups(D, NOW, TZ);
  const g = Object.fromEntries(v.groups.map((x) => [x.id, x.items.map((p) => p.id)]));

  it('groups undecided proposals Overdue / This week / Later / No date', () => {
    expect(g.overdue).toEqual(['p_library']);
    expect(g.thisWeek).toEqual(['p_soccer', 'p_tripform', 'p_rx', 'p_seats', 'p_insurance']);
    expect(g.later).toEqual(['p_trip']);
    expect(g.noDate).toEqual(['p_flu']);
    expect(v.groups.map((x) => x.label)).toEqual(['Overdue', 'This week', 'Later', 'No date']);
  });

  it('keeps missed items apart: calendar / reminder proposals whose date has gone, or marked missed', () => {
    expect(v.missed.map((p) => p.id)).toEqual(['p_yearbook', 'p_streamly', 'p_picture']);
    expect(v.count).toBe(11);
  });

  it('detects missed by time for timed proposals, and never for decided ones', () => {
    const p: Proposal = { id: 'x', noticeId: 'n', kind: 'calendar', agent: 'calendar', title: 'x', due: zoned('2026-10-28', 9, 0, TZ), dueKind: 'time', state: 'proposed', createdAt: NOW.toISOString() };
    expect(isMissed(p, NOW, TZ)).toBe(true);
    expect(isMissed({ ...p, due: zoned('2026-10-28', 18, 0, TZ) }, NOW, TZ)).toBe(false);
    expect(isMissed({ ...p, state: 'accepted' }, NOW, TZ)).toBe(false);
    expect(isMissed({ ...p, kind: 'task' }, NOW, TZ)).toBe(false);
    expect(isMissed({ ...p, state: 'missed', due: undefined }, NOW, TZ)).toBe(true);
  });
});

describe('needsSomeone', () => {
  it('orders worst first: Missed → Overdue → Today → Changed', () => {
    const cards = needsSomeone(D, NOW, TZ);
    expect(cards.map((c) => `${c.tone}:${c.id}`)).toEqual([
      'missed:p_yearbook', 'missed:p_streamly', 'missed:p_picture',
      'overdue:p_library', 'overdue:t_gutters',
      'today:p_tripform', 'today:p_rx',
      'changed:p_soccer',
    ]);
    expect(cards.every((c) => D.notices.some((n) => n.id === c.noticeId))).toBe(true);
    expect(cards.find((c) => c.id === 't_gutters')?.line).toBe('the family accepted this, and the date has gone');
    expect(cards.find((c) => c.id === 'p_soccer')?.line).toBe('the notice changed after it was accepted: was 5 pm, now 5:30 pm');
  });
});

describe('comingUp', () => {
  it('groups what comes after today by day, both clashing items tomorrow', () => {
    const days = comingUp(D, NOW, TZ);
    expect(days[0].label).toBe('Tomorrow');
    expect(days[0].day).toBe(addDays('2026-10-28', 1));
    expect(days[0].entries.map((e) => e.id)).toEqual(['a_dentist', 'a_client_call', 'a_final']);
    expect(days.flatMap((d) => d.entries).some((e) => e.id === 'a_furnace')).toBe(true);
    expect(days.flatMap((d) => d.entries).find((e) => e.id === 'p_insurance')?.undecided).toBe(true);
    expect(days.every((d) => d.day > '2026-10-28')).toBe(true);
  });
});
