"""Doodad (MDDF) and WMO (MODF) placements: unique ids, ground snapping, file coordinates, extents, footprints.

The client builds a placement's matrix as translate(pos), then Z by rotation.y + 180 deg, Y by rotation.x, X by
rotation.z (CMap::CreateDoodadDef / CreateMapObjDef with C44Matrix's row-vector Rotate*: model points are turned
about X first, then Y, then Z). Doodad scale is a u16 with 1024 = 1.0.

A placement is listed in every tile and referenced (MCRF) from every chunk that its footprint overlaps: the client
draws and culls objects through the chunks that reference them, and dedups the copies by unique id (doodadDefHash /
mapObjDefHash), as Blizzard's tiles do. AzerothCore's vmap4_extractor dedups by the same id
(GenerateUniqueObjectId), so ids are unique across doodads and WMOs together.
"""

from __future__ import annotations

from . import coords
from .spec_errors import SpecError


class Resolved:
    __slots__ = ("kind", "model", "uid", "world", "file_pos", "rotation", "scale_u16", "flags", "extents",
                 "doodad_set", "name_set", "footprint", "label", "radius", "bounds_source")

    def __init__(self):
        self.footprint: dict[tuple[int, int], list[tuple[int, int]]] = {}


def _rotate(v, rx_file: float, ry_file: float, rz_file: float):
    x, y, z = v
    # About X by rotation.z.
    c = coords.dcos(rz_file)
    s = coords.dsin(rz_file)
    y, z = y * c - z * s, y * s + z * c
    # About Y by rotation.x.
    c = coords.dcos(rx_file)
    s = coords.dsin(rx_file)
    x, z = x * c + z * s, -x * s + z * c
    # About Z by rotation.y + 180.
    c = coords.dcos(ry_file + 180.0)
    s = coords.dsin(ry_file + 180.0)
    x, y = x * c - y * s, x * s + y * c
    return (x, y, z)


def world_extents(world, rotation, scale: float, bounds):
    """World AABB (lo, hi) of a model-space box placed at `world`."""
    (x0, y0, z0), (x1, y1, z1) = bounds
    lo = [float("inf")] * 3
    hi = [float("-inf")] * 3
    for cx in (x0, x1):
        for cy in (y0, y1):
            for cz in (z0, z1):
                v = _rotate((cx * scale, cy * scale, cz * scale), *rotation)
                p = (world[0] + v[0], world[1] + v[1], world[2] + v[2])
                for i in range(3):
                    lo[i] = min(lo[i], p[i])
                    hi[i] = max(hi[i], p[i])
    return tuple(lo), tuple(hi)


def _file_extents(lo, hi):
    a = coords.world_to_file(*lo)
    b = coords.world_to_file(*hi)
    return (tuple(min(a[i], b[i]) for i in range(3)), tuple(max(a[i], b[i]) for i in range(3)))


def _footprint(spec, x0: float, x1: float, y0: float, y1: float, circle=None):
    """Chunks of the spec's tiles touched by the world rect [x0, x1] x [y0, y1] (or the circle inside it)."""
    out: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for (tx, ty) in spec.tiles:
        bx0, bx1, by0, by1 = coords.tile_bounds(tx, ty)
        if x1 < bx0 or x0 > bx1 or y1 < by0 or y0 > by1:
            continue
        chunks = []
        for iy in range(16):
            for ix in range(16):
                top_x, top_y = coords.chunk_top_left(tx, ty, ix, iy)
                cx0, cx1 = top_x - coords.CHUNK_SIZE, top_x
                cy0, cy1 = top_y - coords.CHUNK_SIZE, top_y
                if x1 < cx0 or x0 > cx1 or y1 < cy0 or y0 > cy1:
                    continue
                if circle is not None:
                    px, py, r = circle
                    dx = cx0 - px if px < cx0 else px - cx1 if px > cx1 else 0.0
                    dy = cy0 - py if py < cy0 else py - cy1 if py > cy1 else 0.0
                    if dx * dx + dy * dy > r * r:
                        continue
                chunks.append((ix, iy))
        if chunks:
            out[(tx, ty)] = chunks
    return out


