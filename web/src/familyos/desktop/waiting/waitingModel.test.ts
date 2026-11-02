// MASTER_AGENT.md §7 Phase 3 "Waiting on you", §3.3.3 / §10 honest state
// lines: due text, missed / changed / overdue lines, clashes ("Friday is
// tight: clashes with … — move one?"), the To-dos rail, Worth doing and You
// will be told.
import { describe, expect, it } from 'vitest';
import { buildDeskData } from '../../desk/data';
import { dayKey, zoned } from '../../desk/format';
import type { Proposal } from '../../desk/types';
import { byText, clashLine, dueText, findClashes, stateLines, todoRail, toldItems, worthDoing } from './waitingModel';

const TZ = 'America/New_York';
// Wednesday, October 28, 2026, 2:40 pm in New York.
const NOW = new Date(zoned('2026-10-28', 14, 40, TZ));
const D = buildDeskData(NOW, TZ);
const TODAY = dayKey(NOW, TZ);
const P = (id: string) => D.proposals.find((p) => p.id === id)!;

describe('row text', () => {
  it('due text: day and slot, or No date', () => {
    expect(dueText(P('p_tripform'), TZ, TODAY)).toBe('Due Today · EOD');
    expect(dueText(P('p_seats'), TZ, TODAY)).toBe('Due Friday');
    expect(dueText(P('p_soccer'), TZ, TODAY)).toBe('Due Today · 5:30 pm');
    expect(dueText(P('p_flu'), TZ, TODAY)).toBe('No date');
  });

  it('state lines, in the words of §10', () => {
    expect(stateLines(P('p_picture'), NOW, TZ)).toEqual(['nobody accepted or dismissed this, and the date has gone']);
    expect(stateLines(P('p_soccer'), NOW, TZ)).toEqual(['the notice changed after it was accepted: was 5 pm, now 5:30 pm']);
    expect(stateLines(P('p_library'), NOW, TZ)).toEqual(['nobody has accepted this yet, and the date has gone']);
    expect(stateLines(P('p_insurance'), NOW, TZ)).toEqual(['a reminder, nothing here pays']);
    expect(stateLines(P('p_tripform'), NOW, TZ)).toEqual([]);
  });
});

describe('clashes', () => {
  it('two things due the same day for the same person: “Friday is tight”', () => {
    const c = findClashes(D, NOW, TZ);
    expect([...c.keys()]).toEqual(['p_seats']);
    const seats = c.get('p_seats')!;
    expect(seats.others.map((o) => o.id)).toEqual(['t_science']);
    expect(clashLine(seats, TODAY)).toBe('Friday is tight: clashes with Finish Mia’s science project — move one?');
    expect(stateLines(P('p_seats'), NOW, TZ, seats)).toEqual([clashLine(seats, TODAY)]);
  });

  it('a timed proposal clashes with timed events for the same person, not for someone else', () => {
    const mk = (forMemberId: string): Proposal => ({ id: 'p_x', noticeId: 'n_client', kind: 'calendar', agent: 'calendar', title: 'Call the bank', due: zoned('2026-10-29', 14, 30, TZ), dueKind: 'time', forMemberId, state: 'proposed', createdAt: NOW.toISOString() });
    const forMichael = findClashes({ ...D, proposals: [...D.proposals, mk('m_michael')] }, NOW, TZ).get('p_x')!;
    expect(forMichael.sameDay).toBe(false);
    expect(forMichael.others.map((o) => o.id).sort()).toEqual(['a_client_call', 'a_final']);
    expect(clashLine(forMichael, TODAY)).toMatch(/^clashes with .+ and more — move one\?$/);
    expect(findClashes({ ...D, proposals: [...D.proposals, mk('m_linda')] }, NOW, TZ).get('p_x')).toBeUndefined();
  });

  it('accepting the clashing proposal ends the clash (only undecided ones are checked)', () => {
    const proposals = D.proposals.map((p) => (p.id === 'p_seats' ? { ...p, state: 'accepted' as const } : p));
    expect(findClashes({ ...D, proposals }, NOW, TZ).size).toBe(0);
  });
});

describe('the rail', () => {
  it('To-dos: open ones by date, no date last; a to-do ticked today stays in reach', () => {
    const todos = D.todos.map((t) => (t.id === 't_filtersize' ? { ...t, done: true, doneAt: NOW.toISOString() } : t));
    const { open, doneToday } = todoRail({ todos }, NOW, TZ);
    expect(open[0].id).toBe('t_gutters');
    expect(open.at(-1)!.due).toBeUndefined();
    expect(open.map((t) => t.id)).not.toContain('t_filtersize');
    expect(doneToday.map((t) => t.id)).toEqual(['t_filtersize']);
    expect(byText(open[0], NOW, TZ)).toBe('was due yesterday');
    expect(byText(open[1], NOW, TZ)).toBe('by Friday');
  });

  it('Worth doing: subscriptions charging within 10 days, and a watched page nobody read — never bills', () => {
    const w = worthDoing(D, NOW, TZ);
    expect(w.map((x) => x.id)).toEqual(['r_coaching', 'r_gym', 'b_flights']);
    expect(w[0]).toMatchObject({ title: 'Check you still use Rivera Math Coaching', noticeId: 'n_balance' });
    expect(w[2]).toMatchObject({ to: '/plans/pl_santafe', noticeId: 'n_trip' });
  });

  it('You will be told: recent notices that ask nothing, newest first, no promotions or Quarantine', () => {
    const told = toldItems(D, NOW).map((n) => n.id);
    expect(told).toEqual(['n_cart', 'n_balance', 'n_photo', 'n_brokerage']);
    const asked = new Set(D.proposals.map((p) => p.noticeId));
    expect(told.some((id) => asked.has(id))).toBe(false);
  });
});
