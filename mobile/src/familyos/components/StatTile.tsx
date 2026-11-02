// Stat tile: 2 px top border in the agent colour fading out to the sides,
// label, and a number that counts up on mount (AGENT.md §6.4, §7.6).
import { StyleSheet, View } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import type { StatTile as Stat } from '../services/interfaces';
import { useCountUp } from '../graphics/Charts';
import { colors, radii, withAlpha } from '../theme/tokens';
import { type as T } from '../theme/typography';
import { AppText } from './AppText';

function format(s: Stat, v: number) {
  if (s.text) return s.text;
  const n = s.decimals ? v.toFixed(s.decimals) : Math.round(v).toLocaleString('en-US');
  return `${s.prefix ?? ''}${n}${s.suffix ?? ''}`;
}

export function StatTile({ stat, color }: { stat: Stat; color: string }) {
  const v = useCountUp(stat.value);
  return (
    <View style={styles.tile} accessible accessibilityLabel={`${stat.label}: ${format(stat, stat.value)}`}>
      <LinearGradient
        colors={[withAlpha(color, 0), color, withAlpha(color, 0)]}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 0 }}
        style={styles.topBorder}
      />
      <AppText style={T.statLabel}>{stat.label}</AppText>
      <AppText style={[T.stat, styles.value]}>{format(stat, v)}</AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  tile: {
    flex: 1,
    borderRadius: radii.tile,
    backgroundColor: colors.cardFill,
    borderWidth: 1,
    borderColor: colors.glassBorder,
    paddingHorizontal: 12,
    paddingTop: 14,
    paddingBottom: 12,
    overflow: 'hidden',
  },
  topBorder: { position: 'absolute', top: 0, left: 8, right: 8, height: 2 },
  value: { marginTop: 6 },
});
