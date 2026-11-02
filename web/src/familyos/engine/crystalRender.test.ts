import { describe, expect, it } from 'vitest';
import { paletteOf } from '../theme/stateThemes';
import { coreMeshV2, satelliteMeshesV2 } from '../graphics/stoneGeometryV2';
import { crystalOut, drawCrystal, PointBatch, type CrystalParams } from './crystalRender';

const base: CrystalParams = {
  cx: 200, cy: 200, R: 80, rotY: 0.8, tiltX: 0.35, phase: 1.2, palette: paletteOf('calm'), agent: null,
  alpha: 1, explode: 0, glow: 0, sx: 1, sy: 1, lowPower: false,
};

describe('crystal shading (port of mobile crystalRenderV2)', () => {
  it('splits the intact core into far wall and front facets with valid colours', () => {
    const out = crystalOut(coreMeshV2);
    const glitter = new PointBatch(64);
    expect(drawCrystal(out, glitter, coreMeshV2, base)).toBe(true);
    expect(out.front.n % 3).toBe(0);
    expect(out.back.n % 3).toBe(0);
    expect(out.front.n + out.back.n).toBe(coreMeshV2.nf * 3);
    for (let i = 0; i < out.front.n * 4; i++) {
      expect(Number.isFinite(out.front.col[i])).toBe(true);
      expect(out.front.col[i]).toBeGreaterThanOrEqual(0);
      expect(out.front.col[i]).toBeLessThanOrEqual(1);
    }
    for (let i = 0; i < out.front.n * 2; i++) expect(Number.isFinite(out.front.pos[i])).toBe(true);
    expect(out.glow[2]).toBeCloseTo(80 * 0.95);
  });

  it('draws every shard (no far wall, no glitter) while shattered', () => {
    const out = crystalOut(coreMeshV2);
    const glitter = new PointBatch(64);
    drawCrystal(out, glitter, coreMeshV2, { ...base, explode: 0.5 });
    expect(out.back.n).toBe(0);
    expect(glitter.n).toBe(0);
    expect(out.front.n).toBeGreaterThan(0);
  });

  it('shades satellites in their agent colour and draws nothing when invisible', () => {
    const m = satelliteMeshesV2[0];
    const out = crystalOut(m);
    const glitter = new PointBatch(64);
    drawCrystal(out, glitter, m, { ...base, R: 22, agent: [0.12, 0.78, 0.72] });
    expect(out.front.n).toBeGreaterThan(0);
    expect(out.frontU[6]).toBeGreaterThan(0.7);
    expect(drawCrystal(out, glitter, m, { ...base, alpha: 0 })).toBe(false);
    expect(out.front.n).toBe(0);
  });
});
