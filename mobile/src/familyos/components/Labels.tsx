// Small typographic pieces: section labels, the status line (● CALM),
// card meta rows, and the count badge.
import { StyleSheet, View, type StyleProp, type TextStyle, type ViewStyle } from 'react-native';
import { sizes } from '../theme/tokens';
import { type as T } from '../theme/typography';
import { AppText } from './AppText';

export function SectionLabel({ children, style }: { children: string; style?: StyleProp<TextStyle> }) {
  return (
    <AppText style={[T.section, styles.section, style]} accessibilityRole="header">
      {children}
    </AppText>
  );
}

export function Dot({ color, size = 6, style }: { color: string; size?: number; style?: StyleProp<ViewStyle> }) {
  return <View style={[{ width: size, height: size, borderRadius: size / 2, backgroundColor: color }, style]} />;
}

export function StatusLine({ label, color, style }: { label: string; color: string; style?: StyleProp<ViewStyle> }) {
  return (
    <View style={[styles.statusRow, style]} accessibilityLabel={`Status: ${label}`}>
      <Dot color={color} size={5} style={styles.statusDot} />
      <AppText style={T.status}>{label}</AppText>
    </View>
  );
}

export function MetaRow({ left, right }: { left: string; right?: string }) {
  return (
    <View style={styles.metaRow}>
      <AppText style={T.meta}>{left}</AppText>
      {right ? <AppText style={T.meta}>{right}</AppText> : null}
    </View>
  );
}

export function Badge({ count, color, style }: { count: number; color: string; style?: StyleProp<ViewStyle> }) {
  return (
    <View style={[styles.badge, { backgroundColor: color }, style]}>
      <AppText style={T.badge}>{count}</AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  section: { marginBottom: 10 },
  statusRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center' },
  statusDot: { marginRight: 7 },
  metaRow: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 6 },
  badge: {
    minWidth: sizes.badge,
    height: sizes.badge,
    borderRadius: sizes.badge / 2,
    paddingHorizontal: 4,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
