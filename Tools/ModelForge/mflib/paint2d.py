"""2D decals painted in chart space: dials, plates, labels, chalkboards, test-cube faces.

Every function returns a tex.Img whose alpha is the decal's coverage; build.py composites it over the part's
base paint before the bake light is applied.
"""

import math

from . import emblem as E
from . import font as F
from . import raster2d as R
from . import tex as T

GOLD_RELIEF = {"base": T.hexc("9A6418"), "raised": T.hexc("DDA830"), "top": T.hexc("F8DC80"),
               "dark": T.hexc("3A2008"), "outline": T.hexc("2A1405")}


def composite(dst, src, ox=0, oy=0):
    for y in range(src.h):
        Y = oy + y
        if not 0 <= Y < dst.h:
            continue
        for x in range(src.w):
            X = ox + x
            if not 0 <= X < dst.w:
                continue
            i = y * src.w + x
            a = src.a[i]
            if a > 0:
                dst.blend(X, Y, (src.r[i], src.g[i], src.b[i]), a)
                j = Y * dst.w + X
                dst.a[j] = max(dst.a[j], a)
    return dst


def ring(img, cx, cy, r0, r1, color, a0=None, a1=None, alpha=1.0):
    """Anti-aliased ring (optionally an arc from angle a0 to a1, radians, 0 = up, clockwise)."""
    for y in range(max(0, int(cy - r1 - 2)), min(img.h, int(cy + r1 + 3))):
        for x in range(max(0, int(cx - r1 - 2)), min(img.w, int(cx + r1 + 3))):
            dx, dy = x + 0.5 - cx, y + 0.5 - cy
            d = math.hypot(dx, dy)
            k = min(T.clamp01(d - r0 + 0.5), T.clamp01(r1 - d + 0.5))
            if k <= 0:
                continue
            if a0 is not None:
                ang = math.atan2(dx, -dy) % (2 * math.pi)
                lo, hi = a0 % (2 * math.pi), a1 % (2 * math.pi)
                inside = lo <= ang <= hi if lo <= hi else (ang >= lo or ang <= hi)
                if not inside:
                    continue
            img.blend(x, y, color, k * alpha)
            img.a[y * img.w + x] = max(img.a[y * img.w + x], k * alpha)


