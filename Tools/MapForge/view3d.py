#!/usr/bin/env python3
"""A first-person / aerial heightfield viewer for a MapForge terrain spec, to judge the map from where a player stands.

A top-down preview (terrain/preview.py) cannot show whether a map is empty, flat or well composed: that only shows
from the ground. This builds the terrain, then ray-marches the height field with lighting, fog, glowing lava (liquid
type 3) and the placements drawn as sprites (crude blocks by kind: fire, bones, banners, ruins, rock), so a layout can
be judged before a build on the VPS. It needs numpy and Pillow, which the rest of MapForge does not (this is a
developer tool, not part of the build or the tests). The sprites are not the real models.

It hooks terrain.preview.render to capture the build's real height grid, texture colours, lava/water levels and
prop positions, then ray-marches the heightfield (voxel-space) with lighting, fog, glowing lava and prop sprites.

    python3 -I Tools/MapForge/view3d.py SPEC.json OUT_DIR  NAME=x,y,z,heading,pitch[,fov]  ...
x, y: world X, Y. z: an absolute height, or "g3.6" for 3.6 yards above the ground there (a standing player).
heading: 0 = looking toward -Y (the direction a spec like crucible_v1 travels), 90 = toward -X, -90 = toward +X.
pitch: degrees up (negative looks down). Each view writes OUT_DIR/view_NAME.png.
"""
import math, os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from PIL import Image
from terrain import build, preview, coords

CAP = {}
preview.render = lambda ctx, tiles, a, b: CAP.update(ctx=ctx, tiles=tiles)

if len(sys.argv) < 4 or sys.argv[1] in ("-h", "--help"):
    sys.exit(__doc__)
spec_path, out_dir = sys.argv[1], sys.argv[2]
views = sys.argv[3:]
os.makedirs(out_dir, exist_ok=True)
build.main([spec_path, out_dir, "--force", "--quiet"])
ctx, tiles = CAP["ctx"], CAP["tiles"]
spec, grid = ctx.spec, ctx.grid

LPT = coords.LATTICE_PER_TILE
W = (spec.tx1 - spec.tx0 + 1) * LPT + 1
Hn = (spec.ty1 - spec.ty0 + 1) * LPT + 1
r0, c0 = spec.ty0 * LPT, spec.tx0 * LPT

H = np.empty((Hn, W), dtype=np.float32)
for r in range(Hn):
    H[r] = [grid.get(r0 + r, c0 + c) for c in range(W)]

# texture colour per lattice point
COL = np.zeros((Hn, W, 3), dtype=np.float32)
for (tx, ty), res in tiles.items():
    for (ix, iy), tex in res.texturing.items():
        rr = (ty * 16 + iy) * 16 - r0
        cc = (tx * 16 + ix) * 16 - c0
        cols = [spec.textures[k].color for k in tex.layers]
        for r in range(17):
            for c in range(17):
                p = r * 17 + c
                acc = [0.0, 0.0, 0.0]
                for li, col in enumerate(cols):
                    w = tex.weights[li][p]
                    acc[0] += w * col[0]; acc[1] += w * col[1]; acc[2] += w * col[2]
                COL[rr + r, cc + c] = acc

# liquid: surface level and type per lattice point
WL = np.full((Hn, W), -1e9, dtype=np.float32)
LT = np.zeros((Hn, W), dtype=np.int8)
for (tx, ty), res in tiles.items():
    for (ix, iy), cw in res.water.items():
        rr = (ty * 16 + iy) * 16 - r0
        cc = (tx * 16 + ix) * 16 - c0
        for (cx, cy) in cw.exists:
            level = cw.levels[(cx, cy)]
            for r in range(2 * cy, 2 * cy + 3):
                for c in range(2 * cx, 2 * cx + 3):
                    if H[rr + r, cc + c] < level:
                        WL[rr + r, cc + c] = level
                        LT[rr + r, cc + c] = cw.liquid_type or 1

