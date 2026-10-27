#!/usr/bin/env python3
"""Renders the Bleakhold Royale HUD art and writes it as BLP2 into Interface/AddOns/Bleakhold/Art/Royale.

Usage: python3 -I make_royale_art.py [--spec ../MapForge/specs/royale_v2.json] [--out DIR] [--preview DIR]
                                     [--skip-map]

Needs Pillow (pip install Pillow) for drawing and resampling; the BLP encoding is blpconvert.py next to this file.
Everything here is drawn by this script (no game data):

  Map.blp        512 x 512, the island map of the HUD (Royale.lua, RoyaleMap.lua). Built in memory from the
                 MapForge terrain spec (terrain/build.py, a few minutes): the terrain's texture colours,
                 shaded by the slope, the water, the buildings (WMOs) as dark footprints and the dressing as specks.
                 Unlike MapForge's preview.png it has no tile grid and none of the server's points (crate spots,
                 orbs, supply and final sites are never shown to players: docs/BleakholdProtocol.md section 17,
                 ROYM). North up, west left: pixel column u = (maxY - y) / (maxY - minY), row v = (maxX - x) /
                 (maxX - minX) over the map's tiles, the frame ROYM sends.
  MapThumb.blp   256 x 256, the same picture for the Activities card.
  Ring.blp, RingMid.blp, RingSmall.blp
                 white circle outlines (512, 128 and 32 pixels) for the storm circles: the client draws interface
                 textures with plain bilinear filtering and no mipmaps (Engine/Source/Frame/CSimpleRender.cpp,
                 s_textureFilterMode = GxTex_Linear), so a ring is drawn from the texture whose size is closest to
                 the size on screen, which keeps its line two to five pixels wide.
  Hole.blp, HoleSmall.blp
                 white outside a circle, clear inside (256 and 64): the storm's shade outside the circle.
  Arrow.blp      64 x 64 arrow pointing up (the player on the map, the way to the safe zone at the minimap).
  Pin.blp        64 x 64 map pin with its tip at the bottom centre (the landing pin).
  Vignette.blp   256 x 256, clear in the middle and white towards the edges (the purple screen edge outside the
                 storm circle; tinted by the addon).

--preview also writes each picture as PNG for checking.
"""

import argparse
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True  # keep the repository free of __pycache__

import blpconvert as bc  # noqa: E402

try:
    from PIL import Image, ImageDraw, ImageFilter
except ImportError:
    raise SystemExit("make_royale_art.py needs Pillow: pip install Pillow")

REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
MAPFORGE = os.path.join(REPO, "Tools", "MapForge")
OUT = os.path.join(REPO, "Interface", "AddOns", "Bleakhold", "Art", "Royale")
SPEC = os.path.join(MAPFORGE, "specs", "royale_v2.json")  # the current map (v1: specs/royale_v1.json)
SS = 4  # supersampling for anti-aliased shapes


def to_blp(img, path, fmt):
    """Writes a Pillow image as one-level BLP2 (interface textures use only the top level)."""
    rgba = img.convert("RGBA")
    pic = bc.Image(rgba.width, rgba.height, bytearray(rgba.tobytes()))
    bc.convert(pic, path, fmt=fmt, mips=False, jobs=1)


# ---------------------------------------------------------------------------------------------- the island map

