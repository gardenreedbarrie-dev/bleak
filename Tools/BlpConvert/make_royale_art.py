#!/usr/bin/env python3
"""Renders the Bleakhold Royale island map and the storm rings into Interface/AddOns/Bleakhold/Art/Royale, and the
map art for the client patch (--tiles).

Usage: python3 -I make_royale_art.py [--spec ../MapForge/specs/royale_v2.json] [--out DIR] [--preview DIR]
                                     [--skip-map] [--tiles DIR] [--check DIR] [--cache FILE] [--zoom]

Needs Pillow and numpy; the BLP encoding is blpconvert.py next to this file. Everything here is drawn by this script
from the MapForge terrain spec (terrain/build.py, about two minutes; --cache FILE keeps what the map needs from it
in an .npz, so later runs take seconds). No game data:

  IslandMap.tga  1024 x 1024, 24-bit uncompressed (RLE) TGA: the illustrated island of the HUD's map window
                 (RoyaleMap.lua). Shaded at twice the height lattice: the terrain's own texture colours (what players
                 see in the world, saturation 1.05), one subtle mode filter for a painted look, a hillshade from the
                 north-west (azimuth 315, altitude 45, multiplied at 0.55 over an ambient of 0.5), contours every
                 20 yd (14 %) and every 100 yd (26 %), water from shallow 4FC1C9 to deep 1C5E8A with shore foam, an
                 ink coastline and a faint wave hatch on the open sea, the buildings (WMOs) as oriented warm-grey
                 footprints, trees as canopy dots and rocks as grey specks. No text and none of the server's points
                 (crate spots, orbs, supply and final sites are never shown to players: docs/BleakholdProtocol.md
                 section 17, ROYM). North up, west left: column u = (maxY - y) / (maxY - minY), row v = (maxX - x) /
                 (maxX - minX) over the map's tiles, the frame ROYM sends. TGA, not DXT1: DXT's 4x4 blocks smear the
                 one-pixel ink lines (spec 1.6). A new name: older packages shipped the old picture as Map.blp,
                 which a manual upgrade keeps, and the client loads a path's .blp before its .tga.
  MapThumb.blp   256 x 256 DXT1, the same picture for the Activities card (shown 1:1).
  MapZoom.tga    (--zoom, P2) 2048 x 2048, for a zoomed map window.
  Ring.blp, RingMid.blp, RingSmall.blp
                 white circle outlines (512, 128 and 32 pixels) for the storm circles: the client draws interface
                 textures with plain bilinear filtering and no mipmaps (Engine/Source/Frame/CSimpleRender.cpp,
                 s_textureFilterMode = GxTex_Linear), so a ring is drawn from the texture whose size is closest to
                 the size on screen, which keeps its line two to five pixels wide.
  RingDashed.tga, RingDashedMid.tga
                 the next circle: white dashed rings (32 dashes, 3-px line) of 512 and 128 pixels, the same outer
                 radius as Ring, so one size and anchor serve both.
  Hole.blp, HoleSmall.blp
                 white outside a circle, clear inside (256 and 64): the storm's shade outside the circle.

The HUD's other art (the arrow, the pin, the storm edge, plates, numerals, icons) is make_royale_hud_art.py's.

--tiles DIR writes the map art of the client patch (spec 2.13), from the same render:
  DIR/minimap/map{tx}_{ty:02d}.png   256 x 256 per ADT tile of the WDT (MapForge package.py --minimap): the same
                                     style with lighter contours, no sea hatch and no building highlight.
  DIR/worldmap/BleakholdRoyale{1..12}.png
                                     4 x 3 tiles of 256 (row-major, the stock world map's order) of a 1024 x 768
                                     canvas whose top-left 1002 x 668 is the WorldMapArea frame MapForge writes (the
                                     island's tiles widened to 1002:668, R.WorldMapBounds): the island fills the
                                     height, the rest is a parchment-toned sea (package.py --worldmap).
--check DIR    renders everything into DIR and fails when a committed file differs.
--preview DIR  also writes every picture as PNG.
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
    from PIL import Image, ImageDraw, ImageFilter
except ImportError:
    raise SystemExit("make_royale_art.py needs Pillow: pip install Pillow")
ak.need_numpy("make_royale_art.py")
np = ak.np

REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
MAPFORGE = os.path.join(REPO, "Tools", "MapForge")
OUT = os.path.join(REPO, "Interface", "AddOns", "Bleakhold", "Art", "Royale")
SPEC = os.path.join(MAPFORGE, "specs", "royale_v2.json")  # the current map (v1: specs/royale_v1.json)
SS = 4  # supersampling for anti-aliased shapes
WORLD_MAP_ASPECT = 1002.0 / 668.0  # Tools/MapForge/dbc/forge.py, the world map frame's detail area

SHALLOW, DEEP = (0x4F, 0xC1, 0xC9), (0x1C, 0x5E, 0x8A)
INK = (0x2A, 0x21, 0x18)
BUILDING = (0x8C, 0x7F, 0x6A)


def to_blp(img, path, fmt):
    """Writes a Pillow image as one-level BLP2 (interface textures use only the top level)."""
    rgba = img.convert("RGBA")
    pic = bc.Image(rgba.width, rgba.height, bytearray(rgba.tobytes()))
    bc.convert(pic, path, fmt=fmt, mips=False, jobs=1)


# ---------------------------------------------------------------------------------------------- the terrain

def extract_terrain(spec_path, cache=None):
    """What the map needs from the MapForge build, as plain arrays (north up, west left, one entry per lattice point
    of the map's tiles): heights, texture colours, water levels (NaN where dry), building footprints and dressing.
    With `cache`, read from that .npz when it exists, else build and write it there."""
    if cache and os.path.isfile(cache):
        z = np.load(cache, allow_pickle=False)
        return {k: z[k] for k in z.files}
    sys.path.insert(0, MAPFORGE)
    from terrain import coords
    from terrain.build import build
    from terrain.placements import _rotate
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
    full = np.frombuffer(grid.h, dtype=np.float64).reshape(grid.rows, grid.cols)
    heights = full[r_base - grid.row0:r_base - grid.row0 + height, c_base - grid.col0:c_base - grid.col0 + width]
    colour = np.zeros((height, width, 3), dtype=np.float64)
    water = np.full((height, width), np.nan, dtype=np.float64)
    tex_cols = np.array([t.color for t in spec.textures], dtype=np.float64)
    for (tx, ty), res in result.tiles.items():
        for (ix, iy), tex in res.texturing.items():
            r0 = (ty * 16 + iy) * 16 - r_base
            c0 = (tx * 16 + ix) * 16 - c_base
            w = np.array(tex.weights, dtype=np.float64)  # layers x 289
            block = (w.T @ tex_cols[list(tex.layers)]).reshape(17, 17, 3)
            colour[r0:r0 + 17, c0:c0 + 17] = block
        for (ix, iy), cw in res.water.items():
            r0 = (ty * 16 + iy) * 16 - r_base
            c0 = (tx * 16 + ix) * 16 - c_base
            for (cx, cy) in cw.exists:
                level = cw.levels.get((cx, cy), cw.height)
                for r in range(2 * cy, 2 * cy + 3):
                    for c in range(2 * cx, 2 * cx + 3):
                        if heights[r0 + r, c0 + c] < level:
                            old = water[r0 + r, c0 + c]
                            water[r0 + r, c0 + c] = level if np.isnan(old) else max(old, level)
    wmos = []
    for p in spec.wmos:
        if p.bounds is not None:
            (x0, y0, _), (x1, y1, _) = p.bounds
            corners = [_rotate((cx, cy, 0.0), *p.rotation) for cx, cy in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
            pts = [(p.x + v[0], p.y + v[1]) for v in corners]
            wmos.append([1.0] + [c for xy in pts for c in xy])
        else:
            wmos.append([0.0, p.x, p.y, p.radius, 0, 0, 0, 0, 0])
    dressing = []  # x, y, kind (1 tree, 2 rock, 3 bush), size
    scattered = {pl.label for pl in getattr(ctx, "scattered", [])}
    for d in ctx.doodads:
        name = d.model.replace("/", "\\").split("\\")[-1].lower()
        if "collision" in name or "waterfall" in name:
            continue
        if any(k in name for k in ("tree", "palm", "bamboo", "treeleaf")):
            kind, size = 1, 4.2 if "palm" in name else 5.0
        elif any(k in name for k in ("rock", "stone", "boulder")):
            kind, size = 2, 2.2
        elif any(k in name for k in ("bush", "fern", "plant", "flower", "vine")):
            kind, size = 3, 1.6
        else:
            continue
        if d.label in scattered and kind == 3:
            size *= 0.8
        dressing.append([d.world[0], d.world[1], kind, size * d.scale_u16 / 1024.0])
    wx0, wx1, wy0, wy1 = spec.world_bounds()
    data = dict(heights=heights.astype(np.float64), colour=colour, water=water,
                wmos=np.array(wmos, dtype=np.float64).reshape(-1, 9),
                dressing=np.array(dressing, dtype=np.float64).reshape(-1, 4),
                frame=np.array([wx0, wx1, wy0, wy1], dtype=np.float64),
                tiles=np.array([spec.tx0, spec.tx1, spec.ty0, spec.ty1], dtype=np.int64))
    if cache:
        np.savez_compressed(cache, **data)
    return data


def resize_f(a, size, resample=Image.BICUBIC):
    """Resizes a float array (H, W) with Pillow's float mode."""
    return np.asarray(Image.fromarray(a.astype(np.float32), mode="F").resize(size, resample), dtype=np.float64)


class Render:
    """The island at twice the lattice (1538 px for three tiles), as float RGB plus the layers the styles need."""

    def __init__(self, t, style):
        self.style = style
        h0, w0 = t["heights"].shape
        self.n = n = 2 * w0  # twice the lattice (1538 px for 769 points), the same extent
        wx0, wx1, wy0, wy1 = t["frame"]
        self.frame = (wx0, wx1, wy0, wy1)
        self.yd_per_px = (wx1 - wx0) / n
        hgt = resize_f(t["heights"], (n, n))
        self.hgt = hgt
        # colour: the texture colours, cleaned by one 3x3 mode filter (a painted look without false bands)
        col8 = Image.fromarray(np.clip(np.rint(t["colour"]), 0, 255).astype(np.uint8))
        col8 = col8.filter(ImageFilter.ModeFilter(3))
        col = np.stack([resize_f(np.asarray(col8)[..., i].astype(np.float64), (n, n)) for i in range(3)], axis=-1)
        col = np.clip(col / 255.0, 0, 1)
        grey = col.mean(axis=-1, keepdims=True)
        self.land = np.clip(grey + (col - grey) * 1.05, 0, 1)
        wl = t["water"]
        wet0 = ~np.isnan(wl)
        self.wet = resize_f(wet0.astype(np.float64), (n, n), Image.BILINEAR) >= 0.5
        filled = np.where(wet0, wl, np.nan)
        # spread the water level into the dry border so the bicubic level stays sane at the shore
        lvl = np.where(wet0, filled, 0.0)
        cnt = wet0.astype(np.float64)
        for _ in range(3):
            lvl_b = ak.gblur(lvl.astype(np.float32), 1.5)
            cnt_b = ak.gblur(cnt.astype(np.float32), 1.5)
            lvl = np.where(wet0, filled, np.where(cnt_b > 1e-3, lvl_b / np.maximum(cnt_b, 1e-3), 0.0))
            cnt = np.where(wet0 | (cnt_b > 1e-3), 1.0, 0.0)
        self.level = resize_f(lvl, (n, n), Image.BILINEAR)
        self.depth = np.where(self.wet, np.maximum(0.0, self.level - hgt), 0.0)
        self.t = t

    def to_px(self, x, y):
        """World (x, y) -> render pixel (column, row), north up and west left."""
        wx0, wx1, wy0, wy1 = self.frame
        return ((wy1 - y) / (wy1 - wy0) * self.n, (wx1 - x) / (wx1 - wx0) * self.n)

    def picture(self):
        st = self.style
        n = self.n
        spc = self.yd_per_px
        # hillshade: sun from the north-west (azimuth 315, altitude 45), the relief exaggerated 2.5 times (the
        # valley floor rises only 30 yd over 1600), normalised so flat ground is 1, multiplied at 0.55 over an
        # ambient of 0.5; plus a little cavity shading (hollows darker, crests lighter) for a painted relief
        gy, gx = np.gradient(self.hgt * 2.5, spc)
        light = ak.light_dir(315.0, 45.0)
        nz = 1.0 / np.sqrt(gx * gx + gy * gy + 1.0)
        lam = np.maximum(0.0, (-gx * nz) * light[0] + (-gy * nz) * light[1] + nz * light[2])
        hill = 0.5 + 0.5 * lam / light[2]
        shade = 1.0 + 0.55 * (np.clip(hill, 0.0, 1.45) - 1.0)
        cavity = self.hgt - ak.gblur(self.hgt.astype(np.float32), 8.0)
        shade = shade * (1.0 + np.clip(cavity * 0.03, -0.14, 0.08))
        # brush texture: soft, deterministic brightness variation at two scales, so wide fields of one texture
        # colour read as painted ground, not a flat fill
        rng = np.random.default_rng(91)
        fine = ak.gblur(rng.standard_normal((n, n)).astype(np.float32), 1.6)
        broad = ak.gblur(rng.standard_normal((n, n)).astype(np.float32), 14.0)
        brush = 0.03 * fine / max(1e-6, fine.std()) + 0.05 * broad / max(1e-6, broad.std())
        rgb = self.land * (shade * (1.0 + brush))[..., None]
        # a painter's light: sunlit slopes a touch warm, shaded ones a touch cool
        dev = np.clip(shade - 1.0, -0.4, 0.4)[..., None]
        rgb = rgb * np.where(dev > 0, 1.0 + dev * np.array([0.10, 0.05, -0.08]),
                             1.0 - dev * np.array([0.06, 0.02, -0.10]))
        # contours over the land: every 20 yd, index every 100 yd
        land = ~self.wet
        for step, alpha in ((20.0, st["contour"]), (100.0, st["index"])):
            c = self.hgt / step
            grad = np.hypot(*np.gradient(c)) + 1e-6
            dist = np.abs(c - np.round(c)) / grad  # pixels to the nearest contour
            line = (1.0 - ak.smoothstep(0.45, 1.0, dist)) * alpha * land
            if step == 20.0:
                line = line * (np.abs(np.round(c) * step % 100.0) > 1e-6)
            rgb = rgb * (1.0 - line[..., None]) + np.array([0.12, 0.10, 0.07]) * line[..., None]
        # water: a depth gradient, foam along the shore, the coastline in ink
        d = self.depth
        t = np.clip(d / 16.0, 0.0, 1.0) ** 0.7
        deep = np.array(st["deep"], dtype=np.float64) / 255.0
        shallow = np.array(SHALLOW, dtype=np.float64) / 255.0
        water = shallow * (1.0 - t[..., None]) + deep * t[..., None]
        # a little of the terrain's relief under shallow water
        water = water * (0.92 + 0.08 * np.clip(hill, 0.6, 1.3)[..., None])
        wet = self.wet
        dist_land = ak.edt(wet, 8)  # pixels from the shore, in the water
        foam = (1.0 - ak.smoothstep(1.0, 2.5, dist_land)) * 0.5 * wet
        if st["hatch"]:
            ys, xs = np.mgrid[0:n, 0:n].astype(np.float64)
            row = np.floor(ys / 14.0)
            xx = xs + (row % 2) * 9.0
            u = (xx % 18.0) / 18.0
            vy = ys % 14.0
            wave = np.exp(-((vy - (5.0 + 2.2 * np.sin(u * 2 * math.pi))) / 0.7) ** 2) * (u < 0.62)
            open_sea = ak.smoothstep(10.0, 18.0, d) * ak.smoothstep(14.0, 24.0, ak.edt(wet, 26))
            water = water + (1.0 - water) * (wave * open_sea * 0.10)[..., None]
        water = water + (1.0 - water) * foam[..., None]
        rgb = np.where(wet[..., None], water, rgb)
        dist_water = ak.edt(~wet, 4)
        edge = np.minimum(dist_land, 99) * wet + np.minimum(dist_water, 99) * (~wet)
        ink = (1.0 - ak.smoothstep(0.5, 1.25, edge)) * st["ink"]
        rgb = rgb * (1.0 - ink[..., None]) + (np.array(INK) / 255.0) * ink[..., None]
        rgb = self.dress(rgb)
        return np.clip(rgb, 0, 1)

    def dress(self, rgb):
        """Trees, rocks and the buildings, drawn at twice the render's resolution and reduced."""
        st = self.style
        n = self.n
        k = 2
        over = Image.new("RGBA", (n * k, n * k), (0, 0, 0, 0))
        d = ImageDraw.Draw(over)
        ppy = k / self.yd_per_px  # supersampled pixels per yard
        dr = self.t["dressing"]
        order = np.argsort(dr[:, 2] * -1, kind="stable") if len(dr) else []
        for i in order:  # bushes first, rocks, then trees on top
            x, y, kind, size = dr[i]
            cx, cy = self.to_px(x, y)
            ix, iy = int(min(n - 1, max(0, cx))), int(min(n - 1, max(0, cy)))
            if self.depth[iy, ix] > 1.5:  # reeds and drifting leaves in the lagoon are not shown
                continue
            cx, cy = cx * k, cy * k
            r = max(1.2, size * ppy * 0.9)
            if kind == 1:  # a canopy: its shadow to the south-east, a dark rim, a lit crown to the north-west
                d.ellipse((cx - r * 0.5, cy - r * 0.4, cx + r * 1.5, cy + r * 1.6), fill=(8, 26, 10, 80))
                d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(22, 64, 28, 240))
                d.ellipse((cx - r * 0.82, cy - r * 0.86, cx + r * 0.7, cy + r * 0.66), fill=(44, 108, 46, 240))
                hr = r * 0.42
                d.ellipse((cx - r * 0.35 - hr, cy - r * 0.4 - hr, cx - r * 0.35 + hr, cy - r * 0.4 + hr),
                          fill=(120, 182, 86, 190))
            elif kind == 2:
                d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(96, 92, 86, 215))
                d.ellipse((cx - r * 0.6, cy - r * 0.6, cx, cy), fill=(170, 164, 152, 170))
            else:
                d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(40, 96, 40, 110))
        for row in self.t["wmos"]:
            if row[0] > 0.5:
                pts = [self.to_px(row[1 + 2 * j], row[2 + 2 * j]) for j in range(4)]
                pts = [(px * k, py * k) for px, py in pts]
                sh = [(px + 1.5 * k, py + 1.5 * k) for px, py in pts]
                d.polygon(sh, fill=(10, 8, 6, 110))
                d.polygon(pts, fill=BUILDING + (255,), outline=(36, 30, 24, 255))
                d.line(pts + [pts[0]], fill=(36, 30, 24, 255), width=max(1, int(k * 1.2)))
                if st["highlight"]:
                    # the edges facing the top left catch the light: a one-pixel pale line on them
                    cx = sum(p[0] for p in pts) / 4.0
                    cy = sum(p[1] for p in pts) / 4.0
                    for a, b in zip(pts, pts[1:] + pts[:1]):
                        mx, my = (a[0] + b[0]) / 2 - cx, (a[1] + b[1]) / 2 - cy
                        if mx * -0.7 + my * -0.7 > 0:
                            ia = (a[0] + (cx - a[0]) * 0.08, a[1] + (cy - a[1]) * 0.08)
                            ib = (b[0] + (cx - b[0]) * 0.08, b[1] + (cy - b[1]) * 0.08)
                            d.line([ia, ib], fill=(214, 202, 178, 200), width=k)
            else:
                cx, cy = self.to_px(row[1], row[2])
                r = row[3] * ppy * 0.6
                d.ellipse((cx * k - r, cy * k - r, cx * k + r, cy * k + r), fill=BUILDING + (255,),
                          outline=(36, 30, 24, 255), width=k)
        o = ak.reduce(ak.to_float(over), k)
        a = o[..., 3:4]
        return rgb * (1.0 - a) + o[..., :3] * a


