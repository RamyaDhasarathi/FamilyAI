/* Orbit: the drawn layer. Canvas 2D, no libraries.
   Ambient   -- the pitch-black root's slow dust and volumetric haze.
   Field     -- the household's avatar at the centre, the five orbits around
                it, the fused branches, and where each orb and each orbital
                notification sits this frame. The page reads the positions
                back and moves its buttons there, so every orb stays a real,
                focusable control. */

const TAU = Math.PI * 2;
const STATUS_RGB = { red: [255, 69, 58], amber: [255, 176, 32], calm: [52, 211, 153] };

function rgba(rgb, a) { return 'rgba(' + rgb[0] + ',' + rgb[1] + ',' + rgb[2] + ',' + a + ')'; }
function hexRgb(hex) {
  const h = hex.replace('#', '');
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
}
function easeOutBack(p) { const c1 = 1.70158, c3 = c1 + 1; return 1 + c3 * Math.pow(p - 1, 3) + c1 * Math.pow(p - 1, 2); }
function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

function fitCanvas(canvas) {
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const r = canvas.getBoundingClientRect();
  const w = Math.max(1, Math.round(r.width)), h = Math.max(1, Math.round(r.height));
  if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
    canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
  }
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { ctx, w, h };
}

/* ── ambient background ───────────────────────────────────────── */

export class Ambient {
  constructor(canvas) {
    this.canvas = canvas;
    this.seg = 'adult';
    this.parts = [];
    this.seed();
  }
  setSeg(seg) { if (seg !== this.seg) { this.seg = seg; this.seed(); } }
  seed() {
    const n = this.seg === 'senior' ? 18 : this.seg === 'kid' ? 70 : 54;
    this.parts = Array.from({ length: n }, () => ({
      x: Math.random(), y: Math.random(), z: 0.3 + Math.random() * 0.7,
      vx: (Math.random() - 0.5) * 0.004, vy: -0.002 - Math.random() * 0.006,
      tw: Math.random() * TAU,
    }));
  }
  palette() {
    if (this.seg === 'kid') return [[0, 229, 255], [255, 43, 214]];
    if (this.seg === 'teen') return [[124, 58, 237], [57, 255, 20]];
    if (this.seg === 'senior') return [[255, 170, 40], [255, 120, 30]];
    return [[20, 120, 140], [90, 70, 170]];
  }
  frame(t, dt) {
    const { ctx, w, h } = fitCanvas(this.canvas);
    ctx.globalCompositeOperation = 'source-over';
    ctx.fillStyle = '#000';
    ctx.fillRect(0, 0, w, h);
    const [c1, c2] = this.palette();
    const s = t / 1000;
    // Two slow volumetric washes, very faint, drifting on long periods.
    const haze = (cx, cy, rad, col, a) => {
      const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, rad);
      g.addColorStop(0, rgba(col, a)); g.addColorStop(1, rgba(col, 0));
      ctx.fillStyle = g; ctx.fillRect(0, 0, w, h);
    };
    if (this.seg !== 'senior') {
      haze(w * (0.3 + 0.12 * Math.sin(s * 0.05)), h * (0.35 + 0.1 * Math.cos(s * 0.04)), Math.max(w, h) * 0.6, c1, 0.10);
      haze(w * (0.75 + 0.1 * Math.cos(s * 0.03)), h * (0.75 + 0.08 * Math.sin(s * 0.05)), Math.max(w, h) * 0.55, c2, 0.08);
    }
    // Dust.
    ctx.globalCompositeOperation = 'lighter';
    const step = Math.min(dt || 16, 50) / 16;
    for (const p of this.parts) {
      p.x += p.vx * 0.06 * step * p.z; p.y += p.vy * 0.06 * step * p.z;
      if (p.y < -0.02) { p.y = 1.02; p.x = Math.random(); }
      if (p.x < -0.02) p.x = 1.02; else if (p.x > 1.02) p.x = -0.02;
      const a = (0.10 + 0.18 * p.z) * (0.6 + 0.4 * Math.sin(s * 0.8 + p.tw));
      const col = this.seg === 'senior' ? [255, 200, 120] : p.tw > 3 ? c1.map((v) => Math.min(255, v + 90)) : [200, 220, 255];
      ctx.fillStyle = rgba(col, a.toFixed(3));
      ctx.beginPath(); ctx.arc(p.x * w, p.y * h, 0.6 + p.z * 1.1, 0, TAU); ctx.fill();
    }
    ctx.globalCompositeOperation = 'source-over';
  }
}

/* ── geometry: an icosphere for the faceted stages ───────────── */

