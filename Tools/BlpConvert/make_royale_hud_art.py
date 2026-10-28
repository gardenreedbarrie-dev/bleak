#!/usr/bin/env python3
"""Draws the Bleakhold Royale HUD art ("Stormforged bronze") into Interface/AddOns/Bleakhold/Art/Royale and writes
Interface/AddOns/Bleakhold/RoyaleArtData.lua, the table of every atlas cell the addon lays out from.

Usage: python3 -I make_royale_hud_art.py [--out DIR] [--data FILE] [--preview DIR] [--stub] [--check DIR]

  --preview DIR  also write every texture as PNG, a contact sheet and mock-ups of the countdown and the drop plate
  --stub         flat placeholder art in the same files, sizes and cells (seconds instead of two minutes), so the addon
                 can be built against the real table before the final art is drawn
  --check DIR    draw everything into DIR and fail when a committed file differs (art and RoyaleArtData.lua); the
                 bytes depend on the Pillow, FreeType and numpy builds, so check with the versions that drew them

Needs Pillow and numpy. Everything is drawn here from shapes, height fields and noise (no game data); the numerals,
DROP! and the titles are set in Cinzel Bold (OFL, Tools/BlpConvert/fonts, used at build time only), whose figures are
aligned optically below (Cinzel's 3, 5, 6 and 9 leave the cap band a little; the countdown must not bob). Marcellus SC
only labels the preview sheets. The design follows the Royale UX spec: sections 1.3 (palette), 1.6 (art inventory)
and 6.2 (the data table).

Formats (spec 1.6): interface textures are drawn with plain linear filtering and no mipmaps
(Engine/Source/Frame/CSimpleRender.cpp, s_textureFilterMode = GxTex_Linear), so every piece is drawn for its size on
screen. Crisp art is uncompressed 32-bit TGA, run-length encoded (Engine/Source/Images/tga.cpp decodes type 10):
DXT's 4x4 blocks smear a gradient next to a dark stroke. Uncompressed BLP is no option, Bleakhold.exe re-encodes
BLP colour encoding 3 to DXT5 when it opens one (blpconvert.py). Soft art (glows, speed lines, the storm edge) is
DXT5 BLP. A .blp of the same name wins over a .tga (TextureCreate tries BLP first), so replaced BLPs are deleted.

The generator fails (exit 1) when a glyph's ink, stroke and shadow leave its cell, a glow cell lacks a 3-sigma
gutter, a digit is not lining after alignment (ink bottom within 1.5 % of the cap from the baseline, top within 2 %),
a cell edge is not a multiple of 4, an atlas is not a power of two, or the widest two-digit countdown number at
countdown.twoDigitCap is wider than 88 % of the ring's inner disc.
"""

import argparse
import filecmp
import math
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True  # keep the repository free of __pycache__

import artkit as ak  # noqa: E402
import blpconvert as bc  # noqa: E402

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    raise SystemExit("make_royale_hud_art.py needs Pillow: pip install Pillow")
ak.need_numpy("make_royale_hud_art.py")
np = ak.np

REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
ADDON = os.path.join(REPO, "Interface", "AddOns", "Bleakhold")
OUT = os.path.join(ADDON, "Art", "Royale")
DATA = os.path.join(ADDON, "RoyaleArtData.lua")
GAME_DIR = "Interface\\AddOns\\Bleakhold\\Art\\Royale\\"
# Art under a new file name, keyed as before in RoyaleArtData.lua: older packages shipped Arrow.blp and Pin.blp, which a
# manual upgrade (the package copied over the game folder, Tools/Package/INSTALL.txt) keeps, and the client tries a
# path's .blp before its .tga (TextureCreate, Engine/Source/Services/Texture.cpp), so the old art would hide the new.
FILE_NAMES = {"Arrow": "SafeArrow", "Pin": "PinFlag"}
FILE_KEYS = {v: k for k, v in FILE_NAMES.items()}


def file_name(key):
    return FILE_NAMES.get(key, key)
FONT_NUM = os.path.join(HERE, "fonts", "Cinzel-Bold.ttf")
FONT_SC = os.path.join(REPO, "Interface", "AddOns", "Bleakhold", "Fonts", "MarcellusSC-Regular.ttf")
SS = 4  # supersampling of every drawn piece

# The Royale palette (spec 1.3); RoyaleStyle.lua's RS.C has the same tokens.
C = {
    "ironTop": "1E2127", "ironBottom": "121418",
    "bronzeHi": "F3DDA4", "bronze": "C9A25A", "bronzeLo": "7A5A2C", "bronzeDeep": "3B2A14",
    "parchment": "F2E8D0", "ash": "BDB4A0", "smoke": "8A8273", "gold": "E5C07B",
    "storm": "A66BE0", "stormLight": "D7B6FF", "stormDeep": "4B2A6E", "safe": "FFFFFF",
    "ember": "FF7A3D", "blood": "E5604F", "beast": "8FD14F",
    "orbSpeed": "6CC6D9", "orbRestore": "7FD47F", "orbBerserk": "FF9D3B",
    "ink": "1B0E06", "rimDark": "1A120A", "rimLight": "FFF1C8",
}


def col(name, alpha=255):
    return ak.rgb(C.get(name, name), alpha)


def c3(name):
    """A palette colour as a float RGB triple."""
    r, g, b, _ = col(name)
    return np.array([r, g, b], dtype=np.float32) / 255.0


# draw_logo's five-stop gold (make_login_art.py) and the same in neutral silver for tinted titles
GOLD_METAL = [(0.0, ak.rgb("fff3cf")), (0.38, ak.rgb("e2b768")), (0.52, ak.rgb("8a5a26")), (0.70, ak.rgb("c58d45")),
              (1.0, ak.rgb("5c3815"))]
SILVER_METAL = [(0.0, ak.rgb("f4f4f4")), (0.38, ak.rgb("dcdcdc")), (0.52, ak.rgb("7e7e7e")), (0.70, ak.rgb("b8b8b8")),
                (1.0, ak.rgb("6a6a6a"))]


class Fail(Exception):
    """A broken rule of spec 1.6; main() prints it and exits 1."""


def check(cond, msg):
    if not cond:
        raise Fail(msg)


def pow2(n):
    return n >= 8 and (n & (n - 1)) == 0


# ============================================================================================ glyphs and words

class Face:
    """A TrueType face measured once: its cap height (the ink of 'H') per point of size."""

    def __init__(self, path):
        check(os.path.isfile(path), "font missing: %s" % path)
        self.path = path
        probe = ImageFont.truetype(path, 1000)
        box = ink_box(probe, "H")
        self.cap_per_size = (box[3] - box[1]) / 1000.0
        self._cache = {}

    def font(self, cap_px):
        size = int(round(cap_px / self.cap_per_size))
        if size not in self._cache:
            self._cache[size] = ImageFont.truetype(self.path, size)
        return self._cache[size]


def ink_box(font, text, threshold=128):
    """The ink box of `text` drawn with its pen at the origin on the baseline: (left, top, right, bottom), pixels,
    counting pixels at least half covered (a box that counts any faint pixel overstates a round glyph by one)."""
    size = getattr(font, "size", 100)
    pad, base = size, int(size * 1.5)
    img = Image.new("L", (int(font.getlength(text)) + 2 * pad, base + size), 0)
    ImageDraw.Draw(img).text((pad, base), text, font=font, fill=255, anchor="ls")
    a = np.asarray(img) >= threshold
    ys, xs = np.nonzero(a)
    if len(xs) == 0:
        return (0, 0, 0, 0)
    return (xs.min() - pad, ys.min() - base, xs.max() + 1 - pad, ys.max() + 1 - base)


class Glyph:
    """One drawn glyph or word at supersampled resolution: its fill coverage (float), the pen origin and baseline in
    that picture, the ink box (after alignment) and the advance, all in supersampled pixels."""

    def __init__(self, fill, pen_x, base_y, ink, advance):
        self.fill, self.pen_x, self.base_y, self.ink, self.advance = fill, pen_x, base_y, ink, advance


def draw_text(face, text, cap, tracking=0.0, align_digits=False, pad=None):
    """Draws `text` at cap height `cap` (final pixels) into a supersampled coverage picture.

    With align_digits every digit is fitted vertically to the lining band of spec 1.6: Cinzel's 3, 5 and 9 dip up to
    8 % of the cap below the baseline and its 5 and 6 rise 5 % over the cap (old-style habits), which would make a
    countdown bob up and down every second. A digit whose ink leaves the band is resampled vertically so its ink
    spans the band, keeping its width and its pen position: an optical alignment of the same face, not another
    face. The stroke is drawn afterwards from the aligned shape, so it stays even."""
    capS = cap * SS
    font = face.font(capS)
    pad = int(capS * 0.25) if pad is None else pad  # room for the stroke, the shadow and the bevel maths
    # the lining band of spec 1.6 (ink bottom within 1.5 % of the cap from the baseline, top within 2 % of the cap
    # line), a hair inside it so rounding to final pixels cannot step over
    band_top, band_bot = -1.018 * capS, 0.013 * capS
    adv = []
    for i, ch in enumerate(text):
        adv.append(font.getlength(ch) + (tracking * capS if i < len(text) - 1 else 0))
    width = int(math.ceil(sum(adv))) + 2 * pad
    height = int(math.ceil(capS * 1.5)) + 2 * pad
    base_y = pad + int(round(capS * 1.15))
    canvas = np.zeros((height, width), dtype=np.float32)
    x = float(pad)
    for ch, a in zip(text, adv):
        g = Image.new("L", (int(a + capS) + 2 * pad, height), 0)
        gx = pad
        ImageDraw.Draw(g).text((gx, base_y), ch, font=font, fill=255, anchor="ls")
        arr = np.asarray(g, dtype=np.float32) / 255.0
        if align_digits and ch.isdigit():
            box = ink_box(font, ch)
            top, bot = box[1], box[3]
            want_top = max(top, band_top)
            want_bot = min(bot, band_bot)
            if (want_top, want_bot) != (top, bot):
                arr = fit_rows(arr, base_y + top, base_y + bot, base_y + want_top, base_y + want_bot)
        ox = int(math.floor(x)) - gx
        frac = x - math.floor(x)
        if frac > 1e-6:  # sub-pixel pen positions, by linear interpolation between columns
            shifted = np.zeros_like(arr)
            shifted[:, 1:] = arr[:, :-1] * frac
            shifted += arr * (1 - frac)
            arr = shifted
        x0, x1 = max(0, ox), min(width, ox + arr.shape[1])
        canvas[:, x0:x1] = np.maximum(canvas[:, x0:x1], arr[:, x0 - ox:x1 - ox])
        x += a
    ys, xs = np.nonzero(canvas >= 0.5)
    ink = (xs.min() - pad, ys.min() - base_y, xs.max() + 1 - pad, ys.max() + 1 - base_y)
    return Glyph(canvas, pad, base_y, ink, sum(adv))


def fit_rows(arr, top, bot, want_top, want_bot):
    """Resamples the rows of a glyph picture so the span top..bot lands on want_top..want_bot (y down)."""
    h = arr.shape[0]
    scale = (want_bot - want_top) / float(bot - top)
    ys = np.arange(h, dtype=np.float64)
    src = top + (ys - want_top) / scale  # inverse map: output row -> source row
    i0 = np.clip(np.floor(src).astype(int), 0, h - 1)
    i1 = np.clip(i0 + 1, 0, h - 1)
    t = (src - np.floor(src))[:, None].astype(np.float32)
    out = arr[i0] * (1 - t) + arr[i1] * t
    out[(src < 0) | (src > h - 1)] = 0
    return out


def metal_glyph(glyph, cap, stroke, shadow_dy, shadow_blur, metal, bevel=0.085, emboss=True):
    """Renders a coverage picture (supersampled) into the forged-metal look, still supersampled, straight alpha:

      fill    a vertical metal gradient over the cap height (draw_logo's five stops: cream, gold, a dark horizon at
              52 %, bronze, dark bronze), shaded by a chiselled bevel: an inner height ramp `bevel` caps wide, lit
              from the top left, so the top-left facets go pale and the bottom-right facets dark, like cast metal
      stroke  `stroke` final pixels of ink (1B0E06) all round, from an exact distance field, so the corners stay round
      shadow  the filled and stroked shape, moved down `shadow_dy` and blurred `shadow_blur` (final pixels), black 75 %
    """
    capS = cap * SS
    fill = glyph.fill
    inside = fill >= 0.5
    reach_out = int(math.ceil(stroke * SS)) + 2
    d_out = ak.edt(~inside, reach_out)
    stroke_a = 1.0 - ak.smoothstep(stroke * SS - 1.0, stroke * SS + 1.0, d_out)
    stroke_a = np.maximum(stroke_a, fill)
    rgba = np.zeros(fill.shape + (4,), dtype=np.float32)
    if shadow_blur > 0 or shadow_dy:
        sh = np.zeros_like(stroke_a)
        dy = int(round(shadow_dy * SS))
        if dy > 0:
            sh[dy:] = stroke_a[:-dy]
        else:
            sh[:] = stroke_a
        sh = ak.gblur(sh, shadow_blur * SS)
        rgba = ak.over(rgba, ak.layer((0, 0, 0), sh * 0.75))
    # the stroke: dark ink with a faint rim light on its outer top-left edge, so it reads as a cast lip
    rim_h = np.minimum(1.0, (stroke * SS + 1.0 - d_out) / (stroke * SS * 0.6 + 1.0)) * (stroke_a > 0)
    sd, _ = ak.shade(rim_h * stroke * SS * 0.35)
    ink = np.broadcast_to(c3("ink"), fill.shape + (3,)).copy()
    ink = ak.lit(ink, sd, lift=0.10)
    rgba = ak.over(rgba, ak.layer(ink, stroke_a))
    # the fill
    top = glyph.base_y - capS * 1.02
    span = capS * 1.04
    ys = (np.arange(fill.shape[0], dtype=np.float32) - top) / span
    base = ak.ramp(np.broadcast_to(ys[:, None], fill.shape), metal)
    if emboss:
        reach_in = int(math.ceil(bevel * capS)) + 2
        d_in = ak.edt(inside, reach_in)
        b = bevel * capS
        t = np.clip(d_in / b, 0.0, 1.0)
        height = b * 0.9 * (1.0 - (1.0 - t) ** 1.6)  # a chisel that rounds into the face
        dif, spec = ak.shade(ak.gblur(height, SS * 0.6), spec_power=28.0)
        base = ak.lit(base, 0.30 + 0.70 * dif, spec, lift=0.62, gloss=0.35)
    rgba = ak.over(rgba, ak.layer(base, fill))
    return rgba


def silhouette_glow(glyph, sigma_final, scale=0.5):
    """The white silhouette of a glyph (its fill) blurred sigma_final pixels at the glow atlas's resolution, which is
    `scale` of the art's; returns the glow coverage at supersampled art resolution reduced to glow resolution."""
    k = int(round(SS / scale))
    small = ak.reduce(glyph.fill, k)
    return ak.gblur(small, sigma_final)


# ============================================================================================ atlases of glyphs

class Atlas:
    """An atlas of uniform cells: name, picture size, cell size, cells per row."""

    def __init__(self, name, w, h, cell_w, cell_h, cap, baseline, stroke, chars, glow_sigma):
        self.name, self.w, self.h = name, w, h
        self.cell_w, self.cell_h, self.cap, self.baseline, self.stroke = cell_w, cell_h, cap, baseline, stroke
        self.chars, self.glow_sigma = chars, glow_sigma
        self.cols = w // cell_w
        self.glyphs = {}


NUMERAL_ATLASES = [
    # name, size, cell, cap, baseline, stroke, characters, glow sigma at half size (spec 1.6)
    Atlas("NumeralsL", 2048, 1024, 408, 512, 288, 400, 18, "0123456789", 9.0),
    Atlas("NumeralsM", 1024, 512, 204, 256, 144, 200, 9, "0123456789", 4.5),
    Atlas("NumeralsS", 1024, 256, 128, 128, 64, 100, 4, "0123456789#/", 2.5),
]


