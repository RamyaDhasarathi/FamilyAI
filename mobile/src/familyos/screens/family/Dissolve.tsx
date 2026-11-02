// Particle dissolve (and its reverse) for removing / restoring a member
// (AGENT_CORE_AND_FAMILY.md §4.9), drawn with Skia over the avatar spot.
// Same idea as the core's particle morph: points leave the shape radially
// with a little curl and fade; `reverse` gathers them back in.
import { useEffect, useMemo } from 'react';
import { StyleSheet } from 'react-native';
import { Canvas, Points, vec } from '@shopify/react-native-skia';
import { useDerivedValue, useSharedValue, withTiming, Easing } from 'react-native-reanimated';
import { seededRandom } from '../../graphics/crystalGeometry';

const N = 90;

export function Dissolve({ color, reverse, cx = 40, cy = 40, size = 80 }: { color: string; reverse?: boolean; cx?: number; cy?: number; size?: number }) {
  const t = useSharedValue(0);
  const seeds = useMemo(() => {
    const r = seededRandom(7);
    return Array.from({ length: N }, () => ({ a: r() * Math.PI * 2, d: Math.sqrt(r()) * 26, s: 0.6 + r() * 0.9, c: (r() - 0.5) * 1.4 }));
  }, []);
  useEffect(() => {
    t.set(withTiming(1, { duration: 650, easing: Easing.out(Easing.cubic) }));
  }, [t]);
  const pts = useDerivedValue(() => {
    const k = reverse ? 1 - t.value : t.value;
    return seeds.map((p) => {
      const r = p.d + k * 46 * p.s;
      const a = p.a + k * p.c;
      return vec(cx + Math.cos(a) * r, cy + Math.sin(a) * r);
    });
  });
  const opacity = useDerivedValue(() => (reverse ? t.value : 1 - t.value));
  return (
    <Canvas style={[styles.c, { left: 12 + 28 - cx, top: '50%', marginTop: -cy, width: size + 40, height: size + 40 }]} pointerEvents="none">
      <Points points={pts} mode="points" color={color} style="stroke" strokeWidth={2.4} strokeCap="round" opacity={opacity} />
    </Canvas>
  );
}

const styles = StyleSheet.create({
  c: { position: 'absolute' },
});
