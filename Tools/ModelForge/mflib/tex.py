"""Procedural textures (CAFE.SPEC.md section 5.5).

In 3.3.5a the look of a prop comes almost entirely from its diffuse map (M2Vertex has no colour, there are no
normal or specular maps; the client lights with ambient + Lambert), so these are painted with baked light, the
way the stock props are: saturated colours, warm lights, cool shadows, broad colour variation, and nothing finer
than 4 texels at mip 1 (8 at mip 0) so nothing averages to grey or shimmers at distance.

Two forms of every generator:
  * a point function  f(ctx) -> (r, g, b) for atlas painting: ctx carries the texel's chart coordinates (s, t)
    in yards, its model-space position and normal and the bake's curvature and occlusion (bake.py);
  * an image function (w, h, seed, params) -> Img, which evaluates the same code on a flat chart (section 5.5's
    generator signature), used for the shared textures, icons and tests.
Colours are floats 0..1 here; Img.to_image() converts to blpconvert.Image (8-bit RGBA).
"""

import math

# ----------------------------------------------------------------------------------------------- colour


def hexc(h):
    h = h.lstrip("#")
    return (int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0)


def mix(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


def scale(c, k):
    return (c[0] * k, c[1] * k, c[2] * k)


def clamp01(x):
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)


def smoothstep(e0, e1, x):
    if e1 == e0:
        return 0.0 if x < e0 else 1.0
    t = clamp01((x - e0) / (e1 - e0))
    return t * t * (3 - 2 * t)


def lum(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def saturate(c, k):
    y = lum(c)
    return (y + (c[0] - y) * k, y + (c[1] - y) * k, y + (c[2] - y) * k)


SHADOW_TINT = (0.80, 0.84, 1.08)   # cool, toward blue-violet
LIGHT_TINT = (1.06, 1.01, 0.90)    # warm


def light(c, k):
    """Applies a light factor k (1 = unchanged) with cool shadows and warm lights."""
    if k < 1.0:
        d = 1.0 - k
        t = (1.0 - d * (1.0 - SHADOW_TINT[0]), 1.0 - d * (1.0 - SHADOW_TINT[1]), 1.0 - d * (1.0 - SHADOW_TINT[2]))
        return (c[0] * k * t[0], c[1] * k * t[1], c[2] * k * t[2])
    d = k - 1.0
    t = (1.0 + d * (LIGHT_TINT[0] - 1.0), 1.0 + d * (LIGHT_TINT[1] - 1.0), 1.0 + d * (LIGHT_TINT[2] - 1.0))
    return (c[0] * k * t[0], c[1] * k * t[1], c[2] * k * t[2])


# ------------------------------------------------------------------------------------------------ noise

def _h(ix, iy, iz, seed):
    h = (ix * 374761393 + iy * 668265263 + iz * 1274126177 + seed * 2654435761) & 0xFFFFFFFF
    h = ((h ^ (h >> 15)) * 2246822519) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 3266489917) & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFFFF) / 16777215.0


def noise3(x, y, z, seed=0):
    """Value noise in [0, 1], smooth (quintic fade), period-free."""
    ix, iy, iz = math.floor(x), math.floor(y), math.floor(z)
    fx, fy, fz = x - ix, y - iy, z - iz
    ux = fx * fx * fx * (fx * (fx * 6 - 15) + 10)
    uy = fy * fy * fy * (fy * (fy * 6 - 15) + 10)
    uz = fz * fz * fz * (fz * (fz * 6 - 15) + 10)
    c000 = _h(ix, iy, iz, seed)
    c100 = _h(ix + 1, iy, iz, seed)
    c010 = _h(ix, iy + 1, iz, seed)
    c110 = _h(ix + 1, iy + 1, iz, seed)
    c001 = _h(ix, iy, iz + 1, seed)
    c101 = _h(ix + 1, iy, iz + 1, seed)
    c011 = _h(ix, iy + 1, iz + 1, seed)
    c111 = _h(ix + 1, iy + 1, iz + 1, seed)
    x00 = c000 + (c100 - c000) * ux
    x10 = c010 + (c110 - c010) * ux
    x01 = c001 + (c101 - c001) * ux
    x11 = c011 + (c111 - c011) * ux
    y0 = x00 + (x10 - x00) * uy
    y1 = x01 + (x11 - x01) * uy
    return y0 + (y1 - y0) * uz