MAP_STYLE = dict(contour=0.14, index=0.26, deep=DEEP, hatch=True, highlight=True, ink=1.0)
MINIMAP_STYLE = dict(contour=0.08, index=0.15, deep=DEEP, hatch=False, highlight=False, ink=0.85)
WORLDMAP_STYLE = dict(contour=0.12, index=0.22, deep=(0x5E, 0x86, 0x96), hatch=True, highlight=True, ink=1.0)
PARCHMENT_SEA = (0x8C, 0xA6, 0xAA)


def finish(rgb, size):
    """The render resampled to `size` with Lanczos, as a Pillow RGB image."""
    img = ak.to_image(rgb).convert("RGB")
    return img.resize((size, size), Image.LANCZOS)


def minimap_tiles(rgb, tiles, out_dir):
    """map{tx}_{ty:02d}.png, 256 x 256, one per ADT tile (tile columns go west to east, rows north to south)."""
    tx0, tx1, ty0, ty1 = (int(v) for v in tiles)
    n = rgb.shape[0]
    count = tx1 - tx0 + 1
    img = ak.to_image(rgb).convert("RGB")
    os.makedirs(out_dir, exist_ok=True)
    names = []
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            x0 = (tx - tx0) * n / count
            y0 = (ty - ty0) * n / count
            tile = img.resize((256, 256), Image.LANCZOS, box=(x0, y0, x0 + n / count, y0 + n / count))
            name = "map%d_%02d.png" % (tx, ty)
            tile.save(os.path.join(out_dir, name))
            names.append(name)
    return names


