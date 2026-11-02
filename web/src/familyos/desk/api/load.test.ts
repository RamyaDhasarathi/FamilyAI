// The desk's reading of the backend (desk/api/load.ts) on answers shaped like the server's: one bad row must not
// lose the household (a finished errand counts its steps, it does not list them), held notices join the inbox,
// replaced dates are left out, and a date nobody decided reads as missed.
import { afterEach, describe, expect, it } from 'vitest';
import { loadDeskData } from './load';

const HH = '00000000-0000-0000-0000-0000000000aa';
const ME = '00000000-0000-0000-0000-000000000001';
const KID = '00000000-0000-0000-0000-000000000002';

const answers: Record<string, unknown> = {
  me: { id: ME, role: 'guardian' },
  household: {
    id: HH, name: 'The Test family', inbound_address: 'test.family@in.familyos.local', telegram_bot: null, country: 'IN', timezone: 'Asia/Kolkata', currency: 'INR',
    members: [
      { id: ME, display_name: 'Asha Rao', role: 'guardian', email: 'asha@example.in', date_of_birth: '1985-05-15', joined: true, created_at: '2026-07-01T00:00:00Z' },
      { id: KID, display_name: 'Ravi Rao', role: 'child', date_of_birth: '2016-01-02', school: 'Greenwood High', class_label: 'Grade 4', created_at: '2026-07-01T00:00:00Z' },
    ],
  },
  inbox: [{ id: 'n1', channel: 'email', received_at: '2026-10-01T04:00:00Z', headline: 'Field trip', from_label: 'school', subject_member_ids: [KID], assigned_to: null, attachments: 0, preview: ['Sign the form'], category: 'school', visibility: 'shared' }],
  quarantine: [{ id: 'q1', received_at: '2026-10-02T04:00:00Z', quarantine_reason: 'sender_domain_not_vouched', source: { from: 'x@y.example', subject: 'Admissions open' }, channel: 'email', category: 'unknown' }],
  obligations: [
    { id: 'o1', artifact_id: 'n1', claim_id: 'c1', kind: 'task', action: 'sign', title: 'Sign the form', due_date: '2026-10-03', status: 'proposed', created_at: '2026-10-01T04:00:00Z' },
    { id: 'o2', artifact_id: 'n1', claim_id: 'c2', kind: 'calendar', title: 'Old rehearsal', due_date: '2099-01-01', status: 'accepted', created_at: '2026-10-01T04:00:00Z', superseded_at: '2026-10-05T00:00:00Z' },
    { id: 'o3', artifact_id: 'n1', claim_id: 'c3', kind: 'calendar', title: 'Annual day', due_date: '2099-01-02', due_time: '09:30', status: 'accepted', created_at: '2026-10-01T04:00:00Z' },
  ],
  amendments: [],
  todos: [{ id: 't1', title: 'Find the passports', due_date: '2099-01-03', assigned_to: ME, created_at: '2026-10-01T04:00:00Z' }],
  money: { recurring: [], running_low: [], usual: [{ item: 'Eggs', item_key: 'eggs', merchant: 'More', last_on: '2026-10-21', last_amount: 92 }], charges: [] },
  errands: [{ id: 'e1', service: 'grocery', kind: 'purchase', title: 'Weekly order', spec: {}, params_sha256: 'abc', status: 'done', created_by: ME, outcome: { steps: 14, total: 2310.5 }, created_at: '2026-10-01T04:00:00Z' }],
  plans: [], audit: [], activity: [], devices: [], watches: [], consents: [], harvests: [],
  'household/rules': { rules: [{ key: 'weekly_digest', title: 'Weekly digest', sentence: 'Sunday summary.', on: false }] },
  'google/mailboxes': [], 'household/schools': [],
};

const realFetch = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = realFetch;
});

describe('loadDeskData', () => {
  it('reads the household into the desk shapes', async () => {
    globalThis.fetch = (async (url: string) => {
      const key = String(url).replace('/v1/', '').split('?')[0];
      return key in answers ? new Response(JSON.stringify(answers[key]), { status: 200 }) : new Response('{"detail":"not found"}', { status: 404 });
    }) as typeof fetch;
    const { data, actor, ids } = await loadDeskData();

    expect(actor).toBe(ME);
    expect(data.settings).toMatchObject({ name: 'The Test family', country: 'India', timezone: 'Asia/Kolkata', currency: 'INR' });
    expect(data.members.map((m) => [m.name, m.role, m.hasAccount])).toEqual([['Asha', 'guardian', true], ['Ravi', 'child', false]]);
    expect(data.children).toEqual([{ memberId: KID, school: 'Greenwood High', grade: 'Grade 4', homeroom: '', teacher: '' }]);
    // A held notice joins the list, marked; Quarantine points at it.
    expect(data.notices.find((n) => n.id === 'q1')).toMatchObject({ quarantined: true, title: 'Admissions open' });
    expect(data.quarantine).toEqual([{ id: 'q1', noticeId: 'q1', heldAt: '2026-10-02T04:00:00Z', reason: 'sender domain not vouched' }]);
    // A replaced date is left out; a date gone by undecided is missed; an accepted date is on the calendar, at its time.
    expect(data.proposals.map((p) => [p.id, p.state])).toEqual([['o1', 'missed'], ['o3', 'accepted']]);
    expect(data.proposals[0]).toMatchObject({ agent: 'education', spaceId: 'education', due: '2026-10-03', dueKind: 'allDay' });
    expect(data.agenda.map((a) => [a.id, a.dueKind, a.when])).toEqual([['o3', 'time', '2099-01-02T04:00:00.000Z']]);
    // A finished errand's outcome counts its steps.
    expect(data.errands[0]).toMatchObject({ status: 'done', steps: [], fingerprint: 'abc' });
    expect(ids.paramsOf.e1).toBe('abc');
    expect(data.todos[0]).toMatchObject({ id: 't1', ownerId: ME, done: false });
    expect(data.orderAgain[0]).toMatchObject({ item: 'Eggs', price: 92 });
    expect(data.toggles.find((t) => t.id === 'weeklyDigest')).toMatchObject({ on: false, label: 'Weekly digest' });
  });
});