def noise(x, y, seed=0):
    return noise3(x, y, 0.5, seed)


def fbm3(x, y, z, seed=0, octaves=3, lac=2.0, gain=0.5):
    a, f, s, n = 1.0, 1.0, 0.0, 0.0
    for o in range(octaves):
        s += a * noise3(x * f, y * f, z * f, seed + 31 * o)
        n += a
        a *= gain
        f *= lac
    return s / n


def fbm(x, y, seed=0, octaves=3):
    return fbm3(x, y, 0.37, seed, octaves)


# ------------------------------------------------------------------------------------------------ image

class Img:
    """Float RGBA image, rows top to bottom."""

    def __init__(self, w, h, fill=(0.0, 0.0, 0.0, 1.0)):
        self.w, self.h = w, h
        n = w * h
        self.r = [fill[0]] * n
        self.g = [fill[1]] * n
        self.b = [fill[2]] * n
        self.a = [fill[3]] * n

    def set(self, x, y, c, a=1.0):
        i = y * self.w + x
        self.r[i], self.g[i], self.b[i], self.a[i] = c[0], c[1], c[2], a

    def get(self, x, y):
        i = y * self.w + x
        return (self.r[i], self.g[i], self.b[i], self.a[i])

    def blend(self, x, y, c, a):
        """Paints colour c with coverage a over the texel (alpha kept)."""
        if a <= 0.0:
            return
        i = y * self.w + x
        if a >= 1.0:
            self.r[i], self.g[i], self.b[i] = c[0], c[1], c[2]
            return
        self.r[i] += (c[0] - self.r[i]) * a
        self.g[i] += (c[1] - self.g[i]) * a
        self.b[i] += (c[2] - self.b[i]) * a

    def to_image(self):
        from blpconvert import Image  # noqa: WPS433 (read-only sibling tool)
        out = Image(self.w, self.h)
        d = out.data
        for i in range(self.w * self.h):
            o = 4 * i
            d[o] = _b(self.r[i])
            d[o + 1] = _b(self.g[i])
            d[o + 2] = _b(self.b[i])
            d[o + 3] = _b(self.a[i])
        return out

    @staticmethod
    def from_image(img):
        out = Img(img.width, img.height)
        d = img.data
        for i in range(img.width * img.height):
            o = 4 * i
            out.r[i] = d[o] / 255.0
            out.g[i] = d[o + 1] / 255.0
            out.b[i] = d[o + 2] / 255.0
            out.a[i] = d[o + 3] / 255.0
        return out


def _b(v):
    v = int(v * 255.0 + 0.5)
    return 0 if v < 0 else (255 if v > 255 else v)


class Ctx:
    """What a point generator sees for one texel."""

    __slots__ = ("s", "t", "pos", "n", "curv", "ao", "cw", "ch", "chart", "part", "u", "v")

    def __init__(self, s=0.0, t=0.0, pos=(0.0, 0.0, 0.0), n=(0.0, 0.0, 1.0), curv=0.0, ao=1.0, cw=1.0, ch=1.0,
                 chart="", part=""):
        self.s, self.t, self.pos, self.n = s, t, pos, n
        self.curv, self.ao, self.cw, self.ch = curv, ao, cw, ch
        self.chart, self.part = chart, part
        self.u = s / cw if cw else 0.0
        self.v = t / ch if ch else 0.0


