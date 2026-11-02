// One Escape key for the whole app (AGENT_WEB.md §9): it closes the top-most
// panel, then ends the walkthrough, then goes back. Whatever registered last
// (and is still active) handles the key.
import { useEffect, useRef } from 'react';

type Entry = { id: number; fn: () => void };
const stack: Entry[] = [];
let nextId = 0;
let bound = false;

function onKey(e: KeyboardEvent) {
  if (e.key !== 'Escape' || e.defaultPrevented) return;
  const top = stack[stack.length - 1];
  if (!top) return;
  e.preventDefault();
  top.fn();
}

export function useEscape(active: boolean, fn: () => void) {
  const ref = useRef(fn);
  useEffect(() => {
    ref.current = fn;
  });
  useEffect(() => {
    if (!active) return;
    if (!bound) {
      window.addEventListener('keydown', onKey);
      bound = true;
    }
    const entry: Entry = { id: ++nextId, fn: () => ref.current() };
    stack.push(entry);
    return () => {
      const i = stack.findIndex((x) => x.id === entry.id);
      if (i >= 0) stack.splice(i, 1);
    };
  }, [active]);
}

/** True while some layer above the page handles Escape (used to ignore page shortcuts). */
export const escapeDepth = () => stack.length;
