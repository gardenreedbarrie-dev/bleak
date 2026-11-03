#!/usr/bin/env python3
"""MapForge packaging: the new map's DBC rows, the patch archives for players, and the AzerothCore SQL.

    python3 -I Tools/MapForge/package.py build --config <map.json> --dbc <folder> --out <folder>
        [--terrain <terrain output>] [--patches <realm patch folder>] [--server-sql <bleakserv/data/sql> ...]
        [--minimap <tile folder>] [--worldmap <tile folder>] [--trs <file or client Data folder>]
        [--drop-map-art] [--force]
    python3 -I Tools/MapForge/package.py pull --patches <folder> --out <folder> [--config <map.json>]
    python3 -I Tools/MapForge/package.py doctor --patches <folder> [--config <map.json>]
    python3 -I Tools/MapForge/package.py validate --config <map.json> --out <folder>
    python3 -I Tools/MapForge/package.py poi-sql --pois <terrain output or pois.json> --out <folder> [--map-id N]
    python3 -I Tools/MapForge/package.py resolve-assets --spec <terrain spec> --out <folder>
        [--sources <folder or MPQ> ...] [--listfile <3.3.5 listfile or kit> ...]
    python3 -I Tools/MapForge/package.py schemas [--check | --write]

It ships no game data: it reads the DBC files and archives you give it and writes modified copies. The terrain
(World\\Maps\\...) comes from Tools/MapForge/terrain. See README.md, section "Data and packaging".
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))

# python3 -I leaves the script's folder off sys.path; the dbc package then adds the sibling tools.
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from dbc import SIBLINGS  # noqa: E402,F401  (import also extends sys.path)
from dbc import config as configmod  # noqa: E402
from dbc import forge as forgemod  # noqa: E402
from dbc import layout, minimap, plan as planmod, sqlgen  # noqa: E402
from dbc.patches import LOCALES, PatchArchive, PatchError, PatchSet, outranks, rebuild  # noqa: E402
from dbc.sources import SourceReadError, SourceSet  # noqa: E402
from terrain import extra_assets  # noqa: E402
from terrain.spec import load_spec  # noqa: E402
from terrain.spec_errors import SpecError  # noqa: E402

import mpqpack  # noqa: E402
from rflib.dbc import DbcError, DbcTable  # noqa: E402

MARKER_FILE = "MapForge\\mapforge.txt"
MAP_ART_FILE = "MapForge\\mapart.txt"  # which map art the archive holds and the terrain it was made for
TRS_FILE = "Textures\\Minimap\\md5translate.trs"
TILE_SIZE = 256
# NUM_WORLDMAP_DETAIL_TILES: the stock world map shows Interface\WorldMap\<area>\<area>1..12 as 4 x 3 tiles of 256,
# row-major, in a 1024 x 768 picture whose top-left 1002 x 668 is the map frame (WorldMapFrame_Update). A tile it
# cannot load keeps the picture it showed before (a failed SetTexture keeps the old texture), so it is all or none.
WORLD_MAP_TILES = 12
# The base archives under every patch, highest priority first: OpenArchives (WoW/Source/Client.cpp) opens the
# patches from priority 64 up, then the base archives of s_archives at falling priorities in the table's order
# ("****" is the locale). Only these can hold a stock md5translate.trs.
BASE_ARCHIVES = ("expansion.MPQ", "lichking.MPQ", "common.MPQ", "common-2.MPQ", "****\\locale-****.MPQ",
                 "****\\expansion-locale-****.MPQ", "****\\lichking-locale-****.MPQ")
EXTRACT_PATCH = "patch-5.MPQ"
LOADING_SIZE = (1024, 1024)
LOADING_WIDE_SIZE = (2048, 1024)
OUTPUT_ENTRIES = ("client", "server", "report.txt")


class BuildError(Exception):
    pass


def find_dbc(folder: str, name: str) -> str | None:
    """<name>.dbc in folder or folder/DBFilesClient, ignoring case."""
    wanted = layout.file_name(name).lower()

    for sub in (folder, os.path.join(folder, "DBFilesClient")):
        if not os.path.isdir(sub):
            continue

        for entry in os.listdir(sub):
            if entry.lower() == wanted and os.path.isfile(os.path.join(sub, entry)):
                return os.path.join(sub, entry)

    return None


def read_tables(folder: str, required: list[str], optional: list[str]) -> tuple[dict[str, DbcTable], list[str]]:
    tables = {}
    notes = []

    for name in required + optional:
        path = find_dbc(folder, name)

        if path is None:
            if name in required:
                raise BuildError(f"{folder}: {layout.file_name(name)} is missing (see README: which DBCs to use)")

            notes.append(f"{layout.file_name(name)} not given: its references are not checked")
            continue

        tables[name] = DbcTable.read(path, layout.get(name))

    return tables, notes


def read_terrain(folder: str, cfg: configmod.Config) -> tuple[dict, list[str], set[tuple[int, int]]]:
    """(manifest, client files to pack as (archive name, path on disk), WDT tiles). The manifest also gets
    "_extra" (the extra-asset files for the map archive) and "_server" (the tiles the server extracts: the
    server copy without the extra-asset doodads when the terrain has one, else the client tiles)."""
    manifest_path = os.path.join(folder, "terrain_manifest.json")

    if not os.path.isfile(manifest_path):
        raise BuildError(f"{folder}: no terrain_manifest.json (point --terrain at the terrain build's output)")

    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    directory = manifest.get("directory", "")

    if directory.lower() != cfg.map.directory.lower():
        raise BuildError(f"the terrain is for {directory!r}, the config for {cfg.map.directory!r}")

    maps_dir = os.path.join(folder, "World", "Maps", directory)

    if not os.path.isdir(maps_dir):
        raise BuildError(f"{folder}: no World/Maps/{directory} folder")

    files = []

    for entry in sorted(os.listdir(maps_dir)):
        if entry.lower().endswith((".wdt", ".wdl", ".adt")):
            files.append((f"World\\Maps\\{directory}\\{entry}", os.path.join(maps_dir, entry)))

    if not any(n.lower().endswith(".wdt") for n, _ in files):
        raise BuildError(f"{maps_dir}: no .wdt (a player without it crashes on teleport)")

    tiles = {tuple(t) for t in manifest.get("tiles", [])}
    terrain_areas = set(manifest.get("area_ids", []))

    if terrain_areas and terrain_areas - {0} - set(cfg.area_ids()):
        raise BuildError(f"the terrain's MCNK area ids {sorted(terrain_areas - {0})} are not all in the config's "
                         f"areas {cfg.area_ids()}")

    extra = []

    for entry in manifest.get("extra_files", []):
        why = extra_assets.unsafe_path(entry["path"]) or extra_assets.unsafe_path(entry["file"])

        if why:
            raise BuildError(f"{folder}: the extra asset {entry['path']!r} ({entry['file']!r}) is not a plain "
                             f"relative path ({why})")

        path = os.path.join(folder, *entry["file"].split("/"))

        if not os.path.isfile(path):
            raise BuildError(f"{folder}: the extra asset {entry['path']} is missing ({entry['file']})")

        with open(path, "rb") as f:
            if hashlib.sha256(f.read()).hexdigest() != entry["sha256"]:
                raise BuildError(f"{path} differs from the terrain manifest (sha256); rebuild the terrain")

        extra.append((entry["path"], path))

    server = files

    if manifest.get("server_tiles"):
        server_dir = os.path.join(folder, *manifest["server_tiles"].split("/"))

        if not os.path.isdir(server_dir):
            raise BuildError(f"{folder}: the manifest names the server copy {manifest['server_tiles']}, which is "
                             "missing")

        server = [(f"World\\Maps\\{directory}\\{entry}", os.path.join(server_dir, entry))
                  for entry in sorted(os.listdir(server_dir)) if entry.lower().endswith((".wdt", ".wdl", ".adt"))]

        if sorted(n.lower() for n, _ in server) != sorted(n.lower() for n, _ in files):
            raise BuildError(f"{server_dir}: the server copy holds other files than World/Maps/{directory}")

    manifest["_extra"] = extra
    manifest["_server"] = server
    return manifest, files, tiles


def convert_loading_screens(cfg: configmod.Config, staging: dict[str, str], work_dir: str) -> list[str]:
    """Convert loading_screen.image / wide_image to BLP into work_dir and stage them. Returns notes."""
    ls = cfg.loading_screen

    if ls is None or ls.reuse is not None or not (ls.image or ls.wide_image):
        return []

    import blpconvert  # noqa: PLC0415  (Tools/BlpConvert, on sys.path)

    notes = []
    os.makedirs(work_dir, exist_ok=True)
    jobs = [(ls.image, ls.file, LOADING_SIZE)]

    if ls.wide_image:
        stem, ext = ls.file.rsplit(".", 1)
        jobs.append((ls.wide_image, f"{stem}Wide.{ext}", LOADING_WIDE_SIZE))

    for source, archive_name, size in jobs:
        if source is None:
            continue

        out_path = os.path.join(work_dir, archive_name.replace("\\", "__"))

        try:
            image = blpconvert.read_image(source, size)
            fmt = blpconvert.convert(image, out_path, fmt="dxt1", jobs=1)
        except SystemExit as e:  # blpconvert reports errors with SystemExit
            raise BuildError(f"loading screen {source}: {e}") from None

        staging[archive_name] = out_path
        notes.append(f"{archive_name}: {size[0]}x{size[1]} {fmt} from {source}")

    return notes


def minimap_tile_name(directory: str, tile: tuple[int, int]) -> str:
    return f"Textures\\Minimap\\{directory}\\map{tile[0]}_{tile[1]:02d}.blp"


def world_map_tile_name(area: str, n: int) -> str:
    return f"Interface\\WorldMap\\{area}\\{area}{n}.blp"


def tile_blp_problems(blob: bytes) -> list[str]:
    """What keeps a BLP from being a map tile the client draws: BLP2, 256 x 256, DXT1, every level it declares
    present and as long as CalcLevelSize wants (Engine/Source/Images/MippedImg.cpp)."""
    import blpconvert  # noqa: PLC0415  (Tools/BlpConvert, on sys.path)

    try:
        header = blpconvert.read_blp_header(blob)
    except (ValueError, struct.error) as e:
        return [str(e)]

    problems = []

    if header["magic"] != b"BLP2" or header["version"] != 1:
        problems.append(f"not a BLP2 file (magic {header['magic']!r}, version {header['version']})")

    if (header["width"], header["height"]) != (TILE_SIZE, TILE_SIZE):
        problems.append(f"{header['width']} x {header['height']}, not {TILE_SIZE} x {TILE_SIZE}")

    if header["encoding"] != 2 or header["preferredFormat"] != blpconvert.PIXEL_DXT1:
        problems.append(f"not DXT1 (encoding {header['encoding']}, format {header['preferredFormat']})")
    elif not problems:
        levels = blpconvert.level_count(TILE_SIZE, TILE_SIZE) if header["hasMips"] & 0xF else 1

        for i in range(levels):
            offset, size = header["offsets"][i], header["sizes"][i]

            if size < blpconvert.level_size(i, TILE_SIZE, TILE_SIZE, "dxt1") or offset + size > len(blob):
                problems.append(f"level {i} is missing or cut off (the client then fails the whole texture)")
                break

    return problems


def collect_world_map_tiles(folder: str, area: str) -> dict[int, str]:
    """{n: path} of <area>1..12 (.png or .blp) in folder: every tile, each once."""
    if not os.path.isdir(folder):
        raise BuildError(f"--worldmap: {folder} is not a folder")

    pattern = re.compile(rf"(?i){re.escape(area)}([1-9][0-9]*)\.(?:blp|png)")
    tiles = {}

    for entry in sorted(os.listdir(folder)):
        if os.path.splitext(entry)[1].lower() not in (".blp", ".png"):
            continue

        match = pattern.fullmatch(entry)

        if not match or int(match.group(1)) > WORLD_MAP_TILES:
            raise BuildError(f"--worldmap: {folder}/{entry}: the world map tiles are {area}1 to "
                             f"{area}{WORLD_MAP_TILES} (.png or .blp), named after the config's world_map_area")

        n = int(match.group(1))

        if n in tiles:
            raise BuildError(f"--worldmap: {folder}: tile {n} is there twice (.png and .blp)")

        tiles[n] = os.path.join(folder, entry)

    missing = [n for n in range(1, WORLD_MAP_TILES + 1) if n not in tiles]

    if missing:
        raise BuildError(f"--worldmap: {folder} lacks {', '.join(f'{area}{n}' for n in missing)}: a tile the client "
                         "cannot load keeps the picture of the map shown before")

    return tiles


def check_world_map_tiles(tiles: dict[int, str]) -> None:
    """Each tile is a 256 x 256 PNG or a 256 x 256 DXT1 BLP the client loads."""
    import blpconvert  # noqa: PLC0415  (Tools/BlpConvert, on sys.path)

    for n, path in sorted(tiles.items()):
        if path.lower().endswith(".png"):
            try:
                image = blpconvert.read_image(path)
            except SystemExit as e:
                raise BuildError(f"world map tile {path}: {e}") from None

            if (image.width, image.height) != (TILE_SIZE, TILE_SIZE):
                raise BuildError(f"world map tile {path} is {image.width} x {image.height}: a tile is a "
                                 f"{TILE_SIZE} x {TILE_SIZE} piece of one 1024 x 768 picture (never resampled)")
        else:
            with open(path, "rb") as f:
                problems = tile_blp_problems(f.read())

            if problems:
                raise BuildError(f"world map tile {path}: {'; '.join(problems)}")


def stage_worldmap(cfg: configmod.Config, tiles: dict[int, str], staging: dict[str, str], work_dir: str) -> None:
    """Stage Interface\\WorldMap\\<area>\\<area>1..12.blp (checked by check_world_map_tiles): a PNG becomes DXT1
    256 x 256 with one level (interface textures are drawn with plain linear filtering and no mips,
    Engine/Source/Frame/CSimpleRender.cpp), a BLP goes in as it is."""
    area = cfg.world_map_area.name
    os.makedirs(work_dir, exist_ok=True)

    for n, path in sorted(tiles.items()):
        if path.lower().endswith(".png"):
            import blpconvert  # noqa: PLC0415

            out_path = os.path.join(work_dir, f"worldmap{n}.blp")

            try:
                blpconvert.convert(blpconvert.read_image(path), out_path, fmt="dxt1", mips=False, jobs=1)
            except SystemExit as e:
                raise BuildError(f"world map tile {path}: {e}") from None

            staging[world_map_tile_name(area, n)] = out_path
        else:
            staging[world_map_tile_name(area, n)] = path


def trs_from_folder(folder: str, packs: dict[str, list[str]], map_archive: str) -> tuple[bytes, str]:
    """The md5translate.trs a client with this Data folder (or a folder holding Data, or a patch folder) loads,
    leaving the map archive out: the top patch archive that holds it (every pack on), else the first base archive in
    the client's order that does."""
    patchset = PatchSet.scan(folder, packs)
    all_on = frozenset({a.pack for a in patchset.archives if a.pack})

    try:
        pool = [a for a in patchset.active(all_on) if a.name.lower() != map_archive.lower()]
        holders = [a for a in pool if a.has(TRS_FILE)]
        top = holders[-1] if holders else None
        blind = [a.name for a in pool if a.reader is None and (top is None or a.rank() > top.rank())]

        if blind:
            raise BuildError(f"--trs {folder}: {', '.join(blind)} cannot be read, so which md5translate.trs the "
                             "players load cannot be told")

        if top:
            return top.read(TRS_FILE), top.client_path
    finally:
        patchset.close()

    data = patchset.folder
    locales = [e for e in sorted(os.listdir(data)) if e.lower() in {c.lower() for c in LOCALES}
               and os.path.isdir(os.path.join(data, e))]

    for pattern in BASE_ARCHIVES:
        for locale in (locales if "****" in pattern else [""]):
            rel = pattern.replace("****", locale)
            path = os.path.join(data, *rel.split("\\"))

            if not os.path.isfile(path):
                continue

            try:
                with PatchArchive(path) as archive:
                    if archive.has_file(TRS_FILE):
                        return archive.read(TRS_FILE), f"Data\\{rel}"
            except (mpqpack.MpqError, OSError, struct.error) as e:
                raise BuildError(f"--trs {folder}: Data\\{rel} cannot be read ({e}), so which md5translate.trs the "
                                 "players load cannot be told") from None

    raise BuildError(f"--trs {folder}: no archive there holds {TRS_FILE} (looked in the patches and in "
                     f"{', '.join(p.replace('****', '<locale>') for p in BASE_ARCHIVES)})")


