// Phase 3 graphics preview (temporary): tap to cycle scenario + morph.
import { useEffect, useState } from 'react';
import { I18nManager, Pressable, StyleSheet, Text, useWindowDimensions, View } from 'react-native';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { StatusBar } from 'expo-status-bar';
import { withTiming, withSequence, withDelay, Easing } from 'react-native-reanimated';
import { useSafeAreaInsets, SafeAreaProvider } from 'react-native-safe-area-context';
import { OrbitSceneCanvas } from './src/familyos/graphics/OrbitScene';
import { ensureMorphData, useCreateOrbitScene } from './src/familyos/graphics/sceneState';
import { paletteOf, SCENARIOS, type Scenario } from './src/familyos/theme/stateThemes';
import { AGENT_IDS, colors, hexToRgb } from './src/familyos/theme/tokens';

I18nManager.allowRTL(false);

function Preview() {
  const { width, height } = useWindowDimensions();
  const insets = useSafeAreaInsets();
  const scene = useCreateOrbitScene('calm');
  const [scen, setScen] = useState<Scenario>('calm');
  const [step, setStep] = useState(0);
  useEffect(() => {
    ensureMorphData(scene);
    scene.intro.value = withTiming(1, { duration: 900 });
  }, [scene]);

  const onTap = () => {
    const next = (step + 1) % 8;
    setStep(next);
    if (next === 1) {
      const ns = SCENARIOS[(SCENARIOS.indexOf(scen) + 1) % 4];
      setScen(ns);
      scene.paletteFrom.value = paletteOf(scen);
      scene.paletteTo.value = paletteOf(ns);
      scene.paletteT.value = 0;
      scene.paletteT.value = withTiming(1, { duration: 700 });
    } else if (next >= 2 && next <= 6) {
      const k = next - 2;
      const prevShape = scene.morphTo.value;
      scene.morphFrom.value = prevShape;
      scene.morphTo.value = k + 1;
      scene.morphColFrom.value = prevShape === 0 ? [0.75, 0.9, 1] : hexToRgb(colors.agents[AGENT_IDS[prevShape - 1]]);
      scene.morphColTo.value = hexToRgb(colors.agents[AGENT_IDS[k]]);
      scene.satHighlight.value = k;
      scene.morphT.value = 0;
      scene.morphT.value = withTiming(1, { duration: 900, easing: Easing.linear });
      if (prevShape === 0) {
        scene.explode.value = withTiming(1, { duration: 650 });
        scene.morphAlpha.value = withTiming(1, { duration: 250 });
      }
    } else if (next === 7) {
      scene.morphFrom.value = scene.morphTo.value;
      scene.morphColFrom.value = scene.morphColTo.value;
      scene.morphColTo.value = [0.75, 0.9, 1];
      scene.morphTo.value = 0;
      scene.satHighlight.value = -1;
      scene.morphT.value = 0;
      scene.morphT.value = withTiming(1, { duration: 900, easing: Easing.linear });
      scene.morphAlpha.value = withDelay(500, withTiming(0, { duration: 400 }));
      scene.explode.value = withDelay(350, withTiming(0, { duration: 650 }));
    } else {
      scene.squash.value = withSequence(withTiming(0.94, { duration: 90 }), withTiming(1, { duration: 300 }));
    }
  };

  return (
    <View style={styles.root}>
      <OrbitSceneCanvas scene={scene} frame={{ W: width, H: height, top: insets.top }} paused={false} blurred={false} />
      <Pressable style={StyleSheet.absoluteFill} onPress={onTap} />
      <Text style={[styles.dbg, { top: insets.top + 8 }]}>{`${scen} · step ${step}`}</Text>
    </View>
  );
}

export default function App() {
  return (
    <GestureHandlerRootView style={styles.root}>
      <SafeAreaProvider>
        <StatusBar style="light" />
        <Preview />
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#000' },
  dbg: { position: 'absolute', left: 20, color: '#8E93A3', fontSize: 12 },
});
