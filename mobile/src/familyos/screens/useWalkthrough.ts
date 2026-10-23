// Summary walkthrough (AGENT.md §8.1.6): steps through items ~3.5 s each.
// Per step the gem's particles morph into the agent's icon, that agent's
// satellite is ringed, and (in Listen mode) the item is read aloud.
// Stopping, or finishing, flies the particles back into the gem.
import { useCallback, useEffect, useRef } from 'react';
import * as Speech from 'expo-speech';
import { Easing, withDelay, withTiming } from 'react-native-reanimated';
import type { AgentId } from '../theme/tokens';
import { AGENT_IDS, colors, hexToRgb } from '../theme/tokens';
import { durations } from '../theme/motion';
import { currentPalette, type OrbitScene } from '../graphics/sceneState';
import { service } from '../mocks/services';
import { useFamilyOS } from '../store/useFamilyOS';

const AGENT_RGB = AGENT_IDS.map((id) => hexToRgb(colors.agents[id]));

/** Morph the particle cloud to `shape` (0 = gem, 1..5 = agent icons). */
export function morphScene(scene: OrbitScene, shape: number) {
  const from = scene.morphTo.value;
  if (from === shape && scene.morphAlpha.value > 0.5) return;
  const pal = currentPalette(scene);
  const gemColour = [pal[10], pal[11], pal[12]];
  scene.morphFrom.value = from;
  scene.morphColFrom.value = from === 0 ? gemColour : scene.morphColTo.value;
  scene.morphColTo.value = shape === 0 ? gemColour : AGENT_RGB[shape - 1];
  scene.morphTo.value = shape;
  scene.morphT.value = 0;
  scene.morphT.value = withTiming(1, { duration: durations.morph, easing: Easing.linear });
  if (shape !== 0) {
    scene.morphAlpha.value = withTiming(1, { duration: 220 });
    scene.explode.value = withTiming(1, { duration: durations.dissolve, easing: Easing.out(Easing.cubic) });
  } else {
    scene.morphAlpha.value = withDelay(520, withTiming(0, { duration: 380 }));
    scene.explode.value = withDelay(320, withTiming(0, { duration: 700, easing: Easing.inOut(Easing.cubic) }));
  }
}

export function useWalkthrough(scene: OrbitScene) {
  const setWalk = useFamilyOS((s) => s.setWalk);
  const run = useRef(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  /** Step currently on screen; late TTS callbacks from earlier steps are ignored. */
  const current = useRef(-1);

  const clear = () => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
  };

  const stop = useCallback(() => {
    run.current += 1;
    clear();
    void Speech.stop();
    scene.satHighlight.value = -1;
    morphScene(scene, 0);
    setWalk({ active: false, index: 0 });
  }, [scene, setWalk]);

  const start = useCallback(
    async (agent: AgentId | undefined, speak: boolean) => {
      clear();
      void Speech.stop();
      const id = ++run.current;
      const steps = await service.getWalkthrough(agent);
      if (id !== run.current || steps.length === 0) return;
      setWalk({ active: true, agent, index: 0, steps, speak });

      const step = (i: number) => {
        if (id !== run.current) return;
        if (i >= steps.length) {
          stop();
          return;
        }
        current.current = i;
        setWalk({ index: i });
        const s = steps[i];
        const k = AGENT_IDS.indexOf(s.agent);
        scene.satHighlight.value = k;
        morphScene(scene, k + 1);
        const t0 = Date.now();
        const next = () => {
          if (id !== run.current || current.current !== i) return;
          current.current = -1;
          clear();
          const wait = Math.max(0, durations.walkStep - (Date.now() - t0));
          timer.current = setTimeout(() => step(i + 1), wait + (speak ? 250 : 0));
        };
        if (speak) {
          Speech.speak(s.text, { rate: 0.98, pitch: 1.0, onDone: next, onStopped: () => undefined, onError: next });
          // Safety net if the TTS engine never reports completion.
          timer.current = setTimeout(next, 12000);
        } else {
          timer.current = setTimeout(() => step(i + 1), durations.walkStep);
        }
      };
      step(0);
    },
    [scene, setWalk, stop]
  );

  useEffect(
    () => () => {
      run.current += 1;
      clear();
      void Speech.stop();
    },
    []
  );

  return { start, stop };
}