def trs_base(trs: str | None, patchset: PatchSet | None, map_archive: str,
             packs: dict[str, list[str]]) -> tuple[bytes, str]:
    """The md5translate.trs this map's lines go into: --trs (the file, or the copy a client Data folder loads), else
    the top copy in the realm's patches outside the map archive, else the map archive's own (an earlier merge)."""
    if trs:
        if os.path.isdir(trs):
            return trs_from_folder(trs, packs, map_archive)

        try:
            with open(trs, "rb") as f:
                return f.read(), trs
        except OSError as e:
            raise BuildError(f"--trs {trs}: {e.strerror}") from None

    if patchset:
        all_on = frozenset({a.pack for a in patchset.archives if a.pack})
        holders = patchset.holders(TRS_FILE, all_on)
        others = [a for a in holders if a.name.lower() != map_archive.lower()]

        if others or holders:
            top = (others or holders)[-1]
            return top.read(TRS_FILE), top.name if others else f"{top.name} (its earlier merge)"

    raise BuildError("--minimap needs the md5translate.trs the players load today, and no archive in --patches holds "
                     "it: give --trs (the file, or the client's Data folder to read it from, such as build-royale.sh's "
                     "/root/mapforge/stage); shipping only our lines would break every stock map's minimap")


def stage_minimap(cfg: configmod.Config, tiles: dict[tuple[int, int], str], trs: str | None,
                  patchset: PatchSet | None, staging: dict[str, str], work_dir: str,
                  wdt_tiles: set[tuple[int, int]]) -> list[str]:
    """Stage the Textures\\Minimap tiles ({(tx, ty): .blp or .png}) and the merged md5translate.trs."""
    directory = cfg.map.directory
    notes = []

    if wdt_tiles and set(tiles) != wdt_tiles:
        missing = sorted(wdt_tiles - set(tiles))
        extra = sorted(set(tiles) - wdt_tiles)
        raise BuildError(f"--minimap: the tiles do not match the WDT (missing {missing}, extra {extra})")

    os.makedirs(work_dir, exist_ok=True)

    for (tx, ty), path in sorted(tiles.items()):
        archive_name = minimap_tile_name(directory, (tx, ty))

        if path.lower().endswith(".png"):
            import blpconvert  # noqa: PLC0415

            out_path = os.path.join(work_dir, f"map{tx}_{ty:02d}.blp")

            try:
                image = blpconvert.read_image(path, (256, 256))
                blpconvert.convert(image, out_path, fmt="dxt1", jobs=1)
            except SystemExit as e:
                raise BuildError(f"minimap tile {path}: {e}") from None

            staging[archive_name] = out_path
        else:
            staging[archive_name] = path

    # The trs is one global file: start from the current one and add this map's lines.
    base, source = trs_base(trs, patchset, cfg.archives.map_archive, cfg.archives.optional_packs)

    if not base:
        raise BuildError(f"md5translate.trs from {source} is empty: shipping only our lines would break every stock "
                         "map's minimap")

    merged = minimap.build(minimap.parse(base, source), directory, sorted(tiles))
    trs_path = os.path.join(work_dir, "md5translate.trs")

    with open(trs_path, "wb") as f:
        f.write(merged)

    staging[TRS_FILE] = trs_path
    notes.append(f"md5translate.trs: merged from {source} plus {len(tiles)} tile lines")
    return notes


