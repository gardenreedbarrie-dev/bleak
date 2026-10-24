"""Build a map's terrain files from a JSON spec.

    python3 -I Tools/MapForge/terrain/build.py SPEC.json OUT_DIR [--force] [--no-preview] [--quiet]

Writes OUT_DIR/World/Maps/<Dir>/<Dir>.wdt, <Dir>.wdl and <Dir>_<tx>_<ty>.adt, OUT_DIR/pois.json (the named points
for the server's spawn tables, with resolved ground heights), OUT_DIR/terrain_manifest.json (placements, bounds,
file hashes) and the previews OUT_DIR/preview.png and OUT_DIR/heightmap.png. Same spec (and seed) = same bytes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from terrain import coords  # noqa: E402
from terrain.adt import build_adt  # noqa: E402
from terrain.heightmap import HeightField, LatticeGrid  # noqa: E402
from terrain.placements import resolve_placements  # noqa: E402
from terrain.spec import Spec, load_spec, parse_spec  # noqa: E402
from terrain.spec_errors import SpecError  # noqa: E402
from terrain.texturing import TexturePainter  # noqa: E402
from terrain.wdt_wdl import build_wdl, build_wdt  # noqa: E402

GENERATOR = "MapForge terrain 1"


class Context:
    def __init__(self, spec: Spec, assets=None):
        self.spec = spec
        self.warnings: list[str] = list(spec.warnings)
        self.field = HeightField(spec)
        self.grid = LatticeGrid(spec, self.field)
        self.painter = TexturePainter(spec, self.grid)
        self.doodads, self.wmos, w = resolve_placements(spec, self.grid, assets)
        self.warnings += w
        self.pois = []
        wx0, wx1, wy0, wy1 = spec.world_bounds()
        for m in spec.pois:
            if not (wx0 <= m["x"] <= wx1 and wy0 <= m["y"] <= wy1):
                raise SpecError(f"poi {m['name']!r} is outside the map's tiles")
            ground = self.grid.ground_height(m["x"], m["y"])
            z = (ground if m["z"] is None else m["z"]) + m["z_offset"]
            self.pois.append(dict(m, z=z, ground=ground))


class BuildResult:
    def __init__(self):
        self.files: dict[str, bytes] = {}  # relative path (forward slashes) -> bytes
        self.tiles = {}  # (tx, ty) -> TileResult
        self.context: Context | None = None
        self.manifest: dict = {}


def map_dir(spec: Spec) -> str:
    return f"World/Maps/{spec.directory}"


def build(spec: Spec, assets=None) -> BuildResult:
    """Build every file in memory. `assets` is an optional assets.AssetFolder for real model bounds."""
    ctx = Context(spec, assets)
    result = BuildResult()
    result.context = ctx
    base = map_dir(spec)
    holes = {}
    for tx, ty in spec.tiles:
        res = build_adt(ctx, tx, ty)
        result.tiles[(tx, ty)] = res
        result.files[f"{base}/{spec.directory}_{tx}_{ty}.adt"] = res.data
        holes[(tx, ty)] = res.holes
    result.files[f"{base}/{spec.directory}.wdt"] = build_wdt(spec)
    result.files[f"{base}/{spec.directory}.wdl"] = build_wdl(spec, ctx.grid, holes)
    result.files["pois.json"] = _pois_json(spec, ctx)
    ctx.border = border_check(spec, ctx.grid)
    if not ctx.border["closed"]:
        x, y = ctx.border["at"]
        ctx.warnings.append(f"players can walk from the map centre to the edge of the tiles (at {x}, {y}); add a "
                            f"steeper 'border' (slopes above {WALKABLE_SLOPE_DEG:g} degrees stop walking)")
    result.manifest = _manifest(spec, ctx, result)
    return result


WALKABLE_SLOPE_DEG = 50.0  # the client's walkable limit (steeper ground makes a character slide)


def border_check(spec: Spec, grid, max_slope_deg: float = WALKABLE_SLOPE_DEG) -> dict:
    """Can a player walk from the map centre to the edge of the tile range?

    Flood fill over the half-unit lattice; a step is walkable when its rise is at most tan(max_slope) per step.
    Water and models are ignored (swimming crosses water anyway), so this only proves the terrain ring is closed.
    """
    import math
    from collections import deque

    r0 = spec.ty0 * coords.LATTICE_PER_TILE
    c0 = spec.tx0 * coords.LATTICE_PER_TILE
    rows = (spec.ty1 - spec.ty0 + 1) * coords.LATTICE_PER_TILE + 1
    cols = (spec.tx1 - spec.tx0 + 1) * coords.LATTICE_PER_TILE + 1
    limit = math.tan(math.radians(max_slope_deg)) * coords.HALF_UNIT
    h = [[grid.get(r0 + r, c0 + c) for c in range(cols)] for r in range(rows)]
    seen = bytearray(rows * cols)
    start = (rows // 2, cols // 2)
    seen[start[0] * cols + start[1]] = 1
    queue = deque([start])
    closest = None
    while queue:
        r, c = queue.popleft()
        edge = min(r, c, rows - 1 - r, cols - 1 - c)
        if closest is None or edge < closest[0]:
            closest = (edge, r, c)
            if edge == 0:
                break
        hr = h[r]
        for nr, nc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
            if 0 <= nr < rows and 0 <= nc < cols and not seen[nr * cols + nc]:
                if abs(h[nr][nc] - hr[c]) <= limit:
                    seen[nr * cols + nc] = 1
                    queue.append((nr, nc))
    edge, r, c = closest
    return {"max_slope_deg": max_slope_deg, "closed": edge > 0,
            "closest_walkable_to_edge_yards": _round(edge * coords.HALF_UNIT),
            "at": [_round(coords.lattice_x(r0 + r)), _round(coords.lattice_y(c0 + c))]}


def _pois_json(spec: Spec, ctx: Context) -> bytes:
    """pois.json: the named points for the server's spawn tables (orb shrines, crate drops, storm centres)."""
    pois = [{"name": m["name"], "kind": m["kind"], "x": _round(m["x"]), "y": _round(m["y"]), "z": _round(m["z"]),
             "ground": _round(m["ground"]), "radius": m["radius"]} for m in ctx.pois]
    doc = {"generator": GENERATOR, "map_id": spec.map_id, "map_directory": spec.directory,
           "coordinates": "world (server .go xyz)", "pois": pois}
    return (json.dumps(doc, indent=2) + "\n").encode("ascii")