function icosphere(subdiv) {
  const p = (1 + Math.sqrt(5)) / 2;
  let v = [[-1, p, 0], [1, p, 0], [-1, -p, 0], [1, -p, 0], [0, -1, p], [0, 1, p], [0, -1, -p], [0, 1, -p], [p, 0, -1], [p, 0, 1], [-p, 0, -1], [-p, 0, 1]];
  let f = [[0, 11, 5], [0, 5, 1], [0, 1, 7], [0, 7, 10], [0, 10, 11], [1, 5, 9], [5, 11, 4], [11, 10, 2], [10, 7, 6], [7, 1, 8],
    [3, 9, 4], [3, 4, 2], [3, 2, 6], [3, 6, 8], [3, 8, 9], [4, 9, 5], [2, 4, 11], [6, 2, 10], [8, 6, 7], [9, 8, 1]];
  const norm = (a) => { const l = Math.hypot(a[0], a[1], a[2]); return [a[0] / l, a[1] / l, a[2] / l]; };
  v = v.map(norm);
  for (let s = 0; s < subdiv; s++) {
    const cache = new Map(), nf = [];
    const mid = (a, b) => {
      const k = a < b ? a + '_' + b : b + '_' + a;
      if (cache.has(k)) return cache.get(k);
      v.push(norm([(v[a][0] + v[b][0]) / 2, (v[a][1] + v[b][1]) / 2, (v[a][2] + v[b][2]) / 2]));
      cache.set(k, v.length - 1); return v.length - 1;
    };
    for (const [a, b, c] of f) { const ab = mid(a, b), bc = mid(b, c), ca = mid(c, a); nf.push([a, ab, ca], [b, bc, ab], [c, ca, bc], [ab, bc, ca]); }
    f = nf;
  }
  const edges = new Set();
  for (const [a, b, c] of f) for (const [x, y] of [[a, b], [b, c], [c, a]]) edges.add(x < y ? x + '_' + y : y + '_' + x);
  return { v, f, e: Array.from(edges).map((k) => k.split('_').map(Number)) };
}
const ICO0 = icosphere(0), ICO1 = icosphere(1);

function rotate(v, ay, ax) {
  const cy = Math.cos(ay), sy = Math.sin(ay), cx = Math.cos(ax), sx = Math.sin(ax);
  const x1 = v[0] * cy + v[2] * sy, z1 = -v[0] * sy + v[2] * cy;
  const y2 = v[1] * cx - z1 * sx, z2 = v[1] * sx + z1 * cx;
  return [x1, y2, z2];
}

/* ── the field ────────────────────────────────────────────────── */

// Each agent rides its own tilted ellipse; all share one angular speed, so
// the five never bunch up.
const ORBITS = [
  { k: 0.80, rot: -0.42 }, { k: 0.88, rot: 0.55 }, { k: 0.74, rot: 0.12 }, { k: 0.92, rot: -0.95 }, { k: 0.84, rot: 1.05 },
];

export class Field {
  constructor(canvas) {
    this.canvas = canvas;
    this.stage = 7;
    this.status = 'calm';
    this.agents = [];
    this.notes = [];
    this.noteBorn = new Map();
    this.reduced = false;
    this.out = { agents: [], notes: [], cx: 0, cy: 0, R: 0 };
    this.glitch = { until: 0, next: 0, slices: [] };
    this.off = document.createElement('canvas');
  }
  configure(o) {
    if (o.stage) this.stage = o.stage;
    if (o.status) this.status = o.status;
    if (o.agents) this.agents = o.agents;
    if (o.notes) {
      const now = performance.now();
      o.notes.forEach((n, i) => { if (!this.noteBorn.has(n.id)) this.noteBorn.set(n.id, now + 500 + i * 140); });
      this.notes = o.notes;
    }
    if (typeof o.reduced === 'boolean') this.reduced = o.reduced;
  }

  speed() { return { 1: 1.2, 2: 1.3, 3: 1.2, 4: 1.6, 5: 1.5, 6: 1.9, 7: 1, 8: 0.35 }[this.stage] || 1; }

