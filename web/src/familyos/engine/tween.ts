// A tiny animation runner for the render loop: the web stand-in for
// Reanimated's withTiming / withSpring / withSequence / withRepeat /
// withDelay on the mobile app's shared values. Values live in a plain
// number record; the loop calls step() once per frame, so nothing here
// touches React.

export type Easing = (t: number) => number;

export const ease = {
  linear: (t: number) => t,
  inOutCubic: (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2),
  outCubic: (t: number) => 1 - Math.pow(1 - t, 3),
  inCubic: (t: number) => t * t * t,
  inOutSine: (t: number) => -(Math.cos(Math.PI * t) - 1) / 2,
};

export type Step =
  | { timing: number; to: number; easing?: Easing; delay?: number }
  | { spring: { stiffness: number; damping: number; mass: number }; to: number; delay?: number };

interface Running {
  steps: Step[];
  i: number;
  repeat: boolean;
  /** Time spent in the current step (s), including its delay. */
  t: number;
  from: number;
  v: number;
  onDone?: () => void;
}

export const timing = (to: number, ms: number, easing: Easing = ease.inOutCubic, delayMs = 0): Step => ({
  timing: ms / 1000,
  to,
  easing,
  delay: delayMs / 1000,
});

export const spring = (to: number, s: { stiffness: number; damping: number; mass: number }, delayMs = 0): Step => ({
  spring: s,
  to,
  delay: delayMs / 1000,
});

export class Tweens<K extends string> {
  private running = new Map<K, Running>();
  private readonly vals: Record<K, number>;

  constructor(vals: Record<K, number>) {
    this.vals = vals;
  }

  /** Jump to a value, cancelling any animation on it. */
  set(k: K, v: number) {
    this.running.delete(k);
    this.vals[k] = v;
  }

  to(k: K, step: Step, onDone?: () => void) {
    this.start(k, [step], false, onDone);
  }

  seq(k: K, steps: Step[], onDone?: () => void) {
    this.start(k, steps, false, onDone);
  }

  /** Loop the steps until cancelled (Reanimated withRepeat(-1)). */
  loop(k: K, steps: Step[]) {
    this.start(k, steps, true);
  }

  cancel(k: K) {
    this.running.delete(k);
  }

  isRunning(k?: K) {
    return k === undefined ? this.running.size > 0 : this.running.has(k);
  }

  private start(k: K, steps: Step[], repeat: boolean, onDone?: () => void) {
    const prev = this.running.get(k);
    this.running.set(k, { steps, i: 0, repeat, t: 0, from: this.vals[k], v: prev?.v ?? 0, onDone });
  }

  /** Advance every animation by dt seconds. */
  step(dt: number) {
    const done: (() => void)[] = [];
    for (const [k, r] of this.running) {
      let left = dt;
      while (left > 0) {
        const s = r.steps[r.i];
        const delay = s.delay ?? 0;
        if (r.t < delay) {
          const d = Math.min(left, delay - r.t);
          r.t += d;
          left -= d;
          if (r.t < delay) break;
          r.from = this.vals[k];
          continue;
        }
        let finished = false;
        if ('timing' in s) {
          const d = Math.min(left, delay + s.timing - r.t);
          r.t += d;
          left -= d;
          const k01 = s.timing <= 0 ? 1 : Math.min(1, (r.t - delay) / s.timing);
          this.vals[k] = r.from + (s.to - r.from) * (s.easing ?? ease.inOutCubic)(k01);
          r.v = 0;
          finished = k01 >= 1;
        } else {
          // Damped spring, a = (−k·(x − to) − c·v) / m, integrated in ≤ 4 ms substeps.
          const { stiffness, damping, mass } = s.spring;
          let x = this.vals[k];
          let v = r.v;
          let rem = left;
          while (rem > 0) {
            const h = Math.min(rem, 0.004);
            const a = (-stiffness * (x - s.to) - damping * v) / mass;
            v += a * h;
            x += v * h;
            rem -= h;
          }
          left = 0;
          const scale = Math.max(1, Math.abs(s.to));
          if (Math.abs(x - s.to) < 0.0005 * scale && Math.abs(v) < 0.005 * scale) {
            x = s.to;
            v = 0;
            finished = true;
          }
          this.vals[k] = x;
          r.v = v;
        }
        if (!finished) break;
        r.i += 1;
        r.t = 0;
        r.from = this.vals[k];
        if (r.i >= r.steps.length) {
          if (r.repeat) r.i = 0;
          else {
            this.running.delete(k);
            if (r.onDone) done.push(r.onDone);
            break;
          }
        }
      }
    }
    for (const f of done) f();
  }
}
