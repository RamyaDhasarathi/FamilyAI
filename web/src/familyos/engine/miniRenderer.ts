// The second (and last) WebGL context (AGENT_WEB.md §7.1): one offscreen
// renderer shared by every mini gem on screen (Dashboard on phones uses the
// Home stage instead). Each frame it renders each visible instance into the
// corner of its canvas and copies the result into that instance's own 2D
// canvas, so any number of mini gems cost one context.
import { GLScene, type MiniFrame } from './glScene';

/** Offscreen buffer size, device px; instances larger than this render at a lower DPR. */
const MAX = 640;

export interface MiniInstance {
  /** The visible 2D canvas this instance draws into. */
  canvas: HTMLCanvasElement;
  /** Skipped while scrolled out of view. */
  visible: boolean;
  frame(dt: number): MiniFrame | null;
  /** 2D drawing under / over the WebGL image (Family header's member dots). */
  before?(ctx: CanvasRenderingContext2D, w: number, h: number): void;
  after?(ctx: CanvasRenderingContext2D, w: number, h: number): void;
}

let gl: GLScene | null = null;
let failed = false;
const instances = new Set<MiniInstance>();
let raf = 0;
let last = 0;

function ensure() {
  if (gl || failed) return;
  try {
    const c = document.createElement('canvas');
    gl = new GLScene(c, { transparent: true, preserve: true });
    gl.renderer.setPixelRatio(1);
    gl.renderer.setSize(MAX, MAX, false);
  } catch (err) {
    console.warn('[FamilyOS] Mini gems fall back to a still image.', err);
    failed = true;
  }
}

export function miniFailed() {
  ensure();
  return failed;
}

export function register(inst: MiniInstance) {
  ensure();
  instances.add(inst);
  if (!raf) {
    last = 0;
    raf = requestAnimationFrame(tick);
  }
  return () => {
    instances.delete(inst);
  };
}

function tick(now: number) {
  raf = 0;
  const dt = Math.min(last ? now - last : 16, 50) / 1000;
  last = now;
  if (gl) {
    const src = gl.renderer.domElement;
    for (const inst of instances) {
      if (!inst.visible) continue;
      const f = inst.frame(dt);
      if (!f) continue;
      const dpr = Math.min(window.devicePixelRatio || 1, 2, MAX / Math.max(f.w, f.h));
      const wd = Math.round(f.w * dpr);
      const hd = Math.round(f.h * dpr);
      const c = inst.canvas;
      if (c.width !== wd || c.height !== hd) {
        c.width = wd;
        c.height = hd;
      }
      if (!gl.renderMini(f, dpr)) continue;
      const ctx = c.getContext('2d');
      if (!ctx) continue;
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, wd, hd);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      inst.before?.(ctx, f.w, f.h);
      // WebGL draws from the bottom-left corner.
      ctx.drawImage(src, 0, MAX - hd, wd, hd, 0, 0, f.w, f.h);
      inst.after?.(ctx, f.w, f.h);
    }
  }
  if (instances.size > 0) raf = requestAnimationFrame(tick);
}
