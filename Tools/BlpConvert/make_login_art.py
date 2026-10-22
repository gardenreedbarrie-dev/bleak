#!/usr/bin/env python3
"""Renders the Bleakhold login-screen art and writes it as BLP2 into Interface/Bleakhold/Glue/Textures.

Usage: python3 make_login_art.py [--background art/LoginBackground.jpg] [--out DIR] [--preview DIR]

Needs Pillow (pip install Pillow) for the JPEG, the font rendering and the blurs; the BLP encoding is
blpconvert.py next to this file. The art follows the owner's design boards (Main: 1920x1080 login
screen, Kit: field, button, checkbox and dialog states). Every piece is drawn at twice the 1080p
design size (four times for the checkbox), so it stays sharp at 4K; the client scales it down.

The atlas cell geometry here is mirrored by BleakholdGlueCore.lua (BleakholdGlue.ART); change both
together. --preview also writes each atlas as PNG for checking.
"""

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True  # keep the repository free of __pycache__

import blpconvert as bc  # noqa: E402

try:
    from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont
except ImportError:
    raise SystemExit("make_login_art.py needs Pillow: pip install Pillow")

REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
GLUE = os.path.join(REPO, "Interface", "Bleakhold", "Glue")
FONT_REGULAR = os.path.join(GLUE, "Fonts", "Marcellus-Regular.ttf")
FONT_SC = os.path.join(GLUE, "Fonts", "MarcellusSC-Regular.ttf")
SS = 4  # supersampling for anti-aliased polygons


def rgb(hexstr, alpha=255):
    hexstr = hexstr.lstrip("#")
    return (int(hexstr[0:2], 16), int(hexstr[2:4], 16), int(hexstr[4:6], 16), alpha)


def lerp(a, b, t):
    return tuple(int(round(x + (y - x) * t)) for x, y in zip(a, b))


def gradient_v(w, h, stops, y0=0, span=None):
    """Vertical gradient image; stops are (position 0..1, colour) over rows y0..y0+span."""
    span = span or h
    img = Image.new("RGBA", (w, h))
    draw = ImageDraw.Draw(img)
    for y in range(h):
        t = min(1.0, max(0.0, (y - y0 + 0.5) / span))
        for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
            if p0 <= t <= p1:
                colour = lerp(c0, c1, 0.0 if p1 == p0 else (t - p0) / (p1 - p0))
                break
        else:
            colour = stops[-1][1] if t > stops[-1][0] else stops[0][1]
        draw.line([(0, y), (w, y)], fill=colour)
    return img


def gradient_h_centre(w, h, colour, alpha):
    """Horizontal band: transparent at both ends, `colour` at `alpha` in the middle (CSS 0%-50%-100%)."""
    img = Image.new("RGBA", (w, h))
    draw = ImageDraw.Draw(img)
    for x in range(w):
        t = 1.0 - abs((x + 0.5) / w * 2.0 - 1.0)
        draw.line([(x, 0), (x, h)], fill=colour[:3] + (int(round(alpha * t)),))
    return img


def hexagon(x, y, w, h, chamfer):
    """The design's clip-path polygon: chamfered left and right points, flat top and bottom."""
    return [(x + chamfer, y), (x + w - chamfer, y), (x + w, y + h / 2.0), (x + w - chamfer, y + h),
            (x + chamfer, y + h), (x, y + h / 2.0)]


def octagon(x, y, w, h, c):
    return [(x + c, y), (x + w - c, y), (x + w, y + c), (x + w, y + h - c), (x + w - c, y + h),
            (x + c, y + h), (x, y + h - c), (x, y + c)]


def mask_polygon(size, points):
    w, h = size
    big = Image.new("L", (w * SS, h * SS), 0)
    ImageDraw.Draw(big).polygon([(px * SS, py * SS) for px, py in points], fill=255)
    return big.resize((w, h), Image.LANCZOS)


def paint(canvas, fill, mask):
    """Composites `fill` (RGBA, canvas-sized) onto canvas through the coverage mask (L)."""
    layer = fill.copy()
    layer.putalpha(ImageChops.multiply(fill.getchannel("A"), mask))
    return Image.alpha_composite(canvas, layer)


