"""19318 ChalkboardSW, the Lion's Roast sandwich board (Stormwind), CAFE.SPEC.md section 5.8.1.

An A-frame café menu board that reads as one at a glance: two walnut-framed boards leaning together in a tent,
the front one a big dark slate written in chalk ("The" / "Lion's" / "Roast" in large serif chalk letters, the
lion drawn in pale gold chalk, the coffee, tea and shake icons in pastel chalk over "Coffee · Tea · Shakes", and
"Fresh every morning" between two chalk sparkles), with a chalk ledge at its foot carrying three fat sticks of
chalk and a felt eraser. Stormwind craftsmanship: each board is crowned by an arched walnut header with a gold
lion medallion on a royal-blue enamel field, a gold-and-blue bead runs round the slate, the stiles stand in
polished brass shoes and two brass spreader bars hold the boards apart. The back board says "Welcome!" (and "by
the Cathedral steps") to the other side of the street. 0.9 (Y) x 0.5 (X) x 1.4 yd, front (+X) toward the
customers.

What makes a player name it (front three-quarter view, 4-15 yd; sizes at 10 yd, about 95 px a yard):
- the A-frame tent: two 0.055 boards meeting at the top and splayed 0.5 at the feet;
- a dark slate panel (0.72 x 0.97) in a 0.09 walnut frame: a dark board in a light frame, 68 x 92 px;
- big chalk words: "Lion's" and "Roast" at a cap height of 0.11 yd (10 px), white on near-black;
- chalk drawings: the lion line icon (about 0.2 yd) and the three family icons (about 0.09 yd);
- the chalk ledge (0.05 deep) with chalk sticks 0.11 x 0.035;
- Stormwind: the gold lion medallion (0.2 across) on its blue arch, brass and royal blue on walnut.

Deviations from section 5.8.1:
- the boards lean 10 degrees (not 12): with boards that meet at the top, the section 5.8 size (D 0.5 at H 1.4,
  the ledge included) leaves room for 10;
- the title is "The" / "Lion's" / "Roast" on three lines, a small "The" between chalk swashes, so the two main
  words are large enough to read at 10 yd;
- added for the Stormwind look and the board's charm: the arched headers with the lion medallions, the slate
  bead, the brass shoes and spreaders, the chalk ledge with its chalk and eraser;
- the front texture (512 x 1024) holds the slate at the slate's own aspect (512 x 684, so the chalk is neither
  stretched nor blurred by anisotropic mips), and the medallions and headers in the rest of it;
- the collision hull is a gable (the A shape) rather than a flat box, so nobody stands on the sign.

The chalk menu layout (chalk_menu) is shared with ChalkboardOrg.
"""

import math

from .. import build as B
from .. import emblem as E
from .. import font as F
from .. import geom as G
from .. import paint2d as P2
from .. import raster2d as R
from .. import tex as T

NAME = "ChalkboardSW"
DISPLAY = 19318

ENAMEL = T.hexc("2E4E8C")
GOLD_LINE = T.hexc("F2C85A")
CHALK = T.hexc("F2EFE6")       # near-white ink: the title must hold under night light
CHALK_GOLD = T.hexc("F6E2A0")
CHALK_BLUE = T.hexc("A8CCF4")

W, D, H = 0.9, 0.5, 1.4
TB = 0.055                 # board thickness
STILE = 0.09               # stile width
OPEN_HW = W / 2 - STILE    # half width of the slate opening (0.36)
RAIL0, RAIL1 = 0.15, 0.24  # bottom rail along the slope (from the board's foot)
HEADER = 0.235             # arched header: height at the crown
SHOULDER = 0.08            # ... and at its shoulders
ARCH_RX, ARCH_RY = 0.27, HEADER - SHOULDER
RECESS = 0.018             # the slate sits this far behind the frame face
LEDGE_P, LEDGE_H = 0.05, 0.03
MED_R, MED_D = 0.1, 0.026
BEAD_GOLD, BEAD_BLUE = 0.011, 0.026   # the gold and blue lines round the slate (yd from its edge)


def _depth(theta):
    """Front-to-back extent of the A-frame at lean `theta`: the back board's foot to the ledge's front lip."""
    s, c = math.sin(theta), math.cos(theta)
    L = (H - TB * s) / c
    return 2 * L * s - (RAIL1 * c - LEDGE_H) * (s / c) + LEDGE_P


def _solve_theta():
    lo, hi = math.radians(4.0), math.radians(16.0)
    for _ in range(50):
        mid = (lo + hi) / 2
        if _depth(mid) > D:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


