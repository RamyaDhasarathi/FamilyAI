#!/usr/bin/env python3
"""
FamilyOS - 3D Avatar & Home Screen Renderer
===========================================
Procedurally renders the visual concepts from the "FamilyOS Master UI/UX
Architecture & Design Specification" as seamlessly looping animated GIFs
(plus PNG key-frames):

  * 8 life-cycle avatar stages (The Playful Spark -> The Warm Solaria)
  * The Avatar Evolution grid (all 8 stages animating together)
  * The Mature-Adult Home Screen: Quantum Glass Hub core, 5 colour-mapped
    agent satellites (Finance, Education, Household, Grocery, Calendar),
    state-driven tension (Calendar pulls in + vibrates, core glow shifts
    from calm green to amber) and the unified voice/chat FAB.

Everything is generated from code: a small vectorised signed-distance-field
ray-marcher (NumPy) renders the 3D cores; orbits, satellites, sparks and
glows are composited on top with front/back depth ordering, then bloomed,
super-sampled down and quantised to GIF.

Requirements:  pip install numpy pillow
Usage:
    python familyos_3d.py                     # render everything -> ./familyos_output
    python familyos_3d.py --only 7            # a single avatar stage
    python familyos_3d.py --only home         # just the home screen
    python familyos_3d.py --frames 24 --size 256   # quicker preview
"""
import argparse
import base64
import io
import json
import math
import os
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

TAU = 2.0 * math.pi
CAM_Z = 4.0      # camera sits at (0, 0, CAM_Z) looking down -Z
FOCAL = 2.6      # focal length (larger = narrower FOV)
SS = 2           # super-sampling factor (render at 2x, downsample)


# =========================================================================
# Fonts
# =========================================================================
_FONT_DIRS = ["/usr/share/fonts/truetype/dejavu/", "/usr/share/fonts/dejavu/",
              "/Library/Fonts/", "C:/Windows/Fonts/", ""]


def font(size, bold=False, light=False):
    names = (["DejaVuSans-Bold.ttf", "arialbd.ttf"] if bold else
             ["DejaVuSans-ExtraLight.ttf", "DejaVuSans.ttf"] if light else
             ["DejaVuSans.ttf", "arial.ttf"])
    for n in names:
        for d in _FONT_DIRS:
            try:
                return ImageFont.truetype(d + n, size)
            except OSError:
                pass
    return ImageFont.load_default()


# =========================================================================
# Math helpers
# =========================================================================
def norm3(x, y, z):
    l = np.sqrt(x * x + y * y + z * z) + 1e-9
    return x / l, y / l, z / l


def vnorm(v):
    v = np.asarray(v, np.float64)
    return v / np.linalg.norm(v)


def rot(x, y, z, ax=0.0, ay=0.0, az=0.0):
    """Rotate about X, then Y, then Z (scalars or arrays)."""
    if ax:
        c, s = math.cos(ax), math.sin(ax)
        y, z = c * y - s * z, s * y + c * z
    if ay:
        c, s = math.cos(ay), math.sin(ay)
        x, z = c * x + s * z, -s * x + c * z
    if az:
        c, s = math.cos(az), math.sin(az)
        x, y = c * x - s * y, s * x + c * y
    return x, y, z


def rot_inv(x, y, z, ax=0.0, ay=0.0, az=0.0):
    """Exact inverse of rot() - used to move sample points into object space."""
    if az:
        c, s = math.cos(-az), math.sin(-az)
        x, y = c * x - s * y, s * x + c * y
    if ay:
        c, s = math.cos(-ay), math.sin(-ay)
        x, z = c * x + s * z, -s * x + c * z
    if ax:
        c, s = math.cos(-ax), math.sin(-ax)
        y, z = c * y - s * z, s * y + c * z
    return x, y, z


def smin(a, b, k):
    """Polynomial smooth-minimum: the 'metaball' fusion operator."""
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return b * (1 - h) + a * h - k * h * (1 - h)


def sph(x, y, z, cx, cy, cz, r):
    return np.sqrt((x - cx) ** 2 + (y - cy) ** 2 + (z - cz) ** 2) - r


def clamp01(a):
    return np.clip(a, 0.0, 1.0)


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def mix(a, b, t):
    return a + (b - a) * t


def irid(h, sat=1.0):
    """Cosine palette -> thin-film / iridescent rainbow, periodic in h."""
    r = 0.5 + 0.5 * np.cos(TAU * (h + 0.00))
    g = 0.5 + 0.5 * np.cos(TAU * (h + 0.33))
    b = 0.5 + 0.5 * np.cos(TAU * (h + 0.67))
    if sat != 1.0:
        l = (r + g + b) / 3.0
        r, g, b = l + (r - l) * sat, l + (g - l) * sat, l + (b - l) * sat
    return clamp01(r), clamp01(g), clamp01(b)


def fib_sphere(n, jitter=0.0, seed=0):
    i = np.arange(n) + 0.5
    phi = np.arccos(1 - 2 * i / n)
    th = math.pi * (1 + 5 ** 0.5) * i
    v = np.stack([np.cos(th) * np.sin(phi), np.cos(phi), np.sin(th) * np.sin(phi)], -1)
    v += np.random.default_rng(seed).normal(0, jitter, v.shape)
    return v / np.linalg.norm(v, axis=1, keepdims=True)


L_KEY = vnorm((-0.55, 0.70, 0.55))   # key light: top-left-front
L_FILL = vnorm((0.65, -0.35, 0.6))   # soft fill from lower right


def lambert(n, L):
    return clamp01(n[0] * L[0] + n[1] * L[1] + n[2] * L[2])


def blinn(n, rd, L, p):
    hx, hy, hz = norm3(L[0] - rd[0], L[1] - rd[1], L[2] - rd[2])
    return clamp01(n[0] * hx + n[1] * hy + n[2] * hz) ** p


def fresnel(n, rd, p=3.0):
    nv = clamp01(-(n[0] * rd[0] + n[1] * rd[1] + n[2] * rd[2]))
    return (1 - nv) ** p, nv


def c255(col, gain=1.0):
    return tuple(int(255 * min(1.0, max(0.0, c * gain))) for c in col)


# =========================================================================
# Canvas, ray-marcher and compositing
# =========================================================================
class Canvas:
    def __init__(self, w, h, cx, cy, scale, ss=SS):
        self.ss = ss
        self.w, self.h = w, h
        self.W, self.H = w * ss, h * ss
        self.cx, self.cy, self.S = cx * ss, cy * ss, scale * ss
        self.img = np.zeros((self.H, self.W, 3), np.float32)

    def project(self, x, y, z):
        """World -> pixel. Returns (sx, sy, pixels-per-world-unit at that depth)."""
        k = FOCAL / (CAM_Z - z) * self.S
        return self.cx + x * k, self.cy - y * k, k

    def layers(self):
        """Back + front additive emission layers (PIL) for lines and shards."""
        b = Image.new("RGB", (self.W, self.H))
        f = Image.new("RGB", (self.W, self.H))
        return b, ImageDraw.Draw(b), f, ImageDraw.Draw(f)

    def add_layer(self, im, gain=1.0, glow=0.0, radius=6.0):
        if gain:
            self.img += np.asarray(im, np.float32) * (gain / 255.0)
        if glow:
            b = im.filter(ImageFilter.GaussianBlur(radius * self.ss))
            self.img += np.asarray(b, np.float32) * (glow / 255.0)


_RAYS = {}


def _rays(cv, bound):
    """Primary rays that intersect the bounding sphere (cached per layout)."""
    key = (cv.W, cv.H, cv.cx, cv.cy, cv.S, bound)
    if key not in _RAYS:
        ys, xs = np.mgrid[0:cv.H, 0:cv.W].astype(np.float32)
        u = (xs + 0.5 - cv.cx) / cv.S
        v = (cv.cy - ys - 0.5) / cv.S
        dx, dy, dz = norm3(u, v, np.full_like(u, -FOCAL))
        b = CAM_Z * dz
        disc = b * b - (CAM_Z ** 2 - bound ** 2)
        m = disc > 0
        sq = np.sqrt(disc[m])
        _RAYS[key] = (np.nonzero(m.ravel())[0], dx[m], dy[m], dz[m], -b[m] - sq, -b[m] + sq)
    return _RAYS[key]


