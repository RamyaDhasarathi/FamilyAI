// The gem at ~64 px with its dust (Dashboard top, agent screens; AGENT.md §7.1).
// Same geometry and shader as the Home core, own clock, own small canvas.
import { memo, useEffect, useMemo } from 'react';
import { AppState } from 'react-native';
import { Canvas, Fill, Picture, Shader, createPicture } from '@shopify/react-native-skia';
import { useDerivedValue, useFrameCallback, useReducedMotion, useSharedValue } from 'react-native-reanimated';
import { paletteOf, type Scenario } from '../theme/stateThemes';
import { hexToRgb } from '../theme/tokens';
import { ambientEffect } from './ambientShader';
import { coreMeshLow } from './crystalGeometry';
import { drawCrystal } from './crystalRender';
import { loopPhase } from './orbitLayout';

/** Palette derived from one agent colour: light → agent → deep, mostly tinted. */
function agentPalette(hex: string): number[] {
  const [r, g, b] = hexToRgb(hex);
  const base = paletteOf('calm');
  const light = [Math.min(1, r * 0.6 + 0.45), Math.min(1, g * 0.6 + 0.45), Math.min(1, b * 0.6 + 0.45)];
  const deep = [r * 0.55 + 0.1, g * 0.4 + 0.08, b * 0.7 + 0.25];
  return [...light, r, g, b, ...deep, 0.62, r, g, b, ...base.slice(13)];
}

interface Props {
  size: number;
  scenario?: Scenario;
  agentColor?: string;
}

function MiniGemView({ size, scenario = 'calm', agentColor }: Props) {
  const reduced = useReducedMotion();
  const clock = useSharedValue(0);
  const pal = useMemo(() => (agentColor ? agentPalette(agentColor) : paletteOf(scenario)), [agentColor, scenario]);
  const cb = useFrameCallback((f) => {
    clock.value += Math.min(f.timeSincePreviousFrame ?? 16, 50) / 1000;
  }, false);
  useEffect(() => {
    cb.setActive(!reduced);
    const sub = AppState.addEventListener('change', (s) => cb.setActive(s === 'active' && !reduced));
    return () => sub.remove();
  }, [cb, reduced]);

  const R = size * 0.27;
  const uniforms = useDerivedValue(() => ({
    res: [size, size],
    ph: loopPhase(clock.value),
    center: [size / 2, size / 2],
    radius: R,
    tint: [0, 0, 0],
    corner: [0, 0, 0],
    halo: [pal[10], pal[11], pal[12]],
    haloAmt: 0.55,
    dustAmt: 1.2,
    dustCol: [0.75, 0.84, 1],
    starAmt: 0,
    sats: [-99, -99, -99, -99, -99, -99, -99, -99, -99, -99],
    satCols: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    satR: 1,
    satAmt: 0,
    lowPower: 1,
  }));
  const picture = useDerivedValue(() =>
    createPicture((canvas) => {
      const ph = loopPhase(clock.value);
      drawCrystal(canvas, coreMeshLow, {
        cx: size / 2,
        cy: size / 2,
        R,
        rotY: 4 * ph,
        tiltX: 0.35,
        phase: 4 * ph,
        palette: pal,
        agent: null,
        alpha: 1,
        explode: 0,
        glow: 0,
        sx: 1,
        sy: 1,
        lowPower: true,
      });
    })
  );
  return (
    <Canvas style={{ width: size, height: size }} pointerEvents="none">
      <Fill>
        <Shader source={ambientEffect} uniforms={uniforms} />
      </Fill>
      <Picture picture={picture} />
    </Canvas>
  );
}

export const MiniGem = memo(MiniGemView);
