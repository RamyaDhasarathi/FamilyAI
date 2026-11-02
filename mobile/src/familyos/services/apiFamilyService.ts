// FamilyService over the FamilyOS backend, with the rest kept on the phone.
//
//   Server   members: name, role, date of birth, email and phone (adults),
//            school and class (children). Created, edited and removed there.
//   Phone    what the server has no column for yet (DATABASE_ARCHITECTURE.md
//            §7.2): preferred name, relationship, photo, and each section's
//            other fields and status. AsyncStorage holds the non-sensitive
//            part; SecureStore the ids, health and banking sections, one item
//            per member and section, as the mock does.
//
// On read the two are merged, the server winning for the fields it holds.
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as SecureStore from 'expo-secure-store';
import { ageOf, emptySections, sortMembers } from '../family/model';
import type { FamilyMember, FamilyService, MemberBasics, MemberSection, Relationship, SectionId, SectionStatus } from './interfaces';
import { request } from './api';
import type { ApiHousehold, ApiMember } from './apiService';
import {
  bloodFromServer, bloodToServer, circleFor, contactFor, contactsWith, medicineRows, moneyToNumber, relationshipFrom, type EmergencyContact,
} from '../family/serverFields';

const KEY = 'familyos.family.server.v1';
const SENSITIVE: SectionId[] = ['ids', 'health', 'banking'];
const secureKey = (id: string, s: SectionId) => `member_${id}_${s}`;
const SECURE_OPTS = { keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY };

/** What the phone keeps for one server member. */
interface Overlay {
  preferredName?: string;
  relationship?: Relationship;
  relationshipOther?: string;
  photoUri?: string;
  sections?: Partial<Record<SectionId, MemberSection>>;
  /** Removed in the app, still inside its Undo window. */
  deletedAt?: string;
  updatedAt?: string;
}

const ROLE_LABEL: Record<ApiMember['role'], string> = { guardian: 'Guardian', adult: 'Adult', child: 'Child' };
const digits = (s: unknown) => String(s ?? '').replace(/\D/g, '');

// ── The phone's part ────────────────────────────────────────────────────────

let overlays: Record<string, Overlay> | null = null;

async function loadOverlays(): Promise<Record<string, Overlay>> {
  if (overlays) return overlays;
  const raw = await AsyncStorage.getItem(KEY).catch(() => null);
  const index: Record<string, Overlay> = raw ? JSON.parse(raw) : {};
  for (const [id, o] of Object.entries(index)) {
    for (const s of SENSITIVE) {
      if (!o.sections?.[s]) continue;
      const v = await SecureStore.getItemAsync(secureKey(id, s), SECURE_OPTS).catch(() => null);
      o.sections[s] = { ...o.sections[s]!, data: v ? (JSON.parse(v) as Record<string, unknown>) : {} };
    }
  }
  overlays = index;
  return index;
}

async function saveOverlay(id: string, o: Overlay | null): Promise<void> {
  const all = await loadOverlays();
  if (o) {
    all[id] = { ...o, updatedAt: new Date().toISOString() };
    await Promise.all(
      SENSITIVE.filter((s) => o.sections?.[s]).map((s) =>
        SecureStore.setItemAsync(secureKey(id, s), JSON.stringify(o.sections![s]!.data), SECURE_OPTS)
      )
    );
  } else {
    delete all[id];
    await Promise.all(SENSITIVE.map((s) => SecureStore.deleteItemAsync(secureKey(id, s), SECURE_OPTS).catch(() => undefined)));
  }
  // The index never carries the sensitive sections' data.
  const stripped: Record<string, Overlay> = {};
  for (const [k, v] of Object.entries(all)) {
    const sections: Overlay['sections'] = {};
    for (const [s, sec] of Object.entries(v.sections ?? {}) as [SectionId, MemberSection][]) {
      sections[s] = SENSITIVE.includes(s) ? { status: sec.status, data: {} } : sec;
    }
    stripped[k] = { ...v, sections };
  }
  await AsyncStorage.setItem(KEY, JSON.stringify(stripped));
}

// ── The server's part ───────────────────────────────────────────────────────

let meId: string | null = null;
let meRole: ApiMember['role'] | null = null;
/** The emergency details, the circle role and the approval limit are a guardian's to set (the backend refuses anyone else). */
const isGuardian = () => meRole === 'guardian';

