// The member form on our backend (Phase 3): what has a column goes to it and comes back from it; what is a guardian's
// to change is sent only when a guardian is signed in; nothing else on the household's emergency card is disturbed.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { FamilyService } from './interfaces';
import { emergencyTag } from '../family/serverFields';
import { formatters, phonePrefix } from '../family/region';

// The phone format follows the app's region (mocks/data.ts), so the expectations do too.
const SURESH = `${phonePrefix} ${formatters.phone('9845099999')}`;

const HH = 'h1';
const ME = 'm-me';
const MUM = 'm-mum';
const KID = 'm-kid';

interface Call { method: string; path: string; body?: unknown }
let calls: Call[];
let role: 'guardian' | 'adult';
let mumCircle: string | null;
let contacts: { name: string; relation: string; phone: string }[];

function members() {
  return [
    { id: ME, household_id: HH, display_name: 'Asha Rao', role, email: 'asha@example.in', phone: '9845012345', date_of_birth: '1985-05-15', created_at: '2026-07-01T00:00:00Z', circle_role: null },
    { id: MUM, household_id: HH, display_name: 'Lalita Rao', role: 'adult', date_of_birth: '1960-02-01', created_at: '2026-07-01T00:00:00Z', circle_role: mumCircle },
    { id: KID, household_id: HH, display_name: 'Ravi Rao', role: 'child', date_of_birth: '2016-01-02', school: 'Greenwood High', class_label: 'Grade 4', created_at: '2026-07-01T00:00:00Z', circle_role: null },
  ];
}

function answer(method: string, path: string): unknown {
  if (path === '/me') return members()[0];
  if (path === '/household') return { id: HH, name: 'The Rao family', currency: 'INR', members: members() };
  if (path === `/members/${MUM}/profile`) return { id: MUM, allergies: 'Penicillin', blood_group: 'B-' };
  if (path.startsWith('/members/') && path.endsWith('/profile')) return { id: path.split('/')[2], allergies: null, blood_group: null };
  if (path === '/emergency/card') return { contacts, people: [{ name: 'Lalita Rao', medicines: ['Amlodipine 5 mg, 1 a day'] }] };
  if (path === '/household/rules') return { rules: [{ key: 'home_place', text: '12 MG Road, Bengaluru' }] };
  if (method === 'PUT' && path === '/emergency/profile') return {};
  if (method === 'PUT') return {};
  if (method === 'PATCH') return {};
  return {};
}

async function service(): Promise<FamilyService> {
  vi.resetModules();
  globalThis.fetch = (async (url: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET';
    const path = String(url).replace(/^\/v1/, '');
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    calls.push({ method, path, body });
    return new Response(JSON.stringify(answer(method, path)), { status: 200 });
  }) as typeof fetch;
  return (await import('./apiFamilyService')).apiFamilyService;
}

const writes = () => calls.filter((c) => c.method !== 'GET');

beforeEach(() => {
  calls = [];
  role = 'guardian';
  mumCircle = null;
  contacts = [{ name: 'Dr Mehta', relation: 'Family doctor', phone: '+91 80000 11111' }];
});

describe('reading members from our backend', () => {
  it('fills what the server holds: medical, the emergency contact, medicines, the relationship and the home address', async () => {
    contacts = [...contacts, { name: 'Suresh Rao', relation: emergencyTag('Lalita Rao'), phone: SURESH }];
    mumCircle = 'parent';
    const list = await (await service()).listMembers();
    const mum = list.find((m) => m.id === MUM)!;
    expect(mum.sections.health.data).toMatchObject({ bloodGroup: 'B−', allergies: 'Penicillin', emergencyName: 'Suresh Rao', emergencyMobile: formatters.phone('9845099999') });
    expect(mum.sections.health.data.medicines).toEqual([{ name: 'Amlodipine 5 mg, 1 a day', dose: '', when: '' }]);
    expect(mum.sections.health.status).toBe('needsUpdate');
    expect([mum.relationship, mum.relationshipOther]).toEqual(['Other', 'Parent']);
    const me = list.find((m) => m.id === ME)!;
    expect(me.sections.contact.data.address).toBe('12 MG Road, Bengaluru');
  });
});