def render_map(spec_path):
    """The terrain of the MapForge spec at one pixel per lattice point (north up, west left), RGB."""
    sys.path.insert(0, MAPFORGE)
    from terrain import coords
    from terrain.build import build
    from terrain.spec import load_spec

    result = build(load_spec(spec_path))
    ctx = result.context
    spec = ctx.spec
    grid = ctx.grid
    per_tile = coords.LATTICE_PER_TILE
    width = (spec.tx1 - spec.tx0 + 1) * per_tile + 1
    height = (spec.ty1 - spec.ty0 + 1) * per_tile + 1
    r_base = spec.ty0 * per_tile
    c_base = spec.tx0 * per_tile

    color = [[(0.0, 0.0, 0.0)] * width for _ in range(height)]
    wet = [[False] * width for _ in range(height)]
    for (tx, ty), res in result.tiles.items():
        for (ix, iy), tex in res.texturing.items():
            r0 = (ty * 16 + iy) * 16 - r_base
            c0 = (tx * 16 + ix) * 16 - c_base
            cols = [spec.textures[k].color for k in tex.layers]
            for r in range(17):
                line = color[r0 + r]
                for c in range(17):
                    p = r * 17 + c
                    red = green = blue = 0.0
                    for li, col in enumerate(cols):
                        w = tex.weights[li][p]
                        red += w * col[0]
                        green += w * col[1]
                        blue += w * col[2]
                    line[c0 + c] = (red, green, blue)
        for (ix, iy), cw in res.water.items():
            r0 = (ty * 16 + iy) * 16 - r_base
            c0 = (tx * 16 + ix) * 16 - c_base
            for (cx, cy) in cw.exists:
                for r in range(2 * cy, 2 * cy + 3):
                    for c in range(2 * cx, 2 * cx + 3):
                        if grid.get(r_base + r0 + r, c_base + c0 + c) < cw.height:
                            wet[r0 + r][c0 + c] = True

    # light from the north-west, a little stronger relief than MapForge's preview; muted colours so the HUD's
    # markers stand out
    lx, ly, lz = 0.55, 0.55, 0.63
    img = Image.new("RGB", (width, height))
    px = img.load()
    for r in range(height):
        for c in range(width):
            nx, ny, nz = grid.normal(r_base + r, c_base + c)
            shade = 0.35 + 0.85 * max(0.0, nx * lx + ny * ly + nz * lz)
            red, green, blue = color[r][c]
            if wet[r][c]:
                red, green, blue = red * 0.25 + 28, green * 0.25 + 70, blue * 0.25 + 120
                shade = 0.9 + 0.1 * shade
            grey = (red + green + blue) / 3.0
            red, green, blue = (grey + (v - grey) * 0.8 for v in (red, green, blue))
            px[c, r] = tuple(max(0, min(255, int(v * shade * 0.92 + 0.5))) for v in (red, green, blue))

    # buildings and dressing (never the server's points: those are not placements)
    over = Image.new("RGBA", (width * SS, height * SS), (0, 0, 0, 0))
    draw = ImageDraw.Draw(over)
    scale = 12.0 / 25.0  # lattice points per yard

    def at(x, y):
        u, v = coords.world_to_lattice(x, y)
        return (v - c_base) * SS, (u - r_base) * SS

    scattered = {p.label for p in getattr(ctx, "scattered", [])}
    for d in ctx.doodads:
        cx, cy = at(d.world[0], d.world[1])
        if d.label in scattered:
            rad = 1.1 * SS
            draw.ellipse((cx - rad, cy - rad, cx + rad, cy + rad), fill=(18, 26, 14, 110))
        else:
            rad = 0.9 * SS
            draw.ellipse((cx - rad, cy - rad, cx + rad, cy + rad), fill=(44, 34, 24, 150))
    for w in ctx.wmos:
        cx, cy = at(w.world[0], w.world[1])
        rad = max(2.0, min(18.0, (getattr(w, "radius", 8.0) or 8.0) * scale * 0.55)) * SS
        draw.ellipse((cx - rad - SS, cy - rad - SS, cx + rad + SS, cy + rad + SS), fill=(12, 10, 9, 90))
        draw.ellipse((cx - rad, cy - rad, cx + rad, cy + rad), fill=(52, 46, 40, 215))
    over = over.resize((width, height), Image.LANCZOS)
    img = Image.alpha_composite(img.convert("RGBA"), over).convert("RGB")
    return img


