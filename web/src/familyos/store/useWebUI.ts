// Web-only UI state, kept apart from the mobile store (useFamilyOS.ts is
// copied from the mobile app unchanged): the Dashboard, the shortcut help,
// the satellite → agent reveal, and remembered preferences.
import { create } from 'zustand';
import type { AgentId } from '../theme/tokens';

export interface Reveal {
  agent: AgentId;
  x: number;
  y: number;
}

const LOW_POWER_KEY = 'familyos.lowPower';

/** The user's own low-power choice, if they made one in Settings ('1' / '0'). */
export function storedLowPower(): boolean | null {
  try {
    const v = window.localStorage.getItem(LOW_POWER_KEY);
    return v === null ? null : v === '1';
  } catch {
    return null;
  }
}

export function storeLowPower(v: boolean) {
  try {
    window.localStorage.setItem(LOW_POWER_KEY, v ? '1' : '0');
  } catch {
    /* private window: the choice lasts for this visit only */
  }
}

interface WebUI {
  dashOpen: boolean;
  helpOpen: boolean;
  reveal: Reveal | null;
  /** Chat on an agent page (Home's chat lives in useFamilyOS.sheet). */
  agentChat: AgentId | null;
  setDashOpen(v: boolean): void;
  setHelpOpen(v: boolean): void;
  setReveal(r: Reveal | null): void;
  setAgentChat(a: AgentId | null): void;
}

export const useWebUI = create<WebUI>((set) => ({
  dashOpen: false,
  helpOpen: false,
  reveal: null,
  agentChat: null,
  setDashOpen: (v) => set({ dashOpen: v }),
  setHelpOpen: (v) => set({ helpOpen: v }),
  setReveal: (r) => set({ reveal: r }),
  setAgentChat: (a) => set({ agentChat: a }),
}));