# lighting from the normals
gy_, gx_ = np.gradient(H, coords.HALF_UNIT)
nz = 1.0 / np.sqrt(gx_ ** 2 + gy_ ** 2 + 1.0)
nx, ny = -gx_ * nz, -gy_ * nz
LIGHT = np.clip(0.42 + 0.9 * np.clip(nx * 0.35 + ny * -0.45 + nz * 0.82, 0, 1), 0.2, 1.25).astype(np.float32)

# props as sprites: (row, col, z, height_px_world, colour)
def prop_style(model):
    m = model.lower()
    if any(k in m for k in ("ember", "fire", "torch", "brazier", "bonfire", "campfire", "firepit")):
        return (255, 140, 40), 4.0, 1.3
    if "smoke" in m or "fog" in m:
        return (120, 110, 110), 9.0, 2.5
    if any(k in m for k in ("skull", "bone", "grave", "skelet", "tiki")):
        return (225, 215, 190), 3.5, 1.0
    if "banner" in m:
        return (170, 30, 30), 7.0, 0.9
    if any(k in m for k in ("arch", "ruin", "pillar", "stone", "wall", "face", "head", "gargoyle", "statue", "obelisk")):
        return (150, 135, 115), 9.0, 3.2
    if "tree" in m or "stump" in m:
        return (60, 45, 35), 12.0, 1.4
    if "crystal" in m:
        return (255, 90, 40), 6.0, 1.3
    return (95, 85, 78), 5.0, 2.2  # rocks and everything else

PROPS = []
allp = list(ctx.doodads) + list(ctx.wmos)
for p in allp:
    wx, wy, wz = p.world
    rr, cc = coords.world_to_lattice(wx, wy)
    if p.kind == "wmo":
        PROPS.append((rr - r0, cc - c0, wz, (200, 60, 200), 30.0, 12.0))
    else:
        col, hh, ww = prop_style(p.model)
        sc = (p.scale_u16 / 1024.0) if getattr(p, "scale_u16", None) else 1.0
        PROPS.append((rr - r0, cc - c0, wz, col, hh * sc, ww * sc))
print("props drawn as sprites:", len(PROPS))

SKY_TOP = np.array([18, 6, 8], np.float32)
SKY_HOR = np.array([120, 38, 20], np.float32)
FOG = np.array([88, 30, 18], np.float32)


def sample(arr, rr, cc):
    ri = np.clip(rr.astype(np.int32), 0, Hn - 1)
    ci = np.clip(cc.astype(np.int32), 0, W - 1)
    return arr[ri, ci]


