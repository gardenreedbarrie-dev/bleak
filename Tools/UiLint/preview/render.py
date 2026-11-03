"""Draws driver.lua's region dump like the 3.3.5a client (preview only; render.sh runs it).

    python3 -I render.py measure dump.json out.lua [roots...]   text widths, wrapped line counts, texture sizes
    python3 -I render.py draw dump.json out.png [roots...] [--bg flat|black|ground|air|IMAGE] [--missing skip|mark]
                                                           [--crop X0,Y0,X1,Y1] [--scale F] [--strict 1]
roots: --repo DIR --addon DIR --stock DIR --journal DIR --font NAME=FILE (repeatable) --font-stretch F

Textures: Interface\\AddOns\\Bleakhold\\Art\\Journal\\* from --journal, the addon's own files from --addon, other
Interface\\ paths from the repository's Interface\\ tree and then from --stock (a stock-art folder laid out like
Interface\\: DialogFrame\\, Buttons\\, ...; or with an Interface\\ folder in it). Every lookup ignores case, as the
client does, and takes .blp, then .tga, then .png. Sampling is bilinear with clamped edges (or repeat when the texture
tiles) and no mipmaps (CSimpleRender.cpp's plain linear filter); the four corners come from the region's texcoords;
vertex colour or gradient, alpha, BLEND / ADD / MOD / ALPHAKEY / DISABLE, desaturation; SetPortraitToTexture's 64x64
circle (CHARACTERFRAME\\TempPortraitAlphaMaskSmall, or a drawn circle when the stock folder lacks it).
Text: see Fonts (the FRIZQT stand-in); lines wrap at the region's width like the client (at spaces).
Models are not drawn: each shown Model / PlayerModel / DressUpModel box gets the caption "3D model (shown in game)"
and, when it shows the player, a faint standing figure (draw_model).
"""
import json
import math
import os
import re
import sys

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))

SEG = re.compile(r"\|c([0-9a-fA-F]{8})|\|r")
EXTS = (".blp", ".tga", ".png")


def parse_args(argv):
    pos, opt, fonts = [], {}, {}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("--"):
            key = a[2:]
            val = argv[i + 1] if i + 1 < len(argv) else ""
            i += 2
            if key == "font":
                name, _, path = val.partition("=")
                fonts[name.upper()] = path
            else:
                opt[key] = val
        else:
            pos.append(a)
            i += 1
    return pos, opt, fonts


class Art:
    """Finds and decodes the files behind texture paths, ignoring case."""

    def __init__(self, repo, addon, stock, journal):
        self.repo, self.addon, self.stock, self.journal = repo, addon, stock, journal
        self.index = {}
        self.cache = {}
        self.missing = set()
        self.mask = None

    def _index(self, root):
        if root in self.index:
            return self.index[root]
        idx = {}
        if root and os.path.isdir(root):
            for d, dirs, files in os.walk(root):
                dirs[:] = [x for x in dirs if x != ".git"]
                for f in files:
                    stem, ext = os.path.splitext(f)
                    if ext.lower() not in EXTS:
                        continue
                    rel = os.path.relpath(os.path.join(d, stem), root).replace(os.sep, "/").lower()
                    idx.setdefault(rel, {})[ext.lower()] = os.path.join(d, f)
        self.index[root] = idx
        return idx

    def _find(self, root, rel):
        rel = rel.replace("\\", "/").lower()
        stem, ext = os.path.splitext(rel)
        if ext in EXTS:
            rel = stem
        hit = self._index(root).get(rel)
        if not hit:
            return None
        for e in EXTS:
            if e in hit:
                return hit[e]
        return None

    def locate(self, path):
        low = path.replace("/", "\\").lower()
        journal = "interface\\addons\\bleakhold\\art\\journal\\"
        own = "interface\\addons\\bleakhold\\"
        if low.startswith(journal):
            return self._find(self.journal, path[len(journal):]) if self.journal else None
        if low.startswith(own):
            return self._find(self.addon, path[len(own):])
        if low.startswith("interface\\"):
            rest = path[len("interface\\"):]
            hit = self._find(os.path.join(self.repo, "Interface"), rest) if self.repo else None
            if not hit and self.stock:
                hit = self._find(self.stock, rest) or self._find(self.stock, "Interface\\" + rest)
            return hit
        return None

    def decode(self, file):
        if file.lower().endswith(".blp"):
            sys.path.insert(0, os.path.join(REPO, "Tools", "BlpConvert"))
            import blpconvert as bc  # noqa: E402
            b = bc.decode_blp(file)
            img = Image.frombytes("RGBA", (b.width, b.height), bytes(b.data))
        else:
            img = Image.open(file).convert("RGBA")
        return img

    def image(self, path):
        """The file as an RGBA PIL image, or None."""
        file = self.locate(path)
        if not file:
            self.missing.add(path)
            return None
        return self.decode(file)

    def texture(self, path, portrait=False):
        key = (path, portrait)
        if key in self.cache:
            return self.cache[key]
        img = self.image(path)
        if img is None:
            self.cache[key] = None
            return None
        if portrait:
            img = self.portrait(img)
        arr = np.asarray(img).astype(np.float32) / 255.0
        self.cache[key] = arr
        return arr

    def portrait(self, img):
        # PortraitButton.cpp SetPortraitTexture: the file's 64x64 texels with their alpha replaced by the mask's
        if img.size != (64, 64):
            img = img.resize((64, 64), Image.BILINEAR)
        if self.mask is None:
            m = self.image("Interface\\CharacterFrame\\TempPortraitAlphaMaskSmall")
            if m is not None:
                # the client reads one channel of the grey mask (GetAlphaMask); the PNG exports carry it in alpha
                self.mask = m.convert("RGBA").resize((64, 64)).split()[3]
                self.missing.discard("Interface\\CharacterFrame\\TempPortraitAlphaMaskSmall")
            else:
                big = Image.new("L", (256, 256), 0)
                ImageDraw.Draw(big).ellipse((4, 4, 251, 251), fill=255)
                self.mask = big.resize((64, 64), Image.LANCZOS)
        out = img.copy()
        out.putalpha(self.mask)
        return out


