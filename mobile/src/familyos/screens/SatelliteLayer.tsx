// React overlay for the five satellites: label, badge and an invisible
// 72 px hit area each, following the Skia satellites' drift on the UI thread
// (same orbitLayout maths). Tap = that agent's walkthrough (video 0:26),
// long-press = that agent's Deep Layer screen.
import { Pressable, StyleSheet, View } from 'react-native';
import Animated, { useAnimatedStyle, useReducedMotion } from 'react-native-reanimated';
import * as Haptics from 'expo-haptics';
import type { AgentId } from '../theme/tokens';
import { AGENT_IDS } from '../theme/tokens';
import { type as T } from '../theme/typography';
import { agentNames } from '../mocks/data';
import type { NeedsItem } from '../services/interfaces';
import type { OrbitScene } from '../graphics/sceneState';
import { loopPhase, satellitePos, satelliteRadius, type Frame } from '../graphics/orbitLayout';
import { AppText } from '../components/AppText';
import { Badge } from '../components/Labels';
import { agentBadges } from './homeLogic';

const HIT = 72;

interface Props {
  scene: OrbitScene;
  frame: Frame;
  needs: NeedsItem[];
  onTap: (agent: AgentId) => void;
  onLongPress: (agent: AgentId, x: number, y: number) => void;
}

function Satellite({ i, scene, frame, badge, onTap, onLongPress }: { i: number; scene: OrbitScene; frame: Frame; badge?: { n: number; color: string }; onTap: Props['onTap']; onLongPress: Props['onLongPress'] }) {
  const id = AGENT_IDS[i];
  const reduced = useReducedMotion();
  const sr = satelliteRadius(frame);
  const st = useAnimatedStyle(() => {
    const ph = reduced ? 0 : loopPhase(scene.clock.value);
    const p = satellitePos(frame, i, ph);
    const pop = Math.min(1, Math.max(0, scene.intro.value * 6 - i * 0.6 - 0.4));
    const hl = scene.satHighlight.value;
    return {
      opacity: (1 - scene.dashT.value) * pop * (hl >= 0 && hl !== i ? 0.6 : 1),
      // Follows the canvas satellites, including their drag parallax (§3.4.6).
      transform: [{ translateX: p.x + scene.parallax.value[0] - HIT / 2 }, { translateY: p.y + scene.parallax.value[1] - HIT / 2 }],
    };
  });
  const label = `${agentNames[id]} agent${badge ? `, ${badge.n} ${badge.n === 1 ? 'item needs' : 'items need'} you` : ''}`;
  return (
    <Animated.View style={[styles.sat, st]} pointerEvents="box-none">
      <Pressable
        style={styles.hit}
        onPress={() => {
          void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
          onTap(id);
        }}
        onLongPress={() => {
          void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
          const p = satellitePos(frame, i, loopPhase(scene.clock.value));
          onLongPress(id, p.x, p.y);
        }}
        delayLongPress={380}
        accessibilityRole="button"
        accessibilityLabel={label}
        accessibilityHint="Plays this agent's summary. Long-press to open the agent."
      />
      <View style={[styles.labelWrap, { top: HIT / 2 + sr + 4 }]} pointerEvents="none">
        <AppText style={T.satLabel}>{agentNames[id]}</AppText>
      </View>
      {badge ? (
        <View style={[styles.badge, { left: HIT / 2 + sr * 0.55, top: HIT / 2 - sr - 6 }]} pointerEvents="none">
          <Badge count={badge.n} color={badge.color} />
        </View>
      ) : null}
    </Animated.View>
  );
}

export function SatelliteLayer({ scene, frame, needs, onTap, onLongPress }: Props) {
  const badges = agentBadges(needs);
  return (
    <View style={StyleSheet.absoluteFill} pointerEvents="box-none">
      {AGENT_IDS.map((id, i) => (
        <Satellite key={id} i={i} scene={scene} frame={frame} badge={badges[id]} onTap={onTap} onLongPress={onLongPress} />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  sat: { position: 'absolute', left: 0, top: 0, width: HIT, height: HIT },
  hit: { width: HIT, height: HIT, borderRadius: HIT / 2 },
  labelWrap: { position: 'absolute', left: -30, right: -30, alignItems: 'center' },
  badge: { position: 'absolute' },
});
