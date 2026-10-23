// Dashboard — "Your agents" (AGENT.md §8.3, video 3:12–3:20 and 5:08).
// Driven by scene.dashT, the same value that shrinks the gem into the mini
// gem above the sheet, so the two move as one.
import { ScrollView, StyleSheet, View, useWindowDimensions } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import Animated, { FadeOut, LinearTransition, useAnimatedStyle, withSpring } from 'react-native-reanimated';
import { scheduleOnRN } from 'react-native-worklets';
import { ChevronRight } from 'lucide-react-native';
import type { AgentId } from '../theme/tokens';
import { colors, radii } from '../theme/tokens';
import { springs } from '../theme/motion';
import { scenarioThemes } from '../theme/stateThemes';
import { type as T } from '../theme/typography';
import { agentNames, copy } from '../mocks/data';
import { summaryCount } from '../mocks/scenarios';
import { useFamilyOS, useMood } from '../store/useFamilyOS';
import type { OrbitScene } from '../graphics/sceneState';
import { AppText } from '../components/AppText';
import { AskBar } from '../components/AskBar';
import { Glass } from '../components/Glass';
import { Badge, Dot, SectionLabel } from '../components/Labels';
import { Pressy } from '../components/Pressy';
import { SwipeCard } from '../components/SwipeCard';
import { formatLongDate, greetingFor } from './homeText';
import { agentBadges } from './homeLogic';

export const DASH_TOP_FRAC = 0.22;

interface Props {
  scene: OrbitScene;
  open: boolean;
  onSettle: (open: boolean) => void;
  onOpenAgent: (agent: AgentId) => void;
  onOpenSummary: () => void;
  onAsk: () => void;
  onMic: () => void;
  listening: boolean;
}

function AgentCardView({ agent, status, badge, wide, onPress }: { agent: AgentId; status: string; badge?: { n: number; color: string }; wide?: boolean; onPress: () => void }) {
  return (
    <Pressy
      onPress={onPress}
      pressScale={0.97}
      style={[styles.card, wide && styles.cardWide]}
      accessibilityLabel={`${agentNames[agent]}: ${status}${badge ? `, ${badge.n} need you` : ''}`}
    >
      <View style={styles.cardHead}>
        <Dot color={colors.agents[agent]} size={7} />
        <AppText style={[T.bodyStrong, styles.cardTitle]}>{agentNames[agent]}</AppText>
        {badge ? <Badge count={badge.n} color={badge.color} /> : null}
      </View>
      <AppText style={[T.small, styles.cardStatus]} numberOfLines={2}>
        {status}
      </AppText>
    </Pressy>
  );
}

