// GLSL (WebGL 2) for the Home stage. Every pass works in CSS-pixel
// coordinates with the origin at the top left, like the mobile app's Skia
// canvas, so the numbers below match the mobile shaders one to one.

/** px → clip space. `uRes` is the canvas size in CSS px. */
const toClip = /* glsl */ `
uniform vec2 uRes;
vec4 toClip(vec2 p) { return vec4(p.x / uRes.x * 2.0 - 1.0, 1.0 - p.y / uRes.y * 2.0, 0.0, 1.0); }
`;

const head = /* glsl */ `precision highp float;\nprecision highp int;\n`;

// ── Ambient: background, stars, dust halo, satellite glow (mobile ambientShader.ts) ──
//
// Seamless looping (design.md §4.1): all motion uses the single loop phase
// `ph` ∈ [0, 2π) with whole-number frequencies, so wrapping ph never jumps.
// Thousands of particles cost nothing per frame on the CPU: every particle is
// generated from a hash of its grid cell.
export const ambientVert = head + toClip + /* glsl */ `
in vec2 position;
out vec2 vPx;
void main() { vPx = position; gl_Position = toClip(position); }
`;

export const ambientFrag = head + /* glsl */ `
in vec2 vPx;
out vec4 fragColor;
uniform vec2 res;
uniform float ph;
uniform vec2 center;
uniform float radius;
uniform vec3 tint;
uniform vec3 corner;
uniform vec3 halo;
uniform float haloAmt;
uniform float dustAmt;
uniform vec3 dustCol;
uniform float starAmt;
uniform vec2 sats[5];
uniform vec3 satCols[5];
uniform float satR;
uniform float satAmt;
uniform float lowPower;
// 1 = transparent background (mini gem over other content): alpha follows brightness.
uniform float clearBg;
// Tap on the core: dust on the touched side is pushed outward by up to pushAmt px.
uniform vec2 pushDir;
uniform float pushAmt;
// Web: overall dim under panels (the canvas stays alive behind them).
uniform float dim;

float hash(vec2 p) {
  p = fract(p * vec2(123.34, 456.21));
  p += dot(p, p + 45.32);
  return fract(p.x * p.y);
}
vec2 hash2(vec2 p) {
  float n = hash(p);
  return vec2(n, hash(p + n + 17.17));
}

// One layer of the dust ring, in polar cells around the gem. Each radial band
// co-rotates at a whole-number speed (inner bands faster); each cell holds at
// most one particle, kept inside its cell so no neighbour lookup is needed.
float dustLayer(vec2 d, float R, float seed, float density) {
  float r = length(d) / R;
  float rr = r - 0.86;
  if (rr < 0.0 || rr > 0.86) return 0.0;
  float band = 0.034;
  float k = floor(rr / band);
  float ringR = 0.86 + (k + 0.5) * band;
  float spin = ph * (k < 6.0 ? 2.0 : 1.0) * (mod(seed, 2.0) < 1.0 ? 1.0 : -1.0);
  float ang = atan(d.y, d.x) - spin;
  float n = floor(6.2831853 * ringR * R / 3.4);
  float cellA = 6.2831853 / n;
  float j = floor(ang / cellA);
  float jm = mod(j, n);
  vec2 h = hash2(vec2(jm + seed * 37.0, k + seed * 11.0));
  // Dense near the gem, thinning outwards; a low-frequency angular wobble
  // keeps the ring uneven like the video.
  float fall = mix(0.72, 0.05, smoothstep(0.0, 0.86, rr));
  float wob = 0.6 + 0.4 * sin(3.0 * jm * cellA + seed * 2.3 + k * 0.7);
  if (h.x > fall * wob * density) return 0.0;
  float pa = (j + 0.2 + 0.6 * h.y) * cellA + spin;
  float pr = (0.86 + (k + 0.2 + 0.6 * fract(h.x * 13.7)) * band) * R;
  vec2 pp = vec2(cos(pa), sin(pa)) * pr;
  float dd = length(d - pp);
  float tw = 0.5 + 0.5 * sin(floor(8.0 + 30.0 * h.y) * ph + h.x * 60.0);
  float size = 0.28 + 0.42 * fract(h.y * 7.31);
  return smoothstep(size + 0.55, size - 0.2, dd) * (0.2 + 0.8 * tw) * (0.35 + 0.65 * fract(h.x * 91.3));
}

void main() {
  vec2 p = vPx;
  float H = max(res.x, res.y);
  vec2 d = p - center;
  float dist = length(d);
  vec3 col = vec3(0.0);

  // Large soft scenario tint behind the gem, plus a faint top-left glow.
  col += tint * exp(-pow(dist / (H * 0.42), 2.0) * 1.7);
  col += corner * exp(-pow(length(p) / (H * 0.5), 2.0) * 2.0) * 0.9;

  // Halo hugging the gem.
  float r = dist / radius;
  col += halo * haloAmt * exp(-pow(max(r - 0.55, 0.0) / 0.62, 2.0)) * 0.42;

  // Star field: one candidate per 36 px cell, drifting on a small closed loop.
  vec2 drift = vec2(cos(ph), sin(2.0 * ph)) * 12.0;
  vec2 sp = p + drift;
  vec2 cell = floor(sp / 36.0);
  vec2 rs = hash2(cell);
  if (rs.x > 0.6) {
    vec2 sc = (cell + 0.15 + 0.7 * hash2(cell + 3.1)) * 36.0;
    float sd = length(sp - sc);
    float tw = 0.5 + 0.5 * sin(floor(4.0 + 20.0 * rs.y) * ph + rs.x * 40.0);
    float sz = 0.4 + 0.7 * rs.y;
    col += vec3(0.75, 0.82, 1.0) * smoothstep(sz + 0.6, sz - 0.3, sd) * tw * (0.15 + 0.45 * rs.y) * starAmt;
  }

  // Dust ring (two interleaved layers; one on low-power devices). Sampling the
  // dust a little closer to the gem makes it appear pushed out.
  vec2 dd = d;
  if (pushAmt > 0.01 && dist > 1.0) {
    vec2 dn = d / dist;
    float w = smoothstep(-0.3, 1.0, dot(dn, pushDir));
    dd = d - dn * pushAmt * w;
  }
  float dust = dustLayer(dd, radius, 1.0, 1.0);
  if (lowPower < 0.5) dust += dustLayer(dd, radius, 2.0, 0.8);
  col += dustCol * dust * dustAmt;

  // Satellites: soft halo + sparkle motes in the agent colour.
  for (int i = 0; i < 5; i++) {
    vec2 sd2 = p - sats[i];
    float sdist = length(sd2);
    if (sdist < satR * 2.6) {
      vec3 c = satCols[i];
      col += c * exp(-pow(sdist / (satR * 1.2), 2.0)) * 0.27 * satAmt;
      if (sdist < satR * 1.05) {
        vec2 mc = floor(sd2 / 3.2);
        vec2 mh = hash2(mc + float(i) * 13.0);
        if (mh.x > 0.62) {
          vec2 mp = (mc + 0.25 + 0.5 * mh) * 3.2;
          float md = length(sd2 - mp);
          float mt = 0.5 + 0.5 * sin(floor(10.0 + 30.0 * mh.y) * ph + mh.x * 50.0);
          col += (c * 0.7 + 0.3) * smoothstep(0.9, 0.0, md) * mt * 0.55 * satAmt;
        }
      }
    }
  }

  // Dither against banding in the soft gradients.
  col += (hash(p) - 0.5) / 255.0;
  col = max(col, vec3(0.0)) * (1.0 - dim);
  if (clearBg > 0.5) {
    // Premultiplied: alpha ≥ every channel, so dark areas become see-through.
    float a = clamp(max(col.r, max(col.g, col.b)) * 1.6, 0.0, 1.0);
    fragColor = vec4(min(col, vec3(a)), a);
  } else {
    fragColor = vec4(col, 1.0);
  }
}
`;