def _round(v: float) -> float:
    return float(f"{v:.3f}")


def _manifest(spec: Spec, ctx: Context, result: BuildResult) -> dict:
    x0, x1, y0, y1 = spec.world_bounds()
    heights = ctx.grid.h
    placements = []
    for p in ctx.doodads + ctx.wmos:
        placements.append({
            "kind": p.kind, "uid": p.uid, "model": p.model, "label": p.label,
            "world": [_round(v) for v in p.world], "rotation": [_round(v) for v in p.rotation],
            "bounds_source": p.bounds_source,
            "tiles": sorted([list(t) for t in p.footprint]),
        })
    files = {}
    for name in sorted(result.files):
        data = result.files[name]
        files[name] = {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    water_chunks = sum(len(t.water) for t in result.tiles.values())
    return {
        "generator": GENERATOR,
        "map_id": spec.map_id,
        "directory": spec.directory,
        "client_paths": {"wdt": f"World\\Maps\\{spec.directory}\\{spec.directory}.wdt",
                         "adt": f"World\\Maps\\{spec.directory}\\{spec.directory}_<tx>_<ty>.adt"},
        "tiles": [list(t) for t in spec.tiles],
        "world_bounds": {"min_x": _round(x0), "max_x": _round(x1), "min_y": _round(y0), "max_y": _round(y1)},
        "world_center": [_round((x0 + x1) * 0.5), _round((y0 + y1) * 0.5)],
        "height_range": [_round(min(heights)), _round(max(heights))],
        "area_ids": sorted({spec.area_id} | {a for a, _ in spec.areas}),
        "textures": [{"name": t.name, "path": t.path} for t in spec.textures],
        "placements": placements,
        "pois": [{"name": m["name"], "kind": m["kind"], "world": [_round(m["x"]), _round(m["y"]), _round(m["z"])],
                  "ground": _round(m["ground"]), "radius": m["radius"]} for m in ctx.pois],
        "water": [{"liquid_type": w["liquid_type"], "height": w["height"]} for w in spec.water],
        "water_chunks": water_chunks,
        "border": ctx.border,
        "warnings": ctx.warnings,
        "files": files,
    }


def write(result: BuildResult, out_dir: str, force: bool = False, preview: bool = True) -> list[str]:
    spec = result.context.spec
    target = os.path.join(out_dir, *map_dir(spec).split("/"))
    if os.path.exists(target):
        if not force:
            raise FileExistsError(f"{target} exists; pass --force to replace it")
        shutil.rmtree(target)
    written = []
    for name, data in sorted(result.files.items()):
        path = os.path.join(out_dir, *name.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        written.append(path)
    manifest_path = os.path.join(out_dir, "terrain_manifest.json")
    with open(manifest_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(result.manifest, f, indent=2, sort_keys=False)
        f.write("\n")
    written.append(manifest_path)
    if preview and spec.preview:
        from terrain.preview import render
        p1 = os.path.join(out_dir, "preview.png")
        p2 = os.path.join(out_dir, "heightmap.png")
        render(result.context, result.tiles, p1, p2)
        written += [p1, p2]
    return written


def build_from_file(spec_path: str) -> BuildResult:
    return build(load_spec(spec_path))


def build_from_dict(data: dict) -> BuildResult:
    return build(parse_spec(data))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build WDT, WDL and ADT files from a MapForge terrain spec.")
    ap.add_argument("spec", help="map spec (JSON)")
    ap.add_argument("out", help="output folder (World\\Maps\\<Dir> is created inside)")
    ap.add_argument("--force", action="store_true", help="replace an existing World/Maps/<Dir> in the output")
    ap.add_argument("--assets", help="folder of extracted client files, for real model bounds (optional)")
    ap.add_argument("--no-preview", action="store_true", help="skip preview.png and heightmap.png")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)
    assets = None
    if args.assets:
        from terrain.assets import AssetFolder
        assets = AssetFolder(args.assets)
    try:
        result = build(load_spec(args.spec), assets)
        written = write(result, args.out, force=args.force, preview=not args.no_preview)
    except (SpecError, FileExistsError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if not args.quiet:
        m = result.manifest
        b = m["world_bounds"]
        print(f"{m['directory']}: {len(m['tiles'])} tiles, X {b['min_x']}..{b['max_x']}, Y {b['min_y']}..{b['max_y']}, "
              f"heights {m['height_range'][0]}..{m['height_range'][1]}")
        print(f"  {len(m['placements'])} placements, {len(m['pois'])} pois, {m['water_chunks']} chunks with water")
        for w in m["warnings"]:
            print(f"  warning: {w}")
        for path in written:
            print(f"  wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
