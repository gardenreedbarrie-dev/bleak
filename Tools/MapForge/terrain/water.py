"""Liquids as MH2O (the 3.3.5a format; Liquid::CAreaData in WoW/Source/LiquidSystem/LiquidData.cpp).

MH2O payload: 256 chunk headers (offsetInstances, layerCount, offsetAttributes; 12 bytes, index 16 * iy + ix),
then per chunk with water one instance (24 bytes: liquidType, vertexFormat, minHeight, maxHeight, xOffset, yOffset,
width, height, offsetExistsBitmap, offsetVertexData), its attributes (fishable u64, deep u64), the exists bitmap
(bit row * width + col, LSB first, padded to 8 bytes because AzerothCore's extractor reads a whole u64) and the
vertex data (vertex format 0: (w + 1) * (h + 1) float heights, then as many depth bytes). All offsets are relative
to the MH2O payload. Liquid "tiles" are the 8 x 8 cells of a chunk; row = along -X (like chunk rows).

Water bodies: the spec's `water` entries (a shape and one height), `lakes` (a shape and a level) and `rivers` (a
channel whose level steps down from reach to reach). A cell is wet when a body's shape holds the cell centre, or
for a river one of its four corners (the lowest level found: the rounded bed stays under the water out to about
0.9 of the half width, so a bank cell centred just outside the channel still has corners over it), and any of its
five terrain vertices is below that body's level there (minus min_depth); where several bodies hold a wet cell,
the lowest water wins (a higher surface cannot stand over lower water).

Several bodies in one chunk: the readers allow it differently. The client walks every instance of a chunk
(CMapChunk::CreateLiquids loops over layerCount), but AzerothCore's map_extractor takes only the first instance
(adt_MH2O::GetLiquidInstance) and stores one liquid type per chunk (liquid_entry[16][16]). So MapForge writes one
instance per chunk: the cells of bodies with the chunk's first-listed liquid type are merged into it, each with its
own level, and cells of another liquid type are dropped (a warning names them).

Vertex heights: the server keeps one level per cell, the height of the cell's top-left vertex (map_extractor copies
the vertex grid; GridTerrainData::GetLiquidData reads it for the whole cell), while the client interpolates the
cell's four corners bilinearly (CChunkLiquid::CreateVertXY, GetHeight). So every wet cell must have all four
corners at its own level, or a point the client shows as dry ground is under water on the server (breath timer,
IsInWater). Each vertex takes the level of the cell it is the top-left corner of, or else of a wet cell to its
left, above or above-left, and where two levels meet inside a chunk (a waterfall) a wet cell with a higher wet
cell among its 8 neighbours is left dry: no two touching wet cells differ, so every corner of a wet cell is its
own level. The upper water reaches the lip, the foot of the fall gets a one-cell gap (the waterfall model covers
it). A chunk's top-left vertices are only ever written by that chunk or by chunks before it in map_extractor's
loop, so every wet cell keeps its own level on the server too; where two levels meet on a chunk edge, the client
draws a step.
"""

from __future__ import annotations

import struct

from . import coords

DEPTH_PER_YARD = 8.0


class WaterBody:
    """One body of water: `probe(x, y)` is its level at a point its shape holds, else None."""

    __slots__ = ("index", "name", "kind", "liquid_type", "min_depth", "bbox", "_probe", "levels", "river")

    def __init__(self, index, name, kind, liquid_type, min_depth, bbox, probe, levels, river=None):
        self.index = index
        self.name = name
        self.kind = kind  # "water" (the spec's water list), "lake" or "river"
        self.liquid_type = liquid_type
        self.min_depth = min_depth
        self.bbox = bbox
        self._probe = probe
        self.levels = levels  # every level the body has
        self.river = river

    def probe(self, x: float, y: float):
        b = self.bbox
        if x < b[0] or x > b[1] or y < b[2] or y > b[3]:
            return None
        return self._probe(x, y)


def _shape_probe(shape, level):
    def probe(x, y):
        return level if shape.contains(x, y) else None
    return probe