def terrain_digest(terrain_files: list[tuple[str, str]]) -> str:
    """A short fingerprint of the terrain files the map archive ships (names and bytes), for the map art record."""
    if not terrain_files:
        return "none"

    digest = hashlib.sha256()

    for name, path in sorted(terrain_files, key=lambda f: f[0].lower()):
        with open(path, "rb") as f:
            digest.update(f"{name.lower()}\0{hashlib.sha256(f.read()).hexdigest()}\n".encode())

    return digest.hexdigest()[:16]


def read_art_record(text: str) -> dict[str, tuple[int, str]]:
    """{kind: (tiles, terrain digest)} from MapForge\\mapart.txt ("minimap 9 <digest>" lines)."""
    out = {}

    for line in text.splitlines():
        parts = line.split()

        if len(parts) == 3 and parts[0] in ("minimap", "worldmap") and parts[1].isdigit():
            out[parts[0]] = (int(parts[1]), parts[2])

    return out


def write_art_record(record: dict[str, tuple[int, str]], work_dir: str) -> str:
    os.makedirs(work_dir, exist_ok=True)
    path = os.path.join(work_dir, "mapart.txt")

    lines = ["Written by Tools/MapForge (package.py): the map art in this archive (kind, tiles, and the fingerprint "
             "of the terrain it was made for)."]
    lines += [f"{kind} {tiles} {made_for}" for kind, (tiles, made_for) in sorted(record.items())]

    with open(path, "w", encoding="utf-8", newline="\r\n") as f:
        f.write("\n".join(lines) + "\n")

    return path


def kept_map_art(cfg: configmod.Config, patchset: PatchSet, wdt_tiles: set[tuple[int, int]], minimap_wanted: bool,
                 worldmap_wanted: bool, work_dir: str) -> tuple[dict, dict, dict, list[str]]:
    """The minimap and world map tiles of the realm's current map archive (a MapForge one in --patches), to ship
    again when this build is not given new ones: a rebuild (a new MapForge, a changed realm patch) must not take the
    island off the players' minimap and world map. Returns (minimap {(tx, ty): path}, world map {n: path}, their
    record {kind: (tiles, terrain digest)}, report lines). A kind that is there only in part is not kept."""
    ours = patchset.find(cfg.archives.map_archive)
    minimap_tiles, world_tiles, record, lines = {}, {}, {}, []

    if ours is None or not ours.has(MARKER_FILE):
        return minimap_tiles, world_tiles, record, lines

    old = read_art_record(ours.read(MAP_ART_FILE).decode("utf-8", "replace")) if ours.has(MAP_ART_FILE) else {}
    kept_dir = os.path.join(work_dir, "kept")

    def keep(names: dict, kind: str, label: str) -> dict:
        present = {key: name for key, name in names.items() if ours.has(name)}

        if not present:
            return {}

        if len(present) != len(names):
            lines.append(f"[WARN] {ours.name} holds only {len(present)} of the {len(names)} {label}: they are not "
                         "kept (render them again: make_royale_art.py --tiles, then build --minimap/--worldmap)")
            return {}

        os.makedirs(kept_dir, exist_ok=True)
        out = {}

        for key, name in sorted(present.items()):
            path = os.path.join(kept_dir, name.replace("\\", "__"))

            with open(path, "wb") as f:
                f.write(ours.read(name))

            out[key] = path

        record[kind] = old.get(kind, (len(out), "unknown"))
        lines.append(f"[NOTE] kept the {len(out)} {label} of the realm's {ours.name} (this build was given none; "
                     "--drop-map-art leaves them out)")
        return out

    if minimap_wanted and wdt_tiles:
        names = {tile: minimap_tile_name(cfg.map.directory, tile) for tile in sorted(wdt_tiles)}
        listed = set()

        if ours.has(TRS_FILE):
            listed = {key.lower() for key, value in minimap.parse(ours.read(TRS_FILE), f"{ours.name}: trs")
                      if key.lower() == value.lower()}

        unlisted = [n for n in names.values() if n[len("Textures\\Minimap\\"):].lower() not in listed]

        if all(ours.has(n) for n in names.values()) and unlisted:
            lines.append(f"[WARN] {ours.name} holds minimap tiles its md5translate.trs does not list: they are not "
                         "kept (render them again: make_royale_art.py --tiles, then build --minimap)")
        else:
            minimap_tiles = keep(names, "minimap", "minimap tiles")

    if worldmap_wanted and cfg.world_map_area is not None:
        area = cfg.world_map_area.name
        names = {n: world_map_tile_name(area, n) for n in range(1, WORLD_MAP_TILES + 1)}
        world_tiles = keep(names, "worldmap", "world map tiles")

    return minimap_tiles, world_tiles, record, lines


