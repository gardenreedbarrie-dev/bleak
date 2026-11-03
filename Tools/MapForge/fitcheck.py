"""Fit check: would the world's spawns still stand on the ground if a new map pack replaced the terrain?

    python3 -I Tools/MapForge/fitcheck.py --new /root/maps-incoming/Maps.7z --server DATA_DIR \\
        --spawns spawns.tsv --maps azeroth,kalimdor --out REPORT_DIR [--work DIR]

--new        the new map files: a .7z (read one map at a time with the system's 7z, never unpacked whole) or a
             folder with world/maps/<map>/ below it (or a map folder itself). 3.3.5 single-file ADTs and split
             modern ADTs (only the root <map>_<x>_<y>.adt is read; _tex0/_obj0/_obj1/_lod are skipped) both work.
--server     the server's client-data folder (holding maps/ and dbc/) or its maps/ folder: the current ground,
             from the .map files (map id from the file names). Or instead:
--old-adts   a folder of the old ADTs (world/maps/<map>/ below it) as the current ground.
--spawns     TSV: guid, entry, kind (creature or go), map, x, y, z [, name]; a header line is skipped.
--map-dbc    Map.dbc for the server's map ids; default: the server's dbc/Map.dbc, else the new files'
             DBFilesClient/Map.dbc. --area-dbc likewise for AreaTable.dbc (zone names). --liquid-dbc: LiquidType.dbc
             for the water of the new ADTs; default: the new files' (map_extractor reads it through the MPQ chain),
             else the server's.
--maps       map folder names or ids, comma separated, or "all" (default: every map of the new files).
--out        the report folder: summary.txt, nonfine_spawns.csv, report.json, heatmap_<id>_<map>.png.
--work       where temporary files go (default: the system's temp folder); --min-free-mb (default 2048) must
             stay free there, and --batch-mb (default 1500) caps one extraction batch.
--quiet      leave out the long summary at the end (fitcheck.sh prints its own); the progress lines stay.

The new files are an overlay (Maps.7z is a patch-z.MPQ): map_extractor and the client read every file through the
MPQ chain, so a tile the new files do not carry keeps the base client's ADT. When the new files have the map's WDT,
its tiles are the ones that exist: a listed tile without a new ADT keeps the base one (unchanged), a server tile it
does not list is lost, and a new ADT it does not list is never loaded (skipped). Without a new WDT the base one
stays, and every server tile without a new ADT is unchanged.

When the new files have a Map.dbc, it is the one a new extraction (and the client) would read: a map the server
knows is read from the folder that Map.dbc names for its id, and a map id it does not have gets no new files.

Exit code: 0 = every requested map was compared, every spawn is fine and the ground (heights, holes, area ids and
water) is the same; 1 = some spawns are shifted or broken, or the ground changed; 2 = it could not run; 3 = nothing
moved, but not everything was checked: a requested map (not a map the server knows, no terrain on either side,
nothing of it in the new files), the water of split ADTs ("NOT CHECKED" in summary.txt), or maps of the server
that the new files also carry but that were not asked for ("NOT ASKED FOR"). 130 (143, 129) = stopped by Ctrl-C
(SIGTERM, SIGHUP): nothing was changed and the temporary files are deleted. fitcheck_report.judge says how each
spawn is decided; the README ("Fit check") says how to read the report.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import sys
import tempfile
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import fitcheck_formats as ff  # noqa: E402
import fitcheck_report as fr  # noqa: E402
import fitcheck_source as fs  # noqa: E402

MB = 1024 * 1024
EXIT_SAME, EXIT_CHANGED, EXIT_ERROR, EXIT_NOT_CHECKED = 0, 1, 2, 3
SAME_LIMIT = 0.01  # yd: a point closer than this (or than the .map file's rounding) has not moved
WATER_LIMIT = 0.01  # yd: a water level closer than this has not moved
WATER_SPAWN_MARGIN = 2.0  # yd: a spawn this far above the water (or lower) is at the water or in it


class Spawn:
    __slots__ = ("guid", "entry", "kind", "map_id", "x", "y", "z", "name")

    def __init__(self, guid, entry, kind, map_id, x, y, z, name=""):
        self.guid, self.entry, self.kind, self.map_id = guid, entry, kind, map_id
        self.x, self.y, self.z, self.name = x, y, z, name


def read_spawns(path: str) -> tuple[list[Spawn], list[str]]:
    spawns, problems = [], []
    with open(path, encoding="utf-8", errors="replace") as f:
        for n, line in enumerate(f, 1):
            line = line.rstrip("\r\n")
            if not line.strip() or line.startswith("#"):
                continue
            cols = line.split("\t")
            if len(cols) < 7:
                problems.append(f"{path}:{n}: {len(cols)} columns, 7 needed")
                continue
            try:
                guid, entry, map_id = int(cols[0]), int(cols[1]), int(cols[3])
                x, y, z = float(cols[4]), float(cols[5]), float(cols[6])
            except ValueError:
                if n == 1:
                    continue  # a header
                problems.append(f"{path}:{n}: not numbers")
                continue
            kind = cols[2].strip().lower()
            kind = {"gameobject": "go", "gobject": "go", "c": "creature", "g": "go"}.get(kind, kind)
            name = cols[7].strip() if len(cols) > 7 else ""
            spawns.append(Spawn(guid, entry, kind, map_id, x, y, z, name))
    return spawns, problems


class MapResult:
    def __init__(self, map_id, name, folder):
        self.map_id = map_id
        self.name = name
        self.folder = folder
        self.notes: list[str] = []
        self.chunk_delta: dict[tuple[int, int], list[float]] = {}
        self.old_only: set[tuple[int, int]] = set()  # the server has ground, the new files drop the tile
        self.new_only: set[tuple[int, int]] = set()
        self.base_kept: set[tuple[int, int]] = set()  # server tiles the new files do not carry: the base ADT stays
        self.pack_empty = False  # the new files have no ADT and no WDT for this map
        self.terrain = {"n": 0, "sum": 0.0, "max_abs": 0.0, "max_signed": 0.0, "max_at": (0.0, 0.0),
                        "max_tile": (0, 0), "over_fine": 0, "over_broken": 0, "same_tiles": 0,
                        "changed_points": 0, "max_excess": 0.0, "tolerance_max": SAME_LIMIT}
        self.holes_changed = 0
        self.areas_changed = 0
        # the water (the .map's MLIQ against what ConvertADT would write): cells that differ, of which gained
        # (water where there was none), lost, other (another type or level); tiles whose water was not read
        self.water = {"cells": 0, "gained": 0, "lost": 0, "other": 0, "max_level": 0.0, "max_at": None,
                      "tiles": set(), "unknown": set(), "flags_unknown": set()}
        self.water_chunks: dict[tuple[int, int], set] = {}  # tile -> chunk indices (iy * 16 + ix) whose water differs
        self.water_spawns: list[dict] = []  # spawns at or in water that differs
        self.refused: list[tuple[tuple[int, int], str]] = []  # new tiles map_extractor would refuse, and why
        self.lost_why = ""  # set when the new files give this map no ground at all (their Map.dbc lacks its id)
        self.zones: dict = {}
        self.spawns: list[dict] = []
        self.class_counts: dict[str, int] = {}

    def to_json(self) -> dict:
        ts = dict(self.terrain)
        ts["mean"] = ts["sum"] / ts["n"] if ts["n"] else None
        state, why = fr.map_state(self)
        return {"map_id": self.map_id, "name": self.name, "folder": self.folder, "notes": self.notes,
                "state": state, "state_reason": why,
                "tiles_shared": len(self.chunk_delta), "tiles_old_only": sorted(self.old_only),
                "tiles_new_only": sorted(self.new_only), "tiles_base_kept": sorted(self.base_kept),
                "terrain": ts, "holes_changed": self.holes_changed,
                "areas_changed": self.areas_changed,
                "water": {"cells_changed": self.water["cells"], "gained": self.water["gained"],
                          "lost": self.water["lost"], "other": self.water["other"],
                          "max_level_change": self.water["max_level"], "tiles_changed": sorted(self.water["tiles"]),
                          "tiles_not_compared": sorted(self.water["unknown"]),
                          "tiles_flags_unknown": sorted(self.water["flags_unknown"]),
                          "spawns_in_changed_water": [r["guid"] for r in self.water_spawns]},
                "tiles_refused": [{"tile": list(tl), "why": why} for tl, why in self.refused],
                "spawns": self.class_counts,
                "zones": {z["label"]: {"ground_mean": (z["sum"] / z["n"]) if z["n"] else None,
                                       "ground_max": z["max"] if z["n"] else None, "spawns": z["spawns"]}
                          for z in self.zones.values()}}


class Zones:
    def __init__(self, areas: dict[int, tuple[int, str]] | None):
        self.areas = areas or {}

    def key(self, area: int | None, tile: tuple[int, int]) -> tuple[str, str]:
        if area and self.areas:
            zone, name = self.areas.get(area, (area, ""))
            zname = self.areas.get(zone, (zone, ""))[1] or name
            return f"zone{zone}", (zname or f"area {area}") + f" ({zone})"
        if area:
            return f"area{area}", f"area {area}"
        return f"tile{tile}", f"tile {tile[0]},{tile[1]}"


def _zone(res: MapResult, key: str, label: str) -> dict:
    z = res.zones.get(key)
    if z is None:
        z = res.zones[key] = {"label": label, "n": 0, "sum": 0.0, "max": None, "spawns": {}}
    return z


def _vertex_heights(g: ff.TileGrid | None):
    if g is None:
        return None, None
    if g.kind == "flat":
        return [g.base] * (129 * 129), [g.base] * (128 * 128)
    if g.kind == "float":
        return list(g.v9), list(g.v8)
    m, b = g.mult, g.base
    return [v * m + b for v in g.v9], [v * m + b for v in g.v8]


def tolerance(old: ff.TileGrid, new: ff.TileGrid) -> float:
    """How far a point may be off and still count as not moved: 0.01 yd, or the rounding of the stored heights
    when that is larger (half a step of a uint8/uint16 grid on each side, plus float32 slack). The server's .map file
    of a tile with 1500 yd of relief rounds by up to 0.0114 yd, which is not ground that moved."""
    return max(SAME_LIMIT, 0.5 * old.step + 0.5 * new.step + 0.002)


def compare_tile(res: MapResult, tile, old: ff.TileGrid, new: ff.TileGrid, zones: Zones, t: fr.Thresholds):
    o9, o8 = _vertex_heights(old)
    n9, n8 = _vertex_heights(new)
    d9 = [b - a for a, b in zip(o9, n9)]
    d8 = [b - a for a, b in zip(o8, n8)]
    ts = res.terrain
    tol = tolerance(old, new)
    ts["tolerance_max"] = max(ts["tolerance_max"], tol)
    vals = [float("nan")] * 256
    tile_changed = 0
    for iy in range(16):
        for ix in range(16):
            ds = []
            for r in range(9):
                s = (iy * 8 + r) * 129 + ix * 8
                ds.extend(d9[s:s + 9])
            for r in range(8):
                s = (iy * 8 + r) * 128 + ix * 8
                ds.extend(d8[s:s + 8])
            ds = [d for d in ds if d == d]
            area = old.chunk_area(iy, ix) or new.chunk_area(iy, ix)
            oa, na = old.chunk_area(iy, ix), new.chunk_area(iy, ix)
            if oa is not None and na is not None and oa != na:
                res.areas_changed += 1
            oh = old.holes[iy * 16 + ix] if old.holes else 0
            nh = new.holes[iy * 16 + ix] if new.holes else 0
            if oh != nh:
                res.holes_changed += 1
            if not ds:
                continue
            big = max(ds, key=abs)
            vals[iy * 16 + ix] = big
            absd = [abs(d) for d in ds]
            s_abs = sum(absd)
            ts["n"] += len(ds)
            ts["sum"] += s_abs
            ts["over_fine"] += sum(1 for a in absd if a > t.fine)
            ts["over_broken"] += sum(1 for a in absd if a > t.broken)
            moved = sum(1 for a in absd if a > tol)
            tile_changed += moved
            a = abs(big)
            if moved:
                ts["max_excess"] = max(ts["max_excess"], a - tol)
            if a > ts["max_abs"]:
                ts["max_abs"] = a
                ts["max_signed"] = big
                ts["max_tile"] = tile
                ts["max_at"] = ff.vertex_world(tile[0], tile[1], iy * 8 + 4, ix * 8 + 4)  # the chunk's centre
            key, label = zones.key(area, tile)
            z = _zone(res, key, label)
            z["n"] += len(ds)
            z["sum"] += s_abs
            z["max"] = a if z["max"] is None else max(z["max"], a)
    ts["changed_points"] += tile_changed
    if not tile_changed:
        ts["same_tiles"] += 1
    res.chunk_delta[tile] = vals
    return compare_water(res, tile, old, new)


def _water_differs(a, b, flags_known: bool) -> bool:
    """Two cells' water as the server reads it ((entry, flags, level) or None): another liquid, other flags (when
    both sides' flags are known) or a level more than WATER_LIMIT away."""
    if a is None or b is None:
        return a is not b
    return a[0] != b[0] or (flags_known and a[1] != b[1]) or abs(a[2] - b[2]) > WATER_LIMIT


