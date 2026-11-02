// The Home stage in WebGL 2 through three.js (AGENT_WEB.md §7). A plain
// three.js render loop rather than React Three Fiber: the mobile renderer is
// a pixel-space pipeline of CPU-shaded facets (engine/crystalRender.ts), so
// each frame simply uploads a few small vertex buffers and draws ~20 passes
// with raw GLSL 3 shaders. Nothing here touches React.
//
// Draw order, back → front (mobile OrbitScene.tsx): ambient field (background,
// stars, dust halo, satellite glow) → satellites → walkthrough ring → gem far
// wall → inner glow → gem facets → glitter → star glint → morph ring →
// particle morph → celebration burst.
import * as THREE from 'three';
import { AGENT_IDS, colors, hexToRgb } from '../theme/tokens';
import { coreMeshLow, type CrystalMesh } from '../graphics/crystalGeometry';
import { coreMeshV2, satelliteMeshesV2 } from '../graphics/stoneGeometryV2';
import { qMul, qToMat } from '../graphics/coreMotion';
import * as S from './shaders';
import { crystalOut, drawCrystal, PointBatch, type CrystalOut, type CrystalParams, type TriBatch, type WallBatch } from './crystalRender';
import { currentPalette, type OrbitScene } from './sceneState';
import { gemAt, loopPhase, satellitePos, satelliteRadius, type Stage } from './orbitLayout';
import { GEM_SCALE, ICON_SCALE, MORPH_PARTICLES_LOW, type MorphData } from './morphData';

const AGENT_RGB = AGENT_IDS.map((id) => hexToRgb(colors.agents[id]));
const DUST = hexToRgb(colors.dust);
/** Whole-number spin speeds per satellite (turns per ambient loop), alternating direction. */
const SAT_SPIN = [3, -4, 4, -3, 4];

type Blend = 'over' | 'add';

function material(vert: string, frag: string, uniforms: Record<string, THREE.IUniform>, blend: Blend = 'over') {
  const m = new THREE.RawShaderMaterial({
    vertexShader: vert,
    fragmentShader: frag,
    uniforms,
    glslVersion: THREE.GLSL3,
    transparent: true,
    depthTest: false,
    depthWrite: false,
    side: THREE.DoubleSide,
  });
  // Premultiplied source-over, or additive (Skia BlendMode.Plus).
  m.blending = THREE.CustomBlending;
  m.blendEquation = THREE.AddEquation;
  m.blendSrc = THREE.OneFactor;
  m.blendDst = blend === 'add' ? THREE.OneFactor : THREE.OneMinusSrcAlphaFactor;
  m.blendSrcAlpha = THREE.OneFactor;
  m.blendDstAlpha = blend === 'add' ? THREE.OneFactor : THREE.OneMinusSrcAlphaFactor;
  return m;
}

/** Draw order comes from renderOrder; give three.js a fixed bound so it never measures our 2D positions. */
const BOUND = new THREE.Sphere(new THREE.Vector3(), Infinity);
function geometry() {
  const g = new THREE.BufferGeometry();
  g.boundingSphere = BOUND;
  return g;
}

function attr(array: Float32Array, size: number) {
  const a = new THREE.BufferAttribute(array, size);
  a.setUsage(THREE.DynamicDrawUsage);
  return a;
}

/** Upload the first n items of an attribute. */
function upload(a: THREE.BufferAttribute, n: number) {
  a.clearUpdateRanges();
  a.addUpdateRange(0, Math.max(1, n * a.itemSize));
  a.needsUpdate = true;
}

const QUAD = new Float32Array([-1, -1, 1, -1, 1, 1, -1, -1, 1, 1, -1, 1]);

