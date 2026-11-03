"""Lettering (CAFE.SPEC.md section 5.5.1). Both fonts are original and defined here.

* Vector lettering for titles and machine plates: a painted serif capital set (plus digits and punctuation)
  drawn as stroke paths in a 100-unit cap-height box (y down, baseline at 100), rasterized with the stroke
  rasterizer of Tools/UiLint/make_art.py. Serifs are added at every stroke end that sits on the cap line or the
  baseline. Two-tone (fill + dark outline) so DXT keeps it readable.
* The 7 x 9 pixel font for small menu lines: glyph rows as hex (bit 0x40 = leftmost column), capitals 7 rows
  tall, descenders in rows 7-8, 1 px between glyphs and 3 px for a space. Renderers: chalk, engrave, paint.

The vector set has a lower case for the chalkboard titles ("The Lion's" / "Roast", "Welcome!"): x-height 62,
ascenders at the cap line, descenders to 132 (a text with g, j, p, q or y gets that much more room below).
`squeeze` narrows the lettering horizontally (tall chalk titles: section 5.5.1 wants caps of 70-90 px on a
512 px board, which "The Grinding" only reaches condensed). chalk_mask composites any coverage mask (vector
lettering, emblem.line_mask icons) as chalk. vector_mask raises KeyError for characters the set lacks.
"""

import math

from . import raster2d as R
from . import tex as T

# ------------------------------------------------------------------------------------------- pixel font

PIXEL_GLYPHS = {
    'A': (5, "3844447C4444440000"), 'B': (5, "784444784444780000"), 'C': (5, "384440404044380000"),
    'D': (5, "704844444448700000"), 'E': (5, "7C40407840407C0000"), 'F': (5, "7C4040784040400000"),
    'G': (5, "3844405C44443C0000"), 'H': (5, "4444447C4444440000"), 'I': (3, "702020202020700000"),
    'J': (5, "1C0808084848300000"), 'K': (5, "444850605048440000"), 'L': (5, "4040404040407C0000"),
    'M': (5, "446C54544444440000"), 'N': (5, "4464544C4444440000"), 'O': (5, "384444444444380000"),
    'P': (5, "784444784040400000"), 'Q': (5, "384444445448340000"), 'R': (5, "784444785048440000"),
    'S': (5, "3C4040380404780000"), 'T': (5, "7C1010101010100000"), 'U': (5, "444444444444380000"),
    'V': (5, "444444442828100000"), 'W': (5, "44444454546C440000"), 'X': (5, "444428102844440000"),
    'Y': (5, "444428101010100000"), 'Z': (5, "7C04081020407C0000"),
    'a': (5, "000038043C443C0000"), 'b': (5, "404078444444780000"), 'c': (5, "000038404040380000"),
    'd': (5, "04043C4444443C0000"), 'e': (5, "000038447C40380000"), 'f': (4, "182020702020200000"),
    'g': (5, "00003C4444443C0438"), 'h': (5, "404058644444440000"), 'i': (3, "200060202020700000"),
    'j': (3, "100030101010105020"), 'k': (4, "404048506050480000"), 'l': (3, "602020202020700000"),
    'm': (5, "000068545444440000"), 'n': (5, "000058644444440000"), 'o': (5, "000038444444380000"),
    'p': (5, "000078444444784040"), 'q': (5, "00003C4444443C0404"), 'r': (5, "000058644040400000"),
    's': (5, "00003C403804780000"), 't': (4, "202070202028100000"), 'u': (5, "00004444444C340000"),
    'v': (5, "000044444428100000"), 'w': (5, "000044445454280000"), 'x': (5, "000044281028440000"),
    'y': (5, "0000444444443C0438"), 'z': (5, "00007C0810207C0000"), 'é': (5, "081038447C40380000"),
    '0': (5, "38444C546444380000"), '1': (5, "103010101010380000"), '2': (5, "3844040810207C0000"),
    '3': (5, "7C0810080444380000"), '4': (5, "081828487C08080000"), '5': (5, "7C4078040444380000"),
    '6': (5, "182040784444380000"), '7': (5, "7C0408102020200000"), '8': (5, "384444384444380000"),
    '9': (5, "3844443C0408300000"),
    '.': (1, "000000000000400000"), ',': (2, "000000000020204000"), ':': (1, "000040000000400000"),
    ';': (2, "000020000000202040"), "'": (1, "404000000000000000"), '!': (1, "404040404000400000"),
    '?': (5, "384404081000100000"), '-': (4, "000000780000000000"), '+': (5, "0010107C1010000000"),
    '&': (5, "304850205448340000"), '(': (3, "102040404020100000"), ')': (3, "402010101020400000"),
    '/': (5, "040808102020400000"), '·': (1, "000000400000000000"),
}
PIXEL_CHARSET = ("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.,:;'!?-+&()/·é")
PIXEL_H = 9
SPACE_PX = 3


