// Onboarding background (design.md §13.1): OLED black, a faint violet glow
// from the top and a teal glow from the bottom, slowly drifting dust.
import { memo, useEffect } from 'react';
import { AppState, StyleSheet, useWindowDimensions } from 'react-native';
import { Canvas, Fill, Shader, Skia } from '@shopify/react-native-skia';
import { useDerivedValue, useFrameCallback, useReducedMotion, useSharedValue } from 'react-native-reanimated';
import { loopPhase } from './orbitLayout';

const effect = Skia.RuntimeEffect.Make(`
uniform float2 res;
uniform float ph;
float hash(float2 p) { p = fract(p * float2(123.34, 456.21)); p += dot(p, p + 45.32); return fract(p.x * p.y); }
half4 main(float2 p) {
  float H = res.y;
  float3 col = float3(0.0);
  col += float3(0.30, 0.22, 0.62) * exp(-pow(length(p - float2(res.x * 0.5, -H * 0.05)) / (H * 0.42), 2.0) * 1.6) * 0.55;
  col += float3(0.05, 0.42, 0.40) * exp(-pow(length(p - float2(res.x * 0.5, H * 1.05)) / (H * 0.4), 2.0) * 1.6) * 0.5;
  float2 sp = p + float2(cos(ph), sin(2.0 * ph)) * 14.0;
  float2 cell = floor(sp / 30.0);
  float r = hash(cell);
  if (r > 0.55) {
    float2 c = (cell + 0.2 + 0.6 * float2(hash(cell + 1.3), hash(cell + 7.1))) * 30.0;
    float d = length(sp - c);
    float tw = 0.5 + 0.5 * sin(floor(4.0 + 18.0 * r) * ph + r * 50.0);
    col += float3(0.75, 0.82, 1.0) * smoothstep(1.2, 0.0, d) * tw * 0.5;
  }
  col += (hash(p) - 0.5) / 255.0;
  return half4(half3(col), 1.0);
}`)!;

function Backdrop() {
  const { width, height } = useWindowDimensions();
  const reduced = useReducedMotion();
  const clock = useSharedValue(0);
  const cb = useFrameCallback((f) => {
    clock.value += Math.min(f.timeSincePreviousFrame ?? 16, 50) / 1000;
  }, false);
  useEffect(() => {
    cb.setActive(!reduced);
    const sub = AppState.addEventListener('change', (s) => cb.setActive(s === 'active' && !reduced));
    return () => {
      sub.remove();
      cb.setActive(false);
    };
  }, [cb, reduced]);
  const uniforms = useDerivedValue(() => ({ res: [width, height], ph: loopPhase(clock.value) }));
  return (
    <Canvas style={StyleSheet.absoluteFill} pointerEvents="none">
      <Fill>
        <Shader source={effect} uniforms={uniforms} />
      </Fill>
    </Canvas>
  );
}

export const OnboardingBackdrop = memo(Backdrop);
