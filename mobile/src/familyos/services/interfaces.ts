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

export interface FamilyMember {
  id: string;
  name: string;
  relationship: string;
  age: number;
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
  getFamily(): Promise<FamilyMember[]>;
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
