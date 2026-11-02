// Hero card of an agent's Deep Layer screen (AGENT.md §8.7): Finance and
// Grocery show a sparkline, Calendar week bars, Education progress bars,
// Household a task ring. The card carries a faint glow in the agent colour.
import { StyleSheet, View, useWindowDimensions } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import type { AgentHero as Hero } from '../services/interfaces';
import { ProgressBars, Sparkline, TaskRing, WeekBars } from '../graphics/Charts';
import { colors, radii, withAlpha } from '../theme/tokens';
import { type as T } from '../theme/typography';
import { AppText } from './AppText';

export function AgentHero({ hero, color }: { hero: Hero; color: string }) {
  const { width } = useWindowDimensions();
  const inner = width - 32 - 32 - 2;
  return (
    <View style={styles.card} accessible accessibilityLabel={`${hero.label}: ${hero.value}`}>
      <LinearGradient
        colors={[withAlpha(color, 0.2), withAlpha(color, 0)]}
        start={{ x: 1, y: 0 }}
        end={{ x: 0.35, y: 0.7 }}
        style={StyleSheet.absoluteFill}
        pointerEvents="none"
      />
      <View style={styles.pad}>
        <View style={styles.row}>
          <View style={styles.flex}>
            <AppText style={[T.small, { fontSize: 12 }]}>{hero.label}</AppText>
            <AppText style={[T.hero, styles.value]}>{hero.value}</AppText>
            <AppText style={[T.smallStrong, { color, fontSize: 12.5 }]}>
              {hero.kind === 'sparkline' ? hero.delta : hero.note}
            </AppText>
          </View>
          {hero.kind === 'ring' ? <TaskRing pct={hero.pct} color={color} /> : null}
        </View>
        {hero.kind === 'sparkline' ? (
          <View style={styles.chart}>
            <Sparkline series={hero.series} color={color} width={inner} height={92} />
          </View>
        ) : null}
        {hero.kind === 'bars' ? (
          <View style={styles.chart}>
            <WeekBars bars={hero.bars} todayIndex={hero.todayIndex} color={color} />
          </View>
        ) : null}
        {hero.kind === 'progress' ? (
          <View style={styles.chart}>
            <ProgressBars
              items={hero.items}
              color={color}
              renderLabel={(name, pct) => (
                <View style={styles.progressLabel}>
                  <AppText style={[T.small, { color: colors.ink, fontSize: 12.5 }]}>{name}</AppText>
                  <AppText style={[T.small, { fontSize: 12.5 }]}>{Math.round(pct * 100)}%</AppText>
                </View>
              )}
            />
          </View>
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: radii.card + 2,
    backgroundColor: 'rgba(255,255,255,0.05)',
    borderWidth: 1,
    borderColor: colors.glassBorder,
    overflow: 'hidden',
  },
  pad: { padding: 16 },
  row: { flexDirection: 'row', alignItems: 'center' },
  flex: { flex: 1 },
  value: { marginTop: 6, marginBottom: 6 },
  chart: { marginTop: 14 },
  progressLabel: { flexDirection: 'row', justifyContent: 'space-between' },
});
