// The Home canvas: ambient shader (background, stars, dust halo, satellite
// glow) + one Picture with the satellites, the gem and the particle morph.
// Nothing here re-renders per frame; everything is derived on the UI thread.
import { memo, useEffect } from 'react';
import { AppState, StyleSheet } from 'react-native';
import {
  Blur,
  Canvas,
  Fill,
  Group,
  Paint,
  PaintStyle,
  Picture,
  Shader,
  Skia,
  createPicture,
  type SkPicture,
} from '@shopify/react-native-skia';
import { useDerivedValue, useFrameCallback, useReducedMotion, useSharedValue } from 'react-native-reanimated';
import { AGENT_IDS, colors, hexToRgb } from '../theme/tokens';
import { ambientEffect } from './ambientShader';
import { coreMeshLow } from './crystalGeometry';
import { drawStone, stoneCoreMesh, stoneSatelliteMeshes } from './stoneStyle';
import { drawBurst, drawMorphBucket, drawMorphRing, morphInFlight, type MorphState } from './ParticleMorph';
import { currentPalette, profAdd, type OrbitScene } from './sceneState';
import { gemAt, loopPhase, satellitePos, satelliteRadius, type Frame } from './orbitLayout';

const AGENT_RGB = AGENT_IDS.map((id) => hexToRgb(colors.agents[id]));
const DUST = hexToRgb(colors.dust);
// Whole-number spin speeds per satellite (turns per ambient loop), alternating direction.
const SAT_SPIN = [3, -4, 4, -3, 4];
/**
 * Satellites re-recorded per frame (round-robin): 1 of 5 → each updates at
 * 12 Hz. At ≤ 20°/s that is a ≤ 1.5 px step at the rim, which reads as smooth.
 */
const SATS_PER_FRAME = 1;

function morphStateOf(scene: OrbitScene, frame: Frame, ph: number): MorphState {
  'worklet';
  const g = gemAt(frame, scene.dashT.get());
  return {
    from: scene.morphFrom.get(),
    to: scene.morphTo.get(),
    t: scene.morphT.get(),
    alpha: scene.morphAlpha.get(),
    colFrom: scene.morphColFrom.get(),
    colTo: scene.morphColTo.get(),
    cx: g.x,
    cy: g.y,
    R: g.r,
    ph,
    lowPower: scene.lowPower.get(),
  };
}

/**
 * One satellite, centred on (0, 0) at full size: rotation, highlight glow and
 * walkthrough dimming are baked in; drift, pop-in scale and fades are applied
 * when the cached picture is drawn.
 */
function recordSatellite(i: number, ph: number, hl: number, low: boolean, still: boolean, sr: number, pal: number[]): SkPicture {
  'worklet';
  return createPicture((c) => {
    drawStone(c, stoneSatelliteMeshes[i], {
      cx: 0,
      cy: 0,
      R: sr,
      rotY: still || low ? 0.6 + i : SAT_SPIN[i] * ph + i,
      tiltX: 0.5 + (still ? 0 : 0.25 * Math.sin(2 * ph + i)),
      // Drives the v2 glitter twinkle (v1 ignores phase on satellites).
      phase: still ? 0 : ph,
      palette: pal,
      agent: AGENT_RGB[i],
      alpha: hl >= 0 && hl !== i ? 0.6 : 1,
      explode: 0,
      glow: hl === i ? 1 : 0,
      sx: 1,
      sy: 1,
      lowPower: low,
    });
  });
}

interface Props {
  scene: OrbitScene;
  frame: Frame;
  /** Pause all animation (screen covered or app in background). */
  paused: boolean;
  /** Blur the scene under a sheet. */
  blurred: boolean;
}

