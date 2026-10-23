// Profile menu popover (AGENT.md §8.5, video 0:12 and 1:18). Scales out
// from the avatar pill's corner. "Summary button" toggles Listen / Read in place.
import { useEffect, useState } from 'react';
import { BackHandler, Pressable, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Animated, { useAnimatedStyle, useSharedValue, withSpring, withTiming } from 'react-native-reanimated';
import { scheduleOnRN } from 'react-native-worklets';
import { copy } from '../mocks/data';
import { useFamilyOS } from '../store/useFamilyOS';
import { colors, radii } from '../theme/tokens';
import { springs } from '../theme/motion';
import { type as T } from '../theme/typography';
import { AppText } from '../components/AppText';
import { Glass } from '../components/Glass';
import { ClosePill } from '../components/Pills';
import { Pressy } from '../components/Pressy';

export type MenuTarget = 'Profile' | 'Family' | 'Settings' | 'Login' | { placeholder: string };

interface Props {
  visible: boolean;
  onClose: () => void;
  onNavigate: (t: MenuTarget) => void;
  onLogout: () => void;
}

function Row({ label, onPress, right, danger }: { label: string; onPress: () => void; right?: React.ReactNode; danger?: boolean }) {
  return (
    <Pressy onPress={onPress} pressScale={0.98} style={styles.row} accessibilityLabel={label}>
      <AppText style={[T.menu, danger && { color: colors.danger }]}>{label}</AppText>
      {right}
    </Pressy>
  );
}

export function ProfileMenu({ visible, onClose, onNavigate, onLogout }: Props) {
  const insets = useSafeAreaInsets();
  const profile = useFamilyOS((s) => s.profile);
  const mode = useFamilyOS((s) => s.summaryMode);
  const toggle = useFamilyOS((s) => s.toggleSummaryMode);
  const [mounted, setMounted] = useState(visible);
  const p = useSharedValue(0);
  if (visible && !mounted) setMounted(true);

  useEffect(() => {
    if (visible) {
      p.set(withSpring(1, springs.soft));
    } else if (mounted) {
      p.set(withTiming(0, { duration: 180 }, (f) => {
        if (f) scheduleOnRN(setMounted, false);
      }));
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

  const scrim = useAnimatedStyle(() => ({ opacity: Math.min(1, p.value) }));
  const card = useAnimatedStyle(() => ({
    opacity: Math.min(1, p.value * 1.5),
    transform: [{ scale: 0.6 + 0.4 * p.value }],
  }));

  if (!mounted || !profile) return null;
  const rows: [string, MenuTarget][] = [
    [copy.profileMenu.rows[0], { placeholder: copy.profileMenu.rows[0] }],
    [copy.profileMenu.rows[1], 'Family'],
    [copy.profileMenu.rows[2], { placeholder: copy.profileMenu.rows[2] }],
    [copy.profileMenu.rows[3], { placeholder: copy.profileMenu.rows[3] }],
    [copy.profileMenu.rows[4], { placeholder: copy.profileMenu.rows[4] }],
  ];
  return (
    <View style={StyleSheet.absoluteFill} pointerEvents={visible ? 'auto' : 'none'}>
      <Animated.View style={[StyleSheet.absoluteFill, styles.scrim, scrim]}>
        <Pressable style={StyleSheet.absoluteFill} onPress={onClose} accessibilityLabel="Close menu" />
      </Animated.View>
      <Animated.View style={[styles.anchor, { top: insets.top + 50 }, card, { transformOrigin: 'top right' }]}>
        <Glass radius={radii.card + 2} fill="rgba(34,37,46,0.92)" style={styles.card}>
          <View style={styles.head}>
            <View style={styles.avatar}>
              <AppText style={[T.smallStrong, { color: colors.inkStrong }]}>{profile.initial}</AppText>
            </View>
            <View style={styles.headText}>
              <AppText style={T.bodyStrong}>{profile.name}</AppText>
              <AppText style={[T.small, { fontSize: 11.5 }]} numberOfLines={1}>
                {profile.plan}
              </AppText>
            </View>
            <ClosePill onPress={onClose} />
          </View>
          {rows.map(([label, target]) => (
            <Row key={label} label={label} onPress={() => onNavigate(target)} />
          ))}
          <Row
            label={copy.profileMenu.summaryButton}
            onPress={toggle}
            right={
              <View style={styles.chip} accessibilityLabel={`Summary button mode: ${copy.summaryModeLabel[mode]}`}>
                <AppText style={[T.chip, { fontSize: 11 }]}>{copy.summaryModeLabel[mode]}</AppText>
              </View>
            }
          />
          <Row label={copy.profileMenu.settings} onPress={() => onNavigate('Settings')} />
          <Row label={copy.profileMenu.help} onPress={() => onNavigate({ placeholder: copy.profileMenu.help })} />
          <View style={styles.divider} />
          <Row label={copy.profileMenu.switchAccount} onPress={() => onNavigate('Login')} />
          <Row label={copy.profileMenu.logout} onPress={onLogout} danger />
        </Glass>
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  scrim: { backgroundColor: colors.scrim },
  anchor: { position: 'absolute', right: 12, width: 284 },
  card: { paddingVertical: 8 },
  head: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 14, paddingTop: 8, paddingBottom: 10 },
  avatar: {
    width: 34,
    height: 34,
    borderRadius: 17,
    backgroundColor: 'rgba(255,255,255,0.12)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  headText: { flex: 1, marginLeft: 10 },
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 18, height: 44 },
  chip: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999, backgroundColor: colors.pillSecondaryBg, borderWidth: 1, borderColor: colors.glassBorder },
  divider: { height: StyleSheet.hairlineWidth, backgroundColor: colors.divider, marginHorizontal: 18, marginVertical: 6 },
});
