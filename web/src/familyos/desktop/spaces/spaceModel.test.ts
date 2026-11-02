// Space template model (MASTER_AGENT.md §7 Phase 4, §10 state lines): the
// space timeline with its honest state lines, header counts, What arrived,
// Spent here / Charges again / Due soon / bills this week, Dates spotted,
// the trip summary and the statements list — over the Carter seed, pinned to
// Wednesday, October 28, 2026, 2:40 pm in New York.
import { describe, expect, it } from 'vitest';
import { buildDeskData } from '../../desk/data';
import { zoned } from '../../desk/format';
import {
  billsThisWeek, chargesAgain, decideList, dueSoon, missedCount, moneyStats, sourceLabel, spaceCounts, spaceTimeline, spentHere, upcoming, upcomingBills, whatArrived,
} from './spaceModel';
import { investActivity, planTodoOrder, reorderCap, sortErrands, statementsByMonth, tripView } from './listModels';

const TZ = 'America/New_York';
const NOW = new Date(zoned('2026-10-28', 14, 40, TZ));
const D = buildDeskData(NOW, TZ);
const byId = <T extends { id: string }>(xs: T[], id: string) => xs.find((x) => x.id === id)!;

describe('spaceTimeline', () => {
  const school = spaceTimeline(D, 'education', NOW, TZ);

  it('lists the School space oldest first, gone dates included', () => {
    expect(school.map((e) => e.id)).toEqual([
      'p_yearbook', 'p_picture', 'p_rehearsal', 'p_soccer', 'p_tripform', 'p_final', 'p_science', 'p_seats', 'p_recital', 'p_conference',
    ]);
    expect(school.map((e) => e.day).slice(0, 3)).toEqual(['2026-10-26', '2026-10-27', '2026-10-28']);
  });

  it('writes the honest state lines of MASTER §10', () => {
    const line = (id: string) => byId(school, id).line;
    expect(line('p_picture')).toBe('nobody accepted or dismissed this, and the date has gone');
    expect(byId(school, 'p_picture').tone).toBe('missed');
    expect(line('p_final')).toBe('clashes with Your client call (quarterly review) — move one?');
    expect(line('p_recital')).toBe('accepted · on the calendar · Mia, Michael, Sarah, Linda, Ethan');
    expect(line('p_science')).toBe('accepted · on the to-dos · Sarah');
    expect(line('p_tripform')).toBe('nobody has accepted this yet · for Ethan');
    expect(line('p_soccer')).toBe('the notice changed: was 5 pm, now 5:30 pm — accept the new time?');
  });

  it('uses what accepting created: its title, time and record id', () => {
    const science = byId(school, 'p_science');
    expect(science.title).toBe('Finish Mia’s science project');
    expect(science.flashId).toBe('t_science');
    expect(byId(school, 'p_final').flashId).toBe('a_final');
    expect(school.every((e) => !!e.noticeId)).toBe(true);
  });

  it('says the date has gone for accepted things in the past', () => {
    const health = spaceTimeline(D, 'health', NOW, TZ);
    expect(health.map((e) => e.id)).toEqual(['p_pt', 'p_rx', 'p_dentist']);
    expect(byId(health, 'p_pt')).toMatchObject({ tone: 'gone', line: 'the family accepted this, and the date has gone', gone: true });
    expect(byId(health, 'p_dentist').line).toBe('accepted · on the calendar · Michael');
  });

  it('drops the clash line once the clash is resolved, and shows done to-dos as done', () => {
    const conflicts = D.conflicts.map((c) => ({ ...c, resolvedAt: NOW.toISOString() }));
    const todos = D.todos.map((t) => (t.id === 't_science' ? { ...t, done: true } : t));
    const tl = spaceTimeline({ ...D, conflicts, todos }, 'education', NOW, TZ);
    expect(byId(tl, 'p_final').line).toBe('accepted · on the calendar · Ethan, Michael');
    expect(byId(tl, 'p_science')).toMatchObject({ tone: 'done', line: 'done · Sarah' });
  });

  it('counts a plan’s to-dos as Travel and keeps dismissed proposals out', () => {
    const travel = spaceTimeline(D, 'travel', NOW, TZ);
    expect(travel.map((e) => e.id)).toEqual(['t_pl_assist', 't_pl_mail', 't_pl_maps', 'p_trip']);
    expect(byId(travel, 't_pl_assist').line).toBe('on the to-dos · Michael');
    expect(spaceTimeline(D, 'grocery', NOW, TZ).map((e) => e.id)).not.toContain('p_promo');
  });

  it('honours the window (This week = today to today + 6)', () => {
    const week = spaceTimeline(D, 'all', NOW, TZ, { from: 0, to: 6 });
    expect(week.every((e) => e.day >= '2026-10-28' && e.day <= '2026-11-03')).toBe(true);
    expect(week.map((e) => e.id)).not.toContain('p_picture');
    expect(week.map((e) => e.id)).toContain('a_delivery');
    expect(upcoming(week).every((e) => !e.gone)).toBe(true);
  });

  it('finds this week’s bills and payments without double-counting what was accepted', () => {
    const bills = billsThisWeek(spaceTimeline(D, 'all', NOW, TZ, { from: 0, to: 6 }));
    expect(bills.map((e) => e.id)).toEqual(['p_mortgage', 'p_insurance']);
  });
});

