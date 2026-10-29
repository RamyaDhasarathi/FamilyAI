// Agent hero charts (AGENT.md §7.6).
import { useEffect, useMemo, useState } from 'react';
import { StyleSheet, View } from 'react-native';
import { BlurMask, Canvas, Circle, LinearGradient, Path, Skia, vec } from '@shopify/react-native-skia';
import Animated, {
  Easing,
  useAnimatedStyle,
  useDerivedValue,
  useSharedValue,
  withDelay,
  withTiming,
} from 'react-native-reanimated';
import { durations, easings } from '../theme/motion';
import { withAlpha } from '../theme/tokens';

/**
 * Smooth curve through the points: Catmull-Rom converted to cubic Béziers.
 * For segment p1→p2 with neighbours p0, p3 the control points are
 * p1 + (p2 − p0)/6 and p2 − (p3 − p1)/6 (uniform Catmull-Rom, tension ½).
 */
function catmullRom(pts: [number, number][]) {
  let d = `M${pts[0][0]} ${pts[0][1]}`;
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[Math.max(0, i - 1)];
    const p1 = pts[i];
    const p2 = pts[i + 1];
    const p3 = pts[Math.min(pts.length - 1, i + 2)];
    const c1x = p1[0] + (p2[0] - p0[0]) / 6;
    const c1y = p1[1] + (p2[1] - p0[1]) / 6;
    const c2x = p2[0] - (p3[0] - p1[0]) / 6;
    const c2y = p2[1] - (p3[1] - p1[1]) / 6;
    d += ` C${c1x} ${c1y} ${c2x} ${c2y} ${p2[0]} ${p2[1]}`;
  }
  return d;
}

export function Sparkline({ series, color, width, height }: { series: number[]; color: string; width: number; height: number }) {
  const { line, fill, end } = useMemo(() => {
    const min = Math.min(...series);
    const max = Math.max(...series);
    const pad = 8;
    const pts = series.map((v, i): [number, number] => [
      pad + (i / (series.length - 1)) * (width - pad * 2),
      pad + (1 - (v - min) / (max - min || 1)) * (height - pad * 2),
    ]);
    const d = catmullRom(pts);
    const last = pts[pts.length - 1];
    return {
      line: Skia.Path.MakeFromSVGString(d)!,
      fill: Skia.Path.MakeFromSVGString(`${d} L${last[0]} ${height} L${pts[0][0]} ${height} Z`)!,
      end: last,
    };
  }, [series, width, height]);
  const t = useSharedValue(0);
  useEffect(() => {
    t.set(0);
    t.set(withTiming(1, { duration: durations.sparkline, easing: easings.inOutCubic }));
  }, [series, t]);
  const fillOpacity = useDerivedValue(() => t.value);
  const dotR = useDerivedValue(() => (t.value > 0.95 ? 4 : 0));
  const glowR = useDerivedValue(() => (t.value > 0.95 ? 9 : 0));
  return (
    <Canvas style={{ width, height }}>
      <Path path={fill} opacity={fillOpacity}>
        <LinearGradient start={vec(0, 0)} end={vec(0, height)} colors={[withAlpha(color, 0.28), withAlpha(color, 0)]} />
      </Path>
      <Path path={line} style="stroke" strokeWidth={2} color={color} strokeCap="round" strokeJoin="round" start={0} end={t} />
      <Circle cx={end[0]} cy={end[1]} r={glowR} color={withAlpha(color, 0.45)}>
        <BlurMask blur={5} style="normal" />
      </Circle>
      <Circle cx={end[0]} cy={end[1]} r={dotR} color={color} />
    </Canvas>
  );
}

function Bar({ h, i, color, maxH }: { h: number; i: number; color: string; maxH: number }) {
  const v = useSharedValue(0);
  useEffect(() => {
    v.set(withDelay(i * 60, withTiming(1, { duration: 520, easing: Easing.out(Easing.cubic) })));
  }, [i, v]);
  const st = useAnimatedStyle(() => ({ height: Math.max(8, h * maxH) * v.value }));
  return <Animated.View style={[styles.bar, { backgroundColor: color }, st]} />;
}

/** Seven rounded bars; today's in the agent colour, the rest muted blue-grey. */
export function WeekBars({ bars, todayIndex, color, height = 72 }: { bars: number[]; todayIndex: number; color: string; height?: number }) {
  return (
    <View style={[styles.bars, { height }]}>
      {bars.map((b, i) => (
        <Bar key={i} i={i} h={b} maxH={height} color={i === todayIndex ? color : 'rgba(120,140,170,0.42)'} />
      ))}
    </View>
  );
}

function ProgressRow({ pct, color, i }: { pct: number; color: string; i: number }) {
  const v = useSharedValue(0);
  useEffect(() => {
    v.set(withDelay(i * 90, withTiming(pct, { duration: 700, easing: Easing.out(Easing.cubic) })));
  }, [pct, i, v]);
  const st = useAnimatedStyle(() => ({ width: `${v.value * 100}%` }));
  return (
    <View style={styles.track}>
      <Animated.View style={[styles.fillBar, { backgroundColor: color }, st]} />
    </View>
  );
}

export function ProgressBars({ items, color, renderLabel }: { items: { name: string; pct: number }[]; color: string; renderLabel: (name: string, pct: number) => React.ReactNode }) {
  return (
    <View>
      {items.map((it, i) => (
        <View key={it.name} style={styles.progressItem}>
          {renderLabel(it.name, it.pct)}
          <ProgressRow pct={it.pct} color={color} i={i} />
        </View>
      ))}
    </View>
  );
}

/** Task ring that sweeps to `pct` on mount. */
export function TaskRing({ pct, color, size = 84 }: { pct: number; color: string; size?: number }) {
  const r = size / 2 - 6;
  const arc = useMemo(() => {
    const p = Skia.Path.MakeFromSVGString(
      `M${size / 2} ${size / 2 - r} A${r} ${r} 0 1 1 ${size / 2 - 0.01} ${size / 2 - r}`
    );
    return p!;
  }, [r, size]);
  const t = useSharedValue(0);
  useEffect(() => {
    t.set(withTiming(pct, { duration: 900, easing: easings.inOutCubic }));
  }, [pct, t]);
  return (
    <Canvas style={{ width: size, height: size }}>
      <Path path={arc} style="stroke" strokeWidth={6} color="rgba(255,255,255,0.08)" />
      <Path path={arc} style="stroke" strokeWidth={6} color={color} strokeCap="round" start={0} end={t} />
    </Canvas>
  );
}

/** Count-up for stat tiles (600 ms on mount). */
export function useCountUp(target: number, duration = durations.countUp) {
  const [v, setV] = useState(0);
  useEffect(() => {
    let raf = 0;
    const t0 = Date.now();
    const tick = () => {
      const k = Math.min(1, (Date.now() - t0) / duration);
      const e = 1 - Math.pow(1 - k, 3);
      setV(target * e);
      if (k < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, duration]);
  return v;
}

const styles = StyleSheet.create({
  bars: { flexDirection: 'row', alignItems: 'flex-end', justifyContent: 'space-between' },
  bar: { width: 28, borderRadius: 8 },
  progressItem: { marginBottom: 12 },
  track: { height: 6, borderRadius: 3, backgroundColor: 'rgba(255,255,255,0.08)', overflow: 'hidden', marginTop: 6 },
  fillBar: { height: 6, borderRadius: 3 },
});
