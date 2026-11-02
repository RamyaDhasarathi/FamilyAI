// Agent Deep Layer screen (AGENT.md §8.7, video 3:20 Finance, 4:06 Calendar, 4:34 Grocery).
import { useEffect, useRef, useState } from 'react';
import { ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Animated, { FadeInDown, FadeInRight } from 'react-native-reanimated';
import { LinearGradient } from 'expo-linear-gradient';
import { ChevronLeft } from 'lucide-react-native';
import type { AgentDetail } from '../services/interfaces';
import { colors, radii, withAlpha } from '../theme/tokens';
import { durations } from '../theme/motion';
import { type as T } from '../theme/typography';
import { agentNames, copy } from '../mocks/data';
import { service } from '../mocks/services';
import { useFamilyOS } from '../store/useFamilyOS';
import type { ScreenProps } from '../navigation/types';
import { MiniGem } from '../graphics/MiniGem';
import { AgentHero } from '../components/AgentHero';
import { AppText } from '../components/AppText';
import { AskBar } from '../components/AskBar';
import { SectionLabel } from '../components/Labels';
import { Pressy } from '../components/Pressy';
import { StatTile } from '../components/StatTile';
import { TimelineItem } from '../components/TimelineItem';
import { ToastHost } from '../components/Toast';
import { ChatSheet } from './ChatSheet';

export function AgentDetailScreen({ route, navigation }: ScreenProps<'Agent'>) {
  const { agent } = route.params;
  const insets = useSafeAreaInsets();
  const color = colors.agents[agent];
  const [detail, setDetail] = useState<AgentDetail | null>(null);
  const [chatOpen, setChatOpen] = useState(false);
  const [listening, setListening] = useState(false);
  const undone = useFamilyOS((s) => s.undone);
  const undo = useFamilyOS((s) => s.undo);
  const queueChat = useFamilyOS((s) => s.queueChat);
  const listenTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let live = true;
    void service.getAgentDetail(agent).then((d) => live && setDetail(d));
    return () => {
      live = false;
      if (listenTimer.current) clearTimeout(listenTimer.current);
    };
  }, [agent]);

  const openChat = (pending?: string) => {
    queueChat(agent, pending);
    setChatOpen(true);
  };
  const onMic = () => {
    if (listenTimer.current) return;
    setListening(true);
    listenTimer.current = setTimeout(() => {
      listenTimer.current = null;
      setListening(false);
      openChat(detail?.chips[0]);
    }, durations.listen);
  };

  const name = agentNames[agent];
  return (
    <View style={styles.root}>
      <View style={[styles.top, { height: insets.top + 64 }]}>
        <View style={[styles.gem, { top: insets.top - 6 }]} pointerEvents="none">
          <MiniGem size={72} agentColor={color} />
        </View>
        <Pressy onPress={() => navigation.goBack()} style={[styles.back, { top: insets.top + 8 }]} accessibilityLabel="Back">
          <ChevronLeft size={20} color={colors.ink} />
        </Pressy>
      </View>
      <Animated.View entering={FadeInRight.duration(320)} style={[styles.panelWrap, { marginTop: insets.top + 66 }]}>
        <LinearGradient colors={['rgba(255,255,255,0.06)', 'rgba(255,255,255,0.02)']} style={styles.panel}>
          <ScrollView contentContainerStyle={[styles.body, { paddingBottom: insets.bottom + 96 }]} showsVerticalScrollIndicator={false}>
            <AppText style={T.agentTitle} accessibilityRole="header">
              {detail?.title ?? name}
            </AppText>
            <LinearGradient colors={[color, withAlpha(color, 0)]} start={{ x: 0, y: 0 }} end={{ x: 1, y: 0 }} style={styles.underline} />
            {detail ? (
              <>
                <AppText style={[T.small, styles.subtitle]}>{detail.subtitle}</AppText>
                <Animated.View entering={FadeInDown.delay(80).duration(360)}>
                  <AgentHero hero={detail.hero} color={color} />
                </Animated.View>
                <Animated.View entering={FadeInDown.delay(160).duration(360)} style={styles.stats}>
                  {detail.stats.map((s, i) => (
                    <View key={s.label} style={[styles.statCell, i > 0 && styles.statGap]}>
                      <StatTile stat={s} color={color} />
                    </View>
                  ))}
                </Animated.View>
                <SectionLabel style={styles.section}>{copy.whatIDid}</SectionLabel>
                {detail.timeline.map((e, i) => (
                  <Animated.View key={e.id} entering={FadeInDown.delay(220 + i * durations.stagger).duration(320)}>
                    <TimelineItem
                      entry={e}
                      color={color}
                      undone={!!undone[e.id]}
                      onUndo={() => undo(e.id)}
                      onAsk={() => openChat(copy.tellMeMore(e.title))}
                      last={i === detail.timeline.length - 1}
                    />
                  </Animated.View>
                ))}
              </>
            ) : null}
          </ScrollView>
        </LinearGradient>
      </Animated.View>
      <LinearGradient
        colors={['rgba(0,0,0,0)', 'rgba(0,0,0,0.92)']}
        locations={[0, 0.5]}
        style={[styles.askFade, { height: insets.bottom + 100 }]}
        pointerEvents="none"
      />
      <View style={[styles.ask, { bottom: insets.bottom + 12 }]}>
        <AskBar placeholder={copy.askAgent(name)} icon="message" onPress={() => openChat()} onMic={onMic} listening={listening} />
      </View>
      <ToastHost bottom={insets.bottom + 80} />
      <ChatSheet visible={chatOpen} onClose={() => setChatOpen(false)} thread={agent} />
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  top: { position: 'absolute', left: 0, right: 0, top: 0, zIndex: 2 },
  back: {
    position: 'absolute',
    left: 16,
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: 'rgba(255,255,255,0.08)',
    borderWidth: 1,
    borderColor: colors.glassBorder,
    alignItems: 'center',
    justifyContent: 'center',
  },
  gem: { position: 'absolute', left: 0, right: 0, alignItems: 'center' },
  panelWrap: { flex: 1 },
  panel: {
    flex: 1,
    borderTopLeftRadius: radii.sheet,
    borderTopRightRadius: radii.sheet,
    borderWidth: 1,
    borderBottomWidth: 0,
    borderColor: colors.glassBorder,
    overflow: 'hidden',
  },
  body: { paddingHorizontal: 16, paddingTop: 22 },
  underline: { width: 64, height: 3, borderRadius: 2, marginTop: 8 },
  subtitle: { marginTop: 12, marginBottom: 16 },
  stats: { flexDirection: 'row', marginTop: 10 },
  statCell: { flex: 1 },
  statGap: { marginLeft: 8 },
  section: { marginTop: 22, marginBottom: 2 },
  ask: { position: 'absolute', left: 16, right: 16 },
  askFade: { position: 'absolute', left: 0, right: 0, bottom: 0 },
});
