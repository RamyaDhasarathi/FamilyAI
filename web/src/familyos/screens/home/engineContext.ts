// The Home stage engine, shared by the Home overlays.
import { createContext, useContext, useEffect, useRef } from 'react';
import type { FrameHook, OrbitEngine } from '../../engine/OrbitEngine';

export const EngineContext = createContext<OrbitEngine | null>(null);

export function useEngine(): OrbitEngine {
  const e = useContext(EngineContext);
  if (!e) throw new Error('useEngine must be used inside the Home stage');
  return e;
}

/** Run `fn` every frame (style writes only; never set React state here). */
export function useFrame(engine: OrbitEngine, fn: FrameHook) {
  const ref = useRef(fn);
  useEffect(() => {
    ref.current = fn;
  });
  useEffect(() => engine.onFrame((e, dt) => ref.current(e, dt)), [engine]);
}