def image_from(fn, w, h, seed=0, params=None, size_yd=None):
    """Evaluates a point generator on a flat w x h chart that measures size_yd yards (default w/256 per side)."""
    params = params or {}
    sw = size_yd[0] if size_yd else w / 256.0
    sh = size_yd[1] if size_yd else h / 256.0
    img = Img(w, h)
    for y in range(h):
        t = (y + 0.5) / h * sh
        for x in range(w):
            s = (x + 0.5) / w * sw
            ctx = Ctx(s, t, (s, 0.0, sh - t), (0.0, -1.0, 0.0) if params.get("side") else (0.0, 0.0, 1.0), 0.0,
                      1.0, sw, sh)
            c = fn(ctx, seed, params)
            if len(c) == 4:
                img.set(x, y, c[:3], c[3])
            else:
                img.set(x, y, c)
    return img


# -------------------------------------------------------------------------------------- point generators
# Each: f(ctx, seed, params) -> (r, g, b) or (r, g, b, a). Feature scales are in yards.

def g_noise(ctx, seed, p):
    v = noise3(ctx.pos[0] * p.get("freq", 8.0), ctx.pos[1] * p.get("freq", 8.0), ctx.pos[2] * p.get("freq", 8.0),
               seed)
    return (v, v, v)


def g_fbm(ctx, seed, p):
    f = p.get("freq", 8.0)
    v = fbm3(ctx.pos[0] * f, ctx.pos[1] * f, ctx.pos[2] * f, seed, p.get("octaves", 3))
    return (v, v, v)


def _metal_bands(n, light_c, base, dark, bounce):
    """Painted 'reflection' of a metal: bright above, a dark horizon band just under the middle, warm bounce
    light from below. View independent, like the painted metals of the stock props."""
    z = n[2]
    if z > 0.5:
        return mix(base, light_c, 0.12 + smoothstep(0.5, 1.0, z) * 0.38)
    if z > -0.1:
        return mix(base, light_c, smoothstep(-0.1, 0.5, z) * 0.12)
    if z > -0.55:
        k = smoothstep(-0.1, -0.28, z) * (1.0 - smoothstep(-0.38, -0.55, z) * 0.45)
        return mix(base, dark, k * 0.85)
    return mix(mix(base, dark, 0.47), bounce, smoothstep(-0.55, -0.9, z))


def _azimuth_streak(n, center=0.55, width=0.35):
    """A broad painted highlight streak on round parts, facing front-left-up (toward the key light)."""
    a = math.atan2(n[1], n[0])
    d = abs((a - center + math.pi) % (2 * math.pi) - math.pi)
    hor = math.sqrt(max(0.0, 1.0 - n[2] * n[2]))
    return smoothstep(width, 0.0, d) * hor


def _elevation_hotspot(n, az_center=0.55, el0=0.55, el1=0.95):
    """A painted specular crescent on up-facing rounds (domes, knobs, the tops of spheres): strongest at about
    35-55 degrees of elevation toward the key light's azimuth (front-left), where _azimuth_streak fades out."""
    el = math.asin(max(-1.0, min(1.0, n[2])))
    k_el = smoothstep(el0 - 0.18, el0, el) * (1.0 - smoothstep(el1, el1 + 0.3, el))
    if k_el <= 0.0:
        return 0.0
    a = math.atan2(n[1], n[0])
    d = abs((a - az_center + math.pi) % (2 * math.pi) - math.pi)
    return k_el * smoothstep(1.25, 0.15, d)