def collisions(patchset: PatchSet, map_archive: str, staging: dict[str, str],
               extra: frozenset = frozenset()) -> list[str]:
    """Map archive files another realm archive already has: terrain paths must be new, and a shared file
    (md5translate.trs) must not be loaded over ours. Extra assets (`extra`, lower-case names) are left to
    extra_asset_notes: they were often found in those very archives."""
    problems = []
    ours = f"Data\\{map_archive}"

    for name in sorted(staging):
        if (name.lower().startswith("dbfilesclient\\") or name in (MARKER_FILE, MAP_ART_FILE)
                or name.lower() in extra):
            continue

        holders = [a for a in patchset.holders(name) if a.name.lower() != map_archive.lower()]

        if not holders:
            continue

        if name.lower() == "textures\\minimap\\md5translate.trs":
            above = [a.name for a in holders if not outranks(ours, [a])]

            if above:
                problems.append(f"{name}: {', '.join(above)} loads over {map_archive}; the merged trs would lose")
        else:
            problems.append(f"{name} is already in {', '.join(a.name for a in holders)}")

    return problems


def extra_asset_notes(patchset: PatchSet, map_archive: str, extra: list[tuple[str, str]]) -> list[str]:
    """Where the realm's archives already hold an extra asset: the same bytes are fine; a different copy in an
    archive that loads over the map archive is what its players see."""
    notes = []
    ours = f"Data\\{map_archive}"

    for name, path in extra:
        holders = [a for a in patchset.holders(name) if a.name.lower() != map_archive.lower()]

        if not holders:
            continue

        with open(path, "rb") as f:
            mine = f.read()

        for archive in holders:
            try:
                same = archive.read(name) == mine
            except PatchError:
                same = False

            over = not outranks(ours, [archive])
            pack = f" (pack {archive.pack})" if archive.pack else ""

            if same:
                notes.append(f"[NOTE] {name}: also in {archive.name}{pack}, same bytes")
            elif over:
                notes.append(f"[WARN] {name}: {archive.name}{pack} holds a different copy and loads over "
                             f"{map_archive}; its players see that one")
            else:
                notes.append(f"[NOTE] {name}: {archive.name}{pack} holds a different copy; {map_archive} loads over it")

    return notes


