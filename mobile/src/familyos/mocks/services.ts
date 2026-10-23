// Mock implementation of FamilyOSService (AGENT.md §5.3).
//
// HOW TO SWAP IN THE REAL BACKEND
//   1. Write `services/apiService.ts` exporting an object that implements
//      `FamilyOSService` from services/interfaces.ts (fetch your API, map the
//      responses to these types).
//   2. Change the single line at the bottom of this file, or point
//      `store/useFamilyOS.ts` at your object instead of `mockService`.
//   Screens and the store only ever talk to `FamilyOSService`, so nothing
//   else changes. The existing SwiftUI client in ios/Kit/API.swift lists the
//   endpoints (/v1/me, /v1/household, /v1/obligations, …) to start from.
import type { FamilyOSService, NeedsItem } from '../services/interfaces';
import type { AgentId } from '../theme/tokens';
import { agentDetails, agentWalkthroughs, dashboardCards, family, needsItems, profile, todayBrief } from './data';
import { greetingFor, replyTo, suggestionsFor } from './chatReplies';
import { scenarioItems } from './scenarios';

/** Simulated network latency, 250–600 ms. */
const latency = <T>(value: T, min = 250, max = 600): Promise<T> =>
  new Promise((resolve) => setTimeout(() => resolve(value), min + Math.random() * (max - min)));

let msgId = 0;
const nextId = () => `m${Date.now()}-${msgId++}`;

export const mockService: FamilyOSService = {
  getProfile: () => latency(profile),
  getFamily: () => latency(family),
  getHomeSummary: () => latency({ greetingName: profile.name, dashboard: dashboardCards }),
  getTodayItems: () => latency(todayBrief),
  getNeedsYou: (scenario) => {
    const open = new Set(scenarioItems[scenario]);
    return latency(needsItems.filter((n) => open.has(n.id)).map((n): NeedsItem => ({ ...n })));
  },
  resolveItem: () => latency({ ok: true, message: 'Done' }, 150, 300),
  snoozeItem: () => latency({ ok: true, message: 'Snoozed until tonight' }, 150, 300),
  getWalkthrough: (agent?: AgentId) =>
    latency(agent ? agentWalkthroughs[agent] : todayBrief.items.map((t) => ({ agent: t.agent, text: t.text })), 0, 60),
  getAgentDetail: (agentId) => latency(agentDetails[agentId], 120, 300),
  undoAction: () => latency({ ok: true, message: 'Undone' }, 150, 300),
  sendChat: (threadId, text, context) =>
    // The typing indicator shows for 600–1200 ms (AGENT.md §8.6).
    latency({ id: nextId(), role: 'assistant' as const, text: replyTo(threadId, text, context) }, 600, 1200),
  getChatGreeting: (threadId) => latency({ id: nextId(), role: 'assistant' as const, text: greetingFor(threadId, profile.name) }, 0, 0),
  getChatSuggestions: (threadId) =>
    latency(threadId === 'home' ? suggestionsFor('home') : agentDetails[threadId as AgentId].chips, 0, 0),
  setSummaryMode: () => latency({ ok: true, message: 'Saved' }, 50, 150),
  logIn: () => latency({ ok: true, message: 'Welcome back' }, 400, 700),
  logOut: () => latency({ ok: true, message: 'Logged out' }, 150, 300),
};

/** The service the app uses. Replace with the real client when it exists. */
export const service: FamilyOSService = mockService;