def sample(tex, u, v, wrap=False):
    """Bilinear, clamp to edge (or repeat), texel centres at (i + 0.5) / size."""
    h, w = tex.shape[:2]
    x = u * w - 0.5
    y = v * h - 0.5
    if wrap:
        x0 = np.floor(x).astype(np.int64)
        y0 = np.floor(y).astype(np.int64)
        fx = (x - x0)[..., None]
        fy = (y - y0)[..., None]
        x1, y1 = (x0 + 1) % w, (y0 + 1) % h
        x0, y0 = x0 % w, y0 % h
    else:
        x = np.clip(x, 0, w - 1)
        y = np.clip(y, 0, h - 1)
        x0 = np.floor(x).astype(np.int64)
        y0 = np.floor(y).astype(np.int64)
        fx = (x - x0)[..., None]
        fy = (y - y0)[..., None]
        x1 = np.minimum(x0 + 1, w - 1)
        y1 = np.minimum(y0 + 1, h - 1)
    a = tex[y0, x0] * (1 - fx) + tex[y0, x1] * fx
    b = tex[y1, x0] * (1 - fx) + tex[y1, x1] * fx
    return a * (1 - fy) + b * fy


def clip_box(it, W, H):
    cl = it.get("clip")
    if not cl:
        return 0, 0, W, H
    return max(0, cl[0]), max(0, cl[1]), min(W, cl[2]), min(H, cl[3])


