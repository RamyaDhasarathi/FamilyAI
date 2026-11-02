// Shrink a one-line heading to fit its box, down to `min` of its CSS size
// (the mobile greeting uses adjustsFontSizeToFit with minimumFontScale 0.78).
import { useLayoutEffect, type RefObject } from 'react';

export function useFitText(ref: RefObject<HTMLElement | null>, text: string, min = 0.78) {
  useLayoutEffect(() => {
    const el = ref.current;
    const box = el?.parentElement;
    if (!el || !box) return;
    const fit = () => {
      el.style.fontSize = '';
      const base = parseFloat(getComputedStyle(el).fontSize);
      const k = el.clientWidth / Math.max(1, el.scrollWidth);
      if (k < 1) el.style.fontSize = `${(base * Math.max(min, k - 0.01)).toFixed(2)}px`;
    };
    fit();
    const ro = new ResizeObserver(fit);
    ro.observe(box);
    return () => ro.disconnect();
  }, [ref, text, min]);
}
