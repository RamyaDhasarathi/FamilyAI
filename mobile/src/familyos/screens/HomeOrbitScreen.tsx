// Home — the Orbit screen (AGENT.md §8.1, video 0:00). Layers, back → front:
// Skia scene (ambient, dust, satellites, gem, morph) → satellite overlays →
// text and controls → Dashboard → modal sheets → toasts.
import { useCallback, useEffect, useMemo, useState } from 'react';
import { BackHandler, Pressable, StyleSheet, View, useWindowDimensions } from 'react-native';
import * as Haptics from 'expo-haptics';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useFocusEffect, useIsFocused } from '@react-navigation/native';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import Animated, { Keyframe, useAnimatedStyle, useReducedMotion, withSpring, withTiming } from 'react-native-reanimated';
import { scheduleOnRN } from 'react-native-worklets';
import type { AgentId } from '../theme/tokens';
import { colors } from '../theme/tokens';
import { springs } from '../theme/motion';
import { scenarioThemes } from '../theme/stateThemes';
import { copy, walkLabel } from '../mocks/data';
import { headlineItem, summaryCount } from '../mocks/scenarios';
import { useFamilyOS, useMood } from '../store/useFamilyOS';
import { OrbitSceneCanvas } from '../graphics/OrbitScene';
import { OrbitSceneContext, ensureMorphData, useCreateOrbitScene } from '../graphics/sceneState';
import { useLowPowerProbe } from '../graphics/useLowPowerProbe';
import { usePerfSampler } from '../graphics/usePerfSampler';
import type { ScreenProps } from '../navigation/types';
import { AskBar } from '../components/AskBar';
import { SummaryButton } from '../components/SummaryButton';
import { SwipeCard } from '../components/SwipeCard';
import { ToastHost } from '../components/Toast';
import { HomeHeader, StatusBlock } from './HomeParts';
import { SatelliteLayer } from './SatelliteLayer';
import { CoreGestureLayer } from './CoreGestureLayer';
import { TodaySheet } from './TodaySheet';
import { NeedsYouSheet } from './NeedsYouSheet';
import { ProfileMenu, type MenuTarget } from './ProfileMenu';
import { ChatSheet } from './ChatSheet';
import { DashboardSheet } from './DashboardSheet';
import { AgentReveal, type Reveal } from './AgentReveal';
import { useWalkthrough } from './useWalkthrough';
import { useCelebration, useListening, useScenarioSync } from './useHomeEffects';

// App open (AGENT.md §9): text rises 8 px and fades in after the gem.
const riseIn = (delay: number) =>
  new Keyframe({
    0: { opacity: 0, transform: [{ translateY: 8 }] },
    100: { opacity: 1, transform: [{ translateY: 0 }] },
  })
    .duration(420)
    .delay(delay);

