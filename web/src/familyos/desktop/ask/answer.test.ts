// MASTER_AGENT.md §7 Phase 3 "Ask", §3.3 principles 1–2, §11 "Every proposed
// change requires a click on Confirm" and "Every row/answer links to its
// source": answers are built from the desk data, cite the notices they came
// from as r1, r2… in order, never cite what the asker cannot see, and any
// change is an action card — answering changes nothing; Confirm does.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { buildDeskData } from '../../desk/data';
import { zoned } from '../../desk/format';
import { isMissed } from '../../desk/selectors';
import { deskClock, useDesk } from '../../desk/store';
import { answer, SUGGESTIONS, type Answer } from './answer';
import type { AskCtx } from './askSearch';

const TZ = 'America/New_York';
const NOW = new Date(zoned('2026-10-28', 14, 40, TZ));
const CTX: AskCtx = { now: NOW, tz: TZ, actor: 'm_michael' };
const D = buildDeskData(NOW, TZ);
const text = (a: Answer) => a.segs.map((s) => ('t' in s ? s.t : `[r${s.cite}]`)).join('');
const cited = (a: Answer) => a.cites.map((c) => c.noticeId);

const QUESTIONS = [
  ...SUGGESTIONS, 'What’s everyone doing tomorrow?', 'Plan our weekend around Mia’s recital', 'What do we pay every month?', 'Which school work is pending for Ethan and Mia?',
  'Plan dinner tonight', 'When are we all free this week?', 'How are we doing on money?', 'What needs me today?', 'Tell me more about: The electrician arrives at 4 pm',
  'when is the furnace service', 'what about Ethan', 'car insurance',
];

describe('answers cite the notices they came from', () => {
  it.each(QUESTIONS)('%s', (q) => {
    const a = answer(q, D, CTX);
    expect(a.cites.length).toBeGreaterThan(0);
    // Numbered r1, r2… in order of first use, one per notice.
    const order = a.segs.filter((s): s is { cite: number } => 'cite' in s).map((s) => s.cite);
    const firsts = order.filter((n, i) => order.indexOf(n) === i);
    expect(firsts).toEqual(a.cites.map((c) => c.n));
    expect(a.cites.map((c) => c.n)).toEqual(a.cites.map((_, i) => i + 1));
    expect(new Set(cited(a)).size).toBe(a.cites.length);
    for (const c of a.cites) expect(D.notices.find((n) => n.id === c.noticeId && !n.quarantined)).toBeTruthy();
    // Any card offers to accept only something still undecided.
    for (const act of a.actions.filter((x) => x.kind === 'accept')) {
      const p = D.proposals.find((x) => x.id === act.target)!;
      expect(['proposed', 'changed']).toContain(p.state);
      expect(isMissed(p, NOW, TZ)).toBe(false);
    }
  });
});

describe('what the answers say', () => {
  it('what we pay every month: every monthly charge, in the household currency token', () => {
    const a = answer('What do we pay every month?', D, CTX);
    expect(text(a)).toContain('¤{2150}');
    expect(cited(a)).toEqual(expect.arrayContaining(['n_mortgage', 'n_insurance', 'n_streamly', 'n_balance']));
    expect(text(a)).toContain('it pays none of them');
    expect(a.actions).toEqual([]);
  });

  it('a "when is" question answers from the calendar entry and cites its notice', () => {
    const a = answer('When is Mia’s recital?', D, CTX);
    expect(text(a)).toMatch(/^Mia’s recital: on Saturday at 2 pm/);
    expect(cited(a)[0]).toBe('n_recital');
  });

  it('what needs someone this week: missed first, then overdue and this week, with cards for the first two', () => {
    const a = answer('What needs someone this week?', D, CTX);
    expect(text(a)).toMatch(/^3 things were missed/);
    expect(cited(a).slice(0, 3)).toEqual(['n_yearbook', 'n_streamly', 'n_picture']);
    expect(a.actions.map((x) => x.target)).toEqual(['p_library', 'p_soccer']);
  });

  it('tomorrow mentions the clash FamilyOS noticed, citing both notices', () => {
    const a = answer('What’s everyone doing tomorrow?', D, CTX);
    expect(text(a)).toContain('FamilyOS noticed');
    expect(cited(a)).toEqual(expect.arrayContaining(['n_dentist', 'n_final', 'n_client']));
  });

  it('nothing matched: an honest answer, no citations, suggestions instead', () => {
    const a = answer('When did the plumber last come?', D, CTX);
    expect(a.cites).toEqual([]);
    expect(text(a)).toContain('could not find anything about “plumber”');
    expect(a.suggest).toEqual(SUGGESTIONS);
  });
});