def _river_probe(path):
    half = path.half

    def probe(x, y):
        dist, seg, _ = path.nearest(x, y)
        if dist > half:
            return None
        return path.levels[path.seg_reach[seg]]
    return probe


def water_bodies(spec) -> list[WaterBody]:
    """The spec's water, lakes and rivers, in that order (the order decides a chunk's liquid type)."""
    cached = getattr(spec, "_water_bodies", None)
    if cached is not None:
        return cached
    out = []
    for i, w in enumerate(spec.water):
        out.append(WaterBody(len(out), f"water[{i}]", "water", w["liquid_type"], w["min_depth"], w["shape"].bbox(),
                             _shape_probe(w["shape"], w["height"]), [w["height"]]))
    for lake in spec.lakes:
        out.append(WaterBody(len(out), lake["name"], "lake", lake["liquid_type"], lake["min_depth"],
                             lake["shape"].bbox(), _shape_probe(lake["shape"], lake["level"]), [lake["level"]]))
    for river in spec.rivers:
        path = river["path"]
        x0, x1, y0, y1 = path.bbox
        h = path.half
        out.append(WaterBody(len(out), river["name"], "river", river["liquid_type"], river["min_depth"],
                             (x0 - h, x1 + h, y0 - h, y1 + h), _river_probe(path), list(river["levels"]), river))
    spec._water_bodies = out
    return out


def water_level_at(spec, x: float, y: float, ground: float) -> float | None:
    """The lowest water level over the ground at a point, or None where it is dry."""
    best = None
    for body in water_bodies(spec):
        level = body.probe(x, y)
        if level is not None and ground < level and (best is None or level < best):
            best = level
    return best


class ChunkWater:
    __slots__ = ("liquid_type", "height", "x0", "y0", "w", "h", "exists", "depths", "levels", "heights", "bodies")

    def __init__(self, liquid_type, height, x0, y0, w, h, exists, depths, levels=None, heights=None, bodies=()):
        self.liquid_type = liquid_type
        self.height = height  # the lowest vertex height (the whole surface when it is flat)
        self.x0 = x0
        self.y0 = y0
        self.w = w
        self.h = h
        self.exists = exists  # set of (cx, cy) wet cells (absolute 0..7)
        self.depths = depths  # (h + 1) x (w + 1) depth bytes, row-major
        self.levels = levels if levels is not None else {c: height for c in exists}  # wet cell -> its level
        self.heights = heights if heights is not None else [height] * ((w + 1) * (h + 1))  # vertex heights
        self.bodies = tuple(bodies)  # indices of the bodies with cells here

    @property
    def min_height(self) -> float:
        return min(self.heights)

    @property
    def max_height(self) -> float:
        return max(self.heights)


