"""Top-down previews for humans: a pure-Python PNG writer, the texture/heightmap renders.

preview.png: one pixel per half unit (2.08 yards), north up and east right (world +X up, -Y right). Colour = the
chunk's texture layers mixed with the textures' preview colours, shaded by the terrain normal (light from the
north-west), water tinted blue, tile borders dark, WMOs red, doodads yellow (scattered ones a single darker pixel),
POIs by kind (POI_COLORS; magenta for other kinds), final sites with a ring at the last circle's radius, waterfalls
and their splashes white, modern doodads (extra assets) cyan.
heightmap.png: grey levels from the lowest (black) to the highest (white) point.
"""

from __future__ import annotations

import struct
import zlib

from . import coords


def write_png(path: str, width: int, height: int, rows: list[bytes]) -> None:
    """8-bit RGB PNG; each row is width * 3 bytes."""
    raw = bytearray()
    for row in rows:
        if len(row) != width * 3:
            raise ValueError("bad row length")
        raw.append(0)
        raw += row

    def png_chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    data = (b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + png_chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + png_chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(data)


# POI kind -> (colour, dot half-size in pixels). Crates and buff orbs by param.
POI_COLORS = {
    "lobby": ((255, 255, 255), 4),
    "landmark": ((230, 60, 230), 3),
    "crossing": ((60, 220, 230), 3),
    "crate:1": ((255, 150, 30), 1),
    "crate:2": ((255, 40, 40), 2),
    "orb_shadow": ((150, 70, 255), 2),
    "orb_buff": ((60, 230, 90), 2),
    "supply_site": ((255, 255, 60), 3),
    "final_site": ((120, 200, 255), 2),
}
FINAL_RING_YARDS = 35.0  # the storm's last circle (stage 5 radius)


def _clamp8(v: float) -> int:
    n = int(v + 0.5)
    return 0 if n < 0 else 255 if n > 255 else n


def render(ctx, tiles: dict, out_preview: str, out_height: str) -> None:
    spec = ctx.spec
    grid = ctx.grid
    width = (spec.tx1 - spec.tx0 + 1) * coords.LATTICE_PER_TILE + 1
    height = (spec.ty1 - spec.ty0 + 1) * coords.LATTICE_PER_TILE + 1
    r_base = spec.ty0 * coords.LATTICE_PER_TILE
    c_base = spec.tx0 * coords.LATTICE_PER_TILE
    color = [[(0.0, 0.0, 0.0)] * width for _ in range(height)]
    wet = [[False] * width for _ in range(height)]
    for (tx, ty), res in tiles.items():
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
                level = cw.levels[(cx, cy)]
                for r in range(2 * cy, 2 * cy + 3):
                    for c in range(2 * cx, 2 * cx + 3):
                        if grid.get(r_base + r0 + r, c_base + c0 + c) < level:
                            wet[r0 + r][c0 + c] = True

    lx, ly, lz = 0.5, 0.5, 0.7071
    lo = min(grid.get(r_base + r, c_base + c) for r in range(0, height, 4) for c in range(0, width, 4))
    hi = max(grid.get(r_base + r, c_base + c) for r in range(0, height, 4) for c in range(0, width, 4))
    span = hi - lo if hi > lo else 1.0
    rows = []
    hrows = []
    for r in range(height):
        row = bytearray()
        hrow = bytearray()
        for c in range(width):
            nx, ny, nz = grid.normal(r_base + r, c_base + c)
            shade = 0.45 + 0.75 * max(0.0, nx * lx + ny * ly + nz * lz)
            red, green, blue = color[r][c]
            if wet[r][c]:
                red, green, blue = red * 0.35 + 30, green * 0.35 + 80, blue * 0.35 + 160
            row += bytes((_clamp8(red * shade), _clamp8(green * shade), _clamp8(blue * shade)))
            g = _clamp8((grid.get(r_base + r, c_base + c) - lo) / span * 255.0)
            hrow += bytes((g, g, g))
        rows.append(row)
        hrows.append(hrow)

    def dot(x: float, y: float, rgb, size: int) -> None:
        u, v = coords.world_to_lattice(x, y)
        r = int(u + 0.5) - r_base
        c = int(v + 0.5) - c_base
        for rr in range(r - size, r + size + 1):
            for cc in range(c - size, c + size + 1):
                if 0 <= rr < height and 0 <= cc < width:
                    rows[rr][cc * 3:cc * 3 + 3] = bytes(rgb)

    for r in range(height):
        for c in range(width):
            if (r % coords.LATTICE_PER_TILE == 0) or (c % coords.LATTICE_PER_TILE == 0):
                rows[r][c * 3:c * 3 + 3] = b"\x20\x20\x20"
    def ring(x: float, y: float, radius: float, rgb) -> None:
        steps = max(24, int(radius * 2))
        for i in range(steps):
            a = 360.0 * i / steps
            dot(x + radius * coords.dcos(a), y + radius * coords.dsin(a), rgb, 0)

    scattered = {p.label for p in getattr(ctx, "scattered", [])}
    falls = {p.label for p in ctx.spec.generated}
    for d in ctx.doodads:
        if d.label in falls:
            dot(d.world[0], d.world[1], (255, 255, 255), 2)
        elif d.modern:
            dot(d.world[0], d.world[1], (40, 230, 230), 0 if d.label in scattered else 1)
        elif d.label in scattered:
            dot(d.world[0], d.world[1], (190, 170, 30), 0)
        else:
            dot(d.world[0], d.world[1], (250, 220, 40), 1)
    for w in ctx.wmos:
        dot(w.world[0], w.world[1], (220, 40, 40), 3)
    for m in ctx.pois:
        key = f"{m['kind']}:{m.get('param', 0)}" if m["kind"] == "crate" else m["kind"]
        rgb, size = POI_COLORS.get(key, ((230, 60, 230), 2))
        if m["kind"] == "final_site":
            ring(m["x"], m["y"], FINAL_RING_YARDS, rgb)
        dot(m["x"], m["y"], rgb, size)
    write_png(out_preview, width, height, rows)
    write_png(out_height, width, height, hrows)