/** A coloured-triangle batch (front faces) bound to a TriBatch. */
class FacetDraw {
  mesh: THREE.Mesh;
  private g = geometry();
  private u: Record<string, THREE.IUniform>;
  constructor(batch: TriBatch, res: THREE.IUniform, order: number) {
    this.g.setAttribute('position', attr(batch.pos, 2));
    this.g.setAttribute('bary', attr(batch.bary, 2));
    this.g.setAttribute('aColor', attr(batch.col, 4));
    this.u = { uRes: res, w: { value: 0 }, g: { value: 0 }, gk: { value: 0 }, edgeCol: { value: new THREE.Vector4() } };
    this.mesh = new THREE.Mesh(this.g, material(S.facetVert, S.facetFrag, this.u));
    this.mesh.frustumCulled = false;
    this.mesh.renderOrder = order;
  }
  update(batch: TriBatch, u: number[]) {
    for (const k of ['position', 'bary', 'aColor']) upload(this.g.getAttribute(k) as THREE.BufferAttribute, batch.n);
    this.g.setDrawRange(0, batch.n);
    this.mesh.visible = batch.n > 0;
    this.u.w.value = u[0];
    this.u.g.value = u[1];
    this.u.gk.value = u[2];
    (this.u.edgeCol.value as THREE.Vector4).set(u[3], u[4], u[5], u[6]);
  }
  dispose() {
    this.g.dispose();
    (this.mesh.material as THREE.Material).dispose();
  }
}

/** The far wall of a crystal, bound to a WallBatch. */
class WallDraw {
  mesh: THREE.Mesh;
  private g = geometry();
  private u: Record<string, THREE.IUniform>;
  constructor(batch: WallBatch, res: THREE.IUniform, order: number) {
    this.g.setAttribute('position', attr(batch.pos, 2));
    this.g.setAttribute('bary', attr(batch.bary, 2));
    this.u = { uRes: res, w: { value: 0 }, fill: { value: new THREE.Vector4() }, edge: { value: new THREE.Vector4() } };
    this.mesh = new THREE.Mesh(this.g, material(S.wallVert, S.wallFrag, this.u));
    this.mesh.frustumCulled = false;
    this.mesh.renderOrder = order;
  }
  update(batch: WallBatch, u: number[]) {
    for (const k of ['position', 'bary']) upload(this.g.getAttribute(k) as THREE.BufferAttribute, batch.n);
    this.g.setDrawRange(0, batch.n);
    this.mesh.visible = batch.n > 0;
    this.u.w.value = u[0];
    (this.u.fill.value as THREE.Vector4).set(u[1], u[2], u[3], u[4]);
    (this.u.edge.value as THREE.Vector4).set(u[5], u[6], u[7], u[8]);
  }
  dispose() {
    this.g.dispose();
    (this.mesh.material as THREE.Material).dispose();
  }
}

/** Round points bound to a PointBatch. */
class PointsDraw {
  obj: THREE.Points;
  private g = geometry();
  constructor(batch: PointBatch, res: THREE.IUniform, dpr: THREE.IUniform, order: number) {
    this.g.setAttribute('position', attr(batch.pos, 2));
    this.g.setAttribute('aSize', attr(batch.size, 1));
    this.g.setAttribute('aColor', attr(batch.col, 4));
    this.obj = new THREE.Points(this.g, material(S.pointsVert, S.pointsFrag, { uRes: res, uDpr: dpr }));
    this.obj.frustumCulled = false;
    this.obj.renderOrder = order;
  }
  update(batch: PointBatch) {
    for (const k of ['position', 'aSize', 'aColor']) upload(this.g.getAttribute(k) as THREE.BufferAttribute, batch.n);
    this.g.setDrawRange(0, batch.n);
    this.obj.visible = batch.n > 0;
  }
  dispose() {
    this.g.dispose();
    (this.obj.material as THREE.Material).dispose();
  }
}

/** A square quad around a centre (glow, star, rings). */
class QuadDraw {
  mesh: THREE.Mesh;
  u: Record<string, THREE.IUniform>;
  constructor(frag: string, res: THREE.IUniform, extra: Record<string, THREE.IUniform>, order: number, blend: Blend = 'over') {
    const g = geometry();
    g.setAttribute('position', new THREE.BufferAttribute(QUAD, 2));
    g.setDrawRange(0, 6);
    this.u = { uRes: res, uCenter: { value: new THREE.Vector2() }, uHalf: { value: 1 }, ...extra };
    this.mesh = new THREE.Mesh(g, material(S.quadVert, frag, this.u, blend));
    this.mesh.frustumCulled = false;
    this.mesh.renderOrder = order;
    this.mesh.visible = false;
  }
  place(x: number, y: number, half: number) {
    (this.u.uCenter.value as THREE.Vector2).set(x, y);
    this.u.uHalf.value = half;
  }
  dispose() {
    this.mesh.geometry.dispose();
    (this.mesh.material as THREE.Material).dispose();
  }
}