def shadow(size, mask, dx, dy, sigma, colour):
    """CSS drop-shadow: the shape's silhouette moved, blurred and tinted."""
    m = Image.new("L", size, 0)
    m.paste(mask, (int(round(dx)), int(round(dy))))
    if sigma > 0:
        m = m.filter(ImageFilter.GaussianBlur(sigma))
    layer = Image.new("RGBA", size, colour[:3] + (0,))
    layer.putalpha(Image.eval(m, lambda v: v * colour[3] // 255))
    return layer


# ------------------------------------------------------------------------------------------- pieces

def draw_field(focused, k=2):
    """One edit-field cell region: 960x180 texels = the 440x50 design field plus 20 px around it."""
    margin = 20 * k
    W, H = 440 * k, 50 * k
    size = (W + 2 * margin, H + 2 * margin)
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    outer = hexagon(margin, margin, W, H, 17 * k)
    inner = hexagon(margin + 2 * k, margin + 2 * k, W - 4 * k, H - 4 * k, 16 * k)
    m_outer = mask_polygon(size, outer)
    m_inner = mask_polygon(size, inner)
    canvas = Image.alpha_composite(canvas, shadow(size, m_outer, 0, 3 * k, 1.5 * k, rgb("#000000", 230)))
    if focused:
        brass = [(0, rgb("#ffe2a0")), (0.40, rgb("#c9934a")), (0.72, rgb("#6e4a22")), (1, rgb("#3a2410"))]
    else:
        brass = [(0, rgb("#c79a5a")), (0.40, rgb("#8a6334")), (0.72, rgb("#4a321a")), (1, rgb("#24170b"))]
    canvas = paint(canvas, gradient_v(size[0], size[1], brass, margin, H), m_outer)
    well = [(0, rgb("#050302")), (0.55, rgb("#110c09")), (1, rgb("#1d140e"))]
    canvas = paint(canvas, gradient_v(size[0], size[1], well, margin + 2 * k, H - 4 * k), m_inner)
    # Underline: 30 px in from each side of the well, on its bottom edge.
    line_h = (2 if focused else 1) * k
    band_w = W - 4 * k - 60 * k
    band = gradient_h_centre(band_w, line_h, rgb("#ff7a2e"), 255 if focused else 71)
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    layer.paste(band, (margin + 2 * k + 30 * k, margin + H - 2 * k - line_h))
    canvas = Image.alpha_composite(canvas, layer)
    return canvas


def draw_field_glow(k=2):
    margin = 20 * k
    W, H = 440 * k, 50 * k
    size = (W + 2 * margin, H + 2 * margin)
    m_outer = mask_polygon(size, hexagon(margin, margin, W, H, 17 * k))
    return shadow(size, m_outer, 0, 0, 4.5 * k, rgb("#ff7a2e", 115))


PRIMARY_STATES = {
    "normal": dict(border=[(0, "#ffe2a0"), (0.42, "#c9934a"), (0.75, "#6e4a22"), (1, "#3a2410")],
                   fill=[(0, "#c2421c"), (0.34, "#8c200c"), (0.70, "#5e1206"), (1, "#3a0a03")],
                   shadow=(4, 4), glow=None),
    "hover": dict(border=[(0, "#fff0c4"), (0.42, "#e0aa5c"), (0.75, "#8a5e2c"), (1, "#4a2e14")],
                  fill=[(0, "#e0582a"), (0.34, "#a82a10"), (0.70, "#721808"), (1, "#460c04")],
                  shadow=(4, 4), glow=(10, rgb("#ff7832", 128))),
    "pressed": dict(border=[(0, "#3a2410"), (0.30, "#6e4a22"), (0.70, "#c9934a"), (1, "#ffe2a0")],
                    fill=[(0, "#2c0702"), (0.40, "#4e0e05"), (1, "#7a1a0b")],
                    shadow=(2, 2), glow=None),
    "disabled": dict(border=[(0, "#8a8070"), (0.50, "#5a5246"), (1, "#2e2a24")],
                     fill=[(0, "#3e3832"), (0.60, "#2a2520"), (1, "#1c1915")],
                     shadow=(4, 4), glow=None),
}


def draw_primary(state, k=2):
    """Primary (Login) button region: 648x216 texels = the 276x60 design button plus 24 px around it."""
    spec = PRIMARY_STATES[state]
    margin = 24 * k
    W, H = 276 * k, 60 * k
    size = (W + 2 * margin, H + 2 * margin)
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    m_outer = mask_polygon(size, hexagon(margin, margin, W, H, 20 * k))
    m_inner = mask_polygon(size, hexagon(margin + 2 * k, margin + 2 * k, W - 4 * k, H - 4 * k, 19 * k))
    if spec["glow"]:
        blur, colour = spec["glow"]
        canvas = Image.alpha_composite(canvas, shadow(size, m_outer, 0, 0, blur / 2.0 * k, colour))
    dy, blur = spec["shadow"]
    canvas = Image.alpha_composite(canvas, shadow(size, m_outer, 0, dy * k, blur / 2.0 * k, rgb("#000000", 230)))
    border = [(p, rgb(c)) for p, c in spec["border"]]
    fill = [(p, rgb(c)) for p, c in spec["fill"]]
    canvas = paint(canvas, gradient_v(size[0], size[1], border, margin, H), m_outer)
    canvas = paint(canvas, gradient_v(size[0], size[1], fill, margin + 2 * k, H - 4 * k), m_inner)
    return canvas


MENU_STATES = {
    "normal": dict(border=[(0, "#b8894c"), (1, "#4a3420")], fill=[(0, "#3d2e23"), (0.55, "#241a13"), (1, "#150f0b")]),
    "hover": dict(border=[(0, "#ffe2a0"), (1, "#8a6334")], fill=[(0, "#54402f"), (0.55, "#33251b"), (1, "#1e1610")]),
    "pressed": dict(border=[(0, "#4a3420"), (1, "#b8894c")], fill=[(0, "#0e0a07"), (0.60, "#1c140f"), (1, "#2c2119")]),
}


def draw_menu(state, inner_width, k=2):
    """Menu button region: the (inner_width + 2) x 44 design button plus 2 px around it."""
    spec = MENU_STATES[state]
    margin = 2 * k
    W, H = (inner_width + 2) * k, 44 * k
    size = (W + 2 * margin, H + 2 * margin)
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    m_outer = mask_polygon(size, hexagon(margin, margin, W, H, 12 * k))
    m_inner = mask_polygon(size, hexagon(margin + k, margin + k, W - 2 * k, H - 2 * k, 11 * k))
    border = [(p, rgb(c)) for p, c in spec["border"]]
    fill = [(p, rgb(c)) for p, c in spec["fill"]]
    canvas = paint(canvas, gradient_v(size[0], size[1], border, margin, H), m_outer)
    canvas = paint(canvas, gradient_v(size[0], size[1], fill, margin + k, H - 2 * k), m_inner)
    return canvas


def draw_checkbox(part, k=4):
    """Checkbox region: the 22x22 design box plus 3 px around it (112x112 texels)."""
    margin = 3 * k
    S = 22 * k
    size = (S + 2 * margin, S + 2 * margin)
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    o = margin
    if part == "box":
        draw.rectangle([o, o, o + S - 1, o + S - 1], fill=rgb("#b8894c"))
        canvas = paint(canvas, gradient_v(size[0], size[1], [(0, rgb("#050302")), (1, rgb("#1a120c"))], o + k, S - 2 * k),
                       mask_polygon(size, [(o + k, o + k), (o + S - k, o + k), (o + S - k, o + S - k), (o + k, o + S - k)]))
        ring = ImageDraw.Draw(canvas)
        ring.rectangle([o + k, o + k, o + S - k - 1, o + S - k - 1], outline=rgb("#000000"), width=k)
    elif part == "hover":
        # Drawn over the box and the check (highlight layer), so only a bright rim and an ember glow: the
        # inside stays clear.
        outer = mask_polygon(size, [(o, o), (o + S, o), (o + S, o + S), (o, o + S)])
        inner = mask_polygon(size, [(o + k, o + k), (o + S - k, o + k), (o + S - k, o + S - k), (o + k, o + S - k)])
        glow = shadow(size, outer, 0, 0, 1.5 * k, rgb("#ff7a2e", 140))
        glow.putalpha(ImageChops.subtract(glow.getchannel("A"), outer))
        canvas = Image.alpha_composite(canvas, glow)
        rim = Image.new("RGBA", size, rgb("#ffe2a0"))
        rim.putalpha(ImageChops.subtract(outer, inner))
        canvas = Image.alpha_composite(canvas, rim)
    elif part == "check":
        # M5 11.5 l4 4 8-9, stroke 2.4, square caps (an inset on the 22-unit box).
        big = Image.new("L", (size[0] * SS, size[1] * SS), 0)
        d = ImageDraw.Draw(big)
        pts = [(5, 11.5), (9, 15.5), (17, 6.5)]
        pts = [((o + x * k) * SS, (o + y * k) * SS) for x, y in pts]
        width = int(2.4 * k * SS)
        d.line(pts, fill=255, width=width, joint="curve")
        for px, py in (pts[0], pts[-1]):
            r = width / 2.0
            d.rectangle([px - r, py - r, px + r, py + r], fill=255)
        mask = big.resize(size, Image.LANCZOS)
        canvas = Image.alpha_composite(canvas, shadow(size, mask, 0, k, k, rgb("#000000", 200)))
        layer = Image.new("RGBA", size, rgb("#ffd100"))
        layer.putalpha(mask)
        canvas = Image.alpha_composite(canvas, layer)
    return canvas


def draw_dialog(k=2):
    """9-slice source: a 192x192 design dialog (octagon, 18 px chamfer, 2 px brass border) centred in
    512x512 texels; the 64-texel margin holds the drop shadow."""
    size = (512, 512)
    margin = 64
    B = 384
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    m_outer = mask_polygon(size, octagon(margin, margin, B, B, 18 * k))
    m_inner = mask_polygon(size, octagon(margin + 2 * k, margin + 2 * k, B - 4 * k, B - 4 * k, 17 * k))
    canvas = Image.alpha_composite(canvas, shadow(size, m_outer, 0, 8 * k, 7 * k, rgb("#000000", 230)))
    border = [(0, rgb("#ffe2a0")), (0.30, rgb("#b8894c")), (1, rgb("#5a3e1e"))]
    canvas = paint(canvas, gradient_v(size[0], size[1], border, margin, B), m_outer)
    canvas = paint(canvas, gradient_v(size[0], size[1], [(0, rgb("#221913")), (1, rgb("#120d0a"))], margin + 2 * k, B - 4 * k), m_inner)
    return canvas


def draw_logo(k=2):
    """'Bleakhold' as on the Main board: Marcellus SC 110 px, letter-spacing 3, metal gradient fill over
    a 3 px #1b0e06 stroke (paint-order stroke), drop shadow 0 4 6 at 0.85. The texture is 2048x512
    texels = the design area from 16 px left of and above the 760x132 logo box."""
    size = (2048, 512)
    origin = 16 * k
    font = ImageFont.truetype(FONT_SC, 110 * k)
    text = "Bleakhold"
    x = origin + 4 * k
    baseline = origin + 104 * k
    fill_mask = Image.new("L", size, 0)
    stroke_mask = Image.new("L", size, 0)
    df, ds = ImageDraw.Draw(fill_mask), ImageDraw.Draw(stroke_mask)
    for ch in text:
        df.text((x, baseline), ch, font=font, fill=255, anchor="ls")
        ds.text((x, baseline), ch, font=font, fill=255, anchor="ls", stroke_width=int(1.5 * k), stroke_fill=255)
        x += font.getlength(ch) + 3 * k
    bbox = fill_mask.getbbox()
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    canvas = Image.alpha_composite(canvas, shadow(size, stroke_mask, 0, 4 * k, 3 * k, rgb("#000000", 217)))
    stroke = Image.new("RGBA", size, rgb("#1b0e06"))
    canvas = paint(canvas, stroke, stroke_mask)
    metal = [(0, rgb("#fff3cf")), (0.38, rgb("#e2b768")), (0.52, rgb("#8a5a26")), (0.70, rgb("#c58d45")), (1, rgb("#5c3815"))]
    canvas = paint(canvas, gradient_v(size[0], size[1], metal, bbox[1], bbox[3] - bbox[1]), fill_mask)
    return canvas, x


def atlas(width, height, cells):
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    for piece, (x, y) in cells:
        img.alpha_composite(piece, (x, y))
    return img


def to_blp(img, path, fmt):
    bc.convert(bc.Image(img.size[0], img.size[1], bytearray(img.tobytes())), path, fmt)
    print("wrote %s (%dx%d %s)" % (os.path.relpath(path, REPO), img.size[0], img.size[1], fmt))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--background", default=os.path.join(HERE, "art", "LoginBackground.jpg"))
    ap.add_argument("--out", default=os.path.join(GLUE, "Textures"))
    ap.add_argument("--preview", help="also write PNG previews here")
    ap.add_argument("--only", help="comma-separated subset: background,logo,field,primary,menu,checkbox,dialog")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    only = set(args.only.split(",")) if args.only else None
    outputs = []

    def want(name):
        return only is None or name in only

    if want("background"):
        # 1920x1080 painting stretched into 2048x1024; the Lua maps it back to 16:9 with texcoords.
        with Image.open(args.background) as im:
            bg = im.convert("RGBA").resize((2048, 1024), Image.LANCZOS)
        outputs.append(("LoginBackground", bg, "dxt1"))
    if want("logo"):
        logo, _ = draw_logo()
        outputs.append(("LoginLogo", logo, "dxt5"))
    if want("field"):
        # 1024x1024: rows of 256, region 960x180 at (32, 38): idle, focused, ember glow.
        cells = [(draw_field(False), (32, 38)), (draw_field(True), (32, 256 + 38)), (draw_field_glow(), (32, 512 + 38))]
        outputs.append(("LoginField", atlas(1024, 1024, cells), "dxt5"))
    if want("primary"):
        # 1024x1024: rows of 256, region 648x216 at (188, 20): normal, hover, pressed, disabled.
        cells = [(draw_primary(s), (188, 256 * i + 20)) for i, s in enumerate(("normal", "hover", "pressed", "disabled"))]
        outputs.append(("LoginButtonPrimary", atlas(1024, 1024, cells), "dxt5"))
    if want("menu"):
        # 1024x512: rows of 128 (normal, hover, pressed); column 0 the 228-wide button (region 468x96 at
        # (22, 16)), column 1 the 200-wide one (region 412x96 at (512 + 50, 16)).
        cells = []
        for i, s in enumerate(("normal", "hover", "pressed")):
            cells.append((draw_menu(s, 228), (22, 128 * i + 16)))
            cells.append((draw_menu(s, 200), (512 + 50, 128 * i + 16)))
        outputs.append(("LoginButtonMenu", atlas(1024, 512, cells), "dxt5"))
    if want("checkbox"):
        # 512x128: cells of 128, region 112x112 at (8, 8): box, check, hover box.
        cells = [(draw_checkbox(p), (128 * i + 8, 8)) for i, p in enumerate(("box", "check", "hover"))]
        outputs.append(("LoginCheckBox", atlas(512, 128, cells), "dxt5"))
    if want("dialog"):
        outputs.append(("LoginDialog", draw_dialog(), "dxt5"))

    for name, img, fmt in outputs:
        if args.preview:
            os.makedirs(args.preview, exist_ok=True)
            img.save(os.path.join(args.preview, name + ".png"))
        to_blp(img, os.path.join(args.out, name + ".blp"), fmt)


if __name__ == "__main__":
    main()
