// Loading (design.md §13.2): the gem with the five agent colours orbiting
// as glowing dots, the wordmark, stepping status text and an agent-colour
// progress bar. ~2.6 s, then Home (or Log in when signed out).
import { useEffect, useState } from 'react';
import { StyleSheet, View } from 'react-native';
import Animated, { Easing, useAnimatedStyle, useSharedValue, withRepeat, withTiming, FadeIn } from 'react-native-reanimated';
import { AGENT_IDS, colors } from '../theme/tokens';
import { fonts, type as T } from '../theme/typography';
import { copy } from '../mocks/data';
import { useFamilyOS } from '../store/useFamilyOS';
import type { ScreenProps } from '../navigation/types';
import { MiniGem } from '../graphics/MiniGem';
import { OnboardingBackdrop } from '../graphics/OnboardingBackdrop';
import { AppText } from '../components/AppText';

const DURATION = 2600;
const RING = 150;

export function LoadingScreen({ navigation }: ScreenProps<'Loading'>) {
  const boot = useFamilyOS((s) => s.boot);
  const [msg, setMsg] = useState(0);
  const [pct, setPct] = useState(0);
  const spin = useSharedValue(0);
  const progress = useSharedValue(0);

  useEffect(() => {
    spin.value = withRepeat(withTiming(1, { duration: 6000, easing: Easing.linear }), -1);
    progress.value = withTiming(1, { duration: DURATION, easing: Easing.inOut(Easing.cubic) });
    const t0 = Date.now();
    const tick = setInterval(() => {
      const k = Math.min(1, (Date.now() - t0) / DURATION);
      setPct(Math.round(k * 100));
      setMsg(Math.min(copy.loading.length - 1, Math.floor(k * copy.loading.length)));
    }, 120);
    const ready = Promise.all([boot(), new Promise((r) => setTimeout(r, DURATION))]);
    void ready.then(() => {
      const loggedIn = useFamilyOS.getState().loggedIn;
      navigation.reset({ index: 0, routes: [{ name: loggedIn ? 'Home' : 'Login' }] });
    });
    return () => clearInterval(tick);
  }, [boot, navigation, progress, spin]);

  const ring = useAnimatedStyle(() => ({ transform: [{ rotate: `${spin.value * 360}deg` }] }));
  const bar = useAnimatedStyle(() => ({ width: `${progress.value * 100}%` }));
  return (
    <View style={styles.root}>
      <OnboardingBackdrop />
      <View style={styles.center}>
        <View style={styles.gemWrap}>
          <View style={styles.ringTrack} />
          <Animated.View style={[styles.ring, ring]}>
            {AGENT_IDS.map((id, i) => {
              const a = (i / AGENT_IDS.length) * Math.PI * 2;
              return (
                <View
                  key={id}
                  style={[
                    styles.dot,
                    {
                      backgroundColor: colors.agents[id],
                      shadowColor: colors.agents[id],
                      left: RING + Math.cos(a) * RING - 5,
                      top: RING + Math.sin(a) * RING - 5,
                    },
                  ]}
                />
              );
            })}
          </Animated.View>
          <MiniGem size={220} />
        </View>
        <AppText style={styles.word} accessibilityRole="header">
          {copy.appName}
        </AppText>
        <Animated.View key={msg} entering={FadeIn.duration(260)}>
          <AppText style={[T.small, styles.msg]}>{copy.loading[msg]}</AppText>
        </Animated.View>
        <View
          style={styles.track}
          accessible
          accessibilityRole="progressbar"
          accessibilityLabel={copy.loading[msg]}
          accessibilityValue={{ min: 0, max: 100, now: pct }}
        >
          <Animated.View style={[styles.fill, bar]}>
            {AGENT_IDS.map((id) => (
              <View key={id} style={[styles.seg, { backgroundColor: colors.agents[id] }]} />
            ))}
          </Animated.View>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  gemWrap: { width: RING * 2, height: RING * 2, alignItems: 'center', justifyContent: 'center', marginBottom: 28 },
  ringTrack: { position: 'absolute', width: RING * 2, height: RING * 2, borderRadius: RING, borderWidth: 1, borderColor: 'rgba(255,255,255,0.08)' },
  ring: { position: 'absolute', width: RING * 2, height: RING * 2 },
  dot: { position: 'absolute', width: 10, height: 10, borderRadius: 5, shadowOpacity: 1, shadowRadius: 8, elevation: 0 },
  word: { fontFamily: fonts.semibold, fontSize: 28, color: '#E1E4EB', letterSpacing: -0.4 },
  msg: { marginTop: 10 },
  track: { width: 180, height: 3, borderRadius: 2, backgroundColor: 'rgba(255,255,255,0.08)', marginTop: 22, overflow: 'hidden' },
  fill: { height: 3, flexDirection: 'row', overflow: 'hidden' },
  seg: { width: 36, height: 3 },
});