def line(img, x0, y0, x1, y1, width, color, alpha=1.0):
    m = R.Mask(img.w, img.h)
    R.stroke(m, [[(x0, y0), (x1, y1)]], width)
    for i, a in enumerate(m.a):
        if a > 0:
            img.blend(i % img.w, i // img.w, color, a * alpha)
            img.a[i] = max(img.a[i], a * alpha)


def gauge_face(w, h, p):
    """White enamel dial: 0-12 ticks over a 270-degree sweep, green / yellow / red bands, a red needle
    (default at 9 o'clock), a brass hub. Original design."""
    img = T.Img(w, h, (0, 0, 0, 0))
    cx, cy = w / 2.0, h / 2.0
    r = min(w, h) / 2.0
    face = p.get("face", T.hexc("F4EFE2"))
    for y in range(h):
        for x in range(w):
            d = math.hypot(x + 0.5 - cx, y + 0.5 - cy) / r
            if d <= 1.0:
                k = 1.0 - 0.12 * d * d - 0.05 * max(0.0, (y - cy) / r)
                img.set(x, y, T.scale(face, k), T.clamp01((1.0 - d) * r + 0.5))
    sweep0 = math.radians(-135)
    sweep = math.radians(270)
    bands = p.get("bands", [(0.0, 0.55, T.hexc("4FA04A")), (0.55, 0.8, T.hexc("E8C030")),
                             (0.8, 1.0, T.hexc("C83A28"))])
    for f0, f1, col in bands:
        ring(img, cx, cy, r * 0.70, r * 0.80, col, sweep0 + sweep * f0, sweep0 + sweep * f1)
    tick_c = T.hexc("2A2420")
    for k in range(13):
        a = sweep0 + sweep * k / 12.0
        major = k % 3 == 0
        r0 = r * (0.62 if major else 0.68)
        x0, y0 = cx + math.sin(a) * r0, cy - math.cos(a) * r0
        x1, y1 = cx + math.sin(a) * r * 0.84, cy - math.cos(a) * r * 0.84
        line(img, x0, y0, x1, y1, max(1.0, r * (0.06 if major else 0.035)), tick_c)
    if p.get("numbers", True) and r >= 24:
        scale = max(1, int(r / 30))
        for k in (0, 6, 12):
            a = sweep0 + sweep * k / 12.0
            tx, ty = cx + math.sin(a) * r * 0.45, cy - math.cos(a) * r * 0.45
            tw, th = F.pixel_measure(str(k))
            F.paint(img, str(k), tick_c, scale, int(tx - tw * scale / 2), int(ty - th * scale / 2 + scale))
    ring(img, cx, cy, r * 0.90, r * 1.0, T.hexc("3A2A1A"))
    needle = math.radians(p.get("needle_deg", -90.0))  # degrees clockwise from up; -90 = 9 o'clock
    nx, ny = cx + math.sin(needle) * r * 0.78, cy - math.cos(needle) * r * 0.78
    bx, by = cx - math.sin(needle) * r * 0.16, cy + math.cos(needle) * r * 0.16
    line(img, bx + 1, by + 1, nx + 1, ny + 1, max(1.5, r * 0.08), T.hexc("2A1A10"), 0.4)
    line(img, bx, by, nx, ny, max(1.5, r * 0.08), T.hexc("D02818"))
    hub = T.Img(w, h, (0, 0, 0, 0))
    R_hub = r * 0.14
    for y in range(h):
        for x in range(w):
            dx, dy = x + 0.5 - cx, y + 0.5 - cy
            d = math.hypot(dx, dy)
            if d < R_hub + 1:
                k = 0.75 + 0.5 * T.clamp01(-(dx + dy) / (R_hub * 2) + 0.5)
                hub.set(x, y, T.scale(T.hexc("D8A840"), k), T.clamp01(R_hub - d + 0.5))
    composite(img, hub)
    return img


def plate(w, h, p):
    """A brass maker's plate: a darker inset frame, an emblem in painted relief and a lettered banner."""
    img = T.Img(w, h, (0, 0, 0, 0))
    frame_c = p.get("frame", T.hexc("5A3A12"))
    bw = max(2, int(min(w, h) * 0.035))
    # inset frame line
    for y in range(h):
        for x in range(w):
            e = min(x, y, w - 1 - x, h - 1 - y)
            if bw <= e < 2 * bw:
                img.set(x, y, frame_c, 0.85)
            elif e < bw:
                img.set(x, y, T.hexc("F2D27A"), 0.35)
    text = p.get("text")
    banner_h = int(h * p.get("banner", 0.24)) if text else 0
    em = p.get("emblem")
    if em:
        es = int(min(w - 4 * bw, h - banner_h - 4 * bw) * p.get("emblem_scale", 1.0))
        rel = E.render_relief(em, es, es, p.get("palette", GOLD_RELIEF))
        composite(img, rel, (w - es) // 2, 2 * bw + (h - banner_h - 4 * bw - es) // 2)
    if text:
        y0 = h - banner_h - bw * 2
        bh = banner_h
        band_c = p.get("band", T.hexc("2C4A86"))
        for y in range(y0, y0 + bh):
            for x in range(2 * bw, w - 2 * bw):
                img.set(x, y, T.scale(band_c, 0.9 + 0.2 * (1 - (y - y0) / max(1, bh))), 1.0)
        try:
            cap = F.fit_cap(text, w - 6 * bw, bh * 0.92, min_cap=4.0)
        except ValueError:
            if min(w, h) >= 64:
                raise           # at full size a text that does not fit is an error (section 5.5.1)
            return img          # a --tex-scale preview build: the plate is too small for lettering
        m = F.vector_mask(text, cap)
        ox = (w - m.w) // 2
        oy = y0 + (bh - m.h) // 2
        F.two_tone(img, m, p.get("text_c", T.hexc("FBE7A1")), T.hexc("1A1006"), ox, oy, 1, (1, 1),
                   T.hexc("0A0804"))
        for x in range(2 * bw, w - 2 * bw):
            for yy in (y0 - 1, y0 + bh):
                if 0 <= yy < h:
                    img.set(x, yy, T.hexc("F6D676"), 1.0)
    return img


def grille(w, h, p):
    """Drip-tray grille: dark slots between lit bars, painted (opaque)."""
    img = T.Img(w, h, (0, 0, 0, 0))
    n = p.get("slots", 9)
    margin = p.get("margin", 0.12)
    dark = p.get("dark", T.hexc("1E1810"))
    x0, x1 = int(w * margin * 0.5), int(w * (1 - margin * 0.5))
    y0, y1 = int(h * margin), int(h * (1 - margin))
    pitch = (x1 - x0) / float(n)
    duty = p.get("duty", 0.38)
    for x in range(x0, x1):
        q = ((x - x0) % pitch) / pitch
        if 0.5 - duty / 2 < q < 0.5 + duty / 2:
            edge = min(q - (0.5 - duty / 2), (0.5 + duty / 2) - q) / (duty / 2)
            for y in range(y0, y1):
                ry = min(y - y0, y1 - 1 - y)
                k = T.clamp01(min(edge * 3.0, ry / 2.0 + 0.3))
                img.set(x, y, T.scale(dark, 0.8 if y < y0 + 2 else 1.0), 0.9 * k)
            img.set(x, y1 - 1, T.hexc("F2D27A"), 0.45)
    return img


def label(w, h, p):
    """A bottle label: a colour band and one large glyph (an emblem layer), no words."""
    img = T.Img(w, h, (0, 0, 0, 0))
    band = p.get("color", T.hexc("E0A030"))
    for y in range(h):
        for x in range(w):
            img.set(x, y, band, 1.0)
    glyph = p.get("glyph")
    if glyph:
        s = int(min(w, h) * 0.8)
        sil = E.silhouette(glyph, s, s)
        for y in range(s):
            for x in range(s):
                a = sil.a[y * s + x]
                if a > 0:
                    img.blend((w - s) // 2 + x, (h - s) // 2 + y, p.get("glyph_c", T.hexc("FFF6E0")), a)
    return img


def chalkboard(w, h, seed, p):
    """Slate with chalk dust, a vector title and pixel-chalk lines (titles need the M5 lower case)."""
    img = T.Img(w, h, (0, 0, 0, 1))
    slate = T.hexc("2A3430")
    for y in range(h):
        for x in range(w):
            v = T.fbm(x / 40.0, y / 40.0, seed, 3)
            img.set(x, y, T.mix(T.scale(slate, 0.85), T.scale(slate, 1.25), v), 1.0)
    y = int(h * 0.06)
    for line_ in p.get("title", []):
        cap = F.fit_cap(line_, w * 0.86, h * 0.09)
        m = F.vector_mask(line_, cap)
        F.two_tone(img, m, T.hexc("F4F0E4"), T.hexc("1A2220"), (w - m.w) // 2, y, 1, None)
        y += m.h
    for line_ in p.get("lines", []):
        tw, th = F.pixel_measure(line_)
        sc = max(2, min(3, int(w * 0.8 / max(1, tw))))
        F.chalk(img, line_, sc, (w - tw * sc) // 2, y + 8, seed)
        y += th * sc + 10
    return img


def cube_face(w, h, p):
    """Test-cube face: a colour, its name in large pixel letters, an arrow pointing to +V's top and a corner
    dot at UV (0, 0) (top-left), for the in-game winding / UV-origin check (V30)."""
    col = p.get("color", (0.5, 0.5, 0.5))
    img = T.Img(w, h, (col[0], col[1], col[2], 1.0))
    for y in range(h):
        for x in range(w):
            e = min(x, y, w - 1 - x, h - 1 - y)
            if e < max(2, w // 32):
                img.set(x, y, T.scale(col, 0.45), 1.0)
    name = p.get("name", "?")
    tw, th = F.pixel_measure(name)
    sc = max(1, int(min(w * 0.7 / max(1, tw), h * 0.3 / th)))
    F.paint(img, name, (1.0, 1.0, 1.0), sc, (w - tw * sc) // 2, (h - th * sc) // 2)
    r = max(3, w // 14)
    R_ = R.Mask(w, h)
    R.disc(R_, r * 1.8, r * 1.8, r)
    for i, a in enumerate(R_.a):
        if a > 0:
            img.blend(i % w, i // w, (1.0, 0.95, 0.2), a)
    sub = p.get("sub")
    if sub:
        tw2, th2 = F.pixel_measure(sub)
        sc2 = max(1, sc // 2)
        F.paint(img, sub, (0.1, 0.1, 0.1), sc2, (w - tw2 * sc2) // 2, int(h * 0.75))
    return img
