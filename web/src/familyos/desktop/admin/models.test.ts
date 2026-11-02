// Phase 5 view logic (MASTER_AGENT.md §7 Phase 5, §11): the errand form
// voids an approval live and on save; the audit raw rows, day groups and
// filters; revision values; and the Erase everything gate.
import { beforeEach, describe, expect, it } from 'vitest';
import { buildDeskData } from '../../desk/data';
import { fmtMoney, zoned } from '../../desk/format';
import { approvalHolds } from '../../desk/fingerprint';
import { deskClock, useDesk } from '../../desk/store';
import type { AuditEntry } from '../../desk/types';
import { changedTerms, draftEffect, parseAmount, parseDraft, patchOf, safeCard, siteOf, sortErrands, toDraft, canApprove } from './errandModel';
import { actorOptions, filterAudit, groupByDay, kindOf, NO_FILTER, rawLine } from './auditModel';
import { canRevert, fmtValue, recordHref, whyNoRevert } from './revisionModel';
import { eraseReady, readableCode, siteHost, validEmail } from './settingsModel';

const TZ = 'America/New_York';
const NOW = new Date(zoned('2026-10-28', 14, 40, TZ));
const st = () => useDesk.getState();
const errand = (id: string) => st().errands.find((e) => e.id === id)!;

beforeEach(() => {
  deskClock.now = () => NOW;
  useDesk.setState({ ...buildDeskData(NOW, TZ), actor: 'm_michael' });
});

describe('errand form', () => {
  it('parses amounts and keeps only the last four digits of a card', () => {
    expect(parseAmount('$48')).toBe(48);
    expect(parseAmount('1,200.50')).toBe(1200.5);
    expect(parseAmount('forty')).toBeNull();
    expect(parseAmount('48.505')).toBeNull();
    expect(safeCard('Visa ending 4417')).toBe('Visa ending 4417');
    expect(safeCard('4111 1111 1111 4417')).toBe('Card ending 4417');
    expect(safeCard('Mastercard 5555444433331111')).toBe('Mastercard ending 1111');
    expect(safeCard('none — FamilyOS holds no card')).toBe('none — FamilyOS holds no card');
    expect(safeCard('ending 12')).toBeNull();
  });

  it('refuses a draft with an open term', () => {
    const d = { ...toDraft(errand('e_insurance')), stopsIf: '  ', atMost: 'a lot' };
    const { terms, errors } = parseDraft(d);
    expect(terms).toBeNull();
    expect(Object.keys(errors).sort()).toEqual(['atMost', 'stopsIf']);
  });

  it('shows, before saving, that a change voids a holding approval', () => {
    const e = errand('e_filters');
    expect(approvalHolds(e)).toBe(true);
    const same = parseDraft({ ...toDraft(e), what: `  ${e.what} ` }).terms!;
    expect(draftEffect(e, same)).toEqual({ changed: [], fingerprint: e.fingerprint, voids: false });
    const dearer = parseDraft({ ...toDraft(e), atMost: '52' }).terms!;
    const fx = draftEffect(e, dearer);
    expect(fx.changed).toEqual(['atMost']);
    expect(fx.voids).toBe(true);
    expect(fx.fingerprint).not.toBe(e.approvedFingerprint);
    // A waiting errand has no approval to void.
    const ins = errand('e_insurance');
    expect(draftEffect(ins, parseDraft({ ...toDraft(ins), atMost: '200' }).terms!).voids).toBe(false);
  });

  it('saving the draft voids the approval in the store and writes the audit rows', () => {
    const e = errand('e_filters');
    const terms = parseDraft({ ...toDraft(e), card: '4000 1234 5678 9010' }).terms!;
    expect(patchOf(e, terms)).toEqual({ card: 'Card ending 9010' });
    expect(st().editErrand(e.id, patchOf(e, terms))).toBe(true);
    const after = errand('e_filters');
    expect(after.status).toBe('proposed');
    expect(approvalHolds(after)).toBe(false);
    expect(st().audit.slice(-2).map((a) => a.code)).toEqual(['errand.updated', 'errand.approval_voided']);
    expect(changedTerms(e, after)).toEqual(['card']);
  });

  it('lists what needs a guardian first; only guardians approve', () => {
    expect(sortErrands(st().errands).map((e) => e.status)).toEqual(['proposed', 'approved', 'done', 'cancelled']);
    expect(siteOf('homesupply.example, signed in as Michael')).toBe('homesupply.example');
    expect(canApprove(errand('e_insurance'), 'guardian')).toBe(true);
    expect(canApprove(errand('e_insurance'), 'adult')).toBe(false);
    expect(canApprove(errand('e_filters'), 'guardian')).toBe(false);
  });
});