async function fetchHousehold(): Promise<ApiMember[]> {
  const [me, household] = await Promise.all([
    meId ? Promise.resolve({ id: meId, role: meRole } as ApiMember) : request<ApiMember>('GET', '/me'),
    request<ApiHousehold>('GET', '/household'),
  ]);
  meId = me.id;
  meRole = me.role;
  return household.members;
}

/** What our backend holds beyond the member rows (family/serverFields.ts), read together; each part may be refused. */
interface Extras {
  profiles: Record<string, { allergies?: string | null; blood_group?: string | null }>;
  contacts: EmergencyContact[];
  /** The emergency card's current medicines, by the member's name (as the card gives them). */
  medicines: Record<string, string[]>;
  homePlace: string | null;
}

interface Card {
  contacts?: EmergencyContact[];
  people?: { name: string; medicines?: string[] }[];
}

async function fetchExtras(list: ApiMember[]): Promise<Extras> {
  // A profile is the person's own or a guardian's to read; the card is a guardian's unless one handed it over.
  const readable = isGuardian() ? list : list.filter((m) => m.id === meId);
  const [profiles, card, rules] = await Promise.all([
    Promise.all(readable.map((m) => request<Extras['profiles'][string]>('GET', `/members/${m.id}/profile`).then((p) => [m.id, p] as const).catch(() => null))),
    request<Card>('GET', '/emergency/card').catch(() => null),
    request<{ rules: { key: string; text?: string | null }[] }>('GET', '/household/rules').catch(() => null),
  ]);
  return {
    profiles: Object.fromEntries(profiles.filter((p): p is NonNullable<typeof p> => p !== null)),
    contacts: card?.contacts ?? [],
    medicines: Object.fromEntries((card?.people ?? []).map((p) => [p.name, p.medicines ?? []])),
    homePlace: rules?.rules.find((r) => r.key === 'home_place')?.text ?? null,
  };
}

const NO_EXTRAS: Extras = { profiles: {}, contacts: [], medicines: {}, homePlace: null };

function merge(a: ApiMember, o: Overlay | undefined, x: Extras = NO_EXTRAS): FamilyMember {
  const isOwner = a.id === meId;
  const sections = emptySections('notStarted');
  for (const [s, sec] of Object.entries(o?.sections ?? {}) as [SectionId, MemberSection][]) {
    sections[s] = { status: sec.status, data: { ...sec.data } };
  }
  // The server's fields win. A child's school and class; an adult's email
  // and phone (the phone's own formatting kept when the digits agree).
  const basic = sections.basic.data;
  if (a.role === 'child') {
    if (a.school) basic.school = a.school;
    else delete basic.school;
    if (a.class_label) basic.grade = a.class_label;
    else delete basic.grade;
  } else {
    const contact = sections.contact.data;
    if (a.email) contact.email = a.email;
    else delete contact.email;
    if (a.phone) {
      if (digits(contact.mobile) !== a.phone && !digits(contact.mobile).endsWith(a.phone.slice(-10))) contact.mobile = a.phone;
    } else delete contact.mobile;
  }
  if (!o?.sections?.basic) sections.basic.status = a.date_of_birth ? 'complete' : 'needsUpdate';
  if (!o?.sections?.contact && (a.email || a.phone)) sections.contact.status = 'needsUpdate';
  // Phase 3: health from the member's row and the household's emergency card; the owner's address from the home place.
  const health = sections.health.data;
  const prof = x.profiles[a.id];
  const ec = contactFor(x.contacts, a.display_name);
  const meds = x.medicines[a.display_name];
  if (prof?.blood_group) health.bloodGroup = bloodFromServer(prof.blood_group);
  if (prof?.allergies) health.allergies = prof.allergies;
  if (ec) Object.assign(health, ec);
  if (meds?.length && !(Array.isArray(health.medicines) && health.medicines.length)) health.medicines = medicineRows(meds);
  const held = !!(prof?.blood_group || prof?.allergies || ec || meds?.length);
  if (!o?.sections?.health && held) sections.health.status = 'needsUpdate';
  if (isOwner && x.homePlace && !sections.contact.data.address) sections.contact.data.address = x.homePlace;
  // A relationship this device has no word for comes from the circle role the server holds.
  const fromRole = !o?.relationship && !isOwner ? relationshipFrom(a.circle_role) : null;
  return {
    id: a.id,
    isOwner,
    fullName: a.display_name,
    preferredName: o?.preferredName,
    relationship: o?.relationship ?? fromRole?.relationship ?? (isOwner ? 'Self' : 'Other'),
    relationshipOther: fromRole
      ? fromRole.relationshipOther
      : o?.relationship && o.relationship !== 'Other' ? o?.relationshipOther : (o?.relationshipOther ?? (isOwner ? undefined : ROLE_LABEL[a.role])),
    dateOfBirth: a.date_of_birth ?? '',
    photoUri: o?.photoUri,
    sections,
    createdAt: a.created_at,
    updatedAt: o?.updatedAt ?? a.created_at,
    deletedAt: o?.deletedAt,
  };
}

