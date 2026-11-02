// Drives the Home stage: one clock, one requestAnimationFrame loop, the
// tweens, the interactive core, and the WebGL scene (loaded lazily, after
// first paint, so the CSS ambient shows at once; AGENT_WEB.md §11.2). DOM
// overlays (satellite labels and hit areas, the Dashboard panel, the text
// layer's fade) subscribe with onFrame() and write their styles directly:
// nothing re-renders in React per frame.
import { createOrbitScene, type OrbitScene } from './sceneState';
import { computeStage, type Stage } from './orbitLayout';
import { applyCoreInput, stepCore } from './coreInput';
import { ease, timing } from './tween';
import { morphData } from './morphData';
import type { Scenario } from '../theme/stateThemes';
import type { GLScene } from './glScene';

export type FrameHook = (e: OrbitEngine, dt: number) => void;

/** Frame-time probe (§7.1, §11.2): skip the intro, then average 2 s of frames. */
const PROBE_SKIP = 40;
const PROBE_FRAMES = 120;
const SLOW_MS = 20;
const VERY_SLOW_MS = 30;

export class OrbitEngine {
  readonly scene: OrbitScene;
  stage: Stage;
  /** WebGL could not start (or was too slow): the CSS/image fallback is shown. */
  fallback = false;
  reduced = false;
  private gl: GLScene | null = null;
  /** The canvas currently attached (kept so resize can be ignored once detached). */
  private canvas: HTMLCanvasElement | null = null;
  private hooks = new Set<FrameHook>();
  private listeners = new Set<() => void>();
  private raf = 0;
  private last = 0;
  private active = true;
  private hidden = typeof document !== 'undefined' && document.hidden;
  private dpr = 1;
  private probe = { n: 0, sum: 0, stage: 0 };
  /** Bumped by attach / detach so a slow attach can't land after a newer one (React StrictMode). */
  private attachToken = 0;
  /** Called when the probe decides the device needs low-power graphics. */
  private onLowPower: (() => void) | null = null;

  setOnLowPower(fn: (() => void) | null) {
    this.onLowPower = fn;
  }

  constructor(initial: Scenario, W: number, H: number) {
    this.scene = createOrbitScene(initial);
    this.stage = computeStage(W, H);
    this.scene.tw.to('intro', timing(1, 1100, ease.outCubic));
  }

  /** Subscribe to fallback / readiness changes (React uses this for the image fallback). */
  subscribe(fn: () => void) {
    this.listeners.add(fn);
    return () => {
      this.listeners.delete(fn);
    };
  }

  private emit() {
    for (const f of this.listeners) f();
  }

  get ready() {
    return !!this.gl;
  }

  async attach(canvas: HTMLCanvasElement) {
    const token = ++this.attachToken;
    this.canvas = canvas;
    document.addEventListener('visibilitychange', this.onVisibility);
    this.hidden = document.hidden;
    if (this.gl || this.fallback) return;
    try {
      // three.js throws if it cannot create a WebGL 2 context.
      const { GLScene } = await import('./glScene');
      if (token !== this.attachToken) return;
      this.gl = new GLScene(canvas);
      this.applySize();
      // Icon point clouds for the particle morph: after first paint, off the critical path.
      const build = () => {
        if (!this.gl) return;
        this.scene.morph = morphData();
        this.gl.setMorph(this.scene.morph);
      };
      if ('requestIdleCallback' in window) window.requestIdleCallback(build, { timeout: 800 });
      else setTimeout(build, 400);
    } catch (err) {
      console.warn('[FamilyOS] WebGL unavailable, showing the still crystal.', err);
      this.fallback = true;
    }
    this.emit();
    this.kick();
  }

  detach() {
    this.attachToken++;
    this.stop();
    this.gl?.dispose();
    this.gl = null;
    this.canvas = null;
    document.removeEventListener('visibilitychange', this.onVisibility);
  }

  /** Viewport changes update the camera and buffers only; the context is never recreated (§11.1). */
  resize(W: number, H: number) {
    this.stage = computeStage(W, H);
    this.emit();
    if (!this.canvas) return;
    this.applySize();
    this.kick();
  }

  private applySize() {
    if (!this.gl) return;
    const { W, H } = this.stage;
    const cap = this.scene.lowPower ? 1.5 : 2;
    let dpr = Math.min(window.devicePixelRatio || 1, cap);
    // Keep the ambient field under ~8 M shaded pixels on very large screens.
    const px = W * H * dpr * dpr;
    if (px > 8.3e6) dpr = Math.max(1, Math.sqrt(8.3e6 / (W * H)));
    this.dpr = dpr;
    this.gl.setSize(W, H, dpr);
  }

  setLowPower(v: boolean) {
    if (this.scene.lowPower === v) return;
    this.scene.lowPower = v;
    this.applySize();
    this.kick();
  }

  setReduced(v: boolean) {
    this.reduced = v;
    this.scene.still = v;
    this.kick();
  }

  /** Run the loop only while Home is on screen (route active, tab visible). */
  setActive(v: boolean) {
    this.active = v;
    if (v) this.kick();
    else this.stop();
  }

  onFrame(fn: FrameHook) {
    this.hooks.add(fn);
    this.kick();
    return () => {
      this.hooks.delete(fn);
    };
  }

  /** Make sure a frame is scheduled. */
  kick() {
    if (this.raf || !this.active || this.hidden) return;
    this.last = 0;
    this.raf = requestAnimationFrame(this.tick);
  }

  private stop() {
    if (this.raf) cancelAnimationFrame(this.raf);
    this.raf = 0;
  }

  private onVisibility = () => {
    this.hidden = document.hidden;
    if (this.hidden) this.stop();
    else this.kick();
  };

  private tick = (now: number) => {
    this.raf = 0;
    const rawDt = this.last ? now - this.last : 16;
    this.last = now;
    const dt = Math.min(rawDt, 50) / 1000;
    const s = this.scene;
    s.clock += dt;
    s.tw.step(dt);
    applyCoreInput(s, this.stage, this.reduced);
    stepCore(s, dt, this.reduced);
    if (this.gl && !this.gl.contextLost) this.gl.render(s, this.stage);
    for (const h of this.hooks) h(this, dt);
    this.probeFrame(rawDt);
    if (this.active && !this.hidden) this.raf = requestAnimationFrame(this.tick);
  };

  /**
   * lowPowerGraphics (§11.2): if the first 2 s after the intro average slower
   * than ~50 fps, switch to fewer facets and particles; if even that stays
   * slower than ~33 fps, fall back to the still crystal image.
   */
  private probeFrame(ms: number) {
    const p = this.probe;
    if (!this.gl || p.stage >= 2 || this.reduced) return;
    p.n += 1;
    if (p.n <= PROBE_SKIP) return;
    p.sum += Math.min(ms, 100);
    if (p.n < PROBE_SKIP + PROBE_FRAMES) return;
    const avg = p.sum / PROBE_FRAMES;
    p.n = 0;
    p.sum = 0;
    if (p.stage === 0) {
      p.stage = avg > SLOW_MS ? 1 : 2;
      if (avg > SLOW_MS) {
        this.setLowPower(true);
        this.onLowPower?.();
      }
    } else {
      p.stage = 2;
      if (avg > VERY_SLOW_MS) {
        this.gl.dispose();
        this.gl = null;
        this.fallback = true;
        this.emit();
      }
    }
  }

  get pixelRatio() {
    return this.dpr;
  }
}
