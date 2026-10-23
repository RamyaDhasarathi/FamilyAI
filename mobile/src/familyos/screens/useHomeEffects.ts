// Home side effects that drive the scene from app state.
import { useCallback, useEffect, useRef, useState } from 'react';
import * as Haptics from 'expo-haptics';
import { cancelAnimation, withRepeat, withSequence, withTiming } from 'react-native-reanimated';
import { paletteOf, PALETTE_LEN, type Scenario } from '../theme/stateThemes';
import { durations, easings } from '../theme/motion';
import { copy } from '../mocks/data';
import { useFamilyOS } from '../store/useFamilyOS';
import type { OrbitScene } from '../graphics/sceneState';

/** Every scenario change interpolates palette, halo and background together (700 ms). */
export function useScenarioSync(scene: OrbitScene, mood: Scenario) {
  const first = useRef(true);
  useEffect(() => {
    const target = paletteOf(mood);
    if (first.current) {
      first.current = false;
      scene.paletteFrom.set(target);
      scene.paletteTo.set(target);
      scene.paletteT.set(1);
      return;
    }
    // Start from wherever the blend currently is, so rapid changes never snap.
    const a = scene.paletteFrom.value;
    const b = scene.paletteTo.value;
    const t = Math.min(1, scene.paletteT.value);
    const cur = new Array(PALETTE_LEN).fill(0).map((_, i) => a[i] + (b[i] - a[i]) * t);
    scene.paletteFrom.set(cur);
    scene.paletteTo.set(target);
    scene.paletteT.set(0);
    scene.paletteT.set(withTiming(1, { duration: durations.scenario, easing: easings.inOutSine }));
  }, [mood, scene]);
}

/** When the last item is resolved: close the sheet, burst of particles, success haptic. */
export function useCelebration(scene: OrbitScene) {
  const count = useFamilyOS((s) => s.needs.length);
  const seed = useFamilyOS((s) => s.seed);
  const prev = useRef({ count, seed });
  useEffect(() => {
    const p = prev.current;
    prev.current = { count, seed };
    if (p.seed !== seed || !(p.count > 0 && count === 0)) return;
    const st = useFamilyOS.getState();
    if (st.sheet === 'needs') st.closeSheet();
    void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    st.toast(copy.allDoneToast);
    scene.burst.set(1);
    scene.burst.set(withTiming(0, { duration: 1500, easing: easings.outCubic }));
    scene.squash.set(withSequence(withTiming(0.9, { duration: 120 }), withTiming(1, { duration: 500 })));
  }, [count, seed, scene]);
}

/** Mic: pulse + waveform + halo breathing on fake audio levels, then a canned transcript into chat. */
export function useListening(scene: OrbitScene) {
  const [listening, setListening] = useState(false);
  const openChat = useFamilyOS((s) => s.openChat);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const listen = useCallback(() => {
    if (timer.current) return;
    setListening(true);
    void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    scene.listen.set(withRepeat(
      withSequence(
        withTiming(0.9, { duration: 110 }),
        withTiming(0.35, { duration: 150 }),
        withTiming(0.7, { duration: 90 }),
        withTiming(0.15, { duration: 170 })
      ),
      -1
    ));
    timer.current = setTimeout(() => {
      timer.current = null;
      cancelAnimation(scene.listen);
      scene.listen.set(withTiming(0, { duration: 250 }));
      setListening(false);
      openChat('home', copy.heardTranscript);
    }, durations.listen);
  }, [openChat, scene]);
  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);
  return { listening, listen };
}
