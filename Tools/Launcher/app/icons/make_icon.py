#!/usr/bin/env python3
"""Draws the Bleakhold Launcher icon: a gold "B" in Marcellus SC on a dark disc with a gold ring, in the
Bleakhold palette (gold C9A25A/E5C07B, dark 0B0C0F/15181D). Original art only.

Writes, next to this script:
  icon.ico      16-256 px (the exe's icon and the window icon on Windows; tauri-build reads it)
  icon.png      512 px (the window icon elsewhere)
  32x32.png, 128x128.png, 128x128@2x.png

Usage: python3 make_icon.py   (needs Pillow)
"""

import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
FONT = REPO / "Interface" / "Bleakhold" / "Glue" / "Fonts" / "MarcellusSC-Regular.ttf"

GOLD = (0xC9, 0xA2, 0x5A)
GOLD_LIGHT = (0xE5, 0xC0, 0x7B)
GOLD_DEEP = (0x8A, 0x68, 0x32)
DARK = (0x0B, 0x0C, 0x0F)
DARK_LIGHT = (0x15, 0x18, 0x1D)

S = 1024  # master size; every output is downscaled from it


def lerp(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def vertical_gradient(size, stops):
    """An RGB image whose rows blend through (position, colour) stops."""
    w, h = size
    col = Image.new("RGB", (1, h))
    for y in range(h):
        t = y / max(1, h - 1)
        c = stops[-1][1]
        if t <= stops[0][0]:
            c = stops[0][1]
        for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
            if t0 <= t <= t1:
                c = lerp(c0, c1, (t - t0) / max(1e-9, t1 - t0))
                break
        col.putpixel((0, y), c)
    return col.resize((w, h), Image.NEAREST)


def radial_disc(size, inner, outer):
    """A soft radial blend from `inner` (upper left) to `outer`, drawn small and scaled up."""
    n = 128
    img = Image.new("RGB", (n, n), outer)
    px = img.load()
    cx, cy, r = n * 0.42, n * 0.36, n * 0.75
    for y in range(n):
        for x in range(n):
            d = min(1.0, ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 / r)
            px[x, y] = lerp(inner, outer, d)
    return img.resize(size, Image.BICUBIC)


def circle_mask(size, inset):
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).ellipse((inset, inset, size - 1 - inset, size - 1 - inset), fill=255)
    return m


def master():
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    # Dark disc.
    disc = radial_disc((S, S), DARK_LIGHT, DARK).convert("RGBA")
    img.paste(disc, (0, 0), circle_mask(S, 8))

    # Gold ring: outer edge minus inner edge, with a light-to-deep gradient.
    ring = ImageChops.subtract(circle_mask(S, 22), circle_mask(S, 74))
    ring_fill = vertical_gradient((S, S), [(0.0, GOLD_LIGHT), (0.5, GOLD), (1.0, GOLD_DEEP)])
    img.paste(ring_fill.convert("RGBA"), (0, 0), ring)
    # Thin inner line for depth.
    hair = ImageChops.subtract(circle_mask(S, 98), circle_mask(S, 108))
    img.paste(Image.new("RGBA", (S, S), GOLD_DEEP + (255,)), (0, 0), hair)

    # The letter.
    font = ImageFont.truetype(str(FONT), int(S * 0.68))
    glyph = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(glyph)
    box = d.textbbox((0, 0), "B", font=font)
    gw, gh = box[2] - box[0], box[3] - box[1]
    d.text(((S - gw) / 2 - box[0], (S - gh) / 2 - box[1] + S * 0.01), "B", font=font, fill=255)
    # Slightly heavier strokes so the letter survives 16 px.
    glyph = glyph.filter(ImageFilter.MaxFilter(9))

    shadow = glyph.filter(ImageFilter.GaussianBlur(S * 0.02))
    img.paste(Image.new("RGBA", (S, S), (0, 0, 0, 200)), (int(S * 0.008), int(S * 0.016)), shadow)
    letter = vertical_gradient((S, S), [(0.2, GOLD_LIGHT), (0.55, GOLD), (0.85, GOLD_DEEP)])
    img.paste(letter.convert("RGBA"), (0, 0), glyph)
    return img


def sized(img, n):
    out = img.resize((n, n), Image.LANCZOS)
    if n <= 32:
        out = out.filter(ImageFilter.UnsharpMask(radius=1, percent=60, threshold=0))
    return out


def main():
    if not FONT.is_file():
        sys.exit(f"font not found: {FONT}")
    m = master()
    sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    frames = {n: sized(m, n) for n in sizes}
    frames[256].save(HERE / "icon.ico", format="ICO", sizes=[(n, n) for n in sizes],
                     append_images=[frames[n] for n in sizes if n != 256])
    sized(m, 512).save(HERE / "icon.png", optimize=True)
    frames[32].save(HERE / "32x32.png", optimize=True)
    frames[128].save(HERE / "128x128.png", optimize=True)
    frames[256].save(HERE / "128x128@2x.png", optimize=True)
    print("wrote", ", ".join(p.name for p in sorted(HERE.glob("*.ico")) + sorted(HERE.glob("*.png"))))


if __name__ == "__main__":
    main()
