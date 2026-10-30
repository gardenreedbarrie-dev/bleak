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


def image_lowres(fn, w, h, seed=0, params=None, size_yd=None, factor=4):
    """image_from evaluated on a grid `factor` times coarser and upsampled bilinearly (section 5.5, "Build
    cost": noise layers at 1/2 or less): for big, low-frequency backgrounds such as a chalkboard's slate."""
    sw = size_yd[0] if size_yd else w / 256.0
    sh = size_yd[1] if size_yd else h / 256.0
    lw, lh = max(2, (w + factor - 1) // factor + 1), max(2, (h + factor - 1) // factor + 1)
    low = image_from(fn, lw, lh, seed, params, (sw * lw / (w / float(factor)), sh * lh / (h / float(factor))))
    img = Img(w, h)
    for y in range(h):
        fy = min(lh - 1.001, (y + 0.5) / factor - 0.5)
        fy = max(0.0, fy)
        y0 = int(fy)
        ty = fy - y0
        for x in range(w):
            fx = max(0.0, min(lw - 1.001, (x + 0.5) / factor - 0.5))
            x0 = int(fx)
            tx = fx - x0
            i00 = y0 * lw + x0
            i10, i01, i11 = i00 + 1, i00 + lw, i00 + lw + 1
            k00, k10, k01, k11 = (1 - tx) * (1 - ty), tx * (1 - ty), (1 - tx) * ty, tx * ty
            j = y * w + x
            img.r[j] = low.r[i00] * k00 + low.r[i10] * k10 + low.r[i01] * k01 + low.r[i11] * k11
            img.g[j] = low.g[i00] * k00 + low.g[i10] * k10 + low.g[i01] * k01 + low.g[i11] * k11
            img.b[j] = low.b[i00] * k00 + low.b[i10] * k10 + low.b[i01] * k01 + low.b[i11] * k11
            img.a[j] = low.a[i00] * k00 + low.a[i10] * k10 + low.a[i01] * k01 + low.a[i11] * k11
    return img


def tile_image(fn, w, h, seed=0, params=None, size_yd=(1.0, 1.0), blend=0.25):
    """A seamless, wrapping w x h tile of a point generator over size_yd yards (build.PropDef.tiles): the
    generator is evaluated over the tile and, in a band of `blend` of the tile along its left and top edges,
    cross-faded with its values one tile further on, so each edge runs on into the opposite one. The chart is
    flat and faces up (ctx.n = +Z, ctx.pos = (s, 0, h - t)): use generators that do not need a real normal
    (wood, planks, marble, hide, stone, slabs, fabric)."""
    params = params or {}
    sw, sh = size_yd
    bx, by = max(1.0, w * blend), max(1.0, h * blend)
    img = Img(w, h)

    def ev(s, t):
        c = fn(Ctx(s, t, (s, 0.0, sh - t), (0.0, 0.0, 1.0), 0.0, 1.0, sw, sh), seed, params)
        return c if len(c) == 4 else (c[0], c[1], c[2], 1.0)

    for y in range(h):
        t = (y + 0.5) / h * sh
        ky = smoothstep(0.0, 1.0, (y + 0.5) / by) if y + 0.5 < by else 1.0
        for x in range(w):
            s = (x + 0.5) / w * sw
            kx = smoothstep(0.0, 1.0, (x + 0.5) / bx) if x + 0.5 < bx else 1.0
            c = ev(s, t)
            if kx < 1.0 or ky < 1.0:
                cx = ev(s + sw, t) if kx < 1.0 else c
                cy = ev(s, t + sh) if ky < 1.0 else c
                cxy = ev(s + sw, t + sh) if kx < 1.0 and ky < 1.0 else (cx if ky >= 1.0 else cy)
                c = tuple(ky * (kx * c[i] + (1 - kx) * cx[i]) + (1 - ky) * (kx * cy[i] + (1 - kx) * cxy[i])
                          for i in range(4))
            img.set(x, y, c[:3], c[3])
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
# Dark iron (the Orgrimmar family): its darkest painted value stays about 0.2, and its worn edges are a bright
# steel, so an iron box keeps its shape and inner detail under night light instead of going black. IRON_DEEP is
# the old near-black iron, kept for the few Stormwind parts that use it (EspressoSW's portafilter baskets).
IRON = dict(light_c=hexc("A8ACB4"), base=hexc("5C5E66"), dark=hexc("34343C"), bounce=hexc("4C4640"),
            patina=hexc("6A4630"))
IRON_DEEP = dict(light_c=hexc("8A8C94"), base=hexc("4A4B52"), dark=hexc("1E1E24"), bounce=hexc("3A3530"),
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
    pal = p.get("palette", IRON)
    c = metal(ctx, seed, p, pal["light_c"], pal["base"], pal["dark"], pal["bounce"], pal["patina"],
              p.get("rust", 0.3))
    grid = p.get("rivet_grid")
    if grid:
        c = rivets(ctx, c, grid, p.get("rivet_r", 0.012), pal["light_c"], pal["dark"])
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
    # the Orgrimmar dark timber: as dark as "dark" to the eye in day light, but its darkest grain stays about 0.16
    # so a timber bar keeps its planks and panels under night light
    "orgdark": (hexc("563A26"), hexc("3A2618"), hexc("886240")),
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
    """Hide (Orgrimmar panels, the parasol canopy, tags): mottled leather-brown or red (p["color"]) with darker
    blotches. Options: p["edge"] yd of darker, burnt-looking rawhide along the chart edges; p["stitch"] the
    margin (yd) of thread stitching around the panel (p["cross"] for X-shaped lacing; see stitches());
    p["scuffs"] 0..1 of pale scuff marks."""
    base = p.get("color", hexc("9C4A2A"))
    v = fbm(ctx.s * 5, ctx.t * 5, seed, 3)
    spots = smoothstep(0.62, 0.72, fbm(ctx.s * 9 + 3, ctx.t * 9, seed + 1, 2))
    c = mix(scale(base, 0.85), scale(base, 1.15), v)
    c = mix(c, scale(base, 0.6), spots * 0.5)
    if p.get("scuffs"):
        sc = smoothstep(0.7, 0.85, noise(ctx.s * 3.0, ctx.t * 12.0, seed + 2))
        c = mix(c, mix(base, hexc("E8C8A0"), 0.5), sc * 0.5 * p["scuffs"])
    if p.get("edge"):
        e = edge_dist(ctx) + (noise(ctx.s * 14.0, ctx.t * 14.0, seed + 3) - 0.5) * p["edge"] * 0.8
        c = mix(c, scale(base, 0.45), smoothstep(p["edge"], 0.0, e) * 0.8)
    if p.get("stitch"):
        c = stitches(ctx, c, p["stitch"], p.get("stitch_step", 0.04), p.get("stitch_w", 0.008),
                     cross=p.get("cross", False))
    return c


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
    """A soft puff: alpha falls off smoothly from the centre to nothing at the sprite's edge (a cubic falloff,
    with the noise only modulating its strength), so overlapping puffs blend into a plume instead of showing
    hard round edges."""
    x = ctx.u * 2 - 1
    y = ctx.v * 2 - 1
    r = math.sqrt(x * x + y * y)
    n = fbm(ctx.u * 4, ctx.v * 4, seed, 3)
    a = smoothstep(1.0, 0.0, r) ** 1.6 * (0.7 + 0.6 * n)
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


# ------------------------------------------------------------------------------------ chart-space helpers
# Shared paint helpers for the props (section 5.5: rivets, bolts and seams are painted, not modelled). All
# distances are in yards on the texel's chart (ctx.s to the right, ctx.t downward, as seen from outside).

RIVET_HI = hexc("FFF2B4")   # a lit brass or iron rivet head
RIVET_LO = hexc("3A2006")   # its dark rim
IRON_RIVET_HI = hexc("B8BCC4")
IRON_RIVET_LO = hexc("101014")


def inset_panel(ctx, c, margin=0.05, width=0.012, raised=True, light=(1.0, 0.95, 0.85), dark=(0.05, 0.03, 0.02)):
    """A painted panel line `margin` yd in from the chart edges (cupboard doors, fascia panels, plates): a
    `width` groove whose upper-left side is shadowed and lower-right side lit (raised=True: the panel inside
    stands proud of its frame), with a faint lit lip just outside the groove."""
    s, t, cw, ch = ctx.s, ctx.t, ctx.cw, ctx.ch
    dl, dr, dt, db = s - margin, cw - margin - s, t - margin, ch - margin - t
    inside = min(dl, dr, dt, db)
    if -width <= inside <= 0.0:
        k = clamp01(-inside / width)
        upper_left = min(dl, dt) <= min(dr, db)
        if raised == upper_left:
            return mix(c, dark, 0.55 * (1.0 - abs(k - 0.5)))
        return mix(c, light, 0.4 * (1.0 - abs(k - 0.5)))
    if -width * 2.0 <= inside < -width:
        return mix(c, light, 0.15)
    return c


def ramp(stops, k):
    """Piecewise-linear colour ramp: stops [(k0, colour), (k1, colour), ...] with increasing k."""
    if k <= stops[0][0]:
        return stops[0][1]
    for (k0, c0), (k1, c1) in zip(stops, stops[1:]):
        if k <= k1:
            return mix(c0, c1, (k - k0) / ((k1 - k0) or 1.0))
    return stops[-1][1]


def edge_dist(ctx):
    """Distance from the texel to the nearest edge of its chart (yd): frames, bevels, worn panel edges."""
    return min(ctx.s, ctx.cw - ctx.s, ctx.t, ctx.ch - ctx.t)


def rivet_dot(c, dx, dy, r, hi=RIVET_HI, lo=RIVET_LO):
    """One bold painted rivet seen from its centre at offset (dx, dy) yd (dy downward): a head lit from the
    upper left, a dark rim and a soft drop shadow toward the lower right. Outside it, c is returned unchanged.
    Keep r at 0.012 yd or more: smaller heads blur away at mip 1."""
    d = math.hypot(dx, dy)
    if d < r:
        k = clamp01(0.55 - dy / r * 0.55 - dx / r * 0.25)
        return mix(scale(c, 0.78), hi, k * 0.9)
    if d < r * 1.55:
        return mix(c, lo, smoothstep(r * 1.55, r, d) * 0.75)
    sd = math.hypot(dx - r * 0.35, dy - r * 0.45)
    if sd < r * 1.5:
        return mix(c, scale(c, 0.55), smoothstep(r * 1.5, r, sd) * 0.5)
    return c


def frame_rivets(ctx, c, margin, step, r, hi=RIVET_HI, lo=RIVET_LO):
    """Rivets on a frame band `margin` yd in from every chart edge, evenly spaced (about `step` apart) along each
    side with one in every corner: the riveted frame of a panel, a plate or a box face."""
    s, t, cw, ch = ctx.s, ctx.t, ctx.cw, ctx.ch
    m = margin
    best = None
    for span, along, across, fixed, horiz in ((cw - 2 * m, s, t, (m, ch - m), True),
                                              (ch - 2 * m, t, s, (m, cw - m), False)):
        span = max(span, 1e-6)
        n = max(1, int(round(span / step)))
        st = span / n
        k = min(n, max(0, int(round((along - m) / st))))
        a0 = m + k * st
        for f in fixed:
            d = math.hypot(along - a0, across - f)
            if best is None or d < best[0]:
                best = (d, s - a0 if horiz else s - f, t - f if horiz else t - a0)
    return rivet_dot(c, best[1], best[2], r, hi, lo)


def rivet_lines(ctx, c, rows=(), cols=(), step=0.08, r=0.013, hi=RIVET_HI, lo=RIVET_LO, phase=None):
    """Rivets along horizontal chart lines t = row and vertical lines s = col (yd), `step` apart (offset by
    `phase`, default half a step): boiler seams, iron bands, straps, the rim of a funnel."""
    ph = step / 2 if phase is None else phase
    best = None
    for row in rows:
        a0 = ph + round((ctx.s - ph) / step) * step
        d = math.hypot(ctx.s - a0, ctx.t - row)
        if best is None or d < best[0]:
            best = (d, ctx.s - a0, ctx.t - row)
    for col in cols:
        a0 = ph + round((ctx.t - ph) / step) * step
        d = math.hypot(ctx.s - col, ctx.t - a0)
        if best is None or d < best[0]:
            best = (d, ctx.s - col, ctx.t - a0)
    if best is None:
        return c
    return rivet_dot(c, best[1], best[2], r, hi, lo)


def stitches(ctx, c, margin=0.025, step=0.035, width=0.008, color=hexc("E6D2A4"), hole=hexc("24140A"),
             edges="lrtb", cross=False):
    """Painted stitching `margin` yd in from the chart edges named in `edges` (l, r, t, b): thread dashes
    `step` apart with a dark hole at each end, or X-shaped cross-stitches (cross=True) lacing a hide panel."""
    best = None
    for e, across, along in (("l", ctx.s, ctx.t), ("r", ctx.cw - ctx.s, ctx.t), ("t", ctx.t, ctx.s),
                             ("b", ctx.ch - ctx.t, ctx.s)):
        if e not in edges:
            continue
        d = abs(across - margin)
        if best is None or d < best[0]:
            best = (d, across - margin, along)
    if best is None:
        return c
    _d, off, along = best
    q = (along % step) / step - 0.5          # -0.5..0.5 within one stitch
    if cross:
        half = step * 0.42
        x = q * step
        k = min(abs(off - x * 0.9), abs(off + x * 0.9))
        if abs(x) < half and k < width:
            return mix(color, scale(color, 0.7), clamp01(k / width))
        if abs(off) < width * 1.2 and abs(abs(x) - half) < width * 0.9:
            return hole
        return c
    if abs(off) < width:
        if abs(q) < 0.3:
            return mix(color, scale(color, 0.72), clamp01(abs(off) / width) * 0.8)
        if abs(abs(q) - 0.36) < 0.06:
            return hole
    return c


# --------------------------------------------------------------------------------- more point generators
# Materials the section 5.8.1 designs share: bone and ivory, rough planks, stone slabs, slate, bottle and
# frosted glass, glazed clay, rope, red lacquer, fire and ember glow, the frost rune, beans, shake, cream,
# coffee, silver. Each is low frequency (section 5.5) and takes its colours from params.

def g_bone(ctx, seed, p):
    """Bone and ivory (tusks, bone handles, tips): a warm cream with broad yellowing, a soft sheen on top and a
    darker underside, faint growth bands across the length, a few long age cracks running along it (a dark line
    with a lit lip) and, with p["root"] (the chart v of the root end along the length: 0 or 1), a darker root
    with a stained collar. kind "ivory" (default, creamy and smooth) or "bone" (greyer, a few pits). The length
    runs along the chart's t (sweeps, capsules); p["along"] "s" turns it."""
    kind = p.get("kind", "ivory")
    if kind == "bone":
        base, lite, dark, stain = hexc("D6CCB0"), hexc("F6F0DE"), hexc("6E6450"), hexc("9A8A64")
    else:
        base, lite, dark, stain = hexc("EAD8AA"), hexc("FFF6DC"), hexc("7A5A30"), hexc("C29A58")
    base = p.get("color", base)
    if p.get("along", "t") == "t":
        a, b, bw, frac = ctx.t, ctx.s, ctx.cw, ctx.v
    else:
        a, b, bw, frac = ctx.s, ctx.t, ctx.ch, ctx.u
    x, y, z = ctx.pos
    v = fbm3(x * 4.0, y * 4.0, z * 4.0, seed, 3)
    c = mix(base, mix(base, stain, 0.55), smoothstep(0.45, 0.8, v))
    n = ctx.n
    c = mix(c, lite, smoothstep(0.1, 0.9, n[2]) * 0.5)
    c = mix(c, scale(dark, 1.4), smoothstep(-0.15, -0.9, n[2]) * 0.35)
    band = 0.5 + 0.5 * math.sin(a * 38.0 + 3.0 * noise(a * 3.0, 0.5, seed + 3))
    c = scale(c, 0.95 + 0.07 * band)
    for k in range(p.get("cracks", 3)):
        b0 = _h(k, 1, 9, seed) * bw + (noise(a * 5.0, k * 3.7, seed + 5) - 0.5) * 0.035
        a0 = _h(k, 2, 9, seed) * 0.5
        a1 = a0 + 0.25 + _h(k, 3, 9, seed) * 0.5
        fa = frac
        if not a0 <= fa <= a1:
            continue
        taper = smoothstep(a0, a0 + 0.08, fa) * smoothstep(a1, a1 - 0.08, fa)
        w = 0.0045 * (0.4 + 0.6 * taper)
        d = b - b0
        if abs(d) < w:
            c = mix(c, dark, 0.75 * taper)
        elif 0 < d < w + 0.006:
            c = mix(c, lite, 0.35 * taper)
    if kind == "bone":
        pit = noise3(x * 40.0, y * 40.0, z * 40.0, seed + 7)
        c = mix(c, scale(dark, 1.2), smoothstep(0.78, 0.9, pit) * 0.45)
    root = p.get("root")
    if root is not None:
        dr = frac if root == 0 else 1.0 - frac
        c = mix(c, mix(stain, dark, 0.5), smoothstep(0.35, 0.0, dr) * 0.55)
        if dr < 0.05:
            c = mix(c, scale(dark, 0.8), 0.5)
    if ctx.curv > 0:
        c = mix(c, lite, clamp01(ctx.curv) * 0.4)
    elif ctx.curv < 0:
        c = mix(c, dark, clamp01(-ctx.curv) * 0.4)
    return c


def g_planks(ctx, seed, p):
    """Rough planks (Orgrimmar timber, the oak ice chest, crates, the plank chalkboard): boards along the chart's
    long axis (p["along"] "s" or "t" overrides), p["count"] of them across the chart or about p["width"] yd
    wide, each with its own tone and grain; dark gaps (p["gap"] yd) with a lit lip on one side and a shadow on
    the other; dark end grain and ragged ends (p["ragged"] yd) at the chart's ends; knots (p["knots"] per
    board); with p["nails"], an iron nail head near each end of every board. Pair it with geom.plank_edges or
    geom.planks so the geometry is as crooked as the paint."""
    base, dark, lite = WOODS[p.get("kind", "timber")]
    along_s = p.get("along", "long")
    if along_s == "long":
        along_s = "s" if ctx.cw >= ctx.ch else "t"
    if along_s == "s":
        a, b, A, Bw = ctx.s, ctx.t, ctx.cw, ctx.ch
    else:
        a, b, A, Bw = ctx.t, ctx.s, ctx.ch, ctx.cw
    n = p.get("count") or max(1, int(round(Bw / p.get("width", 0.16))))
    pw = Bw / n
    i = min(n - 1, max(0, int(b / pw)))
    q = (b - i * pw) / pw
    tone = _h(i, 7, 3, seed)
    pbase = mix(base, lite, 0.3 * (tone - 0.5) * 2) if tone > 0.5 else mix(base, dark, 0.35 * (0.5 - tone) * 2)
    # broad painted grain (features of 0.03 yd or more, so the mips keep it): long light and dark streaks
    # along the board, a few darker grain strokes, and a lighter middle where the plane took the top off
    warp = fbm(a * 1.5, (b + i * 1.7) * 4.0, seed + 3, 2)
    g = noise(a * 0.9, (b + i * 3.1) * 10.0 + warp * 3.0, seed + i)
    g2 = noise(a * 0.5, (b + i * 2.3) * 5.0 + warp * 2.0, seed + 5)
    c = mix(pbase, dark, smoothstep(0.5, 0.85, g) * 0.75)
    c = mix(c, lite, smoothstep(0.55, 0.9, g2) * 0.45)
    for k in range(2):
        gb = (0.2 + 0.6 * _h(i, k, 17, seed)) * pw + (noise(a * 2.5, k * 5.0 + i, seed + 9) - 0.5) * pw * 0.5
        dd = abs((b - i * pw) - gb)
        if dd < 0.009:
            c = mix(c, scale(dark, 0.8), smoothstep(0.009, 0.0, dd) * 0.7)
    for k in range(p.get("knots", 1)):
        if _h(i, k, 13, seed) < 0.4:
            continue
        ka = (0.15 + 0.7 * _h(i, k, 14, seed)) * A
        kb = (i + 0.3 + 0.4 * _h(i, k, 15, seed)) * pw
        kr = 0.012 + 0.008 * _h(i, k, 16, seed)
        d = math.hypot((a - ka) / 1.5, b - kb) / kr
        if d < 1.0:
            c = mix(scale(dark, 0.55), scale(dark, 0.9), smoothstep(0.3, 1.0, d))
        elif d < 1.6:
            c = mix(c, lite, smoothstep(1.6, 1.0, d) * 0.35)
    gap = p.get("gap", 0.012) / pw
    if q < gap or q > 1.0 - gap * 0.35:
        return scale(dark, 0.4)
    if q < gap + 0.08:
        c = mix(c, lite, (1.0 - (q - gap) / 0.08) * 0.35)
    elif q > 1.0 - gap * 0.35 - 0.12:
        c = mix(c, scale(dark, 0.6), smoothstep(1.0 - gap * 0.35 - 0.12, 1.0 - gap * 0.35, q) * 0.6)
    rag = p.get("ragged", 0.03)
    e0 = a - (_h(i, 21, 3, seed) - 0.3) * rag
    e1 = (A - a) - (_h(i, 22, 3, seed) - 0.3) * rag
    de = min(e0, e1)
    if de < 0:
        return scale(dark, 0.45)
    if de < 0.025:
        c = mix(c, scale(dark, 0.85), (1.0 - de / 0.025) * 0.55)
    if p.get("nails"):
        for na in (0.045, A - 0.045):
            c = rivet_dot(c, a - na if along_s == "s" else b - (i + 0.5) * pw,
                          b - (i + 0.5) * pw if along_s == "s" else a - na, 0.011, IRON_RIVET_HI, IRON_RIVET_LO)
    if ctx.curv > 0:
        c = mix(c, lite, clamp01(ctx.curv) * 0.45)
    elif ctx.curv < 0:
        c = mix(c, scale(dark, 0.6), clamp01(-ctx.curv) * 0.5)
    return c


def g_slabs(ctx, seed, p):
    """Stone slabs (the Orgrimmar cold-box lining, a fire box, hearths): big slabs about p["slab"] (w, h) yd in
    staggered rows, each with its own tone, chipped corners, a lit upper edge and a dark lower one, dark joints
    (p["joint"] yd) and now and then a crack. p["color"] the stone, p["mortar"] the joints."""
    base = p.get("color", hexc("7C7266"))
    mortar = p.get("mortar", hexc("2A2420"))
    sw, sh = p.get("slab", (0.34, 0.22))
    joint = p.get("joint", 0.014)
    s, t = ctx.s, ctx.t
    row = math.floor(t / sh)
    off = _h(row, 1, 5, seed) * sw
    col = math.floor((s + off) / sw)
    qx = (s + off) - col * sw
    qy = t - row * sh
    jit = (noise(t * 9.0, col * 1.3, seed + 1) - 0.5) * 0.02
    jit2 = (noise(s * 9.0, row * 1.7, seed + 2) - 0.5) * 0.02
    ex = min(qx, sw - qx) + jit
    ey = min(qy, sh - qy) + jit2
    tone = _h(col, row, 5, seed)
    c = scale(base, 0.8 + 0.32 * tone)
    c = mix(c, hexc("8C90A0"), _h(col, row, 6, seed) * 0.25)
    c = mix(c, scale(c, 0.85), smoothstep(0.4, 0.75, fbm(s * 6.0, t * 6.0, seed + 3, 3)) * 0.6)
    cd = math.hypot(min(qx, sw - qx), min(qy, sh - qy))
    chip = 0.02 + 0.035 * _h(col, row, 7, seed)
    if ex < joint * 0.5 or ey < joint * 0.5 or cd < chip * 0.6:
        return mix(mortar, scale(mortar, 1.3), noise(s * 20.0, t * 20.0, seed + 4))
    if qy < joint * 0.5 + 0.02 and ey < 0.02 + joint * 0.5:
        c = mix(c, hexc("D8D0C0"), 0.22)
    elif sh - qy < 0.03 + joint * 0.5 and ey < 0.03 + joint * 0.5:
        c = mix(c, scale(mortar, 1.2), 0.45)
    if ex < joint + 0.012 or ey < joint + 0.012:
        c = scale(c, 0.85)
    if _h(col, row, 8, seed) < p.get("cracks", 0.35):
        ang = _h(col, row, 9, seed) * math.pi
        cx0, cy0 = sw * (0.3 + 0.4 * _h(col, row, 10, seed)), sh * 0.5
        d = abs((qx - cx0) * math.sin(ang) - (qy - cy0) * math.cos(ang))
        d += (noise(qx * 30.0, qy * 30.0, seed + 11) - 0.5) * 0.01
        along = abs((qx - cx0) * math.cos(ang) + (qy - cy0) * math.sin(ang))
        if d < 0.004 and along < sw * 0.35:
            c = mix(c, mortar, 0.8)
    if ctx.curv > 0:
        c = mix(c, hexc("E8E2D4"), clamp01(ctx.curv) * 0.35)
    return c


def g_slate(ctx, seed, p):
    """Chalkboard slate: dark green-grey (p["color"]) with broad value drift, a haze of wiped chalk in wide
    eraser swipes and heavier dust toward the bottom edge, where the chalk tray is (p["dust"] 0..1)."""
    base = p.get("color", hexc("26302C"))
    dust = p.get("dust", 0.5)
    chalk = hexc("C4CCC4")
    s, t = ctx.s, ctx.t
    v = fbm(s * 3.0, t * 3.0, seed, 3)
    c = mix(scale(base, 0.85), scale(base, 1.2), v)
    sw = noise(s * 1.1, t * 4.5 + noise(s * 2.0, t * 2.0, seed + 1) * 2.2, seed + 2)
    c = mix(c, chalk, smoothstep(0.55, 0.92, sw) * 0.2 * dust)
    k = smoothstep(0.72, 1.0, ctx.v) * (0.45 + 0.55 * noise(s * 8.0, t * 3.0, seed + 3))
    c = mix(c, chalk, k * 0.32 * dust)
    if ctx.curv > 0:
        c = mix(c, scale(base, 1.5), clamp01(ctx.curv) * 0.3)
    return c


def _streaks(ctx, c, a, k_c=1.0):
    """g_glass's vertical highlight streaks around a round chart: (colour, alpha)."""
    for centre, wdt in ((0.18, 0.05), (0.26, 0.015), (0.68, 0.03)):
        d = abs(ctx.u - centre)
        if d < wdt:
            k = smoothstep(wdt, 0.0, d)
            c = mix(c, (1.0, 1.0, 1.0), k * k_c)
            a = max(a, 0.72 + 0.18 * k)
    return c, a


def g_bottle_glass(ctx, seed, p):
    """Bottle and jar glass with its contents (syrup bottles, jars, the blender jar): tinted glass (p["tint"],
    alpha p["alpha"] about 0.34) with g_glass's streak highlights and darker rims; below the fill level the
    liquid (p["liquid"]) at alpha 0.88 with a bright meniscus line. The level is p["level_z"] (model z) or
    p["level_v"] (chart v from the top of the lathe, default 0.3). Use with the glass preset."""
    tint = p.get("tint", hexc("D8EEF0"))
    liquid = p.get("liquid")
    a = p.get("alpha", 0.34)
    c = tint
    if liquid is not None:
        if "level_z" in p:
            depth = p["level_z"] - ctx.pos[2]
        else:
            depth = (ctx.v - p.get("level_v", 0.3)) * ctx.ch
        if depth >= 0.0:
            c = mix(liquid, scale(liquid, 0.72), smoothstep(0.0, 0.25, depth) * 0.6)
            a = p.get("liquid_alpha", 0.88)
            if depth < 0.01:
                c = mix(c, (1.0, 1.0, 1.0), 0.45)
                a = 0.95
    c, a = _streaks(ctx, c, a, 0.85 if liquid is not None else 1.0)
    rim = min(ctx.v, 1.0 - ctx.v)
    if rim < 0.05:
        c = mix(c, scale(tint, 0.55), 0.5)
        a = max(a, 0.55)
    return (c[0], c[1], c[2], a)


def g_frosted_glass(ctx, seed, p):
    """Frosted glass (the cold-box lid): white frost feathering in from the chart's edges (p["edge"] yd) over a
    clearer, faintly blue centre, soft frost ferns and a broad diagonal sheen; alpha from p["alpha"] (0.3) in
    the centre to 0.85 at the edges, so what lies under the lid still reads."""
    tint = p.get("tint", hexc("C4E2F4"))
    edge = p.get("edge", 0.12)
    s, t = ctx.s, ctx.t
    f = fbm(s * 8.0, t * 8.0, seed, 3)
    k = smoothstep(edge, 0.0, edge_dist(ctx) + (f - 0.5) * edge * 0.9)
    fern = 1.0 - abs(noise(s * 14.0, t * 14.0, seed + 1) - 0.5) * 2.0
    fern = smoothstep(0.75, 0.95, fern) * (0.3 + 0.7 * k)
    c = mix(tint, (1.0, 1.0, 1.0), clamp01(k * 0.8 + fern * 0.5))
    a = p.get("alpha", 0.3) + (0.85 - p.get("alpha", 0.3)) * clamp01(k + fern * 0.4)
    sheen = smoothstep(0.08, 0.0, abs((ctx.u - ctx.v) * 0.7 + 0.15))
    c = mix(c, (1.0, 1.0, 1.0), sheen * 0.5)
    return (c[0], c[1], c[2], max(a, 0.55 * sheen + p.get("alpha", 0.3)))


def g_glaze(ctx, seed, p):
    """Clay with a glaze poured over the top and dripping down (the Orgrimmar mug, jugs, pots): matte speckled
    clay (p["color"]), a glossy glaze (p["glaze"]) in a band from the rim (p["band"] yd) with drips of
    different lengths (up to p["drip"] yd) ending in darker beads, and the inside fully glazed. With p["top"]
    (the rim's model z) the drips run down the outer wall by angle around p["center"] (x, y), p["radius"] the
    wall's radius; without it they run down the chart from its top edge."""
    clay = p.get("color", hexc("B8875A"))
    glaze = p.get("glaze", hexc("9C2A1F"))
    band = p.get("band", 0.045)
    drip = p.get("drip", 0.08)
    spacing = p.get("spacing", 0.04)
    x, y, z = ctx.pos
    inside = False
    if "top" in p:
        cx, cy = p.get("center", (0.0, 0.0))
        rx, ry = x - cx, y - cy
        rr = math.hypot(rx, ry) or 1.0
        inside = (ctx.n[0] * rx + ctx.n[1] * ry) / rr < -0.25
        a = math.atan2(ry, rx) * p.get("radius", 0.08)
        d = p["top"] - z
    else:
        a, d = ctx.s, ctx.t
    glazed = inside or d < band + (noise(a * 30.0, 0.5, seed) - 0.5) * 0.012
    pool = 0.0
    if not glazed:
        k = math.floor(a / spacing)
        for j in (k - 1, k, k + 1):
            if _h(j, 4, 2, seed) < 0.22:
                continue
            cxj = (j + 0.5 + (_h(j, 1, 2, seed) - 0.5) * 0.3) * spacing
            wj = spacing * (0.16 + 0.12 * _h(j, 3, 2, seed))
            L = band + drip * (0.25 + 0.75 * _h(j, 2, 2, seed))
            dx = a - cxj
            if band - 0.01 <= d <= L - wj and abs(dx) < wj * (0.75 + 0.25 * (L - d) / L):
                glazed = True
                pool = 0.2
                break
            if math.hypot(dx, d - (L - wj)) < wj:
                glazed = True
                pool = 0.55
                break
    if glazed:
        c = mix(glaze, scale(glaze, 0.6), pool)
        c = mix(c, scale(glaze, 1.25), smoothstep(-0.1, 0.8, ctx.n[2]) * 0.35)
        c = mix(c, mix(glaze, (1.0, 0.92, 0.85), 0.55), _azimuth_streak(ctx.n, 0.55, 0.3) * 0.55)
        if ctx.curv > 0:
            c = mix(c, (1.0, 0.9, 0.85), clamp01(ctx.curv) * 0.4)
        return c
    c = mix(scale(clay, 0.88), scale(clay, 1.1), fbm3(x * 9.0, y * 9.0, z * 9.0, seed + 2, 2))
    sp = noise3(x * 45.0, y * 45.0, z * 45.0, seed + 3)
    c = mix(c, scale(clay, 0.55), smoothstep(0.8, 0.9, sp) * 0.6)
    if ctx.curv > 0:
        c = mix(c, scale(clay, 1.3), clamp01(ctx.curv) * 0.4)
    return c


def g_rope(ctx, seed, p):
    """Twisted rope (lashings, handles, the Orgrimmar parasol and rack): p["strands"] strands (3) spiralling
    along it, one twist every p["pitch"] yd (0.15), dark grooves between them, fibre streaks and a lit top. The
    rope runs along the chart's long axis (a torus band's s, a sweep's t; p["along"] overrides) and the other
    axis goes once around it."""
    base = p.get("color", hexc("B8955A"))
    along_s = p.get("along", "long")
    if along_s == "long":
        along_s = "s" if ctx.cw >= ctx.ch else "t"
    if along_s == "s":
        a, b, circ = ctx.s, ctx.t, ctx.ch
    else:
        a, b, circ = ctx.t, ctx.s, ctx.cw
    strands = p.get("strands", 3)
    q = strands * (b / circ + a / p.get("pitch", 0.15))
    f = q - math.floor(q)
    prof = math.sin(math.pi * f)
    c = mix(scale(base, 0.32), base, smoothstep(0.0, 0.65, prof))
    c = mix(c, mix(base, (1.0, 0.96, 0.85), 0.4), smoothstep(0.75, 1.0, prof) * 0.4)
    fib = noise(f * 3.0 + math.floor(q) * 3.1, a * 12.0, seed)
    c = scale(c, 0.9 + 0.16 * fib)
    c = mix(c, scale(c, 1.15), smoothstep(0.0, 0.9, ctx.n[2]) * 0.4)
    return c


def g_lacquer(ctx, seed, p):
    """Red lacquer (the Orgrimmar accents: p["color"] B5402F, or 9C2A1F for the darker bands): a deep glossy red
    with broad value drift, a gloss band near the top of each panel and toward the light on rounds, darker
    undersides, and worn edges (the bake's curvature, p["worn"] 0..1) showing the black iron under it."""
    base = p.get("color", hexc("B5402F"))
    x, y, z = ctx.pos
    v = fbm3(x * 3.5, y * 3.5, z * 3.5, seed, 3)
    c = mix(scale(base, 0.8), scale(base, 1.12), v)
    c = scale(c, 0.95 + 0.08 * noise3(ctx.s * 8.0, ctx.t * 1.5, 0.5, seed + 13))
    sheen = mix(base, hexc("FFC4A8"), 0.55)
    gl = smoothstep(0.3, 0.06, ctx.v) * smoothstep(0.0, 0.05, ctx.v)
    c = mix(c, sheen, gl * p.get("gloss", 0.4))
    c = mix(c, sheen, _azimuth_streak(ctx.n, 0.55, 0.35) * 0.4)
    c = mix(c, sheen, smoothstep(0.6, 1.0, ctx.n[2]) * 0.3)
    c = mix(c, scale(base, 0.45), smoothstep(-0.2, -0.85, ctx.n[2]) * 0.45)
    worn = p.get("worn", 0.6)
    if ctx.curv > 0 and worn:
        c = mix(c, hexc("2C2826"), clamp01(ctx.curv * 1.8 - 0.3) * worn)
    elif ctx.curv < 0:
        c = mix(c, scale(base, 0.4), clamp01(-ctx.curv) * 0.5)
    return c


def g_fire_glow(ctx, seed, p):
    """The fire behind a stove's grate window (the glow preset: unlit and additive, so the alpha is the
    intensity): a bed of glowing coals along the bottom of the chart and p["tongues"] tongues of flame rising
    from it, deep red to orange to a yellow-white core."""
    u, y = ctx.u, 1.0 - ctx.v
    tong = 0.5 + 0.5 * math.sin(u * 2.0 * math.pi * p.get("tongues", 3) + fbm(u * 3.0, y * 2.0, seed, 2) * 3.0)
    height = 0.3 + 0.5 * tong * (0.6 + 0.4 * fbm(u * 5.0, 0.3, seed + 1, 2))
    k = clamp01(1.0 - y / height)
    k *= 0.7 + 0.6 * fbm(u * 6.0, y * 4.0, seed + 2, 2)
    coal = smoothstep(0.22, 0.0, y) * (0.6 + 0.4 * noise(u * 14.0, y * 6.0, seed + 3))
    k = clamp01(max(k, coal))
    c = ramp([(0.0, hexc("4A0A02")), (0.3, hexc("B02A06")), (0.55, hexc("FF6A10")), (0.8, hexc("FFB040")),
              (1.0, hexc("FFF0B0"))], k)
    return (c[0], c[1], c[2], clamp01(0.12 + k * 1.1))


def g_embers(ctx, seed, p):
    """Glowing coals (a fire box's bed, ember piles): dark charcoal lumps about p["size"] yd with ash on top and
    orange-hot cracks between them, hotter toward the chart's bottom. Opaque; with p["glow"] the alpha is the
    heat, for the glow preset."""
    size = p.get("size", 0.05)
    gx, gy = ctx.s / size, ctx.t / size
    ix, iy = math.floor(gx), math.floor(gy)
    f1, f2 = 9.0, 9.0
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            cx, cy = ix + dx, iy + dy
            px = cx + 0.15 + 0.7 * _h(cx, cy, 1, seed)
            py = cy + 0.15 + 0.7 * _h(cx, cy, 2, seed)
            d = math.hypot(gx - px, gy - py)
            if d < f1:
                f1, f2 = d, f1
            elif d < f2:
                f2 = d
    crack = smoothstep(0.22, 0.0, f2 - f1)
    heat = clamp01(crack * (0.55 + 0.45 * noise(ctx.s * 6.0, ctx.t * 6.0, seed + 3)) + smoothstep(0.6, 1.0,
                                                                                                    ctx.v) * 0.25)
    char = mix(hexc("221E1C"), hexc("3A3430"), _h(ix, iy, 3, seed))
    char = mix(char, hexc("8A8480"), smoothstep(0.45, 0.0, f1) * smoothstep(-0.2, 0.8, ctx.n[2]) * 0.35)
    hot = ramp([(0.0, hexc("6A1204")), (0.5, hexc("FF5A10")), (1.0, hexc("FFD070"))], heat)
    c = mix(char, hot, smoothstep(0.1, 0.6, heat))
    if p.get("glow"):
        return (c[0], c[1], c[2], clamp01(heat * 1.2))
    return c


# Original rune shapes for the frost crystal: strokes in a unit facet box (x right, y down).
RUNES = [
    [((0.5, 0.05), (0.5, 0.95)), ((0.5, 0.3), (0.2, 0.1)), ((0.5, 0.3), (0.8, 0.1)), ((0.5, 0.7), (0.2, 0.9)),
     ((0.5, 0.7), (0.8, 0.9))],
    [((0.3, 0.05), (0.3, 0.95)), ((0.3, 0.1), (0.75, 0.35)), ((0.75, 0.35), (0.3, 0.6))],
    [((0.5, 0.05), (0.2, 0.5)), ((0.2, 0.5), (0.5, 0.95)), ((0.5, 0.95), (0.8, 0.5)), ((0.8, 0.5), (0.5, 0.05))],
    [((0.25, 0.05), (0.25, 0.95)), ((0.75, 0.05), (0.75, 0.95)), ((0.25, 0.35), (0.75, 0.65))],
]


def _seg_dist(x, y, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = dx * dx + dy * dy or 1e-12
    k = max(0.0, min(1.0, ((x - a[0]) * dx + (y - a[1]) * dy) / L))
    return math.hypot(x - (a[0] + k * dx), y - (a[1] + k * dy))


def g_frost_rune(ctx, seed, p):
    """The frost rune crystal (glow preset, pale blue p["color"] 9FD8FF): every facet (p["facets"] around the
    chart, default 6, as a 6-sided lathe gives) brightest along its centre line and at the crystal's waist,
    darker toward its edges, with one bright rune carved into it. The alpha is the brightness (additive)."""
    base = p.get("color", hexc("9FD8FF"))
    facets = p.get("facets", 6)
    fu = ctx.u * facets
    i = int(math.floor(fu)) % facets
    x = fu - math.floor(fu)
    y = ctx.v
    edge = min(x, 1.0 - x) * 2.0
    waist = 1.0 - abs(y - 0.5) * 2.0
    c = mix(scale(base, 0.45), base, smoothstep(0.0, 0.8, edge))
    c = mix(c, hexc("EAF8FF"), smoothstep(0.35, 1.0, edge * waist) * 0.6)
    rune = RUNES[(i + seed) % len(RUNES)]
    lx, ly = (x - 0.22) / 0.56, (y - 0.25) / 0.5
    d = min(_seg_dist(lx, ly, a, b) for a, b in rune)
    if d < 0.07:
        c = hexc("F6FDFF")
    elif d < 0.17:
        c = mix(c, hexc("D8F4FF"), smoothstep(0.17, 0.07, d) * 0.8)
    a = clamp01(0.55 + 0.45 * lum(c))
    return (c[0], c[1], c[2], a)


def g_beans(ctx, seed, p):
    """Roasted coffee beans in a heap (a grinder hopper, a sack, a jar): oval beans about p["size"] yd long
    (default 0.05, exaggerated so they read), lit from the upper left, each with a dark centre crease and its
    own roast, with near-black gaps between them."""
    size = p.get("size", 0.05)
    cell = size * 0.8
    gx, gy = ctx.s / cell, ctx.t / cell
    ix, iy = math.floor(gx), math.floor(gy)
    best = None
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            cx, cy = ix + dx, iy + dy
            px = cx + 0.2 + 0.6 * _h(cx, cy, 1, seed)
            py = cy + 0.2 + 0.6 * _h(cx, cy, 2, seed)
            ang = _h(cx, cy, 3, seed) * math.pi
            ca, sa = math.cos(ang), math.sin(ang)
            ox, oy = gx - px, gy - py
            lx = ox * ca + oy * sa
            ly = -ox * sa + oy * ca
            e = (lx / 0.62) ** 2 + (ly / 0.44) ** 2
            if e < 1.0 and (best is None or e < best[0]):
                best = (e, lx, ly, ox, oy, _h(cx, cy, 4, seed))
    if best is None:
        return hexc("170C06")
    e, lx, ly, ox, oy, tone = best
    nz = math.sqrt(max(0.0, 1.0 - e))
    c = mix(hexc("6E3E1C"), hexc("43230F"), tone)
    k = 0.45 + 0.45 * nz - 0.35 * (ox + oy)
    c = scale(c, clamp01(k) * 1.25 + 0.15)
    if abs(ly) < 0.07 and e < 0.75:
        c = mix(c, hexc("1E0E06"), 0.8)
    if ox < -0.1 and oy < -0.05 and e < 0.6:
        c = mix(c, hexc("C89060"), smoothstep(0.6, 0.2, e) * 0.35)
    return c


def g_shake(ctx, seed, p):
    """A milkshake (the blender jar, the shake glass): pink (p["color"], default F2A2BE) with lighter swirls and
    a pale froth band at the top: chart v < p["froth"] (0.12), or with p["top"] (model z of the surface)
    within p["froth_d"] yd of it."""
    base = p.get("color", hexc("F2A2BE"))
    froth_c = mix(base, (1.0, 0.97, 0.96), 0.65)
    x, y, z = ctx.pos
    sw = math.sin((ctx.u * 2.0 + ctx.v * 1.3) * 2.0 * math.pi * 2.0 + fbm3(x * 5, y * 5, z * 5, seed, 2) * 4.0)
    c = mix(base, mix(base, (1.0, 1.0, 1.0), 0.35), smoothstep(0.4, 1.0, sw) * 0.6)
    c = mix(c, scale(base, 0.82), smoothstep(-0.4, -1.0, sw) * 0.4)
    if "top" in p:
        fd = p["top"] - z
        froth = smoothstep(p.get("froth_d", 0.03), 0.0, fd)
    else:
        froth = smoothstep(p.get("froth", 0.12), 0.0, ctx.v)
    c = mix(c, froth_c, froth * (0.75 + 0.25 * noise3(x * 30, y * 30, z * 30, seed + 1)))
    if ctx.n[2] > 0.7:
        c = mix(c, froth_c, 0.6)
    return c


def g_cream(ctx, seed, p):
    """Whipped cream: warm white (p["color"]) with soft grooves following the piped swirl along the chart's
    long axis, cool grey-violet in the grooves and a lit top."""
    base = p.get("color", hexc("FFF8EC"))
    along = ctx.s if ctx.cw >= ctx.ch else ctx.t
    across = ctx.t if ctx.cw >= ctx.ch else ctx.s
    g = 0.5 + 0.5 * math.sin(across * 90.0 + along * 8.0 + noise(along * 4.0, across * 4.0, seed) * 2.0)
    c = mix(base, hexc("C8C0D8"), smoothstep(0.35, 0.0, g) * 0.45)
    c = mix(c, (1.0, 1.0, 1.0), smoothstep(0.3, 1.0, ctx.n[2]) * 0.4)
    return c


def g_coffee(ctx, seed, p):
    """A coffee surface on a disc chart (the cap of a lathe, a cup or mug top): dark coffee at the rim, golden
    crema, and with p["heart"] a big pale latte-art heart whose point faces the chart's bottom (the model's
    front, +X, for a cap made by geom.lathe). p["crema"], p["coffee"], p["milk"] override the colours."""
    cr = min(ctx.cw, ctx.ch) / 2.0
    X = (ctx.s - ctx.cw / 2.0) / cr
    Y = -(ctx.t - ctx.ch / 2.0) / cr
    r = math.hypot(X, Y)
    coffee = p.get("coffee", hexc("4A2612"))
    crema = p.get("crema", hexc("C08A4A"))
    c = mix(crema, coffee, smoothstep(0.55, 0.95, r))
    c = mix(c, scale(crema, 1.12), noise(ctx.s * 40.0, ctx.t * 40.0, seed) * 0.25)
    if p.get("heart"):
        hx, hy = X / 0.62, (Y - 0.05) / 0.62
        f = (hx * hx + hy * hy - 1.0) ** 3 - hx * hx * hy ** 3
        milk = p.get("milk", hexc("F6EAD2"))
        if p.get("outline"):
            # a crisp heart: a hard milk edge, a dark crema line hugging it and a darker crema ring round it,
            # so the shape (and its point) holds at 4-8 yd instead of blurring into a pale blob
            ring = p.get("ring", scale(crema, 0.62))
            c = mix(c, ring, smoothstep(0.42, 0.25, f) * 0.75)
            if f < 0.0:
                c = mix(milk, scale(milk, 0.94), smoothstep(0.0, 0.8, r))
            elif f < 0.09:
                c = mix(scale(coffee, 1.1), ring, smoothstep(0.03, 0.09, f))
        elif f < 0.0:
            c = mix(milk, scale(milk, 0.92), smoothstep(0.0, 0.8, r))
        elif f < 0.06:
            c = mix(c, milk, smoothstep(0.06, 0.0, f) * 0.6)
    return c


SILVER = dict(light_c=hexc("FFFFFF"), base=hexc("B4BCC8"), dark=hexc("3A4250"), bounce=hexc("8890A0"),
              patina=hexc("6A6E78"))


def g_silver(ctx, seed, p):
    """Painted silver (coins, a tray, SW spoons): cool and bright, with the painted bands of metal()."""
    return metal(ctx, seed, p, SILVER["light_c"], SILVER["base"], SILVER["dark"], SILVER["bounce"],
                 SILVER["patina"], p.get("patina", 0.08))


def g_hammered_iron(ctx, seed, p):
    """g_iron with hammer dents (the Orgrimmar crest, cast boxes): shallow dents about p["dent"] yd (0.045)
    across, each lit on its lower-right inner wall and shaded on its upper-left one."""
    c = g_iron(ctx, seed, p)
    cell = p.get("dent", 0.045)
    gx, gy = ctx.s / cell, ctx.t / cell
    ix, iy = math.floor(gx), math.floor(gy)
    best = None
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            cx, cy = ix + dx, iy + dy
            px = cx + 0.2 + 0.6 * _h(cx, cy, 1, seed)
            py = cy + 0.2 + 0.6 * _h(cx, cy, 2, seed)
            d = math.hypot(gx - px, gy - py)
            if best is None or d < best[0]:
                best = (d, gx - px, gy - py)
    d, ox, oy = best
    if d < 0.5:
        k = (ox + oy) / max(d, 1e-6) * (d / 0.5) * smoothstep(0.5, 0.2, d)
        c = scale(c, 1.0 + 0.18 * k)
    return c


GENERATORS = {
    "noise": g_noise, "fbm": g_fbm, "brass": g_brass, "gold": g_gold, "copper": g_copper, "iron": g_iron,
    "soot": g_soot, "enamel": g_enamel, "wood": g_wood, "marble": g_marble, "stone": g_stone,
    "leather": g_leather, "hide": g_hide, "ceramic": g_ceramic, "clay": g_clay,
    "fabric_stripes": g_fabric_stripes, "glass": g_glass, "frost": g_frost, "env_gradient": g_env_gradient,
    "steam_puff": g_steam_puff, "fire": g_fire, "flat": g_flat,
    # shared by the section 5.8.1 designs (M5)
    "bone": g_bone, "planks": g_planks, "slabs": g_slabs, "slate": g_slate, "bottle_glass": g_bottle_glass,
    "frosted_glass": g_frosted_glass, "glaze": g_glaze, "rope": g_rope, "lacquer": g_lacquer,
    "fire_glow": g_fire_glow, "embers": g_embers, "frost_rune": g_frost_rune, "beans": g_beans,
    "shake": g_shake, "cream": g_cream, "coffee": g_coffee, "silver": g_silver, "hammered_iron": g_hammered_iron,
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
bone = _img("bone")
planks = _img("planks")
slabs = _img("slabs")
slate = _img("slate")
bottle_glass = _img("bottle_glass")
frosted_glass = _img("frosted_glass")
glaze = _img("glaze")
rope = _img("rope")
lacquer = _img("lacquer")
fire_glow = _img("fire_glow")
embers = _img("embers")
frost_rune = _img("frost_rune")
beans = _img("beans")
shake = _img("shake")
cream = _img("cream")
coffee = _img("coffee")
silver = _img("silver")
hammered_iron = _img("hammered_iron")


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