def resolve_placements(spec, grid, assets=None) -> tuple[list[Resolved], list[Resolved], list[str]]:
    """Resolve every placement. `assets` (assets.AssetFolder) supplies real model bounds where the spec has none."""
    warnings: list[str] = []
    used: dict[int, str] = {}
    everything = [("doodads", i, p) for i, p in enumerate(spec.doodads)] + \
                 [("wmos", i, p) for i, p in enumerate(spec.wmos)]
    for group, i, p in everything:
        if p.uid is not None:
            if p.uid in used:
                raise SpecError(f"{group}[{i}].uid {p.uid} is already used by {used[p.uid]} (ids are unique across "
                                "doodads and WMOs)")
            used[p.uid] = f"{group}[{i}]"
    next_uid = spec.uid_base
    doodads: list[Resolved] = []
    wmos: list[Resolved] = []
    wx0, wx1, wy0, wy1 = spec.world_bounds()
    for group, i, p in everything:
        where = f"{group}[{i}]"
        r = Resolved()
        r.kind = p.kind
        r.model = p.model
        r.label = p.label
        if p.uid is None:
            while next_uid in used:
                next_uid += 1
            if next_uid > 0xFFFFFFFF:
                raise SpecError("ran out of unique ids above uid_base")
            used[next_uid] = where
            r.uid = next_uid
        else:
            r.uid = p.uid
        if not (wx0 <= p.x <= wx1 and wy0 <= p.y <= wy1):
            raise SpecError(f"{where}.position ({p.x:g}, {p.y:g}) is outside the map's tiles "
                            f"(X {wx0:.2f}..{wx1:.2f}, Y {wy0:.2f}..{wy1:.2f})")
        z = grid.ground_height(p.x, p.y) if p.z is None else p.z
        z += p.z_offset
        r.world = (p.x, p.y, z)
        r.file_pos = coords.world_to_file(p.x, p.y, z)
        r.rotation = p.rotation
        r.flags = p.flags
        r.radius = p.radius
        bounds = p.bounds
        r.bounds_source = "spec" if bounds is not None else "radius"
        if bounds is None and assets is not None:
            bounds = assets.model_bounds(p.model)
            if bounds is not None:
                r.bounds_source = "assets"
            else:
                warnings.append(f"{where}: {p.model!r} not found in the asset folder; using radius {p.radius:g}")
        if p.kind == "doodad":
            r.scale_u16 = max(1, min(0xFFFF, int(p.scale * 1024.0 + 0.5)))
            r.extents = None
            r.doodad_set = r.name_set = 0
            if bounds is not None:
                lo, hi = world_extents(r.world, p.rotation, r.scale_u16 / 1024.0, bounds)
                r.radius = max(abs(lo[0] - p.x), abs(hi[0] - p.x), abs(lo[1] - p.y), abs(hi[1] - p.y))
                r.footprint = _footprint(spec, lo[0], hi[0], lo[1], hi[1])
            else:
                r.footprint = _footprint(spec, p.x - p.radius, p.x + p.radius, p.y - p.radius, p.y + p.radius,
                                         (p.x, p.y, p.radius))
            doodads.append(r)
        else:
            # The client ignores MODF's scale; 1024 (= 1.0) keeps runtimes that do read it (WarcraftXL's dynamic
            # scaling) at the authored size.
            r.scale_u16 = 1024
            r.doodad_set = p.doodad_set
            r.name_set = p.name_set
            if bounds is not None:
                lo, hi = world_extents(r.world, p.rotation, 1.0, bounds)
                r.radius = max(abs(lo[0] - p.x), abs(hi[0] - p.x), abs(lo[1] - p.y), abs(hi[1] - p.y))
                r.footprint = _footprint(spec, lo[0], hi[0], lo[1], hi[1])
            else:
                rad = p.radius
                lo = (p.x - rad, p.y - rad, z - rad)
                hi = (p.x + rad, p.y + rad, z + rad)
                # The tiles and chunks follow the extents box (not a circle), so every tile the MODF extents reach
                # lists the WMO (validate.py checks this).
                r.footprint = _footprint(spec, lo[0], hi[0], lo[1], hi[1])
            r.extents = _file_extents(lo, hi)
            wmos.append(r)
        if not r.footprint:
            raise SpecError(f"{where}: its footprint touches no chunk of the map")
        if p.x - r.radius < wx0 or p.x + r.radius > wx1 or p.y - r.radius < wy0 or p.y + r.radius > wy1:
            warnings.append(f"{where} reaches past the edge of the map's tiles")
    return doodads, wmos, warnings