// ── Facets: coloured triangles + glowing edges (mobile edgeGlowEffect) ──
export const facetVert = head + toClip + /* glsl */ `
in vec2 position;
in vec2 bary;
in vec4 aColor;
out vec2 vB;
out vec4 vC;
void main() { vB = bary; vC = aColor; gl_Position = toClip(position); }
`;

export const facetFrag = head + /* glsl */ `
in vec2 vB;
in vec4 vC;
out vec4 fragColor;
uniform float w;
uniform float g;
uniform float gk;
uniform vec4 edgeCol;
void main() {
  float e = min(min(vB.x, vB.y), 1.0 - vB.x - vB.y);
  float line = 1.0 - smoothstep(w * 0.3, w, e);
  float glow = 1.0 - smoothstep(0.0, g, e);
  vec4 edge = edgeCol * min(1.0, line + gk * glow * glow);
  // Skia drawVertices(…, BlendMode.Plus): premultiplied vertex colour + edge.
  fragColor = min(vec4(vC.rgb * vC.a, vC.a) + edge, vec4(1.0));
}
`;

// ── Far wall: a flat tint plus faint edges (mobile backWallEffect) ──
export const wallVert = head + toClip + /* glsl */ `
in vec2 position;
in vec2 bary;
out vec2 vB;
void main() { vB = bary; gl_Position = toClip(position); }
`;

