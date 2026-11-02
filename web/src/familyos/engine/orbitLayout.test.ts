import { describe, expect, it } from 'vitest';
import { bottomBarOffset, computeStage, gemHome, satellitePos, satelliteRadius } from './orbitLayout';

describe('Home stage layout', () => {
  it('uses the mobile formulas unchanged on an upright phone', () => {
    const s = computeStage(390, 844);
    expect(gemHome(s)).toEqual({ x: 195, y: 844 * 0.43, r: 390 * 0.215 });
    expect(satelliteRadius(s)).toBeCloseTo(390 * 0.056);
    expect(satellitePos(s, 0, 0).x).toBeCloseTo(195 + 5 * Math.sin(0), 5);
  });

  const widths = [320, 360, 390, 430, 600, 640, 768, 820, 1024, 1280, 1440, 1680, 1920, 2560];
  const heights = [480, 568, 600, 667, 720, 800, 844, 900, 1024, 1080, 1440];

  it.each(widths.flatMap((w) => heights.map((h) => [w, h])))('keeps satellites off the gem and above the status block at %i×%i', (W, H) => {
    const s = computeStage(W, H);
    const g = gemHome(s);
    const sr = satelliteRadius(s);
    const statusTop = s.bp === 'phone' && H / W >= 1.75 ? H - 14 - 52 - 10 - 105 : H - bottomBarOffset(H) - 52 - 10 - 105;
    for (let i = 0; i < 5; i++) {
      // Worst case over the drift (±5 px x, ±4 px y).
      const p = satellitePos(s, i, 0);
      const d = Math.hypot(p.x - g.x, p.y - g.y) - Math.hypot(5, 4);
      expect(d).toBeGreaterThan(g.r + sr * 0.6);
      // Satellites stay on screen.
      expect(p.x - sr).toBeGreaterThan(-6);
      expect(p.x + sr).toBeLessThan(W + 6);
      expect(p.y - sr).toBeGreaterThan(-6);
      // Lower satellites and their labels clear the status label.
      const labelFoot = p.y + 4 + sr + 4 + (s.labels ? 14 : 0);
      expect(labelFoot).toBeLessThan(statusTop + 12);
    }
    // Finance clears the header where the greeting reaches the centre.
    if (W < 720 && !(s.bp === 'phone' && H / W >= 1.75)) expect(satellitePos(s, 0, 0).y - 4 - sr).toBeGreaterThan(100);
    // The gem never grows past ~560 px across (§7.1).
    expect(g.r * 2).toBeLessThanOrEqual(600);
  });
});
