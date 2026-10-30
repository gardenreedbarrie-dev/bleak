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
# Relief palettes for emblem.render_relief: hammered dark iron (the Orgrimmar crest on red lacquer), carved
# ivory, and a crest carved into timber (the Orgrimmar chalkboard's top).
IRON_RELIEF = {"base": T.hexc("2E2E34"), "raised": T.hexc("5A5C64"), "top": T.hexc("A4A8B0"),
               "dark": T.hexc("101014"), "outline": T.hexc("0A0A0C")}
BONE_RELIEF = {"base": T.hexc("A08A5E"), "raised": T.hexc("E2D0A2"), "top": T.hexc("FFF4D6"),
               "dark": T.hexc("4A3A22"), "outline": T.hexc("2E2414")}
CARVED_WOOD = {"base": T.hexc("2A170C"), "raised": T.hexc("6A4428"), "top": T.hexc("A07448"),
               "dark": T.hexc("140A04"), "outline": T.hexc("100804")}
CHALK = T.hexc("EEF0E8")


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
    """A bottle label (section 5.5.1): a colour band and one large flavour glyph (emblem.GLYPHS, or an emblem),
    no words. p: color (the band), color2 (a two-tone band: the lower half, e.g. the cactus apple), glyph,
    glyph_c (default a warm white, or a dark brown on pale bands), outline (a dark ring round the glyph, on by
    default, so it reads on any band), border (a thin dark edge line along the band's top and bottom)."""
    img = T.Img(w, h, (0, 0, 0, 0))
    band = p.get("color", T.hexc("E0A030"))
    band2 = p.get("color2")
    for y in range(h):
        c = band2 if band2 is not None and y >= h // 2 else band
        for x in range(w):
            img.set(x, y, c, 1.0)
    if p.get("border", True):
        bw = max(1, h // 24)
        for y in list(range(bw)) + list(range(h - bw, h)):
            for x in range(w):
                img.set(x, y, T.scale(band, 0.45), 1.0)
    glyph = p.get("glyph")
    if not glyph:
        return img
    table = E.GLYPHS if glyph in E.GLYPHS else E.EMBLEMS
    s = int(min(w, h) * p.get("glyph_scale", 0.8))
    if s < 4:
        return img
    ox, oy = (w - s) // 2, (h - s) // 2
    light_band = T.lum(band) > 0.62
    gc = p.get("glyph_c", T.hexc("3A2414") if light_band else T.hexc("FFF6E0"))
    oc = p.get("outline_c", T.scale(band, 0.35) if not light_band else T.hexc("FFFFFF"))
    layers = E.layer_masks(glyph, s, s, table=table)
    if p.get("outline", True):
        sil = R.Mask(s, s)
        for _n, m, mode, _hh in layers:
            sil.max_with(m)
        ring = R.dilate(sil, max(1, s // 40))
        for i, a in enumerate(ring.a):
            if a > 0:
                img.blend(ox + i % s, oy + i // s, oc, a * 0.9)
    for _n, m, mode, height in layers:
        dark = mode == "dark" or (isinstance(mode, tuple) and height < 0.5)
        for i, a in enumerate(m.a):
            if a > 0:
                x, y = ox + i % s, oy + i // s
                if dark:
                    img.blend(x, y, band2 if band2 is not None and y >= h // 2 else band, a)
                else:
                    img.blend(x, y, gc, a)
    return img


def wrap_front(draw, span=0.3, center=0.5):
    """A decal for the side chart of a lathe or cylinder, which wraps once around the part: `draw(w, h)` is
    rendered into the strip's middle `span` only (center 0.5 is the model's front, +X, for geom's seam at -X),
    so a label or a crest keeps its aspect instead of being stretched round the whole part."""
    def f(w, h):
        img = T.Img(w, h, (0, 0, 0, 0))
        sw = max(1, int(w * span))
        composite(img, draw(sw, h), int(w * center - sw / 2.0), 0)
        return img
    return f


def paint_mask(img, mask, color, ox=0, oy=0, alpha=1.0):
    """Paints a coverage mask (lettering, a line icon) in one colour into an Img."""
    for y in range(mask.h):
        Y = oy + y
        if not 0 <= Y < img.h:
            continue
        for x in range(mask.w):
            X = ox + x
            a = mask.a[y * mask.w + x]
            if a > 0 and 0 <= X < img.w:
                img.blend(X, Y, color, a * alpha)
                j = Y * img.w + X
                img.a[j] = max(img.a[j], a * alpha)
    return img


def engraved_lines(img, x0, y0, w, h, rows=3, seed=1, dark=T.hexc("2A1A08"), light=T.hexc("FFE8A0")):
    """Engraved pseudo-text (section 5.5.1: "anything longer is engraved pseudo-text lines"): `rows` lines of
    word-like dashes of random lengths in the box, dark grooves with a lit lower lip, the last line shorter."""
    lh = h / float(rows)
    th = max(2, int(lh * 0.42))
    for r in range(rows):
        y = int(y0 + r * lh + (lh - th) / 2)
        x = float(x0)
        end = x0 + w * (0.62 if r == rows - 1 and rows > 1 else 1.0)
        k = 0
        while x < end - th:
            wl = th * (1.5 + 3.5 * T._h(r, k, 3, seed))
            x1 = min(end, x + wl)
            for yy in range(y, y + th):
                for xx in range(int(x), int(x1)):
                    if 0 <= xx < img.w and 0 <= yy < img.h:
                        img.blend(xx, yy, dark, 0.9)
            for xx in range(int(x), int(x1)):
                if 0 <= xx < img.w and 0 <= y + th < img.h:
                    img.blend(xx, y + th, light, 0.7)
            x = x1 + th * 1.1
            k += 1
    return img


FAMILY_CHALK = {"coffee": T.hexc("F2D2A0"), "tea": T.hexc("BCE8B0"), "shake": T.hexc("F6BCD0")}


def chalkboard(w, h, seed, p):
    """The section 5.5.1 chalkboard face (see chalkboard_face); kept for tex.chalkboard."""
    return chalkboard_face(w, h, seed, p)


def _pixel_scale(text, box_w, scales=(3, 2)):
    for sc in scales:
        if F.pixel_measure(text)[0] * sc <= box_w:
            return sc
    return None


def _wrap_pixel(text, box_w):
    """[(line, scale)]: the text on one line at pixel scale 4 or 3, else split in two at the word break that
    balances the halves (scale 4 or 3), else the same at scale 2, else []."""
    words = text.split(" ")
    halves = None
    if len(words) > 1:
        best = min(range(1, len(words)), key=lambda i: abs(len(" ".join(words[:i])) - len(" ".join(words[i:]))))
        halves = (" ".join(words[:best]), " ".join(words[best:]))
    for scales in ((4, 3), (2,)):
        sc = _pixel_scale(text, box_w, scales)
        if sc:
            return [(text, sc)]
        if halves:
            sc = min(_pixel_scale(halves[0], box_w, scales) or 0, _pixel_scale(halves[1], box_w, scales) or 0)
            if sc:
                return [(halves[0], sc), (halves[1], sc)]
    return []


def chalkboard_face(w, h, seed, p):
    """A chalkboard face (section 5.5.1; the boards' own 512 x 1024 or 512 x 512 textures): slate with chalk
    dust, then, spread down the board: the title lines in chalk vector lettering (caps of about 7-8.5 % of the
    height, condensed down to 70 % if a line needs it), an optional line-art emblem (emblem.LINE_ICONS, e.g. the
    lion_head line icon), a row of family icons in pastel chalk with a caption under them, and the menu lines in
    the chalk pixel font (scale 4 to 2, the largest that fits). p:
      title: ["The Lion's", "Roast"]; emblem: "lion_head" or None; icons: ["coffee", "tea", "shake"];
      caption: "Coffee · Tea · Shakes"; lines: ["Fresh every morning"]; slate: g_slate params;
      chalk, title_c, emblem_c: colours; strict: raise ValueError when a text does not fit (default: at full
      size, w >= 256; smaller --tex-scale builds skip what does not fit).
    Returns an opaque Img."""
    strict = p.get("strict", w >= 256)
    img = T.image_lowres(T.g_slate, w, h, seed, dict(p.get("slate", {})), (w / 512.0, h / 512.0))
    chalk = p.get("chalk", CHALK)
    mx = int(w * 0.06)
    box_w = w - 2 * mx
    tall = h > w
    blocks = []                                  # (kind, height px, payload)
    titles = p.get("title", [])
    if titles:
        cap_max = h * (0.085 if tall else 0.16)
        cap_min = h * (0.068 if tall else 0.12)
        best = None
        for sq in (1.0, 0.9, 0.8, 0.7):
            cap = min([F.fit_cap(t, box_w, cap_max * 1.6, min_cap=0.5, squeeze=sq) for t in titles] + [cap_max])
            if best is None or cap > best[0] + 0.5:
                best = (cap, sq)
            if cap >= cap_min:
                break
        cap, sq = best
        if cap < h * 0.035:
            if strict:
                raise ValueError("chalkboard title %r does not fit %dx%d" % (titles, w, h))
        else:
            masks = [F.vector_mask(t, cap, squeeze=sq) for t in titles]
            step = int(cap * 1.22)
            blocks.append(("title", step * (len(masks) - 1) + masks[-1].h, (masks, step)))
    icons = p.get("icons", [])
    if icons:
        isz = int(min(box_w / (len(icons) * 1.25), h * 0.11))
        blocks.append(("icons", isz, isz))
    texts = ([p["caption"]] if p.get("caption") else []) + list(p.get("lines", []))
    for k, text in enumerate(texts):
        for part, sc in _wrap_pixel(text, box_w):
            blocks.append(("text", F.PIXEL_H * sc, (part, sc, k)))
        if not _wrap_pixel(text, box_w) and strict:
            raise ValueError("chalkboard line %r does not fit %d px" % (text, box_w))
    used = sum(b[1] for b in blocks)
    em = p.get("emblem")
    if em:
        room = h * 0.9 - used - h * 0.03 * (len(blocks) + 1)
        es = int(min(w * 0.62, room))
        if es >= 16:
            blocks.insert(1 if titles else 0, ("emblem", es, es))
            used += es
    free = h - used
    if free < 0 and strict:
        raise ValueError("chalkboard %dx%d: the content needs %d px more" % (w, h, -free))
    tight = [i for i in range(len(blocks) - 1) if blocks[i][0] == "text" and blocks[i + 1][0] == "text"
             and blocks[i][2][2] == blocks[i + 1][2][2]]
    if p.get("caption") and icons:
        tight += [i for i in range(len(blocks) - 1) if blocks[i][0] == "icons"]
    gap = max(0, free) / float(len(blocks) + 1.4 - 0.75 * len(tight)) if blocks else 0
    y = int(gap * 0.7)
    for bi, (kind, bh, pay) in enumerate(blocks):
        if kind == "title":
            masks, step = pay
            for k, m in enumerate(masks):
                F.chalk_mask(img, m, (w - m.w) // 2, y + k * step, seed + 3 + k, p.get("title_c", chalk), 0.35)
        elif kind == "emblem":
            m = E.line_mask(em, pay, pay, width=4.2)
            F.chalk_mask(img, m, (w - pay) // 2, y, seed + 5, p.get("emblem_c", T.hexc("F6E6A6")), 0.3)
        elif kind == "icons":
            isz = pay
            g2 = (box_w - isz * len(icons)) / float(len(icons))
            for k, name in enumerate(icons):
                m = E.line_mask(name, isz, isz, width=6.0)
                F.chalk_mask(img, m, int(mx + g2 / 2 + k * (isz + g2)), y, seed + 7 + k,
                             FAMILY_CHALK.get(name, chalk), 0.3)
        else:
            text, sc, k = pay
            tw, _th = F.pixel_measure(text)
            F.chalk(img, text, sc, (w - tw * sc) // 2, y, seed + 11 + k, chalk)
        # a caption sits right under its icons, and the halves of a wrapped line stay together
        y += bh + int(gap * 0.25 if bi in tight else gap)
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