def metal(ctx, seed, p, light_c, base, dark, bounce, patina, patina_amt):
    n = ctx.n
    c = _metal_bands(n, light_c, base, dark, bounce)
    # broad colour variation across the part
    f = p.get("freq", 4.0)
    v = fbm3(ctx.pos[0] * f, ctx.pos[1] * f, ctx.pos[2] * f, seed, 3)
    c = mix(c, scale(c, 0.82), smoothstep(0.35, 0.75, v) * 0.55)
    c = mix(c, light_c, smoothstep(0.62, 0.85, v) * 0.18)
    if p.get("streak", True):
        st = _azimuth_streak(n, p.get("streak_az", 0.55), p.get("streak_w", 0.40))
        c = mix(c, light_c, st * p.get("streak_k", 0.65))
        st2 = _azimuth_streak(n, p.get("streak_az", 0.55) + 2.4, 0.25)
        c = mix(c, scale(light_c, 0.95), st2 * 0.25)
    hs = p.get("hotspot", 0.6)
    if hs:
        c = mix(c, mix(light_c, (1.0, 1.0, 0.94), 0.3), _elevation_hotspot(n, p.get("streak_az", 0.55)) * hs)
    # broad painted brush strokes along the chart's t direction (the hand-painted look)
    bs = noise3(ctx.s * 9.0, ctx.t * 1.6, 0.5, seed + 13)
    c = scale(c, 0.93 + 0.12 * bs)
    # brushed direction (very low contrast, along t)
    if p.get("brushed"):
        b = noise3(ctx.s * 3.0, ctx.t * 60.0, 0.0, seed + 7)
        c = scale(c, 0.94 + 0.08 * b)
    # patina in recesses (low occlusion) and broad patches
    if patina_amt > 0:
        pv = fbm3(ctx.pos[0] * 7 + 3.1, ctx.pos[1] * 7, ctx.pos[2] * 7, seed + 11, 3)
        k = patina_amt * (smoothstep(0.55, 0.85, pv) * 0.5 + smoothstep(0.85, 0.55, ctx.ao) * 0.8)
        c = mix(c, patina, clamp01(k))
    # edge wear from the curvature map: convex edges polished bright, concave dark
    cv = ctx.curv
    if cv > 0:
        c = mix(c, saturate(light_c, 0.7), clamp01(cv) * 0.55)
    elif cv < 0:
        c = mix(c, scale(dark, 0.7), clamp01(-cv) * 0.5)
    return c


BRASS = dict(light_c=hexc("FFE58E"), base=hexc("D49A2A"), dark=hexc("5A3206"), bounce=hexc("B0701C"),
             patina=hexc("6E7A4A"))
GOLD = dict(light_c=hexc("FFF3A8"), base=hexc("ECB11C"), dark=hexc("764604"), bounce=hexc("C8841A"),
            patina=hexc("8A7A30"))
COPPER = dict(light_c=hexc("FFB47C"), base=hexc("C05624"), dark=hexc("4E1C0A"), bounce=hexc("9A421E"),
              patina=hexc("4F8A72"))
IRON = dict(light_c=hexc("8A8C94"), base=hexc("4A4B52"), dark=hexc("1E1E24"), bounce=hexc("3A3530"),
            patina=hexc("5A3A26"))


def g_brass(ctx, seed, p):
    pal = dict(BRASS)
    pal.update(p.get("palette", {}))
    return metal(ctx, seed, p, pal["light_c"], pal["base"], pal["dark"], pal["bounce"], pal["patina"],
                 p.get("patina", 0.25))


def g_gold(ctx, seed, p):
    return metal(ctx, seed, p, GOLD["light_c"], GOLD["base"], GOLD["dark"], GOLD["bounce"], GOLD["patina"],
                 p.get("patina", 0.1))


def g_copper(ctx, seed, p):
    return metal(ctx, seed, p, COPPER["light_c"], COPPER["base"], COPPER["dark"], COPPER["bounce"],
                 COPPER["patina"], p.get("patina", 0.35))


def g_iron(ctx, seed, p):
    c = metal(ctx, seed, p, IRON["light_c"], IRON["base"], IRON["dark"], IRON["bounce"], IRON["patina"],
              p.get("rust", 0.3))
    grid = p.get("rivet_grid")
    if grid:
        c = rivets(ctx, c, grid, p.get("rivet_r", 0.012), IRON["light_c"], IRON["dark"])
    return c