def pixel_bits(ch):
    w, hx = PIXEL_GLYPHS[ch]
    rows = [int(hx[2 * i:2 * i + 2], 16) for i in range(PIXEL_H)]
    return w, [[(r >> (6 - c)) & 1 for c in range(w)] for r in rows]


def pixel_measure(text):
    w = 0
    for i, ch in enumerate(text):
        if ch == " ":
            w += SPACE_PX
            continue
        if ch not in PIXEL_GLYPHS:
            raise KeyError("pixel font has no glyph for %r" % ch)
        w += PIXEL_GLYPHS[ch][0] + (1 if i < len(text) - 1 else 0)
    return w, PIXEL_H


def pixel_cells(text):
    """[(x, y)] of lit cells, x from 0, y 0..8."""
    out = []
    x = 0
    for ch in text:
        if ch == " ":
            x += SPACE_PX
            continue
        w, bits = pixel_bits(ch)
        for y in range(PIXEL_H):
            for c in range(w):
                if bits[y][c]:
                    out.append((x + c, y))
        x += w + 1
    return out


def pixel_mask(text, scale, w=None, h=None, ox=0, oy=0):
    tw, th = pixel_measure(text)
    m = R.Mask(w or tw * scale + 2 * ox, h or th * scale + 2 * oy)
    for cx, cy in pixel_cells(text):
        for yy in range(scale):
            for xx in range(scale):
                x, y = ox + cx * scale + xx, oy + cy * scale + yy
                if 0 <= x < m.w and 0 <= y < m.h:
                    m.a[y * m.w + x] = 1.0
    return m


def paint(img, text, color, scale, ox, oy, alpha=1.0):
    """Plain painted pixel text into an Img."""
    for cx, cy in pixel_cells(text):
        for yy in range(scale):
            for xx in range(scale):
                x, y = ox + cx * scale + xx, oy + cy * scale + yy
                if 0 <= x < img.w and 0 <= y < img.h:
                    img.blend(x, y, color, alpha)


def engrave(img, text, scale, ox, oy, dark=(0.18, 0.12, 0.06), light=(1.0, 0.92, 0.65)):
    """Dark fill with a 1 px highlight below (engraved into metal)."""
    cells = set(pixel_cells(text))
    for cx, cy in cells:
        for yy in range(scale):
            for xx in range(scale):
                x, y = ox + cx * scale + xx, oy + cy * scale + yy
                if 0 <= x < img.w and 0 <= y < img.h:
                    img.blend(x, y, dark, 0.95)
        if (cx, cy + 1) not in cells:
            y = oy + (cy + 1) * scale
            for xx in range(scale):
                x = ox + cx * scale + xx
                if 0 <= x < img.w and 0 <= y < img.h:
                    img.blend(x, y, light, 0.7)


def chalk(img, text, scale, ox, oy, seed=1, color=(0.95, 0.94, 0.9)):
    """Each pixel a soft dab with low-frequency noise, about +-0.3 px jitter, and a faint dust smudge."""
    for k, (cx, cy) in enumerate(pixel_cells(text)):
        jx = (T._h(cx, cy, 1, seed) - 0.5) * 0.6
        jy = (T._h(cx, cy, 2, seed) - 0.5) * 0.6
        px = ox + (cx + 0.5 + jx) * scale
        py = oy + (cy + 0.5 + jy) * scale
        r = scale * 0.62
        for y in range(int(py - r - 2), int(py + r + 3)):
            for x in range(int(px - r - 2), int(px + r + 3)):
                if not (0 <= x < img.w and 0 <= y < img.h):
                    continue
                d = math.hypot(x + 0.5 - px, y + 0.5 - py)
                n = T.noise(x * 0.35, y * 0.35, seed)
                a = T.smoothstep(r + 0.8, r - 0.6, d) * (0.65 + 0.35 * n)
                img.blend(x, y, color, a)
                if d < r + 2.5:
                    img.blend(x, y, color, 0.05)