  frame(tms) {
    const { ctx, w, h } = fitCanvas(this.canvas);
    ctx.clearRect(0, 0, w, h);
    const t = this.reduced ? 12 : tms / 1000;
    const st = this.stage;
    const cx = w / 2, cy = h / 2;
    const base = Math.min(w * 0.31, h * 0.21, 160);
    const R = st === 8 ? base * 1.18 : st <= 2 ? base * 1.05 : base;
    const maxA = Math.min(w / 2 - 40, h / 2 - 40, R * 1.75);
    const ang = t * 0.11 * this.speed();
    const out = { agents: [], notes: [], cx, cy, R };

    // Orbit tracks.
    this.agents.forEach((ag, i) => {
      const o = st === 8 ? { k: 1, rot: 0 } : ORBITS[i % ORBITS.length];
      const a = maxA * (1 - 0.16 * (ag.tension || 0));
      const b = Math.max(a * o.k, R * 1.12);
      ctx.save(); ctx.translate(cx, cy); ctx.rotate(o.rot);
      ctx.beginPath(); ctx.ellipse(0, 0, a, b, 0, 0, TAU);
      if (st === 8) { ctx.lineWidth = 3; ctx.strokeStyle = 'rgba(255,196,90,0.55)'; }
      else if (st <= 2) { ctx.lineWidth = 2; ctx.setLineDash([2, 9]); ctx.lineCap = 'round'; ctx.strokeStyle = 'rgba(255,255,255,0.22)'; }
      else if (st === 4) { ctx.lineWidth = 1; ctx.strokeStyle = 'rgba(255,43,214,0.22)'; }
      else { ctx.lineWidth = 1; ctx.strokeStyle = ag.tension ? rgba(hexRgb(ag.color), 0.30) : 'rgba(255,255,255,0.13)'; }
      ctx.stroke(); ctx.restore();
      // Evenly spread in screen angle, each riding its own ring: the five never bunch up.
      const phi = ang + (TAU * i) / this.agents.length - Math.PI * 0.8;
      const d = phi - o.rot;
      const r = (a * b) / Math.sqrt(Math.pow(b * Math.cos(d), 2) + Math.pow(a * Math.sin(d), 2));
      const x = cx + r * Math.cos(phi), y = cy + r * Math.sin(phi);
      const depth = Math.sin(phi);
      let jx = 0, jy = 0;
      if (ag.tension && !this.reduced) { jx = Math.sin(t * 47 + i * 3) * 1.3; jy = Math.cos(t * 53 + i * 5) * 1.3; }
      out.agents.push({ x: x + jx, y: y + jy, depth, scale: 0.92 + 0.1 * (depth + 1) / 2 });
    });

    // The fused branches: metaball necks from the core to each orb.
    if (st === 6 || st === 7 || st === 3) this.drawBranches(ctx, cx, cy, R, out.agents, t);

    // The avatar itself.
    ctx.save();
    const draw = { 1: this.spark, 2: this.pod, 3: this.catalyst, 4: this.glitchSynth, 5: this.prism, 6: this.oasis, 7: this.hub, 8: this.solaria }[st] || this.hub;
    draw.call(this, ctx, cx, cy, R, t, w, h);
    ctx.restore();

    // Orbital notifications: snap in from far out, then ride the inner ring.
    const rn = Math.min(R * 1.2, w / 2 - 22);
    if (this.notes.length && st !== 8) {
      ctx.save(); ctx.setLineDash([1, 6]); ctx.strokeStyle = 'rgba(255,255,255,0.10)'; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.arc(cx, cy, rn, 0, TAU); ctx.stroke(); ctx.restore();
    }
    const now = performance.now();
    this.notes.forEach((n, j) => {
      const born = this.noteBorn.get(n.id) || now;
      const p = this.reduced ? 1 : clamp((now - born) / 750, 0, 1);
      const e = p <= 0 ? 0 : easeOutBack(p);
      const r = rn * (1 + 2.6 * (1 - e));
      const th = (TAU * j) / this.notes.length - Math.PI / 2 + t * 0.045 * this.speed();
      out.notes.push({ x: cx + r * Math.cos(th), y: cy + r * Math.sin(th), shown: p > 0, p });
    });
    this.out = out;
    return out;
  }

  /* metaball necks: wide at the core, pinched mid-way, swelling into the orb */
  drawBranches(ctx, cx, cy, R, pos, t) {
    ctx.save(); ctx.globalCompositeOperation = 'lighter';
    pos.forEach((p, i) => {
      const ag = this.agents[i]; if (!ag) return;
      const dx = p.x - cx, dy = p.y - cy, d = Math.hypot(dx, dy);
      if (d < R * 1.05) return;
      const ux = dx / d, uy = dy / d, px = -uy, py = ux;
      const w0 = R * (0.30 + 0.08 * (ag.tension || 0)), w1 = 15 * p.scale;
      const wm = Math.max(2.2, Math.min(w0, w1) * (0.22 + 0.05 * Math.sin(t * 1.3 + i)) + (ag.tension ? 2 : 0));
      const s0x = cx + ux * R * 0.8, s0y = cy + uy * R * 0.8;
      const mx = cx + ux * (R * 0.8 + (d - R * 0.8) * 0.5), my = cy + uy * (R * 0.8 + (d - R * 0.8) * 0.5);
      const col = hexRgb(ag.color);
      const g = ctx.createLinearGradient(s0x, s0y, p.x, p.y);
      const a = ag.tension ? 0.5 : 0.28;
      g.addColorStop(0, rgba(col, a)); g.addColorStop(0.5, rgba(col, a * 0.35)); g.addColorStop(1, rgba(col, a * 0.9));
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.moveTo(s0x + px * w0, s0y + py * w0);
      ctx.quadraticCurveTo(mx + px * wm, my + py * wm, p.x + px * w1, p.y + py * w1);
      ctx.lineTo(p.x - px * w1, p.y - py * w1);
      ctx.quadraticCurveTo(mx - px * wm, my - py * wm, s0x - px * w0, s0y - py * w0);
      ctx.closePath(); ctx.fill();
    });
    ctx.restore();
  }

  halo(ctx, cx, cy, R, mult, alpha) {
    const col = STATUS_RGB[this.status] || STATUS_RGB.calm;
    const g = ctx.createRadialGradient(cx, cy, R * 0.6, cx, cy, R * mult);
    g.addColorStop(0, rgba(col, alpha)); g.addColorStop(1, rgba(col, 0));
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(cx, cy, R * mult, 0, TAU); ctx.fill();
  }

