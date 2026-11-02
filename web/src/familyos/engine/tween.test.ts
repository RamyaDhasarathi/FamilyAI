import { describe, expect, it } from 'vitest';
import { Tweens, ease, spring, timing } from './tween';

const run = (tw: Tweens<'x'>, seconds: number) => {
  for (let t = 0; t < seconds; t += 1 / 60) tw.step(1 / 60);
};

describe('tween runner', () => {
  it('reaches a timing target exactly and calls onDone once', () => {
    const v = { x: 0 };
    const tw = new Tweens(v);
    let done = 0;
    tw.to('x', timing(10, 300, ease.outCubic), () => done++);
    run(tw, 0.15);
    expect(v.x).toBeGreaterThan(0);
    expect(v.x).toBeLessThan(10);
    run(tw, 0.3);
    expect(v.x).toBe(10);
    expect(done).toBe(1);
    expect(tw.isRunning('x')).toBe(false);
  });

  it('honours delays and sequences', () => {
    const v = { x: 1 };
    const tw = new Tweens(v);
    tw.seq('x', [timing(0.9, 100, ease.linear, 100), timing(1, 100, ease.linear)]);
    run(tw, 0.08);
    expect(v.x).toBe(1);
    run(tw, 0.4);
    expect(v.x).toBe(1);
  });

  it('settles a damped spring (mobile "soft" values) on its target', () => {
    const v = { x: 0 };
    const tw = new Tweens(v);
    tw.to('x', spring(1, { stiffness: 120, damping: 22, mass: 1 }));
    run(tw, 3);
    expect(v.x).toBe(1);
    expect(tw.isRunning()).toBe(false);
  });

  it('keeps looping until cancelled', () => {
    const v = { x: 0 };
    const tw = new Tweens(v);
    tw.loop('x', [timing(1, 100), timing(0, 100)]);
    run(tw, 2);
    expect(tw.isRunning('x')).toBe(true);
    tw.cancel('x');
    expect(tw.isRunning('x')).toBe(false);
  });
});
