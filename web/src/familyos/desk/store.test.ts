// MASTER_AGENT.md §11: accept / dismiss / undo write audit rows and move the
// item to its agent; errand approval is void once a written-down term
// changes; the audit is append-only; export and typed-confirmation erase.
import { beforeEach, describe, expect, it } from 'vitest';
import { buildDeskData } from './data';
import { fmtText, zoned } from './format';
import { approvalHolds, fingerprint } from './fingerprint';
import { deskClock, useDesk } from './store';

const TZ = 'America/New_York';
const NOW = new Date(zoned('2026-10-28', 14, 40, TZ));
const st = () => useDesk.getState();
const last = () => st().audit[st().audit.length - 1];

beforeEach(() => {
  deskClock.now = () => NOW;
  useDesk.setState({ ...buildDeskData(NOW, TZ), actor: 'm_michael' });
});

describe('proposals', () => {
  it('accepting a task moves it to the to-dos and writes an audit row', () => {
    const n = st().audit.length;
    expect(st().acceptProposal('p_tripform')).toBe(true);
    const p = st().proposals.find((x) => x.id === 'p_tripform')!;
    const todo = st().todos.find((t) => t.proposalId === 'p_tripform')!;
    expect(p.state).toBe('accepted');
    expect(todo).toMatchObject({ noticeId: 'n_tripform', ownerId: 'm_michael', done: false, agent: 'education' });
    expect(st().audit).toHaveLength(n + 1);
    expect(last()).toMatchObject({ actor: 'm_michael', code: 'proposal.accepted', at: NOW.toISOString() });
    expect(last().raw).toMatchObject({ proposalId: 'p_tripform', noticeId: 'n_tripform', createdTodoId: todo.id });
  });

  it('accepting a calendar proposal puts it on the calendar', () => {
    st().acceptProposal('p_trip');
    const a = st().agenda.find((x) => x.proposalId === 'p_trip')!;
    expect(a).toMatchObject({ kind: 'event', agent: 'calendar', noticeId: 'n_trip', dueKind: 'allDay' });
  });

  it('accepting a changed notice moves the calendar entry; undo moves it back', () => {
    const before = st().agenda.find((a) => a.id === 'a_soccer')!.when;
    st().acceptProposal('p_soccer');
    expect(st().agenda.find((a) => a.id === 'a_soccer')!.when).toBe(zoned('2026-10-28', 17, 30, TZ));
    expect(st().agenda.find((a) => a.id === 'a_soccer')!.details?.find(([k]) => k === 'When')?.[1]).toBe('5:30 pm – 7:00 pm');
    st().undoProposal('p_soccer');
    expect(st().agenda.find((a) => a.id === 'a_soccer')!.when).toBe(before);
    expect(st().proposals.find((x) => x.id === 'p_soccer')!.state).toBe('changed');
  });

  it('dismiss and undo each write an audit row; undo removes what accept created', () => {
    st().dismissProposal('p_flu');
    expect(last().code).toBe('proposal.dismissed');
    st().undoProposal('p_flu');
    expect(last().code).toBe('proposal.undone');
    expect(st().proposals.find((x) => x.id === 'p_flu')!.state).toBe('proposed');

    const todos = st().todos.length;
    st().acceptProposal('p_rx');
    expect(st().todos).toHaveLength(todos + 1);
    st().undoProposal('p_rx');
    expect(st().todos).toHaveLength(todos);
    expect(last()).toMatchObject({ code: 'proposal.undone', raw: { proposalId: 'p_rx', was: 'accepted', now: 'proposed' } });
  });

  it('does nothing (and logs nothing) for decided or unknown proposals', () => {
    const n = st().audit.length;
    expect(st().acceptProposal('p_electric')).toBe(false);
    expect(st().dismissProposal('nope')).toBe(false);
    expect(st().undoProposal('p_tripform')).toBe(false);
    expect(st().audit).toHaveLength(n);
  });
});

describe('to-dos', () => {
  it('a to-do added and then removed leaves an audit row for each, and its plan forgets it', () => {
    const plan = st().plans[0];
    const id = st().addTodo({ title: 'Pack the snacks', ownerId: 'm_michael', planId: plan.id });
    expect(st().plans[0].todoIds).toContain(id);
    expect(st().removeTodo(id)).toBe(true);
    expect(st().todos.some((t) => t.id === id)).toBe(false);
    expect(st().plans[0].todoIds).not.toContain(id);
    expect(st().audit.slice(-2).map((a) => a.code)).toEqual(['todo.created', 'todo.removed']);
    expect(st().removeTodo(id)).toBe(false);
  });
});

