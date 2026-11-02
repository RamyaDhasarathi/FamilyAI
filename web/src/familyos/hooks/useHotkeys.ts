// Single-key shortcuts (AGENT_WEB.md §9). Ignored while the user types in a
// field, and when Ctrl / Alt / Meta are held (browser shortcuts win).
import { useEffect, useRef } from 'react';

export function isTyping(target: EventTarget | null) {
  const el = target as HTMLElement | null;
  if (!el) return false;
  const tag = el.tagName;
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || el.isContentEditable;
}

export type KeyMap = Record<string, (e: KeyboardEvent) => void>;

/**
 * `map` keys are KeyboardEvent.key values ('/', 't', 'ArrowUp', 'S' for Shift+S, '?').
 * Letter keys match case-insensitively unless Shift is part of the binding.
 */
export function useHotkeys(map: KeyMap, enabled = true) {
  const ref = useRef(map);
  useEffect(() => {
    ref.current = map;
  });
  useEffect(() => {
    if (!enabled) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey || isTyping(e.target)) return;
      const m = ref.current;
      const k = e.key;
      const fn = (e.shiftKey && m[`Shift+${k.toUpperCase()}`]) || m[k] || (k.length === 1 && !e.shiftKey ? m[k.toLowerCase()] : undefined);
      if (fn) fn(e);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [enabled]);
}