export const wallFrag = head + /* glsl */ `
in vec2 vB;
out vec4 fragColor;
uniform float w;
uniform vec4 fill;
uniform vec4 edge;
void main() {
  float e = min(min(vB.x, vB.y), 1.0 - vB.x - vB.y);
  float line = 1.0 - smoothstep(w * 0.3, w, e);
  fragColor = min(fill + edge * line, vec4(1.0));
}
`;

// ── Quads (inner glow, star glint, rings): a square around a centre ──
export const quadVert = head + toClip + /* glsl */ `
in vec2 position;
uniform vec2 uCenter;
uniform float uHalf;
out vec2 vLocal;
void main() {
  vLocal = position * uHalf;
  gl_Position = toClip(uCenter + vLocal);
}
`;

/** Radial gradient, colour at the centre → transparent at uHalf (additive). */
export const glowFrag = head + /* glsl */ `
in vec2 vLocal;
out vec4 fragColor;
uniform float uHalf;
uniform vec4 uColor;
void main() {
  float d = length(vLocal) / uHalf;
  fragColor = uColor * clamp(1.0 - d, 0.0, 1.0);
}
`;

/** Four-point star: soft disc, two fading rays, bright core, composited white-over. */
export const starFrag = head + /* glsl */ `
in vec2 vLocal;
out vec4 fragColor;
uniform float uL;
uniform float uS;
void main() {
  vec2 q = abs(vLocal);
  float d = length(vLocal);
  float soft = 0.22 * uS * (1.0 - smoothstep(4.0, 5.0, d));
  float h = q.y <= 0.6 ? 0.85 * uS * max(0.0, 1.0 - q.x / uL) : 0.0;
  float v = q.x <= 0.6 ? 0.85 * uS * max(0.0, 1.0 - q.y / uL) : 0.0;
  float core = 0.95 * uS * (1.0 - smoothstep(1.0, 2.0, d));
  float a = 1.0 - (1.0 - soft) * (1.0 - h) * (1.0 - v) * (1.0 - core);
  fragColor = vec4(a, a, a, a);
}
`;

/** Thin anti-aliased circle. */
export const ringFrag = head + /* glsl */ `
in vec2 vLocal;
out vec4 fragColor;
uniform float uRadius;
uniform float uWidth;
uniform vec4 uColor;
void main() {
  float d = abs(length(vLocal) - uRadius);
  float a = 1.0 - smoothstep(uWidth * 0.5 - 0.5, uWidth * 0.5 + 0.5, d);
  fragColor = uColor * a;
}
`;

// ── Round points (glitter) ──
export const pointsVert = head + toClip + /* glsl */ `
in vec2 position;
in float aSize;
in vec4 aColor;
uniform float uDpr;
out vec4 vC;
out float vSize;
void main() {
  vC = aColor;
  vSize = aSize * uDpr + 1.0;
  gl_PointSize = vSize;
  gl_Position = toClip(position);
}
`;

export const pointsFrag = head + /* glsl */ `
in vec4 vC;
in float vSize;
out vec4 fragColor;
void main() {
  // Disc of the requested diameter with a 1 device-px soft edge.
  float r = length(gl_PointCoord - 0.5) * vSize;
  float a = vC.a * (1.0 - smoothstep(vSize * 0.5 - 1.0, vSize * 0.5, r));
  fragColor = vec4(vC.rgb * a, a);
}
`;

