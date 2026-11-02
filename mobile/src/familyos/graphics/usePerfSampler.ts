// Dev-only frame sampler for AGENT.md §13.5: `familyos://dev?perf=1` measures
// the next 300 UI-thread frames on Home and logs average, p95 and how many
// frames missed the 60 fps budget.
import { useEffect } from 'react';
import { useFrameCallback, useSharedValue } from 'react-native-reanimated';
import { scheduleOnRN } from 'react-native-worklets';
import { useFamilyOS } from '../store/useFamilyOS';
import type { OrbitScene } from './sceneState';

const N = 300;

const SECTIONS = ['satRecord', 'satDraw', 'core', 'morph', 'picture', 'uniforms'];

function report(samples: number[], prof: number[], mx: number[]) {
  const sorted = [...samples].sort((a, b) => a - b);
  const avg = samples.reduce((s, v) => s + v, 0) / samples.length;
  const p95 = sorted[Math.floor(samples.length * 0.95)];
  const slow = samples.filter((v) => v > 20).length;
  console.log(
    `[perf] ${samples.length} frames: avg ${avg.toFixed(1)} ms (${(1000 / avg).toFixed(0)} fps), p95 ${p95.toFixed(1)} ms, >20 ms: ${slow}`
  );
  console.log(`[perf] per frame: ${prof.map((v, i) => `${SECTIONS[i]} ${(v / samples.length).toFixed(2)}`).join(' · ')} ms`);
  console.log(`[perf] worst / calls: ${SECTIONS.map((n, i) => `${n} ${mx[i].toFixed(1)}/${mx[6 + i]}`).join(' · ')}`);
}

export function usePerfSampler(scene: OrbitScene) {
  const buf = useSharedValue<number[]>([]);
  const cb = useFrameCallback((f) => {
    const dt = f.timeSincePreviousFrame;
    if (dt == null) return;
    buf.modify((arr) => {
      'worklet';
      arr.push(dt);
      return arr;
    });
    const arr = buf.get();
    if (arr.length >= N) {
      scheduleOnRN(report, arr.slice(), scene.prof.get().slice(), scene.profMax.get().slice());
      buf.set([]);
    }
  }, false);
  useEffect(() => {
    if (!__DEV__) return;
    return useFamilyOS.subscribe((s, prev) => {
      if (s.devCommand && s.devCommand !== prev.devCommand && s.devCommand.cmd.perf) {
        buf.set([]);
        scene.prof.set([0, 0, 0, 0, 0, 0]);
        scene.profMax.set(new Array(12).fill(0));
        cb.setActive(true);
        setTimeout(() => cb.setActive(false), 9000);
      }
    });
  }, [buf, cb, scene]);
}
