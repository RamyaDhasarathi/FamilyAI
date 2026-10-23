// Ambient background, dust halo, star field and satellite glow as ONE GPU
// shader (AGENT.md §7.2, §7.5). Thousands of particles cost no per-frame JS:
// every particle is generated procedurally from a hash of its grid cell.
//
// Seamless looping (design.md §4.1): all motion uses the single loop phase
// `ph` ∈ [0, 2π) with whole-number frequencies, so wrapping ph never jumps.
import { Skia } from '@shopify/react-native-skia';

/** Length of the master ambient loop in seconds. The core spins 4× per loop. */
export const AMBIENT_LOOP = 72;

const source = `
uniform float2 res;
uniform float ph;
uniform float2 center;
uniform float radius;
uniform float3 tint;
uniform float3 corner;
uniform float3 halo;
uniform float haloAmt;
uniform float dustAmt;
uniform float3 dustCol;
uniform float starAmt;
uniform float2 sats[5];
uniform float3 satCols[5];
uniform float satR;
uniform float satAmt;
uniform float lowPower;
// 1 = transparent background (mini gem over other content): alpha follows brightness.
uniform float clearBg;
// Tap on the core (AGENT_CORE_AND_FAMILY.md §3.3): dust on the touched side is
// pushed outward by up to pushAmt px, fading towards the far side.
uniform float2 pushDir;
uniform float pushAmt;

float hash(float2 p) {
  p = fract(p * float2(123.34, 456.21));
  p += dot(p, p + 45.32);
  return fract(p.x * p.y);
}
float2 hash2(float2 p) {
  float n = hash(p);
  return float2(n, hash(p + n + 17.17));
}

// One layer of the dust ring, in polar cells around the gem. Each radial band
// co-rotates at a whole-number speed (inner bands faster), each cell holds at
// most one particle, kept inside its cell so no neighbour lookup is needed.
float dustLayer(float2 d, float R, float seed, float density) {
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
  float2 h = hash2(float2(jm + seed * 37.0, k + seed * 11.0));
  // Dense near the gem, thinning outwards; a low-frequency angular wobble
  // keeps the ring uneven like the video.
  float fall = mix(0.72, 0.05, smoothstep(0.0, 0.86, rr));
  float wob = 0.6 + 0.4 * sin(3.0 * jm * cellA + seed * 2.3 + k * 0.7);
  if (h.x > fall * wob * density) return 0.0;
  float pa = (j + 0.2 + 0.6 * h.y) * cellA + spin;
  float pr = (0.86 + (k + 0.2 + 0.6 * fract(h.x * 13.7)) * band) * R;
  float2 pp = float2(cos(pa), sin(pa)) * pr;
  float dd = length(d - pp);
  float tw = 0.5 + 0.5 * sin(floor(8.0 + 30.0 * h.y) * ph + h.x * 60.0);
  float size = 0.28 + 0.42 * fract(h.y * 7.31);
  return smoothstep(size + 0.55, size - 0.2, dd) * (0.2 + 0.8 * tw) * (0.35 + 0.65 * fract(h.x * 91.3));
}

half4 main(float2 p) {
  if (res.x < 2.0) return half4(0.0, 0.0, 0.0, 1.0); // dev profiling: shader off
  float H = max(res.x, res.y);
  float2 d = p - center;
  float dist = length(d);
  float3 col = float3(0.0);

  // Large soft scenario tint behind the gem, plus a faint top-left glow.
  col += tint * exp(-pow(dist / (H * 0.42), 2.0) * 1.7);
  col += corner * exp(-pow(length(p) / (H * 0.5), 2.0) * 2.0) * 0.9;

  // Halo hugging the gem.
  float r = dist / radius;
  col += halo * haloAmt * exp(-pow(max(r - 0.55, 0.0) / 0.62, 2.0)) * 0.42;

  // Star field: one candidate per 36px cell, drifting on a small closed loop.
  float2 drift = float2(cos(ph), sin(2.0 * ph)) * 12.0;
  float2 sp = p + drift;
  float2 cell = floor(sp / 36.0);
  float2 rs = hash2(cell);
  if (rs.x > 0.6) {
    float2 sc = (cell + 0.15 + 0.7 * hash2(cell + 3.1)) * 36.0;
    float sd = length(sp - sc);
    float tw = 0.5 + 0.5 * sin(floor(4.0 + 20.0 * rs.y) * ph + rs.x * 40.0);
    float sz = 0.4 + 0.7 * rs.y;
    col += float3(0.75, 0.82, 1.0) * smoothstep(sz + 0.6, sz - 0.3, sd) * tw * (0.15 + 0.45 * rs.y) * starAmt;
  }

  // Dust ring (two interleaved layers; one on low-power devices).
  // Sampling the dust a little closer to the gem makes it appear pushed out.
  float2 dd = d;
  if (pushAmt > 0.01 && dist > 1.0) {
    float2 dn = d / dist;
    float w = smoothstep(-0.3, 1.0, dot(dn, pushDir));
    dd = d - dn * pushAmt * w;
  }
  float dust = dustLayer(dd, radius, 1.0, 1.0);
  if (lowPower < 0.5) dust += dustLayer(dd, radius, 2.0, 0.8);
  col += dustCol * dust * dustAmt;

  // Satellites: soft halo + sparkle motes in the agent colour.
  for (int i = 0; i < 5; i++) {
    float2 sd2 = p - sats[i];
    float sdist = length(sd2);
    if (sdist < satR * 2.6) {
      float3 c = satCols[i];
      col += c * exp(-pow(sdist / (satR * 1.2), 2.0)) * 0.27 * satAmt;
      if (sdist < satR * 1.05) {
        float2 mc = floor(sd2 / 3.2);
        float2 mh = hash2(mc + float(i) * 13.0);
        if (mh.x > 0.62) {
          float2 mp = (mc + 0.25 + 0.5 * mh) * 3.2;
          float md = length(sd2 - mp);
          float mt = 0.5 + 0.5 * sin(floor(10.0 + 30.0 * mh.y) * ph + mh.x * 50.0);
          col += (c * 0.7 + 0.3) * smoothstep(0.9, 0.0, md) * mt * 0.55 * satAmt;
        }
      }
    }
  }

  // Dither against banding in the soft gradients.
  col += (hash(p) - 0.5) / 255.0;
  col = max(col, float3(0.0));
  if (clearBg > 0.5) {
    // Premultiplied: alpha ≥ every channel, so dark areas become see-through.
    float a = clamp(max(col.r, max(col.g, col.b)) * 1.6, 0.0, 1.0);
    return half4(half3(col), half(a));
  }
  return half4(half3(col), 1.0);
}
`;

export const ambientEffect = Skia.RuntimeEffect.Make(source)!;
if (!ambientEffect) {
  throw new Error('FamilyOS ambient shader failed to compile');
}