def render_body(cv, sdf, shade, bound, steps=80, stepk=1.0, eps=1.2e-3):
    """Sphere-trace an SDF and alpha-composite the shaded result onto the canvas."""
    idx, dx, dy, dz, t0, t1 = _rays(cv, bound)
    t = t0.copy()
    hit = np.zeros(t.shape, bool)
    act = np.arange(t.size)
    for _ in range(steps):
        if act.size == 0:
            break
        tt = t[act]
        d = sdf(dx[act] * tt, dy[act] * tt, CAM_Z + dz[act] * tt)
        h = d < eps
        hit[act[h]] = True
        t[act] = tt + d * stepk
        act = act[(~h) & (t[act] < t1[act])]
    sel = np.nonzero(hit)[0]
    if sel.size == 0:
        return
    tt = t[sel]
    x, y, z = dx[sel] * tt, dy[sel] * tt, CAM_Z + dz[sel] * tt
    e = 1.2e-3
    n = norm3(sdf(x + e, y, z) - sdf(x - e, y, z),
              sdf(x, y + e, z) - sdf(x, y - e, z),
              sdf(x, y, z + e) - sdf(x, y, z - e))
    rd = (dx[sel], dy[sel], dz[sel])
    r, g, b, a = shade((x, y, z), n, rd)
    a = np.broadcast_to(np.asarray(a, np.float32), r.shape)[:, None]
    col = np.stack([r, g, b], -1).astype(np.float32)
    flat = cv.img.reshape(-1, 3)
    pid = idx[sel]
    flat[pid] = flat[pid] * (1 - a) + col * a


def add_glow(img, cx, cy, r, col, gain=1.0, reach=3.0):
    """Additive gaussian glow (particles, coronas)."""
    H, W = img.shape[:2]
    R = r * reach
    x0, x1 = max(0, int(cx - R)), min(W, int(cx + R) + 1)
    y0, y1 = max(0, int(cy - R)), min(H, int(cy + R) + 1)
    if x0 >= x1 or y0 >= y1:
        return
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    d2 = ((xx + 0.5 - cx) ** 2 + (yy + 0.5 - cy) ** 2) / (r * r)
    img[y0:y1, x0:x1] += (gain * np.exp(-d2))[..., None] * np.asarray(col, np.float32)


def orb_px(img, cx, cy, r, col, style="glass", glow=0.5, alpha=0.95, hue=0.0):
    """Shaded sphere sprite: 'glass' satellite, 'bubble', or 'solid' moon."""
    col = np.asarray(col, np.float32)
    H, W = img.shape[:2]
    R = r * (3.4 if glow > 0 else 1.1) + 2
    x0, x1 = max(0, int(cx - R)), min(W, int(cx + R) + 1)
    y0, y1 = max(0, int(cy - R)), min(H, int(cy + R) + 1)
    if x0 >= x1 or y0 >= y1 or r < 0.5:
        return
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    dx = (xx + 0.5 - cx) / r
    dy = (yy + 0.5 - cy) / r
    d = np.sqrt(dx * dx + dy * dy)
    patch = img[y0:y1, x0:x1]
    if glow > 0:
        halo = glow * 0.55 * np.exp(-np.maximum(d - 0.95, 0) * 2.4) * (d > 0.8)
        patch += halo[..., None] * col
    a = np.clip((1.0 - d) * r + 0.5, 0, 1) * alpha
    nz = np.sqrt(np.clip(1 - d * d, 0, 1))
    rim = (1 - nz)
    spec = (np.exp(-((dx + 0.36) ** 2 + (dy + 0.42) ** 2) * 16) * 1.0 +
            np.exp(-((dx - 0.32) ** 2 + (dy - 0.48) ** 2) * 40) * 0.25)
    if style == "glass":
        c = (col * (0.16 + 0.95 * rim ** 2)[..., None] + col * (0.45 * nz ** 4)[..., None]
             + (0.25 * rim ** 6)[..., None])
        c = c + spec[..., None]
    elif style == "bubble":
        ir = np.stack(irid(rim * 0.9 + dy * 0.2 + hue), -1)
        c = ir * (rim ** 2.5 * 1.6)[..., None] + col * 0.08 + spec[..., None] * 1.2
        a = a * (0.25 + 0.75 * rim ** 2 + 0.6 * spec)
    else:  # solid
        lam = np.clip(-0.5 * dx - 0.6 * dy + 0.62 * nz, 0, 1)
        c = col * (0.22 + 0.9 * lam)[..., None] + col * (0.5 * rim ** 3)[..., None] + spec[..., None] * 0.55
    patch[:] = patch * (1 - a[..., None]) + c * a[..., None]


def orbit_point(R, ang, ax=0.0, ay=0.0, az=0.0):
    """Point on a circle of radius R in the XZ plane, then rotated."""
    return rot(R * np.cos(ang), 0.0 * ang, R * np.sin(ang), ax, ay, az)


def draw_orbit(cv, back, front, R, ax=0.0, ay=0.0, az=0.0, col=(1, 1, 1), width=1.0,
               back_gain=0.45, n=260):
    """Draw an orbit ring split into a behind-the-core part and an in-front part."""
    a = np.linspace(0, TAU, n + 1)
    x, y, z = orbit_point(R, a, ax, ay, az)
    sx, sy, _ = cv.project(x, y, z)
    zm = (z[:-1] + z[1:]) * 0.5
    w = max(1, int(round(width * cv.ss)))
    i = 0
    while i < n:
        f = zm[i] > 0
        j = i
        while j < n and (zm[j] > 0) == f:
            j += 1
        pts = [(float(sx[k]), float(sy[k])) for k in range(i, j + 1)]
        (front if f else back).line(pts, fill=c255(col, 1.0 if f else back_gain), width=w, joint="curve")
        i = j


def draw_sprites(sprites, front):
    """sprites: list of (z, callable). Draw back (z<=0) or front (z>0) set, far-to-near."""
    for z, fn in sorted(sprites, key=lambda s: s[0]):
        if (z > 0) == front:
            fn()


def background(cv, t, seed=0, tint=(0.04, 0.03, 0.07), dust=170, spread=2.2):
    """OLED-black root with a faint volumetric tint and slowly drifting dust."""
    H, W = cv.H, cv.W
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    r2 = ((xx - cv.cx) ** 2 + (yy - cv.cy) ** 2) / (max(W, H) * 0.5) ** 2
    cv.img[:] = np.exp(-r2 * spread)[..., None] * np.asarray(tint, np.float32)
    rng = np.random.default_rng(seed)
    px, py = rng.uniform(0, W, dust), rng.uniform(0, H, dust)
    ph = rng.uniform(0, TAU, dust)
    amp = rng.uniform(3, 12, dust) * cv.ss
    br = rng.uniform(0.2, 0.8, dust) ** 2
    x = (px + amp * np.cos(t + ph)) % W
    y = (py + amp * 0.6 * np.sin(t + ph)) % H
    tw = br * (0.55 + 0.45 * np.sin(2 * t + ph * 3))
    lay = np.zeros((H, W), np.float32)
    np.add.at(lay, (y.astype(int), x.astype(int)), tw)
    im = Image.fromarray(np.clip(lay * 255, 0, 255).astype(np.uint8))
    im = im.filter(ImageFilter.GaussianBlur(0.8 * cv.ss))
    cv.img += (np.asarray(im, np.float32) / 255 * 5.0)[..., None] * np.float32([0.75, 0.82, 1.0])