describe('the clash', () => {
  it('moves the call only on Confirm, and Undo restores it', () => {
    const call = () => st().agenda.find((a) => a.id === 'a_client_call')!;
    const was = call().when;
    expect(st().resolveConflict('c_tomorrow', 'fix_call_330')).toBe(true);
    expect(call().when).toBe(zoned('2026-10-29', 15, 30, TZ));
    expect(st().conflicts[0].resolvedAt).toBe(NOW.toISOString());
    expect(last().code).toBe('conflict.resolved');
    expect(st().undoConflict('c_tomorrow')).toBe(true);
    expect(call().when).toBe(was);
    expect(last().code).toBe('conflict.reopened');
  });
});

describe('errands', () => {
  it('fingerprints exactly the written-down terms', () => {
    const e = st().errands.find((x) => x.id === 'e_insurance')!;
    expect(fingerprint(e)).toBe(e.fingerprint);
    expect(fingerprint({ ...e, title: 'renamed' } as typeof e)).toBe(e.fingerprint);
    for (const k of ['what', 'when', 'where', 'paidBy', 'card', 'stopsIf'] as const) expect(fingerprint({ ...e, [k]: `${e[k]}!` })).not.toBe(e.fingerprint);
    expect(fingerprint({ ...e, atMost: e.atMost + 0.01 })).not.toBe(e.fingerprint);
  });

  it('voids an approval when any term changes', () => {
    expect(st().approveErrand('e_insurance')).toBe(true);
    let e = st().errands.find((x) => x.id === 'e_insurance')!;
    expect(e.status).toBe('approved');
    expect(approvalHolds(e)).toBe(true);
    expect(st().editErrand('e_insurance', { atMost: 200 })).toBe(true);
    e = st().errands.find((x) => x.id === 'e_insurance')!;
    expect(e.status).toBe('proposed');
    expect(approvalHolds(e)).toBe(false);
    expect(st().audit.slice(-2).map((a) => a.code)).toEqual(['errand.updated', 'errand.approval_voided']);
    expect(st().audit.at(-2)!.sentence).toContain('changed at most on');
    // An edit that changes nothing is not an edit.
    expect(st().editErrand('e_insurance', { atMost: 200 })).toBe(false);
  });

  it('the seeded approval holds, and only a guardian can approve', () => {
    expect(approvalHolds(st().errands.find((x) => x.id === 'e_filters')!)).toBe(true);
    st().setActor('m_linda');
    expect(st().approveErrand('e_insurance')).toBe(false);
  });
});

describe('audit, export, erase', () => {
  it('has no way to edit or delete audit rows', () => {
    const auditKeys = Object.keys(st()).filter((k) => /audit/i.test(k));
    expect(auditKeys).toEqual(['audit']);
    const n = st().audit.length;
    st().toggleTodo('t_gutters');
    st().setToggle('localModel', true);
    st().revokeToken('tk_sarah');
    st().stopWatcher('w_lunch');
    st().releaseQuarantine('q_camp');
    expect(st().audit).toHaveLength(n + 5);
    expect(st().audit.slice(-5).map((a) => a.code)).toEqual(['todo.done', 'setting.toggled', 'phone_token.revoked', 'watcher.stopped', 'quarantine.released']);
  });

  it('reverts a revision once', () => {
    expect(st().revertRevision('rv_budget')).toBe(true);
    expect(st().plans[0].budget).toBe(2800);
    expect(st().revertRevision('rv_budget')).toBe(false);
    expect(st().revertRevision('rv_filters')).toBe(false);
  });

  it('exports everything (and records it)', () => {
    const out = st().exportAll();
    expect(out.format).toBe('familyos.desk.v1');
    expect(out.data.notices.length).toBe(st().notices.length);
    expect(out.data.audit[out.data.audit.length - 1].code).toBe('export.downloaded');
  });

  it('erases only with the exact typed phrase', () => {
    expect(st().eraseConfirmPhrase()).toBe('erase The Carters');
    expect(st().eraseAll('erase the carters')).toBe(false);
    expect(st().notices.length).toBeGreaterThan(0);
    expect(st().eraseAll('erase The Carters')).toBe(true);
    expect(st().notices).toEqual([]);
    expect(st().audit.map((a) => a.code)).toEqual(['household.erased']);
  });

  it('switches every amount with the one currency setting', () => {
    expect(fmtText(`Reserve is ¤{12450}`, st().settings.currency)).toBe('Reserve is $12,450');
    st().setSetting('currency', 'INR');
    expect(fmtText(`Reserve is ¤{12450}, cart ¤{86.4}, ¤{1245000}`, st().settings.currency)).toBe('Reserve is ₹12,450, cart ₹86.40, ₹12,45,000');
    expect(last().code).toBe('setting.changed');
  });
});
