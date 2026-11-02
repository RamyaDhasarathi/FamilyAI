// The desk dataset is coherent: every row points back to a real notice /
// proposal, quotes are exact substrings of the notice they cite, history is
// never in the future whatever time the app loads, and only fictional
// `.example` addresses are used.
import { describe, expect, it } from 'vitest';
import { buildDeskData } from './data';
import { zoned } from './format';

const TZ = 'America/New_York';
const D = buildDeskData(new Date(zoned('2026-10-28', 14, 40, TZ)), TZ);
const notice = (id?: string) => D.notices.find((n) => n.id === id);

describe('desk dataset', () => {
  it('covers every phase', () => {
    expect(D.notices.length).toBeGreaterThanOrEqual(20);
    expect(D.notices.filter((n) => n.quarantined)).toHaveLength(3);
    expect(D.quarantine.map((q) => q.noticeId).every((id) => notice(id)?.quarantined)).toBe(true);
    expect(new Set(D.proposals.map((p) => p.state))).toEqual(new Set(['proposed', 'accepted', 'dismissed', 'missed', 'changed']));
    expect(new Set(D.errands.map((e) => e.status))).toEqual(new Set(['proposed', 'approved', 'done', 'cancelled']));
    expect(D.errands.find((e) => e.status === 'done')!.steps.length).toBeGreaterThan(2);
    expect(D.audit.length).toBeGreaterThanOrEqual(40);
    expect(D.conflicts).toHaveLength(1);
    expect(D.plans[0].bookings.length).toBeGreaterThan(3);
    expect(D.members.map((m) => m.name)).toEqual(['Michael', 'Linda', 'Sarah', 'Ethan', 'Mia']);
    expect(D.children.map((c) => `${c.school} · ${c.grade}`)).toEqual(['Lakeside High · Grade 11', 'Riverside Elementary · Grade 5']);
  });

  it('keeps every back-link', () => {
    for (const p of D.proposals) {
      expect(notice(p.noticeId), p.id).toBeDefined();
      if (p.quote) expect(notice(p.noticeId)!.body, p.id).toContain(p.quote);
    }
    for (const a of D.agenda) {
      expect(notice(a.noticeId), a.id).toBeDefined();
      if (a.proposalId) expect(D.proposals.some((p) => p.id === a.proposalId), a.id).toBe(true);
    }
    for (const t of D.todos) expect(notice(t.noticeId), t.id).toBeDefined();
    for (const x of [...D.recurring, ...D.statements, ...D.orderAgain]) expect(notice(x.noticeId), x.id).toBeDefined();
    for (const p of D.proposals) for (const id of Object.values(p.created ?? {})) expect([...D.agenda, ...D.todos].some((r) => r.id === id), `${p.id} → ${id}`).toBe(true);
    for (const c of D.conflicts) expect([c.aId, c.bId, ...c.fixes.map((f) => f.agendaId)].every((id) => D.agenda.some((a) => a.id === id))).toBe(true);
    expect(D.plans[0].todoIds.every((id) => D.todos.find((t) => t.id === id)?.planId === 'pl_santafe')).toBe(true);
  });

  it('never puts history in the future, whatever time the app loads', () => {
    for (const [hh, mm] of [[0, 0], [0, 30], [7, 0], [11, 0], [23, 59]]) {
      const now = new Date(zoned('2026-10-28', hh, mm, TZ));
      const d = buildDeskData(now, TZ);
      const past = [...d.audit.map((a) => a.at), ...d.notices.map((n) => n.receivedAt), ...d.proposals.map((p) => p.createdAt), ...d.proposals.flatMap((p) => (p.decidedAt ? [p.decidedAt] : []))];
      for (const at of past) expect(new Date(at).getTime(), `${hh}:${mm} ${at}`).toBeLessThanOrEqual(now.getTime());
      const times = d.audit.map((a) => new Date(a.at).getTime());
      expect([...times].sort((a, b) => a - b)).toEqual(times);
    }
  });

  it('uses only fictional addresses', () => {
    const text = JSON.stringify(D);
    const emails = text.match(/[\w.+-]+@[\w-]+(\.[\w-]+)+/g) ?? [];
    expect(emails.length).toBeGreaterThan(5);
    for (const e of emails) expect(e, e).toMatch(/\.example$|@example\.com$/);
    const urls = text.match(/https?:\/\/[^\s"]+/g) ?? [];
    for (const u of urls) expect(u, u).toMatch(/^https:\/\/[\w.-]+\.example(\/|$)/);
  });
});