# ----------------------------------------------------------------------------------------- vector font

VECTOR_GLYPHS = {
    # char: (advance, stroke path in a 100-unit cap box, y down, baseline 100)
    "A": (100, "M8 100 L50 0 L92 100 M26 64 H74"),
    "B": (86, "M16 0 V100 M16 0 H52 C80 0 80 47 52 47 H16 M52 47 C86 47 86 100 52 100 H16"),
    "C": (92, "M86 20 C74 2 60 0 52 0 C20 0 10 28 10 50 C10 76 22 100 52 100 C66 100 78 94 87 80"),
    "D": (92, "M16 0 V100 M16 0 H44 C78 0 86 28 86 50 C86 72 78 100 44 100 H16"),
    "E": (84, "M16 0 V100 M16 0 H78 M16 48 H64 M16 100 H80"),
    "F": (80, "M16 0 V100 M16 0 H78 M16 48 H62"),
    "G": (96, "M86 20 C74 2 60 0 52 0 C20 0 10 28 10 50 C10 76 22 100 52 100 C70 100 86 92 88 74 V56 H58"),
    "H": (100, "M16 0 V100 M84 0 V100 M16 50 H84"),
    "I": (46, "M23 0 V100"),
    "J": (70, "M56 0 V70 C56 92 46 100 32 100 C18 100 10 92 8 80"),
    "K": (90, "M16 0 V100 M82 0 L16 64 M40 42 L86 100"),
    "L": (80, "M16 0 V100 H78"),
    "M": (112, "M14 100 V0 L56 72 L98 0 V100"),
    "N": (100, "M16 100 V0 L84 100 V0"),
    "O": (100, "M50 0 C20 0 8 26 8 50 C8 74 20 100 50 100 C80 100 92 74 92 50 C92 26 80 0 50 0 Z"),
    "P": (84, "M16 100 V0 H50 C76 0 80 18 80 27 C80 38 74 54 50 54 H16"),
    "Q": (100, "M50 0 C20 0 8 26 8 50 C8 74 20 100 50 100 C80 100 92 74 92 50 C92 26 80 0 50 0 Z M56 72 L92 106"),
    "R": (90, "M16 100 V0 H50 C76 0 80 18 80 27 C80 38 74 54 50 54 H16 M46 54 L86 100"),
    "S": (84, "M76 14 C68 4 58 0 44 0 C26 0 14 10 14 26 C14 58 76 42 76 74 C76 92 62 100 42 100 C28 100 14 94 8 84"),
    "T": (92, "M6 0 H86 M46 0 V100"),
    "U": (100, "M16 0 V64 C16 88 30 100 50 100 C70 100 84 88 84 64 V0"),
    "V": (96, "M6 0 L48 100 L90 0"),
    "W": (124, "M4 0 L32 100 L62 22 L92 100 L120 0"),
    "X": (94, "M10 0 L84 100 M84 0 L10 100"),
    "Y": (94, "M8 0 L47 52 L86 0 M47 52 V100"),
    "Z": (90, "M12 0 H80 L10 100 H82"),
    "0": (80, "M40 0 C16 0 8 24 8 50 C8 76 16 100 40 100 C64 100 72 76 72 50 C72 24 64 0 40 0 Z"),
    "1": (60, "M14 18 L34 0 V100 M16 100 H52"),
    "2": (80, "M10 20 C14 6 26 0 40 0 C58 0 70 10 70 28 C70 52 10 70 10 100 H72"),
    "3": (80, "M10 12 C18 4 28 0 40 0 C58 0 68 10 68 26 C68 40 58 48 38 48 C60 48 72 58 72 74 C72 92 58 100 40 100"
               " C26 100 14 94 8 86"),
    "4": (84, "M58 100 V0 L6 70 H80"),
    "5": (80, "M70 0 H18 L14 46 C22 40 30 38 40 38 C60 38 72 52 72 70 C72 88 58 100 40 100 C26 100 14 94 8 86"),
    "6": (80, "M66 8 C58 2 50 0 42 0 C20 0 8 22 8 54 C8 82 20 100 40 100 C60 100 72 88 72 70 C72 52 60 40 42 40"
               " C26 40 12 48 8 60"),
    "7": (78, "M8 0 H72 L32 100"),
    "8": (80, "M40 48 C22 48 12 40 12 25 C12 10 24 0 40 0 C56 0 68 10 68 25 C68 40 58 48 40 48 C20 48 8 60 8 74"
               " C8 90 22 100 40 100 C58 100 72 90 72 74 C72 60 60 48 40 48 Z"),
    "9": (80, "M14 92 C22 98 30 100 38 100 C60 100 72 78 72 46 C72 18 60 0 40 0 C20 0 8 12 8 30 C8 48 20 60 38 60"
               " C54 60 68 52 72 40"),
    "-": (56, "M10 58 H46"),
    "'": (30, "M15 0 V26"),
    ".": (30, "M15 94 L15 94"),
    ",": (30, "M17 92 L10 110"),
    "!": (34, "M17 0 V66 M17 94 L17 94"),
    "?": (74, "M10 18 C16 6 26 0 38 0 C56 0 66 10 66 24 C66 44 38 48 38 70 M38 94 L38 94"),
    "&": (96, "M86 100 L26 36 C18 26 18 18 18 14 C18 6 26 0 36 0 C46 0 54 6 54 16 C54 30 40 38 30 46 C16 56 10 64"
               " 10 76 C10 90 22 100 38 100 C56 100 72 88 84 66"),
    "·": (30, "M15 50 L15 50"),
    ":": (30, "M15 40 L15 40 M15 94 L15 94"),
    "(": (44, "M36 -6 C14 18 14 82 36 106"),
    ")": (44, "M8 -6 C30 18 30 82 8 106"),
    "/": (60, "M52 -4 L8 104"),
}
VECTOR_LOWER = {
    # x-height 62 (y 38-100), ascenders from 0, descenders to 132
    "a": (82, "M18 46 C26 39 36 36 46 36 C60 36 68 44 68 56 V100 M68 64 C60 59 50 58 40 58 C24 58 14 66 14 80"
              " C14 94 24 100 36 100 C50 100 62 92 68 82"),
    "b": (86, "M14 0 V100 M14 60 C22 44 34 36 46 36 C64 36 76 50 76 68 C76 88 64 100 46 100 C34 100 22 92 14 80"),
    "c": (78, "M70 46 C62 39 54 36 46 36 C26 36 12 50 12 68 C12 88 26 100 46 100 C56 100 64 96 72 88"),
    "d": (86, "M70 0 V100 M70 60 C62 44 50 36 38 36 C20 36 10 50 10 68 C10 88 20 100 38 100 C50 100 62 92 70 80"),
    "e": (82, "M14 68 H72 C72 48 60 36 44 36 C24 36 12 50 12 68 C12 88 26 100 46 100 C58 100 66 96 72 88"),
    "f": (60, "M60 6 C55 2 50 0 44 0 C32 0 26 8 26 20 V100 M8 40 H54"),
    "g": (84, "M68 38 V108 C68 124 56 132 40 132 C28 132 18 128 12 120 M68 60 C60 44 50 36 38 36 C20 36 10 50"
              " 10 66 C10 84 20 96 38 96 C50 96 60 88 68 76"),
    "h": (86, "M14 0 V100 M14 58 C22 44 32 36 46 36 C62 36 72 46 72 62 V100"),
    "i": (48, "M24 40 V100 M24 12 L24 12"),
    "j": (50, "M30 40 V112 C30 126 22 132 10 132 M30 12 L30 12"),
    "k": (76, "M14 0 V100 M66 38 L14 78 M34 62 L70 100"),
    "l": (48, "M24 0 V100"),
    "m": (118, "M12 38 V100 M12 56 C18 44 26 36 38 36 C50 36 58 44 58 58 V100 M58 56 C64 44 72 36 84 36 C96 36"
               " 104 44 104 58 V100"),
    "n": (86, "M14 38 V100 M14 58 C22 44 32 36 46 36 C62 36 72 46 72 62 V100"),
    "o": (88, "M44 36 C24 36 12 50 12 68 C12 88 24 100 44 100 C64 100 76 88 76 68 C76 50 64 36 44 36 Z"),
    "p": (86, "M14 38 V132 M14 60 C22 44 34 36 46 36 C64 36 76 50 76 68 C76 88 64 100 46 100 C34 100 22 92 14 80"),
    "q": (86, "M70 38 V132 M70 60 C62 44 50 36 38 36 C20 36 10 50 10 68 C10 88 20 100 38 100 C50 100 62 92 70 80"),
    "r": (66, "M14 38 V100 M14 62 C20 46 30 36 44 36 C52 36 58 38 62 42"),
    "s": (76, "M64 44 C58 38 50 36 40 36 C26 36 16 42 16 54 C16 76 66 62 66 84 C66 96 54 100 40 100 C28 100 18 96"
              " 12 90"),
    "t": (62, "M28 8 V86 C28 96 34 100 42 100 C48 100 54 98 58 94 M8 40 H54"),
    "u": (86, "M14 38 V76 C14 92 24 100 38 100 C52 100 64 92 72 78 M72 38 V100"),
    "v": (80, "M8 38 L40 100 L72 38"),
    "w": (104, "M6 38 L28 100 L52 50 L76 100 L98 38"),
    "x": (78, "M10 38 L68 100 M68 38 L10 100"),
    "y": (80, "M8 38 L40 100 M72 38 L36 112 C30 126 22 132 10 132"),
    "z": (78, "M12 38 H66 L12 100 H68"),
    "é": (82, "M14 68 H72 C72 48 60 36 44 36 C24 36 12 50 12 68 C12 88 26 100 46 100 C58 100 66 96 72 88"
              " M38 22 L54 6"),
}
VECTOR_GLYPHS.update(VECTOR_LOWER)
VECTOR_CHARSET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-'.,!?&·:()/abcdefghijklmnopqrstuvwxyzé"
SPACE_ADV = 40
TRACKING = 8
DESCENDERS = "gjpqy"
DESCENT = 34          # extra room below the baseline (100-unit cap box) for a text with descenders


