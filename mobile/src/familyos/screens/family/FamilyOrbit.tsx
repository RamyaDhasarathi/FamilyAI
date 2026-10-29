// Family orbit header (AGENT_CORE_AND_FAMILY.md §4.4): the mini crystal with
// one glowing dot per member on a tilted ring, in each member's stage colour
// (the owner's a little larger). New members fly in from the edge; removed
// ones dissolve into particles. Tapping the crystal gives the Home jelly.
// With only the owner, empty dashed slots wait on the ring.
import { useEffect, useMemo, useRef } from 'react';
import { AppState, StyleSheet, View } from 'react-native';
import { Canvas, Fill, PaintStyle, Picture, Shader, Skia, createPicture, type SkCanvas } from '@shopify/react-native-skia';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import Animated, { useDerivedValue, useFrameCallback, useReducedMotion, useSharedValue } from 'react-native-reanimated';
import * as Haptics from 'expo-haptics';
import { scheduleOnRN } from 'react-native-worklets';
import type { FamilyMember } from '../../services/interfaces';
import { stageOf } from '../../family/model';
import { hexToRgb } from '../../theme/tokens';
import { paletteOf } from '../../theme/stateThemes';
import { ambientEffect } from '../../graphics/ambientShader';
import { coreMeshLow } from '../../graphics/crystalGeometry';
import { drawStone } from '../../graphics/stoneStyle';
import { createOrbitScene } from '../../graphics/sceneState';
import { IDLE_AXIS, IDLE_SPEED, qRotateView, qToMat } from '../../graphics/coreMotion';
import { jellyAtGem } from '../../graphics/coreInput';
import { RIPPLE_LIFE } from '../../graphics/crystalRenderV2';

/** One dot: [r, g, b, owner(0/1), bornAt, diedAt (-1 = alive), angle]. */
type Dot = { id: string; c: number[]; owner: boolean; born: number; died: number; ang: number };

const ENTER = 0.9;
const LEAVE = 0.8;
const tap = () => {
  void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
};

function drawDot(c: SkCanvas, x: number, y: number, r: number, col: number[], a: number) {
  'worklet';
  const p = Skia.Paint();
  p.setAntiAlias(true);
  p.setColor(Skia.Color([col[0], col[1], col[2], 0.22 * a]));
  c.drawCircle(x, y, r * 2.6, p);
  p.setColor(Skia.Color([col[0], col[1], col[2], 0.55 * a]));
  c.drawCircle(x, y, r * 1.5, p);
  p.setColor(Skia.Color([Math.min(1, col[0] * 0.5 + 0.55), Math.min(1, col[1] * 0.5 + 0.55), Math.min(1, col[2] * 0.5 + 0.55), a]));
  c.drawCircle(x, y, r, p);
}