def draw_texture(canvas, it, art, missing_mode):
    L, R, T, B = it.get("L"), it.get("R"), it.get("T"), it.get("B")
    if None in (L, R, T, B) or R - L < 0.01 or B - T < 0.01:
        return
    H, W = canvas.shape[:2]
    cx0, cy0, cx1, cy1 = clip_box(it, W, H)
    x0, x1 = max(int(math.floor(cx0)), int(math.floor(L))), min(int(math.ceil(cx1)), int(math.ceil(R)))
    y0, y1 = max(int(math.floor(cy0)), int(math.floor(T))), min(int(math.ceil(cy1)), int(math.ceil(B)))
    if x1 <= x0 or y1 <= y0:
        return
    if it.get("path"):
        tex = art.texture(it["path"], it.get("portrait"))
        if tex is None:
            if missing_mode != "mark":
                return
            tex = np.array([[[1, 0, 1, 1]]], dtype=np.float32)
    else:
        s = (list(it.get("solid") or [1, 1, 1, 1]) + [1, 1, 1, 1])[:4]
        tex = np.array([[s]], dtype=np.float32)
    ys, xs = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    s = (xs + 0.5 - L) / (R - L)
    t = (ys + 0.5 - T) / (B - T)
    # the GPU's rule: a pixel belongs to the quad when its centre is inside (top-left edges in, bottom-right out)
    inside = (xs + 0.5 >= L) & (xs + 0.5 < R) & (ys + 0.5 >= T) & (ys + 0.5 < B)
    inside &= (xs + 0.5 >= cx0) & (xs + 0.5 < cx1) & (ys + 0.5 >= cy0) & (ys + 0.5 < cy1)
    tc = it.get("tc") or [0, 0, 0, 1, 1, 0, 1, 1]
    ul = np.array(tc[0:2]); ll = np.array(tc[2:4]); ur = np.array(tc[4:6]); lr = np.array(tc[6:8])
    s_ = np.clip(s, 0, 1)[..., None]
    t_ = np.clip(t, 0, 1)[..., None]
    uv = ul * (1 - s_) * (1 - t_) + ur * s_ * (1 - t_) + ll * (1 - s_) * t_ + lr * s_ * t_
    px = sample(tex, uv[..., 0], uv[..., 1], it.get("wrap"))
    g = it.get("grad")
    if g:
        # CSimpleRegion::SetVertexGradient: HORIZONTAL min left -> max right, VERTICAL min bottom -> max top
        k = s_ if g[0] == "HORIZONTAL" else 1 - t_
        c1 = np.array(g[1:5], dtype=np.float32)
        c2 = np.array(g[5:9], dtype=np.float32)
        col = c1 * (1 - k) + c2 * k
    else:
        col = np.array((list(it.get("color") or [1, 1, 1, 1]) + [1, 1, 1, 1])[:4], dtype=np.float32)
    rgb = px[..., :3]
    if it.get("desat"):
        lum = (rgb * np.array([0.299, 0.587, 0.114], dtype=np.float32)).sum(-1, keepdims=True)
        rgb = np.repeat(lum, 3, -1)
    rgb = rgb * col[..., :3]
    a = px[..., 3] * col[..., 3] * it["alpha"] * inside
    blend = (it.get("blend") or "BLEND").upper()
    region = canvas[y0:y1, x0:x1]
    if blend == "ADD":
        region[..., :3] = np.minimum(1, region[..., :3] + rgb * a[..., None])
    elif blend == "MOD":
        region[..., :3] = region[..., :3] * (rgb * a[..., None] + (1 - a[..., None]))
    else:
        if blend == "ALPHAKEY":
            a = np.where(a >= 0.5, 1.0, 0.0) * inside
        elif blend == "DISABLE":
            a = inside.astype(np.float32) * it["alpha"]
        region[..., :3] = region[..., :3] * (1 - a[..., None]) + rgb * a[..., None]


class Face:
    """One client font at one pixel size: the stand-in file, its width factor, a faux-bold stroke and, for the
    stand-ins, lining digits."""

    def __init__(self, fonts, path, digit_path, px, stretch, bold):
        self.fonts, self.path, self.digit_path, self.px = fonts, path, digit_path, px
        self.stretch, self.bold = stretch, bold
        self.font = fonts.ft(path, px)
        self.digits = fonts.ft(digit_path, px) if digit_path else None

    def at(self, k):
        """The same face k times larger (the supersampled drawing)."""
        return Face(self.fonts, self.path, self.digit_path, int(round(self.px * k)), self.stretch, self.bold)

    def runs(self, s):
        if not self.digits:
            return [(s, self.font)] if s else []
        out = []
        for m in re.finditer(r"[0-9]+|[^0-9]+", s):
            out.append((m.group(0), self.digits if m.group(0)[0].isdigit() else self.font))
        return out

    def raw_length(self, s):
        return sum(f.getlength(c) for c, f in self.runs(s))

    def length(self, s):
        return self.raw_length(s) * self.stretch