def rivets(ctx, c, spacing, r, hi, lo):
    """Painted rivets in chart space: a lit upper half, a dark lower rim."""
    s, t = ctx.s, ctx.t
    gx = round(s / spacing) * spacing
    gy = round(t / spacing) * spacing
    dx, dy = s - gx, t - gy
    d = math.hypot(dx, dy)
    if d > r * 1.6:
        return c
    if d < r:
        k = clamp01(0.5 - dy / r * 0.6)
        return mix(scale(c, 0.85), hi, k * 0.8)
    return mix(c, lo, smoothstep(r * 1.6, r, d) * 0.7)


def g_soot(ctx, seed, p):
    base = p.get("color", hexc("2A2622"))
    h = p.get("top", 1.0)
    k = smoothstep(h - p.get("span", 0.3), h, ctx.pos[2])
    v = fbm3(ctx.pos[0] * 6, ctx.pos[1] * 6, ctx.pos[2] * 6, seed, 3)
    return mix(p.get("under", hexc("4A4B52")), base, clamp01(k * (0.6 + 0.6 * v)))


def g_enamel(ctx, seed, p):
    """Glossy enamel: a saturated base, broad value drift, a soft gloss band near the top of each panel and a
    few large chips (dark metal with a lit lower rim)."""
    base = p.get("color", hexc("2E4E8C"))
    v = fbm3(ctx.pos[0] * 3.0, ctx.pos[1] * 3.0, ctx.pos[2] * 3.0, seed, 3)
    c = mix(scale(base, 0.85), scale(base, 1.12), v)
    bs = noise3(ctx.s * 8.0, ctx.t * 1.5, 0.5, seed + 13)
    c = scale(c, 0.94 + 0.1 * bs)
    # gloss: a band near the top of the chart (panels) and toward the light on round parts
    gl = smoothstep(0.32, 0.08, ctx.v) * smoothstep(0.0, 0.05, ctx.v)
    c = mix(c, mix(base, (0.92, 0.95, 1.0), 0.55), gl * p.get("gloss", 0.45))
    if ctx.n[2] > 0.6:
        c = mix(c, mix(base, (0.9, 0.94, 1.0), 0.4), smoothstep(0.6, 1.0, ctx.n[2]) * 0.4)
    chips = p.get("chips", 3)
    if chips:
        cr = p.get("chip_r", 0.028)
        for k in range(chips):
            cs = _h(k, 1, 7, seed) * ctx.cw
            ct = 0.2 * ctx.ch + _h(k, 2, 7, seed) * ctx.ch * 0.7
            dx, dy = ctx.s - cs, ctx.t - ct
            # irregular flake: radius modulated by angle
            ang = math.atan2(dy, dx)
            rr = cr * (0.7 + 0.5 * _h(k, 3, 7, seed)) * (0.8 + 0.25 * math.sin(ang * 3 + k) + 0.15 * math.sin(
                ang * 5 + 2 * k))
            d = math.hypot(dx, dy)
            if d < rr:
                metal_c = hexc("3A3634")
                rim = smoothstep(rr * 0.55, rr, d) * clamp01(dy / rr + 0.3)
                c = mix(metal_c, hexc("A8B8D8"), rim * 0.8)
            elif d < rr * 1.25:
                c = mix(c, scale(base, 0.6), smoothstep(rr * 1.25, rr, d) * 0.6)
    if ctx.curv > 0:
        c = mix(c, mix(base, (1.0, 1.0, 1.0), 0.45), clamp01(ctx.curv) * 0.45)
    return c


WOODS = {
    "walnut": (hexc("5C3420"), hexc("3A1E12"), hexc("8A5634")),
    "dark": (hexc("3E2618"), hexc("24150C"), hexc("6A4428")),
    "timber": (hexc("8A6038"), hexc("5A3A20"), hexc("B48858")),
    "oak": (hexc("9A6E3C"), hexc("664422"), hexc("C49A60")),
}