THETA = _solve_theta()                                    # about 10 degrees
SIN, COS = math.sin(THETA), math.cos(THETA)
L = (H - TB * SIN) / COS                                  # board length along the slope (outer face)
S0 = L - HEADER                                           # header bottom = top of the stiles and the slate
SLATE_W, SLATE_H = 2 * OPEN_HW, S0 - RAIL1
S_MED = S0 + 0.117                                        # medallion centre along the slope
FACE_PX = (512, int(round(512 * SLATE_H / SLATE_W / 4.0)) * 4)   # the slate's region of the face texture
X_FOOT = L * SIN                                          # outer foot of each board (before centring)
Z_LEDGE = TB * SIN + RAIL1 * COS                          # top of the ledge = outer top edge of the rail
X_LEDGE = X_FOOT - (RAIL1 * COS - LEDGE_H) * SIN / COS + LEDGE_P
SHIFT = (X_LEDGE - X_FOOT) / 2                            # centres the footprint on the origin


def x_face(z):
    """X of the front board's outer face at height z (before centring)."""
    return X_FOOT - (z - TB * SIN) * SIN / COS


# ------------------------------------------------------------------------------------------- chalk menu

def resample(img, w, h):
    """Bilinear resize of a tex.Img (a face drawn at its geometry's aspect onto a texture of another)."""
    out = T.Img(w, h)
    sx, sy = img.w / float(w), img.h / float(h)
    for y in range(h):
        fy = min(img.h - 1.0, max(0.0, (y + 0.5) * sy - 0.5))
        y0 = int(fy)
        y1 = min(img.h - 1, y0 + 1)
        ty = fy - y0
        for x in range(w):
            fx = min(img.w - 1.0, max(0.0, (x + 0.5) * sx - 0.5))
            x0 = int(fx)
            x1 = min(img.w - 1, x0 + 1)
            tx = fx - x0
            i00, i10, i01, i11 = y0 * img.w + x0, y0 * img.w + x1, y1 * img.w + x0, y1 * img.w + x1
            k00, k10, k01, k11 = (1 - tx) * (1 - ty), tx * (1 - ty), (1 - tx) * ty, tx * ty
            j = y * w + x
            for src, dst in ((img.r, out.r), (img.g, out.g), (img.b, out.b), (img.a, out.a)):
                dst[j] = src[i00] * k00 + src[i10] * k10 + src[i01] * k01 + src[i11] * k11
    return out


def chalk_strokes(img, polys, width, seed, color, dust=0.25):
    """Chalk lines (pixel polylines) into img, rasterized in a mask cropped to their bounding box."""
    xs = [x for poly in polys for x, _y in poly]
    ys = [y for poly in polys for _x, y in poly]
    pad = int(width * 2 + 6)
    ox, oy = max(0, int(min(xs)) - pad), max(0, int(min(ys)) - pad)
    mw = min(img.w, int(max(xs)) + pad) - ox
    mh = min(img.h, int(max(ys)) + pad) - oy
    if mw <= 2 or mh <= 2:
        return
    m = R.Mask(mw, mh)
    R.stroke(m, R.xform_polys(polys, 1.0, 1.0, -ox, -oy), width)
    F.chalk_mask(img, m, ox, oy, seed, color, dust)


def chalk_dots(img, pts, r, seed, color):
    """Chalk dots of radius r at pixel points."""
    for k, (cx, cy) in enumerate(pts):
        ox, oy = max(0, int(cx - r - 4)), max(0, int(cy - r - 4))
        mw, mh = min(img.w - ox, int(2 * r + 9)), min(img.h - oy, int(2 * r + 9))
        if mw <= 2 or mh <= 2:
            continue
        m = R.Mask(mw, mh)
        R.disc(m, cx - ox, cy - oy, r)
        F.chalk_mask(img, m, ox, oy, seed + k, color, 0.2)


def _sparkle(cx, cy, r):
    """A four-point chalk sparkle: a long cross and a short diagonal one."""
    d = r * 0.45
    return [[(cx - r, cy), (cx + r, cy)], [(cx, cy - r), (cx, cy + r)], [(cx - d, cy - d), (cx + d, cy + d)],
            [(cx - d, cy + d), (cx + d, cy - d)]]


def _round_rect(x0, y0, x1, y1, r, steps=4):
    """A closed rounded rectangle as one polyline."""
    pts = []
    for cx, cy, a0 in ((x1 - r, y0 + r, -90.0), (x1 - r, y1 - r, 0.0), (x0 + r, y1 - r, 90.0),
                       (x0 + r, y0 + r, 180.0)):
        for k in range(steps + 1):
            a = math.radians(a0 + 90.0 * k / steps)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    pts.append(pts[0])
    return pts