  pulse(t) {
    // Red pulses deep and quick; amber breathes; calm barely moves.
    if (this.status === 'red') return 0.55 + 0.45 * Math.sin(t * 3.2);
    if (this.status === 'amber') return 0.6 + 0.3 * Math.sin(t * 1.6);
    return 0.5 + 0.12 * Math.sin(t * 0.8);
  }

  blobPath(ctx, cx, cy, R, t, amp, sx = 1, sy = 1) {
    ctx.beginPath();
    const n = 72;
    for (let i = 0; i <= n; i++) {
      const th = (i / n) * TAU;
      const r = R * (1 + amp * (0.55 * Math.sin(2 * th + t * 1.1) + 0.3 * Math.sin(3 * th - t * 1.7 + 1.3) + 0.15 * Math.sin(5 * th + t * 2.3 + 0.7)));
      const x = cx + Math.cos(th) * r * sx, y = cy + Math.sin(th) * r * sy;
      i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
    }
    ctx.closePath();
  }

  conic(ctx, cx, cy, start, stops) {
    if (ctx.createConicGradient) {
      const g = ctx.createConicGradient(start, cx, cy);
      stops.forEach((c, i) => g.addColorStop(i / (stops.length - 1), c));
      return g;
    }
    const g = ctx.createLinearGradient(cx - 100, cy - 100, cx + 100, cy + 100);
    stops.forEach((c, i) => g.addColorStop(i / (stops.length - 1), c));
    return g;
  }

  gloss(ctx, cx, cy, R, a = 0.55) {
    const g = ctx.createRadialGradient(cx - R * 0.38, cy - R * 0.45, 0, cx - R * 0.38, cy - R * 0.45, R * 0.55);
    g.addColorStop(0, 'rgba(255,255,255,' + a + ')'); g.addColorStop(1, 'rgba(255,255,255,0)');
    ctx.fillStyle = g; ctx.beginPath(); ctx.ellipse(cx - R * 0.33, cy - R * 0.42, R * 0.42, R * 0.26, -0.5, 0, TAU); ctx.fill();
  }

  face(ctx, cx, cy, R, t, big) {
    const blink = (t % 4.2) > 4.05 ? 0.12 : 1;
    const ex = R * 0.3, ey = -R * 0.08, er = R * (big ? 0.15 : 0.11);
    ctx.fillStyle = 'rgba(20,10,40,0.9)';
    for (const s of [-1, 1]) {
      ctx.beginPath(); ctx.ellipse(cx + s * ex, cy + ey, er * 0.8, er * blink, 0, 0, TAU); ctx.fill();
      if (blink > 0.5) { ctx.fillStyle = '#fff'; ctx.beginPath(); ctx.arc(cx + s * ex + er * 0.25, cy + ey - er * 0.35, er * 0.28, 0, TAU); ctx.fill(); ctx.fillStyle = 'rgba(20,10,40,0.9)'; }
    }
    ctx.strokeStyle = 'rgba(20,10,40,0.85)'; ctx.lineWidth = Math.max(2, R * 0.05); ctx.lineCap = 'round';
    ctx.beginPath(); ctx.arc(cx, cy + R * 0.12, R * 0.2, 0.15 * Math.PI, 0.85 * Math.PI); ctx.stroke();
    if (big) { ctx.fillStyle = 'rgba(255,110,170,0.45)'; for (const s of [-1, 1]) { ctx.beginPath(); ctx.ellipse(cx + s * R * 0.5, cy + R * 0.14, R * 0.1, R * 0.06, 0, 0, TAU); ctx.fill(); } }
  }

  /* 1 -- The Playful Spark: a fuzzy, bouncy, gelatinous blob with a face */
  spark(ctx, cx, cy, R, t) {
    const bounce = Math.abs(Math.sin(t * 2.2));
    const sy = 1 - 0.07 * (1 - bounce), sx = 1 + 0.07 * (1 - bounce);
    const y = cy - bounce * R * 0.12 + R * 0.06;
    this.halo(ctx, cx, y, R, 1.7, 0.18 * this.pulse(t));
    const fill = this.conic(ctx, cx, y, t * 0.5, ['#7cf8ff', '#ff6bd6', '#ffe36b', '#8b7bff', '#5cffb0', '#7cf8ff']);
    ctx.save();
    ctx.shadowColor = 'rgba(255,120,220,0.8)'; ctx.shadowBlur = R * 0.35;
    for (let k = 3; k >= 0; k--) {
      ctx.globalAlpha = k ? 0.12 : 1;
      this.blobPath(ctx, cx, y, R * (1 + k * 0.05), t * 1.4 + k, 0.09, sx, sy);
      ctx.fillStyle = fill; ctx.fill();
    }
    ctx.restore();
    const inner = ctx.createRadialGradient(cx, y + R * 0.3, R * 0.1, cx, y, R * 1.05);
    inner.addColorStop(0, 'rgba(255,255,255,0.0)'); inner.addColorStop(1, 'rgba(60,20,120,0.35)');
    this.blobPath(ctx, cx, y, R, t * 1.4, 0.09, sx, sy); ctx.fillStyle = inner; ctx.fill();
    this.gloss(ctx, cx, y, R, 0.7);
    this.face(ctx, cx, y, R, t, true);
  }

