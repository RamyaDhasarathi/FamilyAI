// Family-member state (AGENT_CORE_AND_FAMILY.md §4). All reads and writes go
// through FamilyService; this store keeps the list, the soft-delete / Undo
// window and the hand-off between screens (which member just changed, which
// one is being removed).
import { create } from 'zustand';
import type { FamilyMember, MemberBasics, SectionId, SectionStatus } from '../services/interfaces';
import { familyService } from '../mocks/familyService';
import { dependentsOf, displayName, sectionsNeedingUpdate, sortMembers, stageOf } from '../family/model';
import { useFamilyOS } from './useFamilyOS';

/** How long "Removed · Undo" stays before the member is purged (§4.9). */
export const UNDO_MS = 6000;

interface PendingRemoval {
  member: FamilyMember;
  /** Index in the sorted list, so Undo can restore it to the same place. */
  index: number;
  timer: ReturnType<typeof setTimeout>;
}

interface FamilyState {
  members: FamilyMember[];
  loaded: boolean;
  /** Ids whose card should glow briefly (just added or restored). */
  highlight: string | null;
  /** Ids being removed right now (their card dissolves). */
  removing: string[];
  pending: Record<string, PendingRemoval>;

  load(): Promise<void>;
  add(basics: MemberBasics, finishLater: boolean): Promise<FamilyMember>;
  updateBasics(id: string, patch: Partial<MemberBasics>): Promise<FamilyMember>;
  saveSection(id: string, section: SectionId, data: Record<string, unknown>, status: SectionStatus): Promise<FamilyMember>;
  /**
   * Remove with Undo. `reassign` applies first when the member pays children's
   * allowances: another adult's id, or null for "Decide later".
   */
  remove(id: string, reassign?: string | null): Promise<void>;
  undo(id: string): Promise<void>;
  reset(): Promise<void>;
  clearHighlight(): void;
}

const replace = (list: FamilyMember[], m: FamilyMember) => sortMembers(list.map((x) => (x.id === m.id ? m : x)));

export const useFamily = create<FamilyState>((set, get) => ({
  members: [],
  loaded: false,
  highlight: null,
  removing: [],
  pending: {},

  async load() {
    const members = await familyService.listMembers();
    set({ members, loaded: true });
  },

  async add(basics, finishLater) {
    const m = await familyService.createMember(basics);
    set({ members: sortMembers([...get().members, m]), highlight: m.id });
    const toast = useFamilyOS.getState().toast;
    if (finishLater) toast(`${displayName(m)} added to your family`);
    return m;
  },

  async updateBasics(id, patch) {
    const before = get().members.find((x) => x.id === id);
    const m = await familyService.updateBasics(id, patch);
    set({ members: replace(get().members, m) });
    // A date-of-birth change can move someone to another avatar stage (§4.6).
    if (before && patch.dateOfBirth && stageOf(before).stage !== stageOf(m).stage) {
      const st = stageOf(m);
      useFamilyOS.getState().toast(`${displayName(m)} moved to Stage ${st.stage} · ${st.name}`);
    }
    return m;
  },

  async saveSection(id, section, data, status) {
    const m = await familyService.updateSection(id, section, data, status);
    set({ members: replace(get().members, m) });
    return m;
  },

  async remove(id, reassign) {
    const toast = useFamilyOS.getState().toast;
    const list = get().members;
    const m = list.find((x) => x.id === id);
    if (!m) return;
    if (m.isOwner) {
      toast("You can't remove the account owner.");
      return;
    }
    // Children whose allowance this member paid: move to another adult, or
    // mark their payments section "needs update" (Decide later).
    if (reassign !== undefined) {
      for (const child of dependentsOf(list, id)) {
        const data = { ...child.sections.banking.data, paidFrom: reassign ?? undefined };
        const status: SectionStatus = reassign ? child.sections.banking.status : 'needsUpdate';
        const updated = await familyService.updateSection(child.id, 'banking', data, status);
        set({ members: replace(get().members, updated) });
      }
    }
    const index = get().members.findIndex((x) => x.id === id);
    set({ removing: [...get().removing, id] });
    await familyService.deleteMember(id);
    // Let the card dissolve before it leaves the list.
    setTimeout(() => {
      set({ members: get().members.filter((x) => x.id !== id), removing: get().removing.filter((x) => x !== id) });
    }, 520);
    const timer = setTimeout(() => {
      const p = { ...get().pending };
      delete p[id];
      set({ pending: p });
      void familyService.purgeMember(id);
    }, UNDO_MS);
    set({ pending: { ...get().pending, [id]: { member: m, index, timer } } });
    toast(`${displayName(m)} removed`, { duration: UNDO_MS, action: { label: 'Undo', onPress: () => void get().undo(id) } });
  },

  async undo(id) {
    const p = get().pending[id];
    if (!p) return;
    clearTimeout(p.timer);
    const rest = { ...get().pending };
    delete rest[id];
    set({ pending: rest });
    const m = await familyService.restoreMember(id);
    set({ members: sortMembers([...get().members.filter((x) => x.id !== id), m]), highlight: m.id });
  },

  async reset() {
    for (const p of Object.values(get().pending)) clearTimeout(p.timer);
    const members = await familyService.resetDemoFamily();
    set({ members, pending: {}, removing: [], highlight: null });
    useFamilyOS.getState().toast('Demo family restored');
  },

  clearHighlight() {
    set({ highlight: null });
  },
}));

/** Members with at least one section needing an update (Profile menu chip, §4.1). */
export const useNeedsUpdateCount = () => useFamily((s) => s.members.filter((m) => sectionsNeedingUpdate(m).length > 0).length);
