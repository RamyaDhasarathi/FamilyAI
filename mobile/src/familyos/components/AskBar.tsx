// "Ask FamilyOS" glass bar with the white mic button (AGENT.md §8.1.5).
// While listening, the mic pulses and a small waveform runs in the bar.
import { useEffect } from 'react';
import { StyleSheet, View, type StyleProp, type ViewStyle } from 'react-native';
import Animated, {
  cancelAnimation,
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withTiming,
  Easing,
} from 'react-native-reanimated';
import { Keyboard, MessageCircle, Mic } from 'lucide-react-native';
import { colors, sizes } from '../theme/tokens';
import { type as T } from '../theme/typography';
import { copy } from '../mocks/data';
import { AppText } from './AppText';
import { Pressy } from './Pressy';

interface Props {
  placeholder: string;
  icon?: 'keyboard' | 'message';
  onPress: () => void;
  onMic?: () => void;
  listening?: boolean;
  style?: StyleProp<ViewStyle>;
}

function WaveBar({ i, active }: { i: number; active: boolean }) {
  const v = useSharedValue(0.3);
  useEffect(() => {
    if (active) {
      v.set(withRepeat(
        withTiming(1, { duration: 260 + i * 70, easing: Easing.inOut(Easing.sin) }),
        -1,
        true
      ));
    } else {
      cancelAnimation(v);
      v.set(withTiming(0.3, { duration: 150 }));
    }
  }, [active, i, v]);
  const st = useAnimatedStyle(() => ({ transform: [{ scaleY: v.value }] }));
  return <Animated.View style={[styles.wave, st]} />;
}

export function AskBar({ placeholder, icon = 'keyboard', onPress, onMic, listening = false, style }: Props) {
  const pulse = useSharedValue(0);
  useEffect(() => {
    if (listening) pulse.set(withRepeat(withTiming(1, { duration: 700 }), -1, true));
    else {
      cancelAnimation(pulse);
      pulse.set(withTiming(0, { duration: 200 }));
    }
  }, [listening, pulse]);
  const micStyle = useAnimatedStyle(() => ({ transform: [{ scale: 1 + 0.08 * pulse.value }] }));
  const ringStyle = useAnimatedStyle(() => ({
    opacity: 0.5 * pulse.value,
    transform: [{ scale: 1 + 0.45 * pulse.value }],
  }));
  const Icon = icon === 'keyboard' ? Keyboard : MessageCircle;
  return (
    <View style={[styles.bar, style]}>
      <Pressy
        style={styles.input}
        onPress={onPress}
        pressScale={0.98}
        accessibilityLabel={placeholder}
        accessibilityHint="Opens the chat"
      >
        <Icon size={18} color={colors.muted} strokeWidth={1.8} />
        {listening ? (
          <View style={styles.waveRow}>
            {[0, 1, 2, 3, 4, 5, 6].map((i) => (
              <WaveBar key={i} i={i} active={listening} />
            ))}
            <AppText style={[T.input, styles.listening]}>{copy.listening}</AppText>
          </View>
        ) : (
          <AppText style={[T.input, styles.placeholder]} numberOfLines={1}>
            {placeholder}
          </AppText>
        )}
      </Pressy>
      {onMic ? (
        <View style={styles.micWrap}>
          <Animated.View style={[styles.micRing, ringStyle]} pointerEvents="none" />
          <Pressy onPress={onMic} accessibilityLabel={listening ? 'Listening' : 'Speak to FamilyOS'}>
            <Animated.View style={[styles.mic, micStyle]}>
              <Mic size={18} color={colors.pillPrimaryInk} strokeWidth={2} />
            </Animated.View>
          </Pressy>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  bar: {
    height: sizes.askBar,
    borderRadius: sizes.askBar / 2,
    backgroundColor: 'rgba(28,31,40,0.78)',
    borderWidth: 1,
    borderColor: colors.glassBorder,
    flexDirection: 'row',
    alignItems: 'center',
    paddingLeft: 18,
    paddingRight: 6,
  },
  input: { flexDirection: 'row', alignItems: 'center', flex: 1, height: sizes.askBar },
  placeholder: { color: colors.muted, marginLeft: 12, flex: 1 },
  listening: { color: colors.ink, marginLeft: 10 },
  waveRow: { flexDirection: 'row', alignItems: 'center', marginLeft: 12, height: 22 },
  wave: { width: 3, height: 18, borderRadius: 2, backgroundColor: colors.ink, marginRight: 3 },
  micWrap: { width: sizes.micButton, height: sizes.micButton, alignItems: 'center', justifyContent: 'center' },
  micRing: {
    position: 'absolute',
    width: sizes.micButton,
    height: sizes.micButton,
    borderRadius: sizes.micButton / 2,
    backgroundColor: 'rgba(255,255,255,0.45)',
  },
  mic: {
    width: sizes.micButton,
    height: sizes.micButton,
    borderRadius: sizes.micButton / 2,
    backgroundColor: colors.pillPrimaryBg,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