  /* 2 -- The Adventure Pod: a cartoon buddy of bouncy water, bubbles about */
  pod(ctx, cx, cy, R, t) {
    const wob = Math.sin(t * 3) * 0.04;
    this.halo(ctx, cx, cy, R, 1.65, 0.16 * this.pulse(t));
    for (let i = 0; i < 7; i++) {
      const a = t * (0.6 + i * 0.07) + i * 0.9, rr = R * (1.12 + 0.12 * Math.sin(t + i));
      const bx = cx + Math.cos(a) * rr, by = cy + Math.sin(a) * rr * 0.75, br = R * (0.06 + 0.035 * (i % 3));
      const g = ctx.createRadialGradient(bx - br * 0.3, by - br * 0.3, 0, bx, by, br);
      g.addColorStop(0, 'rgba(255,255,255,0.9)'); g.addColorStop(0.4, 'rgba(120,230,255,0.45)'); g.addColorStop(1, 'rgba(255,90,220,0.15)');
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(bx, by, br, 0, TAU); ctx.fill();
    }
    const fill = this.conic(ctx, cx, cy, -t * 0.4, ['#38e1ff', '#7b8cff', '#ff5fd2', '#ffd36b', '#38e1ff']);
    this.blobPath(ctx, cx, cy, R, t * 2.2, 0.075 + wob, 1 + wob, 1 - wob);
    ctx.save(); ctx.shadowColor = 'rgba(80,200,255,0.7)'; ctx.shadowBlur = R * 0.3; ctx.fillStyle = fill; ctx.globalAlpha = 0.92; ctx.fill(); ctx.restore();
    const shade = ctx.createRadialGradient(cx, cy - R * 0.2, R * 0.2, cx, cy, R * 1.1);
    shade.addColorStop(0, 'rgba(255,255,255,0.05)'); shade.addColorStop(1, 'rgba(20,20,90,0.4)');
    this.blobPath(ctx, cx, cy, R, t * 2.2, 0.075 + wob, 1 + wob, 1 - wob); ctx.fillStyle = shade; ctx.fill();
    this.gloss(ctx, cx, cy, R, 0.6);
    this.face(ctx, cx, cy + R * 0.05, R * 0.9, t, false);
  }