export function HomeOrbitScreen({ navigation }: ScreenProps<'Home'>) {
  const { width, height } = useWindowDimensions();
  const insets = useSafeAreaInsets();
  const frame = useMemo(() => ({ W: width, H: height, top: insets.top }), [width, height, insets.top]);
  const scene = useCreateOrbitScene('calm');
  const focused = useIsFocused();
  const reduced = useReducedMotion();
  const st = useFamilyOS();
  const mood = useMood();
  const { start, stop } = useWalkthrough(scene);
  const { listening, listen } = useListening(scene);
  const [dashOpen, setDashOpen] = useState(false);
  const [reveal, setReveal] = useState<Reveal | null>(null);
  const [singleH, setSingleH] = useState(140);
  useScenarioSync(scene, mood);
  usePerfSampler(scene);
  useCelebration(scene);
  useLowPowerProbe(scene, (low, avg) => {
    if (__DEV__) console.log(`[perf] Home UI-thread frame avg ${avg.toFixed(1)} ms (${(1000 / avg).toFixed(0)} fps), lowPower=${low}`);
    if (low) st.setLowPower(true);
  });

  useEffect(() => {
    // Home normally opens after Loading has booted the store; boot here if not.
    if (!useFamilyOS.getState().booted) void useFamilyOS.getState().boot();
    scene.intro.set(withTiming(1, { duration: 1100 }));
    // Icon sampling uses Skia paths on the JS thread; do it after first paint.
    const id = setTimeout(() => ensureMorphData(scene), 400);
    return () => clearTimeout(id);
  }, [scene]);
  useEffect(() => {
    scene.lowPower.set(st.lowPower);
  }, [st.lowPower, scene]);

  // Android back: sheets close themselves; then the dashboard.
  useFocusEffect(
    useCallback(() => {
      const sub = BackHandler.addEventListener('hardwareBackPress', () => {
        if (!dashOpen) return false;
        scene.dashT.set(withSpring(0, springs.soft));
        setDashOpen(false);
        return true;
      });
      return () => sub.remove();
    }, [dashOpen, scene])
  );

  // Dev deep links (navigation/devLinks.ts): open/close the dashboard, start a walkthrough.
  useEffect(
    () =>
      useFamilyOS.subscribe((s, prev) => {
        const dev = s.devCommand;
        if (!dev || dev === prev.devCommand) return;
        if (dev.cmd.dash) {
          const open = dev.cmd.dash === '1';
          scene.dashT.set(withSpring(open ? 1 : 0, springs.soft));
          setDashOpen(open);
        }
        if (dev.cmd.stop) stop();
        if (dev.cmd.dbg) scene.debugMask.set(Number(dev.cmd.dbg));
        if (dev.cmd.low) useFamilyOS.getState().setLowPower(dev.cmd.low === '1');
        if (dev.cmd.walk) void start(dev.cmd.walk === 'today' ? undefined : (dev.cmd.walk as AgentId), false);
      }),
    [scene, start, stop]
  );

  const walking = st.walk.active;
  // Opening a sheet or the dashboard ends a running walkthrough.
  useEffect(() => {
    if ((st.sheet !== null || dashOpen) && useFamilyOS.getState().walk.active) stop();
  }, [st.sheet, dashOpen, stop]);
  const step = st.walk.steps[st.walk.index];
  const top = headlineItem(st.needs);
  const { n, word } = summaryCount(st.needs);
  const theme = scenarioThemes[mood];

  const openAgent = useCallback(
    (agent: AgentId) => {
      st.closeSheet();
      stop();
      navigation.navigate('Agent', { agent });
    },
    [navigation, st, stop]
  );
  const onSummaryButton = () => {
    if (walking) stop();
    else if (st.summaryMode === 'read') st.openSheet('today');
    else void start(undefined, true);
  };
  // Long-press on the crystal plays today's summary (a tap now wobbles it, §3.2).
  const onCoreLongPress = () => {
    void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    void start(undefined, st.summaryMode === 'listen');
  };
  const onMenu = (t: MenuTarget) => {
    st.closeSheet();
    if (typeof t === 'object') navigation.navigate('Placeholder', { title: t.placeholder });
    else if (t === 'Login') navigation.navigate('Login');
    else if (t === 'Profile') navigation.navigate('Placeholder', { title: 'Profile' });
    else navigation.navigate(t);
  };
  const onLogout = async () => {
    stop();
    await st.logOut();
    navigation.reset({ index: 0, routes: [{ name: 'Login' }] });
  };

  // Swipe up anywhere on Home: the dashboard follows the finger.
  const swipeUp = Gesture.Pan()
    .activeOffsetY(-14)
    .failOffsetX([-30, 30])
    .onStart(() => {
      if (walking) scheduleOnRN(stop);
    })
    .onUpdate((e) => {
      scene.dashT.set(Math.min(1, Math.max(0, -e.translationY / (height * 0.55))));
    })
    .onEnd((e) => {
      const open = scene.dashT.value > 0.3 || e.velocityY < -500;
      scene.dashT.set(withSpring(open ? 1 : 0, springs.soft));
      scheduleOnRN(setDashOpen, open);
    });

  const fade = useAnimatedStyle(() => ({ opacity: Math.max(0, 1 - scene.dashT.value * 1.8) }));
  const single = !walking && st.needs.length === 1 && st.sheet === null ? st.needs[0] : null;
  const label = walking && step ? walkLabel(step.agent, st.walk.index + 1, st.walk.steps.length, !!st.walk.agent) : theme.label;
  const labelColor = walking && step ? colors.agents[step.agent] : theme.dot;
  const headline = walking && step ? step.text : mood === 'calm' || !top ? copy.calmHeadline : top.text;

  return (
    <OrbitSceneContext.Provider value={scene}>
      <View style={styles.root}>
        <OrbitSceneCanvas scene={scene} frame={frame} paused={!focused} blurred={st.sheet !== null} />
        <GestureDetector gesture={swipeUp}>
          <Animated.View style={[StyleSheet.absoluteFill, fade]} pointerEvents={dashOpen ? 'none' : 'auto'}>
            {walking ? <Pressable style={StyleSheet.absoluteFill} onPress={stop} accessibilityLabel="Stop the summary" /> : null}
            <CoreGestureLayer
              scene={scene}
              frame={frame}
              walking={walking}
              reduced={reduced}
              swipeUp={swipeUp}
              onLongPress={onCoreLongPress}
              onStop={stop}
            />
            <SatelliteLayer
              scene={scene}
              frame={frame}
              needs={st.needs}
              onTap={(a) => void start(a, st.summaryMode === 'listen')}
              onLongPress={(agent, x, y) => setReveal({ agent, x, y })}
            />
            <Animated.View entering={riseIn(350)} style={{ paddingTop: insets.top + 8 }} pointerEvents="box-none">
              {st.profile ? (
                <HomeHeader
                  profile={st.profile}
                  summaryWord={mood === 'calm' ? copy.allClear : `${n} ${word}`}
                  summaryDot={theme.dot}
                  onSummary={() => st.openSheet(st.needs.length ? 'needs' : 'today')}
                  onAvatar={() => st.openSheet('profile')}
                  onDateLongPress={__DEV__ ? st.cycleScenario : undefined}
                />
              ) : null}
            </Animated.View>
            <Animated.View
              entering={riseIn(500)}
              style={[styles.status, { bottom: single ? insets.bottom + 12 + singleH + 10 : insets.bottom + 14 + 52 + 10 }]}
              pointerEvents="box-none"
            >
              <StatusBlock
                label={label}
                color={labelColor}
                headline={headline}
                compact={!!single}
                calm={!walking && mood === 'calm'}
                more={!walking && st.needs.length > 1 ? copy.more(st.needs.length - 1) : undefined}
                onMore={() => st.openSheet('needs')}
              />
            </Animated.View>
            {single ? (
              <View style={[styles.single, { bottom: insets.bottom + 12 }]} onLayout={(e) => setSingleH(e.nativeEvent.layout.height)}>
                <SwipeCard item={single} onDone={st.resolve} onLater={st.snooze} />
              </View>
            ) : (
              <View style={[styles.bottomBar, { bottom: insets.bottom + 14, opacity: st.sheet === 'chat' ? 0 : 1 }]} pointerEvents="box-none">
                <AskBar placeholder={copy.askPlaceholder} onPress={() => st.openChat('home')} onMic={listen} listening={listening} style={styles.ask} />
                <SummaryButton
                  mode={st.summaryMode}
                  playing={walking}
                  progress={st.walk.steps.length ? (st.walk.index + 1) / st.walk.steps.length : 0}
                  onPress={onSummaryButton}
                />
              </View>
            )}
          </Animated.View>
        </GestureDetector>
        <DashboardSheet
          scene={scene}
          open={dashOpen}
          onSettle={setDashOpen}
          onOpenAgent={openAgent}
          onOpenSummary={() => st.openSheet(mood === 'urgent' ? 'needs' : 'today')}
          onAsk={() => st.openChat('home')}
          onMic={listen}
          listening={listening}
        />
        <TodaySheet visible={st.sheet === 'today'} onClose={st.closeSheet} onOpenAgent={openAgent} />
        <NeedsYouSheet visible={st.sheet === 'needs'} onClose={st.closeSheet} />
        <ChatSheet visible={focused && st.sheet === 'chat'} onClose={st.closeSheet} thread={st.chatThread} />
        <ProfileMenu visible={st.sheet === 'profile'} onClose={st.closeSheet} onNavigate={onMenu} onLogout={onLogout} />
        <ToastHost bottom={insets.bottom + 84} />
        {reveal ? (
          <AgentReveal
            reveal={reveal}
            onCovered={() => navigation.navigate('Agent', { agent: reveal.agent, via: 'reveal' })}
            onDone={() => setReveal(null)}
          />
        ) : null}
      </View>
    </OrbitSceneContext.Provider>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  status: { position: 'absolute', left: 0, right: 0 },
  bottomBar: { position: 'absolute', left: 16, right: 16, flexDirection: 'row', alignItems: 'center' },
  ask: { flex: 1, marginRight: 10 },
  single: { position: 'absolute', left: 14, right: 14 },
});
