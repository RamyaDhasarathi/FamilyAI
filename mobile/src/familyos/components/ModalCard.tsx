// Floating glass modal card used by the Today, Needs-you and Chat sheets
// (AGENT.md §8.2, §8.4, §8.6). Anchored to the bottom and sized to its
// content up to `maxFrac` of the screen; a Close pill floats above it.
// Dismiss: Close, tap outside, swipe down on the header, Android back.
import { useEffect, useState, type ReactNode } from 'react';
import { BackHandler, Pressable, StyleSheet, View, useWindowDimensions, type StyleProp, type ViewStyle } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import Animated, {
  useAnimatedKeyboard,
  useAnimatedStyle,
  useSharedValue,
  withSpring,
  withTiming,
  Easing,
} from 'react-native-reanimated';
import { scheduleOnRN } from 'react-native-worklets';
import { colors, radii } from '../theme/tokens';
import { springs } from '../theme/motion';
import { Glass } from './Glass';
import { ClosePill } from './Pills';

interface Props {
  visible: boolean;
  onClose: () => void;
  /** Rendered above the scrollable body; the swipe-down handle. */
  header?: ReactNode;
  children: ReactNode;
  tint?: [string, string];
  maxFrac?: number;
  /** Close pill floating above the card (Today / Needs-you) or none (Chat has its own). */
  closeAbove?: boolean;
  style?: StyleProp<ViewStyle>;
  /** Fixed height instead of hugging the content (Chat). */
  fixedFrac?: number;
  onClosed?: () => void;
  /** Lift above the keyboard and shrink to fit (Chat). */
  keyboardAware?: boolean;
}

export function ModalCard({
  visible,
  onClose,
  header,
  children,
  tint,
  maxFrac = 0.85,
  closeAbove = true,
  style,
  fixedFrac,
  onClosed,
  keyboardAware,
}: Props) {
  const { height } = useWindowDimensions();
  const insets = useSafeAreaInsets();
  const [mounted, setMounted] = useState(visible);
  const p = useSharedValue(0);
  const drag = useSharedValue(0);
  const kb = useAnimatedKeyboard();

  useEffect(() => {
    if (visible) {
      setMounted(true);
      drag.value = 0;
      p.value = withSpring(1, springs.soft);
    } else if (mounted) {
      const done = () => {
        setMounted(false);
        onClosed?.();
      };
      p.value = withTiming(0, { duration: 220, easing: Easing.in(Easing.cubic) }, (fin) => {
        if (fin) scheduleOnRN(done);
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible]);

  useEffect(() => {
    if (!visible) return;
    const sub = BackHandler.addEventListener('hardwareBackPress', () => {
      onClose();
      return true;
    });
    return () => sub.remove();
  }, [visible, onClose]);

  const pan = Gesture.Pan()
    .activeOffsetY(8)
    .failOffsetX([-20, 20])
    .onUpdate((e) => {
      drag.value = Math.max(0, e.translationY);
    })
    .onEnd((e) => {
      if (e.translationY > 110 || e.velocityY > 900) scheduleOnRN(onClose);
      else drag.value = withSpring(0, springs.snappy);
    });

  const backdrop = useAnimatedStyle(() => ({ opacity: Math.min(1, p.value) }));
  const card = useAnimatedStyle(() => ({
    opacity: Math.min(1, p.value * 1.4),
    transform: [{ translateY: (1 - p.value) * 36 + drag.value }, { scale: 0.94 + 0.06 * Math.min(1, p.value) }],
  }));

  const baseBottom = insets.bottom + 10;
  const maxH = height * maxFrac - insets.bottom;
  const fixedH = fixedFrac ? height * fixedFrac - insets.bottom : undefined;
  const lift = useAnimatedStyle(() => {
    const k = keyboardAware ? kb.height.value : 0;
    const bottom = Math.max(baseBottom, k + 8);
    const room = height - bottom - insets.top - 12;
    return fixedH ? { bottom, height: Math.min(fixedH, room) } : { bottom };
  });

  if (!mounted) return null;
  return (
    <View style={StyleSheet.absoluteFill} pointerEvents={visible ? 'auto' : 'none'}>
      <Animated.View style={[StyleSheet.absoluteFill, styles.scrim, backdrop]}>
        <Pressable style={StyleSheet.absoluteFill} onPress={onClose} accessibilityLabel="Close" accessibilityRole="button" />
      </Animated.View>
      <Animated.View style={[styles.anchor, lift]} pointerEvents="box-none">
        <Animated.View style={[card, style, fixedH ? styles.fill : null]}>
          {closeAbove ? <ClosePill onPress={onClose} style={styles.closeAbove} /> : null}
          <Glass radius={radii.sheet} fill={colors.sheetFill} tint={tint} style={fixedH ? styles.fill : { maxHeight: maxH }}>
            {header ? (
              <GestureDetector gesture={pan}>
                <View>{header}</View>
              </GestureDetector>
            ) : null}
            {children}
          </Glass>
        </Animated.View>
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  scrim: { backgroundColor: colors.scrim },
  anchor: { position: 'absolute', left: 16, right: 16 },
  closeAbove: { marginBottom: 12 },
  fill: { flex: 1 },
});