def _border_double(img, w, h, seed, color):
    """The Stormwind chalk frame: a double rounded rectangle with a small curl in each inner corner."""
    m1, m2 = w * 0.035, w * 0.062
    lw = max(1.5, w * 0.008)
    polys = [_round_rect(m1, m1, w - m1, h - m1, w * 0.05), _round_rect(m2, m2, w - m2, h - m2, w * 0.03)]
    curls = []
    r0 = w * 0.026
    for sx, sy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
        cx = m2 + w * 0.05 if sx > 0 else w - m2 - w * 0.05
        cy = m2 + w * 0.05 if sy > 0 else h - m2 - w * 0.05
        a0 = math.atan2(-sy, -sx)
        turn = 1.0 if sx * sy > 0 else -1.0
        pts = []
        for k in range(12):
            a = a0 + turn * 1.6 * math.pi * k / 11.0
            rr = r0 * (1.0 - 0.6 * k / 11.0)
            pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
        curls.append(pts)
    chalk_strokes(img, polys, lw, seed, color, 0.2)
    chalk_strokes(img, curls, lw * 0.9, seed + 1, color, 0.2)


def _border_teeth(img, w, h, seed, color, rows=(0.1, 0.9)):
    """The Orgrimmar chalk frame: a row of teeth (a zig-zag) across the board at each of `rows` (fractions of
    the height) and a rough upright line down each side between them."""
    m = w * 0.045
    lw = max(1.5, w * 0.009)
    tooth = h * 0.035
    lines = []
    n = 15
    for fy, sgn in ((rows[0], 1), (rows[1], -1)):
        row = []
        for k in range(n + 1):
            x = m + (w - 2 * m) * k / n
            row.append((x, h * fy + (sgn * tooth if k % 2 else 0.0)))
        lines.append(row)
    for x in (m, w - m):
        lines.append([(x, h * rows[0] + tooth * 1.6), (x + w * 0.004, h * 0.5), (x, h * rows[1] - tooth * 1.6)])
    chalk_strokes(img, lines, lw, seed, color, 0.2)


def _pixel_fit(text, box_w, scales=(4, 3, 2)):
    for sc in scales:
        if F.pixel_measure(text)[0] * sc <= box_w:
            return sc
    return None


def _pixel_rows(text, box_w, big=(4, 3)):
    """[(line, scale)]: the text on one line at a `big` scale, else split at the word break that balances the
    halves (a `big` scale), else the same at scale 2, else []."""
    words = text.split(" ")
    halves = None
    if len(words) > 1:
        cut = min(range(1, len(words)), key=lambda i: abs(len(" ".join(words[:i])) - len(" ".join(words[i:]))))
        halves = (" ".join(words[:cut]), " ".join(words[cut:]))
    for scales in (big, (2,)):
        sc = _pixel_fit(text, box_w, scales)
        if sc:
            return [(text, sc)]
        if halves:
            sc = min(_pixel_fit(halves[0], box_w, scales) or 0, _pixel_fit(halves[1], box_w, scales) or 0)
            if sc:
                return [(halves[0], sc), (halves[1], sc)]
    return []