def worldmap_tiles(rgb, out_dir):
    """BleakholdRoyale1..12.png: a 1024 x 768 canvas (4 x 3 tiles of 256, row-major) whose top-left 1002 x 668 is
    the WorldMapArea frame: the island (its tiles' square) fills the height, centred, in a parchment-toned sea."""
    W, H = 1024, 768
    fw, fh = 1002, 668
    side = fh
    left = (fw - side) / 2.0
    sea = np.ones((H, W, 3), dtype=np.float64) * (np.array(PARCHMENT_SEA) / 255.0)
    ys, xs = np.mgrid[0:H, 0:W].astype(np.float64)
    row = np.floor(ys / 12.0)
    u = ((xs + (row % 2) * 8.0) % 16.0) / 16.0
    wave = np.exp(-(((ys % 12.0) - (4.5 + 2.0 * np.sin(u * 2 * math.pi))) / 0.6) ** 2) * (u < 0.62)
    sea = sea + (1.0 - sea) * (wave * 0.10)[..., None]
    rng = np.random.default_rng(81)  # a faint paper grain
    grain = ak.gblur(rng.standard_normal((H, W)).astype(np.float32), 1.2)
    sea = sea * (1.0 + 0.025 * grain[..., None] / max(1e-6, grain.std()))
    # the island's tiles end in its mountain ring, not in water: set the square in like a map inset, with a soft
    # shadow and an ink edge, rather than fading land into the sea
    x0 = int(round(left))
    shadow = np.zeros((H, W), dtype=np.float32)
    shadow[6:side + 6, x0 + 4:x0 + side + 4] = 1.0
    shadow = ak.gblur(shadow, 6.0) * 0.45
    sea = sea * (1.0 - shadow[..., None])
    canvas = ak.to_image(np.clip(sea, 0, 1)).convert("RGB")
    island = ak.to_image(rgb).convert("RGB").resize((side, side), Image.LANCZOS)
    canvas.paste(island, (x0, 0))
    d = ImageDraw.Draw(canvas)
    d.rectangle((x0, 0, x0 + side - 1, side - 1), outline=INK, width=2)
    os.makedirs(out_dir, exist_ok=True)
    names = []
    for i in range(12):
        cx, cy = (i % 4) * 256, (i // 4) * 256
        name = "BleakholdRoyale%d.png" % (i + 1)
        canvas.crop((cx, cy, cx + 256, cy + 256)).save(os.path.join(out_dir, name))
        names.append(name)
    canvas.save(os.path.join(out_dir, "..", "worldmap_canvas.png"))
    return names


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


def ring_dashed(size, line, dashes=32, duty=0.55):
    """The next circle: `dashes` white dashes of `line` pixels on Ring's outer radius (1 pixel margin), square ends,
    the first dash centred at the top."""
    k = 8
    big = size * k
    ys, xs = np.mgrid[0:big, 0:big].astype(np.float32)
    dx, dy = (xs + 0.5) / k - size / 2.0, (ys + 0.5) / k - size / 2.0
    r = np.hypot(dx, dy)
    outer = size / 2.0 - 1.0
    band = (r <= outer) & (r >= outer - line)
    ang = (np.arctan2(dx, -dy) / (2 * math.pi)) % 1.0  # 0 at the top, clockwise
    phase = (ang * dashes + duty / 2.0) % 1.0
    a = (band & (phase < duty)).astype(np.float32)
    return ak.to_image(ak.reduce(ak.layer((255, 255, 255), a), k))


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


# ---------------------------------------------------------------------------------------------- main

def pictures(a):
    """[(name, Pillow image, format)] of everything this script commits (format: tga, tga24, dxt1, dxt5)."""
    pics = []
    if not a.skip_map:
        t = extract_terrain(a.spec, a.cache)
        rgb = Render(t, MAP_STYLE).picture()
        pics.append(("IslandMap", finish(rgb, 1024), "tga24"))
        pics.append(("MapThumb", finish(rgb, 256), "dxt1"))
        if a.zoom:
            pics.append(("MapZoom", finish(rgb, 2048), "tga24"))
        a._terrain = t
        a._map_rgb = rgb
    pics += [
        ("Ring", ring(512, 3), "dxt5"),
        ("RingMid", ring(128, 3), "dxt5"),
        ("RingSmall", ring(32, 2), "dxt5"),
        ("RingDashed", ring_dashed(512, 3), "tga"),
        ("RingDashedMid", ring_dashed(128, 3), "tga"),
        ("Hole", hole(256, 3.0), "dxt5"),
        ("HoleSmall", hole(64, 1.5), "dxt5"),
    ]
    return pics


def write(pics, out_dir, quiet=False):
    os.makedirs(out_dir, exist_ok=True)
    names = []
    for name, img, fmt in pics:
        if fmt in ("tga", "tga24"):
            path = os.path.join(out_dir, name + ".tga")
            ak.write_tga(path, img.convert("RGB" if fmt == "tga24" else "RGBA"))
        else:
            path = os.path.join(out_dir, name + ".blp")
            to_blp(img, path, fmt)
        names.append(os.path.basename(path))
        if not quiet:
            print("wrote %s (%d x %d, %s)" % (os.path.relpath(path, REPO), img.width, img.height, fmt))
    return names


def main():
    ap = argparse.ArgumentParser(description="Render the Bleakhold Royale map and storm rings.")
    ap.add_argument("--spec", default=SPEC, help="MapForge terrain spec of the Royale map")
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--preview", help="also write PNG copies here")
    ap.add_argument("--skip-map", action="store_true", help="only the rings (the map takes a few minutes)")
    ap.add_argument("--tiles", metavar="DIR", help="also write the minimap and world map tiles of the client patch")
    ap.add_argument("--check", metavar="DIR", help="render into DIR and fail when a committed file differs")
    ap.add_argument("--cache", metavar="FILE", help="keep the terrain the map needs in FILE (.npz) between runs")
    ap.add_argument("--zoom", action="store_true", help="also write MapZoom.tga (2048 x 2048, spec P2)")
    a = ap.parse_args()
    if a.tiles and a.skip_map:
        ap.error("--tiles needs the map (drop --skip-map)")
    pics = pictures(a)
    if a.check:
        if os.path.isdir(a.check):
            shutil.rmtree(a.check)
        names = write(pics, a.check, quiet=True)
        bad = []
        for n in names:
            ref = os.path.join(OUT, n)
            if not os.path.exists(ref):
                bad.append("missing in the repository: %s" % n)
            elif not filecmp.cmp(os.path.join(a.check, n), ref, shallow=False):
                bad.append("differs: %s" % n)
        for name, _, fmt in pics:
            if fmt.startswith("tga") and os.path.exists(os.path.join(OUT, name + ".blp")):
                bad.append("stale %s.blp would hide %s.tga in the client" % (name, name))
        if bad:
            for b in bad:
                print("make_royale_art: " + b, file=sys.stderr)
            print("make_royale_art: the committed art is out of date (run python3 -I Tools/BlpConvert/"
                  "make_royale_art.py)", file=sys.stderr)
            return 1
        print("make_royale_art: %d files match the generator" % len(names))
        return 0
    write(pics, a.out)
    for name, _, fmt in pics:  # a .blp wins over a .tga of the same name in the client
        stale = os.path.join(a.out, name + ".blp")
        if fmt.startswith("tga") and os.path.exists(stale):
            os.remove(stale)
            print("removed %s (replaced by %s.tga)" % (os.path.relpath(stale, REPO), name))
    if a.preview:
        os.makedirs(a.preview, exist_ok=True)
        for name, img, _ in pics:
            img.save(os.path.join(a.preview, name + ".png"))
    if a.tiles:
        t = a._terrain
        mini = Render(t, MINIMAP_STYLE).picture()
        names = minimap_tiles(mini, t["tiles"], os.path.join(a.tiles, "minimap"))
        print("wrote %d minimap tiles to %s" % (len(names), os.path.join(a.tiles, "minimap")))
        world = Render(t, WORLDMAP_STYLE).picture()
        names = worldmap_tiles(world, os.path.join(a.tiles, "worldmap"))
        print("wrote %d world map tiles to %s" % (len(names), os.path.join(a.tiles, "worldmap")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
