// Focus trap and return for dialogs, drawers and menus (AGENT_WEB.md §11.4):
// while active, Tab cycles inside the container; on close, focus goes back to
// whatever had it before (the avatar pill, the summary line, …).
import { useEffect, type RefObject } from 'react';

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function focusables(root: HTMLElement) {
  return Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE)).filter((el) => el.offsetParent !== null || el === document.activeElement);
}

export function useFocusTrap(ref: RefObject<HTMLElement | null>, active: boolean, opts: { initial?: RefObject<HTMLElement | null>; restore?: boolean } = {}) {
  useEffect(() => {
    if (!active) return;
    const root = ref.current;
    if (!root) return;
    const before = document.activeElement as HTMLElement | null;
    const t = window.setTimeout(() => {
      const first = opts.initial?.current ?? focusables(root)[0] ?? root;
      if (!root.contains(document.activeElement)) first.focus({ preventScroll: true });
    }, 30);
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Tab') return;
      const list = focusables(root);
      if (list.length === 0) {
        e.preventDefault();
        return;
      }
      const first = list[0];
      const last = list[list.length - 1];
      if (e.shiftKey && (document.activeElement === first || !root.contains(document.activeElement))) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => {
      window.clearTimeout(t);
      document.removeEventListener('keydown', onKey);
      if (opts.restore !== false && before && document.contains(before)) before.focus({ preventScroll: true });
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);
}