describe('header counts and What arrived', () => {
  it('counts notices and the dated ones', () => {
    expect(spaceCounts(D, 'health')).toEqual({ notices: 4, dated: 3 });
    expect(spaceCounts(D, 'travel')).toEqual({ notices: 1, dated: 1 });
    expect(spaceCounts(D, 'memories')).toEqual({ notices: 1, dated: 0 });
  });

  it('lists a space’s notices newest first with “N to decide”, never Quarantine', () => {
    const health = whatArrived(D, 'health');
    expect(health.map((a) => a.notice.id)).toEqual(['n_pharmacy', 'n_dentist', 'n_flu', 'n_pt']);
    expect(health.find((a) => a.notice.id === 'n_pharmacy')?.toDecide).toBe(1);
    expect(whatArrived(D, 'all').some((a) => a.notice.quarantined)).toBe(false);
  });

  it('names the source plainly', () => {
    expect(sourceLabel({ source: 'phone', sender: 'Sarah’s phone · school app' })).toBe('Sarah’s phone · school app');
    expect(sourceLabel({ source: 'phone', sender: 'Maple Street Pharmacy' })).toBe('Maple Street Pharmacy · your phone');
    expect(sourceLabel({ source: 'email', sender: 'Lakeside Dental' })).toBe('Lakeside Dental · email');
    expect(sourceLabel({ source: 'whatsapp', sender: 'Coach Daniels' })).toBe('Coach Daniels · WhatsApp');
  });
});

describe('money', () => {
  it('Spent here: charges in the last 30 days of the scope', () => {
    const all = spentHere(D.recurring, 'all', NOW, TZ);
    expect(all.count).toBe(10);
    expect(all.total).toBe(2908.77);
    expect(all.rows[0].id).toBe('r_streamly');
    expect(spentHere(D.recurring, 'health', NOW, TZ)).toMatchObject({ count: 1, total: 45 });
    expect(spentHere(D.recurring, 'travel', NOW, TZ)).toEqual({ rows: [], total: 0, count: 0 });
  });

  it('Charges again and Due soon: soonest first', () => {
    expect(chargesAgain(D.recurring, 'all', NOW, TZ)[0].id).toBe('r_mortgage');
    expect(dueSoon(D.recurring, NOW, TZ).map((r) => r.id)).toEqual(['r_mortgage', 'r_coaching', 'r_insurance', 'r_power', 'r_gym', 'r_fiber']);
  });

  it('counts the bills (not subscriptions) charging in the next 30 days', () => {
    expect(upcomingBills(D.recurring, NOW, TZ).map((r) => r.id)).toEqual(['r_mortgage', 'r_insurance', 'r_power', 'r_fiber', 'r_mobile']);
  });

  it('stat cards', () => {
    const s = moneyStats(D.recurring, NOW, TZ);
    expect(s.subscriptions).toBe(5);
    expect(s.subscriptionsNext).toBe(267.47);
  });
});

describe('decideList (Dates spotted, Health to decide)', () => {
  it('keeps undecided, dated proposals that can still be decided, soonest first', () => {
    expect(decideList(D, { datedOnly: true }, NOW, TZ).map((p) => p.id)).toEqual(['p_library', 'p_soccer', 'p_rx', 'p_tripform', 'p_seats', 'p_insurance', 'p_trip']);
    expect(missedCount(D, NOW, TZ)).toBe(3);
  });

  it('includes undated ones last when asked for a space', () => {
    expect(decideList(D, { scope: 'health' }, NOW, TZ).map((p) => p.id)).toEqual(['p_rx', 'p_flu']);
  });
});

describe('travel and investments', () => {
  const plan = D.plans[0];

  it('summarises a trip: N to book, N to do', () => {
    expect(tripView(plan, D.todos)).toEqual({ toBook: 4, booked: 1, toDo: 4, done: 1, estToBook: 2280, estBooked: 220 });
  });

  it('orders a plan’s to-dos: open by date, undated, then done', () => {
    const ids = planTodoOrder(D.todos.filter((t) => t.planId === plan.id), TZ).map((t) => t.id);
    expect(ids).toEqual(['t_pl_assist', 't_pl_mail', 't_pl_maps', 't_pl_class', 't_pl_dates']);
  });

  it('groups statements by month, newest first', () => {
    const groups = statementsByMonth(D.statements);
    expect(groups.map((g) => [g.label, g.items.length])).toEqual([['October 2026', 4], ['September 2026', 1]]);
    expect(groups[0].items[0].id).toBe('s_oct');
    expect(investActivity(D.statements, NOW, TZ)).toEqual({ bought: 1500, dividends: 42.18, statements: 2 });
  });

  it('orders errands: waiting for approval, approved, done, cancelled', () => {
    expect(sortErrands(D.errands).map((e) => e.status)).toEqual(['proposed', 'approved', 'done', 'cancelled']);
  });

  it('caps a reorder at the last price plus 15 %, rounded up', () => {
    expect(reorderCap(4.29)).toBe(5);
    expect(reorderCap(38.99)).toBe(45);
  });
});