def write_extract(out_dir: str, cfg: configmod.Config, terrain_files: list, maps: DbcTable, work_dir: str,
                  full: bool) -> list[str]:
    """server/extract/patch-5.MPQ and server-map.json, for the server's extractors (deploy/maps/install-map.sh in
    bleakserv). Server-only: the players' archives never get these tables.

    The extractors read only numbered patches, never a lettered one: map_extractor opens Data/patch-5.MPQ last
    (System.cpp:103-114) and vmap4_extractor opens Data/<locale>/patch-<locale>-2..99.MPQ last (vmapexport.cpp
    scan_patches), so the archive is staged as Data/patch-5.MPQ and Data/enUS/patch-enUS-99.MPQ. Both list the maps
    from Map.dbc and walk every one. By default the archive's Map.dbc holds only this map's row, and an empty
    GameObjectDisplayInfo.dbc stops vmap4_extractor from converting every game object model
    (ExtractGameobjectModels), so both finish in seconds with a few MB instead of 30-90 minutes and gigabytes.
    Nothing else they read is affected: map_extractor reads LiquidType.dbc (stock, from the locale archives) and
    vmap4_extractor nothing more; neither reads AreaTable.dbc. The installer keeps only this map's
    maps/vmaps/mmaps files, never vmaps/GameObjectModels.dtree. full=True ships the whole Map.dbc and no
    GameObjectDisplayInfo.dbc (every map and model is extracted, as before)."""
    extract = dict(terrain_files)
    os.makedirs(work_dir, exist_ok=True)
    map_path = os.path.join(work_dir, "extract-Map.dbc")

    if full:
        maps.write(map_path)
        notes = ["server/extract/patch-5.MPQ: terrain + the full Map.dbc (every map; slow extract)"]
    else:
        only = DbcTable.empty(layout.get("Map"))
        row = list(maps.by_id()[cfg.map.id])

        for i, column in enumerate(only.schema.columns):
            if column.is_string:
                row[i] = only.add_string(maps.string_at(row[i]))

        only.rows.append(row)
        only.write(map_path)
        empty_path = os.path.join(work_dir, "extract-GameObjectDisplayInfo.dbc")
        DbcTable.empty(layout.get("GameObjectDisplayInfo")).write(empty_path)
        extract[layout.archive_name("GameObjectDisplayInfo")] = empty_path
        notes = [f"server/extract/patch-5.MPQ: terrain + a Map.dbc with only map {cfg.map.id} + an empty "
                 "GameObjectDisplayInfo.dbc (fast extract; --full-extract-dbc for every map)"]

    extract[layout.archive_name("Map")] = map_path
    extract_dir = os.path.join(out_dir, "server", "extract")
    os.makedirs(extract_dir, exist_ok=True)
    pack(extract, os.path.join(extract_dir, EXTRACT_PATCH))

    with open(os.path.join(extract_dir, "server-map.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump({"map_id": cfg.map.id, "dir": cfg.map.directory, "patch": EXTRACT_PATCH}, f)
        f.write("\n")

    notes.append("server/extract/server-map.json: for `install-map.sh --from-json`; the installer stages the patch "
                 "as Data/patch-5.MPQ and Data/enUS/patch-enUS-99.MPQ")
    return notes


def write_marker(work_dir: str) -> str:
    os.makedirs(work_dir, exist_ok=True)
    path = os.path.join(work_dir, "mapforge.txt")

    with open(path, "w", encoding="utf-8", newline="\r\n") as f:
        f.write("Written by Tools/MapForge (package.py). This archive is rebuilt on every MapForge run.\n")

    return path


def stage_marker_texture(cfg: configmod.Config, staging: dict[str, str], work_dir: str, report) -> None:
    """The generated patch marker BLP (dbc/marker.py), when the config names one."""
    if not cfg.archives.marker_texture:
        return

    import blpconvert  # noqa: PLC0415  (Tools/BlpConvert, on sys.path)
    from dbc import marker as markermod  # noqa: PLC0415

    path = markermod.write_marker_blp(os.path.join(work_dir, "marker.blp"))
    _, _, problems = blpconvert.check_blp(path)
    report.check(not problems, f"{cfg.archives.marker_texture} (patch marker, generated)", "; ".join(problems))
    staging[cfg.archives.marker_texture] = path


def read_pois(path: str) -> dict:
    """pois.json from a terrain output folder (or the file itself)."""
    if os.path.isdir(path):
        path = os.path.join(path, "pois.json")

    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except OSError as e:
        raise BuildError(f"{path}: {e.strerror}") from None
    except json.JSONDecodeError as e:
        raise BuildError(f"{path}: invalid JSON: {e}") from None


def write_poi_sql(doc: dict, sql_dir: str, map_id: int | None, label: str, report) -> int:
    """bh_royale_poi.sql (the map's rows) and bh_royale_poi_table.sql (the table) into sql_dir; returns the rows."""
    if map_id is not None and doc.get("map_id") not in (None, map_id):
        report.check(False, "pois.json map id", f"{doc.get('map_id')} is not the config's {map_id}")

    try:
        text = sqlgen.poi_sql(doc, map_id, label)
        rows = len(sqlgen.poi_rows(doc, map_id))
    except sqlgen.PoiError as e:
        report.check(False, f"{sqlgen.POI_TABLE} rows", str(e))
        return 0

    os.makedirs(sql_dir, exist_ok=True)

    for filename, body in ((sqlgen.POI_FILE, text), (sqlgen.POI_TABLE_FILE, sqlgen.poi_table_sql())):
        with open(os.path.join(sql_dir, filename), "w", encoding="utf-8", newline="\n") as f:
            f.write(body)

    if any(p["kind"] in sqlgen.ROYALE_POI_KINDS for p in doc.get("pois", [])):
        problems = sqlgen.royale_poi_problems(doc)
        report.check(not problems, "Royale POIs (startup validation and final-site reach)", "; ".join(problems))

    counts = ", ".join(f"{k} {v}" for k, v in sorted(doc.get("counts", {}).items()))
    report.say(f"[NOTE] {sqlgen.POI_FILE}: {rows} rows for `{sqlgen.POI_TABLE}` ({counts}); it goes to bleakserv "
               f"data/sql/updates/pending_db_world as its own rev file after {sqlgen.POI_TABLE_FILE}")
    return rows


def pack(staging: dict[str, str], out_path: str) -> None:
    try:
        mpqpack.write_archive_streaming(out_path, sorted(staging.items()))
    except mpqpack.MpqError as e:
        raise BuildError(f"packing {out_path}: {e}") from None


def prepare_out(out_dir: str, force: bool) -> None:
    if os.path.isdir(out_dir):
        existing = [e for e in os.listdir(out_dir) if e in OUTPUT_ENTRIES]

        if existing and not force:
            raise BuildError(f"{out_dir} already holds MapForge output ({', '.join(existing)}); --force replaces it")

        for entry in existing:
            path = os.path.join(out_dir, entry)
            shutil.rmtree(path) if os.path.isdir(path) else os.remove(path)

    os.makedirs(out_dir, exist_ok=True)


def fix_ids(cfg: configmod.Config, result: forgemod.ForgeResult) -> None:
    """Pin the ids a first forge run chose, so every later run (per merge target) chooses the same ones."""
    if cfg.loading_screen is not None and cfg.loading_screen.reuse is None:
        cfg.loading_screen.id = result.loading_screen_id

    if cfg.light is not None:
        cfg.light.id = result.light_id

    if cfg.world_map_area is not None:
        cfg.world_map_area.id = result.world_map_area_id

    if cfg.battleground is not None:
        for bracket in cfg.battleground.brackets:
            bracket.id = result.bracket_ids[bracket.range_index]

    cfg.zone.area_bit = result.area_bits[cfg.zone.id]

    for subzone in cfg.zone.subzones:
        subzone.area_bit = result.area_bits[subzone.id]


class Report:
    def __init__(self):
        self.lines = []
        self.failed = 0

    def say(self, text: str = ""):
        self.lines.append(text)

    def check(self, ok: bool, what: str, detail: str = ""):
        self.lines.append(f"[{'PASS' if ok else 'FAIL'}] {what}" + (f": {detail}" if detail else ""))
        self.failed += 0 if ok else 1

    def write(self, path: str):
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(self.lines) + "\n")


def cmd_build(args) -> int:
    report = Report()
    cfg = configmod.load(args.config)

    for warning in cfg.warnings:
        report.say(f"[WARN] {warning}")

    required, optional = forgemod.tables_needed(cfg)
    tables, notes = read_tables(args.dbc, required, optional)

    for note in notes:
        report.say(f"[NOTE] {note}")

    input_bytes = {name: table.to_bytes() for name, table in tables.items()}

    # The ids the server's SQL already uses (other content; this map's own files are recognised and skipped).
    reserved = {}

    for root in args.server_sql or []:
        found = sqlgen.scan_server_sql([root], cfg.map.directory)

        for name, ids in found.items():
            reserved.setdefault(name, {}).update(ids)

    # Terrain.
    manifest = None
    terrain_files = []
    wdt_tiles = set()

    extra_files = []
    server_files = []

    if args.terrain:
        manifest, terrain_files, wdt_tiles = read_terrain(args.terrain, cfg)
        extra_files = manifest["_extra"]
        server_files = manifest["_server"]
        report.say(f"[NOTE] terrain: {len(terrain_files)} files, {len(wdt_tiles)} tiles")

        if extra_files:
            used = [u for u in manifest.get("extra_assets", []) if u["modern_used"]]
            report.say(f"[NOTE] extra assets: {len(extra_files)} modern files for {len(used)} uses go into "
                       f"{cfg.archives.map_archive} (every player gets them, HD pack or not)")

        if manifest.get("server_tiles"):
            report.say(f"[NOTE] server/extract gets {manifest['server_tiles']}: the tiles without the "
                       f"{manifest.get('server_doodads_left_out', 0)} modern doodads (vmap4_extractor reads only "
                       "3.3.5 models)")
    else:
        report.say("[WARN] no --terrain: the archive gets DBCs only; a Map.dbc row without the map files crashes "
                   "players on teleport, so do not install this build")

    # The map art given to this run, checked before the output folder is touched.
    minimap_tiles = minimap.collect_tiles(args.minimap) if args.minimap else {}

    if minimap_tiles and wdt_tiles and set(minimap_tiles) != wdt_tiles:
        raise BuildError(f"--minimap: the tiles do not match the WDT (missing {sorted(wdt_tiles - set(minimap_tiles))}"
                         f", extra {sorted(set(minimap_tiles) - wdt_tiles)})")

    world_tiles = {}

    if args.worldmap:
        if cfg.world_map_area is None:
            raise BuildError("--worldmap: the config has no world_map_area, so the client has no world map of this map "
                             "(its WorldMapArea row names the folder Interface\\WorldMap\\<name>\\)")

        world_tiles = collect_world_map_tiles(args.worldmap, cfg.world_map_area.name)
        check_world_map_tiles(world_tiles)

    # The realm's patches: where the modified DBCs must go.
    patchset = None
    placement = None

    if args.patches:
        patchset = PatchSet.scan(args.patches, cfg.archives.optional_packs)

        for archive in patchset.unreadable():
            report.say(f"[WARN] {archive.name}: {archive.error}")

        for problem in planmod.check_map_archive_name(cfg.archives.map_archive, patchset,
                                                      cfg.archives.reserved_letters):
            report.check(False, "map archive name", problem)

    prepare_out(args.out, args.force)
    client_dir = os.path.join(args.out, "client")
    work_dir = os.path.join(args.out, "work")
    os.makedirs(client_dir, exist_ok=True)

    try:
        # Forge on the input copies; this run decides every id.
        baseline = forgemod.Forge(tables, cfg, reserved, wdt_tiles or None)
        result = baseline.run()
        fix_ids(cfg, result)

        for text in result.notes:
            report.say(f"[NOTE] {text}")

        for text in result.warnings:
            report.say(f"[WARN] {text}")

        written = sorted(result.changes)
        dbc_dir = os.path.join(client_dir, "DBFilesClient")
        output_bytes = {}

        for name in written:
            tables[name].write(os.path.join(dbc_dir, layout.file_name(name)))
            output_bytes[name] = tables[name].to_bytes()

        problems = forgemod.check({n: b for n, b in input_bytes.items() if n in written}, output_bytes, cfg, result)
        report.check(not problems, "DBC rows", "; ".join(problems))

        # Placement of the modified DBCs.
        if patchset:
            placement = planmod.plan(patchset, written, cfg.archives.map_archive, cfg.archives.dbc,
                                     cfg.archives.merge_into)

            for problem in planmod.check_inputs_current(patchset, placement,
                                                        {n: input_bytes[n] for n in written}):
                report.check(False, "input DBCs current", problem)

            for problem in placement.problems:
                report.check(False, "DBC placement", problem)

            for note in placement.notes:
                report.say(f"[PLAN] {note}")
        else:
            report.say("[WARN] no --patches: assuming no realm patch holds these DBC files, so they all go into "
                       f"{cfg.archives.map_archive}. Run `package.py doctor --patches ...` on the realm's patches "
                       "to confirm before installing.")

        # The map archive.
        staging = dict(terrain_files)
        staging.update(extra_files)
        staging[MARKER_FILE] = write_marker(work_dir)
        stage_marker_texture(cfg, staging, work_dir, report)

        for note in convert_loading_screens(cfg, staging, work_dir):
            report.say(f"[NOTE] {note}")

        # The map art: the tiles given to this run, else the realm's current map archive's (a rebuild must not take
        # the island off the minimap and the world map), with a record of the terrain each was made for.
        digest = terrain_digest(terrain_files)
        record = {}
        kept_minimap, kept_world = {}, {}

        if patchset and not args.drop_map_art and not (minimap_tiles and world_tiles):
            kept_minimap, kept_world, kept_record, lines = kept_map_art(cfg, patchset, wdt_tiles, not minimap_tiles,
                                                                        not world_tiles, work_dir)

            for line in lines:
                report.say(line)

            for kind, (_, made_for) in sorted(kept_record.items()):
                label = "minimap tiles" if kind == "minimap" else "world map tiles"

                if made_for == "unknown":
                    report.say(f"[NOTE] the kept {label} carry no record of the terrain they were made for")
                elif made_for != digest and digest != "none":
                    report.say(f"[WARN] the {label} kept from {cfg.archives.map_archive} were made for other "
                               "terrain: render them again (make_royale_art.py --tiles; bleakserv "
                               "deploy/maps/README.md, \"The island on the minimap and the world map\")")

            record.update(kept_record)

        if minimap_tiles:
            record["minimap"] = (len(minimap_tiles), digest)

        if world_tiles:
            record["worldmap"] = (len(world_tiles), digest)

        if minimap_tiles or kept_minimap:
            for note in stage_minimap(cfg, minimap_tiles or kept_minimap, args.trs, patchset, staging, work_dir,
                                      wdt_tiles):
                report.say(f"[NOTE] {note}")

        if world_tiles or kept_world:
            stage_worldmap(cfg, world_tiles or kept_world, staging, work_dir)
            area = cfg.world_map_area.name
            source = args.worldmap if world_tiles else f"the realm's {cfg.archives.map_archive}"
            report.say(f"[NOTE] Interface\\WorldMap\\{area}\\: {area}1-{WORLD_MAP_TILES} (DXT1 {TILE_SIZE} x "
                       f"{TILE_SIZE}; 4 x 3 tiles of a 1024 x 768 picture whose top-left 1002 x 668 is the map frame) "
                       f"from {source}")

        if record:
            staging[MAP_ART_FILE] = write_art_record(record, work_dir)
        elif cfg.world_map_area is not None:
            report.say("[NOTE] no minimap or world map tiles: the island's minimap stays black and the addon covers "
                       "the stock world map (build --minimap/--worldmap; bleakserv deploy/maps/README.md)")

        map_archive_tables = placement.map_archive_tables() if placement else list(written)

        if patchset:
            extra_names = frozenset(n.lower() for n, _ in extra_files)

            for problem in collisions(patchset, cfg.archives.map_archive, staging, extra_names):
                report.check(False, "map archive paths", problem)

            for note in extra_asset_notes(patchset, cfg.archives.map_archive, extra_files):
                report.say(note)

            if placement:
                for name in map_archive_tables:
                    winners = set(placement.files[name].winners.values())

                    if winners - {""}:
                        report.say(f"[WARN] {layout.file_name(name)}: players without "
                                   f"{', '.join(sorted(winners - {''}))} get the copy in {cfg.archives.map_archive}, "
                                   "built from the input (that archive's copy); check it holds no pack-only rows")

        for name in map_archive_tables:
            staging[layout.archive_name(name)] = os.path.join(dbc_dir, layout.file_name(name))

        map_archive_path = os.path.join(client_dir, cfg.archives.map_archive)
        pack(staging, map_archive_path)
        report.say(f"[NOTE] {cfg.archives.map_archive}: {len(staging)} files "
                   f"({len(map_archive_tables)} DBCs: {', '.join(map_archive_tables) or 'none'})")

        # Merge targets: each rebuilt from its own copies with the same rows forged in.
        for target_name in (placement.targets if placement else []):
            target = patchset.find(target_name)
            merged_tables = {}
            table_names = placement.target_tables(target_name)

            for name in required + [n for n in optional if n in tables]:
                if target.has(layout.archive_name(name)):
                    merged_tables[name] = DbcTable.from_bytes(target.read(layout.archive_name(name)),
                                                              layout.get(name), f"{target_name}: {name}")
                elif name in tables:
                    merged_tables[name] = DbcTable.from_bytes(input_bytes[name], layout.get(name))

            forgemod.Forge(merged_tables, cfg, reserved, wdt_tiles or None).run()
            replacements = {}

            for name in table_names:
                path = os.path.join(work_dir, f"{target_name}.{layout.file_name(name)}")
                merged_tables[name].write(path)
                replacements[layout.archive_name(name)] = path

            out_path = os.path.join(client_dir, target.name)
            rebuild(target, replacements, out_path, os.path.join(work_dir, "rebuild"))
            report.say(f"[NOTE] {target.name}: rebuilt with {', '.join(table_names)} replaced "
                       f"(install it OVER the realm's current {target.name})")

        # Server SQL.
        sql_dir = os.path.join(args.out, "server", "sql")
        os.makedirs(sql_dir, exist_ok=True)
        sql_files = sqlgen.build(tables, cfg, result)

        for filename, text in sql_files.items():
            with open(os.path.join(sql_dir, filename), "w", encoding="utf-8", newline="\n") as f:
                f.write(text)

        report.say(f"[NOTE] server SQL: {sql_dir}; bleakhold_royale.sql goes to bleakserv "
                   "data/sql/updates/pending_db_world/rev_<timestamp>.sql")

        if args.terrain and os.path.isfile(os.path.join(args.terrain, "pois.json")):
            write_poi_sql(read_pois(args.terrain), sql_dir, cfg.map.id, f"{cfg.map.name.name} ({cfg.map.directory})",
                          report)
        elif args.terrain:
            report.say("[WARN] the terrain output has no pois.json: no bh_royale_poi rows")

        if args.pending:
            path = os.path.join(args.pending, f"rev_{time.time_ns()}.sql")

            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(sql_files["bleakhold_royale.sql"])

            report.say(f"[NOTE] wrote {path}")

        if terrain_files:
            for note in write_extract(args.out, cfg, server_files, tables["Map"], work_dir, args.full_extract_dbc):
                report.say(f"[NOTE] {note}")

        # Re-read the archive and check it holds what was staged.
        with mpqpack.MpqArchive(map_archive_path) as archive:
            verify = archive.verify()
            report.check(not verify.problems, f"{cfg.archives.map_archive} readable by the client",
                         "; ".join(verify.problems))
            report.check(verify.lookup_mode.startswith("listfile"), f"{cfg.archives.map_archive} listfile lookup",
                         verify.lookup_mode)
            listed = {mpqpack.name_key(n) for n in archive.names()}
            missing = [n for n in staging if mpqpack.name_key(n) not in listed]
            report.check(not missing, f"{cfg.archives.map_archive} contents", ", ".join(missing))
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

        if patchset:
            patchset.close()

    report.say()
    report.say(f"Map {cfg.map.id} ({cfg.map.directory}), zone {cfg.zone.id}, areas {cfg.area_ids()}")
    report.write(os.path.join(args.out, "report.txt"))
    print("\n".join(report.lines))
    print(f"\n{'FAILED' if report.failed else 'OK'}: {args.out}/report.txt")
    return 1 if report.failed else 0


def cmd_pull(args) -> int:
    cfg = configmod.load(args.config) if args.config else None
    packs = cfg.archives.optional_packs if cfg else {}
    patchset = PatchSet.scan(args.patches, packs)
    names = list(layout.SERVER) + ["LoadingScreens"] + list(layout.TABLES)
    seen = set()
    all_on = frozenset({a.pack for a in patchset.archives if a.pack})
    os.makedirs(args.out, exist_ok=True)
    missing = []

    try:
        for name in names:
            if name in seen:
                continue

            seen.add(name)
            top = patchset.top(layout.archive_name(name), all_on)

            if top is None:
                missing.append(layout.file_name(name))
                continue

            data = top.read(layout.archive_name(name))
            DbcTable.from_bytes(data, layout.get(name), f"{top.name}: {name}")  # layout check

            with open(os.path.join(args.out, layout.file_name(name)), "wb") as f:
                f.write(data)

            print(f"{layout.file_name(name)}: from {top.name}")
    finally:
        patchset.close()

    if missing:
        print(f"\nNot in any patch (take them from the server's data/dbc, or extract them from the client's locale "
              f"archives): {', '.join(missing)}")

    return 0


def cmd_doctor(args) -> int:
    cfg = configmod.load(args.config) if args.config else None
    packs = cfg.archives.optional_packs if cfg else {}
    patchset = PatchSet.scan(args.patches, packs)

    try:
        print(f"{len(patchset.archives)} patch archives in {patchset.folder} (client load order, last wins):")

        for archive in patchset.archives:
            state = archive.error or f"{len(archive.reader.blocks)} files"
            pack_note = f" [pack {archive.pack}]" if archive.pack else ""
            print(f"  {archive.client_path}{pack_note}: {state}")

        tables = list(dict.fromkeys(list(layout.SERVER) + ["LoadingScreens"]))
        map_archive = cfg.archives.map_archive if cfg else "patch-Q.MPQ"
        dbc_mode = cfg.archives.dbc if cfg else "auto"
        merge_into = cfg.archives.merge_into if cfg else None
        placement = planmod.plan(patchset, tables, map_archive, dbc_mode, merge_into)
        print(f"\nPlacement of the modified DBCs (map archive {map_archive}, mode {dbc_mode}):")

        for note in placement.notes:
            print(f"  {note}")

        for problem in placement.problems:
            print(f"  PROBLEM: {problem}")

        if cfg:
            for problem in planmod.check_map_archive_name(map_archive, patchset, cfg.archives.reserved_letters):
                print(f"  PROBLEM: {problem}")

        trs = patchset.holders("Textures\\Minimap\\md5translate.trs")

        if trs:
            print(f"\nmd5translate.trs is in: {', '.join(a.name for a in trs)} (the build must merge into the last)")

        ours = patchset.find(map_archive) if cfg else None

        if ours and ours.reader:
            area = cfg.world_map_area.name if cfg.world_map_area else None
            world = sum(ours.has(world_map_tile_name(area, n)) for n in range(1, WORLD_MAP_TILES + 1)) if area else 0
            prefix = cfg.map.directory.lower() + "\\"
            listed = [v for k, v in minimap.parse(ours.read(TRS_FILE), ours.name)
                      if k.lower().startswith(prefix)] if ours.has(TRS_FILE) else []
            mini = sum(ours.has(f"Textures\\Minimap\\{v}") for v in listed)
            print(f"\nMap art in {ours.name}: {mini} minimap tiles, {world} of {WORLD_MAP_TILES} world map tiles "
                  "(a build keeps them unless it is given new ones or --drop-map-art)")

        return 1 if placement.problems else 0
    finally:
        patchset.close()


def check_map_art(cfg: configmod.Config, archive, report: Report) -> None:
    """The map art in the map archive is whole or absent: every tile md5translate.trs lists for this map, and all
    twelve world map tiles, each a 256 x 256 DXT1 BLP the client draws. Absent art is a note, not a failure."""
    name = cfg.archives.map_archive

    def problems_of(path: str) -> str:
        if not archive.has_file(path):
            return f"{path} is missing"

        found = tile_blp_problems(archive.read(path))
        return f"{path}: {'; '.join(found)}" if found else ""

    listed = []

    if archive.has_file(TRS_FILE):
        prefix = cfg.map.directory.lower() + "\\"
        listed = [f"Textures\\Minimap\\{value}" for key, value in minimap.parse(archive.read(TRS_FILE), name)
                  if key.lower().startswith(prefix)]

    if listed:
        bad = [p for p in map(problems_of, listed) if p]
        report.check(not bad, f"{name} holds the minimap tiles its md5translate.trs lists ({len(listed)})",
                     ", ".join(bad))
    else:
        report.say(f"[NOTE] {name} has no minimap tiles of {cfg.map.directory}: the minimap stays black there (build "
                   "--minimap)")

    if cfg.world_map_area is None:
        return

    area = cfg.world_map_area.name
    names = [world_map_tile_name(area, n) for n in range(1, WORLD_MAP_TILES + 1)]

    if not any(archive.has_file(n) for n in names):
        report.say(f"[NOTE] {name} has no world map tiles of {area}: the addon covers the stock world map (build "
                   "--worldmap)")
        return

    bad = [p for p in map(problems_of, names) if p]
    report.check(not bad, f"{name} holds the world map tiles ({area}1-{WORLD_MAP_TILES}, DXT1 {TILE_SIZE} x "
                 f"{TILE_SIZE})", ", ".join(bad))


def cmd_validate(args) -> int:
    cfg = configmod.load(args.config)
    report = Report()
    dbc_dir = os.path.join(args.out, "client", "DBFilesClient")
    found = {}

    if os.path.isdir(dbc_dir):
        for entry in sorted(os.listdir(dbc_dir)):
            for name in layout.TABLES:
                if entry.lower() == layout.file_name(name).lower():
                    with open(os.path.join(dbc_dir, entry), "rb") as f:
                        found[name] = f.read()

    report.check(bool(found), "output DBCs found", dbc_dir)

    for name, data in sorted(found.items()):
        try:
            table = DbcTable.from_bytes(data, layout.get(name), layout.file_name(name))
            ids = table.ids()
            report.check(len(ids) == len(table.rows), f"{layout.file_name(name)} unique ids")
        except DbcError as e:
            report.check(False, layout.file_name(name), str(e))

    archive_path = os.path.join(args.out, "client", cfg.archives.map_archive)

    if os.path.isfile(archive_path):
        with mpqpack.MpqArchive(archive_path) as archive:
            verify = archive.verify()
            report.check(not verify.problems, cfg.archives.map_archive, "; ".join(verify.problems))
            wdt = f"World\\Maps\\{cfg.map.directory}\\{cfg.map.directory}.wdt"
            report.check(archive.has_file(wdt), f"{cfg.archives.map_archive} holds the WDT", wdt)

            if cfg.archives.marker_texture:
                report.check(archive.has_file(cfg.archives.marker_texture),
                             f"{cfg.archives.map_archive} holds the patch marker", cfg.archives.marker_texture)

            check_map_art(cfg, archive, report)
    else:
        report.check(False, "map archive", f"{archive_path} is missing")

    print("\n".join(report.lines))
    return 1 if report.failed else 0


def cmd_poi_sql(args) -> int:
    report = Report()
    doc = read_pois(args.pois)
    rows = write_poi_sql(doc, args.out, args.map_id, args.label or doc.get("map_directory", ""), report)
    print("\n".join(report.lines))
    return 1 if report.failed or not rows else 0


def resolve_asset(use, sources: SourceSet, stock: set[str], copies: dict) -> dict:
    """One modern path: found complete in the sources (status "resolved", with the files to ship) or not (status
    "fallback", with the reason). `copies` collects {path: (bytes, source)} for every file to ship."""
    entry = {"modern": use.modern, "fallback": use.fallback, "kind": use.kind, "status": "fallback", "reason": "",
             "source": None, "files": [], "stock": []}
    key = extra_assets.norm(use.modern)
    why = extra_assets.unsafe_path(use.modern)

    if why:
        entry["reason"] = f"{use.modern!r} is not a plain relative client path ({why})"
        return entry

    if key in stock:
        entry.update(status="resolved", reason="a 3.3.5 listfile path: every client has it", source="stock")
        entry["stock"].append(use.modern)

        if use.kind == "texture":
            entry["specular"] = extra_assets.norm(extra_assets.specular_name(use.modern)) in stock

        return entry

    try:
        found = sources.read(use.modern)
    except SourceReadError as e:
        # The copy the client loads; a lower source's copy may be another version, so it is not used instead.
        entry["reason"] = str(e)
        return entry

    if found is None:
        entry["reason"] = "not in the sources" if sources.layers else "no --sources given (offline): falls back"
        return entry

    data, label = found
    entry["source"] = label
    files = {use.modern: (data, label)}

    if use.kind == "texture":
        problem = extra_assets.blp_problem(data)

        if problem:
            entry["reason"] = problem
            return entry

        spec_name = extra_assets.specular_name(use.modern)

        try:
            spec_found = sources.read(spec_name)
        except SourceReadError as e:
            entry["reason"] = f"needs {spec_name}: {e}"
            return entry

        if spec_found is not None and not extra_assets.blp_problem(spec_found[0]):
            files[spec_name] = spec_found
            entry["specular"] = True
        else:
            entry["specular"] = extra_assets.norm(spec_name) in stock

            if entry["specular"]:
                entry["stock"].append(spec_name)
    else:
        try:
            deps = extra_assets.m2_dependencies(use.modern, data)
        except extra_assets.ResolutionError as e:
            entry["reason"] = str(e)
            return entry

        entry["collision"] = deps["collision"]
        entry["format"] = f"M2 version {deps['version']}"

        if deps["fdid"]:
            entry["reason"] = (f"names its files by FileDataID ({', '.join(deps['fdid'])}): a client without the "
                               "HD pack's listfile.csv shows placeholders; use a path-named (MD20) version")
            return entry

        for dep in deps["skins"] + deps["textures"] + deps["anims"]:
            why = extra_assets.unsafe_path(dep)

            if why:
                entry["reason"] = f"names {dep!r}, which is not a plain relative client path ({why})"
                return entry

            if extra_assets.norm(dep) in stock:
                entry["stock"].append(dep)
                continue

            try:
                dep_found = sources.read(dep)
            except SourceReadError as e:
                entry["reason"] = f"needs {dep}: {e}"
                return entry

            if dep_found is None:
                entry["reason"] = f"needs {dep}, which no source holds"
                return entry

            files[dep] = dep_found

    entry["status"] = "resolved"

    for path, (blob, source) in files.items():
        # One copy per file whatever the spelling (models name shared textures in any case): every entry points
        # at the spelling written first, which is the one under files/.
        canon, blob = copies.setdefault(extra_assets.norm(path), (path, blob))
        entry["files"].append({"path": path, "file": extra_assets.file_rel(canon), "size": len(blob),
                               "sha256": hashlib.sha256(blob).hexdigest(), "source": source})

    return entry


def cmd_resolve_assets(args) -> int:
    """Which modern files of the spec's extra assets the sources hold: writes <out>/asset_resolution.json and the
    files under <out>/files/ for `terrain/build.py --resolution`."""
    spec = load_spec(args.spec)
    uses = {}

    for use in spec.assets:
        key = extra_assets.norm(use.modern)
        known = uses.get(key)

        if known is not None and known.kind != use.kind:
            raise BuildError(f"{use.where}: {use.modern} is used as a {use.kind} and as a {known.kind}")

        uses.setdefault(key, use)

    stock = set()

    for path in args.listfile or []:
        try:
            stock |= extra_assets.load_listfile(path)
        except (OSError, ValueError) as e:
            raise BuildError(f"--listfile {path}: {e}") from None

    out = args.out
    target = os.path.join(out, extra_assets.RESOLUTION_FILE)
    files_dir = os.path.join(out, extra_assets.FILES_DIR)

    if os.path.exists(target) or os.path.exists(files_dir):
        if not args.force:
            raise BuildError(f"{out} already holds a resolution; --force replaces it")

        shutil.rmtree(files_dir, ignore_errors=True)

    sources = SourceSet(args.sources or [])
    copies: dict = {}
    entries = []

    try:
        for problem in sources.problems:
            print(f"warning: {problem}")

        opened = len(sources.problems)

        for key in sorted(uses):
            entries.append(resolve_asset(uses[key], sources, stock, copies))

        for problem in sources.problems[opened:]:  # files a source holds but cannot read (their assets fall back)
            print(f"warning: {problem}")
    finally:
        sources.close()

    os.makedirs(out, exist_ok=True)
    root = os.path.realpath(files_dir)

    for path, blob in copies.values():
        dest = os.path.join(out, *extra_assets.file_rel(path).split("/"))

        if os.path.commonpath([os.path.realpath(dest), root]) != root:
            raise BuildError(f"{path!r} would be written outside {files_dir}")

        os.makedirs(os.path.dirname(dest), exist_ok=True)

        with open(dest, "wb") as f:
            f.write(blob)

    doc = {"format": extra_assets.FORMAT, "generator": "MapForge package.py resolve-assets",
           "spec": os.path.basename(args.spec), "sources": list(sources.labels),
           "listfiles": [os.path.basename(p) for p in args.listfile or []], "assets": entries}

    with open(target, "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, indent=2)
        f.write("\n")

    resolved = [e for e in entries if e["status"] == "resolved"]
    print(f"{len(resolved)} of {len(entries)} extra assets resolved, {len(copies)} files to ship; wrote {target}")

    for e in entries:
        if e["status"] == "resolved":
            print(f"  modern   {e['modern']}  (from {e['source']}, {len(e['files'])} files to ship)")
        else:
            found = f"; found in {e['source']}" if e["source"] else ""
            print(f"  fallback {e['modern']}  ({e['reason']}{found})")

        if stock and e["status"] != "resolved" and extra_assets.norm(e["fallback"]) not in stock:
            print(f"  warning: its fallback {e['fallback']} is not in the 3.3.5 listfile")

    return 0


def cmd_schemas(args) -> int:
    rec_dir = layout.default_rec_dir()

    if not rec_dir:
        print("WoW/Source/DB/Rec not found next to the tool", file=sys.stderr)
        return 2

    text = layout.emit_schemas_module(rec_dir)
    path = os.path.join(HERE, "dbc", "schemas.py")

    if args.write:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)

        print(f"wrote {path}")
        return 0

    with open(path, encoding="utf-8") as f:
        current = f.read()

    if current != text:
        print("dbc/schemas.py is stale: run `package.py schemas --write`", file=sys.stderr)
        return 1

    print("dbc/schemas.py matches the client's Rec classes")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="package.py", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("build", help="add the map's rows to the realm's DBCs, pack the archives, write the SQL")
    p.add_argument("--config", required=True,
                   help="the map's JSON config (bleakhold_royale_v2.json; v1: bleakhold_royale.json)")
    p.add_argument("--dbc", required=True, help="folder with the realm's CURRENT DBCs (package.py pull)")
    p.add_argument("--out", required=True, help="output folder")
    p.add_argument("--terrain", help="the terrain build's output folder (terrain_manifest.json)")
    p.add_argument("--patches", help="the realm's patch folder (/srv/bleakhold-launcher/patches), for placement")
    p.add_argument("--server-sql", action="append", help="bleakserv SQL roots to check ids against (repeatable)")
    p.add_argument("--minimap", help="folder with minimap tiles map<X>_<Y>.blp or .png")
    p.add_argument("--worldmap", help="folder with the world map tiles <area>1..12 (.png or DXT1 .blp, 256 x 256; "
                                      "<area> is the config's world_map_area name)")
    p.add_argument("--trs", help="the md5translate.trs the players load today, or a client Data folder to read it "
                                 "from (build-royale.sh's stage); default: from --patches")
    p.add_argument("--drop-map-art", action="store_true",
                   help="ship no minimap or world map tiles this run is not given (by default a build keeps those of "
                        "the realm's current map archive in --patches)")
    p.add_argument("--pending", help="also write the install SQL as rev_<ns>.sql into this folder "
                                     "(bleakserv/data/sql/updates/pending_db_world)")
    p.add_argument("--full-extract-dbc", action="store_true",
                   help="server/extract/patch-5.MPQ gets the full Map.dbc and no empty GameObjectDisplayInfo.dbc "
                        "(the extractors then walk every map and model)")
    p.add_argument("--force", action="store_true", help="replace existing output")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("pull", help="extract the winning copy of each map DBC from the realm's patches")
    p.add_argument("--patches", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--config", help="for archives.optional_packs")
    p.set_defaults(func=cmd_pull)

    p = sub.add_parser("doctor", help="list the realm's patches and where the modified DBCs must go")
    p.add_argument("--patches", required=True)
    p.add_argument("--config", help="for the archive names and packs")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("validate", help="check an output folder again")
    p.add_argument("--config", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("poi-sql", help="write the bh_royale_poi SQL from a terrain build's pois.json")
    p.add_argument("--pois", required=True, help="the terrain build's output folder, or its pois.json")
    p.add_argument("--out", required=True, help="folder for bh_royale_poi.sql and bh_royale_poi_table.sql")
    p.add_argument("--map-id", type=int, help="the map id (default: pois.json's map_id)")
    p.add_argument("--label", help="a name for the SQL header (default: the map directory)")
    p.set_defaults(func=cmd_poi_sql)

    p = sub.add_parser("resolve-assets", help="find the modern files of a terrain spec's extra assets (on the VPS) "
                                              "and write the resolution file the terrain build uses")
    p.add_argument("--spec", required=True, help="the terrain spec (JSON) naming the extra assets")
    p.add_argument("--sources", nargs="*", default=[], help="where to look, in order: folders (the launcher's patches "
                                                           "folder, loose files) and MPQ files; none = all fall back")
    p.add_argument("--listfile", action="append", help="a 3.3.5a listfile or asset kit: files in it are in every "
                                                       "client and are not copied (repeatable)")
    p.add_argument("--out", required=True, help="folder for asset_resolution.json and files/")
    p.add_argument("--force", action="store_true", help="replace an existing resolution")
    p.set_defaults(func=cmd_resolve_assets)

    p = sub.add_parser("schemas", help="check or regenerate dbc/schemas.py from WoW/Source/DB/Rec")
    p.add_argument("--write", action="store_true")
    p.add_argument("--check", action="store_true")
    p.set_defaults(func=cmd_schemas)

    args = parser.parse_args(argv)

    try:
        return args.func(args)
    except (BuildError, configmod.ConfigError, forgemod.ForgeError, planmod.PlanError, PatchError,
            minimap.TrsError, DbcError, mpqpack.MpqError, SpecError, extra_assets.ResolutionError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
