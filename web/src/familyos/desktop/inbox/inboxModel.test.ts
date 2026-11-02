// MASTER_AGENT.md §7 Phase 3 "Inbox": notice status, filter chips and their
// counts, promotions kept out of the way (and counted), Quarantine never
// shown, Dates spotted order, Handling per person, and "Read from this
// notice" — every seeded quote is grounded in its notice's text.
import { describe, expect, it } from 'vitest';
import { buildDeskData } from '../../desk/data';
import { zoned } from '../../desk/format';
import { datesSpotted, handling, inboxView, markQuotes, noticeRows, parseQuery, statusOf, STATUS_ORDER } from './inboxModel';

const TZ = 'America/New_York';
const NOW = new Date(zoned('2026-10-28', 14, 40, TZ));
const D = buildDeskData(NOW, TZ);
const ME = 'm_michael';
const ids = (rows: { notice: { id: string } }[]) => rows.map((r) => r.notice.id);

describe('status and filters', () => {
  it('a notice is To do while anything on it is undecided (or missed), Done once all is decided, else Nothing asked', () => {
    const rows = noticeRows(D, ME);
    const of = (id: string) => rows.find((r) => r.notice.id === id)!;
    expect(of('n_recital')).toMatchObject({ status: 'todo', open: 1 });
    expect(of('n_yearbook')).toMatchObject({ status: 'todo', open: 1 });
    expect(of('n_electric').status).toBe('done');
    expect(of('n_cart').status).toBe('nothing');
    expect(statusOf([])).toBe('nothing');
  });

  it('defaults to To do · Everything and ignores unknown values in the URL', () => {
    expect(parseQuery(new URLSearchParams(''))).toEqual({ show: 'todo', cat: 'everything', who: null });
    expect(parseQuery(new URLSearchParams('show=nope&cat=bogus&who=m_sarah'))).toEqual({ show: 'todo', cat: 'everything', who: 'm_sarah' });
    expect(parseQuery(new URLSearchParams('show=done&cat=school'))).toMatchObject({ show: 'done', cat: 'school' });
  });

  it('never shows a notice held in Quarantine', () => {
    const all = inboxView(D, { show: 'all', cat: 'everything' }, ME);
    expect(ids(all.rows).some((id) => id.startsWith('n_q_'))).toBe(false);
    expect(all.total).toBe(D.notices.filter((n) => !n.quarantined).length);
  });

  it('each chip counts what picking it would show', () => {
    for (const cat of ['everything', 'school', 'bills', 'promo'] as const) {
      const v = inboxView(D, { show: 'todo', cat }, ME);
      for (const s of STATUS_ORDER) expect(v.statusCounts[s]).toBe(inboxView(D, { show: s, cat }, ME).rows.length);
      for (const c of v.categories) expect(c.count).toBe(inboxView(D, { show: 'todo', cat: c.id }, ME).rows.length);
    }
  });

  it('keeps promotions and newsletters that ask nothing out of “Everything”, counted — but not one with something to decide', () => {
    const v = inboxView(D, { show: 'all', cat: 'everything' }, ME);
    expect(ids(v.rows)).not.toContain('n_promo');
    expect(ids(v.rows)).toContain('n_flu');
    expect(v.kept).toBe(1);
    expect(ids(inboxView(D, { show: 'all', cat: 'promo' }, ME).rows)).toEqual(['n_promo']);
  });

  it('rows are newest first and carry the earliest open date', () => {
    const rows = inboxView(D, { show: 'todo', cat: 'everything' }, ME).rows;
    const times = rows.map((r) => r.notice.receivedAt);
    expect(times).toEqual([...times].sort().reverse());
    expect(rows.find((r) => r.notice.id === 'n_recital')!.firstDue?.due).toBe(D.proposals.find((p) => p.id === 'p_seats')!.due);
  });
});

describe('the rail', () => {
  it('Dates spotted: undecided by date, no date last; accepted and missed ones are not there', () => {
    const list = datesSpotted(D, NOW, TZ, ME).map((p) => p.id);
    expect(list[0]).toBe('p_library');
    expect(list.at(-1)).toBe('p_flu');
    for (const gone of ['p_picture', 'p_streamly', 'p_yearbook', 'p_electric', 'p_promo']) expect(list).not.toContain(gone);
    expect(list).toEqual(expect.arrayContaining(['p_tripform', 'p_rx', 'p_seats', 'p_insurance', 'p_trip', 'p_soccer']));
  });

  it('Handling: people with an account, then Nobody yet; the counts add up to the open notices', () => {
    const rows = handling(D, ME);
    expect(rows.map((r) => r.name)).toEqual(['Michael', 'Linda', 'Sarah', 'Nobody yet']);
    expect(rows.find((r) => r.name === 'Sarah')!.count).toBe(2);
    const open = inboxView(D, { show: 'todo', cat: 'everything' }, ME).statusCounts.todo + inboxView(D, { show: 'todo', cat: 'everything' }, ME).kept;
    expect(rows.reduce((n, r) => n + r.count, 0)).toBe(noticeRows(D, ME).filter((r) => r.status === 'todo').length);
    expect(open).toBeGreaterThan(0);
    expect(inboxView(D, { show: 'todo', cat: 'everything', who: 'm_sarah' }, ME).rows.map((r) => r.notice.id).sort()).toEqual(['n_recital', 'n_trip']);
  });
});

describe('Read from this notice', () => {
  it('every seeded quote is found in its notice, and the spans rebuild the text exactly', () => {
    for (const n of D.notices) {
      const ps = D.proposals.filter((p) => p.noticeId === n.id).map((p, i) => ({ n: i + 1, quote: p.quote }));
      const { segs, missing, found } = markQuotes(n.body, ps);
      expect(missing).toEqual([]);
      expect(found.size).toBe(ps.length);
      expect(segs.map((s) => s.text).join('')).toBe(n.body);
    }
  });

  it('a quote that is not in the text is reported, not highlighted', () => {
    const { segs, missing } = markQuotes('Practice moves to 5:30 pm.', [{ n: 1, quote: '5:30 pm' }, { n: 2, quote: 'field 9' }]);
    expect(missing).toEqual([2]);
    expect(segs).toEqual([{ text: 'Practice moves to ' }, { text: '5:30 pm', n: 1 }, { text: '.' }]);
  });
});
