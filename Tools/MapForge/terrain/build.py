"""Build a map's terrain files from a JSON spec.

    python3 -I Tools/MapForge/terrain/build.py SPEC.json OUT_DIR [--force] [--no-preview] [--quiet]
        [--assets DIR] [--resolution asset_resolution.json]

Writes OUT_DIR/World/Maps/<Dir>/<Dir>.wdt, <Dir>.wdl and <Dir>_<tx>_<ty>.adt, OUT_DIR/pois.json (the named points
for the server's spawn tables, with resolved ground heights), OUT_DIR/terrain_manifest.json (placements, bounds,
file hashes) and the previews OUT_DIR/preview.png and OUT_DIR/heightmap.png. Same spec (and seed) = same bytes.

With extra assets resolved (--resolution, from package.py resolve-assets) it also writes OUT_DIR/extra_assets/
(the modern files the tiles use, for the map archive) and, when modern doodads are placed, OUT_DIR/server/
World/Maps/<Dir>/: the same map without them, the copy the server's extractors read.
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
from terrain.extra_assets import Resolution, ResolutionError  # noqa: E402
from terrain.heightmap import HeightField, LatticeGrid  # noqa: E402
from terrain.placements import resolve_placements, scatter_placements  # noqa: E402
from terrain.spec import Spec, load_spec, parse_spec  # noqa: E402
from terrain.spec_errors import SpecError  # noqa: E402
from terrain.texturing import TexturePainter  # noqa: E402
from terrain.water import water_bodies  # noqa: E402
from terrain.wdt_wdl import build_wdl, build_wdt  # noqa: E402

GENERATOR = "MapForge terrain 1"
POI_BELOW_GROUND = 0.25  # a POI this far below the terrain gets a warning


class Context:
    def __init__(self, spec: Spec, assets=None):
        self.spec = spec
        self.warnings: list[str] = list(spec.warnings)
        self.field = HeightField(spec)
        self.grid = LatticeGrid(spec, self.field)
        self.painter = TexturePainter(spec, self.grid)
        self.scattered, self.scatter_stats = scatter_placements(spec, self.grid)
        self.doodads, self.wmos, w = resolve_placements(spec, self.grid, assets, self.scattered)
        self.warnings += w
        self.water_stats: dict = {}
        self.extra_files: list[dict] = []
        self.border = None
        self.texture_overflow: list[dict] = []
        by_label: dict[str, list] = {}
        for p in self.doodads + self.wmos:
            if p.label:
                by_label.setdefault(p.label, []).append(p)
        self.pois = []
        wx0, wx1, wy0, wy1 = spec.world_bounds()
        for m in spec.pois:
            if not (wx0 <= m["x"] <= wx1 and wy0 <= m["y"] <= wy1):
                raise SpecError(f"poi {m['name']!r} is outside the map's tiles")
            ground = self.grid.ground_height(m["x"], m["y"])
            if m["z_from"] is not None:
                found = by_label.get(m["z_from"], [])
                if len(found) != 1:
                    raise SpecError(f"poi {m['name']!r}: z_from {m['z_from']!r} names {len(found)} placements "
                                    "(it must name exactly one WMO or doodad label)")
                z = found[0].world[2] + m["z_offset"]
                source = f"placement:{m['z_from']}"
            elif m["z"] is None:
                z = ground + m["z_offset"]
                source = "ground"
            else:
                z = m["z"] + m["z_offset"]
                source = "explicit"
            if z < ground - POI_BELOW_GROUND:
                self.warnings.append(f"poi {m['name']!r} is {ground - z:.2f} yards below the terrain (z {z:.2f}, "
                                     f"ground {ground:.2f}): a server object there would spawn underground")
            self.pois.append(dict(m, z=z, ground=ground, z_source=source))


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
    if any(d.modern for d in ctx.doodads):
        # The server's extract copy: the same tiles without the modern doodads, so vmap4_extractor only reads 3.3.5
        # models (they are decoration: no collision or line of sight on the server).
        for tx, ty in spec.tiles:
            res = build_adt(ctx, tx, ty, keep_doodad=lambda d: not d.modern, base=result.tiles[(tx, ty)])
            result.files[f"{SERVER_DIR}/{base}/{spec.directory}_{tx}_{ty}.adt"] = res.data
        for ext in ("wdt", "wdl"):
            result.files[f"{SERVER_DIR}/{base}/{spec.directory}.{ext}"] = result.files[f"{base}/{spec.directory}.{ext}"]
    ctx.extra_files = _extra_files(spec, result, ctx)
    result.files["pois.json"] = _pois_json(spec, ctx)
    ctx.texture_overflow = texture_overflow(result.tiles)
    if ctx.texture_overflow:
        names = sorted({spec.textures[k].name for c in ctx.texture_overflow for k in c["dropped"]})
        ctx.warnings.append(f"{len(ctx.texture_overflow)} chunks hold more than 4 textures; dropped there: "
                            f"{', '.join(names)} (keep regional layers at least one chunk apart)")
    ctx.border = border_check(spec, ctx.grid, field=ctx.field)
    if not ctx.border["closed"]:
        x, y = ctx.border["at"]
        ctx.warnings.append(f"players can walk or swim to the edge of the tiles (at {x}, {y}); add a "
                            f"steeper 'border' (slopes above {WALKABLE_SLOPE_DEG:g} degrees stop walking)")
    m = ctx.border.get("mountains")
    if m and m["past_cliff"]:
        x, y = m["at"]
        ctx.warnings.append(f"players can walk {m['deepest_yards']:g} yards into the mountains (at {x}, {y}), past "
                            "the cliff at their foot; make the cliff higher or steeper there")
    for use in spec.assets:
        if use.modern_used and use.kind == "doodad" and use.entry.get("collision"):
            ctx.warnings.append(f"{use.where}: the modern model {use.modern!r} has collision geometry; the client "
                                "collides with it, the server (which never sees it) does not")
    result.manifest = _manifest(spec, ctx, result)
    return result


WALKABLE_SLOPE_DEG = 50.0  # the client's walkable limit (steeper ground makes a character slide)
SERVER_DIR = "server"
EXTRA_DIR = "extra_assets"


def _extra_files(spec: Spec, result: BuildResult, ctx: Context) -> list[dict]:
    """Copy the modern files the tiles use (from the resolution's files/) into extra_assets/."""
    out = []
    seen = set()
    for use in spec.assets:
        if not use.modern_used:
            continue
        for f in spec.resolution.files_for(use.modern):
            key = f["path"].replace("/", "\\").lower()
            if key in seen:
                continue
            seen.add(key)
            try:
                with open(f["file"], "rb") as fh:
                    data = fh.read()
            except OSError as e:
                raise SpecError(f"{use.where}: the resolution's copy of {f['path']!r} is unreadable ({e.strerror}); "
                                "run package.py resolve-assets again") from None
            digest = hashlib.sha256(data).hexdigest()
            if f.get("sha256") and f["sha256"] != digest:
                raise SpecError(f"{use.where}: {f['path']!r} changed since resolve-assets (sha256 differs)")
            rel = f"{EXTRA_DIR}/" + f["path"].replace("\\", "/")
            result.files[rel] = data
            out.append({"path": f["path"], "file": rel, "size": len(data), "sha256": digest})
    return sorted(out, key=lambda e: e["path"].lower())


def texture_overflow(tiles: dict) -> list[dict]:
    """Chunks where a texture above the layer threshold did not fit into the client's 4 layers."""
    out = []
    for (tx, ty) in sorted(tiles):
        for (ix, iy), tex in sorted(tiles[(tx, ty)].texturing.items()):
            if tex.dropped:
                out.append({"tile": [tx, ty], "chunk": [ix, iy], "dropped": list(tex.dropped)})
    return out


def border_check(spec: Spec, grid, max_slope_deg: float = WALKABLE_SLOPE_DEG, field=None,
                 surface: bool | None = None) -> dict:
    """Can a player walk or swim to the edge of the tile range?

    Flood fill over the half-unit lattice from the map centre (with mountains, from the whole valley, below); a
    step is walkable when its rise is at most tan(max_slope) per step.
    Models are ignored, so this only proves the terrain ring is closed. Water is crossed by swimming: a point under
    water counts at the water surface, and the slope of its bed never stops the fill (a carved channel's sides are
    steeper than walking allows, but only the lip stands above the water).

    `surface` (the default when the spec has mountains) also needs walkable ground under each point: its normal at
    most max_slope from vertical. The client stops a character on a steeper surface whichever way it walks, and a
    range's foot is never straight, so a rise per step alone would let the fill zigzag up an oblique cliff. With
    mountains (and the height `field`) the fill starts from every walkable point of the valley, since players can
    be dropped anywhere in it (a steep spot or a river at the centre must not hide a way out), and the result also
    says how far into the range the walkable ground reaches: past the cliff at the foot means players can leave
    the valley there.
    """
    import math
    from collections import deque

    r0 = spec.ty0 * coords.LATTICE_PER_TILE
    c0 = spec.tx0 * coords.LATTICE_PER_TILE
    rows = (spec.ty1 - spec.ty0 + 1) * coords.LATTICE_PER_TILE + 1
    cols = (spec.tx1 - spec.tx0 + 1) * coords.LATTICE_PER_TILE + 1
    limit = math.tan(math.radians(max_slope_deg)) * coords.HALF_UNIT
    h = [[grid.get(r0 + r, c0 + c) for c in range(cols)] for r in range(rows)]
    wet = bytearray(rows * cols)
    for body in water_bodies(spec):
        # The lowest water over the ground, as water_level_at gives it, on the lattice points of the body's box.
        bx0, bx1, by0, by1 = body.bbox
        r_lo = max(0, int(math.floor(coords.LATTICE_ORIGIN - bx1 * 12.0 / 25.0)) - r0)
        r_hi = min(rows - 1, int(math.ceil(coords.LATTICE_ORIGIN - bx0 * 12.0 / 25.0)) - r0)
        c_lo = max(0, int(math.floor(coords.LATTICE_ORIGIN - by1 * 12.0 / 25.0)) - c0)
        c_hi = min(cols - 1, int(math.ceil(coords.LATTICE_ORIGIN - by0 * 12.0 / 25.0)) - c0)
        for r in range(r_lo, r_hi + 1):
            x = coords.lattice_x(r0 + r)
            for c in range(c_lo, c_hi + 1):
                level = body.probe(x, coords.lattice_y(c0 + c))
                if level is not None and grid.get(r0 + r, c0 + c) < level and (not wet[r * cols + c]
                                                                                or level < h[r][c]):
                    h[r][c] = level
                    wet[r * cols + c] = 1
    seen = bytearray(rows * cols)
    if surface is None:
        surface = bool(spec.mountain_features())
    if surface:
        # Points under a steeper surface are marked as seen, so the fill never enters them (a swimmer is not
        # stopped by the bed under it).
        min_nz = coords.dcos(max_slope_deg)
        for r in range(rows):
            for c in range(cols):
                if not wet[r * cols + c] and grid.normal(r0 + r, c0 + c)[2] < min_nz:
                    seen[r * cols + c] = 2
    ranges = spec.mountain_features()
    depth = None
    queue = deque()
    if ranges and field is not None:
        # Players can be dropped anywhere in the valley: every walkable point of it starts the fill.
        depth = [field.mountain_depth(coords.lattice_x(r0 + r), coords.lattice_y(c0 + c))
                 for r in range(rows) for c in range(cols)]
        for i in range(rows * cols):
            if not seen[i] and depth[i] <= 0.0:
                seen[i] = 1
                queue.append(divmod(i, cols))
    if not queue:
        start = (rows // 2, cols // 2)
        seen[start[0] * cols + start[1]] = 1
        queue.append(start)
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
    out = {"max_slope_deg": max_slope_deg, "closed": edge > 0,
           "closest_walkable_to_edge_yards": _round(edge * coords.HALF_UNIT),
           "at": [_round(coords.lattice_x(r0 + r)), _round(coords.lattice_y(c0 + c))]}
    if surface:
        out["surface_slope_checked"] = True
    if depth is not None:
        deepest = None
        at = (0, 0)
        for i in range(rows * cols):
            if seen[i] != 1:
                continue
            t = depth[i]
            if deepest is None or t > deepest:
                deepest = t
                at = divmod(i, cols)
        cliff = min(f["cliff_width"] for f in ranges)
        out["mountains"] = {"foot_yards": min(f["width"] for f in ranges), "deepest_yards": _round(deepest),
                            "past_cliff": deepest > cliff,
                            "at": [_round(coords.lattice_x(r0 + at[0])), _round(coords.lattice_y(c0 + at[1]))]}
    return out


def poi_counts(pois: list[dict]) -> dict:
    """{kind: count}, with crates and buff orbs also counted per param ("crate:1", "orb_buff:3")."""
    counts: dict[str, int] = {}
    for m in pois:
        counts[m["kind"]] = counts.get(m["kind"], 0) + 1
        if m["kind"] in ("crate", "orb_buff"):
            key = f"{m['kind']}:{m['param']}"
            counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _pois_json(spec: Spec, ctx: Context) -> bytes:
    """pois.json: the named points for the server's spawn tables (bh_royale_poi: crates, orbs, landmarks, the lobby,
    supply and final sites), with resolved heights. `z` is what the server uses; `ground` the terrain height."""
    pois = [{"id": m["id"], "name": m["name"], "kind": m["kind"], "title": m["title"], "x": _round(m["x"]),
             "y": _round(m["y"]), "z": _round(m["z"]), "ground": _round(m["ground"]), "z_source": m["z_source"],
             "facing": _round(m["facing"]), "radius": m["radius"], "weight": m["weight"], "param": m["param"]}
            for m in ctx.pois]
    world = spec.world_bounds()
    doc = {"generator": GENERATOR, "map_id": spec.map_id, "map_directory": spec.directory,
           "coordinates": "world (server .go xyz); facing in degrees, 0 = north (+X), counter-clockwise",
           "world_bounds": {"min_x": _round(world[0]), "max_x": _round(world[1]), "min_y": _round(world[2]),
                            "max_y": _round(world[3])},
           "counts": poi_counts(ctx.pois), "pois": pois}
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
        "pois": [{"id": m["id"], "name": m["name"], "kind": m["kind"],
                  "world": [_round(m["x"]), _round(m["y"]), _round(m["z"])], "ground": _round(m["ground"]),
                  "radius": m["radius"]} for m in ctx.pois],
        "poi_counts": poi_counts(ctx.pois),
        "roads": [{"name": r["name"], "width": r["width"], "points": [[_round(v) for v in p] for p in r["points"]]}
                  for r in spec.roads],
        "scatter": ctx.scatter_stats,
        "doodad_count": len(ctx.doodads),
        "wmo_count": len(ctx.wmos),
        "texture_overflow_chunks": len(ctx.texture_overflow),
        "water": [{"liquid_type": w["liquid_type"], "height": w["height"]} for w in spec.water],
        "water_chunks": water_chunks,
        "border": ctx.border,
        "warnings": ctx.warnings,
        "files": files,
    } | _manifest_v2(spec, ctx)


def _manifest_v2(spec: Spec, ctx: Context) -> dict:
    """Manifest keys for mountains, lakes, rivers, beaches and extra assets (only when the spec uses them)."""
    out = {}
    ranges = spec.mountain_features()
    if ranges:
        out["mountains"] = [{"width": f["width"], "height": list(f["height"]),
                             "cliff": [f["cliff_height"], f["cliff_width"]], "layers": f["layers"],
                             "saddles": f["saddles"], "ledges": f["ledges"]} for f in ranges]
    if spec.lakes:
        out["lakes"] = [{"name": lk["name"], "liquid_type": lk["liquid_type"], "level": lk["level"],
                         "islands": len(lk["islands"])} for lk in spec.lakes]
    if spec.rivers:
        out["rivers"] = [{"name": r["name"], "liquid_type": r["liquid_type"], "levels": r["levels"],
                          "falls": [{"at": [_round(f["x"]), _round(f["y"])], "top": f["top"], "bottom": f["bottom"],
                                     "facing": _round(f["facing"])} for f in r["falls"]],
                          "waterfall_doodads": len([p for p in spec.generated
                                                    if p.label.startswith(r["name"] + " ")])} for r in spec.rivers]
    if spec.lakes or spec.rivers or ctx.water_stats:
        out["water_merged_chunks"] = ctx.water_stats.get("merged_chunks", 0)
        out["water_dropped_cells"] = ctx.water_stats.get("dropped_cells", 0)
    if spec.beaches is not None:
        b = spec.beaches
        out["beaches"] = {k: (spec.textures[b[k]].name if b[k] is not None else None)
                          for k in ("sand", "wet_sand", "riverbed", "lakebed")} | \
                         {k: b[k] for k in ("width", "height", "wet_width", "wet_depth", "slope_max")}
    if spec.assets:
        out["extra_assets"] = [{"where": u.where, "kind": u.kind, "modern": u.modern, "fallback": u.fallback,
                                "path": u.path, "modern_used": u.modern_used, "reason": u.reason}
                               for u in spec.assets]
        out["extra_files"] = ctx.extra_files
        modern = [d for d in ctx.doodads if d.modern]
        out["server_tiles"] = f"{SERVER_DIR}/{map_dir(spec)}" if modern else None
        out["server_doodads_left_out"] = len(modern)
    return out


def write(result: BuildResult, out_dir: str, force: bool = False, preview: bool = True) -> list[str]:
    spec = result.context.spec
    target = os.path.join(out_dir, *map_dir(spec).split("/"))
    if os.path.exists(target):
        if not force:
            raise FileExistsError(f"{target} exists; pass --force to replace it")
        shutil.rmtree(target)
    # A rebuild must not leave an older build's extract tiles or extra files behind.
    for stale in (os.path.join(out_dir, SERVER_DIR, *map_dir(spec).split("/")), os.path.join(out_dir, EXTRA_DIR)):
        if os.path.exists(stale):
            if not force:
                raise FileExistsError(f"{stale} exists; pass --force to replace it")
            shutil.rmtree(stale)
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


def build_from_file(spec_path: str, resolution: Resolution | None = None) -> BuildResult:
    return build(load_spec(spec_path, resolution))


def build_from_dict(data: dict, resolution: Resolution | None = None) -> BuildResult:
    return build(parse_spec(data, resolution))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build WDT, WDL and ADT files from a MapForge terrain spec.")
    ap.add_argument("spec", help="map spec (JSON)")
    ap.add_argument("out", help="output folder (World\\Maps\\<Dir> is created inside)")
    ap.add_argument("--force", action="store_true", help="replace an existing World/Maps/<Dir> in the output")
    ap.add_argument("--assets", help="folder of extracted client files, for real model bounds (optional)")
    ap.add_argument("--resolution", help="asset_resolution.json from package.py resolve-assets: the modern files "
                                         "found for the spec's extra assets (without it every one falls back)")
    ap.add_argument("--no-preview", action="store_true", help="skip preview.png and heightmap.png")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)
    assets = None
    if args.assets:
        from terrain.assets import AssetFolder
        assets = AssetFolder(args.assets)
    try:
        resolution = Resolution.load(args.resolution) if args.resolution else None
        result = build(load_spec(args.spec, resolution), assets)
        written = write(result, args.out, force=args.force, preview=not args.no_preview)
    except (SpecError, ResolutionError, FileExistsError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if not args.quiet:
        m = result.manifest
        b = m["world_bounds"]
        print(f"{m['directory']}: {len(m['tiles'])} tiles, X {b['min_x']}..{b['max_x']}, Y {b['min_y']}..{b['max_y']}, "
              f"heights {m['height_range'][0]}..{m['height_range'][1]}")
        print(f"  {len(m['placements'])} placements ({m['doodad_count']} doodads, {m['wmo_count']} WMOs), "
              f"{len(m['pois'])} pois, {m['water_chunks']} chunks with water")
        for g in m["scatter"]:
            print(f"  scatter {g['name']}: {g['placed']} of {g['candidates']} candidates")
        if m["poi_counts"]:
            print("  pois: " + ", ".join(f"{k} {v}" for k, v in m["poi_counts"].items()))
        if "extra_assets" in m:
            used = sum(1 for u in m["extra_assets"] if u["modern_used"])
            print(f"  extra assets: {used} of {len(m['extra_assets'])} uses modern, {len(m['extra_files'])} files to "
                  f"pack; server tiles: {m['server_tiles'] or 'same as the client'}")
        for w in m["warnings"]:
            print(f"  warning: {w}")
        for path in written:
            print(f"  wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