class Fonts:
    """Client font paths to faces. FRIZQT__.TTF (the client's body font) is not in the repository: the addon's
    Marcellus Regular stands in, widened by 9% and thickened by a third of a pixel (measured against the owner's
    screenshot of the old window: Friz Quadrata runs 7-13% wider at the same height, with heavier strokes) and with
    lining digits from Liberation Serif, since Marcellus's old-style 0 and 1 read as O and I. MORPHEUS and the other
    stock faces fall back to Marcellus as before."""

    STRETCH = {"FONTS\\FRIZQT__.TTF": 1.09}
    BOLD = {"FONTS\\FRIZQT__.TTF": 1 / 3}   # extra stroke, in screen pixels

    def __init__(self, addon, extra, stretch=None):
        marcellus = os.path.join(addon, "Fonts", "Marcellus-Regular.ttf")
        sans = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
        serif = "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf"
        self.map = {
            "FONTS\\FRIZQT__.TTF": marcellus,
            "FONTS\\MORPHEUS.TTF": marcellus,
            "FONTS\\ARIALN.TTF": sans if os.path.exists(sans) else marcellus,
            "FONTS\\SKURRI.TTF": marcellus,
        }
        self.stand_in = {"FONTS\\FRIZQT__.TTF", "FONTS\\MORPHEUS.TTF", "FONTS\\SKURRI.TTF"}
        self.digit_file = serif if os.path.exists(serif) else None
        self.addon = addon
        self.default = marcellus
        self.stretch = dict(self.STRETCH)
        self.bold = dict(self.BOLD)
        if stretch is not None:
            self.stretch["FONTS\\FRIZQT__.TTF"] = stretch
        for k, v in extra.items():
            key = k if "\\" in k else "FONTS\\" + k
            self.map[key] = v
            self.stand_in.discard(key)   # a real face: as it is
            self.stretch.pop(key, None)
            self.bold.pop(key, None)
        self.cache = {}
        self.faces = {}

    def path(self, name):
        up = name.upper()
        if up in self.map:
            return self.map[up], up in self.stand_in
        own = "INTERFACE\\ADDONS\\BLEAKHOLD\\"
        if up.startswith(own):
            p = os.path.join(self.addon, name[len(own):].replace("\\", "/"))
            if os.path.exists(p):
                return p, False
        return self.default, True

    def ft(self, path, px):
        key = (path, px)
        if key not in self.cache:
            self.cache[key] = ImageFont.truetype(path, max(4, px))
        return self.cache[key]

    def get(self, name, px):
        key = (name.upper(), px)
        if key not in self.faces:
            path, stand_in = self.path(name)
            digits = self.digit_file if stand_in else None
            self.faces[key] = Face(self, path, digits, px, self.stretch.get(name.upper(), 1.0),
                                   self.bold.get(name.upper(), 0))
        return self.faces[key]


def segments(text, base):
    out, pos, col = [], 0, base
    for m in SEG.finditer(text):
        if m.start() > pos:
            out.append((text[pos:m.start()], col))
        if m.group(1):
            h = m.group(1)
            col = (int(h[2:4], 16) / 255, int(h[4:6], 16) / 255, int(h[6:8], 16) / 255, base[3])
        else:
            col = base
        pos = m.end()
    if pos < len(text):
        out.append((text[pos:], col))
    return out


def wrap_lines(face, text, wrap_px):
    """Splits on newlines, then wraps each at wrap_px (at spaces; a word wider than the line goes on its own)."""
    lines = []
    for para in text.split("\n"):
        if wrap_px is None:
            lines.append(para)
            continue
        cur = ""
        for w in para.split(" "):
            cand = w if not cur else cur + " " + w
            if cur and face.length(SEG.sub("", cand)) > wrap_px + 0.5:
                lines.append(cur)
                cur = w
            else:
                cur = cand
        lines.append(cur)
    return lines


def carry_colours(lines):
    """Each wrapped line starts in the colour the previous one ended in (|c...|r spans lines)."""
    out, open_code = [], None
    for ln in lines:
        prefix = ("|c" + open_code) if open_code else ""
        out.append(prefix + ln)
        for m in SEG.finditer(ln):
            open_code = m.group(1) if m.group(1) else None
    return out