// ── Particle morph (mobile ParticleMorph.ts), interpolated in the vertex shader ──
//
// Each particle i owns a point in the source cloud (aA) and the target cloud
// (aB). With the shared progress uT, particle i starts after aDelay of the
// morph and finishes within the remaining 0.65 (stagger), eases in-out cubic
// on its own local progress, and swings sideways by 4l(1−l)·0.3·aSway of the
// path length (zero at both ends, so the targets stay exact). At rest a tiny
// whole-number-frequency shimmer keeps the icon alive.
export const morphVert = head + toClip + /* glsl */ `
in vec2 aA;
in vec2 aB;
in float aDelay;
in float aSway;
in float aPhase;
in float aBucket;
uniform float uT;
uniform float uSa;
uniform float uSb;
uniform vec2 uCenter;
uniform float uR;
uniform float uPh;
uniform float uAlpha;
uniform float uDpr;
out float vA;
void main() {
  vec2 b = aB * uSb;
  vec2 pos = b;
  if (uT < 1.0) {
    vec2 a = aA * uSa;
    float l = clamp((uT - aDelay) / 0.65, 0.0, 1.0);
    float e = l < 0.5 ? 4.0 * l * l * l : 1.0 - pow(-2.0 * l + 2.0, 3.0) / 2.0;
    vec2 d = b - a;
    pos = a + d * e;
    float len2 = dot(d, d);
    if (len2 > 1e-8) {
      float curl = (4.0 * l * (1.0 - l) * 0.3 * aSway) / sqrt(len2);
      pos += vec2(-d.y, d.x) * curl;
    }
  }
  float sP = sin(aPhase);
  float cP = cos(aPhase);
  vec2 shimmer = vec2(0.006 * sin(12.0 * uPh) * cP + 0.006 * cos(12.0 * uPh) * sP,
                      0.006 * cos(10.0 * uPh) * cP - 0.006 * sin(10.0 * uPh) * sP);
  vA = min(1.0, (0.7 + 0.3 * sin(9.0 * uPh + aBucket * 2.1)) * uAlpha);
  gl_PointSize = 2.4 * uDpr + 1.0;
  gl_Position = toClip(uCenter + (pos + shimmer) * uR);
}
`;

export const morphFrag = head + /* glsl */ `
in float vA;
out vec4 fragColor;
uniform vec3 uColor;
uniform float uDpr;
void main() {
  float size = 2.4 * uDpr + 1.0;
  float r = length(gl_PointCoord - 0.5) * size;
  float a = vA * (1.0 - smoothstep(size * 0.5 - 1.0, size * 0.5, r));
  fragColor = vec4(uColor * a, a);
}
`;

/**
 * Celebration burst (mobile drawBurst): particles leave the gem's rim
 * radially and fade. uB runs 1 → 0: travel = 1 − (1 − k)², k = 1 − uB.
 */
export const burstVert = head + toClip + /* glsl */ `
in float aPhase;
in float aDelay;
uniform float uB;
uniform vec2 uCenter;
uniform float uR;
uniform float uDpr;
void main() {
  float k = 1.0 - uB;
  float travel = 1.0 - (1.0 - k) * (1.0 - k);
  float speed = 0.6 + 0.8 * aDelay / 0.35;
  float r = uR * (0.85 + 1.5 * travel * speed);
  gl_PointSize = 2.4 * uDpr + 1.0;
  gl_Position = toClip(uCenter + vec2(cos(aPhase), sin(aPhase)) * r);
}
`;

export const burstFrag = head + /* glsl */ `
out vec4 fragColor;
uniform float uB;
uniform float uDpr;
void main() {
  float size = 2.4 * uDpr + 1.0;
  float r = length(gl_PointCoord - 0.5) * size;
  float a = min(1.0, uB * 1.2) * (1.0 - smoothstep(size * 0.5 - 1.0, size * 0.5, r));
  fragColor = vec4(vec3(170.0, 255.0, 210.0) / 255.0 * a, a);
}
`;