def g_wood(ctx, seed, p):
    """Painted wood: grain along the chart's long axis (or `axis`), a few broad tone bands, plank seams."""
    base, dark, lite = WOODS[p.get("kind", "walnut")]
    along_s = p.get("along", "long")
    if along_s == "long":
        along_s = "s" if ctx.cw >= ctx.ch else "t"
    a, b = (ctx.s, ctx.t) if along_s == "s" else (ctx.t, ctx.s)
    warp = fbm(a * 2.0, b * 6.0, seed + 3, 2)
    g = noise(a * 1.5, b * 28.0 + warp * 4.0, seed)
    g2 = noise(a * 0.8, b * 9.0 + warp * 2.0, seed + 5)
    c = mix(base, dark, smoothstep(0.55, 0.85, g) * 0.7)
    c = mix(c, lite, smoothstep(0.6, 0.9, g2) * 0.35)
    planks = p.get("planks", 0)
    if planks:
        w = (ctx.ch if along_s == "s" else ctx.cw) / planks
        q = (b % w) / w
        c = mix(c, scale(dark, 0.7), smoothstep(0.06, 0.0, q) * 0.8 + smoothstep(0.94, 1.0, q) * 0.4)
    if ctx.curv > 0:
        c = mix(c, lite, clamp01(ctx.curv) * 0.45)
    elif ctx.curv < 0:
        c = mix(c, scale(dark, 0.6), clamp01(-ctx.curv) * 0.5)
    return c


def g_marble(ctx, seed, p):
    base = p.get("color", hexc("ECE8E0"))
    vein = p.get("vein", hexc("8A8A9A"))
    x, y, z = ctx.pos
    w = fbm3(x * 4, y * 4, z * 4, seed, 3)
    v = abs(math.sin((x * 3 + y * 5 + w * 6.0) * 1.7))
    c = mix(base, vein, smoothstep(0.12, 0.0, v) * 0.6)
    return mix(c, scale(base, 0.92), noise3(x * 6, y * 6, z * 6, seed + 1) * 0.5)


def g_stone(ctx, seed, p):
    base = p.get("color", hexc("8A8478"))
    bw, bh = p.get("block", (0.3, 0.15))
    row = math.floor(ctx.t / bh)
    off = (row % 2) * bw * 0.5
    qx = ((ctx.s + off) % bw) / bw
    qy = (ctx.t % bh) / bh
    v = _h(math.floor((ctx.s + off) / bw), row, 3, seed)
    c = scale(base, 0.85 + 0.25 * v)
    mortar = min(qx, 1 - qx, qy, 1 - qy)
    return mix(scale(base, 0.45), c, smoothstep(0.02, 0.08, mortar))


def g_leather(ctx, seed, p):
    base = p.get("color", hexc("6A3E22"))
    v = fbm(ctx.s * 12, ctx.t * 12, seed, 3)
    c = mix(scale(base, 0.8), scale(base, 1.15), v)
    if p.get("stitch"):
        m = p.get("stitch_margin", 0.02)
        e = min(ctx.s, ctx.cw - ctx.s, ctx.t, ctx.ch - ctx.t)
        if abs(e - m) < 0.004 and (ctx.s + ctx.t) % 0.03 < 0.018:
            c = hexc("E8D8B0")
    return c


def g_hide(ctx, seed, p):
    base = p.get("color", hexc("9C4A2A"))
    v = fbm(ctx.s * 5, ctx.t * 5, seed, 3)
    spots = smoothstep(0.62, 0.72, fbm(ctx.s * 9 + 3, ctx.t * 9, seed + 1, 2))
    c = mix(scale(base, 0.85), scale(base, 1.15), v)
    return mix(c, scale(base, 0.6), spots * 0.5)


