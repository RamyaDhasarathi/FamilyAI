// Pill buttons: white primary ("Move call to 3:30"), glass secondary
// ("Later", "Close", "Ask about this") and the floating Close pill.
import { StyleSheet, type StyleProp, type ViewStyle } from 'react-native';
import { colors, sizes } from '../theme/tokens';
import { type as T } from '../theme/typography';
import { AppText } from './AppText';
import { Pressy } from './Pressy';

interface PillProps {
  label: string;
  onPress?: () => void;
  variant?: 'primary' | 'secondary';
  style?: StyleProp<ViewStyle>;
  accessibilityLabel?: string;
  tint?: string;
}

export function PillButton({ label, onPress, variant = 'secondary', style, accessibilityLabel, tint }: PillProps) {
  const primary = variant === 'primary';
  return (
    <Pressy
      onPress={onPress}
      accessibilityLabel={accessibilityLabel ?? label}
      style={[
        styles.pill,
        primary ? styles.primary : styles.secondary,
        tint ? { backgroundColor: tint } : null,
        style,
      ]}
    >
      <AppText style={[T.pill, { color: primary ? colors.pillPrimaryInk : colors.ink }]}>{label}</AppText>
    </Pressy>
  );
}

export function ClosePill({ onPress, label = 'Close', style }: { onPress: () => void; label?: string; style?: StyleProp<ViewStyle> }) {
  return (
    <Pressy onPress={onPress} accessibilityLabel={label} style={[styles.pill, styles.close, style]}>
      <AppText style={[T.pill, { color: colors.ink }]}>{label}</AppText>
    </Pressy>
  );
}

const styles = StyleSheet.create({
  pill: {
    height: sizes.pillSmall,
    paddingHorizontal: 16,
    borderRadius: 999,
    alignItems: 'center',
    justifyContent: 'center',
    alignSelf: 'flex-start',
  },
  primary: { backgroundColor: colors.pillPrimaryBg },
  secondary: { backgroundColor: colors.pillSecondaryBg, borderWidth: 1, borderColor: colors.glassBorder },
  close: {
    backgroundColor: 'rgba(40,43,52,0.85)',
    borderWidth: 1,
    borderColor: colors.glassBorder,
    alignSelf: 'center',
  },
});
