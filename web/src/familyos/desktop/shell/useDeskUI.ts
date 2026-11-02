// Desktop-only UI state, kept apart from the shared stores: the ⌘K palette,
// whether the Home shows its Ask chat instead of the stones, and record ids to flash after "Show me" (any desk page can highlight rows
// whose `data-desk-id` matches).
import { create } from 'zustand';

interface DeskUI {
  paletteOpen: boolean;
  /** Things happening today (the orb crystal's desktop tooltip); kept by DeskShell. */
  todayCount: number;
  setTodayCount(n: number): void;
  /** Ids to highlight briefly; pages add `desk-flash` to matching rows. */
  flash: string[];
  setPaletteOpen(v: boolean): void;
  /** Home has turned into the Ask chat (after its first message); false shows the stones again. */
  homeChat: boolean;
  setHomeChat(v: boolean): void;
  flashIds(ids: string[], ms?: number): void;
}

let flashTimer: number | undefined;

export const useDeskUI = create<DeskUI>((set) => ({
  paletteOpen: false,
  todayCount: 0,
  setTodayCount: (n) => set({ todayCount: n }),
  flash: [],
  setPaletteOpen: (v) => set({ paletteOpen: v }),
  homeChat: false,
  setHomeChat: (v) => set({ homeChat: v }),
  flashIds(ids, ms = 2600) {
    window.clearTimeout(flashTimer);
    set({ flash: ids });
    flashTimer = window.setTimeout(() => set({ flash: [] }), ms);
  },
}));
