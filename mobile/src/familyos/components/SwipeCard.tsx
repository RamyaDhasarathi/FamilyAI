// Needs-you card (AGENT.md §8.4): swipe right = Done (green), swipe left =
// Later (amber), release past 35 % of the width. Tapping the white pill is
// Done with that action; "Later" snoozes. A small pill confirms, then the
// row collapses (the list's layout animation closes the gap).
import { useState } from 'react';
import { StyleSheet, View, useWindowDimensions } from 'react-native';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import Animated, {
  FadeIn,
  interpolate,
  useAnimatedStyle,
  useSharedValue,
  withSpring,
  withTiming,
  Easing,
} from 'react-native-reanimated';
import { scheduleOnRN } from 'react-native-worklets';
import * as Haptics from 'expo-haptics';
import type { NeedsItem } from '../services/interfaces';
import { agentNames, copy } from '../mocks/data';
import { colors, radii, withAlpha } from '../theme/tokens';
import { springs } from '../theme/motion';
import { type as T } from '../theme/typography';
import { AppText } from './AppText';
import { MetaRow } from './Labels';
import { PillButton } from './Pills';

const SEVERITY_WORD = { urgent: 'URGENT', headsup: 'HEADS-UP', insight: 'INSIGHT' } as const;

interface Props {
  item: NeedsItem;
  onDone: (id: string) => void;
  onLater: (id: string) => void;
  /** Width the card lives in (for the 35 % threshold). */
  width?: number;
}

export function SwipeCard({ item, onDone, onLater, width }: Props) {
  const { width: screenW } = useWindowDimensions();
  const W = width ?? screenW - 64;
  const tx = useSharedValue(0);
  const [result, setResult] = useState<'done' | 'later' | null>(null);
  const sev = colors.severity[item.severity];

  const finish = (kind: 'done' | 'later') => {
    if (kind === 'done') void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    else void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setResult(kind);
    setTimeout(() => (kind === 'done' ? onDone(item.id) : onLater(item.id)), 650);
  };
  const fling = (dir: 1 | -1) => {
    tx.value = withTiming(dir * W * 1.15, { duration: 240, easing: Easing.out(Easing.cubic) }, () =>
      scheduleOnRN(finish, dir === 1 ? 'done' : 'later')
    );
  };

  const pan = Gesture.Pan()
    .activeOffsetX([-12, 12])
    .failOffsetY([-14, 14])
    .onUpdate((e) => {
      tx.value = e.translationX;
    })
    .onEnd((e) => {
      const projected = e.translationX + e.velocityX * 0.08;
      if (projected > W * 0.35) {
        tx.value = withTiming(W * 1.15, { duration: 200 }, () => scheduleOnRN(finish, 'done'));
      } else if (projected < -W * 0.35) {
        tx.value = withTiming(-W * 1.15, { duration: 200 }, () => scheduleOnRN(finish, 'later'));
      } else {
        tx.value = withSpring(0, springs.snappy);
      }
    });

  const cardStyle = useAnimatedStyle(() => ({ transform: [{ translateX: tx.value }] }));
  const greenTint = useAnimatedStyle(() => ({ opacity: interpolate(tx.value, [0, W * 0.4], [0, 0.55], 'clamp') }));
  const amberTint = useAnimatedStyle(() => ({ opacity: interpolate(tx.value, [-W * 0.4, 0], [0.55, 0], 'clamp') }));
  const doneBg = useAnimatedStyle(() => ({ opacity: tx.value > 2 ? 1 : 0 }));
  const laterBg = useAnimatedStyle(() => ({ opacity: tx.value < -2 ? 1 : 0 }));

  if (result) {
    return (
      <Animated.View entering={FadeIn.duration(150)} style={styles.resultRow}>
        <View style={styles.resultPill}>
          <AppText style={[T.smallStrong, { color: colors.ink, fontSize: 12 }]}>
            {result === 'done' ? copy.done : copy.snoozed}
          </AppText>
        </View>
      </Animated.View>
    );
  }

  const label = `${agentNames[item.agent].toUpperCase()} · ${SEVERITY_WORD[item.severity]}`;
  return (
    <View style={styles.wrap}>
      <Animated.View style={[styles.reveal, styles.doneReveal, doneBg]}>
        <AppText style={[T.meta, styles.revealText]}>{copy.doneSwipe}</AppText>
      </Animated.View>
      <Animated.View style={[styles.reveal, styles.laterReveal, laterBg]}>
        <AppText style={[T.meta, styles.revealText]}>{copy.laterSwipe}</AppText>
      </Animated.View>
      <GestureDetector gesture={pan}>
        <Animated.View
          style={[styles.card, cardStyle]}
          accessible
          accessibilityLabel={`${label}. ${item.text}`}
          accessibilityActions={[
            { name: 'activate', label: item.action.label },
            { name: 'magicTap', label: copy.later },
          ]}
          onAccessibilityAction={(e) => fling(e.nativeEvent.actionName === 'activate' ? 1 : -1)}
        >
          <Animated.View style={[StyleSheet.absoluteFill, styles.tint, { backgroundColor: colors.done }, greenTint]} />
          <Animated.View style={[StyleSheet.absoluteFill, styles.tint, { backgroundColor: colors.later }, amberTint]} />
          <View style={[styles.accent, { backgroundColor: sev, shadowColor: sev }]} />
          <View style={styles.body}>
            <MetaRow left={label} right={item.time} />
            <AppText style={[T.body, styles.text]}>{item.text}</AppText>
            <View style={styles.actions}>
              <PillButton label={item.action.label} variant="primary" onPress={() => fling(1)} />
              <PillButton label={copy.later} onPress={() => fling(-1)} style={styles.later} />
            </View>
          </View>
        </Animated.View>
      </GestureDetector>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { marginBottom: 10 },
  reveal: {
    ...StyleSheet.absoluteFill,
    borderRadius: radii.card,
    justifyContent: 'center',
    paddingHorizontal: 18,
  },
  doneReveal: { backgroundColor: withAlpha('#3FCB7E', 0.28), alignItems: 'flex-start' },
  laterReveal: { backgroundColor: withAlpha('#E9A23B', 0.28), alignItems: 'flex-end' },
  revealText: { color: colors.inkStrong, fontSize: 11 },
  card: {
    borderRadius: radii.card,
    backgroundColor: 'rgba(52,56,68,0.62)',
    borderWidth: 1,
    borderColor: colors.glassBorder,
    flexDirection: 'row',
    overflow: 'hidden',
  },
  tint: { borderRadius: radii.card },
  accent: { width: 3, marginVertical: 14, marginLeft: 12, borderRadius: 2, shadowOpacity: 0.8, shadowRadius: 6 },
  body: { flex: 1, paddingVertical: 14, paddingLeft: 12, paddingRight: 14 },
  text: { marginBottom: 12 },
  actions: { flexDirection: 'row' },
  later: { marginLeft: 8 },
  resultRow: { height: 64, alignItems: 'center', justifyContent: 'center', marginBottom: 10 },
  resultPill: {
    paddingHorizontal: 14,
    paddingVertical: 7,
    borderRadius: 999,
    backgroundColor: 'rgba(30,33,42,0.94)',
    borderWidth: 1,
    borderColor: colors.glassBorder,
  },
});
