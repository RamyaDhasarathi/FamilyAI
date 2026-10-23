// Every tappable: scale 0.96 + opacity 0.85 on press, light haptic (AGENT.md §6.5).
// The Pressable itself is the animated, styled element, so layout styles
// (flex, width, margins) behave exactly as on a plain View.
import type { ReactNode } from 'react';
import { Pressable, type PressableProps, type StyleProp, type ViewStyle } from 'react-native';
import * as Haptics from 'expo-haptics';
import Animated, { useAnimatedStyle, useSharedValue, withSpring } from 'react-native-reanimated';
import { press, springs } from '../theme/motion';

const AnimatedPressable = Animated.createAnimatedComponent(Pressable);

interface Props extends Omit<PressableProps, 'style' | 'children'> {
  style?: StyleProp<ViewStyle>;
  children?: ReactNode;
  /** No haptic (e.g. rapid keyboard-like taps). */
  silent?: boolean;
  /** Scale on press; defaults to the motion token. */
  pressScale?: number;
}

export function Pressy({ style, children, silent, pressScale = press.scale, onPressIn, onPressOut, onPress, ...rest }: Props) {
  const p = useSharedValue(0);
  const anim = useAnimatedStyle(() => ({
    transform: [{ scale: 1 - (1 - pressScale) * p.value }],
    opacity: 1 - (1 - press.opacity) * p.value,
  }));
  return (
    <AnimatedPressable
      accessibilityRole="button"
      hitSlop={6}
      style={[style, anim]}
      onPressIn={(e) => {
        p.value = withSpring(1, springs.snappy);
        onPressIn?.(e);
      }}
      onPressOut={(e) => {
        p.value = withSpring(0, springs.snappy);
        onPressOut?.(e);
      }}
      onPress={(e) => {
        if (!silent) void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
        onPress?.(e);
      }}
      {...rest}
    >
      {children}
    </AnimatedPressable>
  );
}