def render_view(name, x, y, z, heading, pitch, fov=78, width=1280, height=560, maxd=1500.0):
    f = (width / 2) / math.tan(math.radians(fov / 2))
    horizon = height * 0.5 + math.tan(math.radians(pitch)) * f
    img = np.zeros((height, width, 3), np.float32)
    ys = np.arange(height, dtype=np.float32)[:, None]
    t = np.clip((ys - 0) / max(horizon, 1), 0, 1)
    img[:] = (SKY_TOP * (1 - t) + SKY_HOR * t)[:, None, :]
    ymin = np.full(width, height, np.int32)
    # camera in lattice coords
    cr, cc = coords.world_to_lattice(x, y)
    cr -= r0; cc -= c0
    h_rad = math.radians(heading)
    # forward in lattice (dr, dc): heading 0 -> +col (toward -Y); heading 90 -> +row (toward -X)
    fdr, fdc = math.sin(h_rad), math.cos(h_rad)
    sdr, sdc = math.cos(h_rad), -math.sin(h_rad)          # screen-right vector
    px = (np.arange(width, dtype=np.float32) - width / 2) / f   # tan of the ray angle
    rdr = fdr + px * sdr
    rdc = fdc + px * sdc
    norm = np.sqrt(rdr ** 2 + rdc ** 2)
    rdr_n, rdc_n = rdr / norm, rdc / norm
    cosθ = 1.0 / norm                                         # perpendicular depth = t * cosθ
    step = 0.6
    d = 1.0
    props = sorted(PROPS, key=lambda p: ((p[0] - cr) * fdr + (p[1] - cc) * fdc))
    pi = 0
    # project props: perpendicular depth along forward, lateral offset along screen-right
    pdepth = [((p[0] - cr) * fdr + (p[1] - cc) * fdc) * coords.HALF_UNIT for p in props]
    plat = [((p[0] - cr) * sdr + (p[1] - cc) * sdc) * coords.HALF_UNIT for p in props]
    while d * coords.HALF_UNIT < maxd:
        dy = d * coords.HALF_UNIT
        t_ray = d
        rr = cr + rdr_n * t_ray
        c2 = cc + rdc_n * t_ray
        depth = t_ray * cosθ * coords.HALF_UNIT
        h = sample(H, rr, c2)
        wl = sample(WL, rr, c2)
        wet = wl > -1e8
        surf = np.where(wet, wl, h)
        top = (horizon + (z - surf) / depth * f).astype(np.int32)
        col = sample(COL, rr, c2) * sample(LIGHT, rr, c2)[:, None]
        lt = sample(LT, rr, c2)
        if wet.any():
            glow = 0.80 + 0.2 * np.sin(rr * 0.33 + c2 * 0.21)[wet]
            lava = np.stack([255 * glow, (100 + 60 * glow) , 24 * glow], axis=1)
            water = np.stack([40 + 0 * glow, 90 + 0 * glow, 150 + 0 * glow], axis=1)
            col[wet] = np.where((lt[wet] == 3)[:, None], lava, water)
        fogk = np.clip(1.0 - np.exp(-depth / 650.0), 0, 0.88)[:, None]
        col = col * (1 - fogk) + FOG * fogk
        vis = top < ymin
        idx = np.nonzero(vis)[0]
        for x_ in idx:
            y0 = max(int(top[x_]), 0)
            if y0 < ymin[x_]:
                img[y0:ymin[x_], x_] = col[x_]
                ymin[x_] = y0
        # prop sprites whose depth lies in this slab (drawn after the terrain of the same slab)
        slab = d * coords.HALF_UNIT
        while pi < len(props) and pdepth[pi] < slab + step * coords.HALF_UNIT * 1.2:
            if pdepth[pi] > 1.0:
                p = props[pi]
                sx = int(width / 2 + plat[pi] / pdepth[pi] * f)
                base = int(horizon + (z - p[2]) / pdepth[pi] * f)
                hpx = max(int(p[4] / pdepth[pi] * f), 1)
                wpx = max(int(p[5] / pdepth[pi] * f * 0.5), 1)
                topy = base - hpx
                fk = float(np.clip(1.0 - math.exp(-pdepth[pi] / 650.0), 0, 0.88))
                pc = np.array(p[3], np.float32) * (1 - fk) + FOG * fk
                for xx in range(sx - wpx, sx + wpx + 1):
                    if 0 <= xx < width and topy < ymin[xx] and base > 0:
                        y0 = max(topy, 0); y1 = min(base, ymin[xx], height)
                        if y1 > y0:
                            img[y0:y1, xx] = pc
                            ymin[xx] = y0
            pi += 1
        d += step
        step = 0.6 + d * 0.006
    out = np.clip(img, 0, 255).astype(np.uint8)
    path = os.path.join(out_dir, f"view_{name}.png")
    Image.fromarray(out).save(path)
    print("wrote", path)


for v in views:
    name, _, rest = v.partition("=")
    toks = rest.split(",")
    x, y = float(toks[0]), float(toks[1])
    z_tok = toks[2]
    ground = grid.ground_height(x, y)
    z = ground + float(z_tok[1:]) if z_tok.startswith("g") else float(z_tok)   # "g3.5" = 3.5 yards above the ground
    hd, pt = float(toks[3]), float(toks[4])
    fov = float(toks[5]) if len(toks) > 5 else 78
    print(f"{name}: ground {ground:.1f}, camera z {z:.1f}")
    render_view(name, x, y, z, hd, pt, fov)