describe('it sees only what the asker can see', () => {
  it('never cites a notice held in Quarantine', () => {
    for (const q of ['Invoice 4471 overdue', 'redelivery fee for my package', 'summer camp early-bird places']) {
      expect(cited(answer(q, D, CTX)).filter((id) => id.startsWith('n_q_'))).toEqual([]);
    }
  });

  it('never cites a notice restricted to someone else, nor what was read from it', () => {
    const data = { ...D, notices: D.notices.map((n) => (n.id === 'n_pt' ? { ...n, visibleTo: ['m_linda'] } : n)) };
    expect(cited(answer('physical therapy', data, CTX))).not.toContain('n_pt');
    expect(cited(answer('physical therapy', data, { ...CTX, actor: 'm_linda' }))).toContain('n_pt');
  });
});

describe('changes are cards; nothing changes until Confirm', () => {
  it('"accept the field trip form" offers one card and changes nothing', () => {
    const before = JSON.stringify(D);
    const a = answer('accept the field trip form', D, CTX);
    expect(a.actions).toEqual([expect.objectContaining({ kind: 'accept', target: 'p_tripform', title: 'Sign Ethan’s field trip form', noticeId: 'n_tripform' })]);
    expect(a.actions[0].detail).toBe('task, due today, by end of day, for Ethan');
    expect(JSON.stringify(D)).toBe(before);
  });

  it('dismiss, tick and add-a-to-do are cards too', () => {
    expect(answer('dismiss flu shots', D, CTX).actions[0]).toMatchObject({ kind: 'dismiss', target: 'p_flu' });
    expect(answer('tick off the gutters', D, CTX).actions[0]).toMatchObject({ kind: 'tick', target: 't_gutters' });
    expect(answer('remind me to call the plumber', D, CTX).actions[0]).toMatchObject({ kind: 'addTodo', title: 'Call the plumber' });
  });

  describe('the conversation store', () => {
    beforeEach(() => {
      vi.useFakeTimers();
      vi.setSystemTime(NOW);
      (globalThis as { window?: unknown }).window ??= globalThis;
      deskClock.now = () => NOW;
      useDesk.setState({ ...buildDeskData(NOW, TZ), actor: 'm_michael', settings: { ...buildDeskData(NOW, TZ).settings, timezone: TZ } });
    });

    it('answers after the typing delay; Confirm accepts and audits; Undo puts it back', async () => {
      const { useAsk } = await import('./askStore');
      useAsk.getState().clear();
      useAsk.getState().ask('accept the field trip form');
      expect(useAsk.getState().pending).toBe(1);
      vi.advanceTimersByTime(1300);
      const msg = useAsk.getState().msgs.find((m) => m.role === 'assistant')!;
      const card = msg.answer!.actions[0];
      const p = () => useDesk.getState().proposals.find((x) => x.id === 'p_tripform')!;
      const rows = useDesk.getState().audit.length;
      expect(p().state).toBe('proposed');
      useAsk.getState().confirm(msg.id, card);
      expect(p().state).toBe('accepted');
      expect(useDesk.getState().audit).toHaveLength(rows + 1);
      expect(useDesk.getState().audit.at(-1)).toMatchObject({ code: 'proposal.accepted', actor: 'm_michael' });
      useAsk.getState().undo(msg.id, card);
      expect(p().state).toBe('proposed');
      expect(useDesk.getState().audit.at(-1)?.code).toBe('proposal.undone');
    });

    it('asks a ?q= question once per navigation', async () => {
      const { useAsk } = await import('./askStore');
      useAsk.getState().clear();
      useAsk.getState().askOnce('key1', 'What is still undecided?');
      useAsk.getState().askOnce('key1', 'What is still undecided?');
      expect(useAsk.getState().msgs.filter((m) => m.role === 'user')).toHaveLength(1);
      useAsk.getState().clear();
      vi.advanceTimersByTime(1300);
      expect(useAsk.getState().msgs).toEqual([]);
    });
  });
});
