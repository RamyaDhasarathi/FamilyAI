// Home side effects that drive the stage from app state (mobile useHomeEffects.ts).
import { useCallback, useEffect, useRef, useState } from 'react';
import type { Scenario } from '../../theme/stateThemes';
import { durations } from '../../theme/motion';
import { copy } from '../../mocks/data';
import { useFamilyOS } from '../../store/useFamilyOS';
import type { OrbitEngine } from '../../engine/OrbitEngine';
import { blendToScenario, celebrate } from '../../engine/coreInput';
import { ease, timing } from '../../engine/tween';

/** Every scenario change interpolates palette, halo and background together (700 ms). */
export function useScenarioSync(engine: OrbitEngine, mood: Scenario) {
  const first = useRef(true);
  useEffect(() => {
    blendToScenario(engine.scene, mood, first.current);
    first.current = false;
    engine.kick();
  }, [mood, engine]);
}

/** When the last item is resolved: close the panel, toast, particle burst (§8.4). */
export function useCelebration(engine: OrbitEngine) {
  const count = useFamilyOS((s) => s.needs.length);
  const seed = useFamilyOS((s) => s.seed);
  const prev = useRef({ count, seed });
  useEffect(() => {
    const p = prev.current;
    prev.current = { count, seed };
    if (p.seed !== seed || !(p.count > 0 && count === 0)) return;
    const st = useFamilyOS.getState();
    if (st.sheet === 'needs') st.closeSheet();
    st.toast(copy.allDoneToast);
    celebrate(engine.scene);
  }, [count, seed, engine]);
}

/** Mic: pulse + waveform + halo breathing on fake levels, then a canned transcript into chat. */
export function useListening(engine: OrbitEngine | null, onHeard: (text: string) => void) {
  const [listening, setListening] = useState(false);
  const timer = useRef<number | null>(null);
  const heard = useRef(onHeard);
  useEffect(() => {
    heard.current = onHeard;
  });
  const listen = useCallback(() => {
    if (timer.current) return;
    setListening(true);
    const tw = engine?.scene.tw;
    tw?.loop('listen', [timing(0.9, 110, ease.inOutSine), timing(0.35, 150, ease.inOutSine), timing(0.7, 90, ease.inOutSine), timing(0.15, 170, ease.inOutSine)]);
    engine?.kick();
    timer.current = window.setTimeout(() => {
      timer.current = null;
      tw?.to('listen', timing(0, 250, ease.outCubic));
      setListening(false);
      heard.current(copy.heardTranscript);
    }, durations.listen);
  }, [engine]);
  useEffect(
    () => () => {
      if (timer.current) window.clearTimeout(timer.current);
    },
    []
  );
  return { listening, listen };
}
