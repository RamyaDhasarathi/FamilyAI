// Circular summary button (AGENT.md §8.1.5): Listen mode plays the spoken
// walkthrough, Read mode opens the written summary. While playing, the icon
// is a stop square and the ring fills with progress.
import { useEffect } from 'react';
import { StyleSheet, View } from 'react-native';
import Svg, { Circle, Defs, LinearGradient, Stop } from 'react-native-svg';
import Animated, { useAnimatedProps, useSharedValue, withTiming, Easing } from 'react-native-reanimated';
import { FileText, ListPlus, Square } from 'lucide-react-native';
import type { SummaryMode } from '../services/interfaces';
import { colors, sizes } from '../theme/tokens';
import { Pressy } from './Pressy';

const AnimatedCircle = Animated.createAnimatedComponent(Circle);
const S = sizes.askBar;
const R = S / 2 - 1.5;
const CIRC = 2 * Math.PI * R;

interface Props {
  mode: SummaryMode;
  playing: boolean;
  /** 0..1 progress through the walkthrough. */
  progress: number;
  onPress: () => void;
}

export function SummaryButton({ mode, playing, progress, onPress }: Props) {
  const p = useSharedValue(0);
  useEffect(() => {
    p.value = withTiming(playing ? progress : 0, { duration: playing ? 600 : 250, easing: Easing.out(Easing.cubic) });
  }, [playing, progress, p]);
  const ring = useAnimatedProps(() => ({ strokeDashoffset: CIRC * (1 - p.value) }));
  const Icon = playing ? Square : mode === 'listen' ? ListPlus : FileText;
  const label = playing
    ? 'Stop the summary'
    : mode === 'listen'
      ? "Summary, plays today's summary aloud"
      : "Summary, opens today's written summary";
  return (
    <Pressy onPress={onPress} accessibilityLabel={label} style={styles.btn}>
      <Svg width={S} height={S} style={StyleSheet.absoluteFill}>
        <Defs>
          <LinearGradient id="sumRing" x1="0" y1="0" x2="1" y2="1">
            <Stop offset="0" stopColor="#5FF2E0" />
            <Stop offset="0.5" stopColor="#8C7CFF" />
            <Stop offset="1" stopColor="#F07BD0" />
          </LinearGradient>
        </Defs>
        <Circle cx={S / 2} cy={S / 2} r={R} stroke="url(#sumRing)" strokeWidth={1.4} fill="rgba(28,31,40,0.8)" opacity={0.9} />
        <AnimatedCircle
          cx={S / 2}
          cy={S / 2}
          r={R}
          stroke="#FFFFFF"
          strokeWidth={2.2}
          fill="none"
          strokeDasharray={`${CIRC} ${CIRC}`}
          animatedProps={ring}
          strokeLinecap="round"
          transform={`rotate(-90 ${S / 2} ${S / 2})`}
        />
      </Svg>
      <View style={styles.icon}>
        <Icon
          size={playing ? 14 : 20}
          color={colors.inkStrong}
          fill={playing ? colors.inkStrong : 'transparent'}
          strokeWidth={1.8}
        />
      </View>
    </Pressy>
  );
}

const styles = StyleSheet.create({
  btn: { width: S, height: S, borderRadius: S / 2 },
  icon: { ...StyleSheet.absoluteFill, alignItems: 'center', justifyContent: 'center' },
});