/** One crystal's draws: far wall, front facets (+ optional glow and star quads). */
interface CrystalDraws {
  out: CrystalOut;
  wall: WallDraw;
  facets: FacetDraw;
}

/** One mini-gem frame (engine/miniRenderer.ts). */
export interface MiniFrame {
  w: number;
  h: number;
  ambient: {
    ph: number;
    center: [number, number];
    radius: number;
    halo: number[];
    haloAmt: number;
    dustAmt: number;
    dustCol: number[];
    pushDir?: number[];
    pushAmt?: number;
  };
  gem?: { mesh: 'low' | 'full'; params: CrystalParams };
}

export interface GLSceneOptions {
  /** Transparent canvas (mini gems over other content). */
  transparent?: boolean;
  /** Keep the drawing buffer between frames (the offscreen mini renderer copies out of it). */
  preserve?: boolean;
}

/**
 * Owns the WebGL renderer for the Home stage. `render()` draws one frame of
 * an OrbitScene for a Stage.
 */
export class GLScene {
  readonly renderer: THREE.WebGLRenderer;
  private scene = new THREE.Scene();
  private camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
  private res: THREE.IUniform = { value: new THREE.Vector2(1, 1) };
  private dprU: THREE.IUniform = { value: 1 };
  private ambient: THREE.Mesh;
  private ambientU: Record<string, THREE.IUniform>;
  private ambientPos = new Float32Array(12);
  private core: CrystalDraws;
  private coreLow: CrystalDraws;
  private sats: CrystalDraws[];
  private glitterSat = new PointBatch(260);
  private glitterCore = new PointBatch(64);
  private glitterSatDraw: PointsDraw;
  private glitterCoreDraw: PointsDraw;
  private glow: QuadDraw;
  private star: QuadDraw;
  private ringHl: QuadDraw;
  private ringMorph: QuadDraw;
  private morph: THREE.Points | null = null;
  private morphU: Record<string, THREE.IUniform>;
  private morphKey = '';
  private burst: THREE.Points | null = null;
  private burstU: Record<string, THREE.IUniform>;
  private pal: number[] = [];
  private lost = false;

