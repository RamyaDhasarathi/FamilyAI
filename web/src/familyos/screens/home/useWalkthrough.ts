// Summary walkthrough (AGENT_WEB.md §8.1.6, mobile useWalkthrough.ts): steps
// through items ~3.5 s each. Per step the gem's particles morph into the
// agent's icon, that satellite is ringed and the status label reads e.g.
// "TODAY · FINANCE · 5 OF 7". In Listen mode each item is read aloud with the
// Web Speech API (feature-detected; cancelled on stop and on unmount).
// Stopping, or finishing, flies the particles back into the gem.
// `stopNow` (desktop navigation, MASTER_AGENT.md §7 Phase 1.2) stops the same
// way and then snaps the gem home at once, so coming back never shows a
// half-finished morph.
import { useCallback, useEffect, useRef } from 'react';
import type { AgentId } from '../../theme/tokens';
import { AGENT_IDS } from '../../theme/tokens';
import { durations } from '../../theme/motion';
import { service } from '../../mocks/services';
import { webCopy } from '../../mocks/webData';
import { useFamilyOS } from '../../store/useFamilyOS';
import type { OrbitEngine } from '../../engine/OrbitEngine';
import { morphScene, setHighlight } from '../../engine/coreInput';
import { snapMorphHome } from './snapMorph';

export const speechSupported = () => typeof window !== 'undefined' && 'speechSynthesis' in window && 'SpeechSynthesisUtterance' in window;

function englishVoice(): SpeechSynthesisVoice | null {
  const voices = window.speechSynthesis.getVoices();
  return (
    voices.find((v) => v.lang === 'en-US' && /natural|samantha|google us/i.test(v.name)) ??
    voices.find((v) => v.lang === 'en-US') ??
    voices.find((v) => v.lang.startsWith('en')) ??
    null
  );
}

const once = { warned: false };

export function useWalkthrough(engine: OrbitEngine) {
  const setWalk = useFamilyOS((s) => s.setWalk);
  const run = useRef(0);
  const timer = useRef<number | null>(null);
  /** Step currently on screen; late speech callbacks from earlier steps are ignored. */
  const current = useRef(-1);

  const clear = () => {
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = null;
  };
  const silence = () => {
    if (speechSupported()) window.speechSynthesis.cancel();
  };

  const stop = useCallback(() => {
    run.current += 1;
    clear();
    silence();
    setHighlight(engine.scene, -1);
    morphScene(engine.scene, 0);
    engine.kick();
    setWalk({ active: false, index: 0 });
  }, [engine, setWalk]);

  const stopNow = useCallback(() => {
    stop();
    snapMorphHome(engine.scene);
    engine.kick();
  }, [engine, stop]);

  const start = useCallback(
    async (agent: AgentId | undefined, wantSpeech: boolean) => {
      clear();
      silence();
      const id = ++run.current;
      const steps = await service.getWalkthrough(agent);
      if (id !== run.current || steps.length === 0) return;
      const speak = wantSpeech && speechSupported();
      if (wantSpeech && !speak && !once.warned) {
        once.warned = true;
        useFamilyOS.getState().toast(webCopy.speechUnavailable);
      }
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
        setHighlight(engine.scene, k);
        morphScene(engine.scene, k + 1);
        engine.kick();
        const t0 = Date.now();
        const next = () => {
          if (id !== run.current || current.current !== i) return;
          current.current = -1;
          clear();
          const wait = Math.max(0, durations.walkStep - (Date.now() - t0));
          timer.current = window.setTimeout(() => step(i + 1), wait + (speak ? 250 : 0));
        };
        if (speak) {
          const u = new SpeechSynthesisUtterance(s.text);
          u.lang = 'en-US';
          u.rate = 0.98;
          u.pitch = 1;
          const v = englishVoice();
          if (v) u.voice = v;
          u.onend = next;
          u.onerror = next;
          window.speechSynthesis.speak(u);
          // Safety net if the engine never reports completion.
          timer.current = window.setTimeout(next, 12000);
        } else {
          timer.current = window.setTimeout(() => step(i + 1), durations.walkStep);
        }
      };
      step(0);
    },
    [engine, setWalk, stop]
  );

  useEffect(
    () => () => {
      run.current += 1;
      clear();
      silence();
    },
    []
  );

  return { start, stop, stopNow };
}