function OrbitSceneView({ scene, frame, paused, blurred }: Props) {
  const reduced = useReducedMotion();
  // Satellite pictures are re-recorded a few per frame instead of all five
  // every frame: building crystals is UI-thread JS, and the five small ones
  // cost more than the big gem (measured on a Snapdragon 778G: 43 → 60 fps).
  const satPics = useSharedValue<(SkPicture | null)[]>([null, null, null, null, null]);
  const satState = useSharedValue({ hl: -2, low: false, next: 0 });
  // Particle-morph buckets, cached the same way (see ParticleMorph.ts).
  const morphPics = useSharedValue<{ key: string; next: number; pics: (SkPicture | null)[] }>({
    key: '',
    next: 0,
    pics: [null, null, null],
  });
  const cb = useFrameCallback((info) => {
    const dt = info.timeSincePreviousFrame ?? 16;
    scene.clock.set(scene.clock.get() + Math.min(dt, 50) / 1000);

    const ms = morphStateOf(scene, frame, loopPhase(scene.clock.get()));
    if (ms.alpha <= 0.01) {
      if (morphPics.get().pics[0] !== null) morphPics.set({ key: '', next: 0, pics: [null, null, null] });
    } else {
      const m0 = performance.now();
      const key = `${ms.from}>${ms.to}`;
      const cur = morphPics.get();
      const all = morphInFlight(ms) || cur.key !== key || cur.pics[0] === null;
      const d = scene.morph.get();
      morphPics.modify((m) => {
        'worklet';
        for (let j = 0; j < (all ? 3 : 1); j++) {
          const k = all ? j : m.next;
          m.pics[k] = createPicture((c) => drawMorphBucket(c, d, ms, k));
        }
        m.key = key;
        m.next = (m.next + 1) % 3;
        return m;
      });
      profAdd(scene, 3, m0);
    }
    if (scene.dashT.get() >= 0.999 || (scene.debugMask.get() & 2) !== 0) return;
    const ph = loopPhase(scene.clock.get());
    const hl = scene.satHighlight.get();
    const low = scene.lowPower.get();
    const st = satState.get();
    // Highlight or quality changes must show at once on every satellite.
    const all = st.hl !== hl || st.low !== low || satPics.get()[4] === null;
    const sr = satelliteRadius(frame);
    const pal = currentPalette(scene);
    const t0 = performance.now();
    satPics.modify((pics) => {
      'worklet';
      for (let k = 0; k < (all ? 5 : SATS_PER_FRAME); k++) {
        const i = all ? k : (st.next + k) % 5;
        pics[i] = recordSatellite(i, ph, hl, low, reduced, sr, pal);
      }
      return pics;
    });
    profAdd(scene, 0, t0);
    satState.set({ hl, low, next: (st.next + SATS_PER_FRAME) % 5 });
  }, false);

  useEffect(() => {
    let active = !paused;
    cb.setActive(active);
    const sub = AppState.addEventListener('change', (st) => {
      active = st === 'active' && !paused;
      cb.setActive(active);
    });
    return () => sub.remove();
  }, [paused, cb]);

  const uniforms = useDerivedValue(() => {
    const u0 = performance.now();
    const ph = loopPhase(scene.clock.value);
    const pal = currentPalette(scene);
    const t = scene.dashT.value;
    const g = gemAt(frame, t);
    const intro = scene.intro.value;
    const pulseK = Math.max(1, Math.round(72 / pal[19]));
    const pulse = 0.78 + 0.22 * Math.sin(pulseK * ph);
    const listen = scene.listen.value;
    const satFade = (1 - t) * intro;
    const hl = scene.satHighlight.value;
    const sats: number[] = [];
    const satCols: number[] = [];
    for (let i = 0; i < 5; i++) {
      const p = satellitePos(frame, i, ph);
      sats.push(p.x, p.y);
      const dim = hl >= 0 && hl !== i ? 0.6 : 1;
      satCols.push(AGENT_RGB[i][0] * dim, AGENT_RGB[i][1] * dim, AGENT_RGB[i][2] * dim);
    }
    profAdd(scene, 5, u0);
    // Dust takes a hint of the scenario colour.
    const dc = [DUST[0] * 0.75 + pal[10] * 0.25, DUST[1] * 0.75 + pal[11] * 0.25, DUST[2] * 0.75 + pal[12] * 0.25];
    return {
      res: [frame.W, frame.H],
      ph,
      center: [g.x, g.y],
      radius: g.r,
      tint: [pal[13] * intro, pal[14] * intro, pal[15] * intro],
      corner: [pal[16] * intro, pal[17] * intro, pal[18] * intro],
      halo: [pal[10], pal[11], pal[12]],
      // While particles form an icon, the halo and dust step back so the icon reads.
      haloAmt: (pulse * (1 - 0.75 * scene.morphAlpha.value) + listen * 0.9 + scene.burst.value) * intro,
      dustAmt: (1.1 * (1 - 0.6 * scene.morphAlpha.value) + scene.burst.value * 1.5) * intro,
      dustCol: dc,
      starAmt: intro,
      sats,
      satCols,
      satR: satelliteRadius(frame),
      satAmt: satFade,
      lowPower: scene.lowPower.value ? 1 : 0,
      clearBg: 0,
      // Profiling: shrink the shader to nothing.
      ...((scene.debugMask.value & 1) !== 0 ? { res: [1, 1] } : {}),
    };
  });

  const picture = useDerivedValue(() =>
    createPicture((canvas) => {
      const p0 = performance.now();
      const ph = loopPhase(scene.clock.value);
      const pal = currentPalette(scene);
      const t = scene.dashT.value;
      const intro = scene.intro.value;
      const low = scene.lowPower.value;
      const still = reduced;

      const dbg = scene.debugMask.value;
      // Satellites (fade out as the dashboard opens; pop in on app open).
      const satFade = (dbg & 2) !== 0 ? 0 : 1 - t;
      const s0 = performance.now();
      if (satFade > 0.01) {
        const sr = satelliteRadius(frame);
        const hl = scene.satHighlight.value;
        const pics = satPics.value;
        for (let i = 0; i < 5; i++) {
          const pop = Math.min(1, Math.max(0, intro * 6 - i * 0.6 - 0.4));
          const pic = pics[i];
          if (pop <= 0 || !pic) continue;
          const p = satellitePos(frame, i, still ? 0 : ph);
          const a = satFade * pop;
          const s = 0.6 + 0.4 * pop;
          canvas.save();
          canvas.translate(p.x, p.y);
          canvas.scale(s, s);
          if (a < 0.99) {
            // Fades (app open, dashboard drag) only: a small alpha layer.
            const lp = Skia.Paint();
            lp.setAlphaf(a);
            canvas.saveLayer(lp, Skia.XYWHRect(-sr * 2, -sr * 2, sr * 4, sr * 4));
            canvas.drawPicture(pic);
            canvas.restore();
          } else {
            canvas.drawPicture(pic);
          }
          canvas.restore();
        }
        // Thin ring around the satellite being read in a walkthrough.
        if (hl >= 0) {
          const p = satellitePos(frame, hl, still ? 0 : ph);
          const ring = Skia.Paint();
          ring.setStyle(PaintStyle.Stroke);
          ring.setAntiAlias(true);
          ring.setStrokeWidth(1.2);
          ring.setColor(Skia.Color(`rgba(255,255,255,${0.75 * satFade})`));
          canvas.drawCircle(p.x, p.y, sr * 1.55, ring);
        }
      }

      profAdd(scene, 1, s0);
      // Gem (with tap squash, urgent tremble and the shatter for the morph).
      const c0 = performance.now();
      const g = gemAt(frame, t);
      const tremble = pal[20] * (1 - t);
      const sq = scene.squash.value;
      const introScale = 0.85 + 0.15 * intro;
      if ((dbg & 4) === 0) drawStone(canvas, low ? coreMeshLow : stoneCoreMesh, {
        cx: g.x + (still ? 0 : tremble * Math.sin(720 * ph)),
        cy: g.y + (still ? 0 : tremble * Math.cos(864 * ph)),
        R: g.r * introScale,
        rotY: still ? 0.8 : 4 * ph,
        tiltX: 0.35 + (still ? 0 : 0.1 * Math.sin(2 * ph)),
        phase: still ? 0 : 4 * ph,
        palette: pal,
        agent: null,
        alpha: intro,
        explode: scene.explode.value,
        glow: 0,
        sx: 2 - sq,
        sy: sq,
        lowPower: low,
      });

      profAdd(scene, 2, c0);
      // Particle morph (gem ↔ agent icons): ring + the cached particle buckets.
      const ms = morphStateOf(scene, frame, ph);
      if (ms.alpha > 0.01) {
        drawMorphRing(canvas, ms);
        const mp = morphPics.value;
        for (let k = 0; k < 3; k++) {
          const pic = mp.pics[k];
          if (pic) canvas.drawPicture(pic);
        }
      }
      drawBurst(canvas, scene.morph.value, scene.burst.value, g.x, g.y, g.r);
      profAdd(scene, 4, p0);
    })
  );

  return (
    <Canvas style={StyleSheet.absoluteFill} pointerEvents="none">
      <Group layer={blurred ? <Paint><Blur blur={8} /></Paint> : undefined}>
        <Fill>
          <Shader source={ambientEffect} uniforms={uniforms} />
        </Fill>
        <Picture picture={picture} />
      </Group>
    </Canvas>
  );
}

export const OrbitSceneCanvas = memo(OrbitSceneView);