  constructor(canvas: HTMLCanvasElement, opts: GLSceneOptions = {}) {
    this.renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: true,
      alpha: !!opts.transparent,
      premultipliedAlpha: true,
      powerPreference: 'high-performance',
      preserveDrawingBuffer: !!opts.preserve,
    });
    this.renderer.autoClear = true;
    this.renderer.setClearColor(0x000000, opts.transparent ? 0 : 1);
    canvas.addEventListener('webglcontextlost', this.onLost, false);
    canvas.addEventListener('webglcontextrestored', this.onRestored, false);

    // Ambient full-screen quad.
    const ag = geometry();
    ag.setAttribute('position', new THREE.BufferAttribute(this.ambientPos, 2));
    ag.setDrawRange(0, 6);
    this.ambientU = {
      uRes: this.res,
      res: { value: new THREE.Vector2() },
      ph: { value: 0 },
      center: { value: new THREE.Vector2() },
      radius: { value: 100 },
      tint: { value: new THREE.Vector3() },
      corner: { value: new THREE.Vector3() },
      halo: { value: new THREE.Vector3() },
      haloAmt: { value: 0 },
      dustAmt: { value: 0 },
      dustCol: { value: new THREE.Vector3() },
      starAmt: { value: 0 },
      sats: { value: new Float32Array(10) },
      satCols: { value: new Float32Array(15) },
      satR: { value: 1 },
      satAmt: { value: 0 },
      lowPower: { value: 0 },
      clearBg: { value: opts.transparent ? 1 : 0 },
      pushDir: { value: new THREE.Vector2(1, 0) },
      pushAmt: { value: 0 },
      dim: { value: 0 },
    };
    this.ambient = new THREE.Mesh(ag, material(S.ambientVert, S.ambientFrag, this.ambientU));
    this.ambient.frustumCulled = false;
    this.ambient.renderOrder = 0;
    this.scene.add(this.ambient);

    const crystal = (m: CrystalMesh, order: number): CrystalDraws => {
      const out = crystalOut(m);
      const d = { out, wall: new WallDraw(out.back, this.res, order), facets: new FacetDraw(out.front, this.res, order + 2) };
      this.scene.add(d.wall.mesh, d.facets.mesh);
      return d;
    };
    this.sats = satelliteMeshesV2.map((m) => crystal(m, 10));
    this.glitterSatDraw = new PointsDraw(this.glitterSat, this.res, this.dprU, 13);
    this.ringHl = new QuadDraw(S.ringFrag, this.res, { uRadius: { value: 0 }, uWidth: { value: 1.2 }, uColor: { value: new THREE.Vector4() } }, 14);
    this.core = crystal(coreMeshV2, 20);
    this.coreLow = crystal(coreMeshLow, 20);
    this.glow = new QuadDraw(S.glowFrag, this.res, { uColor: { value: new THREE.Vector4() } }, 21, 'add');
    this.glitterCoreDraw = new PointsDraw(this.glitterCore, this.res, this.dprU, 23);
    this.star = new QuadDraw(S.starFrag, this.res, { uL: { value: 1 }, uS: { value: 0 } }, 24);
    this.ringMorph = new QuadDraw(S.ringFrag, this.res, { uRadius: { value: 0 }, uWidth: { value: 1 }, uColor: { value: new THREE.Vector4() } }, 30);
    this.scene.add(this.glitterSatDraw.obj, this.ringHl.mesh, this.glow.mesh, this.glitterCoreDraw.obj, this.star.mesh, this.ringMorph.mesh);
    this.morphU = {
      uRes: this.res, uDpr: this.dprU, uT: { value: 1 }, uSa: { value: 1 }, uSb: { value: 1 }, uCenter: { value: new THREE.Vector2() },
      uR: { value: 1 }, uPh: { value: 0 }, uAlpha: { value: 0 }, uColor: { value: new THREE.Vector3(1, 1, 1) },
    };
    this.burstU = { uRes: this.res, uDpr: this.dprU, uB: { value: 0 }, uCenter: { value: new THREE.Vector2() }, uR: { value: 1 } };
    // Precompile so the first walkthrough doesn't hitch.
    this.renderer.compile(this.scene, this.camera);
  }

  private onLost = (e: Event) => {
    e.preventDefault();
    this.lost = true;
  };
  private onRestored = () => {
    this.lost = false;
    this.morphKey = '';
  };

  get contextLost() {
    return this.lost;
  }

  setSize(W: number, H: number, dpr: number) {
    this.renderer.setPixelRatio(dpr);
    this.renderer.setSize(W, H, false);
    (this.res.value as THREE.Vector2).set(W, H);
    (this.ambientU.res.value as THREE.Vector2).set(W, H);
    this.dprU.value = dpr;
    const p = this.ambientPos;
    p.set([0, 0, W, 0, W, H, 0, 0, W, H, 0, H]);
    (this.ambient.geometry.getAttribute('position') as THREE.BufferAttribute).needsUpdate = true;
  }

  /** Point clouds for the morph and burst (built once after first paint). */
  setMorph(d: MorphData) {
    if (this.morph) return;
    const g = geometry();
    const n = d.n;
    const bucket = new Float32Array(n);
    for (let i = 0; i < n; i++) bucket[i] = i % 3;
    g.setAttribute('aA', attr(new Float32Array(n * 2), 2));
    g.setAttribute('aB', attr(new Float32Array(n * 2), 2));
    g.setAttribute('aDelay', new THREE.BufferAttribute(d.delay, 1));
    g.setAttribute('aSway', new THREE.BufferAttribute(d.sway, 1));
    g.setAttribute('aPhase', new THREE.BufferAttribute(d.phase, 1));
    g.setAttribute('aBucket', new THREE.BufferAttribute(bucket, 1));
    g.setDrawRange(0, n);
    this.morph = new THREE.Points(g, material(S.morphVert, S.morphFrag, this.morphU));
    this.morph.frustumCulled = false;
    this.morph.renderOrder = 31;
    this.morph.visible = false;
    const bg = geometry();
    const m = Math.min(320, n);
    bg.setAttribute('aPhase', new THREE.BufferAttribute(d.phase.slice(0, m), 1));
    bg.setAttribute('aDelay', new THREE.BufferAttribute(d.delay.slice(0, m), 1));
    bg.setDrawRange(0, m);
    this.burst = new THREE.Points(bg, material(S.burstVert, S.burstFrag, this.burstU));
    this.burst.frustumCulled = false;
    this.burst.renderOrder = 32;
    this.burst.visible = false;
    this.scene.add(this.morph, this.burst);
  }

  /** Draw one frame. */
  render(scene: OrbitScene, stage: Stage) {
    if (this.lost) return;
    const v = scene.v;
    const still = scene.still;
    const ph = still ? 0 : loopPhase(scene.clock);
    const pal = currentPalette(scene, this.pal);
    this.pal = pal;
    const t = v.dashT;
    const intro = v.intro;
    const low = scene.lowPower;
    const g = gemAt(stage, t);
    const sr = satelliteRadius(stage);
    const hl = scene.satHighlight;
    const par = scene.parallax;

    // ── Ambient uniforms ──
    const u = this.ambientU;
    const pulseK = Math.max(1, Math.round(72 / pal[19]));
    const pulse = 0.78 + 0.22 * Math.sin(pulseK * loopPhase(scene.clock));
    const satFade = (1 - t) * intro;
    u.ph.value = ph;
    (u.center.value as THREE.Vector2).set(g.x, g.y);
    u.radius.value = g.r;
    (u.tint.value as THREE.Vector3).set(pal[13] * intro, pal[14] * intro, pal[15] * intro);
    (u.corner.value as THREE.Vector3).set(pal[16] * intro, pal[17] * intro, pal[18] * intro);
    (u.halo.value as THREE.Vector3).set(pal[10], pal[11], pal[12]);
    // While particles form an icon, the halo and dust step back so the icon reads.
    u.haloAmt.value = ((still ? 0.9 : pulse) * (1 - 0.75 * v.morphAlpha) + v.listen * 0.9 + v.burst + 0.6 * v.coreFlash) * intro;
    u.dustAmt.value = (1.1 * (1 - 0.6 * v.morphAlpha) + v.burst * 1.5) * intro;
    (u.dustCol.value as THREE.Vector3).set(DUST[0] * 0.75 + pal[10] * 0.25, DUST[1] * 0.75 + pal[11] * 0.25, DUST[2] * 0.75 + pal[12] * 0.25);
    u.starAmt.value = intro;
    const satsU = u.sats.value as Float32Array;
    const colsU = u.satCols.value as Float32Array;
    const satPos: { x: number; y: number }[] = [];
    for (let i = 0; i < 5; i++) {
      const p = satellitePos(stage, i, ph);
      satPos.push(p);
      satsU[i * 2] = p.x + par[0];
      satsU[i * 2 + 1] = p.y + par[1];
      const dim = hl >= 0 && hl !== i ? 0.6 : 1;
      const hov = scene.satHover === i ? 1.35 : 1;
      colsU[i * 3] = AGENT_RGB[i][0] * dim * hov;
      colsU[i * 3 + 1] = AGENT_RGB[i][1] * dim * hov;
      colsU[i * 3 + 2] = AGENT_RGB[i][2] * dim * hov;
    }
    u.satR.value = sr;
    u.satAmt.value = satFade;
    u.lowPower.value = low ? 1 : 0;
    (u.pushDir.value as THREE.Vector2).set(scene.dustPushDir[0], scene.dustPushDir[1]);
    u.pushAmt.value = v.dustPush * (1 - t);
    u.dim.value = 0.45 * v.backdrop;

    // ── Satellites (fade out as the dashboard opens; pop in on load) ──
    this.glitterSat.n = 0;
    for (let i = 0; i < 5; i++) {
      const d = this.sats[i];
      const pop = Math.min(1, Math.max(0, intro * 6 - i * 0.6 - 0.4));
      const a = satFade > 0.01 ? (1 - t) * pop : 0;
      const hov = scene.satHover === i ? 1.12 : 1;
      const s = (0.6 + 0.4 * pop) * hov;
      const p = satPos[i];
      drawCrystal(d.out, this.glitterSat, satelliteMeshesV2[i], {
        cx: p.x + par[0],
        cy: p.y + par[1],
        R: sr * s,
        rotY: still || low ? 0.6 + i : SAT_SPIN[i] * ph + i,
        tiltX: 0.5 + (still ? 0 : 0.25 * Math.sin(2 * ph + i)),
        phase: still ? 0 : ph,
        palette: pal,
        agent: AGENT_RGB[i],
        alpha: a * (hl >= 0 && hl !== i ? 0.6 : 1),
        explode: 0,
        glow: hl === i || scene.satHover === i ? 1 : 0,
        sx: 1,
        sy: 1,
        lowPower: low,
      });
      d.wall.update(d.out.back, d.out.backU);
      d.facets.update(d.out.front, d.out.frontU);
    }
    this.glitterSatDraw.update(this.glitterSat);
    // Thin ring around the satellite being read in a walkthrough.
    if (hl >= 0 && satFade > 0.01) {
      const p = satPos[hl];
      this.ringHl.place(p.x + par[0], p.y + par[1], sr * 1.55 + 2);
      this.ringHl.u.uRadius.value = sr * 1.55;
      (this.ringHl.u.uColor.value as THREE.Vector4).setScalar(0.75 * satFade);
      this.ringHl.mesh.visible = true;
    } else this.ringHl.mesh.visible = false;

    // ── Gem (squash, urgent tremble, hover tilt, shatter for the morph) ──
    const useLow = low;
    const coreD = useLow ? this.coreLow : this.core;
    const other = useLow ? this.core : this.coreLow;
    other.wall.mesh.visible = false;
    other.facets.mesh.visible = false;
    const tremble = pal[20] * (1 - t);
    const sq = v.squash;
    const introScale = 0.85 + 0.15 * intro;
    const rp = scene.ripples;
    const ripples: number[] = [];
    for (let r = 0; r < rp.length; r += 4) ripples.push(rp[r], rp[r + 1], rp[r + 2], scene.clock - rp[r + 3]);
    // Hover tilt (web, §7.1) is applied on top of the orientation, never stored in it.
    const tiltQ = v.tiltX !== 0 || v.tiltY !== 0 ? tiltQuat(v.tiltX, v.tiltY) : null;
    const rot = qToMat(tiltQ ? qMul(tiltQ, scene.orient) : scene.orient);
    const jd = scene.jellyDir;
    const sd = scene.stretchDir;
    const lph = loopPhase(scene.clock);
    const coreP: CrystalParams = {
      rot,
      ripples,
      squash: [jd[0], jd[1], jd[2], v.jelly],
      stretch: [sd[0], sd[1], v.stretch],
      flash: v.coreFlash,
      cx: g.x + (still ? 0 : tremble * Math.sin(720 * lph)),
      cy: g.y + (still ? 0 : tremble * Math.cos(864 * lph)),
      R: g.r * introScale * v.corePulse,
      rotY: 0,
      tiltX: 0,
      phase: still ? 0 : 4 * ph,
      palette: pal,
      agent: null,
      alpha: intro,
      explode: v.explode,
      glow: 0,
      sx: 2 - sq,
      sy: sq,
      lowPower: low,
    };
    this.glitterCore.n = 0;
    drawCrystal(coreD.out, this.glitterCore, useLow ? coreMeshLow : coreMeshV2, coreP);
    coreD.wall.update(coreD.out.back, coreD.out.backU);
    coreD.facets.update(coreD.out.front, coreD.out.frontU);
    this.glitterCoreDraw.update(this.glitterCore);
    const gl = coreD.out.glow;
    if (gl[2] > 0 && coreD.out.front.n > 0) {
      this.glow.place(gl[0], gl[1], gl[2]);
      (this.glow.u.uColor.value as THREE.Vector4).set(gl[3], gl[4], gl[5], gl[6]);
      this.glow.mesh.visible = true;
    } else this.glow.mesh.visible = false;
    const st = coreD.out.star;
    if (st[3] > 0) {
      this.star.place(st[0], st[1], st[2] + 6);
      this.star.u.uL.value = st[2];
      this.star.u.uS.value = st[3];
      this.star.mesh.visible = true;
    } else this.star.mesh.visible = false;

    // ── Particle morph (gem ↔ agent icons) and its faint circular outline ──
    const ma = v.morphAlpha;
    if (this.morph && scene.morph && ma > 0.01) {
      const key = `${scene.morphFrom}>${scene.morphTo}`;
      if (key !== this.morphKey) {
        this.morphKey = key;
        const ga = this.morph.geometry.getAttribute('aA') as THREE.BufferAttribute;
        const gb = this.morph.geometry.getAttribute('aB') as THREE.BufferAttribute;
        (ga.array as Float32Array).set(scene.morph.shapes[scene.morphFrom]);
        (gb.array as Float32Array).set(scene.morph.shapes[scene.morphTo]);
        ga.needsUpdate = true;
        gb.needsUpdate = true;
      }
      const mt = v.morphT;
      const col = morphColour(scene.morphColFrom, scene.morphColTo, mt);
      const m = this.morphU;
      m.uT.value = mt;
      m.uSa.value = scene.morphFrom === 0 ? GEM_SCALE : ICON_SCALE;
      m.uSb.value = scene.morphTo === 0 ? GEM_SCALE : ICON_SCALE;
      (m.uCenter.value as THREE.Vector2).set(g.x, g.y);
      m.uR.value = g.r;
      m.uPh.value = ph;
      m.uAlpha.value = ma;
      (m.uColor.value as THREE.Vector3).set(col[0], col[1], col[2]);
      this.morph.geometry.setDrawRange(0, low ? Math.min(MORPH_PARTICLES_LOW, scene.morph.n) : scene.morph.n);
      this.morph.visible = true;
      const ringA = ma * (scene.morphTo === 0 ? 1 - mt : scene.morphFrom === 0 ? mt : 1) * 0.14;
      if (ringA > 0.002 && !(scene.morphTo === 0 && scene.morphFrom === 0)) {
        this.ringMorph.place(g.x, g.y, g.r * 1.62 + 2);
        this.ringMorph.u.uRadius.value = g.r * 1.62;
        (this.ringMorph.u.uColor.value as THREE.Vector4).set(col[0] * ringA, col[1] * ringA, col[2] * ringA, ringA);
        this.ringMorph.mesh.visible = true;
      } else this.ringMorph.mesh.visible = false;
    } else {
      if (this.morph) this.morph.visible = false;
      this.ringMorph.mesh.visible = false;
    }
    if (this.burst && v.burst > 0.01) {
      this.burstU.uB.value = v.burst;
      (this.burstU.uCenter.value as THREE.Vector2).set(g.x, g.y);
      this.burstU.uR.value = g.r;
      this.burst.visible = true;
    } else if (this.burst) this.burst.visible = false;

    this.renderer.render(this.scene, this.camera);
  }

  /**
   * One mini gem (or a dust-only halo) into the bottom-left w×h CSS-px region
   * of this renderer's canvas, at `dpr`; the caller copies it out at once.
   */
  renderMini(f: MiniFrame, dpr: number) {
    if (this.lost) return false;
    const { w, h } = f;
    const wd = Math.round(w * dpr);
    const hd = Math.round(h * dpr);
    (this.res.value as THREE.Vector2).set(w, h);
    this.dprU.value = dpr;
    this.ambientPos.set([0, 0, w, 0, w, h, 0, 0, w, h, 0, h]);
    (this.ambient.geometry.getAttribute('position') as THREE.BufferAttribute).needsUpdate = true;
    const u = this.ambientU;
    const a = f.ambient;
    (u.res.value as THREE.Vector2).set(w, h);
    u.ph.value = a.ph;
    (u.center.value as THREE.Vector2).set(a.center[0], a.center[1]);
    u.radius.value = a.radius;
    (u.tint.value as THREE.Vector3).set(0, 0, 0);
    (u.corner.value as THREE.Vector3).set(0, 0, 0);
    (u.halo.value as THREE.Vector3).set(a.halo[0], a.halo[1], a.halo[2]);
    u.haloAmt.value = a.haloAmt;
    u.dustAmt.value = a.dustAmt;
    (u.dustCol.value as THREE.Vector3).set(a.dustCol[0], a.dustCol[1], a.dustCol[2]);
    u.starAmt.value = 0;
    u.satAmt.value = 0;
    u.lowPower.value = 1;
    u.clearBg.value = 1;
    (u.pushDir.value as THREE.Vector2).set(a.pushDir?.[0] ?? 1, a.pushDir?.[1] ?? 0);
    u.pushAmt.value = a.pushAmt ?? 0;
    u.dim.value = 0;
    // Only the ambient field and one core: hide everything else.
    for (const d of this.sats) {
      d.wall.mesh.visible = false;
      d.facets.mesh.visible = false;
    }
    this.glitterSatDraw.obj.visible = false;
    for (const q of [this.ringHl, this.ringMorph, this.glow, this.star]) q.mesh.visible = false;
    if (this.morph) this.morph.visible = false;
    if (this.burst) this.burst.visible = false;
    const useLow = f.gem ? f.gem.mesh === 'low' : true;
    const coreD = useLow ? this.coreLow : this.core;
    const other = useLow ? this.core : this.coreLow;
    other.wall.mesh.visible = false;
    other.facets.mesh.visible = false;
    this.glitterCore.n = 0;
    if (f.gem) {
      drawCrystal(coreD.out, this.glitterCore, useLow ? coreMeshLow : coreMeshV2, f.gem.params);
      coreD.wall.update(coreD.out.back, coreD.out.backU);
      coreD.facets.update(coreD.out.front, coreD.out.frontU);
      const gl = coreD.out.glow;
      if (gl[2] > 0) {
        this.glow.place(gl[0], gl[1], gl[2]);
        (this.glow.u.uColor.value as THREE.Vector4).set(gl[3], gl[4], gl[5], gl[6]);
        this.glow.mesh.visible = true;
      }
      const st = coreD.out.star;
      if (st[3] > 0) {
        this.star.place(st[0], st[1], st[2] + 6);
        this.star.u.uL.value = st[2];
        this.star.u.uS.value = st[3];
        this.star.mesh.visible = true;
      }
    } else {
      coreD.wall.mesh.visible = false;
      coreD.facets.mesh.visible = false;
    }
    this.glitterCoreDraw.update(this.glitterCore);
    this.renderer.setScissorTest(true);
    this.renderer.setScissor(0, 0, wd, hd);
    this.renderer.setViewport(0, 0, wd, hd);
    this.renderer.render(this.scene, this.camera);
    return true;
  }

  dispose() {
    const c = this.renderer.domElement;
    c.removeEventListener('webglcontextlost', this.onLost);
    c.removeEventListener('webglcontextrestored', this.onRestored);
    for (const d of [...this.sats, this.core, this.coreLow]) {
      d.wall.dispose();
      d.facets.dispose();
    }
    this.glitterSatDraw.dispose();
    this.glitterCoreDraw.dispose();
    for (const q of [this.glow, this.star, this.ringHl, this.ringMorph]) q.dispose();
    for (const p of [this.morph, this.burst]) {
      if (!p) continue;
      p.geometry.dispose();
      (p.material as THREE.Material).dispose();
    }
    this.ambient.geometry.dispose();
    (this.ambient.material as THREE.Material).dispose();
    this.renderer.dispose();
  }
}

/** Particle colour for the current progress, lifted towards white so dots glow. */
function morphColour(a: number[], b: number[], t: number) {
  return [0, 1, 2].map((i) => Math.min(1, (a[i] + (b[i] - a[i]) * t) * 0.85 + 0.2));
}

/** A small view-space rotation: tilt about x (up/down) then y (left/right). */
function tiltQuat(tx: number, ty: number) {
  const qx = [Math.cos(tx / 2), Math.sin(tx / 2), 0, 0];
  const qy = [Math.cos(ty / 2), 0, Math.sin(ty / 2), 0];
  return qMul(qy, qx);
}