def chalk_menu(w, h, seed, p):
    """A café menu chalked on a board, drawn at w x h (the face's own aspect: texels are square).

    p: bg f(w, h, seed) -> Img (the slate or the board under the chalk); border "double" (Stormwind) or "teeth"
    (Orgrimmar) or None; title [(text, "small" or "big")], big words share the largest cap that fits (up to
    big_cap x h, letters condensed to 75 % if a word needs it), a small word sits between two chalk swashes;
    emblem: a line icon (emblem.LINE_ICONS) of emblem_size x h; icons: the family line icons in pastel chalk,
    caption under them; lines: menu lines in the chalk pixel font (scale 4 to 2), sparkles beside the last one
    when p["sparkles"]. Colours: title_c, small_c, emblem_c, line_c, border_c. A text that does not fit raises
    ValueError at full size (w >= 256, section 5.5.1); smaller test builds draw what fits."""
    strict = w >= 256
    img = p["bg"](w, h, seed)
    border = p.get("border")
    if border == "double":
        _border_double(img, w, h, seed + 101, p.get("border_c", CHALK))
    elif border == "teeth":
        _border_teeth(img, w, h, seed + 101, p.get("border_c", CHALK), p.get("teeth_rows", (0.1, 0.9)))
    mx = int(w * 0.1)
    box_w = w - 2 * mx
    top, bottom = h * p.get("top", 0.075), h * (1.0 - p.get("bottom", 0.06))
    blocks = []            # (kind, height px, payload, gap weight before)
    bigs = [t for t, k in p.get("title", []) if k == "big"]
    cap, sq = 0.0, 1.0
    if bigs:
        cap_max = h * p.get("big_cap", 0.12)
        for sq in (1.0, 0.92, 0.84, 0.75):
            cap = min([F.fit_cap(t, box_w, cap_max * 2.0, min_cap=0.5, squeeze=sq) for t in bigs] + [cap_max])
            if cap >= cap_max * 0.98:
                break
        if cap < h * 0.06 and strict:
            raise ValueError("chalk title %r does not fit %dx%d" % (bigs, w, h))
    gap_w = 1.0
    for text, kind in p.get("title", []):
        if kind == "big":
            m = F.vector_mask(text, cap, squeeze=sq)
            blocks.append(("big", m.h - int(cap * 0.1), m, gap_w))
            gap_w = 0.15
        else:
            sc = cap * p.get("small_k", 0.42) if cap else h * 0.05
            m = F.vector_mask(text, sc, weight=0.18)
            blocks.append(("small", m.h, m, gap_w))
            gap_w = 0.1
    em = p.get("emblem")
    if em:
        es = int(h * p.get("emblem_size", 0.2))
        blocks.append(("emblem", es, (em, es), 1.0))
    icons = p.get("icons", [])
    if icons:
        isz = int(min(box_w / (len(icons) * 1.45), h * p.get("icon_size", 0.1)))
        blocks.append(("icons", isz, isz, 1.0))
    texts = ([(p["caption"], p.get("caption_c", CHALK), 0.18 if icons else 1.0)] if p.get("caption") else [])
    texts += [(t, p.get("line_c", CHALK), 1.0 if k == 0 else 0.3) for k, t in enumerate(p.get("lines", []))]
    for k, (text, col, gw) in enumerate(texts):
        rows = _pixel_rows(text, box_w, (3,) if k == len(texts) - 1 and p.get("sparkles") else (4, 3))
        if not rows:
            if strict:
                raise ValueError("chalk line %r does not fit %d px" % (text, box_w))
            continue
        for j, (part, psc) in enumerate(rows):
            last = k == len(texts) - 1 and j == len(rows) - 1
            blocks.append(("text", F.PIXEL_H * psc, (part, psc, col, last), gw if j == 0 else 0.2))
    used = sum(b[1] for b in blocks)
    free = bottom - top - used
    if free < 0 and strict:
        raise ValueError("chalk menu %dx%d: the content needs %d px more" % (w, h, -free))
    unit = max(0.0, free) / (sum(b[3] for b in blocks[1:]) + 0.6) if blocks else 0.0
    y = top + unit * 0.3
    for bi, (kind, bh, pay, gw) in enumerate(blocks):
        if bi:
            y += unit * gw
        if kind == "big":
            # the title in dense chalk (half the grain) with a strong dust halo round the strokes, so it stays a
            # bright readable word at night, when the board itself drops to black
            F.chalk_mask(img, pay, (w - pay.w) // 2, int(y), seed + 3 + bi, p.get("title_c", CHALK), 0.6, 0.2)
        elif kind == "small":
            x0 = (w - pay.w) // 2
            F.chalk_mask(img, pay, x0, int(y), seed + 3 + bi, p.get("small_c", CHALK_GOLD), 0.5, 0.25)
            ym = y + pay.h * 0.55
            sw_len = min(w * 0.16, x0 - mx * 0.6)
            lw = max(1.5, pay.h * 0.07)
            if sw_len > 6:
                g = pay.h * 0.25
                swash = [[(x0 - g, ym), (x0 - g - sw_len, ym)], [(w - x0 + g, ym), (w - x0 + g + sw_len, ym)]]
                chalk_strokes(img, swash, lw, seed + 31, p.get("small_c", CHALK_GOLD))
                chalk_dots(img, [(x0 - g - sw_len - lw * 2.2, ym), (w - x0 + g + sw_len + lw * 2.2, ym)], lw * 1.1,
                           seed + 33, p.get("small_c", CHALK_GOLD))
        elif kind == "emblem":
            name, es = pay
            m = E.line_mask(name, es, es, width=4.6)
            F.chalk_mask(img, m, (w - es) // 2, int(y), seed + 5, p.get("emblem_c", CHALK_GOLD), 0.3)
        elif kind == "icons":
            isz = pay
            g2 = (box_w - isz * len(icons)) / float(len(icons))
            for k, name in enumerate(icons):
                m = E.line_mask(name, isz, isz, width=6.5)
                F.chalk_mask(img, m, int(mx + g2 / 2 + k * (isz + g2)), int(y), seed + 7 + k,
                             P2.FAMILY_CHALK.get(name, CHALK), 0.3)
        else:
            text, sc, col, last = pay
            tw, _th = F.pixel_measure(text)
            x0 = (w - tw * sc) // 2
            F.chalk(img, text, sc, x0, int(y), seed + 11 + bi, col)
            if last and p.get("sparkles"):
                r = bh * 0.55
                sp = _sparkle(x0 - r * 1.8, y + bh * 0.45, r) + _sparkle(w - x0 + r * 1.8, y + bh * 0.45, r)
                chalk_strokes(img, sp, max(1.2, sc * 0.55), seed + 41, p.get("sparkle_c", CHALK_GOLD))
        y += bh
    return img


def slate_bg(face_yd, slate=None):
    """A background for chalk_menu: g_slate over a face of face_yd (w, h) yards, at a quarter resolution
    (low-frequency layers only; section 5.5 "Build cost")."""
    def bg(w, h, seed):
        return T.image_lowres(T.g_slate, w, h, seed, dict(slate or {}), face_yd)
    return bg


def d_front(w, h):
    """The front slate: the Lion's Roast menu."""
    return chalk_menu(w, h, 3, {
        "bg": slate_bg((SLATE_W, SLATE_H), {"dust": 0.55}), "border": "double", "border_c": T.hexc("D8DEE0"),
        "title": [("The", "small"), ("Lion's", "big"), ("Roast", "big")], "big_cap": 0.118,
        "emblem": "lion_head", "emblem_size": 0.2, "icons": ["coffee", "tea", "shake"], "icon_size": 0.095,
        "caption": "Coffee · Tea · Shakes", "lines": ["Fresh every morning"], "line_c": CHALK_BLUE,
        "sparkles": True, "bottom": 0.11})


def d_back(w, h):
    """The back slate (its own 512² texture, drawn at the slate's aspect and resampled): "Welcome!"."""
    lh = max(8, int(round(w * SLATE_H / SLATE_W)))
    img = chalk_menu(w, lh, 7, {
        "bg": slate_bg((SLATE_W, SLATE_H), {"dust": 0.45}), "border": "double", "border_c": T.hexc("D8DEE0"),
        "title": [("Welcome!", "big")], "big_cap": 0.12, "emblem": "coffee", "emblem_size": 0.3,
        "lines": ["by the Cathedral steps"], "line_c": CHALK_BLUE, "sparkles": True, "top": 0.16,
        "bottom": 0.14})
    return resample(img, w, h)


def d_medallion(w, h):
    """The lion medallion: a rounded gold rim (lit from the upper left) round a royal-blue enamel field with the
    lion in gold relief."""
    img = T.Img(w, h, (0, 0, 0, 0))
    cx, cy, r0 = w / 2.0, h / 2.0, min(w, h) / 2.0
    lx, ly, lz = -0.45, -0.6, 0.66             # light toward the viewer from the upper left (y down)
    for y in range(h):
        for x in range(w):
            dx, dy = (x + 0.5 - cx) / r0, (y + 0.5 - cy) / r0
            d = math.hypot(dx, dy)
            if d > 1.0:
                continue
            if d > 0.8:
                nr = ((d - 0.8) / 0.2 - 0.5) * 1.7          # the rim's radial tilt, inward to outward
                nr = max(-0.95, min(0.95, nr))
                nz = math.sqrt(1.0 - nr * nr)
                lam = T.clamp01((dx / d * nr) * lx + (dy / d * nr) * ly + nz * lz)
                c = T.ramp([(0.0, T.hexc("4A2A06")), (0.45, T.hexc("B07A1E")), (0.8, T.hexc("F2C85A")),
                            (1.0, T.hexc("FFF2C0"))], lam)
            else:
                lit = T.clamp01(0.5 - (dx * 0.6 + dy * 0.8) * 0.5)
                c = T.mix(T.scale(ENAMEL, 0.6), T.mix(ENAMEL, T.hexc("6A90D0"), 0.35), lit * (1.0 - d * 0.5))
                if d > 0.77:
                    c = T.scale(c, 0.5)                       # the shadow under the rim
            img.set(x, y, c, 1.0)
    s = int(min(w, h) * 0.66)
    if s > 8:
        P2.composite(img, E.render_relief("lion_head", s, s, P2.GOLD_RELIEF), (w - s) // 2, (h - s) // 2)
    return img


# ----------------------------------------------------------------------------------------------- paints

def _bead(c, d):
    """The bead round the slate, by the distance d (yd) from the slate's edge: a gold line, then royal blue."""
    if d < BEAD_GOLD:
        return T.mix(GOLD_LINE, T.hexc("FFF0B8"), 0.35 * (1.0 - d / BEAD_GOLD))
    if d < BEAD_BLUE:
        k = (d - BEAD_GOLD) / (BEAD_BLUE - BEAD_GOLD)
        return T.mix(T.mix(ENAMEL, T.hexc("5A80C0"), 0.3), T.scale(ENAMEL, 0.75), k)
    if d < BEAD_BLUE + 0.005:
        return T.scale(c, 0.55)
    return c


def _shoe(ctx, seed, sb):
    """The brass shoe on a stile's foot, with a dark seam at its top and two rivets on the front."""
    c = T.g_brass(ctx, seed + 7, {"streak": False, "patina": 0.08})
    if sb > 0.062:
        return T.scale(c, 0.45)
    if ctx.chart == "+x":
        for rs in (STILE * 0.3, STILE * 0.7):
            c = T.rivet_dot(c, ctx.s - rs, -(sb - 0.032), 0.011)
    return c


def frame_paint(back):
    """Paint for one board's stiles: walnut with the grain along them, brass shoes, and on the front face the
    gold-and-blue bead along the slate (back: the back board, whose local +Y is the model's -Y)."""
    def p(ctx, seed, _p):
        sb = S0 - ctx.t                       # along the slope from the foot (t runs down from the top)
        if sb < 0.07:
            return _shoe(ctx, seed, sb)
        c = T.g_wood(ctx, seed, {"kind": "walnut", "along": "t"})
        if ctx.chart != "+x":
            return c
        yb = -ctx.pos[1] if back else ctx.pos[1]
        do = ctx.s if yb > 0 else STILE - ctx.s          # distance from the slate's side edge
        if sb >= RAIL1:
            return _bead(c, do)
        return _bead(c, max(do, RAIL1 - sb))
    return p


def p_rail(ctx, seed, p):
    """Bottom rail: walnut, the bead along the slate's lower edge on the front."""
    c = T.g_wood(ctx, seed, {"kind": "walnut", "along": "s"})
    if ctx.chart == "+x":
        return _bead(c, ctx.t)
    return c


def p_header(ctx, seed, p):
    """The arched header: walnut, a royal-blue enamel arch (the medallion's field) edged in gold, the bead
    along the slate's top edge, and brass caps on the shoulders' outer corners."""
    c = T.g_wood(ctx, seed, {"kind": "walnut", "along": "s"})
    if ctx.chart.endswith("_side"):
        return c
    if not ctx.chart.endswith("_front"):
        return T.scale(c, 0.8)
    px = ctx.s - W / 2                          # across, from the centre
    py = HEADER - ctx.t                         # up, from the header's bottom edge
    if abs(px) > W / 2 - 0.055 and py > SHOULDER - 0.05:
        b = T.g_brass(ctx, seed + 5, {"streak": False, "patina": 0.06})
        b = T.rivet_dot(b, abs(px) - (W / 2 - 0.028), -(py - (SHOULDER - 0.022)), 0.011)
        return b
    # the blue field: an arch over a short rectangle, inset from the header's outline, edged in gold
    rx, ry = ARCH_RX - 0.04, ARCH_RY - 0.03
    if py >= SHOULDER:
        d = (1.0 - math.hypot(px / rx, (py - SHOULDER) / ry)) * min(rx, ry)
    else:
        d = min(rx - abs(px), py - 0.045)
    if d > 0.0:
        k = T.clamp01(py / HEADER)
        return T.mix(T.scale(ENAMEL, 0.78), T.mix(ENAMEL, T.hexc("6A90D0"), 0.3), k)
    if d > -0.012:
        return T.mix(GOLD_LINE, T.hexc("FFF0B8"), 0.3)
    if abs(px) < OPEN_HW + BEAD_BLUE and py < BEAD_BLUE + 0.006:
        return _bead(c, max(py, abs(px) - OPEN_HW))
    e = _outline_dist(px, py)
    if 0.013 < e < 0.022:
        return T.mix(GOLD_LINE, T.hexc("FFF0B8"), 0.25)       # a gold pinstripe along the outline
    if e < 0.006:
        return T.scale(c, 0.7)
    return c


def p_slate_back(ctx, seed, p):
    return T.scale(T.g_wood(ctx, seed, {"kind": "dark", "along": "t"}), 0.85)


def p_gold(ctx, seed, p):
    return T.g_gold(ctx, seed, {"patina": 0.05})


def p_brass(ctx, seed, p):
    return T.g_brass(ctx, seed, {"streak": True, "patina": 0.06})


def p_ledge(ctx, seed, p):
    """Walnut ledge with a brass lip along its front and chalk dust on its top."""
    if ctx.chart == "+x":
        return T.mix(T.g_brass(ctx, seed + 3, {"streak": False}), T.hexc("FFE9A0"), 0.15)
    c = T.g_wood(ctx, seed, {"kind": "walnut", "along": "s"})
    if ctx.chart == "+z":
        n = T.noise(ctx.s * 14.0, ctx.t * 30.0, seed + 9)
        c = T.mix(c, T.hexc("C8CCC8"), T.smoothstep(0.5, 0.85, n) * 0.45)
    return c


CHALK_STICKS = ((-0.24, CHALK, 8.0), (-0.1, T.hexc("F4B8CC"), -12.0), (0.03, CHALK_BLUE, 5.0))


def p_chalk(ctx, seed, p):
    """Fat sticks of chalk, each its own colour, the ends a little brighter."""
    y = ctx.pos[1]
    col = min(CHALK_STICKS, key=lambda s: abs(s[0] - y))[1]
    v = T.noise(ctx.s * 40.0, ctx.t * 40.0, seed)
    c = T.scale(col, 0.88 + 0.12 * v)
    if ctx.chart in ("+y", "-y"):
        c = T.mix(c, (1.0, 1.0, 1.0), 0.25)
    return c


def p_eraser(ctx, seed, p):
    """A felt eraser: a light oak back, a grey felt pad full of chalk below."""
    z = ctx.pos[2]
    if z > Z_LEDGE + 0.024 or ctx.chart == "+z":
        return T.g_wood(ctx, seed, {"kind": "oak", "along": "s"})
    n = T.noise(ctx.s * 30.0, ctx.t * 30.0, seed + 3)
    return T.mix(T.hexc("8A8C90"), T.hexc("D8DAD8"), 0.35 + 0.35 * n)


# ------------------------------------------------------------------------------------------------ parts

def _header_outline():
    """The header's top outline, from its +Y foot round to its -Y foot (Y across, up from the header's bottom
    edge): shoulders and an elliptic arch to the crown."""
    pts = [(W / 2, 0.0), (W / 2, SHOULDER), (ARCH_RX, SHOULDER)]
    for k in range(1, 8):
        a = math.pi * k / 8.0
        pts.append((ARCH_RX * math.cos(a), SHOULDER + ARCH_RY * math.sin(a)))
    return pts + [(-ARCH_RX, SHOULDER), (-W / 2, SHOULDER), (-W / 2, 0.0)]


HEADER_OUTLINE = _header_outline()


def _outline_dist(px, py):
    best = 1e9
    for (x0, y0), (x1, y1) in zip(HEADER_OUTLINE, HEADER_OUTLINE[1:]):
        dx, dy = x1 - x0, y1 - y0
        t = max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / (dx * dx + dy * dy)))
        best = min(best, math.hypot(px - x0 - t * dx, py - y0 - t * dy))
    return best


def _header_polygon():
    """The header outline in board space (Y across, slope up), closed along its bottom edge."""
    return [(x, S0 + y) for x, y in HEADER_OUTLINE[-1:] + HEADER_OUTLINE[:-1]]


def _board_matrix(back):
    """Board space (outer face at x 0, the board behind it to -TB, Y across, Z up the slope from the foot)
    to model space: lean back by THETA, the outer top edge at the apex; the back board turned round."""
    m = G.mat_chain(G.mat_translate(X_FOOT, 0.0, TB * SIN), G.mat_rot_y(-THETA))
    if back:
        m = G.mat_chain(G.mat_rot_z(math.pi), m)
    return G.mat_chain(G.mat_translate(-SHIFT, 0.0, 0.0), m)


def _mitre(mesh, back):
    """Cuts a board's top at the A-frame's middle plane: the boards meet with their outer top edges at the
    apex, so near the top each one's thickness would show through the other; vertices beyond the plane are
    moved onto it (only the inner top corners move)."""
    out = mesh.copy()
    out.p = [((min(x, -SHIFT) if back else max(x, -SHIFT)), y, z) for x, y, z in mesh.p]
    return out


def _board(add, back):
    """One board: two stiles, the bottom rail, the arched header with its medallion, the slate (on the face or
    back texture) and the plain inner side of the panel."""
    m = _board_matrix(back)
    tag = "back_" if back else ""
    yc = OPEN_HW + STILE / 2
    stiles = [G.translate(G.box(STILE, TB, S0, faces="+x -x +y -y"), -TB / 2, sy * yc, 0.0) for sy in (1, -1)]
    stiles = _mitre(G.transform(G.merge(stiles), m), back)
    for ch in stiles.charts:
        ch.weight = 1.0 if ch.name == "+x" else 0.45
    add(B.Part(tag + "stiles", stiles, paint=frame_paint(back), seed=11 if not back else 12))
    rail = G.translate(G.box(2 * OPEN_HW, TB, RAIL1 - RAIL0, faces="+x -x +z -z", z0=RAIL0), -TB / 2, 0.0, 0.0)
    rail = G.transform(rail, m)
    for ch in rail.charts:
        ch.weight = 1.0 if ch.name == "+x" else 0.5
    add(B.Part(tag + "rail", rail, paint=p_rail, seed=13))
    head = G.extrude(_header_polygon(), TB, 0.0, True, name="header")
    head = _mitre(G.transform(head, G.mat_chain(m, G.mat_translate(-TB, 0.0, 0.0), G.MAT_EXTRUDE_FRONT)), back)
    for ch in head.charts:
        ch.weight = {"header_front": 1.0, "header_side": 0.5}.get(ch.name, 0.3)
    add(B.Part(tag + "header", head, texture="face", paint=p_header, seed=15))
    med = G.cylinder(MED_R, MED_D, 10, (False, True))
    med = G.transform(med, G.mat_chain(m, G.mat_translate(0.0, 0.0, S_MED), G.MAT_DISC_FRONT))
    for ch in med.charts:
        ch.weight = 1.6 if ch.name == "cyl_top" else 0.5
    add(B.Part(tag + "medallion", med, texture="face", paint=p_gold, seed=17,
               decals={"cyl_top": d_medallion}, ao_floor=0.7))
    slate = G.translate(G.box(SLATE_W, 0.002, SLATE_H, faces="+x", z0=RAIL1), -RECESS - 0.001, 0.0, 0.0)
    slate = G.transform(slate, m)
    if back:
        G.uv_region(slate, (0, 0, 512, 512))
        add(B.Part("back_slate", slate, texture="back", paint=("flat", {}), seed=19, decals={"+x": d_back}))
    else:
        G.uv_region(slate, (0, 0) + FACE_PX)
        add(B.Part("slate", slate, texture="face", paint=("flat", {}), seed=19, decals={"+x": d_front}))
    inner = G.translate(G.box(SLATE_W, 0.002, SLATE_H, faces="-x", z0=RAIL1), -TB + 0.001, 0.0, 0.0)
    add(B.Part(tag + "panel_inside", _mitre(G.transform(inner, m), back), paint=p_slate_back, seed=21, weight=0.3))


def build(opts=None):
    d = B.PropDef(NAME)
    d.display = DISPLAY
    d.size = (W, D, H)
    d.budget = 300
    d.kind = "chalkboard"
    d.atlas = {"atlas": 256, "face": (512, 1024), "back": 512}
    d.tex_flags = {"face": 0, "back": 0}
    d.sloped_top = True
    add = d.add

    _board(add, False)
    _board(add, True)

    # the chalk ledge on the front board's rail: level, its back sunk into the board, a brass lip in front
    x0 = x_face(Z_LEDGE) - 0.006
    x1 = X_LEDGE
    ledge = G.box(SLATE_W + 0.03, x1 - x0, LEDGE_H, faces="+x +y -y +z -z", z0=Z_LEDGE - LEDGE_H)
    ledge = G.translate(ledge, (x0 + x1) / 2 - SHIFT, 0.0, 0.0)
    add(B.Part("ledge", ledge, paint=p_ledge, seed=31, weight=1.2))
    cx = x_face(Z_LEDGE) + 0.024 - SHIFT
    sticks = []
    for y, _c, deg in CHALK_STICKS:
        st = G.box(0.11, 0.034, 0.034, faces="+x -x +y -y +z")
        sticks.append(G.transform(st, G.mat_chain(G.mat_translate(cx, y, Z_LEDGE), G.mat_rot_z(math.radians(deg)))))
    add(B.Part("chalk", G.merge(sticks), paint=p_chalk, seed=33, ao_floor=0.75))
    eraser = G.translate(G.box(0.13, 0.042, 0.04, faces="+x -x +y -y +z", z0=Z_LEDGE), cx - 0.002, 0.22, 0.0)
    add(B.Part("eraser", eraser, paint=p_eraser, seed=35, ao_floor=0.75))

    # brass spreader bars between the boards, inside each pair of stiles
    zs = 0.56
    xin = X_FOOT - TB * COS - (zs + 0.02) * SIN / COS
    bars = [G.translate(G.box(0.012, 2 * xin + 0.02, 0.04, faces="+y -y +z -z", z0=zs), -SHIFT,
                        sy * (OPEN_HW + STILE / 2), 0.0) for sy in (1, -1)]
    add(B.Part("spreaders", G.merge(bars), paint=p_brass, seed=37, weight=0.6))

    # collision: an A-shaped gable over the footprint (the roof is far steeper than walkable)
    d.collision = G.hull_gable(W, D, 0.08, H)
    d.particles = []
    return d
