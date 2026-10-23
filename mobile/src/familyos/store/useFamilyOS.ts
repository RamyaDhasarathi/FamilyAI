// App state (zustand). Everything it shows comes from the service layer, so
// swapping mocks for the real backend does not touch this file's callers.
import { create } from 'zustand';
import type { AgentId } from '../theme/tokens';
import type { Scenario } from '../theme/stateThemes';
import { SCENARIOS } from '../theme/stateThemes';
import type {
  AgentCard,
  ChatMessage,
  FamilyMember,
  NeedsItem,
  Profile,
  SummaryMode,
  TodayBrief,
  WalkthroughStep,
} from '../services/interfaces';
import { service } from '../mocks/services';
import { copy, defaultSummaryMode } from '../mocks/data';
import { headlineItem, moodOf, sortNeeds } from '../mocks/scenarios';

export type SheetName = 'today' | 'needs' | 'profile' | 'chat' | null;

export interface Toast {
  id: number;
  text: string;
}

export interface Walk {
  active: boolean;
  /** Set when the walkthrough is filtered to one agent. */
  agent?: AgentId;
  index: number;
  steps: WalkthroughStep[];
  /** Read aloud (summary button in Listen mode). */
  speak: boolean;
}

interface State {
  booted: boolean;
  loggedIn: boolean;
  profile: Profile | null;
  family: FamilyMember[];
  dashboard: AgentCard[];
  today: TodayBrief | null;
  seed: Scenario;
  needs: NeedsItem[];
  summaryMode: SummaryMode;
  lowPower: boolean;
  undone: Record<string, true>;
  threads: Record<string, ChatMessage[]>;
  typing: Record<string, boolean>;
  suggestions: Record<string, string[]>;
  toasts: Toast[];
  sheet: SheetName;
  chatThread: string;
  /** Text to send as soon as the chat opens ("Ask about this", voice). */
  chatPending: string | null;
  walk: Walk;
  /** Dev-only commands for Home (navigation/devLinks.ts). */
  devCommand: { id: number; cmd: Record<string, string> } | null;

  boot(): Promise<void>;
  setScenario(s: Scenario): Promise<void>;
  cycleScenario(): void;
  resolve(id: string): void;
  snooze(id: string): void;
  setSummaryMode(mode: SummaryMode): void;
  toggleSummaryMode(): void;
  toast(text: string): void;
  dismissToast(id: number): void;
  openSheet(name: Exclude<SheetName, null>): void;
  openChat(thread: string, pending?: string): void;
  /** Prepare a thread (and an auto-sent message) without opening the Home sheet. */
  queueChat(thread: string, pending?: string): void;
  closeSheet(): void;
  ensureThread(thread: string): Promise<void>;
  sendChat(thread: string, text: string): Promise<void>;
  takePending(): string | null;
  undo(entryId: string): void;
  setWalk(w: Partial<Walk>): void;
  setLowPower(v: boolean): void;
  setDevCommand(cmd: Record<string, string>): void;
  logIn(email: string, password: string): Promise<boolean>;
  logOut(): Promise<void>;
}

let toastId = 0;

export const useFamilyOS = create<State>((set, get) => ({
  booted: false,
  loggedIn: true,
  profile: null,
  family: [],
  dashboard: [],
  today: null,
  seed: 'calm',
  needs: [],
  summaryMode: defaultSummaryMode,
  lowPower: false,
  undone: {},
  threads: {},
  typing: {},
  suggestions: {},
  toasts: [],
  sheet: null,
  chatThread: 'home',
  chatPending: null,
  walk: { active: false, index: 0, steps: [], speak: false },
  devCommand: null,

  async boot() {
    const [profile, family, home, today, needs] = await Promise.all([
      service.getProfile(),
      service.getFamily(),
      service.getHomeSummary(),
      service.getTodayItems(),
      service.getNeedsYou(get().seed),
    ]);
    set({ profile, family, dashboard: home.dashboard, today, needs: sortNeeds(needs), booted: true });
  },

  async setScenario(s) {
    const needs = await service.getNeedsYou(s);
    set({ seed: s, needs: sortNeeds(needs) });
  },

  cycleScenario() {
    const i = SCENARIOS.indexOf(get().seed);
    void get().setScenario(SCENARIOS[(i + 1) % SCENARIOS.length]);
  },

  resolve(id) {
    const item = get().needs.find((n) => n.id === id);
    if (!item) return;
    set({ needs: get().needs.filter((n) => n.id !== id) });
    void service.resolveItem(id, item.action.id);
  },

  snooze(id) {
    set({ needs: get().needs.filter((n) => n.id !== id) });
    void service.snoozeItem(id);
  },

  setSummaryMode(mode) {
    set({ summaryMode: mode });
    void service.setSummaryMode(mode);
    get().toast(copy.summaryModeToast[mode]);
  },

  toggleSummaryMode() {
    get().setSummaryMode(get().summaryMode === 'listen' ? 'read' : 'listen');
  },

  toast(text) {
    const id = ++toastId;
    set({ toasts: [...get().toasts.slice(-1), { id, text }] });
  },

  dismissToast(id) {
    set({ toasts: get().toasts.filter((t) => t.id !== id) });
  },

  openSheet(name) {
    set({ sheet: name });
  },

  openChat(thread, pending) {
    get().queueChat(thread, pending);
    set({ sheet: 'chat' });
  },

  queueChat(thread, pending) {
    set({ chatThread: thread, chatPending: pending ?? null });
    void get().ensureThread(thread);
  },

  closeSheet() {
    set({ sheet: null });
  },

  async ensureThread(thread) {
    if (get().threads[thread]) return;
    const [greeting, chips] = await Promise.all([service.getChatGreeting(thread), service.getChatSuggestions(thread)]);
    if (get().threads[thread]) return;
    set({
      threads: { ...get().threads, [thread]: [greeting] },
      suggestions: { ...get().suggestions, [thread]: chips },
    });
  },

  async sendChat(thread, text) {
    const t = text.trim();
    if (!t) return;
    await get().ensureThread(thread);
    const mine: ChatMessage = { id: `u${Date.now()}`, role: 'user', text: t };
    set({
      threads: { ...get().threads, [thread]: [...(get().threads[thread] ?? []), mine] },
      typing: { ...get().typing, [thread]: true },
    });
    const needs = get().needs;
    const reply = await service.sendChat(thread, t, {
      scenario: moodOf(needs),
      openCount: needs.length,
      topText: headlineItem(needs)?.text,
    });
    set({
      threads: { ...get().threads, [thread]: [...(get().threads[thread] ?? []), reply] },
      typing: { ...get().typing, [thread]: false },
    });
  },

  takePending() {
    const p = get().chatPending;
    if (p) set({ chatPending: null });
    return p;
  },

  undo(entryId) {
    set({ undone: { ...get().undone, [entryId]: true } });
    void service.undoAction(entryId);
    get().toast(copy.undoneToast);
  },

  setWalk(w) {
    set({ walk: { ...get().walk, ...w } });
  },

  setLowPower(v) {
    set({ lowPower: v });
  },

  setDevCommand(cmd) {
    set({ devCommand: { id: Date.now(), cmd } });
  },

  async logIn(email, password) {
    const r = await service.logIn(email, password);
    if (r.ok) set({ loggedIn: true });
    return r.ok;
  },

  async logOut() {
    await service.logOut();
    set({ loggedIn: false, sheet: null });
  },
}));

/** Derived selectors. */
export const useMood = () => useFamilyOS((s) => moodOf(s.needs));
