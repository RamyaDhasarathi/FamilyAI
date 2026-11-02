// prefers-reduced-motion (AGENT_WEB.md §6.5): ambient rotation and drift stop,
// transitions become quick fades, every hotspot keeps working.
import { useSyncExternalStore } from 'react';

const q = typeof window !== 'undefined' ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;

export function prefersReducedMotion() {
  return !!q?.matches;
}

export function useReducedMotion(): boolean {
  return useSyncExternalStore(
    (cb) => {
      q?.addEventListener('change', cb);
      return () => q?.removeEventListener('change', cb);
    },
    () => !!q?.matches,
    () => false
  );
}