  /* 3 -- The Bio-Kinetic Catalyst: fluid glass-putty, glowing particles */
  catalyst(ctx, cx, cy, R, t) {
    this.halo(ctx, cx, cy, R, 1.7, 0.2 * this.pulse(t));
    const parts = 12;
    const drawParts = (front) => {
      for (let i = 0; i < parts; i++) {
        const a = t * (0.5 + (i % 4) * 0.12) + i * 2.1, tilt = 0.4 + (i % 3) * 0.5;
        const z = Math.sin(a); if ((z > 0) !== front) continue;
        const ex = Math.cos(a) * R * (1.25 + (i % 3) * 0.1), ey = Math.sin(a) * R * 0.35;
        const x = cx + ex * Math.cos(tilt) - ey * Math.sin(tilt), y = cy + ex * Math.sin(tilt) + ey * Math.cos(tilt);
        const col = [[255, 120, 80], [80, 220, 255], [255, 90, 200], [160, 255, 120]][i % 4];
        const g = ctx.createRadialGradient(x, y, 0, x, y, 7); g.addColorStop(0, rgba(col, 0.95)); g.addColorStop(1, rgba(col, 0));
        ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, 7, 0, TAU); ctx.fill();
      }
    };
    drawParts(false);
    this.blobPath(ctx, cx, cy, R, t, 0.07);
    const body = ctx.createRadialGradient(cx, cy, R * 0.2, cx, cy, R * 1.1);
    body.addColorStop(0, '#2a1650'); body.addColorStop(1, '#130a26');
    ctx.fillStyle = body; ctx.fill();
    ctx.save(); this.blobPath(ctx, cx, cy, R, t, 0.07); ctx.clip();
    ctx.globalCompositeOperation = 'lighter';
    [[255, 110, 70], [70, 210, 255], [255, 70, 190], [255, 210, 60]].forEach((col, i) => {
      const x = cx + Math.cos(t * 0.7 + i * 1.6) * R * 0.45, y = cy + Math.sin(t * 0.9 + i * 2.2) * R * 0.4;
      const g = ctx.createRadialGradient(x, y, 0, x, y, R * 0.7); g.addColorStop(0, rgba(col, 0.75)); g.addColorStop(1, rgba(col, 0));
      ctx.fillStyle = g; ctx.fillRect(cx - R * 1.2, cy - R * 1.2, R * 2.4, R * 2.4);
    });
    ctx.restore();
    this.blobPath(ctx, cx, cy, R, t, 0.07); ctx.strokeStyle = 'rgba(255,255,255,0.35)'; ctx.lineWidth = 1.5; ctx.stroke();
    this.gloss(ctx, cx, cy, R, 0.5);
    drawParts(true);
  }

  /* 4 -- The Glitch Synth: neon ring, acid magenta and cyber blue, spikes, slices */
  glitchSynth(ctx, cx, cy, R, t, w, h) {
    const off = this.off, size = Math.ceil(R * 3.2);
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    if (off.width !== size * dpr) { off.width = size * dpr; off.height = size * dpr; }
    const o = off.getContext('2d'); o.setTransform(dpr, 0, 0, dpr, 0, 0); o.clearRect(0, 0, size, size);
    const ox = size / 2, oy = size / 2;
    const ring = (dx, col) => {
      o.save(); o.globalCompositeOperation = 'lighter';
      o.lineWidth = R * 0.2; o.strokeStyle = col; o.shadowColor = col; o.shadowBlur = R * 0.3;
      o.beginPath(); o.arc(ox + dx, oy, R * 0.72, t * 1.2, t * 1.2 + TAU * 0.82); o.stroke();
      o.lineWidth = R * 0.07; o.beginPath(); o.arc(ox + dx, oy, R * 0.4, -t * 2, -t * 2 + TAU * 0.6); o.stroke();
      o.restore();
    };
    ring(-3, 'rgba(255,43,214,0.85)'); ring(3, 'rgba(0,200,255,0.85)');
    o.save(); o.globalCompositeOperation = 'lighter'; o.lineCap = 'round';
    for (let i = 0; i < 28; i++) {
      const a = (i / 28) * TAU + Math.sin(t * 0.7 + i) * 0.05;
      const len = R * (0.15 + 0.5 * Math.abs(Math.sin(t * 2.3 + i * 7.1)) ** 3);
      const r0 = R * 0.9;
      o.strokeStyle = i % 2 ? 'rgba(255,60,220,0.7)' : 'rgba(40,180,255,0.7)'; o.lineWidth = 1.6;
      o.beginPath(); o.moveTo(ox + Math.cos(a) * r0, oy + Math.sin(a) * r0); o.lineTo(ox + Math.cos(a) * (r0 + len), oy + Math.sin(a) * (r0 + len)); o.stroke();
    }
    o.restore();
    this.halo(ctx, cx, cy, R, 1.6, 0.18 * this.pulse(t));
    // Slice glitch: every couple of seconds a few bands jump sideways.
    const now = t;
    if (!this.reduced && now > this.glitch.next) {
      this.glitch.until = now + 0.18; this.glitch.next = now + 1.4 + Math.random() * 2.2;
      this.glitch.slices = Array.from({ length: 4 }, () => ({ y: Math.random() * size, h: 4 + Math.random() * 18, dx: (Math.random() - 0.5) * R * 0.5 }));
    }
    const x0 = cx - size / 2, y0 = cy - size / 2;
    ctx.drawImage(off, x0, y0, size, size);
    if (now < this.glitch.until) {
      for (const s of this.glitch.slices) {
        ctx.clearRect(x0, y0 + s.y, size, s.h);
        ctx.drawImage(off, 0, s.y * dpr, size * dpr, s.h * dpr, x0 + s.dx, y0 + s.y, size, s.h);
      }
    }
  }

  /* 5 -- The Kinetic Prism: faceted glass in glowing wireframe */
  prism(ctx, cx, cy, R, t) {
    this.halo(ctx, cx, cy, R, 1.6, 0.2 * this.pulse(t));
    const wire = (mesh, rr, ay, ax, colA, colB, lw) => {
      const p = mesh.v.map((v) => rotate(v, ay, ax));
      ctx.save(); ctx.globalCompositeOperation = 'lighter'; ctx.lineWidth = lw;
      for (const [a, b] of mesh.e) {
        const z = (p[a][2] + p[b][2]) / 2;
        ctx.strokeStyle = z > 0 ? colA : colB;
        ctx.beginPath(); ctx.moveTo(cx + p[a][0] * rr, cy + p[a][1] * rr); ctx.lineTo(cx + p[b][0] * rr, cy + p[b][1] * rr); ctx.stroke();
      }
      for (const v of p) { if (v[2] < 0) continue; ctx.fillStyle = colA; ctx.beginPath(); ctx.arc(cx + v[0] * rr, cy + v[1] * rr, 2, 0, TAU); ctx.fill(); }
      ctx.restore();
      return p;
    };
    const p = ICO0.v.map((v) => rotate(v, t * 0.5, 0.5 + Math.sin(t * 0.3) * 0.2));
    // Faces: thin faceted glass.
    ICO0.f.forEach(([a, b, c]) => {
      const z = (p[a][2] + p[b][2] + p[c][2]) / 3; if (z < 0) return;
      ctx.fillStyle = 'rgba(120,80,255,' + (0.05 + 0.1 * z).toFixed(3) + ')';
      ctx.beginPath(); ctx.moveTo(cx + p[a][0] * R, cy + p[a][1] * R); ctx.lineTo(cx + p[b][0] * R, cy + p[b][1] * R); ctx.lineTo(cx + p[c][0] * R, cy + p[c][1] * R); ctx.closePath(); ctx.fill();
    });
    wire(ICO0, R * 0.55, -t * 0.9, 0.3, 'rgba(0,229,255,0.9)', 'rgba(0,229,255,0.25)', 1.2);
    ctx.save(); ctx.shadowColor = 'rgba(255,60,230,0.9)'; ctx.shadowBlur = 12;
    wire(ICO0, R, t * 0.5, 0.5 + Math.sin(t * 0.3) * 0.2, 'rgba(255,90,240,0.95)', 'rgba(140,90,255,0.3)', 1.6);
    ctx.restore();
  }

  /* 6 -- The Digital Oasis: symmetrical iridescent fluid glass, fast satellites */
  oasis(ctx, cx, cy, R, t) {
    this.halo(ctx, cx, cy, R, 1.7, 0.22 * this.pulse(t));
    const rings = [{ rx: 1.45, ry: 0.34, rot: -0.35, sp: 1.6 }, { rx: 1.3, ry: 0.22, rot: 0.5, sp: -2.1 }];
    const ringHalf = (r, back) => {
      ctx.save(); ctx.translate(cx, cy); ctx.rotate(r.rot);
      ctx.strokeStyle = back ? 'rgba(180,200,255,0.18)' : 'rgba(200,220,255,0.5)'; ctx.lineWidth = back ? 1 : 1.6;
      ctx.beginPath(); ctx.ellipse(0, 0, R * r.rx, R * r.ry, 0, back ? Math.PI : 0, back ? TAU : Math.PI); ctx.stroke();
      const a = t * r.sp, sz = Math.sin(a);
      if ((sz < 0) === back) {
        ctx.fillStyle = '#fff'; ctx.shadowColor = '#9be7ff'; ctx.shadowBlur = 12;
        ctx.beginPath(); ctx.arc(Math.cos(a) * R * r.rx, Math.sin(a) * R * r.ry, 3.5, 0, TAU); ctx.fill();
      }
      ctx.restore();
    };
    rings.forEach((r) => ringHalf(r, true));
    this.blobPath(ctx, cx, cy, R, t * 1.6, 0.035);
    ctx.fillStyle = this.conic(ctx, cx, cy, t * 0.8, ['#64f0ff', '#a07bff', '#ff7ad9', '#ffd66b', '#7dffb7', '#64f0ff']);
    ctx.globalAlpha = 0.85; ctx.fill(); ctx.globalAlpha = 1;
    const depth = ctx.createRadialGradient(cx + R * 0.15, cy + R * 0.2, R * 0.1, cx, cy, R * 1.05);
    depth.addColorStop(0, 'rgba(10,10,30,0.55)'); depth.addColorStop(0.7, 'rgba(10,10,30,0.15)'); depth.addColorStop(1, 'rgba(255,255,255,0.25)');
    this.blobPath(ctx, cx, cy, R, t * 1.6, 0.035); ctx.fillStyle = depth; ctx.fill();
    this.gloss(ctx, cx, cy, R, 0.65);
    rings.forEach((r) => ringHalf(r, false));
  }

  /* 7 -- The Quantum Glass Hub: a multi-faceted frosted glass core, iridescent
     bioluminescent activity inside, the status glowing from its centre */
  hub(ctx, cx, cy, R, t) {
    const pulse = this.pulse(t);
    this.halo(ctx, cx, cy, R, 1.6, 0.10 + 0.16 * pulse);
    const ay = t * 0.1, ax = 0.42 + Math.sin(t * 0.21) * 0.08;
    const pts = ICO1.v.map((v, i) => { const s = 1 + 0.02 * Math.sin(t * 0.9 + i * 1.7); return rotate([v[0] * s, v[1] * s, v[2] * s], ay, ax); });
    // Frosted glass body: darker in the middle, bright towards the rim.
    const body = ctx.createRadialGradient(cx, cy, R * 0.1, cx, cy, R);
    body.addColorStop(0, 'rgba(40,46,60,0.9)'); body.addColorStop(0.6, 'rgba(110,120,140,0.55)'); body.addColorStop(1, 'rgba(225,232,245,0.85)');
    ctx.fillStyle = body; ctx.beginPath(); ctx.arc(cx, cy, R * 0.99, 0, TAU); ctx.fill();
    // Bioluminescent activity: each agent's colour drifts inside, brighter with work.
    ctx.save(); ctx.beginPath(); ctx.arc(cx, cy, R * 0.97, 0, TAU); ctx.clip();
    ctx.globalCompositeOperation = 'lighter';
    const ags = (this.agents.length ? this.agents : [{ color: '#2dd4bf' }, { color: '#b9a5ff' }, { color: '#ffb547' }, { color: '#5cc8ff' }, { color: '#7ef2b1' }])
      .concat([{ color: '#ff4fd8', badge: 2 }, { color: '#3cff9e', badge: 2 }]);
    ags.forEach((ag, i) => {
      const k = 0.55 + Math.min(1, (ag.badge || 0) / 4) * 0.45;
      const x = cx + Math.cos(t * (0.33 + i * 0.06) + i * 1.3) * R * 0.42, y = cy + Math.sin(t * (0.41 + i * 0.05) + i * 2.1) * R * 0.4;
      const g = ctx.createRadialGradient(x, y, 0, x, y, R * 0.4);
      g.addColorStop(0, rgba(hexRgb(ag.color), 0.5 * k)); g.addColorStop(1, rgba(hexRgb(ag.color), 0));
      ctx.fillStyle = g; ctx.fillRect(cx - R, cy - R, R * 2, R * 2);
    });
    if (this.status !== 'calm' || true) {
      const status = STATUS_RGB[this.status] || STATUS_RGB.calm;
      const core = ctx.createRadialGradient(cx, cy, 0, cx, cy, R * 0.6);
      const ca = this.status === 'calm' ? 0.22 : 0.6 * pulse;
      core.addColorStop(0, rgba(status, ca)); core.addColorStop(1, rgba(status, 0));
      ctx.fillStyle = core; ctx.fillRect(cx - R, cy - R, R * 2, R * 2);
    }
    ctx.restore();
    // Back facet lines show faintly through the glass.
    ctx.lineWidth = 0.7;
    for (const [a, b, c] of ICO1.f) {
      const z = (pts[a][2] + pts[b][2] + pts[c][2]) / 3; if (z >= 0) continue;
      ctx.strokeStyle = 'rgba(230,240,255,0.10)';
      ctx.beginPath(); ctx.moveTo(cx + pts[a][0] * R, cy + pts[a][1] * R); ctx.lineTo(cx + pts[b][0] * R, cy + pts[b][1] * R); ctx.lineTo(cx + pts[c][0] * R, cy + pts[c][1] * R); ctx.closePath(); ctx.stroke();
    }
    // Front facets: frosted, crystalline, lit from the upper left.
    const light = [-0.45, -0.6, 0.66];
    for (const [a, b, c] of ICO1.f) {
      const A = pts[a], B = pts[b], C = pts[c];
      const z = (A[2] + B[2] + C[2]) / 3; if (z < 0) continue;
      const ux = B[0] - A[0], uy = B[1] - A[1], uz = B[2] - A[2], vx = C[0] - A[0], vy = C[1] - A[1], vz = C[2] - A[2];
      let nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx; const nl = Math.hypot(nx, ny, nz) || 1; nx /= nl; ny /= nl; nz /= nl;
      if (nz < 0) { nx = -nx; ny = -ny; nz = -nz; }
      const lam = Math.max(0, nx * light[0] + ny * light[1] + nz * light[2]);
      ctx.beginPath(); ctx.moveTo(cx + A[0] * R, cy + A[1] * R); ctx.lineTo(cx + B[0] * R, cy + B[1] * R); ctx.lineTo(cx + C[0] * R, cy + C[1] * R); ctx.closePath();
      // Edge-on facets frost over; facets facing you stay clear so the core shows.
      ctx.fillStyle = 'rgba(225,232,245,' + (0.03 + 0.26 * Math.pow(1 - nz, 1.6) + 0.2 * Math.pow(lam, 4)).toFixed(3) + ')'; ctx.fill();
      ctx.strokeStyle = 'rgba(255,255,255,' + (0.18 + 0.25 * z).toFixed(3) + ')'; ctx.lineWidth = 0.8; ctx.stroke();
    }
    const rim = ctx.createRadialGradient(cx, cy, R * 0.85, cx, cy, R * 1.03);
    rim.addColorStop(0, 'rgba(230,240,255,0)'); rim.addColorStop(1, 'rgba(230,240,255,0.5)');
    ctx.fillStyle = rim; ctx.beginPath(); ctx.arc(cx, cy, R * 1.03, 0, TAU); ctx.fill();
    this.gloss(ctx, cx, cy, R, 0.35);
  }

  /* 8 -- The Warm Solaria: a large, slow-pulsing amber sun */
  solaria(ctx, cx, cy, R, t) {
    const p = 1 + 0.03 * Math.sin((t * TAU) / 6);
    const r = R * p;
    const corona = ctx.createRadialGradient(cx, cy, r * 0.9, cx, cy, r * 1.9);
    corona.addColorStop(0, 'rgba(255,170,40,0.45)'); corona.addColorStop(1, 'rgba(255,120,20,0)');
    ctx.fillStyle = corona; ctx.beginPath(); ctx.arc(cx, cy, r * 1.9, 0, TAU); ctx.fill();
    if (this.status !== 'calm') {
      // A clear, solid ring says "needs you" without asking anyone to read a glow.
      ctx.strokeStyle = this.status === 'red' ? '#ff453a' : '#ffd60a'; ctx.lineWidth = 5;
      ctx.beginPath(); ctx.arc(cx, cy, r * 1.12, 0, TAU); ctx.stroke();
    }
    const sun = ctx.createRadialGradient(cx - r * 0.3, cy - r * 0.35, r * 0.05, cx, cy, r);
    sun.addColorStop(0, '#fff6d6'); sun.addColorStop(0.35, '#ffd166'); sun.addColorStop(0.8, '#ff9f1c'); sun.addColorStop(1, '#e8700a');
    ctx.fillStyle = sun; ctx.beginPath(); ctx.arc(cx, cy, r, 0, TAU); ctx.fill();
  }
}