describe('saving to our backend', () => {
  it('health: blood group and allergies to the member, the contact onto the household card beside the others', async () => {
    const svc = await service();
    await svc.listMembers();
    calls = [];
    await svc.updateSection(MUM, 'health', { bloodGroup: 'O−', allergies: 'Dust', emergencyName: 'Suresh Rao', emergencyMobile: '98450 99999' }, 'complete');
    expect(writes()).toEqual([
      { method: 'PUT', path: `/members/${MUM}/medical`, body: { allergies: 'Dust', blood_group: 'O-' } },
      {
        method: 'PUT', path: '/emergency/profile',
        body: { contacts: [{ name: 'Suresh Rao', relation: emergencyTag('Lalita Rao'), phone: SURESH }, contacts[0]] },
      },
    ]);
  });

  it('"Not sure" clears the blood group rather than storing the words', async () => {
    const svc = await service();
    await svc.updateSection(KID, 'health', { bloodGroup: 'Not sure', allergies: '' }, 'complete');
    expect(writes()[0]).toEqual({ method: 'PUT', path: `/members/${KID}/medical`, body: { allergies: null, blood_group: null } });
  });

  it('a member who is not a guardian keeps these on the device: the backend would refuse them', async () => {
    role = 'adult';
    const svc = await service();
    await svc.listMembers();
    calls = [];
    await svc.updateSection(MUM, 'health', { bloodGroup: 'O−', emergencyName: 'Suresh Rao', emergencyMobile: '98450 99999' }, 'complete');
    await svc.updateSection(MUM, 'banking', { approvalLimit: '1,500' }, 'complete');
    expect(writes()).toEqual([]);
  });

  it('relationship: the circle role for an adult, never over a caregiver set on the server, never for a child', async () => {
    let svc = await service();
    await svc.updateBasics(MUM, { relationship: 'Mother' });
    expect(writes()).toEqual([{ method: 'PUT', path: `/members/${MUM}/circle-role`, body: { circle_role: 'parent' } }]);

    calls = [];
    mumCircle = 'caregiver';
    svc = await service();
    await svc.updateBasics(MUM, { relationship: 'Sister' });
    expect(writes()).toEqual([]);

    calls = [];
    await svc.updateBasics(KID, { relationship: 'Son' });
    expect(writes()).toEqual([]);
  });

  it('approval limit: the adult\'s limit, or the child\'s "ask an adult above", as a number', async () => {
    const svc = await service();
    await svc.updateSection(MUM, 'banking', { approvalLimit: '1,500' }, 'complete');
    await svc.updateSection(KID, 'banking', { approvalThreshold: '200' }, 'complete');
    await svc.updateSection(KID, 'banking', { approvalThreshold: '' }, 'complete');
    expect(writes()).toEqual([
      { method: 'PUT', path: `/members/${MUM}/payment-limit`, body: { payment_limit: 1500 } },
      { method: 'PUT', path: `/members/${KID}/payment-limit`, body: { payment_limit: 200 } },
      { method: 'PUT', path: `/members/${KID}/payment-limit`, body: { payment_limit: null } },
    ]);
  });

  it('renaming a member carries their emergency contact over to the new name', async () => {
    contacts = [...contacts, { name: 'Suresh Rao', relation: emergencyTag('Lalita Rao'), phone: SURESH }];
    const svc = await service();
    await svc.updateBasics(MUM, { fullName: 'Lalita Devi Rao' });
    expect(writes()).toEqual([
      { method: 'PATCH', path: `/members/${MUM}`, body: { display_name: 'Lalita Devi Rao' } },
      { method: 'PUT', path: '/emergency/profile', body: { contacts: [{ name: 'Suresh Rao', relation: emergencyTag('Lalita Devi Rao'), phone: SURESH }, contacts[0]] } },
    ]);
  });

  it('removing a member takes their entry off the emergency card and leaves the rest', async () => {
    contacts = [...contacts, { name: 'Suresh Rao', relation: emergencyTag('Lalita Rao'), phone: SURESH }];
    const svc = await service();
    await svc.listMembers();
    calls = [];
    await svc.purgeMember(MUM);
    expect(writes()).toEqual([
      { method: 'DELETE', path: `/members/${MUM}`, body: undefined },
      { method: 'PUT', path: '/emergency/profile', body: { contacts: [contacts[0]] } },
    ]);
  });
});
