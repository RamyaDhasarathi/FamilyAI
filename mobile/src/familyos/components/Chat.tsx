// Chat pieces (AGENT.md §8.6): bubbles, typing indicator, suggestion chips.
import { useEffect } from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';
import Animated, {
  FadeInDown,
  useAnimatedStyle,
  useSharedValue,
  withDelay,
  withRepeat,
  withSequence,
  withTiming,
} from 'react-native-reanimated';
import type { ChatMessage } from '../services/interfaces';
import { colors, radii } from '../theme/tokens';
import { type as T } from '../theme/typography';
import { AppText } from './AppText';
import { Pressy } from './Pressy';

export function ChatBubble({ msg }: { msg: ChatMessage }) {
  const mine = msg.role === 'user';
  return (
    <Animated.View
      entering={FadeInDown.duration(260)}
      style={[styles.bubble, mine ? styles.mine : styles.theirs]}
      accessibilityLabel={`${mine ? 'You' : 'FamilyOS'}: ${msg.text}`}
    >
      <AppText style={[T.small, { color: mine ? colors.pillPrimaryInk : colors.ink, fontSize: 14, lineHeight: 19 }]}>
        {msg.text}
      </AppText>
    </Animated.View>
  );
}

function Dot({ i }: { i: number }) {
  const v = useSharedValue(0.3);
  useEffect(() => {
    v.value = withDelay(
      i * 150,
      withRepeat(withSequence(withTiming(1, { duration: 300 }), withTiming(0.3, { duration: 300 })), -1, false)
    );
  }, [i, v]);
  const st = useAnimatedStyle(() => ({ opacity: v.value, transform: [{ translateY: -2 * v.value }] }));
  return <Animated.View style={[styles.dot, st]} />;
}

export function TypingDots() {
  return (
    <Animated.View entering={FadeInDown.duration(200)} style={[styles.bubble, styles.theirs, styles.typing]} accessibilityLabel="FamilyOS is typing">
      <Dot i={0} />
      <Dot i={1} />
      <Dot i={2} />
    </Animated.View>
  );
}

export function SuggestionChips({ chips, onPick }: { chips: string[]; onPick: (c: string) => void }) {
  if (!chips.length) return null;
  return (
    <ScrollView
      horizontal
      style={styles.chipsBar}
      showsHorizontalScrollIndicator={false}
      contentContainerStyle={styles.chips}
      keyboardShouldPersistTaps="handled"
    >
      {chips.map((c) => (
        <Pressy key={c} onPress={() => onPick(c)} style={styles.chip} accessibilityLabel={`Ask: ${c}`}>
          <AppText style={[T.chip, { fontSize: 12 }]}>{c}</AppText>
        </Pressy>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  bubble: { maxWidth: '82%', borderRadius: radii.bubble, paddingHorizontal: 14, paddingVertical: 10, marginBottom: 10 },
  theirs: { alignSelf: 'flex-start', backgroundColor: 'rgba(255,255,255,0.07)', borderWidth: 1, borderColor: colors.glassBorder },
  mine: { alignSelf: 'flex-end', backgroundColor: colors.pillPrimaryBg },
  typing: { flexDirection: 'row', paddingVertical: 14 },
  dot: { width: 6, height: 6, borderRadius: 3, backgroundColor: colors.muted, marginHorizontal: 2 },
  chipsBar: { flexGrow: 0, flexShrink: 0 },
  chips: { paddingHorizontal: 14, paddingVertical: 8 },
  chip: {
    height: 32,
    paddingHorizontal: 14,
    borderRadius: 999,
    justifyContent: 'center',
    backgroundColor: colors.pillSecondaryBg,
    borderWidth: 1,
    borderColor: colors.glassBorder,
    marginRight: 8,
  },
});
