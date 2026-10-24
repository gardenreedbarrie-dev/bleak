"""Liquids as MH2O (the 3.3.5a format; Liquid::CAreaData in WoW/Source/LiquidSystem/LiquidData.cpp).

MH2O payload: 256 chunk headers (offsetInstances, layerCount, offsetAttributes; 12 bytes, index 16 * iy + ix),
then per chunk with water one instance (24 bytes: liquidType, vertexFormat, minHeight, maxHeight, xOffset, yOffset,
width, height, offsetExistsBitmap, offsetVertexData), its attributes (fishable u64, deep u64), the exists bitmap
(bit row * width + col, LSB first, padded to 8 bytes because AzerothCore's extractor reads a whole u64) and the
vertex data (vertex format 0: (w + 1) * (h + 1) float heights, then as many depth bytes). All offsets are relative
to the MH2O payload. Liquid "tiles" are the 8 x 8 cells of a chunk; row = along -X (like chunk rows).

A cell is wet when a water body's shape holds the cell centre and any of its five terrain vertices is below the
water level (minus min_depth). v1 writes one liquid layer per chunk: where two bodies meet in one chunk, the first
listed wins and a warning is printed.
"""

from __future__ import annotations

import struct

from . import coords

DEPTH_PER_YARD = 8.0


class ChunkWater:
    __slots__ = ("liquid_type", "height", "x0", "y0", "w", "h", "exists", "depths")

    def __init__(self, liquid_type, height, x0, y0, w, h, exists, depths):
        self.liquid_type = liquid_type
        self.height = height
        self.x0 = x0
        self.y0 = y0
        self.w = w
        self.h = h
        self.exists = exists  # set of (cx, cy) wet cells (absolute 0..7)
        self.depths = depths  # (h + 1) x (w + 1) depth bytes, row-major


def water_for_chunk(spec, grid, tx: int, ty: int, ix: int, iy: int, warnings: list[str]) -> ChunkWater | None:
    if not spec.water:
        return None
    row0 = (ty * 16 + iy) * coords.LATTICE_PER_CHUNK
    col0 = (tx * 16 + ix) * coords.LATTICE_PER_CHUNK
    found = None
    wet: set[tuple[int, int]] = set()
    for bi, body in enumerate(spec.water):
        level = body["height"]
        cells = set()
        for cy in range(8):
            for cx in range(8):
                r = row0 + 2 * cy
                c = col0 + 2 * cx
                x = coords.lattice_x(r + 1)
                y = coords.lattice_y(c + 1)
                if not body["shape"].contains(x, y):
                    continue
                low = min(grid.get(r, c), grid.get(r, c + 2), grid.get(r + 2, c), grid.get(r + 2, c + 2),
                          grid.get(r + 1, c + 1))
                if low < level - body["min_depth"]:
                    cells.add((cx, cy))
        if not cells:
            continue
        if found is None:
            found = bi
            wet = cells
        else:
            warnings.append(f"water[{bi}] meets water[{found}] in tile {tx},{ty} chunk {ix},{iy}; kept water[{found}]")
    if found is None:
        return None
    body = spec.water[found]
    level = body["height"]
    xs = [c[0] for c in wet]
    ys = [c[1] for c in wet]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    w = x1 - x0 + 1
    h = y1 - y0 + 1
    depths = []
    for vy in range(h + 1):
        for vx in range(w + 1):
            r = row0 + 2 * (y0 + vy)
            c = col0 + 2 * (x0 + vx)
            d = (level - grid.get(r, c)) * DEPTH_PER_YARD
            depths.append(0 if d <= 0.0 else 255 if d >= 255.0 else int(d + 0.5))
    return ChunkWater(body["liquid_type"], level, x0, y0, w, h, wet, depths)


def build_mh2o(chunks: list[ChunkWater | None]) -> bytes:
    """MH2O payload for 256 chunks (index 16 * iy + ix); b'' when no chunk has water."""
    if not any(chunks):
        return b""
    header = bytearray(256 * 12)
    body = bytearray()
    base = len(header)
    for i, cw in enumerate(chunks):
        if cw is None:
            continue
        inst_ofs = base + len(body)
        attr_ofs = inst_ofs + 24
        bitmap_ofs = attr_ofs + 16
        bits = 0
        for (cx, cy) in cw.exists:
            bits |= 1 << ((cy - cw.y0) * cw.w + (cx - cw.x0))
        bitmap_len = 8  # (w * h + 7) // 8 bytes are used; padded to a full u64
        vert_ofs = bitmap_ofs + bitmap_len
        fishable = 0
        for (cx, cy) in cw.exists:
            fishable |= 1 << (cy * 8 + cx)
        nverts = (cw.w + 1) * (cw.h + 1)
        body += struct.pack("<HHffBBBBII", cw.liquid_type, 0, cw.height, cw.height, cw.x0, cw.y0, cw.w, cw.h,
                            bitmap_ofs, vert_ofs)
        body += struct.pack("<QQ", fishable, 0)
        body += bits.to_bytes(8, "little")
        body += struct.pack(f"<{nverts}f", *([cw.height] * nverts))
        body += bytes(cw.depths)
        while len(body) % 4:
            body.append(0)
        struct.pack_into("<III", header, i * 12, inst_ofs, 1, attr_ofs)
    return bytes(header + body)