async function serverMember(id: string): Promise<ApiMember> {
  const m = (await fetchHousehold()).find((x) => x.id === id);
  if (!m) throw new Error('That member is no longer in this household.');
  return m;
}

async function one(id: string): Promise<FamilyMember> {
  const m = await serverMember(id);
  return merge(m, (await loadOverlays())[id], await fetchExtras([m]));
}

/** The role a member should have for this birthday: guardians and the signed-in member keep theirs. */
function roleFor(a: ApiMember, dateOfBirth: string): 'adult' | 'child' | null {
  if (a.role === 'guardian' || a.id === meId || !dateOfBirth) return null;
  const want = ageOf(dateOfBirth) < 18 ? 'child' : 'adult';
  return want === a.role ? null : want;
}

/** Change this member's entry on the household's emergency card; sent only when the list really changes. */
async function putContact(name: string, entry: { name: string; mobile: string } | null, rename?: string): Promise<void> {
  const card = await request<Card>('GET', '/emergency/card').catch(() => null);
  if (!card) return;
  const now = card.contacts ?? [];
  let next: EmergencyContact[];
  if (rename) {
    const mine = contactFor(now, name);
    if (!mine) return;
    next = contactsWith(contactsWith(now, name, null), rename, { name: mine.emergencyName, mobile: mine.emergencyMobile });
  } else next = contactsWith(now, name, entry);
  if (JSON.stringify(next) !== JSON.stringify(now)) await request('PUT', '/emergency/profile', { contacts: next });
}

async function remove(id: string): Promise<void> {
  const gone = (await fetchHousehold()).find((m) => m.id === id);
  await request('DELETE', `/members/${id}`);
  await saveOverlay(id, null);
  if (gone && isGuardian()) await putContact(gone.display_name, null);
}

