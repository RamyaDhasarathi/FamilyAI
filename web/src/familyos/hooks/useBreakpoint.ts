// Viewport size and breakpoint (AGENT_WEB.md §8.0): phone < 640 ≤ tablet < 1024 ≤ desktop < 1920 ≤ large.
import { useSyncExternalStore } from 'react';
import { breakpointOf, type Breakpoint } from '../engine/orbitLayout';

export interface Viewport {
  W: number;
  H: number;
  bp: Breakpoint;
  /** Desktop or larger (drawers, popovers, key hints). */
  wide: boolean;
  /** Primary pointer is a mouse or trackpad. */
  fine: boolean;
}

let snap: Viewport | null = null;
const fineQuery = typeof window !== 'undefined' ? window.matchMedia('(hover: hover) and (pointer: fine)') : null;

function read(): Viewport {
  const W = window.innerWidth;
  const H = window.innerHeight;
  const fine = !!fineQuery?.matches;
  if (snap && snap.W === W && snap.H === H && snap.fine === fine) return snap;
  const bp = breakpointOf(W);
  snap = { W, H, bp, wide: bp === 'desktop' || bp === 'large', fine };
  return snap;
}

function subscribe(cb: () => void) {
  window.addEventListener('resize', cb);
  window.addEventListener('orientationchange', cb);
  fineQuery?.addEventListener('change', cb);
  return () => {
    window.removeEventListener('resize', cb);
    window.removeEventListener('orientationchange', cb);
    fineQuery?.removeEventListener('change', cb);
  };
}

export function useViewport(): Viewport {
  return useSyncExternalStore(subscribe, read, read);
}

export const useBreakpoint = () => useViewport().bp;
