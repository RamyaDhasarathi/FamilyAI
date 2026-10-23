// Touch handling for the Home crystal (AGENT_CORE_AND_FAMILY.md §3.2).
// Handlers only queue input (graphics/coreInput.ts); the scene applies it
// once per frame.
//
//   tap ........ jelly wobble (or stops a running walkthrough)
//   drag ....... trackball rotation; the surface under the finger follows it
//   flick ...... momentum spin with friction, then back to the idle spin
//   long-press . today's summary (what a tap used to do)
//
// The touch area is the circle of radius R + 12 px over the crystal: touches
// outside it fail at once, so they reach the Home swipe-up untouched. Every
// crystal gesture blocks the swipe-up, so a pan that starts on the crystal
// never opens the Dashboard.
import { StyleSheet } from 'react-native';
import { Gesture, GestureDetector, type GestureType } from 'react-native-gesture-handler';
import Animated, { withSpring, withTiming } from 'react-native-reanimated';
import { scheduleOnRN, scheduleOnUI } from 'react-native-worklets';
import * as Haptics from 'expo-haptics';
import { copy } from '../mocks/data';
import type { OrbitScene } from '../graphics/sceneState';
import { gemHome, type Frame } from '../graphics/orbitLayout';
import { IDLE_SPEED, JELLY_SPRING, MAX_SPIN } from '../graphics/coreMotion';
import { queueDrag, queueTap } from '../graphics/coreInput';

/** Extra touch margin around the crystal, px (§3.2). */
const HIT_MARGIN = 12;
const hapticLight = () => {
  void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
};

interface Props {
  scene: OrbitScene;
  frame: Frame;
  /** A summary walkthrough is running (the crystal is broken into icons). */
  walking: boolean;
  reduced: boolean;
  /** The Home swipe-up, which must never start from the crystal. */
  swipeUp: GestureType;
  onLongPress: () => void;
  onStop: () => void;
}

export function CoreGestureLayer({ scene, frame, walking, reduced, swipeUp, onLongPress, onStop }: Props) {
  const g = gemHome(frame);
  const hr = g.r + HIT_MARGIN;

  const inside = (x: number, y: number) => {
    'worklet';
    const dx = x - hr;
    const dy = y - hr;
    return dx * dx + dy * dy <= hr * hr;
  };

  const tap = Gesture.Tap()
    .maxDuration(400)
    .onTouchesDown((e, m) => {
      const t = e.changedTouches[0];
      if (!t || !inside(t.x, t.y)) m.fail();
    })
    .onEnd((e, ok) => {
      if (!ok) return;
      if (walking) {
        scheduleOnRN(onStop);
        return;
      }
      queueTap(scene, g.x - hr + e.x, g.y - hr + e.y);
    })
    .blocksExternalGesture(swipeUp);

  const pan = Gesture.Pan()
    .minDistance(6)
    .enabled(!walking)
    .onTouchesDown((e, m) => {
      const t = e.changedTouches[0];
      if (!t || !inside(t.x, t.y)) m.fail();
    })
    .onBegin(() => {
      // Light impact on touch-down (tap or drag).
      scheduleOnRN(hapticLight);
    })
    .onStart(() => {
      scene.dragging.set(true);
      scene.spin.set([0, 0, 0]);
      scene.idleBlend.set(0);
      scene.settling.set(false);
      scene.spinTicks.set([0, 0]);
    })
    .onChange((e) => {
      queueDrag(scene, e.changeX, e.changeY, e.velocityX, e.velocityY, e.translationX, e.translationY);
    })
    .onEnd((e) => {
      // Flick: the surface speed becomes an angular velocity, clamped to ~4 turns/s.
      const sp = Math.hypot(e.velocityX, e.velocityY);
      if (sp > 80) {
        const w = Math.min(MAX_SPIN, sp / g.r);
        scene.spin.set([(e.velocityY / sp) * w, (e.velocityX / sp) * w, 0]);
        scene.settling.set(w > IDLE_SPEED);
      }
    })
    .onFinalize(() => {
      scene.dragging.set(false);
      scene.stretch.set(reduced ? withTiming(0, { duration: 150 }) : withSpring(0, JELLY_SPRING));
    })
    .blocksExternalGesture(swipeUp);

  const longPress = Gesture.LongPress()
    .minDuration(500)
    .enabled(!walking)
    .onTouchesDown((e, m) => {
      const t = e.changedTouches[0];
      if (!t || !inside(t.x, t.y)) m.fail();
    })
    .onStart(() => {
      scheduleOnRN(onLongPress);
    })
    .blocksExternalGesture(swipeUp);

  const gesture = Gesture.Race(pan, Gesture.Exclusive(longPress, tap));

  return (
    <GestureDetector gesture={gesture}>
      <Animated.View
        style={[styles.hit, { left: g.x - hr, top: g.y - hr, width: hr * 2, height: hr * 2, borderRadius: hr }]}
        accessible
        accessibilityRole="button"
        accessibilityLabel={walking ? copy.core.stopLabel : copy.core.label}
        accessibilityActions={walking ? [{ name: 'activate', label: copy.core.stopLabel }] : [
          { name: 'activate', label: copy.core.wobble },
          { name: 'playSummary', label: copy.core.playSummary },
        ]}
        onAccessibilityAction={(e) => {
          if (walking) onStop();
          else if (e.nativeEvent.actionName === 'playSummary') onLongPress();
          else scheduleOnUI(queueTap, scene, g.x, g.y);
        }}
      />
    </GestureDetector>
  );
}

const styles = StyleSheet.create({
  hit: { position: 'absolute' },
});
