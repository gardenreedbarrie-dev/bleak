"""Puts preview PNGs (and reference screenshots) on one labelled sheet, for side-by-side review.

    python3 -I sheet.py out.png [--cols N] [--scale F] [--title TEXT] [--gap PX] IMAGE[@X0,Y0,X1,Y1][=LABEL] ...

Each IMAGE may carry its own crop (@x0,y0,x1,y1, pixels of that image) and label (=text; default: the file name).
--scale resizes every tile by F after its crop (zoom in on details with F > 1); tiles fill rows of --cols (default
1) in order, each row as tall as its tallest tile.
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = os.path.join(HERE, "..", "..", "..", "Interface", "AddOns", "Bleakhold", "Fonts", "Marcellus-Regular.ttf")


def parse(argv):
    opt = {"cols": 1, "scale": 1.0, "title": "", "gap": 12}
    tiles, out = [], None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--cols", "--scale", "--title", "--gap"):
            opt[a[2:]] = argv[i + 1]
            i += 2
            continue
        if out is None:
            out = a
        else:
            path, label = a, None
            if "=" in path:
                path, label = path.split("=", 1)
            crop = None
            if "@" in path:
                path, box = path.rsplit("@", 1)
                crop = tuple(int(v) for v in box.split(","))
            tiles.append((path, crop, label if label is not None else os.path.splitext(os.path.basename(path))[0]))
        i += 1
    return out, tiles, int(opt["cols"]), float(opt["scale"]), opt["title"], int(opt["gap"])


def main():
    out, tiles, cols, scale, title, gap = parse(sys.argv[1:])
    if not out or not tiles:
        print(__doc__)
        return 2
    font = ImageFont.truetype(FONT, 16) if os.path.exists(FONT) else ImageFont.load_default()
    big = ImageFont.truetype(FONT, 22) if os.path.exists(FONT) else font
    imgs = []
    for path, crop, label in tiles:
        im = Image.open(path).convert("RGB")
        if crop:
            im = im.crop(crop)
        if scale != 1:
            im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))), Image.LANCZOS)
        imgs.append((label, im))
    rows = [imgs[i:i + cols] for i in range(0, len(imgs), cols)]
    col_w = [max((r[c][1].width for r in rows if c < len(r)), default=0) for c in range(cols)]
    label_h = 24
    top = 40 if title else 6
    width = sum(col_w) + gap * (cols + 1)
    height = top + sum(max(t.height for _, t in r) + label_h + gap for r in rows) + gap
    sheet = Image.new("RGB", (width, height), (24, 26, 30))
    d = ImageDraw.Draw(sheet)
    if title:
        d.text((gap, 8), title, font=big, fill=(230, 210, 160))
    y = top
    for r in rows:
        x = gap
        for c, (label, im) in enumerate(r):
            d.text((x, y + 2), label, font=font, fill=(200, 190, 170))
            sheet.paste(im, (x, y + label_h))
            x += col_w[c] + gap
        y += max(t.height for _, t in r) + label_h + gap
    sheet.save(out)
    print("wrote", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