def g_ceramic(ctx, seed, p):
    base = p.get("color", hexc("F4EFE4"))
    band = p.get("band")
    c = mix(base, scale(base, 0.94), noise3(ctx.pos[0] * 9, ctx.pos[1] * 9, ctx.pos[2] * 9, seed) * 0.6)
    if band:
        bc, v0, v1 = band
        if v0 <= ctx.v <= v1:
            c = bc
        elif v0 - 0.03 <= ctx.v <= v1 + 0.03:
            c = mix(c, bc, 0.4)
    if ctx.n[2] > 0.5:
        c = mix(c, (1.0, 1.0, 1.0), (ctx.n[2] - 0.5) * 0.3)
    if ctx.curv > 0:
        c = mix(c, (1.0, 1.0, 1.0), clamp01(ctx.curv) * 0.4)
    return c


def g_clay(ctx, seed, p):
    base = p.get("color", hexc("A0603A"))
    glaze = p.get("glaze", hexc("9C2A1F"))
    drip = fbm(ctx.s * 8, 0.3, seed, 2) * 0.3 + 0.35
    c = mix(scale(base, 0.9), scale(base, 1.1), fbm(ctx.s * 10, ctx.t * 10, seed + 2, 2))
    return mix(glaze, c, smoothstep(drip - 0.03, drip + 0.03, ctx.v))


def g_fabric_stripes(ctx, seed, p):
    cols = p.get("colors", (hexc("3F6FB5"), hexc("F1E6CC")))
    count = p.get("count", 8)
    k = int((ctx.u * count) % len(cols))
    c = cols[k]
    weave = 0.95 + 0.05 * noise(ctx.s * 80, ctx.t * 80, seed)
    c = scale(c, weave)
    if p.get("underside"):
        c = scale(saturate(c, 0.8), 0.62)
    return c


def g_glass(ctx, seed, p):
    """Glass body alpha 70-110 with vertical streak highlights (alpha 180-230) and darker rims."""
    tint = p.get("tint", hexc("D8EEF0"))
    a = p.get("alpha", 0.36)
    c = tint
    sx = ctx.u
    for centre, wdt in ((0.18, 0.05), (0.26, 0.015), (0.68, 0.03)):
        d = abs(sx - centre)
        if d < wdt:
            k = smoothstep(wdt, 0.0, d)
            c = mix(c, (1.0, 1.0, 1.0), k)
            a = max(a, 0.72 + 0.18 * k)
    rim = min(ctx.v, 1.0 - ctx.v)
    if rim < 0.06:
        c = mix(c, scale(tint, 0.55), 0.5)
        a = max(a, 0.55)
    return (c[0], c[1], c[2], a)


def g_frost(ctx, seed, p):
    v = fbm(ctx.s * 14, ctx.t * 14, seed, 3)
    c = mix(hexc("C8E4F4"), (1.0, 1.0, 1.0), v)
    return (c[0], c[1], c[2], 0.45 + 0.35 * v)


def g_env_gradient(ctx, seed, p):
    """Chrome env (sphere map): a soft sky-over-ground gradient with a gentle horizon, low contrast."""
    sky = p.get("sky", hexc("F2E6CC"))
    zen = p.get("zenith", hexc("C8D4E4"))
    hor = p.get("horizon", hexc("FFF6E0"))
    gnd = p.get("ground", hexc("5A4632"))
    x = ctx.u * 2 - 1
    y = ctx.v * 2 - 1
    r = math.sqrt(x * x + y * y)
    y2 = y  # -1 top (sky) .. +1 bottom (ground)
    if y2 < 0.05:
        c = mix(hor, mix(sky, zen, smoothstep(-0.2, -0.9, y2)), smoothstep(0.05, -0.35, y2))
    else:
        c = mix(hor, gnd, smoothstep(0.05, 0.45, y2))
    # rim darkening: a vertical chrome tube seen from the side samples the horizon row, so this is what gives it
    # a bright core and dark edges instead of a flat light grey
    rim = p.get("rim", 0.62)
    return scale(c, 1.0 - rim * smoothstep(0.35, 1.0, r))