def measure(dump, fonts, art, out):
    widths, lines, sizes = {}, {}, {}
    for it in dump["items"]:
        if it["kind"] != "FontString":
            continue
        face = fonts.get(it["font"], it["px"])
        plain = SEG.sub("", it["text"])
        widths["%s|%d|%s" % (it["font"], it["px"], plain)] = max(face.length(p) for p in plain.split("\n"))
        if it.get("wrapPx"):
            n = len(wrap_lines(face, plain, it["wrapPx"]))
            lines["%s|%d|%d|%s" % (it["font"], it["px"], it["wrapPx"], plain)] = n
    for path in dump.get("needSizes", []):
        img = art.image(path)
        if img is not None:
            sizes[path] = img.size

    def lua_str(v):
        return json.dumps(v, ensure_ascii=False)
    rows = ["return {", "  widths = {"]
    rows += ["    [%s] = %.3f," % (lua_str(k), v) for k, v in widths.items()]
    rows += ["  },", "  lines = {"]
    rows += ["    [%s] = %d," % (lua_str(k), v) for k, v in lines.items()]
    rows += ["  },", "  sizes = {"]
    rows += ["    [%s] = { %d, %d }," % (lua_str(k), v[0], v[1]) for k, v in sizes.items()]
    rows += ["  },", "}"]
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(rows) + "\n")


SS = 3   # text is drawn at three times the size and scaled down (smoother edges, sub-pixel faux bold)