def water_for_chunk(spec, grid, tx: int, ty: int, ix: int, iy: int, warnings: list[str],
                    stats: dict | None = None) -> ChunkWater | None:
    bodies = water_bodies(spec)
    if not bodies:
        return None
    row0 = (ty * 16 + iy) * coords.LATTICE_PER_CHUNK
    col0 = (tx * 16 + ix) * coords.LATTICE_PER_CHUNK
    top_x = coords.lattice_x(row0)
    top_y = coords.lattice_y(col0)
    bottom_x = coords.lattice_x(row0 + coords.LATTICE_PER_CHUNK)
    bottom_y = coords.lattice_y(col0 + coords.LATTICE_PER_CHUNK)
    near = [b for b in bodies if not (b.bbox[1] < bottom_x or b.bbox[0] > top_x or b.bbox[3] < bottom_y
                                      or b.bbox[2] > top_y)]
    if not near:
        return None
    cells: dict[tuple[int, int], tuple[WaterBody, float]] = {}
    for cy in range(8):
        for cx in range(8):
            r = row0 + 2 * cy
            c = col0 + 2 * cx
            x = coords.lattice_x(r + 1)
            y = coords.lattice_y(c + 1)
            low = min(grid.get(r, c), grid.get(r, c + 2), grid.get(r + 2, c), grid.get(r + 2, c + 2),
                      grid.get(r + 1, c + 1))
            best = None
            for body in near:
                level = body.probe(x, y)
                if level is None and body.kind == "river":
                    # A bank cell centred just outside the channel still has corners over the rounded bed, which
                    # stays under the water out to about 0.9 of the half width.
                    corner = [body.probe(coords.lattice_x(rr), coords.lattice_y(cc))
                              for rr, cc in ((r, c), (r, c + 2), (r + 2, c), (r + 2, c + 2))]
                    corner = [lv for lv in corner if lv is not None]
                    level = min(corner) if corner else None
                if level is None or not low < level - body.min_depth:
                    continue
                if best is None or level < best[1]:
                    best = (body, level)
            if best is not None:
                cells[(cx, cy)] = best
    if not cells:
        return None
    first = min(b.index for b, _ in cells.values())
    liquid_type = bodies[first].liquid_type
    kept = {c: v for c, v in cells.items() if v[0].liquid_type == liquid_type}
    dropped = {c: v for c, v in cells.items() if v[0].liquid_type != liquid_type}
    if dropped:
        names = sorted({v[0].name for v in dropped.values()})
        warnings.append(f"tile {tx},{ty} chunk {ix},{iy}: {', '.join(names)} (another liquid type) meets "
                        f"{bodies[first].name}; dropped {len(dropped)} cells, since AzerothCore's map_extractor "
                        f"reads one liquid instance and type per chunk")
        if stats is not None:
            stats["dropped_cells"] = stats.get("dropped_cells", 0) + len(dropped)
    # A cell next to higher water (any of its 8 neighbours) stays dry: it would get corners at both levels, which
    # the client draws as a slope while the server holds its top-left level over the whole cell. The highest cells
    # are never dropped, so `kept` keeps at least one.
    step = {c for c, v in kept.items()
            if any((n := kept.get((c[0] + dx, c[1] + dy))) is not None and n[1] > v[1]
                   for dx in (-1, 0, 1) for dy in (-1, 0, 1))}
    for c in step:
        del kept[c]
    in_chunk = sorted({v[0].index for v in kept.values()})
    if len(in_chunk) > 1 and stats is not None:
        stats["merged_chunks"] = stats.get("merged_chunks", 0) + 1
    levels = {c: v[1] for c, v in kept.items()}
    xs = [c[0] for c in kept]
    ys = [c[1] for c in kept]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    w = x1 - x0 + 1
    h = y1 - y0 + 1
    lowest = min(levels.values())
    heights = []
    depths = []
    for vy in range(h + 1):
        for vx in range(w + 1):
            ax, ay = x0 + vx, y0 + vy
            level = None
            for cell in ((ax, ay), (ax - 1, ay), (ax, ay - 1), (ax - 1, ay - 1)):
                if cell in levels:
                    level = levels[cell]
                    break
            if level is None:
                level = lowest
            heights.append(level)
            r = row0 + 2 * ay
            c = col0 + 2 * ax
            d = (level - grid.get(r, c)) * DEPTH_PER_YARD
            depths.append(0 if d <= 0.0 else 255 if d >= 255.0 else int(d + 0.5))
    return ChunkWater(liquid_type, lowest, x0, y0, w, h, set(kept), depths, levels, heights, in_chunk)


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
        body += struct.pack("<HHffBBBBII", cw.liquid_type, 0, cw.min_height, cw.max_height, cw.x0, cw.y0, cw.w, cw.h,
                            bitmap_ofs, vert_ofs)
        body += struct.pack("<QQ", fishable, 0)
        body += bits.to_bytes(8, "little")
        body += struct.pack(f"<{nverts}f", *cw.heights)
        body += bytes(cw.depths)
        while len(body) % 4:
            body.append(0)
        struct.pack_into("<III", header, i * 12, inst_ofs, 1, attr_ofs)
    return bytes(header + body)
