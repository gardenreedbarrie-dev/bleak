#!/usr/bin/env python3
"""MapForge packaging: the new map's DBC rows, the patch archives for players, and the AzerothCore SQL.

    python3 -I Tools/MapForge/package.py build --config <map.json> --dbc <folder> --out <folder>
        [--terrain <terrain output>] [--patches <realm patch folder>] [--server-sql <bleakserv/data/sql> ...]
        [--minimap <tile folder>] [--force]
    python3 -I Tools/MapForge/package.py pull --patches <folder> --out <folder> [--config <map.json>]
    python3 -I Tools/MapForge/package.py doctor --patches <folder> [--config <map.json>]
    python3 -I Tools/MapForge/package.py validate --config <map.json> --out <folder>
    python3 -I Tools/MapForge/package.py schemas [--check | --write]

It ships no game data: it reads the DBC files and archives you give it and writes modified copies. The terrain
(World\\Maps\\...) comes from Tools/MapForge/terrain. See README.md, section "Data and packaging".
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
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
from dbc.patches import PatchError, PatchSet, outranks, rebuild  # noqa: E402

import mpqpack  # noqa: E402
from rflib.dbc import DbcError, DbcTable  # noqa: E402

MARKER_FILE = "MapForge\\mapforge.txt"
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
    """(manifest, client files to pack as (archive name, path on disk), WDT tiles)."""
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


def stage_minimap(cfg: configmod.Config, tile_folder: str, trs_base: str | None, patchset: PatchSet | None,
                  staging: dict[str, str], work_dir: str, wdt_tiles: set[tuple[int, int]]) -> list[str]:
    """Stage Textures\\Minimap tiles and the merged md5translate.trs."""
    directory = cfg.map.directory
    tiles = minimap.collect_tiles(tile_folder)
    notes = []

    if wdt_tiles and set(tiles) != wdt_tiles:
        missing = sorted(wdt_tiles - set(tiles))
        extra = sorted(set(tiles) - wdt_tiles)
        raise BuildError(f"--minimap: the tiles do not match the WDT (missing {missing}, extra {extra})")

    os.makedirs(work_dir, exist_ok=True)

    for (tx, ty), path in sorted(tiles.items()):
        archive_name = f"Textures\\Minimap\\{directory}\\map{tx}_{ty:02d}.blp"

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
    base = b""
    source = ""

    if trs_base:
        with open(trs_base, "rb") as f:
            base = f.read()

        source = trs_base
    elif patchset:
        all_on = frozenset({a.pack for a in patchset.archives if a.pack})
        top = patchset.top("Textures\\Minimap\\md5translate.trs", all_on)

        if top:
            base = top.read("Textures\\Minimap\\md5translate.trs")
            source = top.name

    if not base:
        raise BuildError("--minimap needs the realm's current md5translate.trs (--trs, or --patches with an archive "
                         "holding it): shipping only our lines would break every stock map's minimap")

    merged = minimap.build(minimap.parse(base, source or "md5translate.trs"), directory, sorted(tiles))
    trs_path = os.path.join(work_dir, "md5translate.trs")

    with open(trs_path, "wb") as f:
        f.write(merged)

    staging["Textures\\Minimap\\md5translate.trs"] = trs_path
    notes.append(f"md5translate.trs: merged from {source or trs_base} plus {len(tiles)} tile lines")
    return notes


def collisions(patchset: PatchSet, map_archive: str, staging: dict[str, str]) -> list[str]:
    """Map archive files another realm archive already has: terrain paths must be new, and a shared file
    (md5translate.trs) must not be loaded over ours."""
    problems = []
    ours = f"Data\\{map_archive}"

    for name in sorted(staging):
        if name.lower().startswith("dbfilesclient\\") or name == MARKER_FILE:
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


def write_marker(work_dir: str) -> str:
    os.makedirs(work_dir, exist_ok=True)
    path = os.path.join(work_dir, "mapforge.txt")

    with open(path, "w", encoding="utf-8", newline="\r\n") as f:
        f.write("Written by Tools/MapForge (package.py). This archive is rebuilt on every MapForge run.\n")

    return path


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

    if args.terrain:
        manifest, terrain_files, wdt_tiles = read_terrain(args.terrain, cfg)
        report.say(f"[NOTE] terrain: {len(terrain_files)} files, {len(wdt_tiles)} tiles")
    else:
        report.say("[WARN] no --terrain: the archive gets DBCs only; a Map.dbc row without the map files crashes "
                   "players on teleport, so do not install this build")

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
        staging[MARKER_FILE] = write_marker(work_dir)

        for note in convert_loading_screens(cfg, staging, work_dir):
            report.say(f"[NOTE] {note}")

        if args.minimap:
            for note in stage_minimap(cfg, args.minimap, args.trs, patchset, staging, work_dir, wdt_tiles):
                report.say(f"[NOTE] {note}")

        map_archive_tables = placement.map_archive_tables() if placement else list(written)

        if patchset:
            for problem in collisions(patchset, cfg.archives.map_archive, staging):
                report.check(False, "map archive paths", problem)

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

        if args.pending:
            path = os.path.join(args.pending, f"rev_{time.time_ns()}.sql")

            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(sql_files["bleakhold_royale.sql"])

            report.say(f"[NOTE] wrote {path}")

        # The server's extractors read only patch.MPQ / patch-2..5.MPQ (map_extractor) and patch-N.MPQ
        # (vmap4_extractor), never a lettered patch, and list the maps from Map.dbc: give them one archive with the
        # terrain and the new Map.dbc, to stage as Data/patch-5.MPQ and Data/enUS/patch-enUS-9.MPQ.
        if terrain_files:
            extract = dict(terrain_files)
            extract["DBFilesClient\\Map.dbc"] = os.path.join(dbc_dir, "Map.dbc")
            extract_dir = os.path.join(args.out, "server", "extract")
            os.makedirs(extract_dir, exist_ok=True)
            pack(extract, os.path.join(extract_dir, "patch-5.MPQ"))
            report.say(f"[NOTE] {extract_dir}/patch-5.MPQ: terrain + Map.dbc for map_extractor / vmap4_extractor")

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

        return 1 if placement.problems else 0
    finally:
        patchset.close()


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
    else:
        report.check(False, "map archive", f"{archive_path} is missing")

    print("\n".join(report.lines))
    return 1 if report.failed else 0


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
    p.add_argument("--config", required=True, help="the map's JSON config (bleakhold_royale.json)")
    p.add_argument("--dbc", required=True, help="folder with the realm's CURRENT DBCs (package.py pull)")
    p.add_argument("--out", required=True, help="output folder")
    p.add_argument("--terrain", help="the terrain build's output folder (terrain_manifest.json)")
    p.add_argument("--patches", help="the realm's patch folder (/srv/bleakhold-launcher/patches), for placement")
    p.add_argument("--server-sql", action="append", help="bleakserv SQL roots to check ids against (repeatable)")
    p.add_argument("--minimap", help="folder with minimap tiles map<X>_<Y>.blp or .png")
    p.add_argument("--trs", help="the realm's current md5translate.trs (default: read from --patches)")
    p.add_argument("--pending", help="also write the install SQL as rev_<ns>.sql into this folder "
                                     "(bleakserv/data/sql/updates/pending_db_world)")
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

    p = sub.add_parser("schemas", help="check or regenerate dbc/schemas.py from WoW/Source/DB/Rec")
    p.add_argument("--write", action="store_true")
    p.add_argument("--check", action="store_true")
    p.set_defaults(func=cmd_schemas)

    args = parser.parse_args(argv)

    try:
        return args.func(args)
    except (BuildError, configmod.ConfigError, forgemod.ForgeError, planmod.PlanError, PatchError,
            minimap.TrsError, DbcError, mpqpack.MpqError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
