// Long-press a satellite: a circle in the agent's colour expands from the
// satellite to cover the screen, then the agent screen fades in over it
// (AGENT.md §7.3, §9 "agent screen expands from its position").
import { useEffect } from 'react';
import { StyleSheet, useWindowDimensions } from 'react-native';
import Animated, { Easing, useAnimatedStyle, useSharedValue, withTiming } from 'react-native-reanimated';
import { scheduleOnRN } from 'react-native-worklets';
import type { AgentId } from '../theme/tokens';
import { colors, withAlpha } from '../theme/tokens';

export interface Reveal {
  agent: AgentId;
  x: number;
  y: number;
}

export function AgentReveal({ reveal, onCovered, onDone }: { reveal: Reveal; onCovered: () => void; onDone: () => void }) {
  const { width, height } = useWindowDimensions();
  const { x, y, agent } = reveal;
  const R = Math.hypot(Math.max(x, width - x), Math.max(y, height - y));
  const p = useSharedValue(0);
  useEffect(() => {
    p.value = withTiming(1, { duration: 380, easing: Easing.out(Easing.cubic) }, (f) => {
      if (f) scheduleOnRN(onCovered);
    });
    const id = setTimeout(onDone, 1100);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const st = useAnimatedStyle(() => ({ transform: [{ scale: 0.04 + 0.96 * p.value }], opacity: Math.min(1, p.value * 3) }));
  return (
    <Animated.View
      pointerEvents="none"
      style={[
        styles.circle,
        { left: x - R, top: y - R, width: R * 2, height: R * 2, borderRadius: R, backgroundColor: withAlpha(colors.agents[agent], 0.16) },
        st,
      ]}
    >
      <Animated.View style={[StyleSheet.absoluteFill, { borderRadius: R, backgroundColor: 'rgba(0,0,0,0.82)' }]} />
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  circle: { position: 'absolute' },
});
