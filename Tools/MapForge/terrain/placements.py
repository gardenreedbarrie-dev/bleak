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
from .noise import Fbm, hash32
from .shapes import Polyline
from .spec import Placement
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


def resolve_placements(spec, grid, assets=None, extra=None) -> tuple[list[Resolved], list[Resolved], list[str]]:
    """Resolve every placement. `assets` (assets.AssetFolder) supplies real model bounds where the spec has none.
    `extra` are generated doodads (scatter_placements); they come last, so their automatic ids never shift the
    spec's own placements."""
    warnings: list[str] = []
    used: dict[int, str] = {}
    everything = [("doodads", i, p) for i, p in enumerate(spec.doodads)] + \
                 [("wmos", i, p) for i, p in enumerate(spec.wmos)] + \
                 [("scatter", i, p) for i, p in enumerate(extra or [])]
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


# --- scatter ------------------------------------------------------------------------------------------------------


class _Rng:
    """xorshift32 seeded from a cell hash: the same group, seed and cell give the same numbers everywhere."""

    __slots__ = ("s",)

    def __init__(self, seed: int):
        self.s = (seed & 0xFFFFFFFF) or 0x6D2B79F5

    def next(self) -> int:
        s = self.s
        s ^= (s << 13) & 0xFFFFFFFF
        s ^= s >> 17
        s ^= (s << 5) & 0xFFFFFFFF
        self.s = s
        return s

    def unit(self) -> float:
        """[0, 1) with 24 bits: exact in every float format."""
        return (self.next() >> 8) / 16777216.0


