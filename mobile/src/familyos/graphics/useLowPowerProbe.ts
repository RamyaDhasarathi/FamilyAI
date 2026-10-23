// Decide `lowPowerGraphics` at start-up (AGENT.md §7.1, §11.2): measure the
// UI-thread frame time over ~2 s after the intro; if the device averages
// slower than ~42 fps, switch to fewer facets, fewer particles and no
// satellite spin for the rest of the session.
import { useEffect } from 'react';
import { useFrameCallback, useSharedValue } from 'react-native-reanimated';
import { scheduleOnRN } from 'react-native-worklets';
import type { OrbitScene } from './sceneState';

const SKIP = 40;
const SAMPLE = 120;
const SLOW_MS = 24;

export function useLowPowerProbe(scene: OrbitScene, onDecide: (low: boolean, avgMs: number) => void) {
  const n = useSharedValue(0);
  const sum = useSharedValue(0);
  const cb = useFrameCallback((f) => {
    const dt = f.timeSincePreviousFrame;
    if (dt == null) return;
    n.value += 1;
    if (n.value <= SKIP) return;
    sum.value += Math.min(dt, 100);
    if (n.value === SKIP + SAMPLE) {
      const avg = sum.value / SAMPLE;
      const low = avg > SLOW_MS;
      if (low) scene.lowPower.value = true;
      scheduleOnRN(onDecide, low, avg);
    }
  }, true);
  useEffect(() => {
    const id = setTimeout(() => cb.setActive(false), 8000);
    return () => clearTimeout(id);
  }, [cb]);
}