export function DashboardSheet({ scene, open, onSettle, onOpenAgent, onOpenSummary, onAsk, onMic, listening }: Props) {
  const { height } = useWindowDimensions();
  const insets = useSafeAreaInsets();
  const profile = useFamilyOS((s) => s.profile);
  const cards = useFamilyOS((s) => s.dashboard);
  const needs = useFamilyOS((s) => s.needs);
  const resolve = useFamilyOS((s) => s.resolve);
  const snooze = useFamilyOS((s) => s.snooze);
  const mood = useMood();
  const top = height * DASH_TOP_FRAC;
  const travel = height - top;
  const badges = agentBadges(needs);
  const { n, word } = summaryCount(needs);

  const pan = Gesture.Pan()
    .activeOffsetY(10)
    .onUpdate((e) => {
      scene.dashT.value = Math.min(1, Math.max(0, 1 - e.translationY / travel));
    })
    .onEnd((e) => {
      const close = scene.dashT.value < 0.7 || e.velocityY > 700;
      scene.dashT.value = withSpring(close ? 0 : 1, springs.soft);
      scheduleOnRN(onSettle, !close);
    });

  const sheet = useAnimatedStyle(() => ({
    transform: [{ translateY: (1 - Math.min(1, scene.dashT.value)) * travel }],
    opacity: Math.min(1, scene.dashT.value * 4),
  }));

  if (!profile) return null;
  const grid = cards.filter((c) => c.agent !== 'grocery');
  const grocery = cards.find((c) => c.agent === 'grocery');
  const summary = mood === 'calm' ? copy.summaryCardCalm : copy.summaryCardBusy(n, word);
  return (
    <Animated.View style={[styles.sheet, { top, height: travel }, sheet]} pointerEvents={open ? 'auto' : 'none'}>
      <Glass radius={radii.sheet} fill="rgba(30,34,44,0.82)" tint={scenarioThemes[mood].sheetTint} style={styles.glass}>
        <GestureDetector gesture={pan}>
          <View style={styles.grab}>
            <View style={styles.handle} />
            <AppText style={T.date}>{formatLongDate(new Date())}</AppText>
            <AppText style={[T.greeting, styles.greeting]}>{greetingFor(new Date(), profile.name)}</AppText>
          </View>
        </GestureDetector>
        <ScrollView contentContainerStyle={[styles.body, { paddingBottom: 90 + insets.bottom }]} showsVerticalScrollIndicator={false}>
          <SectionLabel>{copy.yourAgents}</SectionLabel>
          <View style={styles.grid}>
            {grid.map((c) => (
              <AgentCardView key={c.agent} agent={c.agent} status={c.status} badge={badges[c.agent]} onPress={() => onOpenAgent(c.agent)} />
            ))}
            {grocery ? (
              <AgentCardView agent="grocery" status={grocery.status} badge={badges.grocery} wide onPress={() => onOpenAgent('grocery')} />
            ) : null}
          </View>
          <Pressy onPress={onOpenSummary} pressScale={0.98} style={styles.summary} accessibilityLabel={`${copy.todaysSummary}. ${summary}`}>
            <View style={styles.summaryText}>
              <AppText style={[T.bodyStrong, { fontSize: 17 }]}>{copy.todaysSummary}</AppText>
              <AppText style={[T.small, styles.cardStatus]}>{summary}</AppText>
            </View>
            <ChevronRight size={18} color={colors.muted} />
          </Pressy>
          {mood === 'urgent' ? (
            <View style={styles.needs}>
              <View style={styles.needsHead}>
                <AppText style={T.section}>{copy.needsSection}</AppText>
                <AppText style={T.section}>{copy.needsOpen(needs.length)}</AppText>
              </View>
              {needs.map((it) => (
                <Animated.View key={it.id} layout={LinearTransition.duration(280)} exiting={FadeOut.duration(180)}>
                  <SwipeCard item={it} onDone={resolve} onLater={snooze} />
                </Animated.View>
              ))}
            </View>
          ) : null}
        </ScrollView>
        <View style={[styles.askWrap, { paddingBottom: insets.bottom + 12 }]}>
          <AskBar placeholder={copy.askPlaceholder} icon="message" onPress={onAsk} onMic={onMic} listening={listening} />
        </View>
      </Glass>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  sheet: { position: 'absolute', left: 0, right: 0 },
  glass: { flex: 1, borderBottomLeftRadius: 0, borderBottomRightRadius: 0, borderBottomWidth: 0 },
  grab: { paddingHorizontal: 20, paddingTop: 10, paddingBottom: 8 },
  handle: { alignSelf: 'center', width: 40, height: 4, borderRadius: 2, backgroundColor: 'rgba(255,255,255,0.28)', marginBottom: 14 },
  greeting: { marginTop: 4, fontSize: 24 },
  body: { paddingHorizontal: 16, paddingTop: 10 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between' },
  card: {
    width: '48.5%',
    borderRadius: radii.card,
    backgroundColor: colors.cardFill,
    borderWidth: 1,
    borderColor: colors.glassBorder,
    paddingHorizontal: 14,
    paddingVertical: 14,
    marginBottom: 10,
    minHeight: 92,
  },
  cardWide: { width: '100%', minHeight: 0 },
  cardHead: { flexDirection: 'row', alignItems: 'center' },
  cardTitle: { marginLeft: 8, flex: 1 },
  cardStatus: { marginTop: 6, fontSize: 12.5 },
  summary: {
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: radii.card,
    backgroundColor: colors.cardFill,
    borderWidth: 1,
    borderColor: colors.glassBorder,
    paddingHorizontal: 16,
    paddingVertical: 16,
    marginTop: 4,
  },
  summaryText: { flex: 1 },
  needs: { marginTop: 18 },
  needsHead: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 10 },
  askWrap: { position: 'absolute', left: 14, right: 14, bottom: 0, paddingTop: 10 },
});