def g_steam_puff(ctx, seed, p):
    x = ctx.u * 2 - 1
    y = ctx.v * 2 - 1
    r = math.sqrt(x * x + y * y)
    n = fbm(ctx.u * 4, ctx.v * 4, seed, 3)
    a = smoothstep(1.0, 0.15, r + (n - 0.5) * 0.5)
    c = p.get("color", (1.0, 1.0, 1.0))
    return (c[0], c[1], c[2], a * p.get("alpha", 0.9))


def g_fire(ctx, seed, p):
    x = ctx.u * 2 - 1
    y = ctx.v
    n = fbm(ctx.u * 5, ctx.v * 3, seed, 3)
    k = clamp01((1.0 - abs(x) * (1.3 - y * 0.6)) * (0.3 + y) + (n - 0.5) * 0.6)
    c = mix(hexc("8A1A04"), hexc("FF8A20"), smoothstep(0.1, 0.5, k))
    c = mix(c, hexc("FFF0A0"), smoothstep(0.55, 0.9, k))
    return (c[0], c[1], c[2], smoothstep(0.05, 0.35, k))


def g_flat(ctx, seed, p):
    return p.get("color", (0.5, 0.5, 0.5))


GENERATORS = {
    "noise": g_noise, "fbm": g_fbm, "brass": g_brass, "gold": g_gold, "copper": g_copper, "iron": g_iron,
    "soot": g_soot, "enamel": g_enamel, "wood": g_wood, "marble": g_marble, "stone": g_stone,
    "leather": g_leather, "hide": g_hide, "ceramic": g_ceramic, "clay": g_clay,
    "fabric_stripes": g_fabric_stripes, "glass": g_glass, "frost": g_frost, "env_gradient": g_env_gradient,
    "steam_puff": g_steam_puff, "fire": g_fire, "flat": g_flat,
}


def generator(name):
    return GENERATORS[name]


# ---------------------------------------------------------------- image-form generators (section 5.5 API)

def _img(name):
    def f(w, h, seed=0, params=None):
        return image_from(GENERATORS[name], w, h, seed, params or {})
    f.__name__ = name
    return f


noise_img = _img("noise")
fbm_img = _img("fbm")
brass = _img("brass")
copper = _img("copper")
iron = _img("iron")
soot = _img("soot")
enamel = _img("enamel")
wood = _img("wood")
marble = _img("marble")
stone = _img("stone")
leather = _img("leather")
hide = _img("hide")
ceramic = _img("ceramic")
clay = _img("clay")
fabric_stripes = _img("fabric_stripes")
glass = _img("glass")
frost = _img("frost")
env_gradient = _img("env_gradient")
steam_puff = _img("steam_puff")
fire = _img("fire")


def brushed_metal(w, h, seed=0, params=None):
    p = dict(params or {})
    p["brushed"] = True
    p.setdefault("streak", False)
    color = p.get("color")
    if color:
        p["palette"] = {"base": color, "light_c": mix(color, (1, 1, 1), 0.5), "dark": scale(color, 0.4),
                        "bounce": scale(color, 0.75)}
    return image_from(g_brass, w, h, seed, p)


def gauge(w, h, seed=0, params=None):
    """A dial face: white enamel, 0-12 ticks, coloured bands, a needle (section 5.5)."""
    from . import paint2d
    return paint2d.gauge_face(w, h, params or {})


def label(w, h, seed=0, params=None):
    from . import paint2d
    return paint2d.label(w, h, params or {})


def chalkboard(w, h, seed=0, params=None):
    from . import paint2d
    return paint2d.chalkboard(w, h, seed, params or {})