describe('audit view', () => {
  it('prints raw rows the way the reference does', () => {
    expect(rawLine({ code: 'member.signed_in', raw: { via: 'google' } })).toBe('member.signed_in via "google"');
    expect(rawLine({ code: 'calendar.synced', raw: { kept: 17, dropped: 0 } })).toBe('calendar.synced kept 17 dropped 0');
    expect(rawLine({ code: 'proposal.accepted', raw: { proposalId: 'p_x', proposalIds: ['a', 'b'] } })).toBe('proposal.accepted proposal_id "p_x" proposal_ids ["a","b"]');
    expect(rawLine({ code: 'export.downloaded' })).toBe('export.downloaded');
  });

  it('groups newest first by household day, ties in log order', () => {
    const rows = st().audit;
    const groups = groupByDay(rows, TZ);
    expect(groups[0].day).toBe('2026-10-28');
    expect(groups.map((g) => g.day)).toEqual([...groups.map((g) => g.day)].sort().reverse());
    expect(groups.reduce((n, g) => n + g.rows.length, 0)).toBe(rows.length);
    const at = NOW.toISOString();
    const tie: AuditEntry[] = [
      { id: 'x1', at, actor: 'm_michael', sentence: 'first', code: 'a.b' },
      { id: 'x2', at, actor: 'm_michael', sentence: 'second', code: 'a.b' },
    ];
    expect(groupByDay(tie, TZ)[0].rows.map((r) => r.sentence)).toEqual(['second', 'first']);
  });

  it('filters by actor, kind and text without touching the log', () => {
    const rows = st().audit;
    const copy = JSON.stringify(rows);
    const fos = filterAudit(rows, { ...NO_FILTER, actor: 'FamilyOS' });
    expect(fos.length).toBeGreaterThan(0);
    expect(fos.every((r) => r.actor === 'FamilyOS')).toBe(true);
    const errands = filterAudit(rows, { ...NO_FILTER, kind: 'Errands' });
    expect(errands.every((r) => r.code.startsWith('errand.'))).toBe(true);
    expect(filterAudit(rows, { ...NO_FILTER, text: 'kept 17' }).map((r) => r.code)).toEqual(['calendar.synced']);
    expect(kindOf('phone_token.revoked')).toBe('Connections');
    expect(actorOptions(rows).at(-1)).toBe('FamilyOS');
    expect(JSON.stringify(rows)).toBe(copy);
  });
});

describe('revisions view', () => {
  const ctx = { currency: 'USD', tz: TZ, money: (n: number) => fmtMoney(n, 'USD') };

  it('says values in household terms', () => {
    expect(fmtValue('budget', 2800, ctx)).toBe('$2,800');
    expect(fmtValue('due', '2026-10-25', ctx)).toBe('Oct 25');
    expect(fmtValue('when', zoned('2026-10-30', 11, 0, TZ), ctx)).toBe('Oct 30, 11 am');
    expect(fmtValue('title', null, ctx)).toBe('nothing');
  });

  it('offers Revert only where allowed, and says why not', () => {
    const rv = (id: string) => st().revisions.find((r) => r.id === id)!;
    expect(canRevert(rv('rv_budget'))).toBe(true);
    expect(whyNoRevert(rv('rv_filters'))).toMatch(/voids the approval/);
    expect(whyNoRevert(rv('rv_electric'))).toMatch(/notice/);
    expect(recordHref(rv('rv_budget'), st())).toBe('/plans/pl_santafe');
    expect(st().revertRevision('rv_budget')).toBe(true);
    expect(canRevert(rv('rv_budget'))).toBe(false);
    const back = st().revisions.at(-1)!;
    expect(back.revertOf).toBe('rv_budget');
    expect(whyNoRevert(back)).toBe('This is itself a revert.');
  });
});

describe('erase gate and validators', () => {
  it('opens only for the exact phrase, and the store agrees', () => {
    const phrase = st().eraseConfirmPhrase();
    expect(eraseReady('', phrase)).toBe(false);
    expect(eraseReady('erase the carters', phrase)).toBe(false);
    expect(eraseReady('erase The Carter', phrase)).toBe(false);
    expect(eraseReady(`  ${phrase} `, phrase)).toBe(true);
    expect(st().eraseAll('erase the carters')).toBe(false);
    expect(st().notices.length).toBeGreaterThan(0);
    expect(st().eraseAll(`  ${phrase} `.trim())).toBe(true);
    expect(st().audit.map((a) => a.code)).toEqual(['household.erased']);
  });

  it('checks sites, addresses and codes', () => {
    expect(siteHost('https://Portal.Riverside-Elem.example/login')).toBe('portal.riverside-elem.example');
    expect(siteHost('not a site')).toBeNull();
    expect(validEmail('linda@example.com')).toBe(true);
    expect(validEmail('linda@example')).toBe(false);
    expect(readableCode('tk_7K2Mq9xd4tpa')).toBe('fos-tk7k-2mq9-xd4t');
  });
});