def finish_map(img, size):
    out = img.resize((size, size), Image.LANCZOS)
    out = out.filter(ImageFilter.UnsharpMask(radius=1.2, percent=60, threshold=2))
    # a soft dark rim, so the picture sits in the frame
    rim = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(rim)
    edge = max(4, size // 40)
    for i in range(edge):
        a = int(150 * (1 - i / edge) ** 2)
        d.rectangle((i, i, size - 1 - i, size - 1 - i), outline=a)
    dark = Image.new("RGB", (size, size), (8, 8, 10))
    return Image.composite(dark, out, rim)


# ---------------------------------------------------------------------------------------------- shapes

def ring(size, line):
    """White anti-aliased circle outline of `line` pixels touching the texture's edges (1 pixel margin)."""
    big = size * SS
    img = Image.new("L", (big, big), 0)
    d = ImageDraw.Draw(img)
    outer = big / 2 - SS
    inner = outer - line * SS
    c = big / 2
    d.ellipse((c - outer, c - outer, c + outer, c + outer), fill=255)
    d.ellipse((c - inner, c - inner, c + inner, c + inner), fill=0)
    alpha = img.resize((size, size), Image.LANCZOS)
    out = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    out.putalpha(alpha)
    return out


def hole(size, soft):
    """White outside a circle that touches the edges, clear inside, with a soft edge of `soft` pixels."""
    out = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    alpha = Image.new("L", (size, size), 0)
    px = alpha.load()
    c = (size - 1) / 2.0
    radius = size / 2.0 - 1.0
    for y in range(size):
        for x in range(size):
            dist = math.hypot(x - c, y - c)
            t = (dist - (radius - soft)) / soft
            t = max(0.0, min(1.0, t))
            px[x, y] = int(255 * (t * t * (3 - 2 * t)) + 0.5)
    out.putalpha(alpha)
    return out


def arrow(size):
    """An arrow pointing up: white body, dark soft outline. It stays inside the inscribed circle, so the addon can
    turn it (Texture:SetRotation turns the texture coordinates inside the square) without cutting its tips."""
    big = size * SS
    body = [(0.5, 0.08), (0.8, 0.84), (0.5, 0.67), (0.2, 0.84)]
    pts = [(x * big, y * big) for x, y in body]
    shape = Image.new("L", (big, big), 0)
    ImageDraw.Draw(shape).polygon(pts, fill=255)
    outline = shape.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.GaussianBlur(SS))
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    img.paste((10, 10, 12, 200), (0, 0), outline)
    img.paste((255, 255, 255, 255), (0, 0), shape)
    return img.resize((size, size), Image.LANCZOS)


def pin(size):
    """A map pin: a round head with a hole and a point at the bottom centre."""
    big = size * SS
    cx, head_y, rad = big / 2, big * 0.36, big * 0.27
    shape = Image.new("L", (big, big), 0)
    d = ImageDraw.Draw(shape)
    d.ellipse((cx - rad, head_y - rad, cx + rad, head_y + rad), fill=255)
    shoulder = head_y + rad * 0.55
    d.polygon([(cx - rad * 0.82, shoulder), (cx + rad * 0.82, shoulder), (cx, big - SS * 2)], fill=255)
    inner = rad * 0.38
    d.ellipse((cx - inner, head_y - inner, cx + inner, head_y + inner), fill=0)
    outline = shape.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.GaussianBlur(SS))
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    img.paste((10, 10, 12, 190), (0, 0), outline)
    img.paste((255, 255, 255, 255), (0, 0), shape)
    return img.resize((size, size), Image.LANCZOS)


def vignette(size):
    """Clear in the middle, white at the edges (a rounded-rectangle falloff, strongest in the corners)."""
    out = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    alpha = Image.new("L", (size, size), 0)
    px = alpha.load()
    c = (size - 1) / 2.0
    for y in range(size):
        for x in range(size):
            dx, dy = abs(x - c) / c, abs(y - c) / c
            d = (dx ** 4 + dy ** 4) ** 0.25
            t = max(0.0, min(1.0, (d - 0.62) / 0.38))
            px[x, y] = int(235 * t * t + 0.5)
    out.putalpha(alpha)
    return out


# ---------------------------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="Write the Bleakhold Royale HUD art as BLP2.")
    ap.add_argument("--spec", default=SPEC, help="MapForge terrain spec of the Royale map")
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--preview", help="also write PNG copies here")
    ap.add_argument("--skip-map", action="store_true", help="only the shapes (the map takes a few minutes)")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    pics = []
    if not a.skip_map:
        base = render_map(a.spec)
        pics.append(("Map", finish_map(base, 512), "dxt1"))
        pics.append(("MapThumb", finish_map(base, 256), "dxt1"))
    pics += [
        ("Ring", ring(512, 3), "dxt5"),
        ("RingMid", ring(128, 3), "dxt5"),
        ("RingSmall", ring(32, 2), "dxt5"),
        ("Hole", hole(256, 3.0), "dxt5"),
        ("HoleSmall", hole(64, 1.5), "dxt5"),
        ("Arrow", arrow(64), "dxt5"),
        ("Pin", pin(64), "dxt5"),
        ("Vignette", vignette(256), "dxt5"),
    ]
    for name, img, fmt in pics:
        path = os.path.join(a.out, name + ".blp")
        to_blp(img, path, fmt)
        if a.preview:
            os.makedirs(a.preview, exist_ok=True)
            img.save(os.path.join(a.preview, name + ".png"))
        print("wrote %s (%d x %d, %s)" % (os.path.relpath(path, REPO), img.width, img.height, fmt))


if __name__ == "__main__":
    main()
