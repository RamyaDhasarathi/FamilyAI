// Typed contracts between the UI and the data layer (AGENT.md §5.3).
// The mock implementation lives in mocks/services.ts. A real backend client
// implements the same `FamilyOSService` interface; screens never change.
import type { AgentId, Severity } from '../theme/tokens';
import type { Scenario } from '../theme/stateThemes';

export type SummaryMode = 'listen' | 'read';

export interface Profile {
  name: string;
  initial: string;
  plan: string;
  email: string;
}

// ── Family members (AGENT_CORE_AND_FAMILY.md §4.2) ─────────────────────────

export type Relationship =
  | 'Self' | 'Spouse' | 'Partner' | 'Son' | 'Daughter' | 'Father' | 'Mother'
  | 'Brother' | 'Sister' | 'Grandfather' | 'Grandmother' | 'Grandson' | 'Granddaughter'
  | 'Uncle' | 'Aunt' | 'Nephew' | 'Niece' | 'Cousin' | 'In-law' | 'Other';

export type SectionId = 'basic' | 'contact' | 'ids' | 'health' | 'banking';
export type SectionStatus = 'complete' | 'needsUpdate' | 'notStarted';

export interface MemberSection {
  status: SectionStatus;
  data: Record<string, unknown>;
}

export interface FamilyMember {
  id: string;
  /** True only for the account holder ("Self"). */
  isOwner: boolean;
  fullName: string;
  preferredName?: string;
  relationship: Relationship;
  /** When relationship === 'Other'. */
  relationshipOther?: string;
  /** ISO date (YYYY-MM-DD). */
  dateOfBirth: string;
  photoUri?: string;
  sections: Record<SectionId, MemberSection>;
  createdAt: string;
  updatedAt: string;
  /** Set while a removal can still be undone (soft delete). */
  deletedAt?: string;
}
// Derived, never stored: age, avatarStage (1–8), stageName, completion (0–1),
// sectionsNeedingUpdate. See family/model.ts.

export interface MemberBasics {
  fullName: string;
  preferredName?: string;
  relationship: Relationship;
  relationshipOther?: string;
  dateOfBirth: string;
  photoUri?: string;
}

/**
 * Family-member storage. The mock (mocks/familyService.ts) keeps members on
 * the device: non-sensitive fields in AsyncStorage, ID / health / banking data
 * in SecureStore. A real backend implements the same contract.
 */
export interface FamilyService {
  /** Active members (soft-deleted ones excluded), owner first. */
  listMembers(): Promise<FamilyMember[]>;
  getMember(id: string): Promise<FamilyMember | null>;
  createMember(basics: MemberBasics): Promise<FamilyMember>;
  updateBasics(id: string, patch: Partial<MemberBasics>): Promise<FamilyMember>;
  updateSection(id: string, sectionId: SectionId, data: Record<string, unknown>, status: SectionStatus): Promise<FamilyMember>;
  /** Soft delete: hidden from lists, restorable until purged. */
  deleteMember(id: string): Promise<void>;
  restoreMember(id: string): Promise<FamilyMember>;
  /** Permanently delete, including the member's secure-store keys. */
  purgeMember(id: string): Promise<void>;
  resetDemoFamily(): Promise<FamilyMember[]>;
}

export interface TodayItem {
  id: string;
  agent: AgentId;
  text: string;
}

export interface TodayTile {
  label: string;
  value: string;
  detail: string;
}

export interface TodayBrief {
  /** Optional "TOMORROW MORNING" commute card. */
  commute?: { section: string; label: string; title: string; detail: string; alt: string };
  weather: TodayTile;
  firstEvent: TodayTile;
  items: TodayItem[];
}

export interface NeedsAction {
  id: string;
  label: string;
}

export interface NeedsItem {
  id: string;
  severity: Exclude<Severity, 'positive'>;
  agent: AgentId;
  /** Meta timestamp, e.g. "NOW", "3 MIN AGO", "YESTERDAY". */
  time: string;
  text: string;
  action: NeedsAction;
  /** Lower = shown first in the Home headline among equal severities. */
  priority: number;
}

export interface WalkthroughStep {
  agent: AgentId;
  text: string;
}

export interface AgentCard {
  agent: AgentId;
  status: string;
}

export interface StatTile {
  label: string;
  value: number;
  /** Rendered as prefix + formatted value + suffix. */
  prefix?: string;
  suffix?: string;
  decimals?: number;
  /** Shown as-is instead of counting up (e.g. "6:00 pm"). */
  text?: string;
}

export interface TimelineEntry {
  id: string;
  when: string;
  title: string;
  description: string;
  rows?: [string, string][];
  /** The newest action can be undone. */
  undoable?: boolean;
}

export type AgentHero =
  | { kind: 'sparkline'; label: string; value: string; delta: string; up: boolean; series: number[] }
  | { kind: 'bars'; label: string; value: string; note: string; bars: number[]; todayIndex: number }
  | { kind: 'progress'; label: string; value: string; note: string; items: { name: string; pct: number }[] }
  | { kind: 'ring'; label: string; value: string; note: string; pct: number };

export interface AgentDetail {
  agent: AgentId;
  title: string;
  subtitle: string;
  hero: AgentHero;
  stats: StatTile[];
  timeline: TimelineEntry[];
  chips: string[];
}

export interface ChatMessage {
  id: string;
  role: 'assistant' | 'user';
  text: string;
}

export interface HomeSummary {
  greetingName: string;
  dashboard: AgentCard[];
}

export interface ResolveResult {
  ok: boolean;
  message: string;
}

export interface FamilyOSService {
  getProfile(): Promise<Profile>;
  getHomeSummary(): Promise<HomeSummary>;
  getTodayItems(): Promise<TodayBrief>;
  /** Open items for a scenario (the dev switcher seeds different sets). */
  getNeedsYou(scenario: Scenario): Promise<NeedsItem[]>;
  resolveItem(id: string, actionId: string): Promise<ResolveResult>;
  snoozeItem(id: string): Promise<ResolveResult>;
  getWalkthrough(agent?: AgentId): Promise<WalkthroughStep[]>;
  getAgentDetail(agentId: AgentId): Promise<AgentDetail>;
  undoAction(actionId: string): Promise<ResolveResult>;
  /** Thread is 'home' or an agent id. Returns the assistant's reply. */
  sendChat(
    threadId: string,
    text: string,
    context: { scenario: Scenario; openCount: number; topText?: string }
  ): Promise<ChatMessage>;
  getChatGreeting(threadId: string): Promise<ChatMessage>;
  getChatSuggestions(threadId: string): Promise<string[]>;
  setSummaryMode(mode: SummaryMode): Promise<ResolveResult>;
  logIn(email: string, password: string): Promise<ResolveResult>;
  logOut(): Promise<ResolveResult>;
}
