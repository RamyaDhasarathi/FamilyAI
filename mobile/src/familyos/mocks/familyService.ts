// Mock FamilyService that survives app restarts (AGENT_CORE_AND_FAMILY.md §4.3).
//
//   AsyncStorage   key `familyos.family.v1`: every member, with the data of
//                  the sensitive sections (ids, health, banking) removed.
//   SecureStore    key `member_<id>_<section>`: that section's data, one small
//                  item per member and section. Never logged.
//
// To use a real backend, implement FamilyService (services/interfaces.ts) and
// change the export at the bottom; the store and screens only see the contract.
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as SecureStore from 'expo-secure-store';
import type { FamilyMember, FamilyService, MemberBasics, SectionId } from '../services/interfaces';
import { emptySections, sortMembers } from '../family/model';
import { seedFamily } from './familySeed';

const KEY = 'familyos.family.v1';
const SENSITIVE: SectionId[] = ['ids', 'health', 'banking'];
const secureKey = (id: string, s: SectionId) => `member_${id}_${s}`;
const SECURE_OPTS = { keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY };

/** Simulated network latency, 250–600 ms (like the other mock services). */
const latency = <T,>(value: T, min = 250, max = 600): Promise<T> =>
  new Promise((resolve) => setTimeout(() => resolve(value), min + Math.random() * (max - min)));

const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v));

let cache: FamilyMember[] | null = null;
let loading: Promise<FamilyMember[]> | null = null;

async function writeSecure(m: FamilyMember) {
  await Promise.all(SENSITIVE.map((s) => SecureStore.setItemAsync(secureKey(m.id, s), JSON.stringify(m.sections[s].data), SECURE_OPTS)));
}

async function deleteSecure(id: string) {
  await Promise.all(SENSITIVE.map((s) => SecureStore.deleteItemAsync(secureKey(id, s)).catch(() => undefined)));
}

/** Persist the non-sensitive part of every member. */
async function writeIndex(list: FamilyMember[]) {
  const stripped = list.map((m) => {
    const c = clone(m);
    for (const s of SENSITIVE) c.sections[s].data = {};
    return c;
  });
  await AsyncStorage.setItem(KEY, JSON.stringify(stripped));
}

async function load(): Promise<FamilyMember[]> {
  if (cache) return cache;
  if (loading) return loading;
  loading = (async () => {
    const raw = await AsyncStorage.getItem(KEY);
    let list: FamilyMember[];
    if (!raw) {
      // Fresh install: seed the demo family.
      list = seedFamily();
      await Promise.all(list.map(writeSecure));
      await writeIndex(list);
    } else {
      list = JSON.parse(raw) as FamilyMember[];
      // Removals whose Undo window was cut short by quitting the app are final.
      const stale = list.filter((m) => m.deletedAt);
      if (stale.length) {
        await Promise.all(stale.map((m) => deleteSecure(m.id)));
        list = list.filter((m) => !m.deletedAt);
        await writeIndex(list);
      }
      for (const m of list) {
        for (const s of SENSITIVE) {
          const v = await SecureStore.getItemAsync(secureKey(m.id, s), SECURE_OPTS);
          m.sections[s].data = v ? (JSON.parse(v) as Record<string, unknown>) : {};
        }
      }
    }
    cache = list;
    loading = null;
    return list;
  })();
  return loading;
}

async function save(list: FamilyMember[], changed?: FamilyMember) {
  cache = list;
  if (changed) await writeSecure(changed);
  await writeIndex(list);
}

function newId() {
  return `m_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 7)}`;
}

export const mockFamilyService: FamilyService = {
  async listMembers() {
    const list = await load();
    return latency(sortMembers(clone(list.filter((m) => !m.deletedAt))));
  },

  async getMember(id) {
    const list = await load();
    const m = list.find((x) => x.id === id && !x.deletedAt);
    return latency(m ? clone(m) : null, 120, 250);
  },

  async createMember(basics: MemberBasics) {
    const list = await load();
    const now = new Date().toISOString();
    const m: FamilyMember = {
      id: newId(),
      isOwner: false,
      ...basics,
      sections: emptySections('notStarted'),
      createdAt: now,
      updatedAt: now,
    };
    await save([...list, m], m);
    return latency(clone(m));
  },

  async updateBasics(id, patch) {
    const list = await load();
    const next = list.map((m) => (m.id === id ? { ...m, ...patch, updatedAt: new Date().toISOString() } : m));
    const m = next.find((x) => x.id === id);
    if (!m) throw new Error('Member not found');
    await save(next);
    return latency(clone(m), 150, 300);
  },

  async updateSection(id, sectionId, data, status) {
    const list = await load();
    const next = list.map((m) =>
      m.id === id
        ? { ...m, sections: { ...m.sections, [sectionId]: { status, data } }, updatedAt: new Date().toISOString() }
        : m
    );
    const m = next.find((x) => x.id === id);
    if (!m) throw new Error('Member not found');
    await save(next, SENSITIVE.includes(sectionId) ? m : undefined);
    return latency(clone(m), 150, 300);
  },

  async deleteMember(id) {
    const list = await load();
    const target = list.find((m) => m.id === id);
    if (!target) return;
    if (target.isOwner) throw new Error("You can't remove the account owner.");
    await save(list.map((m) => (m.id === id ? { ...m, deletedAt: new Date().toISOString() } : m)));
    return latency(undefined, 100, 200);
  },

  async restoreMember(id) {
    const list = await load();
    const next = list.map((m) => (m.id === id ? { ...m, deletedAt: undefined } : m));
    const m = next.find((x) => x.id === id);
    if (!m) throw new Error('Member not found');
    await save(next);
    return latency(clone(m), 100, 200);
  },

  async purgeMember(id) {
    const list = await load();
    await deleteSecure(id);
    await save(list.filter((m) => m.id !== id));
  },

  async resetDemoFamily() {
    const list = await load();
    await Promise.all(list.map((m) => deleteSecure(m.id)));
    const fresh = seedFamily();
    await Promise.all(fresh.map(writeSecure));
    await writeIndex(fresh);
    cache = fresh;
    return latency(sortMembers(clone(fresh)));
  },
};

/** The family service the app uses. Replace with the real client when it exists. */
export const familyService: FamilyService = mockFamilyService;