export function FamilyOrbit({ members, width, height = 150 }: { members: FamilyMember[]; width: number; height?: number }) {
  const reduced = useReducedMotion();
  const scene = useMemo(() => createOrbitScene('calm'), []);
  const dots = useSharedValue<Dot[]>([]);
  const seen = useRef<Set<string>>(new Set());
  const first = useRef(true);
  const cx = width / 2;
  const cy = height / 2;
  const R = 26;
  const rx = Math.min(width * 0.4, 170);
  const ry = height * 0.28;
  const pal = useMemo(() => paletteOf('calm'), []);

  // Diff members → dots: new ids fly in, missing ids dissolve.
  useEffect(() => {
    const now = scene.clock.get();
    const ids = new Set(members.map((m) => m.id));
    const cur = dots.get();
    const next: Dot[] = cur.map((d) => (!ids.has(d.id) && d.died < 0 ? { ...d, died: now } : d));
    for (const m of members) {
      if (cur.some((d) => d.id === m.id && d.died < 0)) continue;
      const revived = next.findIndex((d) => d.id === m.id);
      const st = stageOf(m);
      const dot: Dot = { id: m.id, c: hexToRgb(st.accent), owner: m.isOwner, born: first.current ? -10 : now, died: -1, ang: 0 };
      if (revived >= 0) next[revived] = dot;
      else next.push(dot);
      seen.current.add(m.id);
    }
    // Colours follow stage changes.
    for (const d of next) {
      const m = members.find((x) => x.id === d.id);
      if (m) d.c = hexToRgb(stageOf(m).accent);
    }
    first.current = false;
    dots.set(next);
  }, [members, dots, scene]);

  const cb = useFrameCallback((f) => {
    const dt = Math.min(f.timeSincePreviousFrame ?? 16, 50) / 1000;
    scene.clock.set(scene.clock.get() + dt);
    if (!reduced) scene.orient.set(qRotateView(scene.orient.get(), IDLE_AXIS[0], IDLE_AXIS[1], IDLE_AXIS[2], IDLE_SPEED * 1.3 * dt));
    const now = scene.clock.get();
    // Ease each dot towards its evenly spaced slot; drop finished dissolves.
    scene.ripples.modify((rp) => {
      'worklet';
      return rp.length > 0 && now - rp[3] > RIPPLE_LIFE ? rp.slice(4) : rp;
    }, false);
    dots.modify((ds) => {
      'worklet';
      const live = ds.filter((d) => d.died < 0);
      const out: Dot[] = [];
      for (const d of ds) {
        if (d.died >= 0 && now - d.died > LEAVE) continue;
        const k = live.indexOf(d);
        if (k >= 0) {
          const target = (k / Math.max(1, live.length)) * Math.PI * 2 + now * (reduced ? 0 : 0.18);
          let diff = target - d.ang;
          diff -= Math.round(diff / (Math.PI * 2)) * Math.PI * 2;
          d.ang = d.ang + diff * Math.min(1, dt * 4);
        }
        out.push(d);
      }
      return out;
    }, false);
  }, false);

  useEffect(() => {
    cb.setActive(true);
    const sub = AppState.addEventListener('change', (s) => cb.setActive(s === 'active'));
    return () => {
      sub.remove();
      cb.setActive(false);
    };
  }, [cb]);

  const uniforms = useDerivedValue(() => ({
    res: [width, height], ph: (scene.clock.value / 72) * Math.PI * 2, center: [cx, cy], radius: R,
    tint: [0, 0, 0], corner: [0, 0, 0], halo: [pal[10], pal[11], pal[12]], haloAmt: 0.7 + 0.5 * scene.coreFlash.value, dustAmt: 1.3,
    dustCol: [0.75, 0.84, 1], starAmt: 0,
    sats: [-99, -99, -99, -99, -99, -99, -99, -99, -99, -99], satCols: new Array(15).fill(0), satR: 1, satAmt: 0,
    lowPower: 1, clearBg: 1, pushDir: scene.dustPushDir.value, pushAmt: scene.dustPush.value * 0.6,
  }));

  const picture = useDerivedValue(() =>
    createPicture((c) => {
      const now = scene.clock.value;
      const ds = dots.value;
      const live = ds.filter((d) => d.died < 0);
      // Empty state: dashed slots on the ring.
      if (live.length <= 1) {
        const p = Skia.Paint();
        p.setStyle(PaintStyle.Stroke);
        p.setAntiAlias(true);
        p.setStrokeWidth(1);
        p.setPathEffect(Skia.PathEffect.MakeDash([3, 4], 0));
        p.setColor(Skia.Color([1, 1, 1, 0.28]));
        for (let i = 1; i < 5; i++) {
          const a = (i / 5) * Math.PI * 2 + 0.5;
          c.drawCircle(cx + Math.cos(a) * rx, cy + Math.sin(a) * ry, 7, p);
        }
      }
      const place = (d: Dot) => {
        let x = cx + Math.cos(d.ang) * rx;
        let y = cy + Math.sin(d.ang) * ry;
        const enter = Math.min(1, (now - d.born) / ENTER);
        if (enter < 1) {
          // Fly in from the right edge on an ease-out curve.
          const e = 1 - Math.pow(1 - enter, 3);
          x = width + 24 + (x - width - 24) * e;
          y = cy - 30 + (y - cy + 30) * e;
        }
        return { x, y, front: Math.sin(d.ang) > 0 };
      };
      const draw = (front: boolean) => {
        for (const d of ds) {
          const pos = place(d);
          if (pos.front !== front) continue;
          const r = (d.owner ? 5.5 : 4) * (0.8 + 0.2 * (pos.front ? 1 : 0));
          if (d.died >= 0) {
            // Dissolve: the dot fades while particles fly outward.
            const t = (now - d.died) / LEAVE;
            drawDot(c, pos.x, pos.y, r * (1 - t), d.c, 1 - t);
            const p = Skia.Paint();
            p.setAntiAlias(true);
            p.setColor(Skia.Color([d.c[0], d.c[1], d.c[2], 1 - t]));
            for (let k = 0; k < 10; k++) {
              const a = (k / 10) * Math.PI * 2 + d.ang;
              c.drawCircle(pos.x + Math.cos(a) * t * 22, pos.y + Math.sin(a) * t * 22, 1.3, p);
            }
          } else drawDot(c, pos.x, pos.y, r, d.c, Math.min(1, (now - d.born) / 0.3));
        }
      };
      draw(false);
      const rp = scene.ripples.value;
      const ripples: number[] = [];
      for (let k = 0; k < rp.length; k += 4) ripples.push(rp[k], rp[k + 1], rp[k + 2], now - rp[k + 3]);
      const jd = scene.jellyDir.value;
      drawStone(c, coreMeshLow, {
        cx, cy, R: R * scene.corePulse.value, rotY: 0, tiltX: 0.35, phase: (now / 18) * Math.PI * 2, palette: pal, agent: null,
        alpha: 1, explode: 0, glow: 0, sx: 1, sy: 1, lowPower: false,
        rot: qToMat(scene.orient.value), ripples, squash: [jd[0], jd[1], jd[2], scene.jelly.value], flash: scene.coreFlash.value,
      } as Parameters<typeof drawStone>[2]);
      draw(true);
    })
  );

  const gesture = Gesture.Tap()
    .onEnd((e, ok) => {
      if (!ok) return;
      if (Math.hypot(e.x - cx, e.y - cy) > R + 14) return;
      scheduleOnRN(tap);
      jellyAtGem(scene, cx, cy, R, e.x, e.y, reduced);
    });

  return (
    <GestureDetector gesture={gesture}>
      <Animated.View style={{ width, height }} accessibilityRole="image" accessibilityLabel={`Your family: ${members.length} ${members.length === 1 ? 'member' : 'members'}`}>
        <Canvas style={StyleSheet.absoluteFill} pointerEvents="none">
          <Fill>
            <Shader source={ambientEffect} uniforms={uniforms} />
          </Fill>
          <Picture picture={picture} />
        </Canvas>
        <View pointerEvents="none" />
      </Animated.View>
    </GestureDetector>
  );
}