class _Occupancy:
    """Discs already placed (centre, body radius), bucketed for the spacing tests."""

    def __init__(self, bucket: float):
        self.bucket = bucket
        self.cells: dict[tuple[int, int], list[tuple[float, float, float, int]]] = {}
        self.largest = 0.0

    def add(self, x: float, y: float, r: float, group: int) -> None:
        key = (int(x // self.bucket), int(y // self.bucket))
        self.cells.setdefault(key, []).append((x, y, r, group))
        self.largest = max(self.largest, r)

    def clear(self, x: float, y: float, r: float, group: int, spacing: float) -> bool:
        """True when a disc of radius r at (x, y) overlaps nothing (and keeps `spacing` from its own group)."""
        reach = max(spacing, r + self.largest)
        span = int(reach // self.bucket) + 1
        bx = int(x // self.bucket)
        by = int(y // self.bucket)
        for ix in range(bx - span, bx + span + 1):
            for iy in range(by - span, by + span + 1):
                for (ox, oy, orad, og) in self.cells.get((ix, iy), ()):
                    need = r + orad
                    if og == group and spacing > need:
                        need = spacing
                    dx = ox - x
                    dy = oy - y
                    if dx * dx + dy * dy < need * need:
                        return False
        return True


def _slope_ok(grid, x: float, y: float, min_nz: float) -> bool:
    """Every lattice normal around the point is at most the group's slope (normal.z >= cos(max slope))."""
    u, v = coords.world_to_lattice(x, y)
    r0 = int(u // 1)
    c0 = int(v // 1)
    for r in (r0, r0 + 1):
        for c in (c0, c0 + 1):
            if grid.normal(r, c)[2] < min_nz:
                return False
    return True


def _body_radius(p: Placement, share: float) -> float:
    """How far a spec placement keeps scattered doodads away: half its model box (bounds), else `share` of its
    footprint radius (a WMO's whole radius; half a doodad's, since trees and rocks are narrower at the ground)."""
    if p.bounds is not None:
        (x0, y0, _), (x1, y1, _) = p.bounds
        return max(abs(x0), abs(y0), abs(x1), abs(y1)) * p.scale
    return p.radius * share


def scatter_placements(spec, grid) -> tuple[list[Placement], list[dict]]:
    """Doodads of every scatter group, in group order: (placements, per-group stats).

    Each group throws one candidate into every cell of a grid of `cell` yards over its shape's box (jittered inside
    the cell by a hash of the group seed and the cell), in row order, or in a hashed order when the group has a
    `count`. A candidate stays when it is inside the shape and outside every `exclude`, passes the noise, slope,
    height and dry masks, keeps its clearances from roads, the river, POIs and the spec's own placements, and its
    body clears every doodad scattered before it (and `min_spacing` from its own group). Pure integer hashing and
    IEEE arithmetic: the same spec gives the same placements on every platform.
    """
    out: list[Placement] = []
    stats: list[dict] = []
    if not spec.scatter:
        return out, stats
    wx0, wx1, wy0, wy1 = spec.world_bounds()
    rivers = [(Polyline(list(f["path"]), f["width"]), f["width"] * 0.5) for f in spec.features
              if f["type"] == "river"]
    fixed = [(p.x, p.y, _body_radius(p, 1.0)) for p in spec.wmos] + \
            [(p.x, p.y, _body_radius(p, 0.5)) for p in spec.doodads]
    occupancy = _Occupancy(16.0)
    for gi, g in enumerate(spec.scatter):
        seed = (spec.seed * 2654435761 + g["seed"] * 40503 + gi * 977 + 17) & 0xFFFFFFFF
        cell = g["cell"]
        x0, x1, y0, y1 = g["shape"].bbox() if g["shape"] is not None else (wx0, wx1, wy0, wy1)
        nx = int((x1 - x0) / cell) + 1
        ny = int((y1 - y0) / cell) + 1
        cells = [(i, j) for i in range(nx) for j in range(ny)]
        if g["count"] is not None:
            cells.sort(key=lambda ij: (hash32(ij[0], ij[1], seed ^ 0x5BD1E995), ij))
        noise = None
        if g["noise"] is not None:
            n = g["noise"]
            noise = Fbm((seed * 131 + n["seed"] * 977 + 5) & 0xFFFFFFFF, n["scale"], 1.0, n["octaves"])
        weights = [m["weight"] for m in g["models"]]
        total = sum(weights)
        clear = g["clearance"]
        pois = [(p["x"], p["y"], p["radius"]) for p in spec.pois
                if g["poi_kinds"] is None or p["kind"] in g["poi_kinds"]]
        placed = 0
        rejected = {"outside": 0, "noise": 0, "slope": 0, "height": 0, "wet": 0, "roads": 0, "river": 0, "pois": 0,
                    "placements": 0, "spacing": 0}
        for (i, j) in cells:
            if g["count"] is not None and placed >= g["count"]:
                break
            rng = _Rng(hash32(i, j, seed))
            x = x0 + (i + rng.unit()) * cell
            y = y0 + (j + rng.unit()) * cell
            pick = rng.unit() * total
            k = 0
            while k < len(weights) - 1 and pick >= weights[k]:
                pick -= weights[k]
                k += 1
            model = g["models"][k]
            lo, hi = model["scale"]
            scale = lo + (hi - lo) * rng.unit()
            facing_t = rng.unit()
            body = model["body"] * scale
            # The model's footprint stays on the tiles (resolve_placements warns about anything reaching past them).
            footprint = model["radius"] * scale
            if not (wx0 + footprint <= x <= wx1 - footprint and wy0 + footprint <= y <= wy1 - footprint):
                rejected["outside"] += 1
                continue
            if (g["shape"] is not None and not g["shape"].contains(x, y)) or \
                    any(s.contains(x, y) for s in g["exclude"]):
                rejected["outside"] += 1
                continue
            if noise is not None:
                n = g["noise"]
                if coords.smoothstep((noise(x, y) - n["threshold"]) / n["fade"] + 0.5) <= rng.unit():
                    rejected["noise"] += 1
                    continue
            if g["slope"] is not None and not _slope_ok(grid, x, y, g["slope"]):
                rejected["slope"] += 1
                continue
            ground = grid.ground_height(x, y)
            if g["height"] is not None and not (g["height"][0] <= ground <= g["height"][1]):
                rejected["height"] += 1
                continue
            if g["dry"] and any(w["shape"].contains(x, y) and ground < w["height"] + 0.25 for w in spec.water):
                rejected["wet"] += 1
                continue
            if clear["roads"] is not None and any(r["shape"].distance(x, y) < clear["roads"] + body
                                                  for r in spec.roads):
                rejected["roads"] += 1
                continue
            if clear["river"] is not None and any(line.center_distance(x, y) - half < clear["river"] + body
                                                  for line, half in rivers):
                rejected["river"] += 1
                continue
            if clear["pois"] is not None and any((px - x) ** 2 + (py - y) ** 2 < (pr + clear["pois"] + body) ** 2
                                                 for px, py, pr in pois):
                rejected["pois"] += 1
                continue
            cp = clear["placements"]
            if any((px - x) ** 2 + (py - y) ** 2 < (pr + cp + body) ** 2 for px, py, pr in fixed):
                rejected["placements"] += 1
                continue
            if not occupancy.clear(x, y, body, gi, g["min_spacing"]):
                rejected["spacing"] += 1
                continue
            occupancy.add(x, y, body, gi)
            facing = g["facing"] if g["facing"] is not None else facing_t * 360.0
            placed += 1
            out.append(Placement("doodad", model["model"], x, y, None, model["z_offset"],
                                 (0.0, (facing - 180.0) % 360.0, 0.0), scale, None, model["radius"] * scale, 0, None,
                                 0, 0, f"{g['name']} #{placed}"))
        stats.append({"name": g["name"], "candidates": len(cells), "placed": placed, "rejected": rejected})
    return out, stats
