// Today — written summary (AGENT.md §8.2, video 0:18 and 3:45).
import { ScrollView, StyleSheet, View } from 'react-native';
import Animated, { FadeInDown } from 'react-native-reanimated';
import { ChevronRight } from 'lucide-react-native';
import type { AgentId } from '../theme/tokens';
import { colors, radii } from '../theme/tokens';
import { durations } from '../theme/motion';
import { type as T } from '../theme/typography';
import { scenarioThemes } from '../theme/stateThemes';
import { agentNames, copy } from '../mocks/data';
import { useFamilyOS, useMood } from '../store/useFamilyOS';
import { AppText } from '../components/AppText';
import { SectionLabel } from '../components/Labels';
import { ModalCard } from '../components/ModalCard';
import { Pressy } from '../components/Pressy';
import { GlowOrb } from '../graphics/GlowDot';
import { formatLongDate } from './homeText';

interface Props {
  visible: boolean;
  onClose: () => void;
  onOpenAgent: (agent: AgentId) => void;
}

function Tile({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <View style={styles.tile} accessible accessibilityLabel={`${label}: ${value}. ${detail}`}>
      <AppText style={T.meta}>{label}</AppText>
      <AppText style={[T.heroSmall, styles.tileValue]}>{value}</AppText>
      <AppText style={[T.small, styles.tileDetail]}>{detail}</AppText>
    </View>
  );
}

export function TodaySheet({ visible, onClose, onOpenAgent }: Props) {
  const today = useFamilyOS((s) => s.today);
  const mood = useMood();
  const header = (
    <View style={styles.header}>
      <AppText style={T.sheetTitle} accessibilityRole="header">
        {copy.todayTitle}
      </AppText>
      <AppText style={T.date}>{formatLongDate(new Date())}</AppText>
    </View>
  );
  return (
    <ModalCard visible={visible} onClose={onClose} header={header} tint={scenarioThemes[mood].sheetTint}>
      {today ? (
        <ScrollView contentContainerStyle={styles.body} showsVerticalScrollIndicator={false}>
          {today.commute ? (
            <>
              <SectionLabel>{today.commute.section}</SectionLabel>
              <View style={styles.commute}>
                <AppText style={T.meta}>{today.commute.label}</AppText>
                <AppText style={[T.heroSmall, styles.commuteTitle]}>{today.commute.title}</AppText>
                <AppText style={T.small}>{today.commute.detail}</AppText>
                <View style={styles.altChip}>
                  <AppText style={[T.chip, { fontSize: 11 }]}>{today.commute.alt}</AppText>
                </View>
              </View>
            </>
          ) : null}
          <View style={styles.tiles}>
            <Tile {...today.weather} />
            <View style={styles.tileGap} />
            <Tile {...today.firstEvent} />
          </View>
          <SectionLabel style={styles.todayLabel}>{copy.todaySection}</SectionLabel>
          {today.items.map((it, i) => (
            <Animated.View key={it.id} entering={visible ? FadeInDown.delay(120 + i * durations.stagger).duration(320) : undefined}>
              <Pressy
                onPress={() => onOpenAgent(it.agent)}
                pressScale={0.98}
                style={styles.row}
                accessibilityLabel={`${agentNames[it.agent]}: ${it.text}`}
                accessibilityHint={`Opens ${agentNames[it.agent]}`}
              >
                <GlowOrb color={colors.agents[it.agent]} size={30} />
                <View style={styles.rowText}>
                  <AppText style={T.meta}>{agentNames[it.agent].toUpperCase()}</AppText>
                  <AppText style={T.body}>{it.text}</AppText>
                </View>
                <ChevronRight size={16} color={colors.muted} />
              </Pressy>
            </Animated.View>
          ))}
        </ScrollView>
      ) : null}
    </ModalCard>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 20, paddingTop: 20, paddingBottom: 14 },
  body: { paddingHorizontal: 16, paddingBottom: 16 },
  commute: {
    borderRadius: radii.card,
    backgroundColor: colors.cardFill,
    borderWidth: 1,
    borderColor: colors.glassBorder,
    padding: 16,
    marginBottom: 10,
  },
  commuteTitle: { marginTop: 8, marginBottom: 4 },
  altChip: {
    alignSelf: 'flex-start',
    marginTop: 10,
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 999,
    backgroundColor: colors.pillSecondaryBg,
  },
  tiles: { flexDirection: 'row', marginBottom: 6 },
  tileGap: { width: 10 },
  tile: {
    flex: 1,
    borderRadius: radii.card,
    backgroundColor: colors.cardFill,
    borderWidth: 1,
    borderColor: colors.glassBorder,
    padding: 14,
  },
  tileValue: { marginTop: 8, marginBottom: 6, fontSize: 24, lineHeight: 30 },
  tileDetail: { fontSize: 12, lineHeight: 16 },
  todayLabel: { marginTop: 14 },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: radii.card,
    backgroundColor: colors.cardFill,
    borderWidth: 1,
    borderColor: colors.glassBorder,
    paddingVertical: 12,
    paddingHorizontal: 12,
    marginBottom: 8,
  },
  rowText: { flex: 1, marginLeft: 12, marginRight: 8 },
});
