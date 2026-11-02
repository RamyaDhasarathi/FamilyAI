// Small family pieces (AGENT_CORE_AND_FAMILY.md §4.4, §4.6): the member avatar
// (stage image or photo in a glass ring with a halo in the stage colour), a
// completion ring, "needs update" tags and section status pills.
import { useEffect } from 'react';
import { StyleSheet, View, type StyleProp, type ViewStyle } from 'react-native';
import { Image } from 'expo-image';
import Svg, { Circle, Defs, RadialGradient, Stop } from 'react-native-svg';
import Animated, { useAnimatedProps, useSharedValue, withDelay, withTiming, Easing } from 'react-native-reanimated';
import type { FamilyMember, SectionStatus } from '../../services/interfaces';
import { stageOf } from '../../family/model';
import { colors, withAlpha } from '../../theme/tokens';
import { type as T } from '../../theme/typography';
import { AppText } from '../AppText';

const AnimatedCircle = Animated.createAnimatedComponent(Circle);
export const AMBER = '#FFB23F';
export const GREEN = '#4DD98C';

/** Stage image (GIF when `animated`), or the member's photo, in a glass ring with a stage-coloured halo. */
export function MemberAvatar({ member, size, animated, style }: { member: FamilyMember; size: number; animated?: boolean; style?: StyleProp<ViewStyle> }) {
  const st = stageOf(member);
  const halo = size * 1.5;
  const src = member.photoUri ? { uri: member.photoUri } : animated ? st.gif : st.png;
  return (
    <View style={[{ width: size, height: size }, style]}>
      <Svg width={halo} height={halo} style={{ position: 'absolute', left: (size - halo) / 2, top: (size - halo) / 2 }} pointerEvents="none">
        <Defs>
          <RadialGradient id={`h${member.id}`} cx="50%" cy="50%" r="50%">
            <Stop offset="0.55" stopColor={st.accent} stopOpacity={0.35} />
            <Stop offset="1" stopColor={st.accent} stopOpacity={0} />
          </RadialGradient>
        </Defs>
        <Circle cx={halo / 2} cy={halo / 2} r={halo / 2} fill={`url(#h${member.id})`} />
      </Svg>
      <View style={[styles.ring, { width: size, height: size, borderRadius: size / 2, borderColor: withAlpha(st.accent, 0.55) }]}>
        <Image
          source={src}
          style={{ width: size - 4, height: size - 4, borderRadius: (size - 4) / 2 }}
          contentFit="cover"
          accessibilityIgnoresInvertColors
          accessible={false}
        />
      </View>
    </View>
  );
}

/** Completion ring (SVG; a sweep animates in on mount). */
export function CompletionRing({ value, size, stroke = 3, color, delay = 0 }: { value: number; size: number; stroke?: number; color: string; delay?: number }) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const p = useSharedValue(0);
  useEffect(() => {
    p.set(withDelay(delay, withTiming(value, { duration: 700, easing: Easing.out(Easing.cubic) })));
  }, [value, delay, p]);
  const props = useAnimatedProps(() => ({ strokeDashoffset: c * (1 - p.value) }));
  return (
    <Svg width={size} height={size} accessibilityLabel={`${Math.round(value * 100)}% complete`}>
      <Circle cx={size / 2} cy={size / 2} r={r} stroke="rgba(255,255,255,0.1)" strokeWidth={stroke} fill="none" />
      <AnimatedCircle
        cx={size / 2} cy={size / 2} r={r} stroke={color} strokeWidth={stroke} fill="none"
        strokeDasharray={`${c} ${c}`} animatedProps={props} strokeLinecap="round"
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
      />
    </Svg>
  );
}

export function Tag({ text, color }: { text: string; color: string }) {
  return (
    <View style={[styles.tag, { backgroundColor: withAlpha(color, 0.14), borderColor: withAlpha(color, 0.45) }]}>
      <AppText style={[T.chip, styles.tagText, { color }]}>{text}</AppText>
    </View>
  );
}

const STATUS: Record<SectionStatus, { text: string; color: string }> = {
  complete: { text: 'Complete', color: GREEN },
  needsUpdate: { text: 'Needs update', color: AMBER },
  notStarted: { text: 'Not started', color: colors.dim },
};

export function StatusPill({ status }: { status: SectionStatus }) {
  const s = STATUS[status];
  return <Tag text={s.text} color={s.color} />;
}

const styles = StyleSheet.create({
  ring: { borderWidth: 1.5, alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(10,12,18,0.9)', overflow: 'hidden' },
  tag: { height: 22, paddingHorizontal: 9, borderRadius: 11, borderWidth: 1, justifyContent: 'center', marginRight: 6, marginTop: 6 },
  tagText: { fontSize: 10.5 },
});