def finalize(cv, bloom=0.7, thresh=0.6, radius=8, post_np=None, post_pil=None):
    """Bloom -> optional post FX -> clamp -> 2x PIL hook -> downsample."""
    img = cv.img
    if bloom > 0:
        br = np.clip(img - thresh, 0, 1)
        b = Image.fromarray((br * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(radius * cv.ss))
        img = img + bloom * 1.8 * np.asarray(b, np.float32) / 255
    if post_np:
        img = post_np(img)
    pil = Image.fromarray((np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8))
    if post_pil:
        post_pil(pil)
    return pil.resize((cv.w, cv.h), Image.LANCZOS)


def new_canvas(size):
    return Canvas(size, size, size / 2, size / 2, size / 2)


def _done(cv, own, **fx):
    """Standalone stage -> finished frame; embedded (home-screen core) -> its post-FX settings."""
    return finalize(cv, **fx) if own else fx


# =========================================================================
# STAGE 1 (Age 3-5) - The Playful Spark: bouncy, gelatinous, smiling blob
# =========================================================================
def stage1(t, size, cv=None, decor=True):
    own = cv is None
    if own:
        cv = new_canvas(size)
        background(cv, t, seed=11, tint=(0.08, 0.04, 0.10))
    bounce = 0.10 * abs(math.sin(t))
    sq = 1.0 + 0.08 * math.cos(2 * t)                 # squash & stretch
    cy0 = -0.10 + bounce
    a, b, c = 0.98 / math.sqrt(sq), 0.80 * sq, 0.86 / math.sqrt(sq)
    m = min(a, b, c)

    def sdf(x, y, z):
        yy = y - cy0
        k = np.sqrt((x / a) ** 2 + (yy / b) ** 2 + (z / c) ** 2)
        wob = 0.035 * np.sin(5 * x + t) * np.sin(4 * yy + 2 * t) * np.sin(5 * z - t)
        return (k - 1.0) * m + wob

    def shade(p, n, rd):
        F, nv = fresnel(n, rd, 2.0)
        r, g, bb = irid(0.55 * (1 - nv) + 0.22 * n[1] - 0.15 * n[0] + t / TAU)
        r, g, bb = 0.42 + 0.58 * r, 0.40 + 0.60 * g, 0.48 + 0.52 * bb      # pastel
        dif = 0.55 + 0.45 * lambert(n, L_KEY)
        sp = 0.95 * blinn(n, rd, L_KEY, 55) + 0.18 * blinn(n, rd, L_KEY, 6)
        sss = 0.22 * nv ** 2                                             # jelly glow
        return (r * dif + sp + 0.32 * F + sss, g * dif + sp + 0.30 * F + sss * 0.6,
                bb * dif + sp + 0.36 * F + sss * 0.9, 1.0)

    # floor glow + sparkles
    sx, sy, k = cv.project(0, -0.95, 0)
    add_glow(cv.img, sx, sy + 0.05 * k, 0.55 * k * (1.1 - bounce), (0.6, 0.3, 0.8), 0.25)
    sparks = []
    for i in range(7):
        ang = i * TAU / 7 + 0.5 * t
        R = 1.18 + 0.06 * math.sin(2 * t + i)
        x, y, z = orbit_point(R, ang, ax=1.2, az=0.2)
        tw = max(0.0, math.sin(2 * t + i * 1.7)) ** 2
        col = irid(i / 7.0)
        sparks.append((z, lambda x=x, y=y, z=z, tw=tw, col=col: _sparkle(cv, x, y, z, tw, col)))
    sparks = sparks if decor else []
    draw_sprites(sparks, front=False)
    render_body(cv, sdf, shade, bound=1.12, stepk=0.8)
    draw_sprites(sparks, front=True)

    def face(pil):
        d = ImageDraw.Draw(pil, "RGBA")

        def surf(x, y):
            yy = y - cy0
            return c * math.sqrt(max(1 - (x / a) ** 2 - (yy / b) ** 2, 0.02))

        ink = (75, 35, 105, 255)
        for s in (-1, 1):
            x, y = 0.27 * s, cy0 + 0.13
            px, py, k = cv.project(x, y, surf(x, y))
            w, h = 0.10 * k, 0.085 * k
            d.arc([px - w, py - h, px + w, py + h], 195, 345, fill=ink, width=max(2, int(0.038 * k)))
            x2, y2 = 0.45 * s, cy0 - 0.06
            qx, qy, k2 = cv.project(x2, y2, surf(x2, y2))
            d.ellipse([qx - 0.10 * k2, qy - 0.055 * k2, qx + 0.10 * k2, qy + 0.055 * k2],
                      fill=(255, 105, 170, 95))
        x, y = 0.0, cy0 - 0.02
        px, py, k = cv.project(x, y, surf(x, y))
        w = 0.13 * k
        d.arc([px - w, py - w * 0.95, px + w, py + w * 0.55], 22, 158, fill=ink, width=max(2, int(0.038 * k)))

    return _done(cv, own, bloom=0.55, thresh=0.7, post_pil=face)


def _sparkle(cv, x, y, z, tw, col):
    sx, sy, k = cv.project(x, y, z)
    add_glow(cv.img, sx, sy, 0.035 * k, col, 1.6 * tw + 0.2)
    L = (0.06 + 0.10 * tw) * k
    for dx, dy in ((1, 0), (0, 1)):
        for i in range(-int(L), int(L) + 1):
            f = (1 - abs(i) / max(L, 1)) ** 2 * tw * 0.9
            yy, xx = int(sy + dy * i), int(sx + dx * i)
            if 0 <= yy < cv.H and 0 <= xx < cv.W:
                cv.img[yy, xx] += np.float32(col) * f + f * 0.5


# =========================================================================
# STAGE 2 (Age 6-8) - The Adventure Pod: bouncy cluster of iridescent bubbles
# =========================================================================
def stage2(t, size, cv=None, decor=True):
    own = cv is None
    if own:
        cv = new_canvas(size)
        background(cv, t, seed=22, tint=(0.03, 0.05, 0.10))
    wob = 0.03 * math.sin(2 * t)
    lobes = []
    for i, (R, rr, ph, tilt, sp) in enumerate([(0.60, 0.30, 0.0, 0.35, 1), (0.64, 0.24, 2.2, -0.55, -1),
                                                (0.58, 0.21, 4.1, 0.95, 1), (0.66, 0.16, 1.1, -1.2, -1)]):
        x, y, z = orbit_point(R + 0.03 * math.sin(2 * t + i), ph + sp * t, ax=tilt)
        lobes.append((x, y, z, rr * (1 + 0.06 * math.sin(2 * t + 1.3 * i))))

    def sdf(x, y, z):
        d = sph(x, y, z, 0, wob, 0, 0.60)
        for (cx, cy, cz, r) in lobes:
            d = smin(d, sph(x, y, z, cx, cy + wob, cz, r), 0.13)
        return d

    def shade(p, n, rd):
        F, nv = fresnel(n, rd, 2.0)
        r, g, b = irid(0.85 * (1 - nv) + 0.3 * n[1] + 0.2 * n[0] + t / TAU)
        sp = 1.3 * blinn(n, rd, L_KEY, 90) + 0.35 * blinn(n, rd, L_FILL, 40)
        k = 0.12 + 1.05 * F
        a = clamp01(0.42 + 0.58 * F + sp)
        inner = 0.12 * nv
        return (0.04 + r * k + sp + inner * 0.4, 0.04 + g * k + sp + inner * 0.55,
                0.08 + b * k + sp + inner, a)

    rng = np.random.default_rng(5)
    sprites = []
    for i in range(10):
        R = rng.uniform(0.95, 1.35)
        x, y, z = orbit_point(R, rng.uniform(0, TAU) + (1 if i % 2 else -1) * t,
                              ax=rng.uniform(-1.3, 1.3), az=rng.uniform(-0.5, 0.5))
        y += 0.05 * math.sin(2 * t + i)
        rr = rng.uniform(0.04, 0.11)
        sprites.append((z, lambda x=x, y=y, z=z, rr=rr, i=i: _bubble(cv, x, y, z, rr, i)))
    sprites = sprites if decor else []
    draw_sprites(sprites, False)
    render_body(cv, sdf, shade, bound=1.08)
    # sparkle motes inside the pod
    for i in range(9):
        x, y, z = orbit_point(0.25 + 0.04 * i, i * 2.4 + 2 * t, ax=0.6 * i)
        sx, sy, k = cv.project(x, y + wob, z)
        tw = 0.5 + 0.5 * math.sin(3 * t + i)
        add_glow(cv.img, sx, sy, 0.02 * k, irid(i / 9.0), 0.9 * tw)
    draw_sprites(sprites, True)
    return _done(cv, own, bloom=0.6, thresh=0.65)


def _bubble(cv, x, y, z, rr, i):
    sx, sy, k = cv.project(x, y, z)
    orb_px(cv.img, sx, sy, rr * k, (0.5, 0.8, 1.0), "bubble", glow=0.15, hue=i * 0.13)


# =========================================================================
# STAGE 3 (Age 9-12) - The Bio-Kinetic Catalyst: glass/putty metaballs + rings
# =========================================================================
S3_COLS = [(1.0, 0.55, 0.15), (1.0, 0.28, 0.62), (0.15, 0.80, 1.0), (0.55, 1.0, 0.30), (0.58, 0.38, 1.0)]


def stage3(t, size, cv=None, decor=True):
    own = cv is None
    if own:
        cv = new_canvas(size)
        background(cv, t, seed=33, tint=(0.05, 0.04, 0.08))
    balls = []
    for i in range(5):
        R = 0.40 + 0.07 * math.sin(2 * t + i)
        x, y, z = orbit_point(R, i * TAU / 5 + t * (1 if i % 2 else -1), ax=0.5 * i, az=0.3)
        balls.append((x, y, z, 0.33 + 0.05 * math.sin(2 * t + 2 * i)))

    def sdf(x, y, z):
        d = sph(x, y, z, *balls[0])
        for bl in balls[1:]:
            d = smin(d, sph(x, y, z, *bl), 0.16)
        return d

    def shade(p, n, rd):
        x, y, z = p
        ws = [np.exp(-14 * np.maximum(sph(x, y, z, *bl), 0) - 6.0 * np.sqrt((x - bl[0]) ** 2 + (y - bl[1]) ** 2 + (z - bl[2]) ** 2)) for bl in balls]
        tot = sum(ws) + 1e-6
        cr = sum(w * c[0] for w, c in zip(ws, S3_COLS)) / tot
        cg = sum(w * c[1] for w, c in zip(ws, S3_COLS)) / tot
        cb = sum(w * c[2] for w, c in zip(ws, S3_COLS)) / tot
        F, nv = fresnel(n, rd, 3.0)
        dif = 0.30 + 0.70 * lambert(n, L_KEY)
        sp = 1.0 * blinn(n, rd, L_KEY, 70) + 0.22 * blinn(n, rd, L_KEY, 10)
        s = 0.35 * nv ** 2
        return (cr * dif + cr * s + sp + 0.18 * F, cg * dif + cg * s + sp + 0.20 * F,
                cb * dif + cb * s + sp + 0.26 * F, 1.0)

    bk, bd, fr, fd = cv.layers()
    rings = [(1.10, 0.32, 0.0, 0.35, 1), (1.28, -0.45, 0.6, -0.5, -1)]
    sprites = []
    for ri, (R, ax, ay, az, dirn) in enumerate(rings if decor else []):
        draw_orbit(cv, bd, fd, R, ax, ay, az, (0.55, 0.65, 1.0), 1.2, back_gain=0.35)
        for j in range(5):
            x, y, z = orbit_point(R, j * TAU / 5 + dirn * t + ri, ax, ay, az)
            col = S3_COLS[(j + ri * 2) % 5]
            sprites.append((z, lambda x=x, y=y, z=z, col=col: _sat(cv, x, y, z, 0.045, col, "solid", 1.2)))
    cv.add_layer(bk, 0.6, 1.2, 3)
    draw_sprites(sprites, False)
    render_body(cv, sdf, shade, bound=1.0)
    cv.add_layer(fr, 0.9, 1.5, 3)
    draw_sprites(sprites, True)
    return _done(cv, own, bloom=0.6, thresh=0.65)


def _sat(cv, x, y, z, r, col, style="glass", glow=0.6):
    sx, sy, k = cv.project(x, y, z)
    orb_px(cv.img, sx, sy, r * k, col, style, glow=glow)
    return sx, sy, r * k


# =========================================================================
# STAGE 4 (Age 13-15) - The Glitch Synth: neon core, shard burst, RGB glitch
# =========================================================================
MAGENTA = np.float32([1.0, 0.15, 0.78])
CYAN = np.float32([0.15, 0.85, 1.0])


def stage4(t, size, cv=None, decor=True):
    own = cv is None
    if own:
        cv = new_canvas(size)
        background(cv, t, seed=44, tint=(0.07, 0.01, 0.07))
    beat = max(0.0, math.sin(4 * t)) ** 4
    trot = dict(ax=1.15 + 0.2 * math.sin(t), ay=t, az=0.3)

    def tor(x, y, z):
        x, y, z = rot_inv(x, y, z, **trot)
        q = np.sqrt(x * x + z * z) - 0.68
        return np.sqrt(q * q + y * y) - 0.07

    def sdf(x, y, z):
        return np.minimum(np.sqrt(x * x + y * y + z * z) - 0.5, tor(x, y, z))

    def shade(p, n, rd):
        x, y, z = p
        is_t = tor(x, y, z) < np.sqrt(x * x + y * y + z * z) - 0.5
        lx, ly, lz = rot_inv(x, y, z, **trot)
        F, nv = fresnel(n, rd, 2.0)
        sp = blinn(n, rd, L_KEY, 60)
        m = (0.5 + 0.5 * np.sin(2 * np.arctan2(lz, lx) + 3 * t))[:, None]
        tcol = (MAGENTA * (1 - m) + CYAN * m) * 1.5 + sp[:, None]
        rim = (0.5 + 0.5 * n[0])[:, None]
        scan = (np.sin(28 * ly + 4 * t) ** 14 * 0.6)[:, None]
        scol = (np.float32([0.04, 0.02, 0.09]) + (MAGENTA * (1 - rim) + CYAN * rim) * (1.6 * F)[:, None]
                + CYAN * scan * nv[:, None] + sp[:, None] * 0.6)
        col = np.where(is_t[:, None], tcol, scol)
        return col[:, 0], col[:, 1], col[:, 2], 1.0

    bk, bd, fr, fd = cv.layers()
    rng = np.random.default_rng(4)
    dirs = fib_sphere(18, 0.25, seed=8)
    for i, dv in enumerate(dirs):
        dx_, dy_, dz_ = rot(*dv, ay=0.5 * t)
        L = (0.80 + 0.5 * rng.random()) * (1 + 0.35 * beat + 0.2 * max(0, math.sin(3 * t + i)) ** 2)
        L = L if decor else 0.42 + (L - 0.42) * 0.55
        perp = vnorm(np.cross([dx_, dy_, dz_], [0.3, 0.9, 0.1]))
        w = 0.05 + 0.04 * rng.random()
        base = np.array([dx_, dy_, dz_]) * 0.42
        pts3 = [base + perp * w, np.array([dx_, dy_, dz_]) * L, base - perp * w]
        pts = [cv.project(*p)[:2] for p in pts3]
        col = CYAN if i % 4 == 0 else MAGENTA
        (fd if dz_ * L > 0.25 else bd).polygon(pts, fill=c255(col, 0.85))
    cv.add_layer(bk, 0.9, 2.0, 4)
    render_body(cv, sdf, shade, bound=0.8)
    cv.add_layer(fr, 0.9, 2.0, 4)
    for i in range(26 if decor else 0):        # debris
        x, y, z = orbit_point(rng.uniform(0.8, 1.4), rng.uniform(0, TAU) + t, ax=rng.uniform(-1.5, 1.5))
        sx, sy, k = cv.project(x, y, z)
        add_glow(cv.img, sx, sy, 0.012 * k, MAGENTA if i % 3 else CYAN, 1.2)

    g = max(0.0, math.sin(3 * t)) ** 6

    def glitch(img):
        ss = cv.ss
        sh = int((2 + 9 * g) * ss) if decor else int((1 + 3 * g) * ss)
        out = img.copy()
        out[..., 0] = np.roll(img[..., 0], sh, axis=1)
        out[..., 2] = np.roll(img[..., 2], -sh, axis=1)
        if g > 0.15 and decor:
            r = np.random.default_rng(int(t * 1000))
            for _ in range(7):
                y0 = int(r.integers(0, cv.H - 10))
                hh = int(r.integers(3, 18)) * ss
                out[y0:y0 + hh] = np.roll(out[y0:y0 + hh], int(r.integers(-30, 30) * ss * g), axis=1)
        out[::3 * ss] *= 0.78 if decor else 0.9       # scanlines
        return out

    return _done(cv, own, bloom=0.75, thresh=0.55, post_np=glitch)


# =========================================================================
# STAGE 5 (Age 16-18) - The Kinetic Prism: stellated glowing wireframe
# =========================================================================
PHI = (1 + 5 ** 0.5) / 2
ICO_V = np.array([(-1, PHI, 0), (1, PHI, 0), (-1, -PHI, 0), (1, -PHI, 0), (0, -1, PHI), (0, 1, PHI),
                  (0, -1, -PHI), (0, 1, -PHI), (PHI, 0, -1), (PHI, 0, 1), (-PHI, 0, -1), (-PHI, 0, 1)], float)
ICO_V /= np.linalg.norm(ICO_V, axis=1, keepdims=True)
_D = np.linalg.norm(ICO_V[:, None] - ICO_V[None], axis=-1)
_EMIN = _D[_D > 0].min()
ICO_E = [(i, j) for i in range(12) for j in range(i + 1, 12) if abs(_D[i, j] - _EMIN) < 1e-6]
ICO_F = [(i, j, k) for (i, j) in ICO_E for k in range(j + 1, 12)
         if abs(_D[i, k] - _EMIN) < 1e-6 and abs(_D[j, k] - _EMIN) < 1e-6]
ICO_FN = np.array([ICO_V[list(f)].mean(0) for f in ICO_F])
ICO_FN /= np.linalg.norm(ICO_FN, axis=1, keepdims=True)
ICO_IN = 0.7947  # inradius / circumradius


def stage5(t, size, cv=None, decor=True):
    own = cv is None
    if own:
        cv = new_canvas(size)
        background(cv, t, seed=55, tint=(0.05, 0.02, 0.09))
    beat = max(0.0, math.sin(4 * t)) ** 3
    Ro = 0.74 * (1 + 0.05 * beat)
    ro = dict(ax=0.5 + 0.25 * math.sin(t), ay=t, az=0.15)
    ri = dict(ax=-t, ay=-2 * t, az=0.4)

    def sdf(x, y, z):
        lx, ly, lz = rot_inv(x, y, z, **ro)
        P = np.stack([lx, ly, lz], -1) @ ICO_FN.T
        return P.max(1) - Ro * ICO_IN * 0.98

    def shade(p, n, rd):
        F, nv = fresnel(n, rd, 2.0)
        m = (0.5 + 0.5 * n[1])
        sp = blinn(n, rd, L_KEY, 80)
        k = 0.05 + 0.55 * F
        return (mix(0.15, 1.0, m) * k + sp, mix(0.85, 0.2, m) * k + sp, mix(1.0, 0.9, m) * k + sp,
                0.55 + 0.45 * F)

    render_body(cv, sdf, shade, bound=Ro * 1.02)

    def V(scale, r):
        return np.stack(rot(ICO_V[:, 0] * scale, ICO_V[:, 1] * scale, ICO_V[:, 2] * scale, **r), -1)

    Vo, Vi = V(Ro, ro), V(0.36, ri)
    gim = Image.new("RGB", (cv.W, cv.H))
    gd = ImageDraw.Draw(gim)
    cim = Image.new("RGB", (cv.W, cv.H))
    cd = ImageDraw.Draw(cim)

    def line(p, q, gain=1.0, w=1.2):
        zm = (p[2] + q[2]) / 2
        b = 0.5 + 0.5 * float(np.clip((zm + 1) / 2, 0, 1))
        m = float(np.clip(0.5 + 0.9 * (p[1] + q[1]) / 2 + 0.3 * math.sin(t), 0, 1))
        col = CYAN * (1 - m) + MAGENTA * m
        a, b2 = cv.project(*p)[:2], cv.project(*q)[:2]
        gd.line([a, b2], fill=c255(col, b * gain * 0.7), width=int(5 * cv.ss))
        cd.line([a, b2], fill=c255(col * 0.6 + 0.4, b * gain), width=max(1, int(w * cv.ss)))

    for i, j in ICO_E:
        line(Vo[i], Vo[j], 1.0, 1.4)
        line(Vi[i], Vi[j], 0.8, 1.0)
    for i in range(12):
        line(Vi[i], Vo[i], 0.45, 0.8)
    for fi, f in enumerate(ICO_F):
        L = Ro * (1.28 + 0.38 * max(0.0, math.sin(3 * t + 2.1 * fi)) ** 2 + 0.1 * beat)
        L = L if decor else Ro * 1.02 + (L - Ro * 1.02) * 0.6
        tip = np.array(rot(*(ICO_FN[fi] * L), **ro))
        for vi in f:
            line(Vo[vi], tip, 0.55, 0.9)
    cv.add_layer(gim, 0.0, 2.0, 4)
    cv.add_layer(cim, 1.0, 1.0, 1.2)
    for v in Vo:
        sx, sy, k = cv.project(*v)
        add_glow(cv.img, sx, sy, 0.028 * k, (0.9, 0.8, 1.0), 1.0)
    sx, sy, k = cv.project(0, 0, 0)
    add_glow(cv.img, sx, sy, 0.22 * k, (0.7, 0.4, 1.0), 0.5 + 0.4 * beat)
    return _done(cv, own, bloom=0.7, thresh=0.55)


# =========================================================================
# STAGE 6 (Age 19-25) - The Digital Oasis: iridescent fluid glass + fast satellites
# =========================================================================
def stage6(t, size, cv=None, decor=True):
    own = cv is None
    if own:
        cv = new_canvas(size)
        background(cv, t, seed=66, tint=(0.03, 0.05, 0.09))
    r0 = 0.72

    def sdf(x, y, z):
        return np.sqrt(x * x + y * y + z * z) - r0

    def shade(p, n, rd):
        qx, qy, qz = rot_inv(*p, ay=t, ax=0.3)
        ang = np.arctan2(qz, qx)
        F, nv = fresnel(n, rd, 2.4)
        sw = np.sin(3.5 * qy + 2 * ang + t + 1.5 * np.sin(2 * qx - t))
        h = ang / TAU + 0.30 * qy + 0.18 * sw + 0.45 * (1 - nv)
        r, g, b = irid(h, 0.8)
        k = 0.16 + 1.0 * F + 0.50 * nv ** 3 * (0.6 + 0.4 * sw)
        sp = 1.0 * blinn(n, rd, L_KEY, 110) + 0.3 * blinn(n, rd, L_FILL, 30)
        return (r * k + sp + 0.15 * F, g * k + sp + 0.18 * F, b * k + sp + 0.22 * F, 1.0)

    bk, bd, fr, fd = cv.layers()
    rings = [(1.00, 0.33, 0.0, 0.32, (0.55, 0.88, 1.0), 1.5, 2), (1.18, 0.52, 0.5, -0.42, (0.95, 0.6, 1.0), 1.0, -3)]
    sprites = []
    for i, (R, ax, ay, az, col, w, sp_) in enumerate(rings if decor else []):
        draw_orbit(cv, bd, fd, R, ax, ay, az, col, w, back_gain=0.4)
        for j in range(2):
            x, y, z = orbit_point(R, sp_ * t + j * math.pi + i, ax, ay, az)
            sprites.append((z, lambda x=x, y=y, z=z, col=col: _sat(cv, x, y, z, 0.05, col, "glass", 1.3)))
    cv.add_layer(bk, 0.7, 1.6, 3)
    draw_sprites(sprites, False)
    render_body(cv, sdf, shade, bound=0.76)
    cv.add_layer(fr, 0.9, 1.8, 3)
    draw_sprites(sprites, True)
    return _done(cv, own, bloom=0.65, thresh=0.6)


# =========================================================================
# STAGE 7 (Age 26-59) - The Quantum Glass Hub: faceted frosted crystal core
# =========================================================================
FACETS = fib_sphere(150, 0.05, seed=5).astype(np.float32)
FACET_RAND = np.random.default_rng(9).uniform(0, 1, len(FACETS)).astype(np.float32)


def quantum_core(cv, t, radius=0.72, tint=(0.3, 1.0, 0.6), tint_amt=0.0, spin=1):
    """Faceted obsidian/frosted glass with refracted bioluminescent interior."""
    rx = 0.35
    tint = np.float32(tint)

    def local(x, y, z):
        return rot_inv(x, y, z, ax=rx, ay=spin * t)

    def sdf(x, y, z):
        lx, ly, lz = local(x, y, z)
        return (np.stack([lx, ly, lz], -1) @ FACETS.T).max(1) - radius

    def shade(p, n, rd):
        x, y, z = p
        lx, ly, lz = local(x, y, z)
        P = np.stack([lx, ly, lz], -1) @ FACETS.T
        part = np.partition(P, -2, axis=1)
        edge = smoothstep(0.010, 0.0, part[:, -1] - part[:, -2])
        fi = np.argmax(P, 1)
        F, nv = fresnel(n, rd, 2.0)
        lam = lambert(n, L_KEY)
        frost = 0.30 + 0.28 * lam + 0.20 * FACET_RAND[fi]
        base = frost * (0.30 + 0.85 * F)
        bx, by, bz = norm3(rd[0] - 0.45 * n[0], rd[1] - 0.45 * n[1], rd[2] - 0.45 * n[2])
        qx, qy, qz = local(x + bx * 0.62, y + by * 0.62, z + bz * 0.62)
        v = np.sin(5 * qx + t) + np.sin(4 * qy - 2 * t) + np.sin(4 * qz + 3 * qx + t)
        ar, ag, ab = irid(0.12 * v + 0.32 * qy + 0.25 * FACET_RAND[fi] + t / TAU, 0.85)
        ar, ag, ab = mix(ar, tint[0], tint_amt), mix(ag, tint[1], tint_amt), mix(ab, tint[2], tint_amt)
        inner = nv ** 2.2 * (0.30 + 0.70 * (0.5 + 0.5 * np.sin(2 * v + t)) ** 2) * 1.45
        sp = 0.85 * blinn(n, rd, L_KEY, 140) + 0.25 * blinn(n, rd, L_FILL, 40)
        e = edge * (0.10 + 0.22 * lam)
        return (base * 0.90 + ar * inner + e + sp, base * 0.95 + ag * inner + e + sp,
                base * 1.05 + ab * inner + e + sp, 1.0)

    render_body(cv, sdf, shade, bound=radius * 1.14)


S7_SATS = [(1.10, 0.40, 0.0, 0.25, (0.25, 0.95, 0.8), 0.0), (1.22, 1.05, 0.4, -0.3, (0.78, 0.55, 1.0), 1.4),
           (1.05, -0.35, 0.9, 0.5, (1.0, 0.6, 0.18), 2.9), (1.25, 0.75, -0.6, 0.6, (0.35, 0.65, 1.0), 4.2),
           (1.15, -0.9, 0.2, -0.2, (0.45, 0.95, 0.45), 5.3)]


def stage7(t, size, cv=None, decor=True):
    own = cv is None
    if own:
        cv = new_canvas(size)
        background(cv, t, seed=77, tint=(0.04, 0.05, 0.07))
    bk, bd, fr, fd = cv.layers()
    sprites = []
    for i, (R, ax, ay, az, col, ph) in enumerate(S7_SATS if decor else []):
        draw_orbit(cv, bd, fd, R, ax, ay, az, (0.55, 0.6, 0.7), 0.7, back_gain=0.3)
        x, y, z = orbit_point(R, ph + t * (1 if i % 2 == 0 else -1), ax, ay, az)
        sprites.append((z, lambda x=x, y=y, z=z, col=col: _sat(cv, x, y, z, 0.10, col, "glass", 0.8)))
    cv.add_layer(bk, 0.35, 0.6, 2)
    draw_sprites(sprites, False)
    quantum_core(cv, t)
    cv.add_layer(fr, 0.45, 0.8, 2)
    draw_sprites(sprites, True)
    return _done(cv, own, bloom=0.55, thresh=0.65)


# =========================================================================
# STAGE 8 (Age 60+) - The Warm Solaria: slow-pulsing golden sun, thick orbits
# =========================================================================
def stage8(t, size, cv=None, decor=True):
    own = cv is None
    if own:
        cv = new_canvas(size)
        background(cv, t, seed=88, tint=(0.07, 0.04, 0.01), dust=90)
    pulse = 0.5 + 0.5 * math.sin(t)
    r0 = 0.70 * (1 + 0.015 * math.sin(t))
    sx, sy, k = cv.project(0, 0, 0)
    add_glow(cv.img, sx, sy, 0.95 * k, (1.0, 0.55, 0.12), 0.20 + 0.10 * pulse, reach=3.5)

    def sdf(x, y, z):
        return np.sqrt(x * x + y * y + z * z) - r0

    def shade(p, n, rd):
        qx, qy, qz = rot_inv(*p, ay=t)
        bands = 0.5 + 0.5 * np.sin(9 * qy + 1.5 * np.sin(3 * np.arctan2(qz, qx) + t))
        F, nv = fresnel(n, rd, 2.5)
        lam = lambert(n, L_KEY)
        m = clamp01(0.35 * bands + 0.55 * lam)
        br, bg, bb = mix(0.92, 1.0, m), mix(0.42, 0.74, m), mix(0.04, 0.26, m)
        core = nv ** 2 * 0.45 * (0.8 + 0.4 * pulse)
        sp = 0.6 * blinn(n, rd, L_KEY, 45)
        dif = 0.48 + 0.52 * lam
        return (br * dif + core + F + sp, bg * dif + core * 0.8 + F * 0.82 + sp * 0.95,
                bb * dif + core * 0.4 + F * 0.4 + sp * 0.8, 1.0)

    bk, bd, fr, fd = cv.layers()
    rings = [(1.10, 0.36, 0.0, -0.28, (1.0, 0.62, 0.18), 4.0), (1.32, 0.30, 0.0, -0.22, (1.0, 0.78, 0.40), 1.8)]
    sprites = []
    for i, (R, ax, ay, az, col, w) in enumerate(rings if decor else []):
        draw_orbit(cv, bd, fd, R, ax, ay, az, col, w, back_gain=0.5)
        x, y, z = orbit_point(R, (0.5 + t) if i == 0 else (2.6 - t), ax, ay, az)
        sprites.append((z, lambda x=x, y=y, z=z, i=i: _sat(cv, x, y, z, 0.075 - 0.02 * i, (1.0, 0.58, 0.15), "solid", 1.0)))
    cv.add_layer(bk, 0.8, 1.2, 3)
    draw_sprites(sprites, False)
    render_body(cv, sdf, shade, bound=0.74)
    cv.add_layer(fr, 1.0, 1.4, 3)
    draw_sprites(sprites, True)
    return _done(cv, own, bloom=0.75, thresh=0.7, radius=10)


STAGES = [
    (1, "AGE 3-5", "The Playful Spark", stage1),
    (2, "AGE 6-8", "The Adventure Pod", stage2),
    (3, "AGE 9-12", "The Bio-Kinetic Catalyst", stage3),
    (4, "AGE 13-15", "The Glitch Synth", stage4),
    (5, "AGE 16-18", "The Kinetic Prism", stage5),
    (6, "AGE 19-25", "The Digital Oasis", stage6),
    (7, "AGE 26-59", "The Quantum Glass Hub", stage7),
    (8, "AGE 60+", "The Warm Solaria", stage8),
]
STAGE_FN = {num: fn for num, _, _, fn in STAGES}


# =========================================================================
# HOME SCREEN - orbital agents + tension + FAB (any stage's avatar as the core)
# =========================================================================
AGENTS = [  # id, label, colour (spec colour mapping), screen angle (deg), icon, badge
    ("finance", "FINANCE", (0.12, 0.78, 0.72), 152, "finance", True),
    ("education", "EDUCATION", (0.74, 0.62, 1.00), 42, "edu", True),
    ("household", "HOUSEHOLD", (1.00, 0.62, 0.20), -6, "home", False),
    ("grocery", "GROCERY", (0.42, 0.95, 0.58), -50, "grocery", False),
    ("calendar", "CALENDAR", (0.38, 0.72, 1.00), -142, "cal", True),
]
AG_PLANE = dict(ax=1.15, ay=0.22, az=0.0)
# per-stage home layout: (projection scale at 1x, agent orbit radius) - keeps every avatar + agents in frame
HOME_CFG = {1: (170, 1.40), 2: (176, 1.36), 3: (182, 1.32), 4: (172, 1.40),
            5: (165, 1.45), 6: (190, 1.28), 7: (190, 1.28), 8: (182, 1.32)}
# per-stage agent orbit styling (colour, width): e.g. thick high-contrast track for older adults
ORBIT_STYLE = {4: ((1.0, 0.35, 0.85), 0.9), 5: ((0.80, 0.60, 1.0), 0.8), 8: ((1.0, 0.66, 0.26), 2.4)}
HOME_W, HOME_H, HOME_CY, FAB_Y, FAB_R = 360, 640, 300, 566, 34


def _icon(d, kind, x, y, s, fill):
    w = max(2, int(s * 0.16))
    if kind == "finance":
        f = font(int(s * 1.5), bold=True)
        d.text((x, y), "\u20b9", font=f, fill=fill, anchor="mm")
    elif kind == "edu":
        d.polygon([(x - s, y - s * 0.15), (x, y - s * 0.6), (x + s, y - s * 0.15), (x, y + s * 0.3)], fill=fill)
        d.rectangle([x - s * 0.5, y + s * 0.05, x + s * 0.5, y + s * 0.55], fill=fill)
        d.line([(x + s * 0.8, y - s * 0.1), (x + s * 0.8, y + s * 0.55)], fill=fill, width=w)
    elif kind == "home":
        d.polygon([(x - s, y - s * 0.05), (x, y - s * 0.85), (x + s, y - s * 0.05)], fill=fill)
        d.rectangle([x - s * 0.65, y - s * 0.1, x + s * 0.65, y + s * 0.7], fill=fill)
        d.rectangle([x - s * 0.18, y + s * 0.2, x + s * 0.18, y + s * 0.7], fill=(30, 20, 10, 200))
    elif kind == "grocery":
        d.polygon([(x - s * 0.9, y - s * 0.2), (x + s * 0.9, y - s * 0.2), (x + s * 0.6, y + s * 0.7),
                   (x - s * 0.6, y + s * 0.7)], fill=fill)
        d.arc([x - s * 0.55, y - s * 0.9, x + s * 0.55, y + s * 0.2], 180, 360, fill=fill, width=w)
    elif kind == "cal":
        d.rounded_rectangle([x - s * 0.8, y - s * 0.7, x + s * 0.8, y + s * 0.75], radius=s * 0.18, outline=fill, width=w)
        d.rectangle([x - s * 0.8, y - s * 0.7, x + s * 0.8, y - s * 0.32], fill=fill)
        for i in range(3):
            for j in range(2):
                cx, cy = x - s * 0.45 + i * s * 0.45, y - s * 0.02 + j * s * 0.38
                d.rectangle([cx - s * 0.1, cy - s * 0.1, cx + s * 0.1, cy + s * 0.1], fill=fill)


def tension(t):
    """0 = calm, 1 = full tension; calm at both ends of the loop so it repeats seamlessly."""
    T = float(np.clip(1.7 * (0.5 - 0.5 * math.cos(t)) - 0.35, 0, 1))
    return T * T * (3 - 2 * T)


def home_screen(t, stage=7, k=1.0, with_text=True, w=HOME_W, h=HOME_H):
    """
    Render one Home Screen frame.
      stage      - which avatar stage (1-8) sits at the core
      k          - output scale (1.0 = 360x640, 1.25 = 450x800 ...)
      with_text  - burn title / labels / badges into the image (GIF export). The interactive
                   prototype draws these as live HTML instead, so it renders with_text=False.
    Returns (PIL image, meta) where meta holds every clickable item's position in 360x640 layout px.
    """
    S0, R0 = HOME_CFG[stage]
    cv = Canvas(int(round(w * k)), int(round(h * k)), w * k / 2, HOME_CY * k, S0 * k)
    u = k * cv.ss                      # 1x layout px -> internal canvas px
    background(cv, t, seed=101 + stage, tint=(0.05, 0.06, 0.09), dust=220, spread=1.2)
    T = tension(t)
    status = np.float32(mix(np.float32([0.30, 1.0, 0.55]), np.float32([1.0, 0.62, 0.12]), T))

    sx, sy, kk = cv.project(0, 0, 0)
    add_glow(cv.img, sx, sy, 0.85 * kk, status, 0.10 + 0.14 * T, reach=3)

    ocol, ow = ORBIT_STYLE.get(stage, ((0.75, 0.8, 0.9), 0.8))
    bk, bd, fr, fd = cv.layers()
    draw_orbit(cv, bd, fd, R0, **AG_PLANE, col=ocol, width=ow * k, back_gain=0.4)
    if stage in (6, 7):
        draw_orbit(cv, bd, fd, R0 * 0.84, ax=1.45, ay=-0.5, az=0.55, col=(0.7, 0.75, 0.9), width=0.7 * k, back_gain=0.35)
        draw_orbit(cv, bd, fd, R0 * 0.9, ax=0.55, ay=0.3, az=-0.35, col=(0.7, 0.75, 0.9), width=0.7 * k, back_gain=0.35)

    placed, sprites = [], []
    for i, (aid, name, col, deg, icon, badge) in enumerate(AGENTS):
        tense = aid == "calendar"
        R = R0 - (0.30 * T if tense else 0.0)
        ang = -math.radians(deg) + 0.10 * math.sin(t + i * 1.3)
        if tense:
            ang += 0.035 * T * math.sin(13 * t)            # micro-vibration
            R += 0.02 * T * math.sin(17 * t)
        x, y, z = orbit_point(R, ang, **AG_PLANE)
        glow = 0.7 + (1.6 * T if tense else 0.0)
        p0 = cv.project(x * 0.55, y * 0.55, z * 0.55)[:2]
        p1 = cv.project(x * 0.86, y * 0.86, z * 0.86)[:2]
        (fd if z > 0 else bd).line([p0, p1], fill=c255(col, 0.45 + (0.5 * T if tense else 0)), width=max(1, int(2 * u)))
        sprites.append((z, lambda x=x, y=y, z=z, col=col, glow=glow: _sat(cv, x, y, z, 0.20, col, "glass", glow)))
        placed.append((aid, name, col, icon, badge, tense, *cv.project(x, y, z)))
    cv.add_layer(bk, 0.30, 0.6, 3)
    cv.add_layer(fr, 0.30, 0.6, 3)
    draw_sprites(sprites, False)
    fx = dict(bloom=0.5, thresh=0.68)
    if stage == 7:
        quantum_core(cv, t, radius=0.72, tint=status, tint_amt=0.22 + 0.45 * T)
    else:
        fx = STAGE_FN[stage](t, None, cv=cv, decor=False)
    draw_sprites(sprites, True)

    # ---- unified FAB with pulsing rings and waveform
    fxp, fyp, frp = w / 2 * u, FAB_Y * u, FAB_R * u
    rim = Image.new("RGB", (cv.W, cv.H))
    rd_ = ImageDraw.Draw(rim)
    for kq in range(3):
        ph = (t / TAU * 2 + kq / 3) % 1.0
        rr = frp * (1.05 + 0.75 * ph)
        rd_.ellipse([fxp - rr, fyp - rr, fxp + rr, fyp + rr], outline=c255((0.55, 0.5, 1.0), (1 - ph) * 0.8),
                    width=max(1, int(1.5 * u)))
    for s_ in (-1, 1):
        for j in range(14):
            bx = fxp + s_ * (frp * 1.3 + j * 5.5 * u)
            env = (1 - j / 14) ** 0.7
            hh = (3 + 16 * env * abs(math.sin(3 * t + j * 0.8 + (s_ > 0) * 1.1))) * u
            rd_.line([(bx, fyp - hh), (bx, fyp + hh)],
                     fill=c255(mix(np.float32([0.65, 0.45, 1.0]), CYAN, j / 13), 0.75), width=max(1, int(1.6 * u)))
    cv.add_layer(rim, 1.0, 1.2, 3)
    orb_px(cv.img, fxp, fyp, frp, (0.50, 0.45, 1.0), "glass", glow=1.0)
    add_glow(cv.img, fxp, fyp, frp * 0.55, (0.4, 0.75, 1.0), 0.45)

    stage_pil = fx.pop("post_pil", None)

    def overlay(pil):
        if stage_pil:
            stage_pil(pil)
        d = ImageDraw.Draw(pil, "RGBA")
        for aid, name, col, icon, badge, tense, px, py, kp in placed:
            _icon(d, icon, px, py, 0.20 * kp * 0.42, (255, 255, 255, 235))
        # mic glyph on the FAB
        U = u
        d.rounded_rectangle([fxp - 5 * U, fyp - 12 * U, fxp + 5 * U, fyp + 3 * U], radius=5 * U, fill=(255, 255, 255, 240))
        d.arc([fxp - 9 * U, fyp - 8 * U, fxp + 9 * U, fyp + 8 * U], 0, 180, fill=(255, 255, 255, 240), width=max(1, int(2 * U)))
        d.line([(fxp, fyp + 8 * U), (fxp, fyp + 13 * U)], fill=(255, 255, 255, 240), width=max(1, int(2 * U)))
        if not with_text:
            return
        d.text((w / 2 * U, 52 * U), "FamilyOS", font=font(int(27 * U)), fill=(225, 228, 235), anchor="mm")
        d.text((w / 2 * U, 80 * U), "Active Pod - Mahesh \u25be", font=font(int(12 * U)), fill=(150, 155, 168), anchor="mm")
        lab = "CORE  \u25cf  NEEDS ATTENTION" if T > 0.5 else "CORE  \u25cf  CALM"
        sc = c255(status, 1.0)
        f = font(int(9 * U), bold=True)
        tw = d.textlength(lab, font=f)
        d.rounded_rectangle([w / 2 * U - tw / 2 - 10 * U, 98 * U, w / 2 * U + tw / 2 + 10 * U, 116 * U],
                            radius=9 * U, fill=(sc[0], sc[1], sc[2], 38), outline=(sc[0], sc[1], sc[2], 150), width=max(1, int(U)))
        d.text((w / 2 * U, 107 * U), lab, font=f, fill=sc + (255,), anchor="mm")
        fl = font(int(9 * U))
        for aid, name, col, icon, badge, tense, px, py, kp in placed:
            r = 0.20 * kp
            ly = py - r - 11 * U if py < cv.cy - 20 * U else py + r + 11 * U
            d.text((px, ly), name, font=fl, fill=(200, 205, 215, 230), anchor="mm")
            if badge:
                bx, by, br = px + r * 0.78, py - r * 0.78, 7 * U
                bc = c255(mix(np.float32(col), np.float32([1.0, 0.35, 0.2]), T if tense else 0.0), 1.0)
                if tense:
                    br *= 1 + 0.25 * T * abs(math.sin(4 * t))
                d.ellipse([bx - br, by - br, bx + br, by + br], fill=bc + (255,))
                d.text((bx, by), "1", font=font(int(8 * U), bold=True), fill=(15, 15, 25), anchor="mm")
        d.text((w / 2 * U, 506 * U), "\u2191 SWIPE UP FOR DASHBOARD", font=font(int(8 * U)), fill=(150, 155, 168), anchor="mm")
        d.text((w / 2 * U, 618 * U), "TAP TO CHAT \u2022 HOLD TO LISTEN", font=font(int(8 * U)), fill=(150, 155, 168), anchor="mm")

    fx["post_pil"] = overlay
    img = finalize(cv, **fx)

    core_r = 0.80 * FOCAL / CAM_Z * S0          # generous tap radius for the avatar core
    meta = {
        "T": round(T, 3),
        "core": [w / 2, HOME_CY, round(core_r, 1)],
        "fab": [w / 2, FAB_Y, FAB_R],
        "agents": {aid: [round(px / u, 1), round(py / u, 1), round(0.20 * kp / u, 1), int(z > 0)]
                   for (aid, name, col, icon, badge, tense, px, py, kp), (z, _) in zip(placed, sprites)},
    }
    return img, meta


# =========================================================================
# Output helpers
# =========================================================================
def save_gif(frames, path, ms):
    """Quantise every frame against one shared palette (no colour flicker)."""
    step = max(1, len(frames) // 6)
    sample = frames[::step]
    W, H = sample[0].size
    sheet = Image.new("RGB", (W, H * len(sample)))
    for i, f in enumerate(sample):
        sheet.paste(f, (0, i * H))
    pal = sheet.quantize(colors=255, method=Image.Quantize.MEDIANCUT)
    q = [f.quantize(palette=pal, dither=Image.Dither.FLOYDSTEINBERG) for f in frames]
    q[0].save(path, save_all=True, append_images=q[1:], duration=ms, loop=0, disposal=1, optimize=False)


def make_grid(all_frames, tile=240, cols=4, header=52):
    rows = math.ceil(len(STAGES) / cols)
    W, H = cols * tile, rows * (tile + header)
    fb, fs = font(15, bold=True), font(11)
    out = []
    for fi in range(len(all_frames[0])):
        im = Image.new("RGB", (W, H), (0, 0, 0))
        d = ImageDraw.Draw(im)
        for si, (num, age, name, _) in enumerate(STAGES):
            c, r = si % cols, si // cols
            x0, y0 = c * tile, r * (tile + header)
            im.paste(all_frames[si][fi].resize((tile, tile), Image.LANCZOS), (x0, y0 + header))
            d.text((x0 + tile / 2, y0 + 20), f"STAGE {num}: {age}", font=fb, fill=(235, 235, 240), anchor="mm")
            d.text((x0 + tile / 2, y0 + 39), f"({name})", font=fs, fill=(150, 150, 160), anchor="mm")
        for c in range(1, cols):
            d.line([(c * tile, 0), (c * tile, H)], fill=(28, 28, 32))
        for r in range(1, rows):
            d.line([(0, r * (tile + header)), (W, r * (tile + header))], fill=(28, 28, 32))
        out.append(im)
    return out


def _webp_uri(im, q):
    buf = io.BytesIO()
    im.save(buf, "WEBP", quality=q, method=5)
    return "data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode()


def _anim_webp_uri(frames, ms, q):
    buf = io.BytesIO()
    frames[0].save(buf, "WEBP", save_all=True, append_images=frames[1:], duration=ms, loop=0, quality=q, method=4)
    return "data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode()


def build_prototype(out_dir, template, home_frames=40, k=1.25, quality=70, tile=200, tile_frames=36,
                    stage_frames=None, stages=range(1, 9), use_cache=True):
    """
    Render every stage's Home Screen (text-free, so the UI can be live HTML), record where every
    clickable item is on every frame, and inject it all into the HTML template.
    Per-stage renders are cached in <out_dir>/.proto_cache, so editing only the template and
    re-running `--only proto` rebuilds the HTML in seconds. Delete the cache to force a re-render.
    """
    data = {"ms": 80, "tileMs": 70, "stages": {}}
    for num, age, name, fn in STAGES:
        if num not in stages:
            continue
        t0 = time.time()
        cache = os.path.join(out_dir, ".proto_cache", f"stage{num}_{home_frames}f_k{k}_q{quality}.json")
        if use_cache and os.path.exists(cache):          # reuse renders: rebuild the HTML in seconds
            with open(cache) as f:
                data["stages"][str(num)] = json.load(f)
            continue
        if stage_frames and num in stage_frames:
            tf = [f.resize((tile, tile), Image.LANCZOS) for f in stage_frames[num]]
        else:
            tf = [fn(TAU * i / tile_frames, tile) for i in range(tile_frames)]
        frames, metas = [], []
        for i in range(home_frames):
            im, meta = home_screen(TAU * i / home_frames, stage=num, k=k, with_text=False)
            frames.append(_webp_uri(im, quality))
            metas.append(meta)
        data["stages"][str(num)] = {"tile": _anim_webp_uri(tf, 70, 72), "frames": frames, "meta": metas}
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        with open(cache, "w") as f:
            json.dump(data["stages"][str(num)], f)
        print(f"  prototype stage {num} {name:<24} {time.time() - t0:5.1f}s")
    html = open(template, encoding="utf-8").read()
    html = html.replace("/*__FAMILYOS_DATA__*/null", json.dumps(data, separators=(",", ":")))
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "familyos_prototype.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  prototype -> {path} ({os.path.getsize(path) / 1e6:.1f} MB)")
    return path


def main():
    ap = argparse.ArgumentParser(description="Render FamilyOS 3D avatars, home screens and the clickable prototype.")
    ap.add_argument("--out", default="familyos_output")
    ap.add_argument("--frames", type=int, default=36, help="frames per avatar loop")
    ap.add_argument("--home-frames", type=int, default=48, help="frames in the home-screen GIF")
    ap.add_argument("--size", type=int, default=320, help="avatar GIF size (px)")
    ap.add_argument("--only", default="all", help="'all', 'gifs', 'home', 'grid', 'proto' or a stage number 1-8")
    ap.add_argument("--template", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                       "familyos_prototype_template.html"))
    ap.add_argument("--proto-frames", type=int, default=40, help="frames per home loop in the prototype")
    ap.add_argument("--proto-scale", type=float, default=1.5, help="prototype render scale (1.5 = 540x960)")
    ap.add_argument("--proto-quality", type=int, default=72, help="WebP quality for prototype frames")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    want = a.only.lower()
    gif_modes = ("all", "gifs", "grid")
    stage_frames = {}
    for num, age, name, fn in STAGES:
        if want not in gif_modes and want != str(num):
            continue
        t0 = time.time()
        frames = [fn(TAU * i / a.frames, a.size) for i in range(a.frames)]
        slug = name.lower().replace("the ", "").replace(" ", "_").replace("-", "")
        save_gif(frames, os.path.join(a.out, f"stage{num}_{slug}.gif"), 70)
        frames[a.frames // 4].save(os.path.join(a.out, f"stage{num}_{slug}.png"))
        stage_frames[num] = frames
        print(f"  stage {num} {name:<26} {time.time() - t0:5.1f}s")

    if want in gif_modes and len(stage_frames) == 8:
        grid = make_grid([stage_frames[n] for n in range(1, 9)])
        save_gif(grid, os.path.join(a.out, "avatar_evolution_grid.gif"), 70)
        grid[a.frames // 4].save(os.path.join(a.out, "avatar_evolution_grid.png"))
        print("  evolution grid done")

    if want in ("all", "gifs", "home"):
        t0 = time.time()
        frames = [home_screen(TAU * i / a.home_frames)[0] for i in range(a.home_frames)]
        save_gif(frames, os.path.join(a.out, "home_screen_mature_adult.gif"), 80)
        frames[0].save(os.path.join(a.out, "home_screen_calm.png"))
        frames[a.home_frames // 2].save(os.path.join(a.out, "home_screen_needs_attention.png"))
        print(f"  home screen GIF                 {time.time() - t0:5.1f}s")

    if want in ("all", "proto"):
        build_prototype(a.out, a.template, home_frames=a.proto_frames, k=a.proto_scale,
                        quality=a.proto_quality, stage_frames=stage_frames or None)
    print("done ->", os.path.abspath(a.out))


if __name__ == "__main__":
    main()