def compare_water(res: MapResult, tile, old: ff.TileGrid, new: ff.TileGrid):
    """Compare the water of a tile cell by cell (LiquidGrid.cells: what GridTerrainData::GetLiquidData finds).
    Returns (old cells, new cells, flags known) when some cell differs, else None. A side whose water was not read
    (split ADTs) makes the tile's water unknown."""
    w = res.water
    if old.liquid_note or new.liquid_note:
        w["unknown"].add(tile)
        return None
    if old.liquid is None and new.liquid is None:
        return None
    n = ff.MAP_RESOLUTION * ff.MAP_RESOLUTION
    oc = old.liquid.cells() if old.liquid is not None else [None] * n
    nc = new.liquid.cells() if new.liquid is not None else [None] * n
    known = all(g.liquid is None or g.liquid.flags_known for g in (old, new))
    if not known:
        w["flags_unknown"].add(tile)
    chunks = set()
    for i, (a, b) in enumerate(zip(oc, nc)):
        if not _water_differs(a, b, known):
            continue
        if a is None:
            w["gained"] += 1
        elif b is None:
            w["lost"] += 1
        else:
            w["other"] += 1
            dl = abs(b[2] - a[2])
            if dl > w["max_level"]:
                w["max_level"] = dl
                w["max_at"] = (tile, ff.vertex_world(tile[0], tile[1], i // 128 + 0.5, i % 128 + 0.5))
        w["cells"] += 1
        chunks.add(((i // 128) >> 3) * 16 + ((i % 128) >> 3))
    if not chunks:
        return None
    w["tiles"].add(tile)
    res.water_chunks[tile] = chunks
    return oc, nc, known


def _cell(x: float, y: float) -> int:
    """The water cell (row * 128 + column) of a world point, as GridTerrainData::GetLiquidData picks it."""
    r = int(ff.MAP_RESOLUTION * (32 - x / ff.TILE_SIZE)) & (ff.MAP_RESOLUTION - 1)
    c = int(ff.MAP_RESOLUTION * (32 - y / ff.TILE_SIZE)) & (ff.MAP_RESOLUTION - 1)
    return r * ff.MAP_RESOLUTION + c


def check_spawns(res: MapResult, tile, spawns, old, new, zones: Zones, t: fr.Thresholds, new_tile: bool = True,
                 note: str = "", water=None):
    """Judge the spawns of one tile. new_tile: the new files have this tile (False: no tile, or an unreadable
    one); note: added to every reason. water: (old cells, new cells, flags known) when the tile's water differs:
    a spawn at or in water that differs (no deeper than WATER_SPAWN_MARGIN over the higher level) is listed."""
    for s in spawns:
        if water is not None:
            oc, nc, known = water
            ci = _cell(s.x, s.y)
            a, b = oc[ci], nc[ci]
            if _water_differs(a, b, known):
                top = max(v[2] for v in (a, b) if v is not None)
                if s.z <= top + WATER_SPAWN_MARGIN:
                    res.water_spawns.append({"guid": s.guid, "entry": s.entry, "kind": s.kind, "name": s.name,
                                             "x": s.x, "y": s.y, "z": s.z, "old": a[2] if a else None,
                                             "new": b[2] if b else None, "tile": tile})
        oh = old.height(s.x, s.y) if old is not None else None
        nh = new.height(s.x, s.y) if new is not None else None
        v = fr.judge(oh, nh, s.z, t, new_tile=new_tile and new is not None)
        if note:
            v.reason += f" ({note})"
        area = None
        if old is not None:
            area = old.area_at(s.x, s.y)
        if not area and new is not None:
            area = new.area_at(s.x, s.y)
        key, label = zones.key(area, tile)
        z = _zone(res, key, label)
        z["spawns"][v.cls] = z["spawns"].get(v.cls, 0) + 1
        res.class_counts[v.cls] = res.class_counts.get(v.cls, 0) + 1
        res.spawns.append({"guid": s.guid, "entry": s.entry, "kind": s.kind, "name": s.name, "x": s.x, "y": s.y,
                           "z": s.z, "old": oh, "new": nh, "delta": v.delta, "judged": v.judged, "class": v.cls,
                           "stance": v.stance, "reason": v.reason, "zone": label, "tile": tile})


ISSUE_SAMPLE = 8


def run_map(res: MapResult, src, mf: fs.MapFiles | None, old_loader, old_tiles: set, spawns: list[Spawn],
            zones: Zones, t: fr.Thresholds, work: str, budget: int, log, liquid_types: dict | None = None,
            base_same: str = "", lost: str = ""):
    """Compare one map. liquid_types: LiquidType.dbc's {id: sound bank} for the new ADTs' water. base_same: why a
    server tile that the new files do not carry is not the base client's copy of the server's ground (the new
    files' Map.dbc reads the map from another folder), or "" when it is. lost: why the new files give this map no
    ground at all (every server tile is lost), or ""."""
    by_tile: dict[tuple[int, int], list[Spawn]] = {}
    for s in spawns:
        by_tile.setdefault(ff.tile_of(s.x, s.y), []).append(s)
    done = set()
    if lost:
        res.lost_why = lost
        res.notes.append(f"{lost}: every server tile of it is lost")
        for tile in sorted(old_tiles, key=lambda k: (k[1], k[0])):
            try:
                old = old_loader(tile)
            except (OSError, ff.FormatError, ValueError) as e:
                res.notes.append(f"server tile {tile[0]},{tile[1]} unreadable: {e}")
                old = None
            if old is not None:
                res.old_only.add(tile)
            check_spawns(res, tile, by_tile.get(tile, ()), old, None, zones, t, new_tile=False, note=lost)
            done.add(tile)
        for tile, group in by_tile.items():
            if tile not in done:
                check_spawns(res, tile, group, None, None, zones, t, new_tile=False)
        return
    new_tiles = set(mf.tiles) if mf else set()
    has_wdt = bool(mf and mf.wdt)
    flagged: set | None = None  # the tiles the new WDT lists; None: the new files have no WDT (the base one stays)
    wdt_bad = False
    unlisted: list[tuple[int, int]] = []
    issues: dict[str, list] = {}  # what was odd in the new ADTs: {issue: [chunks, [tiles]]}
    unreadable: list[tuple[tuple[int, int], str]] = []

    def load_old(tile):
        try:
            return old_loader(tile)
        except (OSError, ff.FormatError, ValueError) as e:
            res.notes.append(f"server tile {tile[0]},{tile[1]} unreadable: {e}")
            return None

    if base_same and (mf is None or (not new_tiles and not has_wdt)):
        res.notes.append(f"{base_same}; the new files have no ground files in that folder")
    elif mf is None:
        res.pack_empty = True
        res.notes.append("the new files have no folder for this map: the base client's files stay")
    elif not new_tiles and not has_wdt:
        res.pack_empty = True
        res.notes.append("the new files have no ADT and no WDT for this map: the base client's files stay")
    else:
        log(f"  {res.name}: {len(new_tiles)} new tiles ({mf.total_bytes() // MB} MB), {len(old_tiles)} on the "
            f"server side, {len(spawns)} spawns")
        n_seen = 0
        for bi, (batch, wdt) in enumerate(src.batches(mf, work, budget, log)):
            if bi == 0 and has_wdt:
                # the WDT always comes with the first batch, so it is read before any tile is sorted
                try:
                    if not wdt:
                        raise ff.FormatError("it was not extracted")
                    flagged, mphd = ff.read_wdt_tiles(wdt)
                    if not flagged:
                        res.notes.append("the new WDT lists no terrain tiles" +
                                         (" (a WMO-only map)" if mphd & 1 else ""))
                except (OSError, ff.FormatError) as e:
                    wdt_bad = True
                    res.notes.append(f"the new WDT could not be read ({e}): server tiles without a new ADT are "
                                     f"counted as lost")
            for tile in sorted(batch, key=lambda k: (k[1], k[0])):
                n_seen += 1
                if flagged is not None and tile not in flagged:
                    unlisted.append(tile)
                    continue
                note = ""
                try:
                    new = ff.read_adt(batch[tile], tile[0], tile[1], liquid_types=liquid_types)
                    for text, n in new.issues.items():
                        rec = issues.setdefault(text, [0, []])
                        rec[0] += n
                        rec[1].append(tile)
                except ff.ExtractorRefusal as e:
                    # the server would get no .map file for this tile: its ground is lost
                    res.refused.append((tile, e.short()))
                    note = ("map_extractor would crash on the new tile" if e.crash else
                            "map_extractor would refuse the new tile: no .map file") + ", see NOTE"
                    new = None
                except (OSError, ff.FormatError, ValueError) as e:
                    unreadable.append((tile, str(e).replace(batch[tile], mf.tiles[tile])))
                    new = None
                old = load_old(tile) if tile in old_tiles else None
                water = None
                if old is not None and new is not None:
                    water = compare_tile(res, tile, old, new, zones, t)
                elif new is not None:
                    res.new_only.add(tile)
                elif old is not None:
                    res.old_only.add(tile)
                check_spawns(res, tile, by_tile.get(tile, ()), old, new, zones, t, new_tile=new is not None,
                             note=note, water=water)
                done.add(tile)
            if batch:
                log(f"  {res.name}: {n_seen} of {len(new_tiles)} new tiles done")
        if res.refused:
            crash = sum(1 for _t, why in res.refused if "would crash" in why)
            res.notes.append(f"{len(res.refused)} new ADT(s) that map_extractor would not convert, so the server would "
                             f"get no .map file for them (their ground is lost, and the spawns on them are broken)"
                             + (f"; {crash} of them would crash it, which ends the whole extraction" if crash else "")
                             + ": " + "; ".join(f"{tl[0]},{tl[1]}: {why}" for tl, why in res.refused[:ISSUE_SAMPLE])
                             + (f"; and {len(res.refused) - ISSUE_SAMPLE} more" if len(res.refused) > ISSUE_SAMPLE
                                else ""))
        for tile, why in unreadable:
            res.notes.append(f"new tile {tile[0]},{tile[1]} unreadable: {why}")
        if unlisted:
            res.notes.append(f"{len(unlisted)} new ADT(s) that the new WDT does not list are never loaded (by the "
                             f"client or map_extractor): skipped ({_tiles(unlisted)})")
        for text, (n, tiles) in sorted(issues.items()):
            res.notes.append(f"new ADTs: {n} chunk(s) {text}, in {len(tiles)} tile(s) ({_tiles(tiles)})")
        if flagged:
            nowhere = sorted(flagged - new_tiles - old_tiles, key=lambda k: (k[1], k[0]))
            if nowhere:
                res.notes.append(f"the new WDT lists {len(nowhere)} tile(s) that are neither in the new files nor "
                                 f"on the server: the base client's ADT would be used, if it has one (not compared: "
                                 f"{_tiles(nowhere)})")
        elif flagged is None and not wdt_bad:
            extra = sorted(new_tiles - old_tiles, key=lambda k: (k[1], k[0]))
            if extra:
                res.notes.append(f"the new files have no WDT for this map, so the base client's stays: their "
                                 f"{len(extra)} tile(s) the server does not have are used only if that WDT lists "
                                 f"them ({_tiles(extra)})")
    moved: list[tuple[int, int]] = []
    for tile in sorted(old_tiles - done, key=lambda k: (k[1], k[0])):
        old = load_old(tile)
        done.add(tile)
        if old is None:
            check_spawns(res, tile, by_tile.get(tile, ()), None, None, zones, t, new_tile=False)
        elif base_same:
            # the base client's tile of the other folder, if it has one, is not the server's ground: lost
            moved.append(tile)
            res.old_only.add(tile)
            check_spawns(res, tile, by_tile.get(tile, ()), old, None, zones, t, new_tile=False,
                         note="the new files' Map.dbc reads this map from another folder, see NOTE")
        elif not wdt_bad and (flagged is None or tile in flagged):
            # the new files do not carry this tile: map_extractor and the client read the base client's ADT
            res.base_kept.add(tile)
            check_spawns(res, tile, by_tile.get(tile, ()), old, old, zones, t,
                         note="its tile is not in the new files: the base client's stays")
        else:
            res.old_only.add(tile)
            check_spawns(res, tile, by_tile.get(tile, ()), old, None, zones, t, new_tile=False)
    for tile, group in by_tile.items():
        if tile not in done:
            check_spawns(res, tile, group, None, None, zones, t, new_tile=False)
    if moved:
        res.notes.append(f"{len(moved)} server tile(s) that the new files do not carry in that folder are counted as "
                         f"lost: the base client's tile of that folder, if it has one, is not this map's ground and "
                         f"is not compared ({_tiles(moved)})")


def _tiles(tiles, n: int = ISSUE_SAMPLE) -> str:
    tiles = list(tiles)
    shown = " ".join(f"{a},{b}" for a, b in tiles[:n])
    return shown + (f" and {len(tiles) - n} more" if len(tiles) > n else "")


def _find_server(path: str) -> tuple[str | None, str | None]:
    """(maps folder, dbc folder) of a server data folder or a maps folder."""
    if os.path.isdir(os.path.join(path, "maps")):
        dbc = os.path.join(path, "dbc")
        return os.path.join(path, "maps"), dbc if os.path.isdir(dbc) else None
    if os.path.isdir(path):
        dbc = os.path.join(os.path.dirname(os.path.abspath(path)), "dbc")
        return path, dbc if os.path.isdir(dbc) else None
    return None, None


def _ci_file(folder: str | None, name: str) -> str | None:
    if not folder or not os.path.isdir(folder):
        return None
    for f in os.listdir(folder):
        if f.lower() == name.lower():
            return os.path.join(folder, f)
    return None


class Stopped(BaseException):
    """A SIGTERM or SIGHUP, turned into an exception so the temporary files are deleted (not an Exception: nothing
    may take it for a problem of the files)."""

    def __init__(self, signum: int):
        super().__init__(signal.Signals(signum).name)
        self.name = signal.Signals(signum).name
        self.code = 128 + signum


def _on_signal(signum, _frame):
    raise Stopped(signum)


def _say(msg: str) -> None:
    try:
        print(msg, file=sys.stderr, flush=True)
    except OSError:  # the terminal is gone (SIGHUP)
        pass


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Check whether spawns still fit the ground of a new map pack.")
    ap.add_argument("--new", required=True, help=".7z archive or folder with the new map files")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--server", help="the server's data folder (maps/, dbc/) or its maps folder")
    g.add_argument("--old-adts", help="a folder of the old ADTs instead of the server's .map files")
    ap.add_argument("--spawns", help="spawns TSV (guid, entry, kind, map, x, y, z [, name])")
    ap.add_argument("--map-dbc", help="Map.dbc (default: the server's dbc/Map.dbc, else the new files')")
    ap.add_argument("--area-dbc", help="AreaTable.dbc (default: the server's, else the new files')")
    ap.add_argument("--liquid-dbc", help="LiquidType.dbc for the new water (default: the new files', else the "
                                         "server's)")
    ap.add_argument("--maps", default="", help="map folder names or ids, comma separated, or 'all' (default: all)")
    ap.add_argument("--out", required=True, help="report folder (made when missing)")
    ap.add_argument("--work", help="folder for temporary files (default: the system's temp folder)")
    ap.add_argument("--min-free-mb", type=int, default=2048, help="free disk that must stay free in --work")
    ap.add_argument("--batch-mb", type=int, default=1500, help="the most one extraction batch may take")
    ap.add_argument("--sevenzip", help="the 7z program (default: 7z, 7zz or 7za on PATH)")
    ap.add_argument("--fine", type=float, default=1.5)
    ap.add_argument("--broken", type=float, default=4.0)
    ap.add_argument("--floor-margin", type=float, default=3.0,
                    help="a spawn this far above (below) the old ground stands on a floor (in a cave)")
    ap.add_argument("--worst", type=int, default=20)
    ap.add_argument("--no-png", action="store_true")
    ap.add_argument("--quiet", action="store_true",
                    help="leave out the long summary at the end (the progress lines stay)")
    args = ap.parse_args(argv)

    def log(msg):
        print(msg, flush=True)

    try:
        t = fr.Thresholds(args.fine, args.broken, args.floor_margin)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    work_base = args.work or tempfile.gettempdir()
    if not os.path.isdir(work_base):
        print(f"ERROR: the work folder {work_base} does not exist", file=sys.stderr)
        return 2
    min_free = args.min_free_mb * MB
    free = fs.free_bytes(work_base)
    if free < min_free:
        print(f"ERROR: only {free // MB} MB free in {work_base}; {args.min_free_mb} MB must stay free. Nothing was "
              f"extracted.", file=sys.stderr)
        return 2
    try:
        work = tempfile.mkdtemp(prefix="fitcheck-", dir=work_base)
    except OSError as e:
        print(f"ERROR: cannot make a temporary folder in {work_base}: {e}. Nothing was changed.", file=sys.stderr)
        return EXIT_ERROR
    handlers = {}
    for name in ("SIGTERM", "SIGHUP"):
        sig = getattr(signal, name, None)
        if sig is None:
            continue
        try:
            handlers[sig] = signal.signal(sig, _on_signal)
        except (ValueError, OSError):  # not the main thread
            pass
    stopped = None
    try:
        return _run(args, t, work, min_free, log)
    except KeyboardInterrupt:
        stopped = ("Ctrl-C", 130)
    except Stopped as e:
        stopped = (e.name, e.code)
    except (fs.SourceError, ff.FormatError, OSError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return EXIT_ERROR
    except Exception as e:  # a crash must never look like exit code 1 ("something moved")
        where = traceback.extract_tb(e.__traceback__)[-1]
        print(f"ERROR: the fit check stopped on an unexpected problem: {type(e).__name__}: {e} (at "
              f"{os.path.basename(where.filename)}:{where.lineno}). Nothing was changed; no report was written.",
              file=sys.stderr)
        return EXIT_ERROR
    finally:
        shutil.rmtree(work, ignore_errors=True)
        for sig, h in handlers.items():
            signal.signal(sig, h)
    # reached only when it was stopped, after the temporary files are gone
    _say(f"\nSTOPPED ({stopped[0]}): nothing was changed; its temporary files are deleted; no report was written.")
    return stopped[1]


def _first(*paths):
    return next((p for p in paths if p), None)


def _run(args, t, work, min_free, log) -> int:
    started = time.time()
    src = fs.open_source(args.new, args.sevenzip, min_free, log)
    log(f"new files: {src.describe()}; maps there: {', '.join(src.map_names()) or 'none'}")
    general = []

    server_maps = server_dbc = None
    old_src = None
    if args.server:
        server_maps, server_dbc = _find_server(args.server)
        if server_maps is None:
            raise fs.SourceError(f"{args.server} is not a folder")
        old_index = ff.scan_map_folder(server_maps)
        log(f"server maps: {server_maps} ({sum(len(v) for v in old_index.values())} .map files, "
            f"{len(old_index)} maps)")
    else:
        old_src = fs.FolderSource(args.old_adts)
        old_index = {}

    def server_file(name):
        return _ci_file(server_dbc, name)

    def old_file(name):
        tf = old_src.dbc(name, work) if old_src is not None else None
        return tf.path if tf else None

    # The new files' DBFilesClient is part of the MPQ chain map_extractor reads (install-map.sh stages them as the
    # last archive), so their Map.dbc and LiquidType.dbc are the ones a new extraction would use. Every DBC wanted
    # from them comes out in one 7z pass.
    want = ["Map.dbc"] + ([] if args.liquid_dbc else ["LiquidType.dbc"])
    if not args.area_dbc and not server_file("AreaTable.dbc"):
        want.append("AreaTable.dbc")
    with src.dbcs([n for n in want if src.has_dbc(n)], work) as pack_dbc:
        pack_map = pack_dbc.get("Map.dbc")
        if args.map_dbc:
            ids_path, where = args.map_dbc, args.map_dbc
        elif server_file("Map.dbc"):
            ids_path = server_file("Map.dbc")
            where = f"the server's {ids_path}"
        elif pack_map:
            ids_path, where = pack_map, "the new files' DBFilesClient/Map.dbc"
        elif old_file("Map.dbc"):
            ids_path, where = old_file("Map.dbc"), "the old files' DBFilesClient/Map.dbc"
        else:
            raise fs.SourceError("no Map.dbc: give --map-dbc, or a --server folder with dbc/Map.dbc")
        map_dirs = ff.read_map_dbc(ids_path)
        log(f"map ids from {where}")
        pack_dirs = None  # the new files' Map.dbc {id: Directory}, when it is not where the ids came from
        if pack_map and ids_path != pack_map:
            try:
                pack_dirs = ff.read_map_dbc(pack_map)
                log("map folders for a new extraction from the new files' DBFilesClient/Map.dbc")
            except ff.FormatError as e:
                general.append(f"the new files' Map.dbc cannot be read ({e}). map_extractor stops at once on a "
                               f"Map.dbc it cannot read, so nothing could be extracted from these files; the maps "
                               f"are compared under the server's folder names")

        liquid_types = None
        cands = [(args.liquid_dbc, args.liquid_dbc)] if args.liquid_dbc else []
        if not args.liquid_dbc:
            if pack_dbc.get("LiquidType.dbc"):
                cands.append((pack_dbc.get("LiquidType.dbc"), "the new files' DBFilesClient/LiquidType.dbc"))
            if server_file("LiquidType.dbc"):
                cands.append((server_file("LiquidType.dbc"), f"the server's {server_file('LiquidType.dbc')}"))
        for path, label in cands:
            try:
                liquid_types = ff.read_liquid_types(path)
                log(f"water types from {label}")
                break
            except ff.FormatError as e:
                general.append(f"LiquidType.dbc unreadable ({e})")
        if liquid_types is None:
            general.append("no LiquidType.dbc (give --liquid-dbc, or a --server folder with dbc/LiquidType.dbc): "
                           "the water of the new MH2O chunks is compared by its liquid type and level, not by its "
                           "flags")
        old_types = liquid_types
        if old_src is not None and old_file("LiquidType.dbc"):
            try:
                old_types = ff.read_liquid_types(old_file("LiquidType.dbc"))
            except ff.FormatError:
                pass

        areas = None
        apath = _first(args.area_dbc, server_file("AreaTable.dbc"), pack_dbc.get("AreaTable.dbc"),
                       old_file("AreaTable.dbc"))
        if apath:
            try:
                areas = ff.read_area_dbc(apath)
                log(f"zone names from {apath if apath != pack_dbc.get('AreaTable.dbc') else 'the new files'}")
            except ff.FormatError as e:
                log(f"AreaTable.dbc unreadable ({e}): zones by area id")
    zones = Zones(areas)
    by_dir = {d.lower(): i for i, d in map_dirs.items()}
    pack_folders = set(src.map_names())

    def new_folder_of(mid: int) -> str | None:
        """The folder a new extraction reads map mid from (None: the new files' Map.dbc has no such id)."""
        if pack_dirs is None:
            return map_dirs[mid]
        return pack_dirs.get(mid)

    # the server's maps whose ground the new files would change: a folder of theirs is the map's new folder, or
    # their Map.dbc drops the map (it would get no files at all)
    carried = sorted(mid for mid in map_dirs if (new_folder_of(mid) or "").lower() in pack_folders)
    dropped = []
    if pack_dirs is not None:
        dropped = sorted(mid for mid in map_dirs if mid not in pack_dirs and old_index.get(mid))
        if dropped:
            general.append(f"the new files' Map.dbc has no row for {len(dropped)} map(s) of the server that have "
                           f"terrain: map_extractor would write no .map files for them, and the client could not "
                           f"load them: {', '.join(f'{map_dirs[m]} ({m})' for m in dropped[:20])}"
                           + (f" and {len(dropped) - 20} more" if len(dropped) > 20 else ""))

    wanted = [w.strip() for w in args.maps.split(",") if w.strip()] if args.maps else []
    explicit = bool(wanted) and [w.lower() for w in wanted] != ["all"]
    if not explicit:
        wanted = [str(m) for m in carried + dropped]
    jobs = []  # (map id, the server's folder, the folder of the new files it is read from, why it is lost or "")
    not_checked: list[tuple[str, str]] = []  # (map, why) of the requested maps that were not compared
    for w in wanted:
        if w.isdigit():
            mid = int(w)
            folder = map_dirs.get(mid)
            if folder is None:
                general.append(f"map id {mid} is not in Map.dbc: skipped")
                not_checked.append((f"map id {mid}", "not in the server's Map.dbc"))
                continue
        else:
            mid = by_dir.get(w.lower())
            if mid is None:
                general.append(f"'{w}' is not a Directory of Map.dbc: skipped (a map the server does not know "
                               "has no spawns to check)")
                not_checked.append((f"'{w}'", "not a map of the server's Map.dbc"))
                continue
            folder = map_dirs[mid]
        if any(m == mid for m, *_rest in jobs):
            continue
        nf = new_folder_of(mid)
        lost = ""
        if nf is None:
            others = [pid for pid, d in pack_dirs.items() if d.lower() == folder.lower()]
            lost = (f"the new files' Map.dbc has no map {mid}" +
                    (f" (it gives '{folder}' id {others[0]})" if others else "") +
                    ": map_extractor writes no .map files for it, and the client cannot load it")
        jobs.append((mid, folder, nf or folder, lost))
    unknown = sorted(n for n in pack_folders if not any((new_folder_of(m) or "").lower() == n for m in map_dirs))
    if unknown:
        general.append(f"map folders of the new files that no map id of the server is read from: "
                       f"{', '.join(unknown)}")
    asked = {m for m, *_rest in jobs}
    not_asked = [m for m in carried + dropped if m not in asked] if explicit else []

    spawns: list[Spawn] = []
    if args.spawns:
        spawns, problems = read_spawns(args.spawns)
        general += problems[:20]
        log(f"spawns: {len(spawns)} from {args.spawns}")
    else:
        general.append("no --spawns: only the terrain is compared")

    os.makedirs(args.out, exist_ok=True)
    mfs = [None if lost else src.map_files(nf) for _m, _f, nf, lost in jobs]
    groups = _prefetch_groups(src, mfs, work, min_free, args.batch_mb * MB)
    results = []
    pending = None  # (temporary folder of a prefetch, index of the last job in it)
    try:
        for ji, (mid, folder, nf, lost) in enumerate(jobs):
            if ji in groups:
                pending = (src.prefetch([mfs[k] for k in groups[ji]], work, log), groups[ji][-1])
            res = MapResult(mid, folder, folder)
            base_same = ""
            if not lost and nf.lower() != folder.lower():
                base_same = (f"the new files' Map.dbc reads map {mid} from the folder '{nf}', not '{folder}' (so do "
                             f"the client and map_extractor), so its new ground is that folder's")
                res.notes.append(base_same)
            if pack_dirs is not None and not lost:
                for pid, pdir in sorted(pack_dirs.items()):
                    if pdir.lower() == folder.lower() and pid != mid:
                        res.notes.append(f"the new files' Map.dbc also gives '{folder}' id {pid}: map_extractor "
                                         f"writes that folder's files for map {pid} too")
            mf = mfs[ji]
            if old_src is None:
                old_paths = old_index.get(mid, {})

                def old_loader(tile, _p=old_paths):
                    return ff.read_map_file(_p[tile], tile[0], tile[1])

                old_tiles = set(old_paths)
            else:
                omf = old_src.map_files(folder)
                old_paths = omf.tiles if omf else {}

                def old_loader(tile, _p=old_paths):
                    return ff.read_adt(_p[tile], tile[0], tile[1], liquid_types=old_types)

                old_tiles = set(old_paths)
            if not old_tiles:
                res.notes.append("the server side has no terrain tiles for this map")
            mine = [s for s in spawns if s.map_id == mid]
            run_map(res, src, mf, old_loader, old_tiles, mine, zones, t, work, args.batch_mb * MB, log,
                    liquid_types=liquid_types, base_same=base_same, lost=lost)
            results.append(res)
            if pending and ji >= pending[1]:
                if pending[0]:
                    shutil.rmtree(pending[0], ignore_errors=True)
                pending = None
            if not args.no_png:
                png = os.path.join(args.out, f"heatmap_{mid:03}_{folder.lower()}.png")
                if fr.heatmap(png, res, t):
                    res.notes.append(f"heatmap: {png}")
            log(f"  {folder}: done, {fr.map_state(res)[0]}; spawns "
                f"{fr._counts(res.class_counts) if res.spawns else '-'}")
    finally:
        if pending and pending[0]:
            shutil.rmtree(pending[0], ignore_errors=True)

    lines = ["Bleakhold fit check: the new map files against the server's ground and spawns",
             f"  new files: {src.describe()}",
             f"  current ground: {'server maps ' + server_maps if server_maps else 'old ADTs ' + str(args.old_adts)}",
             f"  spawns: {args.spawns or '-'} ({len(spawns)})",
             f"  thresholds: fine <= {t.fine:g} yd, shifted <= {t.broken:g} yd, broken above; floor margin "
             f"{t.floor_margin:g} yd",
             ""] + fr.method_lines(t) + [""]
    if not_asked:
        general.append(f"the new files also carry {len(not_asked)} more map(s) of the server that were not asked for "
                       f"(NOT ASKED FOR below): their ground would be replaced too, unchecked. Run again with "
                       f"--maps all before anything ships")
    for gline in general:
        lines.append(f"NOTE: {gline}")
    total = {}
    for res in results:
        for k, v in res.class_counts.items():
            total[k] = total.get(k, 0) + v
    lines.append("")
    lines.append("In short:")
    for res in results:
        ts = res.terrain
        moved = (f"ground moved {ts['sum'] / ts['n']:.2f} yd on average, at most {ts['max_abs']:.1f} yd"
                 if ts["n"] else "no shared terrain")
        water = f"; water differs in {res.water['cells']} cell(s)" if res.water["cells"] else ""
        lines.append(f"  {res.name} (map {res.map_id}): {moved}{water}; tiles lost {len(res.old_only)}, "
                     f"new {len(res.new_only)}, kept from the base client {len(res.base_kept)}; spawns "
                     f"{fr._counts(res.class_counts)}")
    lines.append(f"  all maps: {fr._counts(total)}")
    compared = []
    for res in results:
        state, why = fr.map_state(res)
        if state == fr.NOT_CHECKED:
            not_checked.append((f"{res.name} (map {res.map_id})", why))
            continue
        compared.append(f"{res.name} (map {res.map_id})")
        if state == fr.SAME and res.water["unknown"]:
            not_checked.append((f"the water of {res.name} (map {res.map_id})",
                                f"{len(res.water['unknown'])} tile(s) of split ADTs, whose water is not read (the "
                                f"server is extracted from 3.3.5 files: check those)"))
    if not jobs and not not_checked:
        not_checked.append(("every map", "none of the maps of the new files is one the server's Map.dbc knows"))
    if compared:
        lines.append(f"  compared: {', '.join(compared)}")
    if not_checked:
        lines.append(f"  NOT CHECKED: {'; '.join(f'{m}: {why}' for m, why in not_checked)}")
    if not_asked:
        lines.append(f"  NOT ASKED FOR: {len(not_asked)} more map(s) of the server that the new files carry, so they "
                     f"would change too (run again with --maps all): "
                     f"{', '.join(f'{map_dirs[m]} (map {m})' for m in not_asked)}")
    for res in results:
        lines.append("")
        lines += fr.map_summary(res, t, args.worst)
    lines.append("")
    lines.append(f"(took {time.time() - started:.0f} s)")
    summary = os.path.join(args.out, "summary.txt")
    with open(summary, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    n_csv = fr.write_csv(os.path.join(args.out, "nonfine_spawns.csv"), results)
    bad = total.get(fr.BROKEN, 0) + total.get(fr.SHIFTED, 0)
    changed = any(fr.map_state(r)[0] == fr.CHANGED for r in results)
    rc = EXIT_CHANGED if bad or changed else EXIT_NOT_CHECKED if not_checked or not_asked else EXIT_SAME
    with open(os.path.join(args.out, "report.json"), "w", encoding="utf-8") as f:
        json.dump({"maps": [r.to_json() for r in results], "notes": general, "totals": total,
                   "compared": compared, "not_checked": [{"map": m, "why": why} for m, why in not_checked],
                   "not_asked": [{"map_id": m, "name": map_dirs[m]} for m in not_asked],
                   "exit_code": rc,
                   "thresholds": {"fine": t.fine, "broken": t.broken, "floor_margin": t.floor_margin}}, f, indent=1)
    if not args.quiet:
        log("")
        log("\n".join(lines))
        log("")
        log(f"report: {summary} ; {n_csv} spawns not fine in {os.path.join(args.out, 'nonfine_spawns.csv')}")
    return rc


def _prefetch_groups(src, mfs, work: str, min_free: int, budget: int) -> dict[int, list[int]]:
    """{index of the first job: the job indices whose files come out together}: runs of maps next to each other
    that fit one batch together are extracted in one 7z pass (on a big solid archive each pass takes minutes; one
    per dungeon would make --maps all take hours). A map bigger than a batch goes alone, in its own batches, and
    ends the run before it, so a prefetch never shares the disk with another map's batches."""
    if getattr(src, "kind", "") != "7z":
        return {}
    room = fs.free_bytes(work) - min_free
    cap = min(budget, room) if budget > 0 else room
    groups: dict[int, list[int]] = {}
    cur: list[int] = []
    size = 0

    def flush():
        nonlocal cur, size
        if len(cur) >= 2:
            groups[cur[0]] = cur
        cur, size = [], 0

    for i, mf in enumerate(mfs):
        n = mf.total_bytes() if mf is not None else 0
        if mf is None or not (mf.tiles or mf.wdt):
            continue  # nothing to extract for it
        if n > cap:
            flush()
            continue
        if size + n > cap:
            flush()
        cur.append(i)
        size += n
    flush()
    return groups


if __name__ == "__main__":
    sys.exit(main())
