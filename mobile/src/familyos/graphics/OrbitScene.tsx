// The Home canvas: ambient shader (background, stars, dust halo, satellite
// glow) + one Picture with the satellites, the gem and the particle morph.
// Nothing here re-renders per frame; everything is derived on the UI thread.
import { memo, useEffect } from 'react';
import { AppState, StyleSheet } from 'react-native';
import { Blur, Canvas, Fill, Group, Paint, PaintStyle, Picture, Shader, Skia, createPicture } from '@shopify/react-native-skia';
import { useDerivedValue, useFrameCallback, useReducedMotion } from 'react-native-reanimated';
import { AGENT_IDS, colors, hexToRgb } from '../theme/tokens';
import { ambientEffect } from './ambientShader';
import { coreMesh, coreMeshLow, satelliteMeshes } from './crystalGeometry';
import { drawCrystal } from './crystalRender';
import { drawBurst, drawMorph } from './ParticleMorph';
import { currentPalette, type OrbitScene } from './sceneState';
import { gemAt, loopPhase, satellitePos, satelliteRadius, type Frame } from './orbitLayout';

const AGENT_RGB = AGENT_IDS.map((id) => hexToRgb(colors.agents[id]));
const DUST = hexToRgb(colors.dust);
// Whole-number spin speeds per satellite (turns per ambient loop), alternating direction.
const SAT_SPIN = [5, -6, 7, -5, 6];

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
  const cb = useFrameCallback((info) => {
    const dt = info.timeSincePreviousFrame ?? 16;
    scene.clock.set(scene.clock.get() + Math.min(dt, 50) / 1000);
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
    };
  });

  const picture = useDerivedValue(() =>
    createPicture((canvas) => {
      const ph = loopPhase(scene.clock.value);
      const pal = currentPalette(scene);
      const t = scene.dashT.value;
      const intro = scene.intro.value;
      const low = scene.lowPower.value;
      const still = reduced;

      // Satellites (fade out as the dashboard opens; pop in on app open).
      const satFade = 1 - t;
      if (satFade > 0.01) {
        const sr = satelliteRadius(frame);
        const hl = scene.satHighlight.value;
        for (let i = 0; i < 5; i++) {
          const pop = Math.min(1, Math.max(0, intro * 6 - i * 0.6 - 0.4));
          if (pop <= 0) continue;
          const p = satellitePos(frame, i, still ? 0 : ph);
          const dim = hl >= 0 && hl !== i ? 0.6 : 1;
          drawCrystal(canvas, satelliteMeshes[i], {
            cx: p.x,
            cy: p.y,
            R: sr * (0.6 + 0.4 * pop),
            rotY: still || low ? 0.6 + i : SAT_SPIN[i] * ph + i,
            tiltX: 0.5 + 0.25 * Math.sin(2 * ph + i),
            phase: 0,
            palette: pal,
            agent: AGENT_RGB[i],
            alpha: satFade * pop * dim,
            explode: 0,
            glow: hl === i ? 1 : 0,
            sx: 1,
            sy: 1,
            lowPower: low,
          });
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

      // Gem (with tap squash, urgent tremble and the shatter for the morph).
      const g = gemAt(frame, t);
      const tremble = pal[20] * (1 - t);
      const sq = scene.squash.value;
      const introScale = 0.85 + 0.15 * intro;
      drawCrystal(canvas, low ? coreMeshLow : coreMesh, {
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

      // Particle morph (gem ↔ agent icons).
      drawMorph(canvas, scene.morph.value, {
        from: scene.morphFrom.value,
        to: scene.morphTo.value,
        t: scene.morphT.value,
        alpha: scene.morphAlpha.value,
        colFrom: scene.morphColFrom.value,
        colTo: scene.morphColTo.value,
        cx: g.x,
        cy: g.y,
        R: g.r,
        ph,
        lowPower: low,
      });
      drawBurst(canvas, scene.morph.value, scene.burst.value, g.x, g.y, g.r);
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