def build_numerals(face, atlas, stub=False):
    """Draws one numeral atlas and its half-size glow atlas; fills atlas.glyphs with the cell metrics."""
    art = np.zeros((atlas.h, atlas.w, 4), dtype=np.float32)
    glow = np.zeros((atlas.h // 2, atlas.w // 2), dtype=np.float32)
    shadow_dy, shadow_blur = 10.0 * atlas.cap / 288.0, 4.0 * atlas.cap / 288.0
    check(atlas.cell_w % 4 == 0 and atlas.cell_h % 4 == 0, "%s: cell %dx%d is not a multiple of 4"
          % (atlas.name, atlas.cell_w, atlas.cell_h))
    for i, ch in enumerate(atlas.chars):
        cx, cy = (i % atlas.cols) * atlas.cell_w, (i // atlas.cols) * atlas.cell_h
        g = draw_text(face, ch, atlas.cap, align_digits=True)
        l, t, r, b = (v / SS for v in g.ink)
        if ch.isdigit():
            check(abs(b) <= 0.015 * atlas.cap + 0.5, "%s '%s': ink bottom %.1f px from the baseline (not lining)"
                  % (atlas.name, ch, b))
            check(abs(-t - atlas.cap) <= 0.02 * atlas.cap + 0.5, "%s '%s': ink top %.1f px from the cap line"
                  % (atlas.name, ch, -t - atlas.cap))
        # centre the ink in the cell; the pen origin is then ox from the cell's left edge
        ox = (atlas.cell_w - (r - l)) / 2.0 - l
        ox = round(ox * SS) / SS
        if stub:
            piece = stub_glyph(g, atlas)
        else:
            piece = metal_glyph(g, atlas.cap, atlas.stroke, shadow_dy, shadow_blur, GOLD_METAL)
        cell = place(piece, g, atlas.cell_w, atlas.cell_h, ox, atlas.baseline, "%s '%s'" % (atlas.name, ch))
        art[cy:cy + atlas.cell_h, cx:cx + atlas.cell_w] = cell
        gl = place_glow(g, atlas.cell_w // 2, atlas.cell_h // 2, ox / 2.0, atlas.baseline / 2.0, atlas.glow_sigma,
                        "%sGlow '%s'" % (atlas.name, ch))
        glow[cy // 2:(cy + atlas.cell_h) // 2, cx // 2:(cx + atlas.cell_w) // 2] = gl
        atlas.glyphs[ch] = dict(
            u0=cx / atlas.w, u1=(cx + atlas.cell_w) / atlas.w, v0=cy / atlas.h, v1=(cy + atlas.cell_h) / atlas.h,
            advance=g.advance / SS / atlas.cap, inkL=l / atlas.cap, inkR=r / atlas.cap, ox=ox / atlas.cap)
    return art, glow


def place(piece, g, cell_w, cell_h, ox, baseline, what):
    """Puts a supersampled glyph rendering into a cell (final pixels) with its pen at ox and its baseline at
    `baseline`; fails when anything visible (alpha > 1/255) would be cut by the cell's edges."""
    big = np.zeros((cell_h * SS, cell_w * SS, 4), dtype=np.float32)
    dx = int(round(ox * SS)) - g.pen_x
    dy = int(round(baseline * SS)) - g.base_y
    vis = piece[..., 3] > (0.5 / 255.0)
    ys, xs = np.nonzero(vis)
    check(xs.min() + dx >= 0 and xs.max() + dx < cell_w * SS and ys.min() + dy >= 0 and ys.max() + dy < cell_h * SS,
          "%s: ink, stroke and shadow leave the %dx%d cell" % (what, cell_w, cell_h))
    h, w = piece.shape[:2]
    y0, x0 = max(0, dy), max(0, dx)
    y1, x1 = min(cell_h * SS, dy + h), min(cell_w * SS, dx + w)
    big[y0:y1, x0:x1] = piece[y0 - dy:y1 - dy, x0 - dx:x1 - dx]
    return ak.reduce(big, SS)


def place_glow(g, cell_w, cell_h, ox, baseline, sigma, what):
    """The glow cell: the glyph's white silhouette at half resolution, blurred `sigma`; fails without a 3-sigma
    gutter between the silhouette and the cell's edges."""
    k = SS * 2
    big = np.zeros((cell_h * k, cell_w * k), dtype=np.float32)
    dx = int(round(ox * k)) - g.pen_x
    dy = int(round(baseline * k)) - g.base_y
    h, w = g.fill.shape
    y0, x0 = max(0, dy), max(0, dx)
    y1, x1 = min(cell_h * k, dy + h), min(cell_w * k, dx + w)
    big[y0:y1, x0:x1] = g.fill[y0 - dy:y1 - dy, x0 - dx:x1 - dx]
    small = ak.reduce(big, k)
    ys, xs = np.nonzero(small > 0.02)
    gut = 3.0 * sigma
    check(xs.min() >= gut - 0.5 and cell_w - 1 - xs.max() >= gut - 0.5 and ys.min() >= gut - 0.5
          and cell_h - 1 - ys.max() >= gut - 0.5, "%s: no 3-sigma gutter (%.1f px) in the %dx%d cell"
          % (what, gut, cell_w, cell_h))
    blurred = ak.gblur(small, sigma)
    peak = blurred.max()
    return np.clip(blurred / peak if peak > 0 else blurred, 0.0, 1.0)


def stub_glyph(g, atlas):
    """Placeholder rendering: the glyph's shape in flat gold, no stroke, no shading."""
    return ak.layer(c3("gold"), g.fill)

TITLES = ["MATCH FOUND", "NEW STORM CIRCLE", "THE STORM MOVES", "SUPPLY DROP", "PLAYERS LEFT", "A BEAST STIRS",
          "THUNDERMAW AWAKENS", "THUNDERMAW SLAIN", "THUNDERMAW FLEES", "VICTORY", "ELIMINATED", "WINNER", "LANDED",
          "MATCH CANCELLED"]
TITLE_CAP, TITLE_ROW, TITLE_STROKE, TITLE_TRACKING, TITLE_GLOW = 64, 128, 6, 0.06, 4.0
DROP_CAP, DROP_STROKE, DROP_GLOW, DROP_TRACKING = 150, 10, 9.0, 0.03


def build_titles(face, stub=False):
    """The Titles atlas (2048x1024, rows of 128) and its glow: every fixed title in Cinzel Bold at cap 64 in neutral
    silver metal with a 6-px dark stroke, so SetVertexColor tints it to any palette token. Rows are packed widest
    first; each cell is the title's ink plus a margin that holds the stroke, the shadow and the glow's 3 sigma."""
    w, h = 2048, 1024
    art = np.zeros((h, w, 4), dtype=np.float32)
    glow = np.zeros((h // 2, w // 2), dtype=np.float32)
    margin = int(math.ceil((3 * TITLE_GLOW * 2 + TITLE_STROKE + 4) / 4.0)) * 4  # full-size pixels each side
    glyphs = {t: draw_text(face, t, TITLE_CAP, tracking=TITLE_TRACKING) for t in TITLES}
    cells = {}
    rows = []  # [x used]
    for t in sorted(TITLES, key=lambda s: -(glyphs[s].ink[2] - glyphs[s].ink[0])):
        g = glyphs[t]
        cw = int(math.ceil(((g.ink[2] - g.ink[0]) / SS + 2 * margin) / 4.0)) * 4
        check(cw <= w, "title %s is wider than the atlas" % t)
        for ri, used in enumerate(rows):
            if used + cw <= w:
                break
        else:
            rows.append(0)
            ri = len(rows) - 1
        check((ri + 1) * TITLE_ROW <= h, "the titles need more than %d rows" % (h // TITLE_ROW))
        x = rows[ri]
        rows[ri] += cw
        cells[t] = (x, ri * TITLE_ROW, cw)
    baseline = TITLE_ROW / 2.0 + TITLE_CAP / 2.0  # the cap's middle on the row's middle
    data = {}
    for t in TITLES:
        g = glyphs[t]
        x, y, cw = cells[t]
        ink_w = (g.ink[2] - g.ink[0]) / SS
        ox = round(((cw - ink_w) / 2.0 - g.ink[0] / SS) * SS) / SS
        if stub:
            piece = stub_glyph(g, Atlas("Titles", w, h, cw, TITLE_ROW, TITLE_CAP, baseline, TITLE_STROKE, "", 0))
        else:
            piece = metal_glyph(g, TITLE_CAP, TITLE_STROKE, 2.4, 1.2, SILVER_METAL, bevel=0.07)
        art[y:y + TITLE_ROW, x:x + cw] = place(piece, g, cw, TITLE_ROW, ox, baseline, "title %s" % t)
        glow[y // 2:(y + TITLE_ROW) // 2, x // 2:(x + cw) // 2] = place_glow(
            g, cw // 2, TITLE_ROW // 2, ox / 2.0, baseline / 2.0, TITLE_GLOW, "TitlesGlow %s" % t)
        data[t] = dict(u0=x / w, u1=(x + cw) / w, v0=y / h, v1=(y + TITLE_ROW) / h, w=cw / TITLE_CAP,
                       h=TITLE_ROW / TITLE_CAP, inkW=ink_w / TITLE_CAP)
    return art, glow, data, len(rows)


def build_dropword(face, stub=False):
    """DROP! (1024x512) in Cinzel Bold at cap 150, the gold metal recipe, a 10-px stroke; its glow at half size."""
    w, h = 1024, 512
    g = draw_text(face, "DROP!", DROP_CAP, tracking=DROP_TRACKING)
    ink_w = (g.ink[2] - g.ink[0]) / SS
    ox = round(((w - ink_w) / 2.0 - g.ink[0] / SS) * SS) / SS
    baseline = h / 2.0 + DROP_CAP / 2.0
    if stub:
        piece = stub_glyph(g, Atlas("DropWord", w, h, w, h, DROP_CAP, baseline, DROP_STROKE, "", 0))
    else:
        piece = metal_glyph(g, DROP_CAP, DROP_STROKE, 5.2, 2.2, GOLD_METAL, bevel=0.08)
    art = place(piece, g, w, h, ox, baseline, "DropWord")
    glow = place_glow(g, w // 2, h // 2, ox / 2.0, baseline / 2.0, DROP_GLOW, "DropWordGlow")
    word = dict(u0=0.0, u1=1.0, v0=0.0, v1=1.0, w=w / DROP_CAP, h=h / DROP_CAP, inkW=ink_w / DROP_CAP,
                advance=g.advance / SS / DROP_CAP, inkL=g.ink[0] / SS / DROP_CAP, inkR=g.ink[2] / SS / DROP_CAP,
                ox=ox / DROP_CAP)
    return art, glow, word, baseline


# ============================================================================================ shaded vector parts

def bronze_ramp():
    return [(0.0, col("bronzeDeep")), (0.30, col("bronzeLo")), (0.60, col("bronze")), (0.85, col("bronzeHi")),
            (1.0, ak.rgb("fff7df"))]


# name: colour stops dark -> light, base level, bevel contrast, gloss
MATERIALS = {
    "gold": ([(0.0, ak.rgb("2e1d0c")), (0.28, ak.rgb("6e4a1e")), (0.55, ak.rgb("c08f45")), (0.80, ak.rgb("ecc97c")),
              (1.0, ak.rgb("fff4d2"))], 0.60, 0.55, 0.55),
    "bronze": (None, 0.56, 0.55, 0.45),  # filled in below from the palette
    "steel": ([(0.0, ak.rgb("1b1f26")), (0.30, ak.rgb("454d59")), (0.58, ak.rgb("8a94a3")), (0.82, ak.rgb("c9d1db")),
               (1.0, ak.rgb("f7f9fc"))], 0.58, 0.55, 0.6),
    "silver": ([(0.0, ak.rgb("3a3a3c")), (0.30, ak.rgb("8a8a8e")), (0.58, ak.rgb("cfcfd2")), (0.82, ak.rgb("ececee")),
                (1.0, ak.rgb("ffffff"))], 0.66, 0.45, 0.5),
    "bone": ([(0.0, ak.rgb("3e3324")), (0.30, ak.rgb("857456")), (0.58, ak.rgb("c8b892")), (0.82, ak.rgb("e8dec4")),
              (1.0, ak.rgb("fffaec"))], 0.60, 0.5, 0.25),
    "wood": ([(0.0, ak.rgb("24160b")), (0.35, ak.rgb("553519")), (0.62, ak.rgb("8a5a2e")), (0.85, ak.rgb("b8834c")),
              (1.0, ak.rgb("deb07a"))], 0.55, 0.5, 0.15),
    "cloth": ([(0.0, ak.rgb("4a3e2c")), (0.30, ak.rgb("9a8c70")), (0.58, ak.rgb("d9cdb0")), (0.82, ak.rgb("f2e8d0")),
               (1.0, ak.rgb("fffbf0"))], 0.62, 0.45, 0.1),
    "storm": ([(0.0, ak.rgb("1e0c33")), (0.30, ak.rgb("4b2a6e")), (0.58, ak.rgb("a66be0")), (0.82, ak.rgb("d7b6ff")),
               (1.0, ak.rgb("ffffff"))], 0.58, 0.55, 0.5),
    "speed": ([(0.0, ak.rgb("0c2a33")), (0.30, ak.rgb("23697a")), (0.58, ak.rgb("6cc6d9")), (0.82, ak.rgb("b5ecf5")),
               (1.0, ak.rgb("ffffff"))], 0.58, 0.55, 0.45),
    "restore": ([(0.0, ak.rgb("0f2a10")), (0.30, ak.rgb("2f6e30")), (0.58, ak.rgb("7fd47f")), (0.82, ak.rgb("c3f0c0")),
                 (1.0, ak.rgb("ffffff"))], 0.58, 0.55, 0.45),
    "berserk": ([(0.0, ak.rgb("3a1404")), (0.30, ak.rgb("8a3a0c")), (0.58, ak.rgb("ff9d3b")), (0.82, ak.rgb("ffd29a")),
                 (1.0, ak.rgb("fff6e8"))], 0.58, 0.55, 0.45),
    "ember": ([(0.0, ak.rgb("3a0e04")), (0.30, ak.rgb("8f2e0c")), (0.58, ak.rgb("ff7a3d")), (0.82, ak.rgb("ffc08a")),
               (1.0, ak.rgb("fff2e0"))], 0.60, 0.5, 0.4),
    "blood": ([(0.0, ak.rgb("2e0806")), (0.30, ak.rgb("7a1c14")), (0.58, ak.rgb("c9473a")), (0.82, ak.rgb("ec8a7c")),
               (1.0, ak.rgb("ffe0da"))], 0.56, 0.5, 0.35),
    "beast": ([(0.0, ak.rgb("10240a")), (0.30, ak.rgb("3a6e1e")), (0.58, ak.rgb("8fd14f")), (0.82, ak.rgb("cdf0a2")),
               (1.0, ak.rgb("ffffff"))], 0.62, 0.45, 0.5),
    "glass": ([(0.0, ak.rgb("1a2a33")), (0.30, ak.rgb("41606e")), (0.58, ak.rgb("8db4c2")), (0.82, ak.rgb("cfe6ee")),
               (1.0, ak.rgb("ffffff"))], 0.55, 0.45, 0.8),
    "arcane": ([(0.0, ak.rgb("101a3a")), (0.30, ak.rgb("2e4a9a")), (0.58, ak.rgb("7aa0f0")), (0.82, ak.rgb("c6d8ff")),
                (1.0, ak.rgb("ffffff"))], 0.58, 0.6, 0.6),
    "iron": ([(0.0, ak.rgb("0a0b0d")), (0.30, ak.rgb("15171b")), (0.58, ak.rgb("262a31")), (0.82, ak.rgb("454c57")),
              (1.0, ak.rgb("7a8391"))], 0.45, 0.55, 0.35),
    "stone": ([(0.0, ak.rgb("1e1c1a")), (0.30, ak.rgb("4c4741")), (0.58, ak.rgb("8c857a")), (0.82, ak.rgb("c2bbae")),
               (1.0, ak.rgb("ece6da"))], 0.58, 0.5, 0.15),
    "white": ([(0.0, ak.rgb("5a5a5a")), (0.30, ak.rgb("a8a8a8")), (0.58, ak.rgb("e4e4e4")), (0.82, ak.rgb("f6f6f6")),
               (1.0, ak.rgb("ffffff"))], 0.70, 0.40, 0.35),
    "void": ([(0.0, ak.rgb("030202")), (0.5, ak.rgb("140d08")), (1.0, ak.rgb("3a2a1c"))], 0.35, 0.6, 0.0),
    "glowgreen": ([(0.0, ak.rgb("3a7a1e")), (0.5, ak.rgb("8fd14f")), (1.0, ak.rgb("f0ffd8"))], 0.75, 0.2, 0.0),
    "ink": (None, 0, 0, 0),  # flat dark lines
}
MATERIALS["bronze"] = (bronze_ramp(), 0.56, 0.55, 0.45)
INK = ak.rgb("0d0806")


def bez(p0, p1, p2, p3, n=20):
    """Points of a cubic Bezier curve (p0 excluded, p3 included)."""
    out = []
    for i in range(1, n + 1):
        t = i / float(n)
        a, b, c, d = (1 - t) ** 3, 3 * t * (1 - t) ** 2, 3 * t * t * (1 - t), t ** 3
        out.append((a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0], a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]))
    return out


def arc_pts(cx, cy, rx, ry, a0, a1, n=32):
    """Points on an ellipse from angle a0 to a1 (degrees, 0 = right, 90 = down: image coordinates)."""
    return [(cx + rx * math.cos(math.radians(a0 + (a1 - a0) * i / float(n))),
             cy + ry * math.sin(math.radians(a0 + (a1 - a0) * i / float(n)))) for i in range(n + 1)]


def rot(pts, cx, cy, deg):
    a = math.radians(deg)
    ca, sa = math.cos(a), math.sin(a)
    return [(cx + (x - cx) * ca - (y - cy) * sa, cy + (x - cx) * sa + (y - cy) * ca) for x, y in pts]


class Sketch:
    """A small picture drawn from parts at supersampled resolution, then shaded and outlined together: every part
    gets a bevel from its own distance field (lit from the top left, or from the front for art the addon rotates),
    a material ramp, and the union gets a dark outline and a soft drop shadow. Coordinates are 0..1 of the
    picture's width and height."""

    def __init__(self, w, h, ss=SS):
        self.w, self.h, self.k = w, h, ss
        self.W, self.H = w * ss, h * ss
        self.parts = []

    def _canvas(self):
        img = Image.new("L", (self.W, self.H), 0)
        return img, ImageDraw.Draw(img)

    def xy(self, pts):
        return [(x * self.W, y * self.H) for x, y in pts]

    def add(self, img, mat, bevel=None, cut=False, height=1.0):
        self.parts.append(dict(mask=np.asarray(img, dtype=np.float32) / 255.0, mat=mat, bevel=bevel, cut=cut,
                               height=height))

    def poly(self, pts, mat, **kw):
        img, d = self._canvas()
        d.polygon(self.xy(pts), fill=255)
        self.add(img, mat, **kw)

    def ellipse(self, cx, cy, rx, ry, mat, **kw):
        img, d = self._canvas()
        d.ellipse((( cx - rx) * self.W, (cy - ry) * self.H, (cx + rx) * self.W, (cy + ry) * self.H), fill=255)
        self.add(img, mat, **kw)

    def line(self, pts, width, mat, cap=True, **kw):
        """A polyline `width` final pixels wide (round joins and caps)."""
        img, d = self._canvas()
        wp = width * self.k
        q = self.xy(pts)
        d.line(q, fill=255, width=max(1, int(round(wp))), joint="curve")
        if cap:
            for x, y in (q[0], q[-1]):
                d.ellipse((x - wp / 2, y - wp / 2, x + wp / 2, y + wp / 2), fill=255)
        self.add(img, mat, **kw)

    def ring(self, cx, cy, r_out, r_in, mat, **kw):
        img, d = self._canvas()
        d.ellipse(((cx - r_out) * self.W, (cy - r_out) * self.H, (cx + r_out) * self.W, (cy + r_out) * self.H),
                  fill=255)
        d.ellipse(((cx - r_in) * self.W, (cy - r_in) * self.H, (cx + r_in) * self.W, (cy + r_in) * self.H), fill=0)
        self.add(img, mat, **kw)

    def custom(self, fn, mat, clip=None, **kw):
        """A part drawn by fn(draw, sketch); with clip=(cx, cy, r) it is kept only inside that circle."""
        img, d = self._canvas()
        fn(d, self)
        if clip is not None:
            m, md = self._canvas()
            cx, cy, r = clip
            md.ellipse(((cx - r) * self.W, (cy - r) * self.H, (cx + r) * self.W, (cy + r) * self.H), fill=255)
            img = Image.fromarray((np.asarray(img, dtype=np.uint16) * np.asarray(m, dtype=np.uint16) // 255)
                                  .astype(np.uint8))
        self.add(img, mat, **kw)

    def text(self, x, y, txt, cap, mat, font_path=None, **kw):
        """Text centred on (x, y) with its cap height `cap` (fraction of the picture's height)."""
        face = Face(font_path or FONT_NUM)
        font = face.font(cap * self.H)

        def draw(d, sk):
            d.text((x * sk.W, y * sk.H), txt, font=font, fill=255, anchor="mm")
        self.custom(draw, mat, **kw)

    def render(self, outline=2.0, bevel=2.0, front=False, grad=0.16, shadow=True, outline_rgb=INK):
        k = self.k
        masks = []
        for p in self.parts:
            if p["cut"]:
                masks = [None if m is None else m * (1.0 - p["mask"]) for m in masks]
                masks.append(None)
            else:
                masks.append(p["mask"].copy())
        union = np.zeros((self.H, self.W), dtype=np.float32)
        for m in masks:
            if m is not None:
                union = np.maximum(union, m)
        rgba = np.zeros((self.H, self.W, 4), dtype=np.float32)
        if outline > 0:
            wpx = outline * k
            d_out = ak.edt(union < 0.5, int(math.ceil(wpx)) + 2)
            out_a = np.maximum(1.0 - ak.smoothstep(wpx - k * 0.5, wpx + k * 0.5, d_out), union)
        else:
            out_a = union
        if shadow:
            sh = np.zeros_like(out_a)
            dy = int(round(k * 1.0))
            sh[dy:] = out_a[:-dy]
            sh = ak.gblur(sh, k * 1.0)
            rgba = ak.over(rgba, ak.layer((0, 0, 0), sh * 0.55))
        if outline > 0:
            rgba = ak.over(rgba, ak.layer(outline_rgb, out_a))
        light = np.array([0.0, 0.0, 1.0]) if front else ak.light_dir(315.0, 50.0)
        ys = np.linspace(0.5, -0.5, self.H, dtype=np.float32)[:, None] * np.ones((1, self.W), dtype=np.float32)
        for p, m in zip(self.parts, masks):
            if m is None or m.max() <= 0:
                continue
            stops, base, contrast, gloss = MATERIALS[p["mat"]]
            if stops is None:
                rgba = ak.over(rgba, ak.layer(outline_rgb, m))
                continue
            b = (p["bevel"] if p["bevel"] is not None else bevel) * k
            d_in = ak.edt(m >= 0.5, int(math.ceil(b)) + 2)
            t = np.clip(d_in / b, 0.0, 1.0)
            hgt = b * 0.85 * (1.0 - (1.0 - t) ** 1.7) * p["height"]
            if p["mat"] == "void":
                hgt = -hgt
            dif, spec = ak.shade(ak.gblur(hgt, k * 0.5), light, spec_power=22.0)
            if front:  # lit from the viewer: flat faces are 1.0, slopes darker; keep some sparkle on the faces
                v = base + (dif - 1.0) * contrast * 1.4 + spec * gloss * 0.25
            else:
                v = base + grad * ys + (dif - 1.0) * contrast * 1.25 + spec * gloss * 0.5
            rgba = ak.over(rgba, ak.layer(ak.ramp(v, stops), m))
        return ak.reduce(rgba, k)


# ============================================================================================ plates and frames

def convex_distance(w, h, pts):
    """Signed distance (pixels) to a convex polygon given clockwise in image coordinates: positive inside (the
    distance to the nearest edge), negative outside (approximately). Evaluated at pixel centres."""
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    xs += 0.5
    ys += 0.5
    d = np.full((h, w), 1e9, dtype=np.float32)
    n = len(pts)
    for i in range(n):
        (x0, y0), (x1, y1) = pts[i], pts[(i + 1) % n]
        ex, ey = x1 - x0, y1 - y0
        ln = math.hypot(ex, ey)
        nx, ny = -ey / ln, ex / ln  # inward normal for a clockwise polygon (y down)
        d = np.minimum(d, (xs - x0) * nx + (ys - y0) * ny)
    return d


def chamfer_rect(x0, y0, x1, y1, c):
    return [(x0 + c, y0), (x1 - c, y0), (x1, y0 + c), (x1, y1 - c), (x1 - c, y1), (x0 + c, y1), (x0, y1 - c),
            (x0, y0 + c)]


def brushed_noise(h, w, seed, sx=24.0, sy=0.6):
    """Horizontal brushed-metal streaks, zero mean, about unit amplitude."""
    rng = np.random.default_rng(seed)
    n = rng.standard_normal((h, w)).astype(np.float32)
    k, r = ak.gauss_kernel(sx)
    p = np.pad(n, ((0, 0), (r, r)), mode="wrap")
    acc = np.zeros_like(n)
    for i in range(2 * r + 1):
        acc += k[i] * p[:, i:i + w]
    acc = ak.gblur(acc, sy, wrap=True)
    return acc / max(1e-6, acc.std())


def iron_fill(h, w, d_fill, top, span, seed, inner=10.0):
    """The plate's iron: a vertical gradient ironTop -> ironBottom over rows top..top+span, brushed noise of
    +-3 levels and an inner shadow `inner` pixels deep from the rim (d_fill = distance from the rim's inner edge)."""
    ys = (np.arange(h, dtype=np.float32) + 0.5 - top) / span
    t = np.clip(ys, 0, 1)[:, None] * np.ones((1, w), dtype=np.float32)
    colour = ak.ramp(t, [(0.0, col("ironTop")), (1.0, col("ironBottom"))])
    colour = colour + brushed_noise(h, w, seed)[..., None] * (3.0 / 255.0)
    shadow = 0.55 * np.exp(-np.maximum(d_fill, 0.0) / (inner / 2.6))
    return np.clip(colour * (1.0 - shadow[..., None]), 0, 1)


def bronze_rim(d, lo, hi, light=None):
    """Bronze bevel colour for the rim band lo <= d < hi (d = distance inside the shape): a rounded moulding that
    rises steeply from the outer edge and falls gently to the inner lip, lit from the top left, so the top and
    left rims catch the light (F3DDA4) and the bottom and right ones fall into shade (7A5A2C)."""
    t = np.clip((d - lo) / max(1e-6, hi - lo), 0.0, 1.0)
    hgt = np.sin(np.minimum(t / 0.45, 1.0) * math.pi / 2) * (1.0 - 0.35 * np.clip((t - 0.45) / 0.55, 0, 1))
    hgt = hgt * (hi - lo) * 1.1
    dif, spec = ak.shade(hgt, light, spec_power=14.0)
    v = 0.52 + (dif - 1.0) * 0.62 + spec * 0.3
    return ak.ramp(v, bronze_ramp())


def plate_piece(w, h, inset, rim, chamfer, k=SS, seed=1, caps=False, shadow_sigma=4.0, shadow_dy=2.0,
                shadow_alpha=0.6, inner=10.0):
    """A 9-slice plate: dark iron fill with a bevelled bronze rim (1 px dark line, rim-2 px of bevel, 1 px inner
    highlight FFF1C8 at 40 %), an inner shadow, an outer drop shadow, optional riveted corner caps. Sizes are
    final pixels; drawn at k times and reduced."""
    W, H = w * k, h * k
    pts = chamfer_rect(inset * k, inset * k, W - inset * k, H - inset * k, chamfer * k)
    d = convex_distance(W, H, pts) / k  # in final pixels
    shape = ak.smoothstep(-0.5, 0.5, d)
    rgba = np.zeros((H, W, 4), dtype=np.float32)
    sh = np.zeros_like(shape)
    dy = int(round(shadow_dy * k))
    sh[dy:] = shape[:-dy] if dy > 0 else shape
    rgba = ak.over(rgba, ak.layer((0, 0, 0), ak.gblur(sh, shadow_sigma * k) * shadow_alpha))
    rgba = ak.over(rgba, ak.layer(col("rimDark"), shape))
    bev_lo, bev_hi = 1.0, float(rim - 1)
    rim_rgb = bronze_rim(d * k, bev_lo * k, bev_hi * k)
    rgba = ak.over(rgba, ak.layer(rim_rgb, ak.smoothstep(bev_lo - 0.5, bev_lo + 0.5, d) * shape))
    hl = ak.smoothstep(bev_hi - 0.5, bev_hi + 0.5, d) * (1.0 - ak.smoothstep(rim - 0.5, rim + 0.5, d))
    rgba = ak.over(rgba, ak.layer(col("rimLight"), hl * 0.4))
    fill_a = ak.smoothstep(rim - 0.5, rim + 0.5, d)
    span = H - 2 * inset * k
    fill = iron_fill(H, W, (d - rim) * k, inset * k, span, seed, inner * k)
    rgba = ak.over(rgba, ak.layer(fill, fill_a))
    if caps:
        rgba = corner_caps(rgba, w, h, inset, chamfer, k)
    return ak.reduce(rgba, k)


def corner_caps(rgba, w, h, inset, chamfer, k):
    """Four riveted bronze corner caps (spec 1.6: 28-px chamfered caps with a 6-px rivet), each a chamfered square
    over the rim's corner with an engraved inner square and a domed rivet, inside its 32-px 9-slice corner."""
    size, cham, r_rivet = 24.0, 7.0, 3.2
    for flip_x in (False, True):
        for flip_y in (False, True):
            sk = Sketch(w, h, k)

            def P(x, y):
                return (((w - x) if flip_x else x) / w, ((h - y) if flip_y else y) / h)

            a0 = inset - 4.0
            a1 = a0 + size
            pts = [P(a0 + cham, a0), P(a1 - cham, a0), P(a1, a0 + cham), P(a1, a1 - cham), P(a1 - cham, a1),
                   P(a0 + cham, a1), P(a0, a1 - cham), P(a0, a0 + cham)]
            sk.poly(pts, "bronze", bevel=3.0)
            m = 5.0
            inner = [P(a0 + m + 3, a0 + m), P(a1 - m - 3, a0 + m), P(a1 - m, a0 + m + 3), P(a1 - m, a1 - m - 3),
                     P(a1 - m - 3, a1 - m), P(a0 + m + 3, a1 - m), P(a0 + m, a1 - m - 3), P(a0 + m, a0 + m + 3)]
            sk.poly(inner, "iron", bevel=1.4, height=-0.6)
            cx, cy = P((a0 + a1) / 2.0, (a0 + a1) / 2.0)
            sk.ellipse(cx, cy, r_rivet / w, r_rivet / h, "gold", bevel=r_rivet, height=1.4)
            rgba = ak.over(rgba, sk_render_noreduce(sk, outline=1.0, bevel=3.0))
    return rgba


def sk_render_noreduce(sk, **kw):
    """Sketch.render without the final reduction (for compositing into a supersampled picture)."""
    k = sk.k
    out = sk.render(**kw)
    return np.repeat(np.repeat(out, k, axis=0), k, axis=1)


def build_plate():
    return plate_piece(256, 256, inset=8, rim=6, chamfer=7, seed=11, caps=True)


def build_plate_tab():
    return plate_piece(128, 64, inset=3, rim=4, chamfer=4, seed=12, shadow_sigma=1.6, shadow_dy=1.0,
                       shadow_alpha=0.55, inner=5.0)


def build_button():
    """The gold button face (128x64, 16-px margins): a bevelled bronze plate, lighter at the top, with a dark
    outline and a pale lip; dark text sits on it. Iron buttons use PlateTab."""
    w, h, inset, k = 128, 64, 4, SS
    W, H = w * k, h * k
    pts = chamfer_rect(inset * k, inset * k, W - inset * k, H - inset * k, 6 * k)
    d = convex_distance(W, H, pts) / k
    shape = ak.smoothstep(-0.5, 0.5, d)
    rgba = np.zeros((H, W, 4), dtype=np.float32)
    sh = np.zeros_like(shape)
    sh[k * 2:] = shape[:-k * 2]
    rgba = ak.over(rgba, ak.layer((0, 0, 0), ak.gblur(sh, 2.0 * k) * 0.6))
    rgba = ak.over(rgba, ak.layer(col("rimDark"), shape))
    ys = (np.arange(H, dtype=np.float32) + 0.5 - inset * k) / (H - 2 * inset * k)
    t = np.clip(ys, 0, 1)[:, None] * np.ones((1, W), dtype=np.float32)
    face = ak.ramp(t, [(0.0, col("bronzeHi")), (0.45, col("bronze")), (1.0, col("bronzeLo"))])
    rise = np.clip((d - 1.0) / 3.0, 0, 1)
    dif, spec = ak.shade((1.0 - (1.0 - rise) ** 2) * 3.0 * k, spec_power=16.0)
    face = ak.lit(face, 0.55 + 0.45 * dif, spec, lift=0.5, gloss=0.25)
    face = face + brushed_noise(H, W, 13)[..., None] * (2.5 / 255.0)
    rgba = ak.over(rgba, ak.layer(np.clip(face, 0, 1), ak.smoothstep(0.5, 1.5, d)))
    lip = ak.smoothstep(1.0, 1.6, d) * (1.0 - ak.smoothstep(2.0, 2.6, d))
    rgba = ak.over(rgba, ak.layer(col("rimLight"), lip * 0.45 * np.clip(1.4 - t * 1.8, 0, 1)))
    return ak.reduce(rgba, k)


def build_button_glow():
    """White inner glow of the button shape (128x64), for hover and press (ADD)."""
    w, h, inset, k = 128, 64, 4, 2
    W, H = w * k, h * k
    d = convex_distance(W, H, chamfer_rect(inset * k, inset * k, W - inset * k, H - inset * k, 6 * k)) / k
    inner = np.exp(-np.maximum(d, 0) / 5.0) * 0.85 + 0.18
    a = inner * ak.smoothstep(-0.5, 0.8, d)
    a += np.exp(-np.maximum(-d, 0) / 2.0) * 0.35 * (d < 0)  # a little bloom outside the edge
    return ak.reduce(ak.layer((255, 255, 255), np.clip(a, 0, 1)), k)


def build_banner():
    """The ribbon plaque (1024x128): an iron band with double bronze hairlines, both ends fading to clear over
    160 px, a bronze diamond on the top hairline at the centre, a soft shadow. The band is 88 px (66 of the banner's
    96 units, 15..81 from its top), not the spec's 72: the title (cap 26 centred at 34 units) and the line under it
    (13 units at 64) need that much room inside the hairlines."""
    w, h, k = 1024, 128, 2
    W, H = w * k, h * k
    top, bot = 20, 108
    ys = (np.arange(H, dtype=np.float32) + 0.5) / k
    xs = (np.arange(W, dtype=np.float32) + 0.5) / k
    fade = np.clip(np.minimum(xs, w - xs) / 160.0, 0, 1)
    fade = fade * fade * (3 - 2 * fade)
    band = (ak.smoothstep(top - 0.5, top + 0.5, ys) * (1 - ak.smoothstep(bot - 0.5, bot + 0.5, ys)))[:, None]
    band = band * fade[None, :]
    rgba = np.zeros((H, W, 4), dtype=np.float32)
    sh = np.zeros_like(band)
    sh[3 * k:] = band[:-3 * k]
    rgba = ak.over(rgba, ak.layer((0, 0, 0), ak.gblur(sh, 5 * k) * 0.65))
    d_fill = np.minimum(ys - top, bot - ys)[:, None] * np.ones((1, W), dtype=np.float32) * k
    fill = iron_fill(H, W, d_fill - 3 * k, top * k, (bot - top) * k, 21, 8 * k)
    rgba = ak.over(rgba, ak.layer(fill, band))
    for y0, y1, alpha in ((top, top + 2, 1.0), (top + 4, top + 5, 0.55), (bot - 5, bot - 4, 0.55), (bot - 2, bot, 1.0)):
        line = (ak.smoothstep(y0 - 0.5, y0 + 0.5, ys) * (1 - ak.smoothstep(y1 - 0.5, y1 + 0.5, ys)))[:, None]
        t = np.clip((ys - y0) / max(1, y1 - y0), 0, 1)[:, None] * np.ones((1, W), dtype=np.float32)
        rgb_ = ak.ramp(1.0 - t * 0.6, bronze_ramp())
        rgba = ak.over(rgba, ak.layer(rgb_, line * fade[None, :] * alpha))
    # the diamond on the top hairline
    sk = Sketch(48, 40, k * 2)
    sk.poly([(0.5, 0.06), (0.9, 0.5), (0.5, 0.94), (0.1, 0.5)], "bronze", bevel=3.0)
    sk.poly([(0.5, 0.30), (0.68, 0.5), (0.5, 0.70), (0.32, 0.5)], "gold", bevel=1.6, height=1.2)
    dia = sk.render(outline=1.2, bevel=3.0)
    dia = np.repeat(np.repeat(dia, k, axis=0), k, axis=1)
    x0, y0 = (w // 2 - 24) * k, (top + 1 - 20) * k
    region = rgba[y0:y0 + 40 * k, x0:x0 + 48 * k]
    rgba[y0:y0 + 40 * k, x0:x0 + 48 * k] = ak.over(region, dia)
    return ak.reduce(rgba, k)


def build_shine_strip():
    """A soft diagonal white streak in the middle 192 px of a clear 1024x128 strip (ADD), slid by texcoords."""
    w, h = 1024, 128
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    slant = (ys - h / 2.0) * 0.45
    u = (xs + 0.5 - w / 2.0 + slant) / 34.0
    core = np.exp(-u * u) * 0.9 + np.exp(-((xs + 0.5 - w / 2.0 + slant - 40) / 10.0) ** 2) * 0.35
    a = core * np.clip(1.0 - np.abs(xs + 0.5 - w / 2.0) / 96.0, 0, 1) ** 0.5
    return ak.layer((255, 255, 255), np.clip(a, 0, 1))


def build_label_halo():
    """A soft dark pill (64x32, 9-slice): black at 50 % with a 6-px soft edge."""
    w, h, k = 64, 32, 4
    W, H = w * k, h * k
    ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)
    xs = (xs + 0.5) / k
    ys = (ys + 0.5) / k
    r = 10.0
    cx = np.clip(xs, 6 + r, w - 6 - r)
    dist = np.hypot(xs - cx, ys - h / 2.0) - r
    a = 0.5 * (1.0 - ak.smoothstep(-3.0, 3.0, dist))
    return ak.reduce(ak.layer((0, 0, 0), a), k)


def build_feed_strip():
    """Kill-feed backing (256x32): iron dark at the right fading to clear at the left, a bronze hairline at the
    right edge and faint hairlines along the top and bottom that fade with it."""
    w, h, k = 256, 32, 2
    W, H = w * k, h * k
    xs = (np.arange(W, dtype=np.float32) + 0.5) / k
    ys = (np.arange(H, dtype=np.float32) + 0.5) / k
    t = np.clip(xs / (w - 40.0), 0, 1)
    fa = (t * t * (3 - 2 * t)) * 0.82
    a = np.ones((H, 1), dtype=np.float32) * fa[None, :]
    fill = iron_fill(H, W, np.full((H, W), 99.0, dtype=np.float32), 0, H, 31)
    rgba = ak.layer(fill, a)
    edge = (ak.smoothstep(w - 4.5, w - 3.5, xs) * (1 - ak.smoothstep(w - 1.5, w - 0.5, xs)))[None, :]
    edge = edge * np.ones((H, 1), dtype=np.float32)
    rgba = ak.over(rgba, ak.layer(col("bronze"), edge))
    for y0 in (0.0, h - 1.0):
        line = (ak.smoothstep(y0 - 0.5, y0, ys) * (1 - ak.smoothstep(y0 + 1.0, y0 + 1.5, ys)))[:, None]
        rgba = ak.over(rgba, ak.layer(col("bronzeLo"), line * fa[None, :] * 0.8))
    return ak.reduce(rgba, k)


# ============================================================================================ the countdown ring

RING_DISC = 0.35      # the dark centre disc's radius, as a fraction of the ring's size (70 % of the radius)
RING_BAND_IN = 0.365  # the band's inner edge (after the lip down into the disc)
RING_BAND_OUT = 0.468
RING_OUT = 0.496
RING_SOCKETS = 15
RING_SOCKET_R = (RING_BAND_IN + RING_BAND_OUT) / 2.0


def socket_angles():
    """The sockets' angles (radians, maths convention: 0 = right, pi/2 = up): the first at the top, then clockwise
    every 24 degrees."""
    return [math.pi / 2.0 - i * (2.0 * math.pi / RING_SOCKETS) for i in range(RING_SOCKETS)]


def build_count_ring(size, detail=True):
    """The countdown's engraved bronze ring: a raised outer rim, a bronze band with 15 empty radial sockets (at the
    angles of socket_angles(), written to RoyaleArtData.lua), studs between them, a lip down into a dark iron
    centre disc of 70 % of the radius with two faint engraved circles."""
    k = SS if size <= 256 else 2
    S = size * k
    ys, xs = np.mgrid[0:S, 0:S].astype(np.float32)
    cx = cy = S / 2.0
    dx, dy = (xs + 0.5 - cx), (ys + 0.5 - cy)
    r = np.hypot(dx, dy) / S  # fraction of the size
    ang = np.arctan2(-dy, dx)  # maths angle, y up
    px = 1.0 / size  # one final pixel as a fraction of the size
    # height field: rim (high), band (mid), sockets (recessed), lip down into the disc (low)
    hgt = np.zeros((S, S), dtype=np.float32)
    rim_t = np.clip((r - RING_BAND_OUT) / (RING_OUT - RING_BAND_OUT), 0, 1)
    rim_profile = np.maximum(np.sin(rim_t * math.pi), 0.0) ** 0.6
    band = (r >= RING_BAND_IN) & (r < RING_BAND_OUT)
    hgt += np.where(band, 0.55, 0.0)
    hgt += np.where((r >= RING_BAND_OUT) & (r < RING_OUT), 0.55 + 0.6 * rim_profile, 0.0)
    lip_t = np.clip((r - RING_DISC) / (RING_BAND_IN - RING_DISC), 0, 1)
    hgt += np.where((r >= RING_DISC) & (r < RING_BAND_IN), 0.55 * lip_t ** 0.7, 0.0)
    socket = np.zeros((S, S), dtype=np.float32)
    stud = np.zeros((S, S), dtype=np.float32)
    half_len = 0.046 if detail else 0.05
    half_w = 0.0165 if detail else 0.022
    for a in socket_angles():
        ux, uy = math.cos(a), -math.sin(a)  # radial unit vector in image coordinates
        sx, sy = cx + ux * RING_SOCKET_R * S, cy + uy * RING_SOCKET_R * S
        along = ((xs + 0.5 - sx) * ux + (ys + 0.5 - sy) * uy) / S
        across = ((xs + 0.5 - sx) * -uy + (ys + 0.5 - sy) * ux) / S
        # a stadium: distance to the segment along the radius
        seg = np.clip(along, -(half_len - half_w), half_len - half_w)
        dist = np.hypot(along - seg, across) - half_w
        socket = np.maximum(socket, 1.0 - ak.smoothstep(-0.6 * px, 0.6 * px, dist))
        if detail:
            b = a - math.pi / RING_SOCKETS
            bx, by = cx + math.cos(b) * RING_SOCKET_R * S, cy - math.sin(b) * RING_SOCKET_R * S
            sd = np.hypot(xs + 0.5 - bx, ys + 0.5 - by) / S
            stud = np.maximum(stud, np.clip(1.0 - sd / 0.0085, 0, 1))
    soft = ak.gblur(socket, 1.2 * k)
    hgt = hgt - 0.5 * soft * band + 0.25 * np.sqrt(stud)
    if detail:  # two engraved grooves along the band's edges
        for rr in (RING_BAND_IN + 0.012, RING_BAND_OUT - 0.010):
            hgt -= 0.22 * np.exp(-((r - rr) / (0.9 * px)) ** 2)
    hgt_px = hgt * 9.0 * k * (size / 512.0) ** 0.5
    dif, spec = ak.shade(ak.gblur(hgt_px, 0.7 * k), spec_power=20.0)
    # colours
    grain = brushed_noise(S, S, 41, sx=3.0, sy=3.0)
    # a turned-metal sheen: broad highlights on the top-left and bottom-right of the band, like a lathe-turned dial
    # under one light, and the whole ring a little brighter towards the light
    sheen = 0.5 + 0.5 * np.cos(2.0 * (ang - 3.0 * math.pi / 4.0))
    toward = -(dx + dy) / (S * 0.7)
    v = 0.43 + (dif - 1.0) * 0.6 + spec * 0.35 + grain * 0.02 + 0.2 * (sheen - 0.5) + 0.08 * toward
    metal = ak.ramp(v, bronze_ramp())
    deep = ak.ramp(0.18 + (dif - 1.0) * 0.4,
                   [(0.0, ak.rgb("070504")), (0.5, col("bronzeDeep")), (1.0, col("bronzeLo"))])
    metal = metal * (1 - socket[..., None]) + deep * socket[..., None]
    # the centre disc: dark iron, lighter towards the top left, an inner shadow under the lip, engraved circles
    t = np.clip(0.5 + (dx + dy) / (S * RING_DISC * 2.8), 0, 1)
    disc_rgb = ak.ramp(t, [(0.0, ak.rgb("23272e")), (0.5, col("ironTop")), (1.0, ak.rgb("0c0d10"))])
    disc_rgb = disc_rgb + grain[..., None] * (2.0 / 255.0)
    under = np.exp(-np.maximum(RING_DISC - r, 0) / (0.03 if detail else 0.05)) * 0.6
    disc_rgb = disc_rgb * (1 - under[..., None])
    if detail:
        for rr in (0.30, 0.18):
            g = np.exp(-((r - rr) / (0.8 * px)) ** 2)
            g2 = np.exp(-((r - rr - 1.1 * px) / (0.8 * px)) ** 2)
            disc_rgb = disc_rgb * (1 - 0.35 * g[..., None]) + 0.05 * g2[..., None]
    in_disc = 1.0 - ak.smoothstep(RING_DISC - 0.5 * px, RING_DISC + 0.5 * px, r)
    rgb_ = metal * (1 - in_disc[..., None]) + np.clip(disc_rgb, 0, 1) * in_disc[..., None]
    # thin dark lines: the outer edge, the band's outer edge, the lip's foot
    for rr, wd, a_ in ((RING_OUT - 0.6 * px, 0.9, 1.0), (RING_BAND_OUT, 0.7, 0.55), (RING_DISC, 0.8, 0.8)):
        g = np.exp(-((r - rr) / (wd * px)) ** 2)
        rgb_ = rgb_ * (1 - a_ * g[..., None]) + np.array([0.04, 0.03, 0.02]) * (a_ * g[..., None])
    alpha = 1.0 - ak.smoothstep(RING_OUT - 0.5 * px, RING_OUT + 0.5 * px, r)
    rgba = np.concatenate([np.clip(rgb_, 0, 1), alpha[..., None]], axis=-1).astype(np.float32)
    return ak.reduce(rgba, k)


def build_notch():
    """One engraved tick (64x64, white, tinted lit / off / ember), pointing up; rotated by the addon, so it is lit
    from the front: a faceted lozenge with a bright ridge and darker edges, inside the inscribed 70 %, with a 2-px
    clear border."""
    sk = Sketch(64, 64)
    sk.poly([(0.5, 0.17), (0.635, 0.5), (0.5, 0.83), (0.365, 0.5)], "white", bevel=4.0)
    return sk.render(outline=1.6, bevel=4.0, front=True, shadow=False)


def build_shock(size):
    """A soft expanding ring (white): a sharp outer front at 44 % of the size, a long soft trail inwards, dusty."""
    k = 2
    S = size * k
    ys, xs = np.mgrid[0:S, 0:S].astype(np.float32)
    r = np.hypot(xs + 0.5 - S / 2.0, ys + 0.5 - S / 2.0) / S
    ang = np.arctan2(ys + 0.5 - S / 2.0, xs + 0.5 - S / 2.0)
    r0 = 0.44
    out = np.exp(-((r - r0) / 0.016) ** 2)
    inn = np.exp(-((r0 - r) / 0.11) ** 2) * 0.55
    a = np.where(r > r0, out, np.maximum(out, inn))
    rng = np.random.default_rng(51)
    ph = rng.uniform(0, 2 * math.pi, 6)
    dust = 1.0 + 0.18 * sum(np.sin(ang * (m + 3) + ph[m]) / (m + 1) for m in range(6))
    a = a * dust
    a = a * (1.0 - ak.smoothstep(0.47, 0.495, r))
    return ak.reduce(ak.layer((255, 255, 255), np.clip(a, 0, 1)), k)


def build_gem():
    """Stage pip (64x32): a bronze socket (left 32x32) and a faceted white gem (right 32x32) that the addon tints."""
    sk = Sketch(32, 32)
    sk.ring(0.5, 0.5, 0.44, 0.29, "bronze", bevel=2.2)
    sk.ellipse(0.5, 0.5, 0.29, 0.29, "void", bevel=2.5)
    sock = sk.render(outline=1.0, bevel=2.0)
    gem = gem_facets(32)
    out = np.zeros((32, 64, 4), dtype=np.float32)
    out[:, :32] = sock
    out[:, 32:] = gem
    return out


def gem_facets(size):
    """A brilliant-cut gem seen from above in greys (white table, lit facets top left), 1-px dark outline."""
    k = SS
    S = size * k
    ys, xs = np.mgrid[0:S, 0:S].astype(np.float32)
    dx, dy = (xs + 0.5) / S - 0.5, (ys + 0.5) / S - 0.5
    r = np.hypot(dx, dy)
    ang = np.arctan2(dy, dx)
    R = 0.27
    # an octagon outline
    oct_r = R * math.cos(math.pi / 8) / np.cos(((ang + math.pi / 8) % (math.pi / 4)) - math.pi / 8)
    inside = r <= oct_r
    table = r <= oct_r * 0.5
    sector = np.floor((ang + math.pi) / (math.pi / 4)).astype(int) % 8
    light = np.array([0.55, 0.85, 0.95, 0.7, 0.45, 0.3, 0.25, 0.4])  # facets facing the top left are bright
    val = light[sector]
    val = np.where(table, 0.92, val * (0.75 + 0.5 * (r / R)))
    # a sparkle
    sp = np.exp(-(((dx + 0.07) / 0.03) ** 2 + ((dy + 0.08) / 0.03) ** 2))
    val = np.clip(val + sp * 0.6, 0, 1)
    g = val[..., None] * np.ones(3)
    edge = (r > oct_r - 1.2 / size) & inside
    a = inside.astype(np.float32)
    d_out = ak.edt(~inside, 2 * k)
    outline = 1.0 - ak.smoothstep(0.5 * k, 1.5 * k, d_out)
    rgba = ak.layer(INK, outline)
    rgba = ak.over(rgba, ak.layer(g * (1 - 0.3 * edge[..., None]), a))
    return ak.reduce(rgba, k)


def build_gem_glow():
    s = 32
    ys, xs = np.mgrid[0:s, 0:s].astype(np.float32)
    r = np.hypot(xs + 0.5 - s / 2, ys + 0.5 - s / 2) / (s / 2)
    a = np.exp(-(r / 0.55) ** 2) * (1 - ak.smoothstep(0.85, 1.0, r))
    return ak.layer((255, 255, 255), a)


# ============================================================================================ rotatable markers

def build_you():
    """The player's gold chevron (64x64), pointing up, rotated by the addon (so lit from the front): inside the
    inscribed 70 % with a 2-px clear border."""
    sk = Sketch(64, 64)
    sk.poly([(0.5, 0.165), (0.75, 0.78), (0.5, 0.64), (0.25, 0.78)], "gold", bevel=4.0)
    sk.poly([(0.5, 0.27), (0.6, 0.58), (0.5, 0.52), (0.4, 0.58)], "gold", bevel=2.0, height=1.4)
    return sk.render(outline=2.2, bevel=4.0, front=True, shadow=False)


def build_arrow():
    """The safe-zone arrow (64x64), white for tinting, bevelled, pointing up; rotated by the addon."""
    sk = Sketch(64, 64)
    sk.poly([(0.5, 0.165), (0.74, 0.72), (0.56, 0.64), (0.56, 0.82), (0.44, 0.82), (0.44, 0.64), (0.26, 0.72)],
            "white", bevel=3.5)
    return sk.render(outline=2.2, bevel=3.5, front=True, shadow=False)


def build_edge_tick():
    """The direction tick of an icon pinned to the minimap's edge (32x32), pointing up, white, rotated."""
    sk = Sketch(32, 32)
    sk.poly([(0.5, 0.2), (0.76, 0.66), (0.24, 0.66)], "white", bevel=2.0)
    return sk.render(outline=1.4, bevel=2.0, front=True, shadow=False)


def build_pin():
    """The landing pin (64x64): a banner flag on a pole whose tip is the bottom centre; white metal for tinting."""
    sk = Sketch(64, 64)
    sk.line([(0.5, 0.955), (0.5, 0.12)], 4.0, "silver", bevel=1.6)
    sk.poly([(0.52, 0.13), (0.86, 0.17), (0.76, 0.31), (0.88, 0.45), (0.52, 0.43)], "white", bevel=2.6)
    sk.ellipse(0.5, 0.11, 0.055, 0.055, "silver", bevel=1.8, height=1.3)
    return sk.render(outline=2.0, bevel=2.4)


# ============================================================================================ icons

ICON_NAMES = [
    ["alive", "kills", "storm", "timer", "pin", "pack", "canopy", "altitude"],
    ["crown", "beast", "claw", "supply", "hoard", "orbSpeed", "orbRestore", "orbBerserk"],
    ["eye", "lobby", "crossing", "landmark", "swords", "fall", "door", "afk"],
    ["warning", "shards", "honor", "map", "pinHollow", "nextCircle", "stormArea", "north"],
    ["close"],
]


def mirror(pts):
    return [(1.0 - x, y) for x, y in pts]


def spiral_arm(cx, cy, a0, turns, r0, r1, w0, w1, n=64):
    """A tapered spiral arm as a polygon: radius r0 -> r1 over `turns`, width w0 -> w1 (fractions)."""
    outer, inner = [], []
    for i in range(n + 1):
        t = i / float(n)
        a = a0 + t * turns * 2 * math.pi
        r = r0 + (r1 - r0) * t
        w = w0 + (w1 - w0) * t
        outer.append((cx + math.cos(a) * (r + w / 2), cy + math.sin(a) * (r + w / 2)))
        inner.append((cx + math.cos(a) * max(0.0, r - w / 2), cy + math.sin(a) * max(0.0, r - w / 2)))
    return outer + inner[::-1]


def tapered(path, w0, w1):
    """A polygon around a polyline whose width goes from w0 to w1 (fractions), pointed when w1 is 0."""
    left, right = [], []
    n = len(path)
    for i, (x, y) in enumerate(path):
        x0, y0 = path[max(0, i - 1)]
        x1, y1 = path[min(n - 1, i + 1)]
        tx, ty = x1 - x0, y1 - y0
        ln = math.hypot(tx, ty) or 1.0
        nx, ny = -ty / ln, tx / ln
        w = (w0 + (w1 - w0) * i / float(n - 1)) / 2.0
        left.append((x + nx * w, y + ny * w))
        right.append((x - nx * w, y - ny * w))
    return left + right[::-1]


def sword(sk, deg, small):
    """A sword pointing up, turned `deg` degrees about the picture's centre."""
    R = lambda pts: rot(pts, 0.5, 0.5, deg)
    sk.poly(R([(0.5, 0.0), (0.552, 0.09), (0.552, 0.64), (0.448, 0.64), (0.448, 0.09)]), "steel", bevel=1.4)
    if not small:
        sk.line(R([(0.5, 0.1), (0.5, 0.6)]), 0.9, "ink", cap=False)
    sk.poly(R([(0.33, 0.63), (0.67, 0.63), (0.67, 0.7), (0.33, 0.7)]), "gold", bevel=1.0)
    sk.poly(R([(0.475, 0.7), (0.525, 0.7), (0.525, 0.86), (0.475, 0.86)]), "wood", bevel=0.8)
    cx, cy = R([(0.5, 0.9)])[0]
    sk.ellipse(cx, cy, 0.05, 0.05, "gold", bevel=1.0)


def draw_icon(sk, name, small):
    """One icon, filled and bevelled, in its own colours (spec 1.6 list); `small` drops the fine details of the
    32-px cells."""
    if name == "alive":  # a great helm
        dome = arc_pts(0.5, 0.5, 0.31, 0.38, 180, 360, 40)
        sk.poly(dome + [(0.81, 0.64), (0.75, 0.88), (0.5, 0.93), (0.25, 0.88), (0.19, 0.64)], "steel", bevel=2.6)
        sk.poly([(0.455, 0.13), (0.545, 0.13), (0.55, 0.45), (0.45, 0.45)], "gold", bevel=1.2)
        sk.poly([(0.26, 0.46), (0.74, 0.46), (0.74, 0.535), (0.535, 0.535), (0.535, 0.8), (0.465, 0.8),
                 (0.465, 0.535), (0.26, 0.535)], "void", bevel=1.0)
        if not small:
            for x in (0.31, 0.69):
                sk.ellipse(x, 0.68, 0.028, 0.028, "gold", bevel=0.8)
    elif name in ("kills", "beast"):
        if name == "beast":  # curved horns first, under the skull
            horn = bez((0.32, 0.38), (0.14, 0.34), (0.06, 0.2), (0.12, 0.05), 16)
            sk.poly(tapered([(0.34, 0.40)] + horn, 0.16, 0.0), "bone", bevel=1.6)
            sk.poly(mirror(tapered([(0.34, 0.40)] + horn, 0.16, 0.0)), "bone", bevel=1.6)
        cr = (0.5, 0.44, 0.30, 0.29) if name == "kills" else (0.5, 0.46, 0.27, 0.25)
        sk.ellipse(cr[0], cr[1], cr[2], cr[3], "bone", bevel=2.6)
        sk.poly([(0.31, 0.56), (0.69, 0.56), (0.66, 0.79), (0.6, 0.89), (0.4, 0.89), (0.34, 0.79)], "bone", bevel=2.0)
        eye_mat = "void" if name == "kills" else "glowgreen"
        for x in (0.375, 0.625):
            sk.ellipse(x, 0.52, 0.095, 0.085, eye_mat, bevel=1.6)
        sk.poly([(0.5, 0.61), (0.545, 0.7), (0.455, 0.7)], "void", bevel=0.8)
        if not small:
            for x in (0.43, 0.5, 0.57):
                sk.line([(x, 0.76), (x, 0.86)], 1.4, "ink")
    elif name == "storm":  # a violet swirl
        for i in range(3):
            sk.poly(spiral_arm(0.5, 0.5, i * 2 * math.pi / 3, 0.62, 0.05, 0.40, 0.06, 0.13), "storm", bevel=1.8)
        sk.ellipse(0.5, 0.5, 0.11, 0.11, "storm", bevel=2.0, height=1.4)
    elif name == "timer":  # an hourglass
        sk.poly([(0.33, 0.2), (0.67, 0.2), (0.67, 0.27), (0.545, 0.5), (0.67, 0.73), (0.67, 0.8), (0.33, 0.8),
                 (0.33, 0.73), (0.455, 0.5), (0.33, 0.27)], "glass", bevel=1.6)
        sk.poly([(0.37, 0.78), (0.63, 0.78), (0.6, 0.69), (0.5, 0.6), (0.4, 0.69)], "gold", bevel=1.0)
        sk.poly([(0.41, 0.31), (0.59, 0.31), (0.5, 0.43)], "gold", bevel=0.8)
        for x in (0.29, 0.71):
            sk.line([(x, 0.2), (x, 0.8)], 3.0 if not small else 2.2, "wood", bevel=1.0)
        sk.poly([(0.22, 0.11), (0.78, 0.11), (0.78, 0.2), (0.22, 0.2)], "gold", bevel=1.6)
        sk.poly([(0.22, 0.8), (0.78, 0.8), (0.78, 0.89), (0.22, 0.89)], "gold", bevel=1.6)
    elif name in ("pin", "pinHollow"):  # a banner flag on a pole
        flag = [(0.39, 0.14), (0.84, 0.19), (0.71, 0.33), (0.86, 0.47), (0.39, 0.44)]
        if name == "pin":
            sk.line([(0.36, 0.92), (0.36, 0.12)], 3.6 if not small else 2.6, "gold", bevel=1.2)
            sk.poly(flag, "gold", bevel=2.2)
            if not small:
                sk.line([(0.42, 0.24), (0.66, 0.26)], 1.2, "ink")
        else:
            sk.line([(0.36, 0.92), (0.36, 0.12)], 3.0 if not small else 2.2, "cloth", bevel=1.0)
            sk.line(flag + [flag[0]], 3.0 if not small else 2.2, "cloth", bevel=1.0)
        sk.ellipse(0.36, 0.1, 0.05, 0.05, "gold" if name == "pin" else "cloth", bevel=1.2)
    elif name == "pack":  # a packed parachute
        body = arc_pts(0.5, 0.36, 0.27, 0.18, 180, 360, 20) + [(0.77, 0.8), (0.7, 0.88), (0.3, 0.88), (0.23, 0.8)]
        sk.poly(body, "cloth", bevel=2.4)
        sk.poly([(0.23, 0.42), (0.77, 0.42), (0.77, 0.5), (0.23, 0.5)], "bronze", bevel=1.0)
        for x in (0.36, 0.64):
            sk.poly([(x - 0.04, 0.24), (x + 0.04, 0.24), (x + 0.04, 0.88), (x - 0.04, 0.88)], "wood", bevel=1.0)
            if not small:
                sk.poly([(x - 0.055, 0.6), (x + 0.055, 0.6), (x + 0.055, 0.68), (x - 0.055, 0.68)], "gold",
                        bevel=0.8)
        sk.ring(0.8, 0.62, 0.075, 0.035, "gold", bevel=1.0)
    elif name == "canopy":
        dome = arc_pts(0.5, 0.44, 0.4, 0.32, 180, 360, 40)
        scal = []
        xs = [0.9, 0.7, 0.5, 0.3, 0.1]
        for a, b in zip(xs, xs[1:]):
            scal += arc_pts((a + b) / 2, 0.44, (a - b) / 2, 0.06, 0, 180, 8)
        sk.poly(dome + scal, "cloth", bevel=2.2)
        sk.poly([(0.5, 0.12), (0.62, 0.15), (0.6, 0.47), (0.5, 0.5), (0.4, 0.47), (0.38, 0.15)], "bronze",
                bevel=1.2)
        if not small:
            sk.poly([(0.2, 0.2), (0.27, 0.16), (0.24, 0.44), (0.12, 0.44)], "bronze", bevel=1.0)
            sk.poly(mirror([(0.2, 0.2), (0.27, 0.16), (0.24, 0.44), (0.12, 0.44)]), "bronze", bevel=1.0)
        for x in ((0.12, 0.31, 0.5, 0.69, 0.88) if not small else (0.14, 0.5, 0.86)):
            sk.line([(x, 0.47), (0.5, 0.78)], 1.1 if not small else 0.7, "ink")
        sk.ellipse(0.5, 0.8, 0.045, 0.045, "gold", bevel=1.0)
        sk.poly([(0.46, 0.83), (0.54, 0.83), (0.55, 0.94), (0.45, 0.94)], "gold", bevel=0.8)
    elif name == "altitude":  # a double chevron down
        ch = [(0.2, 0.2), (0.5, 0.44), (0.8, 0.2), (0.8, 0.35), (0.5, 0.59), (0.2, 0.35)]
        sk.poly(ch, "gold", bevel=1.8)
        sk.poly([(x, y + 0.24) for x, y in ch], "gold", bevel=1.8)
    elif name == "crown":
        sk.poly([(0.17, 0.66), (0.17, 0.3), (0.34, 0.5), (0.5, 0.2), (0.66, 0.5), (0.83, 0.3), (0.83, 0.66)], "gold",
                bevel=2.0)
        sk.poly([(0.17, 0.62), (0.83, 0.62), (0.83, 0.8), (0.17, 0.8)], "gold", bevel=1.8)
        for x, y in ((0.17, 0.27), (0.5, 0.17), (0.83, 0.27)):
            sk.ellipse(x, y, 0.05, 0.05, "gold", bevel=1.2)
        sk.ellipse(0.5, 0.71, 0.06, 0.05, "blood", bevel=1.2)
        if not small:
            for x in (0.31, 0.69):
                sk.ellipse(x, 0.71, 0.04, 0.035, "arcane", bevel=1.0)
    elif name == "claw":  # three talon slashes
        for i in range(3):
            x = 0.24 + i * 0.2
            path = bez((x, 0.88), (x + 0.02, 0.6), (x + 0.1, 0.32), (x + 0.2, 0.1), 16)
            sk.poly(tapered([(x - 0.01, 0.9)] + path, 0.13, 0.0), "bone", bevel=1.5)
    elif name == "supply":  # a crate under a small chute
        sk.poly(arc_pts(0.5, 0.36, 0.36, 0.25, 180, 360, 30), "cloth", bevel=1.8)
        sk.poly([(0.5, 0.11), (0.6, 0.13), (0.58, 0.36), (0.42, 0.36), (0.4, 0.13)], "bronze", bevel=1.0)
        for x0 in (0.16, 0.84):
            sk.line([(x0, 0.37), (0.5 + (x0 - 0.5) * 0.45, 0.55)], 1.1, "ink")
        sk.poly([(0.29, 0.53), (0.71, 0.53), (0.71, 0.92), (0.29, 0.92)], "wood", bevel=1.8)
        if not small:
            sk.line([(0.31, 0.56), (0.69, 0.9)], 1.4, "ink")
            sk.line([(0.69, 0.56), (0.31, 0.9)], 1.4, "ink")
        for x, y in ((0.29, 0.53), (0.71, 0.53), (0.29, 0.92), (0.71, 0.92)):
            sk.poly([(x - 0.05, y - 0.05), (x + 0.05, y - 0.05), (x + 0.05, y + 0.05), (x - 0.05, y + 0.05)],
                    "gold", bevel=0.8)
    elif name == "hoard":  # a heaped chest
        sk.ellipse(0.5, 0.5, 0.33, 0.17, "gold", bevel=2.0)
        for x, y in ((0.38, 0.38), (0.55, 0.33), (0.47, 0.27), (0.63, 0.42)):
            sk.ellipse(x, y, 0.07, 0.05, "gold", bevel=1.2)
        sk.poly([(0.16, 0.52), (0.84, 0.52), (0.8, 0.9), (0.2, 0.9)], "wood", bevel=1.8)
        for x in (0.32, 0.68):
            sk.poly([(x - 0.04, 0.52), (x + 0.04, 0.52), (x + 0.035, 0.9), (x - 0.035, 0.9)], "gold", bevel=0.9)
        sk.poly([(0.45, 0.6), (0.55, 0.6), (0.55, 0.72), (0.45, 0.72)], "gold", bevel=0.9)
    elif name == "orbSpeed":  # a wing
        root = (0.2, 0.84)
        for tip, w0, bend in (((0.62, 0.62), 0.16, 0.05), ((0.76, 0.4), 0.17, 0.07), ((0.9, 0.12), 0.18, 0.09)):
            mid = ((root[0] + tip[0]) / 2 - bend, (root[1] + tip[1]) / 2 - bend)
            path = bez(root, mid, (tip[0] - 0.08, tip[1] + 0.02), tip, 14)
            sk.poly(tapered([root] + path, w0, 0.015), "speed", bevel=1.8)
        sk.ellipse(0.3, 0.72, 0.13, 0.11, "speed", bevel=1.8, height=1.2)
    elif name == "orbRestore":  # a drop with a leaf
        drop = [(0.5, 0.1)] + bez((0.5, 0.1), (0.62, 0.3), (0.78, 0.45), (0.78, 0.62), 14)
        drop += arc_pts(0.5, 0.62, 0.28, 0.27, 0, 180, 24)[1:]
        drop += bez((0.22, 0.62), (0.22, 0.45), (0.38, 0.3), (0.5, 0.1), 14)
        sk.poly(drop, "restore", bevel=2.4)
        leaf = bez((0.4, 0.74), (0.38, 0.56), (0.5, 0.46), (0.64, 0.44), 10) + \
            bez((0.64, 0.44), (0.64, 0.6), (0.54, 0.72), (0.4, 0.74), 10)
        sk.poly(leaf, "beast", bevel=1.2)
        if not small:
            sk.line([(0.42, 0.72), (0.6, 0.48)], 1.0, "ink")
    elif name == "orbBerserk":  # a fang
        fang = bez((0.28, 0.16), (0.24, 0.5), (0.38, 0.78), (0.66, 0.93), 18) + \
            bez((0.66, 0.93), (0.56, 0.72), (0.56, 0.42), (0.72, 0.16), 18)
        sk.poly([(0.28, 0.16)] + fang, "berserk", bevel=2.4)
        sk.poly(arc_pts(0.5, 0.17, 0.25, 0.09, 180, 360, 14) + arc_pts(0.5, 0.17, 0.25, 0.05, 0, 180, 14)[1:],
                "blood", bevel=1.2)
    elif name == "eye":  # Shadow Sight
        eye = [(0.1, 0.5)] + bez((0.1, 0.5), (0.32, 0.17), (0.68, 0.17), (0.9, 0.5), 16) + \
            bez((0.9, 0.5), (0.68, 0.83), (0.32, 0.83), (0.1, 0.5), 16)
        sk.poly(eye, "cloth", bevel=1.6)
        sk.ellipse(0.5, 0.5, 0.18, 0.18, "storm", bevel=1.6)
        sk.ellipse(0.5, 0.5, 0.07, 0.07, "void", bevel=1.0)
        sk.ellipse(0.44, 0.44, 0.035, 0.035, "white", bevel=0.6)
    elif name == "lobby":  # a tower shield
        sh = [(0.22, 0.12), (0.78, 0.12), (0.78, 0.6)]
        sh += bez((0.78, 0.6), (0.76, 0.76), (0.62, 0.86), (0.5, 0.93), 10)
        sh += bez((0.5, 0.93), (0.38, 0.86), (0.24, 0.76), (0.22, 0.6), 10)
        sk.poly(sh, "gold", bevel=1.8)
        inner = [(0.5 + (x - 0.5) * 0.8, 0.12 + (y - 0.12) * 0.86 + 0.06) for x, y in sh]
        sk.poly(inner, "steel", bevel=1.8)
        sk.poly([(0.47, 0.2), (0.53, 0.2), (0.53, 0.82), (0.47, 0.82)], "gold", bevel=1.0)
        sk.ellipse(0.5, 0.45, 0.08, 0.08, "gold", bevel=1.4, height=1.3)
    elif name == "crossing":  # an arched stone bridge
        sk.poly([(0.08, 0.4), (0.92, 0.4), (0.92, 0.5), (0.08, 0.5)], "stone", bevel=1.4)
        sk.poly([(0.13, 0.5), (0.87, 0.5), (0.87, 0.8), (0.13, 0.8)], "stone", bevel=1.6)
        sk.ellipse(0.5, 0.82, 0.25, 0.22, "void", cut=True)
        for x in (0.14, 0.32, 0.5, 0.68, 0.86):
            sk.poly([(x - 0.03, 0.3), (x + 0.03, 0.3), (x + 0.03, 0.4), (x - 0.03, 0.4)], "stone", bevel=0.8)
        if not small:
            sk.line([(0.1, 0.3), (0.9, 0.3)], 1.6, "wood")
        sk.line([(0.06, 0.9), (0.2, 0.86), (0.34, 0.9), (0.5, 0.86), (0.66, 0.9), (0.8, 0.86), (0.94, 0.9)],
                2.0 if not small else 1.6, "speed", bevel=0.8)
    elif name == "landmark":  # a watchtower
        sk.poly([(0.36, 0.3), (0.64, 0.3), (0.7, 0.9), (0.3, 0.9)], "stone", bevel=1.8)
        sk.poly([(0.28, 0.17), (0.72, 0.17), (0.72, 0.31), (0.28, 0.31)], "stone", bevel=1.4)
        for x in (0.37, 0.5, 0.63):
            sk.poly([(x - 0.035, 0.16), (x + 0.035, 0.16), (x + 0.035, 0.22), (x - 0.035, 0.22)], "void", cut=True)
        sk.line([(0.5, 0.17), (0.5, 0.04)], 1.6, "wood", cap=False)
        sk.poly([(0.51, 0.04), (0.68, 0.07), (0.51, 0.11)], "blood", bevel=0.8)
        sk.poly(arc_pts(0.5, 0.82, 0.07, 0.09, 180, 360, 10) + [(0.57, 0.9), (0.43, 0.9)], "void", bevel=0.8)
        if not small:
            sk.poly([(0.48, 0.42), (0.52, 0.42), (0.52, 0.54), (0.48, 0.54)], "void", bevel=0.6)
    elif name == "swords":
        sword(sk, -42, small)
        sword(sk, 42, small)
    elif name == "fall":  # a downward arrow into the ground
        sk.poly([(0.44, 0.1), (0.56, 0.1), (0.56, 0.48), (0.7, 0.48), (0.5, 0.72), (0.3, 0.48), (0.44, 0.48)],
                "silver", bevel=1.6)
        sk.poly([(0.12, 0.8), (0.88, 0.8), (0.88, 0.9), (0.12, 0.9)], "stone", bevel=1.2)
        for a, b in (((0.22, 0.72), (0.3, 0.66)), ((0.78, 0.72), (0.7, 0.66))):
            sk.line([a, b], 1.6, "silver")
        if not small:
            sk.line([(0.46, 0.8), (0.42, 0.86), (0.48, 0.9)], 1.2, "ink")
    elif name == "door":  # leaving through a door
        sk.poly(arc_pts(0.6, 0.38, 0.26, 0.26, 180, 360, 20) + [(0.86, 0.9), (0.34, 0.9)], "stone", bevel=1.6)
        sk.poly(arc_pts(0.6, 0.42, 0.17, 0.18, 180, 360, 20) + [(0.77, 0.9), (0.43, 0.9)], "void", bevel=1.2)
        sk.poly([(0.08, 0.6), (0.3, 0.42), (0.3, 0.53), (0.62, 0.53), (0.62, 0.67), (0.3, 0.67), (0.3, 0.78)],
                "gold", bevel=1.4)
    elif name == "afk":  # Zz
        sk.poly([(0.18, 0.44), (0.62, 0.44), (0.62, 0.53), (0.34, 0.8), (0.62, 0.8), (0.62, 0.9), (0.16, 0.9),
                 (0.16, 0.81), (0.44, 0.54), (0.18, 0.54)], "cloth", bevel=1.4)
        sk.poly([(0.6, 0.12), (0.86, 0.12), (0.86, 0.19), (0.7, 0.34), (0.86, 0.34), (0.86, 0.41), (0.58, 0.41),
                 (0.58, 0.34), (0.74, 0.19), (0.6, 0.19)], "cloth", bevel=1.0)
    elif name == "warning":
        sk.poly([(0.5, 0.1), (0.92, 0.86), (0.08, 0.86)], "ember", bevel=2.2)
        sk.poly([(0.455, 0.34), (0.545, 0.34), (0.53, 0.64), (0.47, 0.64)], "void", bevel=0.8)
        sk.ellipse(0.5, 0.74, 0.05, 0.05, "void", bevel=0.8)
    elif name == "shards":  # a crystal cluster
        def crystal(cx, top, bot, w, deg):
            pts = [(cx, top), (cx + w / 2, top + w * 0.7), (cx + w / 2, bot), (cx - w / 2, bot),
                   (cx - w / 2, top + w * 0.7)]
            return rot(pts, cx, bot, deg)
        sk.poly(crystal(0.33, 0.3, 0.88, 0.2, -18), "arcane", bevel=1.6)
        sk.poly(crystal(0.68, 0.34, 0.88, 0.2, 20), "arcane", bevel=1.6)
        sk.poly(crystal(0.5, 0.08, 0.9, 0.24, 0), "arcane", bevel=1.8)
        if not small:
            sk.line([(0.5, 0.1), (0.5, 0.86)], 1.0, "ink")
    elif name == "honor":  # a medal on a ribbon
        sk.poly([(0.28, 0.08), (0.44, 0.08), (0.58, 0.5), (0.44, 0.56)], "blood", bevel=1.2)
        sk.poly([(0.72, 0.08), (0.56, 0.08), (0.42, 0.5), (0.56, 0.56)], "blood", bevel=1.2)
        sk.ellipse(0.5, 0.64, 0.25, 0.25, "gold", bevel=2.2)
        star = []
        for i in range(10):
            a = -math.pi / 2 + i * math.pi / 5
            r = 0.15 if i % 2 == 0 else 0.065
            star.append((0.5 + r * math.cos(a), 0.65 + r * math.sin(a)))
        sk.poly(star, "gold", bevel=1.2, height=1.3)
    elif name == "map":  # a scroll
        sk.poly([(0.22, 0.2), (0.78, 0.2), (0.78, 0.8), (0.22, 0.8)], "cloth", bevel=1.6)
        for y in (0.18, 0.82):
            sk.poly([(0.14, y - 0.06), (0.86, y - 0.06), (0.86, y + 0.06), (0.14, y + 0.06)], "wood", bevel=1.4)
        sk.line([(0.32, 0.66), (0.42, 0.56), (0.5, 0.6), (0.6, 0.44)], 1.4 if not small else 1.1, "ink")
        sk.line([(0.6, 0.34), (0.7, 0.44)], 1.6, "blood")
        sk.line([(0.7, 0.34), (0.6, 0.44)], 1.6, "blood")
    elif name == "nextCircle":  # a white dashed ring
        n = 10 if not small else 7
        gap = 360.0 / n
        for i in range(n):
            a0 = i * gap
            sk.line(arc_pts(0.5, 0.5, 0.34, 0.34, a0 + gap * 0.2, a0 + gap * 0.72, 6), 4.0 if not small else 2.8,
                    "white", bevel=1.2)
    elif name == "stormArea":  # a hatched storm disc
        sk.ellipse(0.5, 0.5, 0.36, 0.36, "storm", bevel=1.6, height=0.6)

        def hatch(d, sk_):
            for i in range(-6, 7):
                o = i * 0.12
                d.line([((0.0 + o) * sk_.W, 1.0 * sk_.H), ((1.0 + o) * sk_.W, 0.0)], fill=255,
                       width=int(sk_.k * (1.6 if not small else 1.2)))
        sk.custom(hatch, "white", clip=(0.5, 0.5, 0.33), bevel=0.5)
        sk.ring(0.5, 0.5, 0.38, 0.32, "storm", bevel=1.0)
    elif name == "north":  # a compass rose with an engraved N
        cy = 0.6
        sk.ring(0.5, cy, 0.25, 0.19, "bronze", bevel=1.2)
        pts = []
        for i in range(8):
            a = -math.pi / 2 + i * math.pi / 4
            r = 0.37 if i % 2 == 0 else 0.2
            pts.append((0.5 + r * math.cos(a), cy + r * math.sin(a)))
            b = a + math.pi / 8
            pts.append((0.5 + 0.1 * math.cos(b), cy + 0.1 * math.sin(b)))
        sk.poly(pts, "gold", bevel=1.8)
        sk.poly([(0.5, cy - 0.37), (0.57, cy - 0.08), (0.5, cy), (0.43, cy - 0.08)], "blood", bevel=1.2)
        sk.ellipse(0.5, cy, 0.05, 0.05, "gold", bevel=0.9, height=1.3)
        sk.text(0.5, 0.1, "N", 0.18 if not small else 0.22, "gold", bevel=0.9)
    elif name == "close":  # an X
        sk.poly(rot([(0.42, 0.14), (0.58, 0.14), (0.58, 0.86), (0.42, 0.86)], 0.5, 0.5, 45), "silver", bevel=1.6)
        sk.poly(rot([(0.42, 0.14), (0.58, 0.14), (0.58, 0.86), (0.42, 0.86)], 0.5, 0.5, -45), "silver", bevel=1.6)
    else:
        raise Fail("no drawing for icon %s" % name)


def build_icons(cell, stub=False):
    """Icons (8x8 cells of 64) or IconsSmall (32-px cells): 2-px or 1.5-px dark outline."""
    cols = 8
    size = cell * cols
    art = np.zeros((size, size, 4), dtype=np.float32)
    small = cell < 64
    cells = {}
    for row, names in enumerate(ICON_NAMES):
        for c, name in enumerate(names):
            sk = Sketch(cell, cell)
            if stub:
                sk.ellipse(0.5, 0.5, 0.36, 0.36, "gold", bevel=0.01)
                piece = sk.render(outline=1.0, bevel=0.01, shadow=False)
            else:
                draw_icon(sk, name, small)
                piece = sk.render(outline=1.5 if small else 2.0, bevel=1.2 if small else 2.0, grad=0.16)
            art[row * cell:(row + 1) * cell, c * cell:(c + 1) * cell] = piece
            cells[name] = (c * cell / size, (c + 1) * cell / size, row * cell / size, (row + 1) * cell / size)
    return art, cells


# ============================================================================================ illustrations

def build_parachute():
    """Two 128x128 pictures: the packed parachute (left) and an open canopy with a small figure under it (right);
    panels in bronze and cream, rigging lines, a dark outline."""
    out = np.zeros((128, 256, 4), dtype=np.float32)
    sk = Sketch(128, 128)
    for x0 in (0.16, 0.84):  # shoulder straps behind the container
        sk.poly([(x0 - 0.05, 0.16), (x0 + 0.05, 0.16), (x0 + 0.06, 0.9), (x0 - 0.04, 0.9)], "wood", bevel=2.0)
    body = [(0.24, 0.2), (0.76, 0.2), (0.82, 0.26), (0.82, 0.84), (0.76, 0.9), (0.24, 0.9), (0.18, 0.84),
            (0.18, 0.26)]
    sk.poly(body, "cloth", bevel=4.0)
    flap = [(0.22, 0.16), (0.78, 0.16), (0.84, 0.22), (0.84, 0.36), (0.5, 0.46), (0.16, 0.36), (0.16, 0.22)]
    sk.poly(flap, "bronze", bevel=3.2)
    sk.line([(0.2, 0.33), (0.5, 0.42), (0.8, 0.33)], 1.0, "ink")
    sk.poly([(0.24, 0.6), (0.76, 0.6), (0.76, 0.68), (0.24, 0.68)], "wood", bevel=1.6)
    for x in (0.34, 0.66):
        sk.poly([(x - 0.06, 0.58), (x + 0.06, 0.58), (x + 0.06, 0.7), (x - 0.06, 0.7)], "gold", bevel=1.6)
        sk.poly([(x - 0.025, 0.61), (x + 0.025, 0.61), (x + 0.025, 0.67), (x - 0.025, 0.67)], "void", bevel=0.6)
    sk.line([(0.3, 0.78), (0.7, 0.78)], 1.0, "ink")
    sk.ring(0.5, 0.8, 0.075, 0.04, "blood", bevel=1.8)
    sk.line([(0.5, 0.72), (0.5, 0.75)], 2.0, "blood")
    out[:, :128] = sk.render(outline=2.4, bevel=3.0)
    sk = Sketch(128, 128)
    dome = arc_pts(0.5, 0.42, 0.44, 0.34, 180, 360, 48)
    xs = [0.94, 0.72, 0.5, 0.28, 0.06]
    scal = []
    for a, b in zip(xs, xs[1:]):
        scal += arc_pts((a + b) / 2, 0.42, (a - b) / 2, 0.055, 0, 180, 10)
    sk.poly(dome + scal, "cloth", bevel=3.6)
    gores = [((0.5, 0.08), (0.62, 0.1), (0.61, 0.46), (0.5, 0.48), (0.39, 0.46), (0.38, 0.1)),
             ((0.17, 0.2), (0.25, 0.14), (0.24, 0.44), (0.1, 0.45)),
             ((0.83, 0.2), (0.75, 0.14), (0.76, 0.44), (0.9, 0.45))]
    for g in gores:
        sk.poly(list(g), "bronze", bevel=2.4)
    for x in (0.06, 0.28, 0.5, 0.72, 0.94):
        sk.line([(x, 0.45), (0.5, 0.74)], 1.2, "ink")
    sk.ellipse(0.5, 0.765, 0.04, 0.04, "bone", bevel=1.2)
    sk.poly([(0.46, 0.8), (0.54, 0.8), (0.56, 0.9), (0.44, 0.9)], "bronze", bevel=1.2)
    sk.line([(0.47, 0.9), (0.45, 0.97)], 2.4, "wood")
    sk.line([(0.53, 0.9), (0.55, 0.97)], 2.4, "wood")
    sk.line([(0.46, 0.81), (0.42, 0.74)], 2.0, "bronze")
    sk.line([(0.54, 0.81), (0.58, 0.74)], 2.0, "bronze")
    out[:, 128:] = sk.render(outline=2.4, bevel=3.0)
    return out


ALT_TOP, ALT_BOTTOM = 24, 472  # the altimeter's scale: drop height at row 24, the ground at row 472 (of 512)


def build_altimeter():
    """The altimeter (64x512): a bronze-framed iron column with a recessed track, ticks every 1/12 of the scale
    (ALT_TOP to ALT_BOTTOM), longer every 3rd, and a ground band under the scale."""
    w, h, k = 64, 512, SS
    sk = Sketch(w, h, k)
    sk.poly([(10 / w, 14 / h), (18 / w, 6 / h), (46 / w, 6 / h), (54 / w, 14 / h), (54 / w, 498 / h), (46 / w, 506 / h),
             (18 / w, 506 / h), (10 / w, 498 / h)], "bronze", bevel=3.4)
    sk.poly([(17 / w, 14 / h), (47 / w, 14 / h), (47 / w, 498 / h), (17 / w, 498 / h)], "iron", bevel=2.0,
            height=-0.8)
    sk.poly([(21 / w, ALT_TOP / h), (31 / w, ALT_TOP / h), (31 / w, ALT_BOTTOM / h), (21 / w, ALT_BOTTOM / h)],
            "void", bevel=2.0)
    for i in range(13):
        y = (ALT_TOP + (ALT_BOTTOM - ALT_TOP) * i / 12.0) / h
        major = i % 3 == 0
        sk.line([(34 / w, y), ((45 if major else 41) / w, y)], 2.4 if major else 1.5, "gold", bevel=0.8, cap=False)
    sk.poly([(17 / w, (ALT_BOTTOM + 2) / h), (47 / w, (ALT_BOTTOM + 2) / h), (47 / w, 498 / h), (17 / w, 498 / h)],
            "restore", bevel=1.6)

    def ground(d, s_):
        for i in range(-4, 12):
            x0 = (17 + i * 6) * s_.k
            d.line([(x0, 498 * s_.k), (x0 + 24 * s_.k, (ALT_BOTTOM + 2) * s_.k)], fill=255, width=s_.k)
        # keep the hatch inside the ground band
        d.rectangle((0, 0, 17 * s_.k - 1, s_.H), fill=0)
        d.rectangle((47 * s_.k, 0, s_.W, s_.H), fill=0)
        d.rectangle((0, 0, s_.W, (ALT_BOTTOM + 2) * s_.k - 1), fill=0)
        d.rectangle((0, 498 * s_.k, s_.W, s_.H), fill=0)
    sk.custom(ground, "ink")
    sk.poly([(32 / w, 1 / h), (38 / w, 7 / h), (32 / w, 13 / h), (26 / w, 7 / h)], "gold", bevel=1.6)
    return sk.render(outline=1.6, bevel=2.0)


def build_alt_marker():
    """The player's mark on the altimeter (64x32): a gold chevron pointing right."""
    sk = Sketch(64, 32)
    sk.poly([(0.18, 0.14), (0.84, 0.5), (0.18, 0.86), (0.34, 0.5)], "gold", bevel=2.6)
    return sk.render(outline=2.0, bevel=2.6)


# ============================================================================================ soft art

def smooth_noise(h, w, sigma, seed):
    """Isotropic smooth noise (blurred white noise, wrapping), about 0..1 with mean 0.5."""
    rng = np.random.default_rng(seed)
    n = ak.gblur(rng.standard_normal((h, w)).astype(np.float32), sigma, wrap=True)
    return np.clip(0.5 + n / (6.0 * max(1e-6, n.std())), 0.0, 1.0)


def fbm(h, w, sigma, octaves, seed):
    """Fractal noise: octaves of smooth_noise, each half the size and half the weight of the last."""
    total, amp, norm = np.zeros((h, w), dtype=np.float32), 1.0, 0.0
    for o in range(octaves):
        total += amp * smooth_noise(h, w, max(0.8, sigma / (2 ** o)), seed + 17 * o)
        norm += amp
        amp *= 0.5
    return total / norm


def build_speed_lines(seed):
    """Radial white streaks (1024x1024), strongest at the edges and gone well before the centre, for the freefall;
    two seeds make the A and B variants that the addon cross-fades."""
    s = 1024
    rng = np.random.default_rng(seed)
    ys, xs = np.mgrid[0:s, 0:s].astype(np.float32)
    dx, dy = (xs + 0.5) / s - 0.5, (ys + 0.5) / s - 0.5
    r = np.hypot(dx, dy) / 0.5  # 1.0 at the middle of each edge
    ang = np.arctan2(dy, dx)
    a = np.zeros((s, s), dtype=np.float32)
    n = 150
    for i in range(n):
        th = rng.uniform(-math.pi, math.pi)
        r0 = rng.uniform(0.62, 0.95)
        width = rng.uniform(0.0016, 0.0045)  # radians-ish at r = 1
        strength = rng.uniform(0.35, 1.0)
        dth = np.angle(np.exp(1j * (ang - th)))
        across = np.abs(dth) * r  # roughly the distance in edge units
        w_here = width * (0.4 + 0.6 * np.clip((r - r0) / 0.4, 0, 1))
        streak = np.exp(-(across / np.maximum(w_here, 1e-4)) ** 2)
        ramp_ = np.clip((r - r0) / 0.35, 0, 1) ** 1.5
        a = np.maximum(a, streak * ramp_ * strength)
    a = a * ak.smoothstep(0.55, 0.9, r)
    return ak.layer((255, 255, 255), np.clip(a, 0, 1))


def build_vignette():
    """The storm edge (512x512, white, tinted storm): a fractal-noise cloud border with a clear centre, densest in
    the corners."""
    s = 512
    ys, xs = np.mgrid[0:s, 0:s].astype(np.float32)
    dx, dy = np.abs((xs + 0.5) / s - 0.5) * 2, np.abs((ys + 0.5) / s - 0.5) * 2
    d = (dx ** 4 + dy ** 4) ** 0.25
    n = fbm(s, s, 40.0, 5, 61)
    edge = 0.74 + (n - 0.5) * 0.30
    a = ak.smoothstep(edge, edge + 0.30, d)
    wisps = fbm(s, s, 14.0, 3, 67)
    a = np.clip(a * (0.7 + 0.6 * wisps), 0, 1) * 0.95
    return ak.layer((255, 255, 255), a)


def build_hatch():
    """Sparse white diagonal lines on clear (32x32, 25 % coverage), tiling seamlessly over the storm shade."""
    k = 8
    S = 32 * k
    ys, xs = np.mgrid[0:S, 0:S].astype(np.float32)
    u = ((xs + ys + 1.0) / k) % 8.0  # 8-px period along the diagonal (in x + y), so 32 tiles exactly
    a = (u < 2.0).astype(np.float32)
    return ak.reduce(ak.layer((255, 255, 255), a), k)


# ============================================================================================ placeholders (--stub)

def stub_piece(name, w, h):
    """A flat placeholder of the right size: a plate-like box, a disc, or a soft white wash."""
    a = np.zeros((h, w, 4), dtype=np.float32)
    if name in ("Plate", "PlateTab", "Button", "Banner", "FeedStrip", "LabelHalo", "Altimeter"):
        inset = max(1, min(w, h) // 16)
        d = convex_distance(w, h, chamfer_rect(inset, inset, w - inset, h - inset, inset))
        rim = ak.smoothstep(-0.5, 0.5, d)
        a = ak.over(a, ak.layer(col("bronze"), rim))
        a = ak.over(a, ak.layer(col("ironBottom"), ak.smoothstep(inset - 0.5, inset + 0.5, d)))
        return a
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    r = np.hypot((xs + 0.5) / w - 0.5, (ys + 0.5) / h - 0.5)
    disc = 1.0 - ak.smoothstep(0.30, 0.32, r)
    return ak.layer((255, 255, 255), disc)


# ============================================================================================ build everything

def white(alpha):
    return ak.layer((255, 255, 255), np.clip(alpha, 0, 1))


def build_all(stub=False, log=print):
    """Draws every texture; returns ([(name, float RGBA, 'tga' or 'dxt5')], data table, extra info)."""
    face = Face(FONT_NUM)
    out = []
    data = {"atlases": {}}

    def piece(name, fn, w, h, fmt="tga"):
        img = stub_piece(name, w, h) if stub else fn()
        check(img.shape[:2] == (h, w), "%s is %dx%d, not %dx%d" % (name, img.shape[1], img.shape[0], w, h))
        out.append((file_name(name), img, fmt))

    for at in NUMERAL_ATLASES:
        log("drawing %s" % at.name)
        art, glow = build_numerals(face, at, stub)
        out.append((at.name, art, "tga"))
        out.append((at.name + "Glow", white(glow), "dxt5"))
        data["atlases"][at.name] = dict(file=GAME_DIR + at.name, w=at.w, h=at.h, cap=at.cap, baseline=at.baseline,
                                        cellW=at.cell_w, cellH=at.cell_h, stroke=at.stroke,
                                        glow=GAME_DIR + at.name + "Glow", glyphs=at.glyphs)
    log("drawing DropWord")
    art, glow, word, baseline = build_dropword(face, stub)
    out.append(("DropWord", art, "tga"))
    out.append(("DropWordGlow", white(glow), "dxt5"))
    data["atlases"]["DropWord"] = dict(file=GAME_DIR + "DropWord", w=1024, h=512, cap=DROP_CAP, baseline=baseline,
                                       cellW=1024, cellH=512, stroke=DROP_STROKE, glow=GAME_DIR + "DropWordGlow",
                                       glyphs={"DROP!": word})
    log("drawing Titles")
    art, glow, titles, rows = build_titles(face, stub)
    out.append(("Titles", art, "tga"))
    out.append(("TitlesGlow", white(glow), "dxt5"))
    data["atlases"]["Titles"] = dict(file=GAME_DIR + "Titles", w=2048, h=1024, cap=TITLE_CAP,
                                     baseline=TITLE_ROW / 2.0 + TITLE_CAP / 2.0, cellH=TITLE_ROW, rows=rows,
                                     stroke=TITLE_STROKE, glow=GAME_DIR + "TitlesGlow")
    data["titles"] = titles
    log("drawing plates, rings, markers")
    piece("Plate", build_plate, 256, 256)
    piece("PlateTab", build_plate_tab, 128, 64)
    piece("Button", build_button, 128, 64)
    piece("ButtonGlow", build_button_glow, 128, 64)
    piece("Banner", build_banner, 1024, 128)
    piece("ShineStrip", build_shine_strip, 1024, 128)
    piece("LabelHalo", build_label_halo, 64, 32)
    piece("FeedStrip", build_feed_strip, 256, 32)
    piece("Notch", build_notch, 64, 64)
    piece("CountRing", lambda: build_count_ring(512), 512, 512)
    piece("CountRingSmall", lambda: build_count_ring(128, detail=False), 128, 128)
    piece("Shock", lambda: build_shock(256), 256, 256)
    piece("ShockSmall", lambda: build_shock(128), 128, 128)
    piece("Gem", build_gem, 64, 32)
    piece("GemGlow", build_gem_glow, 32, 32)
    piece("You", build_you, 64, 64)
    piece("Arrow", build_arrow, 64, 64)
    piece("EdgeTick", build_edge_tick, 32, 32)
    piece("Pin", build_pin, 64, 64)
    piece("Parachute", build_parachute, 256, 128)
    piece("Altimeter", build_altimeter, 64, 512)
    piece("AltMarker", build_alt_marker, 64, 32)
    piece("Hatch", build_hatch, 32, 32)
    log("drawing icons")
    icons, cells = build_icons(64, stub)
    small, _ = build_icons(32, stub)
    out.append(("Icons", icons, "tga"))
    out.append(("IconsSmall", small, "tga"))
    data["icons"] = dict(file=GAME_DIR + "Icons", small=GAME_DIR + "IconsSmall", cellPx=64, smallCellPx=32,
                         cells=cells)
    log("drawing speed lines and the storm edge")
    piece("SpeedLinesA", lambda: build_speed_lines(71), 1024, 1024, "dxt5")
    piece("SpeedLinesB", lambda: build_speed_lines(73), 1024, 1024, "dxt5")
    piece("Vignette", build_vignette, 512, 512, "dxt5")

    for name, img, fmt in out:
        h, w = img.shape[:2]
        check(pow2(w) and pow2(h), "%s: %dx%d is not a power of two" % (name, w, h))
    for name in ("Notch", "You", "Arrow", "EdgeTick"):
        img = dict((n, i) for n, i, _ in out)[file_name(name)]
        check_rotatable(name, img)

    # the countdown's two-digit cap: the widest of 10..15 (NumeralsL metrics, stroke included) at most 88 % of the
    # ring's inner disc (196 units across a 280-unit ring)
    gl = data["atlases"]["NumeralsL"]["glyphs"]
    stroke_caps = NUMERAL_ATLASES[0].stroke / float(NUMERAL_ATLASES[0].cap)

    def width_caps(s):
        return sum(gl[c]["advance"] for c in s[:-1]) + gl[s[-1]]["inkR"] - gl[s[0]]["inkL"] + 2 * stroke_caps
    disc_units = 280.0 * 2 * RING_DISC
    widest = max(width_caps(str(n)) for n in range(10, 16))
    two_cap = min(112, int(math.floor(0.88 * disc_units / widest)))
    check(widest * two_cap <= 0.88 * disc_units + 1e-6, "the widest two-digit number does not fit the ring")
    data["countdown"] = dict(twoDigitCap=two_cap, ringUnits=280, discUnits=disc_units, widestTwoDigit=widest)
    data["ring"] = dict(file=GAME_DIR + "CountRing", small=GAME_DIR + "CountRingSmall", disc=2 * RING_DISC,
                        sockets=[dict(angle=a, r=RING_SOCKET_R) for a in socket_angles()])
    data["rotatable"] = {n: GAME_DIR + file_name(n) for n in ("Notch", "You", "Arrow", "EdgeTick")}
    data["slices"] = dict(
        Plate=dict(w=256, h=256, margin=32, edge=8, rim=6, chamfer=7, cornerUnits=16),
        PlateTab=dict(w=128, h=64, margin=16, edge=3, rim=4, chamfer=4, cornerUnits=8),
        Button=dict(w=128, h=64, margin=16, edge=4, rim=2, chamfer=6, cornerUnits=8),
        ButtonGlow=dict(w=128, h=64, margin=16, edge=4, rim=0, chamfer=6, cornerUnits=8),
        LabelHalo=dict(w=64, h=32, margin=12, edge=6, rim=0, chamfer=0, cornerUnits=6))
    data["gem"] = dict(socket=(0.0, 0.5, 0.0, 1.0), gem=(0.5, 1.0, 0.0, 1.0))
    data["parachute"] = dict(pack=(0.0, 0.5, 0.0, 1.0), canopy=(0.5, 1.0, 0.0, 1.0))
    data["altimeter"] = dict(top=ALT_TOP / 512.0, bottom=ALT_BOTTOM / 512.0)
    data["files"] = {FILE_KEYS.get(n, n): GAME_DIR + n for n, _, _ in out}
    return out, data


def check_rotatable(name, img):
    """SetRotation shows the whole texture turned inside the region (spec 1.7): nothing may lie outside the
    inscribed circle, and the art itself (the shape, before its soft outline) inside 70 % of it, with a 2-px clear
    border."""
    h, w = img.shape[:2]
    a = img[..., 3]
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    r = np.hypot(xs + 0.5 - w / 2.0, ys + 0.5 - h / 2.0)
    check(a[r > w / 2.0 - 2.0].max() <= 1.0 / 255.0, "%s: ink outside the inscribed circle less its 2-px border" % name)
    check(a[:2].max() + a[-2:].max() + a[:, :2].max() + a[:, -2:].max() <= 4.0 / 255.0, "%s: no 2-px clear border"
          % name)
    solid = a >= 0.98
    check(r[solid].max() <= 0.35 * w + 2.5, "%s: the shape leaves the inscribed 70 %%" % name)


# ============================================================================================ writing

def texture_bytes(img, fmt):
    pic = ak.to_image(img)
    if fmt == "tga":
        return ak.tga_bytes(pic.convert("RGBA"))
    raise ValueError(fmt)


def write_outputs(out, data, out_dir, data_path, log=print, jobs=None):
    os.makedirs(out_dir, exist_ok=True)
    for name, img, fmt in out:
        if fmt == "tga":
            path = os.path.join(out_dir, name + ".tga")
            with open(path, "wb") as f:
                f.write(texture_bytes(img, fmt))
        else:
            path = os.path.join(out_dir, name + ".blp")
            pic = ak.to_image(img).convert("RGBA")
            bc.convert(bc.Image(pic.width, pic.height, bytearray(pic.tobytes())), path, fmt=fmt, mips=False,
                       jobs=jobs)
        log("wrote %s (%dx%d, %s)" % (os.path.relpath(path, REPO), img.shape[1], img.shape[0], fmt))
    with open(data_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(lua_data(data))
    log("wrote %s" % os.path.relpath(data_path, REPO))


def num(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, np.integer)):
        return str(int(v))
    s = ("%.6f" % float(v)).rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def lua_str(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


LUA_WORDS = ("and", "break", "do", "else", "elseif", "end", "false", "for", "function", "if", "in", "local", "nil",
             "not", "or", "repeat", "return", "then", "true", "until", "while")


def lua_key(k):
    return k if (k.isidentifier() and k not in LUA_WORDS) else "[%s]" % lua_str(k)


def lua_value(v, indent):
    pad = "    " * indent
    if isinstance(v, dict):
        if not v:
            return "{}"
        keys = sorted(v.keys(), key=lambda k: (str(k)))
        if all(not isinstance(v[k], (dict, list, tuple)) for k in keys):  # a flat record fits on one line
            pos = [k for k in keys if k.isdigit()]
            named = [k for k in keys if not k.isdigit()]
            parts = [num(v[k]) for k in sorted(pos, key=int)] + \
                ["%s = %s" % (lua_key(k), lua_value(v[k], indent + 1)) for k in named]
            line = "{ " + ", ".join(parts) + " }"
            if len(pad) + len(line) <= 112:
                return line
        inner = []
        for k in keys:
            inner.append("%s    %s = %s," % (pad, lua_key(str(k)), lua_value(v[k], indent + 1)))
        return "{\n" + "\n".join(inner) + "\n" + pad + "}"
    if isinstance(v, (list, tuple)):
        if all(isinstance(x, (int, float, np.integer, np.floating)) for x in v):
            return "{ " + ", ".join(num(x) for x in v) + " }"
        return "{\n" + "\n".join("%s    %s," % (pad, lua_value(x, indent + 1)) for x in v) + "\n" + pad + "}"
    if isinstance(v, str):
        return lua_str(v)
    return num(v)


def lua_data(data):
    d = dict(data)
    # icon cells: positional { u0, u1, v0, v1 } plus the same four by name
    cells = {}
    for name, (u0, u1, v0, v1) in d["icons"]["cells"].items():
        cells[name] = {"1": u0, "2": u1, "3": v0, "4": v1, "u0": u0, "u1": u1, "v0": v0, "v1": v1}
    icons = dict(d["icons"])
    icons["cells"] = cells
    d["icons"] = icons
    body = lua_value(d, 0)
    head = """-- Bleakhold Royale art: every texture of Art\\Royale and the cells the addon lays out from.
-- Generated by Tools/BlpConvert/make_royale_hud_art.py with the art; do not edit (rerun the generator).
--
-- atlases.NumeralsL/M/S, DropWord: glyph metrics are in caps (1.0 = the atlas's cap height `cap`, in texels).
--   To draw a glyph at cap height c (units) with its pen at x on a baseline at y (y up): the quad is
--   cellW/cap*c wide and cellH/cap*c tall, its left edge at x - ox*c and its top at y + (baseline/cap)*c, with
--   texcoords u0..u1, v0..v1; then move the pen by advance*c. The ink spans x + inkL*c .. x + inkR*c, and the
--   dark stroke adds stroke/cap*c on each side. Every cell of an atlas shares one baseline, and the digits are
--   lining (aligned optically to the cap band), so a number never bobs. The glow atlas (`glow`) has the same
--   cells at half resolution: the same texcoords and quad.
-- titles: each fixed title's cell in the Titles atlas; w, h, inkW in caps. The cap's middle is the cell's
--   middle, and the ink is centred in it. Tint with SetVertexColor (the art is neutral silver).
-- icons.cells: { u0, u1, v0, v1 } (also by name) in both Icons (64-px cells) and IconsSmall (32-px cells).
-- ring.sockets: angle in radians (0 = right, pi/2 = up: the first socket at the top, then clockwise every 24
--   degrees) and r as a fraction of the ring's size; ring.disc: the dark centre disc's diameter, same fraction.
-- countdown.twoDigitCap: the cap (units) at which the widest of 10-15 fills at most 88 % of the inner disc.
-- slices: 9-slice margins in texels (corners drawn at cornerUnits); edge = where the plate's shape starts, rim =
--   its rim's width inside that, both in texels from the texture's edge / the shape's edge.
-- altimeter.top/bottom: the scale's drop height and ground rows, as fractions of the texture's height.
local _, ns = ...

ns.RoyaleArt = """
    return head + body + "\n"


# ============================================================================================ previews

def on_bg(img, rgb_=(24, 26, 31)):
    pic = ak.to_image(img).convert("RGBA")
    bg = Image.new("RGBA", pic.size, rgb_ + (255,))
    bg.alpha_composite(pic)
    return bg


def compose_number(atlas_img, at_data, text, cap_px, glow_img=None, glow_rgb=None, glow_alpha=0.0):
    """Lays a number out exactly as the data table says (advances, shared baseline), centred on its ink box;
    returns an RGBA picture and the baseline row in it."""
    glyphs = at_data["glyphs"]
    s = cap_px / float(at_data["cap"])
    stroke = at_data["stroke"] / float(at_data["cap"])
    width_c = sum(glyphs[c]["advance"] for c in text[:-1]) + glyphs[text[-1]]["inkR"] - glyphs[text[0]]["inkL"]
    pad = int(cap_px * 0.6)
    W = int(math.ceil(width_c * cap_px + 2 * stroke * cap_px)) + 2 * pad
    H = int(cap_px * 1.8) + 2 * pad
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    base = pad + int(cap_px * 1.3)
    x = pad + stroke * cap_px - glyphs[text[0]]["inkL"] * cap_px
    for c in text:
        g = glyphs[c]
        cw, ch = at_data["cellW"], at_data["cellH"]
        u0, v0 = int(round(g["u0"] * at_data["w"])), int(round(g["v0"] * at_data["h"]))
        cell = atlas_img.crop((u0, v0, u0 + cw, v0 + ch))
        qw, qh = max(1, int(round(cw * s))), max(1, int(round(ch * s)))
        cell = cell.resize((qw, qh), Image.BILINEAR if s > 0.5 else Image.BOX)
        left = int(round(x - g["ox"] * cap_px))
        top = int(round(base - at_data["baseline"] * s))
        if left >= 0 and top >= 0:
            canvas.alpha_composite(cell, (left, top))
        x += g["advance"] * cap_px
    return canvas, base


def write_previews(out, data, pdir, log=print):
    os.makedirs(pdir, exist_ok=True)
    pics = {}
    for name, img, fmt in out:
        pic = ak.to_image(img).convert("RGBA")
        pics[name] = pic
        bg = Image.new("RGBA", pic.size, (24, 26, 31, 255))
        bg.alpha_composite(pic)
        bg.save(os.path.join(pdir, name + ".png"))
    # the contact sheet: every texture at 1:1 on a dark ground, labelled
    label_font = ImageFont.truetype(FONT_SC, 18)
    order = [n for n, _, _ in out]
    x = y = 16
    rowh = 0
    W = 2048 + 32
    placed = []
    for n in order:
        p = pics[n]
        tw = max(p.width, int(label_font.getlength("%s  %dx%d" % (n, p.width, p.height))) + 8)
        if x + tw > W - 16:
            x, y = 16, y + rowh + 40
            rowh = 0
        placed.append((n, x, y))
        x += tw + 24
        rowh = max(rowh, p.height)
    H = y + rowh + 40
    sheet = Image.new("RGBA", (W, H), (34, 30, 27, 255))
    d = ImageDraw.Draw(sheet)
    for n, px, py in placed:
        p = pics[n]
        tile = Image.new("RGBA", p.size, (24, 26, 31, 255))
        # a checker under soft art shows its alpha
        if n.endswith("Glow") or n in ("SpeedLinesA", "SpeedLinesB", "Vignette", "ShineStrip", "Shock", "ShockSmall",
                                        "Hatch", "LabelHalo"):
            ys, xs = np.mgrid[0:p.height, 0:p.width]
            chk = (((xs // 16) + (ys // 16)) % 2).astype(np.uint8) * 18 + 30
            tile = Image.fromarray(np.dstack([chk, chk, chk + 6, np.full_like(chk, 255)]).astype(np.uint8))
        tile.alpha_composite(p)
        sheet.alpha_composite(tile, (px, py + 24))
        d.text((px, py), "%s  %dx%d" % (n, p.width, p.height), font=label_font, fill=(243, 221, 164, 255))
    # the countdown: the ring at 280 units on a 1080p screen (1.406 px per unit), with 15, 10, 4 and 1
    ppu = 1080 / 768.0
    ring_px = int(round(280 * ppu))
    two = data["countdown"]["twoDigitCap"]
    shots = []
    for text, cap_u in (("15", two), ("10", two), ("4", 150), ("1", 172)):
        canvas = Image.new("RGBA", (ring_px + 80, ring_px + 80), (52, 70, 58, 255))
        ring = pics["CountRing"].resize((ring_px, ring_px), Image.BOX)
        canvas.alpha_composite(ring, (40, 40))
        notch = pics["Notch"]
        n_lit = int(text)
        for i, sock in enumerate(data["ring"]["sockets"]):
            a = sock["angle"]
            vis = 22 * ppu
            reg = int(round(vis * math.sqrt(2)))
            img = notch.resize((reg, reg), Image.BOX).rotate(math.degrees(a) - 90, resample=Image.BILINEAR)
            lit = i < n_lit
            tint = (243, 221, 164) if lit and n_lit > 3 else ((255, 122, 61) if lit else (59, 42, 20))
            arr = np.asarray(img).astype(np.float32)
            arr[..., :3] *= np.array(tint, dtype=np.float32) / 255.0
            if not lit:
                arr[..., 3] *= 0.9
            img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
            cx = 40 + ring_px / 2 + math.cos(a) * sock["r"] * ring_px
            cy = 40 + ring_px / 2 - math.sin(a) * sock["r"] * ring_px
            canvas.alpha_composite(img, (int(round(cx - reg / 2)), int(round(cy - reg / 2))))
        cap_px = cap_u * ppu
        at = "NumeralsL" if cap_px >= 144 else ("NumeralsM" if cap_px >= 72 else "NumeralsS")
        numimg, base = compose_number(pics[at], data["atlases"][at], text, cap_px)
        # the cap's middle on the ring's centre
        ox = int(round(40 + ring_px / 2 - numimg.width / 2))
        oy = int(round(40 + ring_px / 2 - (base - cap_px / 2)))
        layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        layer.paste(numimg, (ox, oy))
        canvas.alpha_composite(layer)
        shots.append(canvas)
    row = Image.new("RGBA", (sum(s.width for s in shots) + 16 * (len(shots) + 1), shots[0].height + 32),
                    (34, 30, 27, 255))
    xx = 16
    for s_ in shots:
        row.alpha_composite(s_, (xx, 16))
        xx += s_.width + 16
    row.save(os.path.join(pdir, "countdown_1080p.png"))
    plate_shot = write_drop_plate_preview(pics, data, pdir)
    # the contact sheet ends with the two mock-ups: the countdown at 15, 10, 4 and 1, and the drop plate
    extra = [row, plate_shot]
    full = Image.new("RGBA", (W, H + sum(e.height + 16 for e in extra) + 16), (34, 30, 27, 255))
    full.alpha_composite(sheet, (0, 0))
    yy = H + 16
    for e in extra:
        full.alpha_composite(e.crop((0, 0, min(e.width, W), e.height)), (0, yy))
        yy += e.height + 16
    full.save(os.path.join(pdir, "contact_sheet.png"))
    log("wrote previews to %s" % pdir)


def nine_slice(pic, w, h, margin, corner):
    """Draws a 9-slice texture into a w x h picture with corners `corner` pixels big (as the addon does)."""
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    tw, th = pic.size
    m = margin
    xs_src = [0, m, tw - m, tw]
    ys_src = [0, m, th - m, th]
    xs_dst = [0, corner, w - corner, w]
    ys_dst = [0, corner, h - corner, h]
    for i in range(3):
        for j in range(3):
            src = pic.crop((xs_src[i], ys_src[j], xs_src[i + 1], ys_src[j + 1]))
            dw, dh = xs_dst[i + 1] - xs_dst[i], ys_dst[j + 1] - ys_dst[j]
            if dw > 0 and dh > 0:
                out.alpha_composite(src.resize((dw, dh), Image.BILINEAR), (xs_dst[i], ys_dst[j]))
    return out


def write_drop_plate_preview(pics, data, pdir):
    """The drop plate (320x68 units at 1080p) in freefall: pack, FREEFALL, 'Parachute opens in', the numeral 8 (the
    owner's 8 s freefall); and under the canopy: PARACHUTE, 'Landing in 12', the bar. FRIZQT is not shipped with
    the tools, so its lines are set in Marcellus here."""
    ppu = 1080 / 768.0
    W, H = int(320 * ppu), int(68 * ppu)
    shots = []
    for phase in ("freefall", "canopy"):
        bg = Image.new("RGBA", (W + 60, H + 60), (96, 128, 150, 255))
        plate = nine_slice(pics["Plate"], W, H, 32, int(16 * ppu))
        bg.alpha_composite(plate, (30, 30))
        para = pics["Parachute"].crop((0, 0, 128, 128) if phase == "freefall" else (128, 0, 256, 128))
        ps = int(44 * ppu)
        bg.alpha_composite(para.resize((ps, ps), Image.BOX), (30 + int(12 * ppu), 30 + (H - ps) // 2))
        d = ImageDraw.Draw(bg)
        lab = ImageFont.truetype(FONT_SC, int(11 * ppu))
        body = ImageFont.truetype(os.path.join(ADDON, "Fonts", "Marcellus-Regular.ttf"), int(14 * ppu))
        tx = 30 + int(64 * ppu)
        d.text((tx, 30 + int(12 * ppu)), "FREEFALL" if phase == "freefall" else "PARACHUTE", font=lab,
               fill=(243, 221, 164, 255))
        d.text((tx, 30 + int(28 * ppu)), "Parachute opens in" if phase == "freefall" else "Landing in 12", font=body,
               fill=(242, 232, 208, 255))
        if phase == "freefall":
            cap = 34 * ppu
            at = "NumeralsS" if cap < 72 else "NumeralsM"
            numimg, base = compose_number(pics[at], data["atlases"][at], "8", cap)
            right = 30 + W - int(14 * ppu)
            ox = right - numimg.width + int(cap * 0.6)
            oy = 30 + H // 2 - int(base - cap / 2)
            bg.alpha_composite(numimg, (max(0, ox), max(0, oy)))
        else:
            bx, by, bw, bh = tx, 30 + int(48 * ppu), int(200 * ppu), max(3, int(5 * ppu))
            d.rectangle((bx, by, bx + bw, by + bh), fill=(59, 42, 20, 255))
            d.rectangle((bx, by, bx + int(bw * 0.62), by + bh), fill=(229, 192, 123, 255))
            d.rectangle((bx + int(bw * 0.62) - 2, by, bx + int(bw * 0.62), by + bh), fill=(255, 241, 200, 255))
        shots.append(bg)
    sheet = Image.new("RGBA", (shots[0].width * 2 + 48, shots[0].height + 32), (34, 30, 27, 255))
    sheet.alpha_composite(shots[0], (16, 16))
    sheet.alpha_composite(shots[1], (32 + shots[0].width, 16))
    sheet.save(os.path.join(pdir, "drop_plate_1080p.png"))
    return sheet


# ============================================================================================ main

def memory_estimate(out, art_dir):
    """Texture memory of every Royale texture when loaded (spec 1.6 budget 40 MB): 32-bit TGA 4 bytes a texel (24-bit
    TGA too: the client adds alpha), DXT5 1, DXT1 0.5; the map family (make_royale_art.py) read from the files."""
    mine = set()
    total = 0.0
    for name, img, fmt in out:
        h, w = img.shape[:2]
        total += w * h * (4 if fmt == "tga" else 1)
        mine.add(name.lower())
    other = 0.0
    if os.path.isdir(art_dir):
        for f in sorted(os.listdir(art_dir)):
            base, ext = os.path.splitext(f)
            if base.lower() in mine or ext.lower() not in (".tga", ".blp"):
                continue
            path = os.path.join(art_dir, f)
            if ext.lower() == ".tga":
                w, h, _ = ak.read_tga_size(path)
                other += w * h * 4
            else:
                with open(path, "rb") as fh:
                    head = fh.read(20)
                enc, alpha = head[8], head[9]
                w, h = int.from_bytes(head[12:16], "little"), int.from_bytes(head[16:20], "little")
                other += w * h * (4 if enc == 3 else (0.5 if alpha == 0 else 1))
    return total / 2 ** 20, other / 2 ** 20


def compare(out_dir, ref_dir, names, data_new, data_ref):
    bad = []
    for n in names:
        a, b = os.path.join(out_dir, n), os.path.join(ref_dir, n)
        if not os.path.exists(b):
            bad.append("missing in the repository: %s" % n)
        elif not filecmp.cmp(a, b, shallow=False):
            bad.append("differs: %s" % n)
    if not os.path.exists(data_ref):
        bad.append("missing in the repository: RoyaleArtData.lua")
    elif not filecmp.cmp(data_new, data_ref, shallow=False):
        bad.append("differs: RoyaleArtData.lua")
    return bad


def main():
    ap = argparse.ArgumentParser(description="Draw the Bleakhold Royale HUD art and RoyaleArtData.lua.")
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--data", default=DATA)
    ap.add_argument("--preview", help="also write PNGs, a contact sheet and mock-ups here")
    ap.add_argument("--stub", action="store_true", help="flat placeholder art, same files and cells")
    ap.add_argument("--check", metavar="DIR", help="draw into DIR and fail when a committed file differs")
    ap.add_argument("--jobs", type=int, default=None, help="DXT encoder processes (default: all cores)")
    a = ap.parse_args()
    try:
        out, data = build_all(stub=a.stub)
    except Fail as e:
        print("make_royale_hud_art: FAIL: %s" % e, file=sys.stderr)
        return 1
    hud_mb, map_mb = memory_estimate(out, OUT)
    if a.check:
        if os.path.isdir(a.check):
            shutil.rmtree(a.check)
        art_dir = os.path.join(a.check, "Art", "Royale")
        data_path = os.path.join(a.check, "RoyaleArtData.lua")
        write_outputs(out, data, art_dir, data_path, log=lambda s: None, jobs=a.jobs)
        names = [n + (".tga" if f == "tga" else ".blp") for n, _, f in out]
        bad = compare(art_dir, OUT, names, data_path, DATA)
        for n, _, f in out:
            if f == "tga" and os.path.exists(os.path.join(OUT, n + ".blp")):
                bad.append("stale %s.blp would hide %s.tga in the client" % (n, n))
        if bad:
            for b in bad:
                print("make_royale_hud_art: " + b, file=sys.stderr)
            print("make_royale_hud_art: the committed art is out of date (run python3 -I "
                  "Tools/BlpConvert/make_royale_hud_art.py; Pillow %s, numpy %s here)"
                  % (Image.__version__ if hasattr(Image, "__version__") else "?", np.__version__), file=sys.stderr)
            return 1
        print("make_royale_hud_art: %d textures and RoyaleArtData.lua match the generator" % len(out))
        return 0
    write_outputs(out, data, a.out, a.data, jobs=a.jobs)
    for n, _, f in out:  # a .blp wins over a .tga of the same name in the client
        stale = os.path.join(a.out, n + ".blp")
        if f == "tga" and os.path.exists(stale):
            os.remove(stale)
            print("removed %s (replaced by %s.tga)" % (os.path.relpath(stale, REPO), n))
    if a.preview:
        write_previews(out, data, a.preview)
    print("texture memory: HUD art %.1f MB + map art %.1f MB = %.1f MB (budget 40 MB)" % (hud_mb, map_mb,
                                                                                         hud_mb + map_mb))
    if hud_mb + map_mb > 40.0:
        print("make_royale_hud_art: FAIL: over the 40 MB texture budget", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