export const apiFamilyService: FamilyService = {
  async listMembers() {
    const [list, local] = await Promise.all([fetchHousehold(), loadOverlays()]);
    // A removal whose Undo window was cut short by quitting the app is final.
    const stale = list.filter((m) => local[m.id]?.deletedAt);
    await Promise.all(stale.map((m) => remove(m.id).catch(() => undefined)));
    const kept = list.filter((m) => !local[m.id]?.deletedAt);
    const x = await fetchExtras(kept);
    return sortMembers(kept.map((m) => merge(m, local[m.id], x)));
  },

  async getMember(id) {
    return one(id).catch(() => null);
  },

  async createMember(basics: MemberBasics) {
    const role = basics.dateOfBirth && ageOf(basics.dateOfBirth) < 18 ? 'child' : 'adult';
    const r = await request<ApiMember | { member: ApiMember }>('POST', '/household/members', {
      display_name: basics.fullName.trim(),
      role,
      date_of_birth: basics.dateOfBirth || null,
    });
    const created = 'member' in r ? r.member : r;
    const circle = role !== 'child' && isGuardian() ? circleFor(basics.relationship) : null;
    if (circle) await request('PUT', `/members/${created.id}/circle-role`, { circle_role: circle });
    const o: Overlay = {
      preferredName: basics.preferredName,
      relationship: basics.relationship,
      relationshipOther: basics.relationshipOther,
      photoUri: basics.photoUri,
      sections: emptySections('notStarted'),
    };
    await saveOverlay(created.id, o);
    return merge({ ...created, circle_role: circle }, (await loadOverlays())[created.id]);
  },

  async updateBasics(id, patch: Partial<MemberBasics>) {
    const a = await serverMember(id);
    if (patch.fullName !== undefined && patch.fullName.trim() && patch.fullName.trim() !== a.display_name) {
      await request('PATCH', `/members/${id}`, { display_name: patch.fullName.trim() });
      // The emergency card finds a member's contact by their name: it follows the new one.
      if (isGuardian()) await putContact(a.display_name, null, patch.fullName.trim());
    }
    if (patch.dateOfBirth !== undefined && (patch.dateOfBirth || null) !== (a.date_of_birth ?? null)) {
      await request('PATCH', `/members/${id}/birthday`, { date_of_birth: patch.dateOfBirth || null });
      const role = roleFor(a, patch.dateOfBirth);
      if (role) await request('PATCH', `/members/${id}`, { role });
    }
    // A caregiver set on the server stays: that role also decides what they see, and the form has no word for it.
    if ('relationship' in patch && isGuardian() && a.role !== 'child' && a.circle_role !== 'caregiver') {
      const circle = circleFor(patch.relationship);
      if (circle !== (a.circle_role ?? null)) await request('PUT', `/members/${id}/circle-role`, { circle_role: circle });
    }
    const o = { ...((await loadOverlays())[id] ?? {}) };
    if ('preferredName' in patch) o.preferredName = patch.preferredName;
    if ('relationship' in patch) o.relationship = patch.relationship;
    if ('relationshipOther' in patch) o.relationshipOther = patch.relationshipOther;
    if ('photoUri' in patch) o.photoUri = patch.photoUri;
    await saveOverlay(id, o);
    return one(id);
  },

  async updateSection(id: string, sectionId: SectionId, data: Record<string, unknown>, status: SectionStatus) {
    const a = await serverMember(id);
    if (sectionId === 'basic' && a.role === 'child') {
      const school = String(data.school ?? '').trim() || null;
      const grade = String(data.grade ?? '').trim() || null;
      if (school !== (a.school ?? null) || grade !== (a.class_label ?? null)) {
        await request('PATCH', `/members/${id}/school`, { school, class_label: grade });
      }
    }
    if (sectionId === 'contact' && a.role !== 'child') {
      const email = String(data.email ?? '').trim().toLowerCase() || null;
      const phone = digits(data.mobile) || null;
      const body: Record<string, string | null> = {};
      if (email !== (a.email ?? null)) body.email = email;
      if (phone !== (a.phone ?? null) && !(phone && a.phone && phone.endsWith(a.phone.slice(-10)))) body.phone = phone;
      if (Object.keys(body).length) await request('PATCH', `/members/${id}`, body);
    }
    const before = (await loadOverlays())[id]?.sections?.[sectionId]?.data ?? {};
    if (sectionId === 'health' && isGuardian()) {
      await request('PUT', `/members/${id}/medical`, { allergies: String(data.allergies ?? '').trim() || null, blood_group: bloodToServer(data.bloodGroup) });
      await putContact(a.display_name, { name: String(data.emergencyName ?? ''), mobile: String(data.emergencyMobile ?? '') });
    }
    if (sectionId === 'banking' && isGuardian()) {
      // The backend keeps one number: the most this person may ask to buy at once. It has no way to read it back,
      // so it is sent when it changes from what this device last saved.
      const key = a.role === 'child' ? 'approvalThreshold' : 'approvalLimit';
      const limit = moneyToNumber(data[key]);
      if (limit !== moneyToNumber(before[key])) await request('PUT', `/members/${id}/payment-limit`, { payment_limit: limit });
    }
    const o = { ...((await loadOverlays())[id] ?? {}) };
    o.sections = { ...(o.sections ?? {}), [sectionId]: { status, data } };
    await saveOverlay(id, o);
    return one(id);
  },

  // Removal is two steps, as the app's Undo needs: hidden here at once, gone
  // from the server only when the Undo window closes (purgeMember).
  async deleteMember(id) {
    const o = { ...((await loadOverlays())[id] ?? {}), deletedAt: new Date().toISOString() };
    await saveOverlay(id, o);
  },

  async restoreMember(id) {
    const o = { ...((await loadOverlays())[id] ?? {}) };
    delete o.deletedAt;
    await saveOverlay(id, o);
    return one(id);
  },

  purgeMember: remove,

  // The demo reset belongs to the mocks; here it just reloads the household.
  async resetDemoFamily() {
    return apiFamilyService.listMembers();
  },
};
