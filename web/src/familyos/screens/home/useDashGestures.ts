// Opening the Dashboard follows the input (AGENT_WEB.md §8.1.7, §9):
//   touch / pen: swipe up anywhere on Home that isn't a control;
//   mouse wheel / trackpad: scroll down on Home, scroll up at the top of the
//   Dashboard to come back.
// The gem shrinks and travels with the same value (scene.v.dashT).
import { useEffect, useRef, type RefObject } from 'react';
import { useDrag } from '@use-gesture/react';
import type { OrbitEngine } from '../../engine/OrbitEngine';
import { settleDash } from '../../engine/coreInput';
import { useFamilyOS } from '../../store/useFamilyOS';
import { useWebUI } from '../../store/useWebUI';

const interactive = (t: EventTarget | null) => !!(t as HTMLElement | null)?.closest?.('button, a, input, textarea, [role="dialog"], [data-no-swipe]');

export function useDashGestures(engine: OrbitEngine, layer: RefObject<HTMLElement | null>, enabled: boolean, onStart: () => void) {
  const setDashOpen = useWebUI((s) => s.setDashOpen);
  const started = useRef(false);

  const bind = useDrag(
    ({ first, last, movement: [mx, my], velocity: [, vy], direction: [, dy], event, cancel }) => {
      const pe = event as PointerEvent;
      if (first) {
        started.current = false;
        if (!enabled || pe.pointerType === 'mouse' || interactive(pe.target) || useWebUI.getState().dashOpen) {
          cancel();
          return;
        }
      }
      // Mobile: activeOffsetY(-14), failOffsetX ±30.
      if (!started.current) {
        if (Math.abs(mx) > 30) {
          cancel();
          return;
        }
        if (my > -14) return;
        started.current = true;
        onStart();
      }
      const H = engine.stage.H;
      engine.scene.tw.set('dashT', Math.min(1, Math.max(0, -my / (H * 0.55))));
      engine.kick();
      if (last) {
        const open = engine.scene.v.dashT > 0.3 || (vy > 0.5 && dy < 0);
        settleDash(engine.scene, open);
        setDashOpen(open);
      }
    },
    { filterTaps: true, pointer: { touch: true } }
  );

  // Wheel: accumulate while the user scrolls, settle shortly after they stop.
  useEffect(() => {
    if (!layer.current || !enabled) return;
    let settle: number | null = null;
    let base = 0;
    let acc = 0;
    const onWheel = (e: WheelEvent) => {
      const st = useFamilyOS.getState();
      const ui = useWebUI.getState();
      if (st.sheet || ui.helpOpen || e.ctrlKey) return;
      const scroller = (e.target as HTMLElement).closest?.('[data-dash-scroller]') as HTMLElement | null;
      if (ui.dashOpen) {
        if (scroller && scroller.scrollTop > 0) return;
        if (e.deltaY > 0 && settle === null) return;
      } else if (e.deltaY < 0 && settle === null) return;
      if (settle === null) {
        base = engine.scene.v.dashT;
        acc = 0;
        if (!ui.dashOpen) onStart();
      } else window.clearTimeout(settle);
      acc += e.deltaMode === 1 ? e.deltaY * 16 : e.deltaY;
      const t = Math.min(1, Math.max(0, base + acc / (engine.stage.H * 0.55)));
      engine.scene.tw.set('dashT', t);
      engine.kick();
      settle = window.setTimeout(() => {
        settle = null;
        const opening = !useWebUI.getState().dashOpen;
        const open = opening ? engine.scene.v.dashT > 0.15 : engine.scene.v.dashT > 0.85;
        settleDash(engine.scene, open);
        setDashOpen(open);
      }, 140);
    };
    window.addEventListener('wheel', onWheel, { passive: true });
    return () => {
      window.removeEventListener('wheel', onWheel);
      if (settle !== null) window.clearTimeout(settle);
    };
  }, [engine, layer, enabled, setDashOpen, onStart]);

  return bind;
}
