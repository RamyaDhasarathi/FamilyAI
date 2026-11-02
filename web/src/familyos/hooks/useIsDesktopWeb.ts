// The one desktop gate (MASTER_AGENT.md §6.1). Everything desktop-only —
// sidebar, ⌘K, floating Ask, stones that open dashboards, the desk routes'
// shell — renders only when this is true. Width only, never the user agent:
// a matchMedia query plus its change listener, so resizing a desktop window
// below 1024 px falls back to the mobile behaviour live (§6.3). The Expo app
// never runs this file, so iOS / Android are always "not desktop".
import { useSyncExternalStore } from 'react';

/** The existing desktop breakpoint (hooks/useBreakpoint.ts: desktop ≥ 1024). */
export const DESKTOP_MIN_WIDTH = 1024;
export const DESKTOP_QUERY = `(min-width: ${DESKTOP_MIN_WIDTH}px)`;

let mql: MediaQueryList | null = null;
let mqlOwner: Window | null = null;

/** Read lazily so tests (and server rendering) can provide their own window. */
function query(): MediaQueryList | null {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return null;
  if (!mql || mqlOwner !== window) {
    mql = window.matchMedia(DESKTOP_QUERY);
    mqlOwner = window;
  }
  return mql;
}

/** Snapshot: true on a desktop-width browser window, false everywhere else. */
export function isDesktopWeb(): boolean {
  return !!query()?.matches;
}

export function subscribeDesktopWeb(cb: () => void): () => void {
  const q = query();
  if (!q) return () => {};
  q.addEventListener('change', cb);
  return () => q.removeEventListener('change', cb);
}

export function useIsDesktopWeb(): boolean {
  return useSyncExternalStore(subscribeDesktopWeb, isDesktopWeb, () => false);
}