def draw_line(layer, face, segs, x, cy, line_h, it, alpha, stroke):
    """Draws one line (its colour segments) at x / vertical centre cy: supersampled and unstretched into a scratch
    image, then scaled down and widened by the face's factor, so shadow, outline and digits stretch with the letters."""
    ppu = (it.get("ppu") or 1) * SS
    big = face.at(SS)
    sox, soy = it.get("shadow") or (0, 0)
    sc = it.get("shadowColor") or (0, 0, 0, 0)
    bold = int(round(big.bold * SS))
    raw_w = sum(big.raw_length(s) for s, _ in segs)
    pad = int(math.ceil(SS * stroke + bold + abs(sox) * ppu + abs(soy) * ppu + 2 * SS))
    w, h = int(math.ceil(raw_w)) + 2 * pad, int(math.ceil(line_h * SS * 1.6)) + 2 * pad
    w += (-w) % SS
    h += (-h) % SS
    tmp = Image.new("RGBA", (max(SS, w), max(SS, h)), (0, 0, 0, 0))
    d = ImageDraw.Draw(tmp)
    mid = h / 2
    cx = pad
    for s, c in segs:
        ca = c[3] if len(c) > 3 else 1
        fill = (int(c[0] * 255), int(c[1] * 255), int(c[2] * 255), int(255 * ca * alpha))
        for run, f in big.runs(s):
            if len(sc) > 3 and sc[3] > 0 and (sox or soy):
                shade = (int(sc[0] * 255), int(sc[1] * 255), int(sc[2] * 255), int(sc[3] * 255 * alpha))
                d.text((cx + sox * ppu, mid - soy * ppu), run, font=f, anchor="lm", fill=shade, stroke_width=bold,
                       stroke_fill=shade)
            if stroke:
                black = (0, 0, 0, int(255 * ca * alpha))
                d.text((cx, mid), run, font=f, anchor="lm", fill=black, stroke_width=SS * stroke + bold,
                       stroke_fill=black)
            d.text((cx, mid), run, font=f, anchor="lm", fill=fill, stroke_width=bold, stroke_fill=fill)
            cx += f.getlength(run)
    k = face.stretch
    out_w, out_h = max(1, int(round(w * k / SS))), max(1, h // SS)
    tmp = tmp.resize((out_w, out_h), Image.LANCZOS)
    ox, oy = int(round(x - pad * k / SS)), int(round(cy - mid / SS))
    layer.alpha_composite(tmp, (max(0, ox), max(0, oy)), (max(0, -ox), max(0, -oy)))


def draw_text(img, it, fonts):
    L, R, T, B = it.get("L"), it.get("R"), it.get("T"), it.get("B")
    if None in (L, R, T, B):
        return
    ppu = it.get("ppu") or 1
    face = fonts.get(it["font"], it["px"])
    base = tuple((list(it["color"]) + [1, 1, 1, 1])[:4])
    lines = carry_colours(wrap_lines(face, it["text"], it.get("wrapPx")))
    line_h = it["size"] * ppu
    spacing = (it.get("spacing") or 0) * ppu
    pitch = line_h + spacing
    if it.get("fixedH"):
        # a box of fixed height keeps the lines that fit; the last one kept ends in "..." (CSimpleFontString)
        fit = max(1, int((B - T + spacing) // max(pitch, 1)))
        if len(lines) > fit:
            lines = lines[:fit]
            lines[-1] = lines[-1].rstrip() + "..."
    total = line_h + (len(lines) - 1) * pitch
    jv = it.get("justifyV") or "MIDDLE"
    if jv == "TOP":
        y = T
    elif jv == "BOTTOM":
        y = B - total
    else:
        y = (T + B) / 2 - total / 2
    flags = (it.get("flags") or "").upper()
    stroke = 2 if "THICKOUTLINE" in flags else (1 if "OUTLINE" in flags else 0)
    just = it.get("justify", "CENTER")
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    for ln in lines:
        segs = segments(ln, base)
        total_w = sum(face.length(s) for s, _ in segs)
        if just == "LEFT":
            x = L
        elif just == "RIGHT":
            x = R - total_w
        else:
            x = (L + R) / 2 - total_w / 2
        draw_line(layer, face, segs, x, y + line_h / 2, line_h, it, it["alpha"], stroke)
        y += pitch
    cl = it.get("clip")
    if cl:
        mask = Image.new("L", img.size, 0)
        ImageDraw.Draw(mask).rectangle([cl[0], cl[1], cl[2] - 1, cl[3] - 1], fill=255)
        layer.putalpha(ImageChops.multiply(layer.split()[3], mask))
    img.alpha_composite(layer)


# Model frames: the 3D model is not drawn (draw_model marks the box instead). A box that shows the player (a
# DressUpModel or TabardModel, or a model given SetUnit("player")) holds a faint standing figure with the caption under
# it; any other model box (a mount, a pet) holds the caption in its centre. The caption is grey FRIZQT 11 (smaller only
# in a box without a figure that is too narrow for it at 11).
MODEL_CAPTION = "3D model (shown in game)"
MODEL_CAPTION_LINES = "3D model\n(shown in game)"   # when one line does not fit the box
MODEL_CAPTION_SIZE = 11
MODEL_CAPTION_COLOR = [0.5, 0.5, 0.5, 1]
MODEL_FIGURE_COLOR = (200, 204, 216)
MODEL_FIGURE_ALPHA = 0.1
MODEL_FIGURE_SPAN = 0.4    # the figure's width (hand to hand) per unit of height


def figure_mask(w, h):
    """A plain standing figure, w x h pixels, as an L image (255 inside): drawn four times larger, softened, scaled
    down. Coordinates are in figure heights: x from the centre line, y from the top of the head."""
    k = 4
    big_w, big_h = max(4, w * k), max(4, h * k)
    m = Image.new("L", (big_w, big_h), 0)
    d = ImageDraw.Draw(m)
    s = big_h * 0.98

    def p(x, y):
        return (big_w / 2 + x * s, big_h * 0.01 + y * s)

    def poly(points):
        d.polygon([p(x, y) for x, y in points], fill=255)

    def disc(x, y, rx, ry=None):
        cx, cy = p(x, y)
        ry = rx if ry is None else ry
        d.ellipse((cx - rx * s, cy - ry * s, cx + rx * s, cy + ry * s), fill=255)

    disc(0, 0.068, 0.048, 0.064)                                                         # head
    poly([(-0.024, 0.11), (0.024, 0.11), (0.03, 0.17), (-0.03, 0.17)])                    # neck
    poly([(-0.112, 0.178), (0.112, 0.178), (0.104, 0.29), (0.082, 0.44), (0.098, 0.52),
          (-0.098, 0.52), (-0.082, 0.44), (-0.104, 0.29)])                                 # torso and hips
    disc(0, 0.185, 0.1, 0.02)                                                             # the shoulder line
    for side in (-1, 1):
        disc(side * 0.122, 0.208, 0.03)                                                   # shoulder
        poly([(side * 0.098, 0.205), (side * 0.15, 0.205), (side * 0.17, 0.36), (side * 0.172, 0.52),
              (side * 0.146, 0.52), (side * 0.14, 0.37), (side * 0.118, 0.28)])            # arm
        disc(side * 0.159, 0.54, 0.018, 0.03)                                             # hand
        poly([(side * 0.006, 0.52), (side * 0.1, 0.52), (side * 0.092, 0.74), (side * 0.072, 0.95),
              (side * 0.028, 0.95), (side * 0.024, 0.74), (side * 0.006, 0.6)])             # leg
        disc(side * 0.054, 0.965, 0.034, 0.02)                                            # foot
    m = m.filter(ImageFilter.GaussianBlur(k * 0.8))
    return m.resize((max(1, w), max(1, h)), Image.LANCZOS)


def draw_figure(img, mask, x, y, w, h, alpha):
    """The faint figure, w x h pixels with its top-left at (x, y), brightest at the head; clipped by mask."""
    w, h = int(round(w)), int(round(h))
    if w < 4 or h < 8:
        return
    fade = Image.linear_gradient("L").resize((w, h)).point(lambda v: 255 - int(v * 0.5))
    a = ImageChops.multiply(figure_mask(w, h), fade).point(lambda v: int(v * MODEL_FIGURE_ALPHA * alpha))
    fig = Image.new("RGBA", (w, h), MODEL_FIGURE_COLOR + (0,))
    fig.putalpha(a)
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    layer.alpha_composite(fig, (int(round(x)), int(round(y))))
    layer.putalpha(ImageChops.multiply(layer.split()[3], mask))
    img.alpha_composite(layer)


def draw_model(img, it, fonts):
    """A Model / PlayerModel / DressUpModel frame (driver.lua's "Model" items): the faint figure and the caption."""
    L, R, T, B = it.get("L"), it.get("R"), it.get("T"), it.get("B")
    if None in (L, R, T, B) or R - L < 1 or B - T < 1:
        return
    ppu = it.get("ppu") or 1
    alpha = it.get("alpha", 1)
    W, H = img.size
    # everything stays inside the model's box (and its scroll frame's clip)
    cx0, cy0, cx1, cy1 = clip_box(it, W, H)
    box = (max(cx0, L), max(cy0, T), min(cx1, R), min(cy1, B))
    if box[2] - box[0] < 1 or box[3] - box[1] < 1:
        return
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rectangle([box[0], box[1], box[2] - 1, box[3] - 1], fill=255)
    bw, bh = R - L, B - T
    shows_player = it.get("otype") in ("DressUpModel", "TabardModel") or str(it.get("unit") or "").lower() == "player"

    # the caption: one line, else two, at 11; a box with a figure goes without it when even two lines do not fit
    font = "Fonts\\FRIZQT__.TTF"
    room = bw - 8 * ppu
    spacing = 2
    text, size = None, MODEL_CAPTION_SIZE
    while size >= 7:
        face = fonts.get(font, int(math.floor(size * ppu + 0.5)))
        if face.length(MODEL_CAPTION) <= room:
            text = MODEL_CAPTION
        elif max(face.length(s) for s in MODEL_CAPTION_LINES.split("\n")) <= room:
            text = MODEL_CAPTION_LINES
        if text or shows_player:
            break
        size -= 1
    lines = text.count("\n") + 1 if text else 0
    text_h = (lines * size + (lines - 1) * spacing) * ppu if text else 0

    tT, tB = T, B   # where the caption goes: the whole box, or the strip under the figure
    if shows_player:
        gap = 8 * ppu if text else 0
        fh = min(0.8 * bh, 0.88 * bh - text_h - gap)
        if fh < 0.5 * bh:   # too short for the caption under the figure: the figure alone, centred
            fh, text = 0.8 * bh, None
            text_h = gap = 0
        fh = min(fh, 0.8 * bw / MODEL_FIGURE_SPAN)
        fw = fh * MODEL_FIGURE_SPAN
        top = T + (bh - (fh + gap + text_h)) / 2
        draw_figure(img, mask, (L + R) / 2 - fw / 2, top, fw, fh, alpha)
        tT, tB = top + fh + gap, top + fh + gap + text_h
    if text:
        draw_text(img, {"text": text, "font": font, "size": size, "px": int(math.floor(size * ppu + 0.5)),
                        "wrapPx": None, "L": L, "R": R, "T": tT, "B": tB, "ppu": ppu, "color": MODEL_CAPTION_COLOR,
                        "justify": "CENTER", "justifyV": "MIDDLE", "spacing": spacing, "shadow": [1, -1],
                        "shadowColor": [0, 0, 0, 1], "flags": "", "alpha": alpha, "clip": list(box)}, fonts)


def background(kind, W, H, addon):
    if kind in ("flat", "", None):
        return Image.new("RGBA", (W, H), (58, 64, 70, 255))
    if kind == "black":
        return Image.new("RGBA", (W, H), (0, 0, 0, 255))
    if kind in ("ground", "air"):
        mp = Image.open(os.path.join(addon, "Art", "Royale", "IslandMap.tga")).convert("RGB")
        k = W / 1920.0
        if kind == "air":
            bg = mp.resize((int(2400 * k), int(2400 * k)), Image.BILINEAR).crop(
                (int(240 * k), int(700 * k), int(240 * k) + W, int(700 * k) + H)).filter(
                ImageFilter.GaussianBlur(3 * k))
        else:
            bg = mp.resize((int(5200 * k), int(5200 * k)), Image.BILINEAR).crop(
                (int(1900 * k), int(1900 * k), int(1900 * k) + W, int(1900 * k) + H)).filter(
                ImageFilter.GaussianBlur(6 * k))
            sky = Image.new("RGB", (W, H // 3), (150, 190, 220))
            grad = Image.linear_gradient("L").resize((W, H // 3)).point(lambda v: 255 - v)
            bg.paste(sky, (0, 0), grad)
        return bg.convert("RGBA")
    # an image file, scaled to cover the window
    src = Image.open(kind).convert("RGB")
    k = max(W / src.width, H / src.height)
    src = src.resize((int(src.width * k + 0.5), int(src.height * k + 0.5)), Image.BILINEAR)
    x0, y0 = (src.width - W) // 2, (src.height - H) // 2
    return src.crop((x0, y0, x0 + W, y0 + H)).convert("RGBA")


def draw(dump, out, art, fonts, opt):
    W, H = int(dump["w"]), int(dump["h"])
    img = background(opt.get("bg", "flat"), W, H, art.addon)
    # CFrameStrataNode: per strata and level, one batch per draw layer; inside a batch frame by frame
    items = sorted(dump["items"], key=lambda it: (it["strata"], it["level"], it["layer"], it.get("fidx", 0),
                                                  it["idx"]))
    canvas = np.asarray(img).astype(np.float32)[..., :3] / 255.0
    pending_np = True
    for it in items:
        if it["kind"] == "Texture":
            if not pending_np:
                canvas = np.asarray(img).astype(np.float32)[..., :3] / 255.0
                pending_np = True
            draw_texture(canvas, it, art, opt.get("missing", "skip"))
        else:
            if pending_np:
                img = Image.fromarray((np.clip(canvas, 0, 1) * 255 + 0.5).astype(np.uint8)).convert("RGBA")
                pending_np = False
            if it["kind"] == "Model":
                draw_model(img, it, fonts)
            else:
                draw_text(img, it, fonts)
    if pending_np:
        img = Image.fromarray((np.clip(canvas, 0, 1) * 255 + 0.5).astype(np.uint8)).convert("RGBA")
    if opt.get("crop"):
        x0, y0, x1, y1 = [int(v) for v in opt["crop"].split(",")]
        img = img.crop((x0, y0, x1, y1))
    if opt.get("scale") and float(opt["scale"]) != 1:
        k = float(opt["scale"])
        img = img.resize((max(1, int(img.width * k)), max(1, int(img.height * k))), Image.LANCZOS)
    img.convert("RGB").save(out)
    print("wrote", out)


def main():
    pos, opt, extra_fonts = parse_args(sys.argv[1:])
    if len(pos) < 3 or pos[0] not in ("measure", "draw"):
        print(__doc__)
        return 2
    mode, dump_path, out = pos[0], pos[1], pos[2]
    repo = opt.get("repo") or REPO
    addon = opt.get("addon") or os.path.join(repo, "Interface", "AddOns", "Bleakhold")
    art = Art(repo, addon, opt.get("stock") or None, opt.get("journal") or None)
    fonts = Fonts(addon, extra_fonts, float(opt["font-stretch"]) if opt.get("font-stretch") else None)
    with open(dump_path, encoding="utf-8") as fh:
        dump = json.load(fh)
    if mode == "measure":
        measure(dump, fonts, art, out)
        return 0
    for e in dump.get("errors") or []:
        print("addon error: " + e, file=sys.stderr)
    draw(dump, out, art, fonts, opt)
    if art.missing:
        print("missing %d texture file(s):" % len(art.missing), file=sys.stderr)
        for p in sorted(art.missing):
            print("  " + p, file=sys.stderr)
        if opt.get("strict") == "1":
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