def _descent(text):
    return DESCENT if any(ch in DESCENDERS for ch in text) else 0


def vector_measure(text, cap, squeeze=1.0):
    """Width in pixels of `text` at cap height `cap` (pixels), narrowed by `squeeze`."""
    k = cap / 100.0 * squeeze
    w = 0.0
    for i, ch in enumerate(text):
        if ch == " ":
            w += SPACE_ADV
            continue
        if ch not in VECTOR_GLYPHS:
            raise KeyError("vector lettering has no glyph for %r" % ch)
        w += VECTOR_GLYPHS[ch][0] + (TRACKING if i < len(text) - 1 else 0)
    return w * k


def _serifs(polys, sw):
    out = []
    for poly in polys:
        if len(poly) < 2:
            continue
        for end, nxt in ((poly[0], poly[1]), (poly[-1], poly[-2])):
            if abs(end[1]) < 1.5 or abs(end[1] - 100) < 1.5:
                dx, dy = nxt[0] - end[0], nxt[1] - end[1]
                if abs(dy) > abs(dx) * 0.4:   # not a horizontal stroke end
                    hl = sw * 1.05
                    out.append([(end[0] - hl, end[1]), (end[0] + hl, end[1])])
    return out


def vector_mask(text, cap, w=None, h=None, ox=0.0, oy=0.0, weight=0.16, serif=True, squeeze=1.0):
    """Coverage mask of `text`, cap height `cap` px, top-left of the cap box at (ox, oy). The mask is tall
    enough for descenders when the text has any; `squeeze` narrows the letters (the stroke keeps its width)."""
    k = cap / 100.0
    kx = k * squeeze
    tw = vector_measure(text, cap, squeeze)
    sw = 100.0 * weight
    pad = sw * k
    m = R.Mask(int(w or math.ceil(tw + 2 * pad + 2 * ox)),
               int(h or math.ceil(cap + 2 * pad + 2 * oy + _descent(text) * k)))
    x = 0.0
    strokes = []
    serifs = []
    for ch in text:
        if ch == " ":
            x += SPACE_ADV
            continue
        adv, d = VECTOR_GLYPHS[ch]
        polys = R.parse(d)
        moved = [[(x + px, py) for px, py in poly] for poly in polys]
        strokes.extend(moved)
        if serif:
            serifs.extend(_serifs(moved, sw))
        x += adv + TRACKING
    R.stroke(m, R.xform_polys(strokes, kx, k, ox + pad, oy + pad), sw * k)
    if serifs:
        R.stroke(m, R.xform_polys(serifs, kx, k, ox + pad, oy + pad), sw * k * 0.55)
    return m


