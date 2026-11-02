// Mock FamilyService for the browser (same contract and behaviour as the
// mobile app's mocks/familyService.ts, AGENT_CORE_AND_FAMILY.md §4.3).
//
//   localStorage   key `familyos.family.v1`: every member, with the data of
//                  the sensitive sections (ids, health, banking) removed.
//                  key `member_<id>_<section>`: that section's data, one small
//                  item per member and section (the mobile app keeps these in
//                  SecureStore; a browser has no equivalent, so this demo
//                  keeps them in this browser only). Never logged.
//
// To use a real backend, implement FamilyService (services/interfaces.ts) and
// change the export at the bottom; the store and screens only see the contract.
import type { FamilyMember, FamilyService, MemberBasics, SectionId } from '../services/interfaces';
import { emptySections, sortMembers } from '../family/model';
import { seedFamily } from './familySeed';
import { API_ENABLED } from '../services/api';
import { apiFamilyService } from '../services/apiFamilyService';

const KEY = 'familyos.family.v1';
const SENSITIVE: SectionId[] = ['ids', 'health', 'banking'];
const secureKey = (id: string, s: SectionId) => `member_${id}_${s}`;

/** Simulated network latency, 250–600 ms (like the other mock services). */
const latency = <T,>(value: T, min = 250, max = 600): Promise<T> =>
  new Promise((resolve) => setTimeout(() => resolve(value), min + Math.random() * (max - min)));

const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v));

/** Storage that tolerates private windows and blocked site data (falls back to memory). */
const memory = new Map<string, string>();
const store = {
  get(k: string): string | null {
    try {
      return window.localStorage.getItem(k);
    } catch {
      return memory.get(k) ?? null;
    }
  },
  set(k: string, v: string) {
    try {
      window.localStorage.setItem(k, v);
    } catch {
      memory.set(k, v);
    }
  },
  remove(k: string) {
    try {
      window.localStorage.removeItem(k);
    } catch {
      memory.delete(k);
    }
  },
};

let cache: FamilyMember[] | null = null;

function writeSecure(m: FamilyMember) {
  for (const s of SENSITIVE) store.set(secureKey(m.id, s), JSON.stringify(m.sections[s].data));
}

function deleteSecure(id: string) {
  for (const s of SENSITIVE) store.remove(secureKey(id, s));
}

/** Persist the non-sensitive part of every member. */
function writeIndex(list: FamilyMember[]) {
  const stripped = list.map((m) => {
    const c = clone(m);
    for (const s of SENSITIVE) c.sections[s].data = {};
    return c;
  });
  store.set(KEY, JSON.stringify(stripped));
}

function load(): FamilyMember[] {
  if (cache) return cache;
  const raw = store.get(KEY);
  let list: FamilyMember[];
  if (!raw) {
    // First visit: seed the demo family.
    list = seedFamily();
    list.forEach(writeSecure);
    writeIndex(list);
  } else {
    list = JSON.parse(raw) as FamilyMember[];
    // Removals whose Undo window was cut short by closing the tab are final.
    const stale = list.filter((m) => m.deletedAt);
    if (stale.length) {
      stale.forEach((m) => deleteSecure(m.id));
      list = list.filter((m) => !m.deletedAt);
      writeIndex(list);
    }
    for (const m of list) {
      for (const s of SENSITIVE) {
        const v = store.get(secureKey(m.id, s));
        m.sections[s].data = v ? (JSON.parse(v) as Record<string, unknown>) : {};
      }
    }
  }
  cache = list;
  return list;
}

function save(list: FamilyMember[], changed?: FamilyMember) {
  cache = list;
  if (changed) writeSecure(changed);
  writeIndex(list);
}

function newId() {
  return `m_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 7)}`;
}

export const mockFamilyService: FamilyService = {
  async listMembers() {
    return latency(sortMembers(clone(load().filter((m) => !m.deletedAt))));
  },

  async getMember(id) {
    const m = load().find((x) => x.id === id && !x.deletedAt);
    return latency(m ? clone(m) : null, 120, 250);
  },

  async createMember(basics: MemberBasics) {
    const list = load();
    const now = new Date().toISOString();
    const m: FamilyMember = {
      id: newId(),
      isOwner: false,
      ...basics,
      sections: emptySections('notStarted'),
      createdAt: now,
      updatedAt: now,
    };
    save([...list, m], m);
    return latency(clone(m));
  },

  async updateBasics(id, patch) {
    const next = load().map((m) => (m.id === id ? { ...m, ...patch, updatedAt: new Date().toISOString() } : m));
    const m = next.find((x) => x.id === id);
    if (!m) throw new Error('Member not found');
    save(next);
    return latency(clone(m), 150, 300);
  },

  async updateSection(id, sectionId, data, status) {
    const next = load().map((m) =>
      m.id === id
        ? { ...m, sections: { ...m.sections, [sectionId]: { status, data } }, updatedAt: new Date().toISOString() }
        : m
    );
    const m = next.find((x) => x.id === id);
    if (!m) throw new Error('Member not found');
    save(next, SENSITIVE.includes(sectionId) ? m : undefined);
    return latency(clone(m), 150, 300);
  },

  async deleteMember(id) {
    const list = load();
    const target = list.find((m) => m.id === id);
    if (!target) return;
    if (target.isOwner) throw new Error("You can't remove the account owner.");
    save(list.map((m) => (m.id === id ? { ...m, deletedAt: new Date().toISOString() } : m)));
    return latency(undefined, 100, 200);
  },

  async restoreMember(id) {
    const next = load().map((m) => (m.id === id ? { ...m, deletedAt: undefined } : m));
    const m = next.find((x) => x.id === id);
    if (!m) throw new Error('Member not found');
    save(next);
    return latency(clone(m), 100, 200);
  },

  async purgeMember(id) {
    deleteSecure(id);
    save(load().filter((m) => m.id !== id));
  },

  async resetDemoFamily() {
    load().forEach((m) => deleteSecure(m.id));
    const fresh = seedFamily();
    fresh.forEach(writeSecure);
    writeIndex(fresh);
    cache = fresh;
    return latency(sortMembers(clone(fresh)));
  },
};

/** The family service the app uses: the backend when VITE_FAMILYOS_API=on (production builds), else the mocks. */
export const familyService: FamilyService = API_ENABLED ? apiFamilyService : mockFamilyService;
