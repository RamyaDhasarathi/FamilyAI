// MASTER_AGENT.md §11 "Tests to add": the desktop gate is true at or above
// 1024 px, false below, follows resizes live, and is false with no browser
// window at all (the native apps and server rendering).
import { afterEach, describe, expect, it, vi } from 'vitest';
import { DESKTOP_MIN_WIDTH, DESKTOP_QUERY, isDesktopWeb, subscribeDesktopWeb } from './useIsDesktopWeb';

/** A minimal window whose matchMedia evaluates min-width against a settable width. */
function fakeWindow(width: number) {
  const listeners = new Set<() => void>();
  const state = { width };
  const mql = {
    media: DESKTOP_QUERY,
    get matches() {
      return state.width >= DESKTOP_MIN_WIDTH;
    },
    addEventListener: (_: string, fn: () => void) => listeners.add(fn),
    removeEventListener: (_: string, fn: () => void) => listeners.delete(fn),
  };
  const win = {
    matchMedia: (q: string) => {
      expect(q).toBe('(min-width: 1024px)');
      return mql;
    },
  };
  const resize = (w: number) => {
    state.width = w;
    listeners.forEach((fn) => fn());
  };
  return { win, resize, listeners };
}

afterEach(() => vi.unstubAllGlobals());

describe('useIsDesktopWeb', () => {
  it('uses the existing 1024 px desktop breakpoint', () => {
    expect(DESKTOP_MIN_WIDTH).toBe(1024);
  });

  it('is true at and above the breakpoint, false below', () => {
    for (const [w, want] of [
      [390, false],
      [768, false],
      [1023, false],
      [1024, true],
      [1440, true],
      [1920, true],
    ] as const) {
      vi.stubGlobal('window', fakeWindow(w).win);
      expect(isDesktopWeb(), `${w}px`).toBe(want);
    }
  });

  it('follows a live resize across the breakpoint', () => {
    const f = fakeWindow(1440);
    vi.stubGlobal('window', f.win);
    const seen: boolean[] = [];
    const off = subscribeDesktopWeb(() => seen.push(isDesktopWeb()));
    f.resize(900);
    f.resize(1280);
    off();
    expect(seen).toEqual([false, true]);
    expect(f.listeners.size).toBe(0);
  });

  it('is false with no browser window (native apps, server rendering)', () => {
    vi.stubGlobal('window', undefined);
    expect(isDesktopWeb()).toBe(false);
    expect(() => subscribeDesktopWeb(() => {})()).not.toThrow();
  });
});