def fit_cap(text, box_w, box_h, weight=0.16, min_cap=8.0, squeeze=1.0):
    """The largest cap height (px) at which `text` fits the box (descenders included when the text has any);
    raises ValueError when it would be below min_cap (section 5.5.1: a test renders every text into its region
    and fails when it does not fit)."""
    pad_k = 2 * weight
    cap_h = box_h / (1.0 + pad_k + _descent(text) / 100.0)
    w100 = vector_measure(text, 100.0, squeeze) / 100.0
    cap_w = box_w / (w100 + pad_k)
    cap = min(cap_h, cap_w)
    if cap < min_cap:
        raise ValueError("%r does not fit %dx%d px (cap %.1f px < %.1f)" % (text, box_w, box_h, cap, min_cap))
    return cap


def two_tone(img, mask, fill, outline, ox=0, oy=0, outline_px=1, shadow=(1, 1), shadow_c=None):
    """Composites lettering as a fill with a dark outline (and an optional drop shadow) into an Img."""
    out = R.dilate(mask, outline_px) if outline_px else mask
    if shadow and shadow_c is not None:
        sx, sy = shadow
        for y in range(mask.h):
            for x in range(mask.w):
                a = out.a[y * mask.w + x]
                X, Y = ox + x + sx, oy + y + sy
                if a > 0 and 0 <= X < img.w and 0 <= Y < img.h:
                    img.blend(X, Y, shadow_c, a * 0.6)
    for y in range(mask.h):
        for x in range(mask.w):
            X, Y = ox + x, oy + y
            if not (0 <= X < img.w and 0 <= Y < img.h):
                continue
            a = out.a[y * mask.w + x]
            if a > 0:
                img.blend(X, Y, outline, a)
            f = mask.a[y * mask.w + x]
            if f > 0:
                img.blend(X, Y, fill, f)


def chalk_mask(img, mask, ox=0, oy=0, seed=1, color=(0.93, 0.94, 0.9), dust=0.3, grain=0.4):
    """Composites a coverage mask (vector lettering, emblem.line_mask line art) as chalk: strokes whose coverage
    breaks up in low-frequency grain (features of 5 px or more, so DXT and the mips keep it), a little brighter
    where the chalk pressed hardest, and a soft dust halo around them."""
    halo = R.blur(mask, max(2, int(round(min(mask.w, mask.h) * 0.012)) + 2))
    for y in range(mask.h):
        Y = oy + y
        if not 0 <= Y < img.h:
            continue
        for x in range(mask.w):
            X = ox + x
            if not 0 <= X < img.w:
                continue
            i = y * mask.w + x
            hv = halo.a[i]
            if hv > 0.0:
                img.blend(X, Y, color, hv * dust * 0.5)
            a = mask.a[i]
            if a > 0.0:
                n = T.noise(X * 0.19, Y * 0.19, seed)
                n2 = T.noise(X * 0.07, Y * 0.07, seed + 1)
                ca = a * (1.0 - grain * T.smoothstep(0.5, 0.85, n)) * (0.82 + 0.18 * n2)
                img.blend(X, Y, color, ca)
    return img
