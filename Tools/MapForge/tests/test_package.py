"""package.py end to end on a made-up realm: DBC folder, patch folder with optional packs, terrain output."""

import contextlib
import io
import json
import os
import shutil
import struct
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL_DIR = os.path.dirname(HERE)

if TOOL_DIR not in sys.path:
    sys.path.insert(0, TOOL_DIR)

import package  # noqa: E402
from dbc import layout  # noqa: E402
from tests import synth_dbc, synth_mpq  # noqa: E402

import mpqpack  # noqa: E402
from rflib.dbc import DbcTable  # noqa: E402

MAP = "DBFilesClient\\Map.dbc"
AREA = "DBFilesClient\\AreaTable.dbc"
DIRECTORY = "BleakholdRoyale"


def write_terrain(folder: str, tiles=synth_dbc.TILES, area_ids=(5100,)):
    """A stand-in for the terrain build's output: the folder layout and the manifest, with placeholder files."""
    maps = os.path.join(folder, "World", "Maps", DIRECTORY)
    os.makedirs(maps, exist_ok=True)
    main = bytearray(4096 * 8)

    for tx, ty in tiles:
        struct.pack_into("<I", main, 8 * (64 * ty + tx), 1)

    wdt = b"REVM" + struct.pack("<II", 4, 18) + b"DHPM" + struct.pack("<I", 32) + bytes(32) + b"NIAM" + \
        struct.pack("<I", len(main)) + bytes(main)

    with open(os.path.join(maps, f"{DIRECTORY}.wdt"), "wb") as f:
        f.write(wdt)

    with open(os.path.join(maps, f"{DIRECTORY}.wdl"), "wb") as f:
        f.write(b"REVM" + struct.pack("<II", 4, 18))

    for tx, ty in tiles:
        with open(os.path.join(maps, f"{DIRECTORY}_{tx}_{ty}.adt"), "wb") as f:
            f.write(b"REVM" + struct.pack("<II", 4, 18) + bytes(64))

    with open(os.path.join(folder, "terrain_manifest.json"), "w", encoding="utf-8") as f:
        json.dump({"directory": DIRECTORY, "tiles": [list(t) for t in sorted(tiles)], "area_ids": list(area_ids)}, f)


def run(*argv) -> tuple[int, str]:
    out = io.StringIO()
    err = io.StringIO()

    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = package.main(list(argv))

    return code, out.getvalue() + err.getvalue()


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dbc = os.path.join(self.tmp, "dbc")
        self.raw = synth_dbc.write_tables(self.dbc)
        self.terrain = os.path.join(self.tmp, "terrain")
        write_terrain(self.terrain)
        self.config = os.path.join(self.tmp, "map.json")

        with open(self.config, "w", encoding="utf-8") as f:
            json.dump(synth_dbc.default_config(), f)

        self.patches = os.path.join(self.tmp, "patches")
        os.makedirs(self.patches)
        self.out = os.path.join(self.tmp, "out")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def build(self, *extra) -> tuple[int, str]:
        return run("build", "--config", self.config, "--dbc", self.dbc, "--terrain", self.terrain,
                   "--patches", self.patches, "--out", self.out, *extra)

    def test_no_realm_patch_holds_the_tables(self):
        synth_mpq.write(os.path.join(self.patches, "patch-R.MPQ"), {"DBFilesClient\\ChrRaces.dbc": b"races"})
        code, output = self.build()
        self.assertEqual(code, 0, output)

        with mpqpack.MpqArchive(os.path.join(self.out, "client", "patch-Q.MPQ")) as archive:
            names = sorted(archive.names())
            self.assertEqual(archive.verify().problems, [])

        dbcs = [n for n in names if n.startswith("DBFilesClient\\")]
        self.assertEqual(dbcs, sorted(layout.archive_name(n) for n in ("AreaTable", "BattlemasterList", "Light",
                                                                       "Map", "PvpDifficulty", "WorldMapArea")))
        self.assertIn(f"World\\Maps\\{DIRECTORY}\\{DIRECTORY}.wdt", names)
        self.assertIn(f"World\\Maps\\{DIRECTORY}\\{DIRECTORY}.wdl", names)
        self.assertEqual(len([n for n in names if n.endswith(".adt")]), 4)
        self.assertIn("MapForge\\mapforge.txt", names)
        # The client copies in the archive equal the written DBCs, and keep every input row.
        with mpqpack.MpqArchive(os.path.join(self.out, "client", "patch-Q.MPQ")) as archive:
            data = archive.read(MAP)

        with open(os.path.join(self.out, "client", "DBFilesClient", "Map.dbc"), "rb") as f:
            self.assertEqual(f.read(), data)

        maps = DbcTable.from_bytes(data, layout.get("Map"))
        self.assertEqual(sorted(maps.ids()), [0, 489, 532, 901])

        # Server side: SQL and the extractor archive.
        sql = os.path.join(self.out, "server", "sql")
        self.assertEqual(sorted(os.listdir(sql)), ["bleakhold_royale.sql", "bleakhold_royale_check.sql",
                                                   "bleakhold_royale_remove.sql"])

        with mpqpack.MpqArchive(os.path.join(self.out, "server", "extract", "patch-5.MPQ")) as archive:
            self.assertIn(MAP, archive.names())
            self.assertIn(f"World\\Maps\\{DIRECTORY}\\{DIRECTORY}.wdt", archive.names())

        with open(os.path.join(self.out, "report.txt"), encoding="utf-8") as f:
            report = f.read()

        self.assertNotIn("[FAIL]", report)
        self.assertIn("patch-enUS-99.MPQ", report)
        self.assertNotIn("patch-enUS-9.MPQ", report)

        # A second run needs --force, and validate passes on the output.
        code, output = self.build()
        self.assertEqual(code, 2)
        self.assertIn("--force", output)
        code, output = run("validate", "--config", self.config, "--out", self.out)
        self.assertEqual(code, 0, output)

    def test_merges_into_the_realm_patches_that_win(self):
        # Patch-Z (every player) holds Map.dbc; Patch-Y (HD pack) and patch-R (every player) hold AreaTable.dbc.
        area_y = DbcTable.from_bytes(self.raw["AreaTable"], layout.get("AreaTable"))
        row = list(area_y.rows[0])
        area_y.set(row, "id", 4800)
        area_y.set_str(row, "areaName[0]", "HD only")
        area_y.rows.append(row)
        area_y_bytes = area_y.to_bytes()
        synth_mpq.write(os.path.join(self.patches, "Patch-Z.MPQ"), {MAP: self.raw["Map"], "Interface\\z.blp": b"z"},
                        compression="bzip2", encrypt=True, fix_key=True)
        synth_mpq.write(os.path.join(self.patches, "Patch-Y.MPQ"), {AREA: area_y_bytes})
        synth_mpq.write(os.path.join(self.patches, "patch-R.MPQ"), {AREA: self.raw["AreaTable"]})

        # The input folder must hold the winning copies with every pack on: Patch-Y's AreaTable.
        with open(os.path.join(self.dbc, "AreaTable.dbc"), "wb") as f:
            f.write(area_y_bytes)

        code, output = self.build()
        self.assertEqual(code, 0, output)
        client = os.path.join(self.out, "client")
        self.assertEqual(sorted(e for e in os.listdir(client) if e.endswith(".MPQ")),
                         ["Patch-Y.MPQ", "Patch-Z.MPQ", "patch-Q.MPQ", "patch-R.MPQ"])

        with mpqpack.MpqArchive(os.path.join(client, "Patch-Z.MPQ")) as archive:
            self.assertEqual(sorted(archive.names()), [MAP, "Interface\\z.blp"])
            self.assertEqual(archive.read("Interface\\z.blp"), b"z")
            self.assertIn(901, DbcTable.from_bytes(archive.read(MAP), layout.get("Map")).ids())

        with mpqpack.MpqArchive(os.path.join(client, "Patch-Y.MPQ")) as archive:
            ids = DbcTable.from_bytes(archive.read(AREA), layout.get("AreaTable")).ids()
            self.assertTrue({4800, 5100} <= ids)

        with mpqpack.MpqArchive(os.path.join(client, "patch-R.MPQ")) as archive:
            ids = DbcTable.from_bytes(archive.read(AREA), layout.get("AreaTable")).ids()
            # Players without the HD pack keep patch-R's copy (no HD-only row), plus our zone.
            self.assertIn(5100, ids)
            self.assertNotIn(4800, ids)

        with mpqpack.MpqArchive(os.path.join(client, "patch-Q.MPQ")) as archive:
            names = archive.names()
            self.assertNotIn(MAP, names)  # Patch-Z carries it
            self.assertNotIn(AREA, names)  # Patch-Y / patch-R carry it
            self.assertIn(layout.archive_name("Light"), names)  # no realm patch holds Light.dbc

    def test_stale_input_is_refused(self):
        synth_mpq.write(os.path.join(self.patches, "Patch-Z.MPQ"), {MAP: self.raw["Map"] + b""})
        maps = DbcTable.from_bytes(self.raw["Map"], layout.get("Map"))
        row = list(maps.rows[0])
        maps.set(row, "id", 740)
        maps.set_str(row, "directory", "EmberwingHollow")
        maps.rows.append(row)
        # The realm's Patch-Z has map 740; the input folder holds an older Map.dbc without it.
        synth_mpq.write(os.path.join(self.patches, "Patch-Z.MPQ"), {MAP: maps.to_bytes()})
        code, output = self.build()
        self.assertEqual(code, 1)
        self.assertIn("differs from the winning copy in Patch-Z.MPQ", output)

    def test_pull_extracts_the_winning_copies(self):
        synth_mpq.write(os.path.join(self.patches, "Patch-Z.MPQ"), {MAP: self.raw["Map"]})
        synth_mpq.write(os.path.join(self.patches, "patch-H.MPQ"), {MAP: b"older", AREA: self.raw["AreaTable"]})
        pulled = os.path.join(self.tmp, "pulled")
        code, output = run("pull", "--patches", self.patches, "--out", pulled, "--config", self.config)
        self.assertEqual(code, 0, output)

        # Patch-Z's Map.dbc wins over patch-H's (which is never read); AreaTable comes from patch-H.
        with open(os.path.join(pulled, "Map.dbc"), "rb") as f:
            self.assertEqual(f.read(), self.raw["Map"])

        with open(os.path.join(pulled, "AreaTable.dbc"), "rb") as f:
            self.assertEqual(f.read(), self.raw["AreaTable"])

        self.assertIn("Map.dbc: from Patch-Z.MPQ", output)
        self.assertIn("Not in any patch", output)

    def test_terrain_area_ids_must_be_ours(self):
        write_terrain(self.terrain, area_ids=(5100, 3277))
        code, output = self.build()
        self.assertEqual(code, 2)
        self.assertIn("MCNK area ids", output)

    def test_path_collision_with_another_patch(self):
        synth_mpq.write(os.path.join(self.patches, "patch-X.MPQ"),
                        {f"World\\Maps\\{DIRECTORY}\\{DIRECTORY}.wdt": b"someone else's"})
        code, output = self.build()
        self.assertEqual(code, 1)
        self.assertIn("is already in patch-X.MPQ", output)

    def test_doctor(self):
        synth_mpq.write(os.path.join(self.patches, "Patch-Z.MPQ"), {MAP: self.raw["Map"]})
        synth_mpq.write(os.path.join(self.patches, "patch-A.MPQ"), {"x.m2": b"x"})
        code, output = run("doctor", "--patches", self.patches, "--config", self.config)
        self.assertEqual(code, 0, output)
        self.assertIn("Data\\patch-A.MPQ [pack hd]", output)
        self.assertIn("DBFilesClient\\Map.dbc: Patch-Z.MPQ", output)
        self.assertIn("DBFilesClient\\AreaTable.dbc: patch-Q.MPQ", output)


def extractor_open(data: bytes, strict: bool) -> tuple[int, int, int]:
    """The header checks of the server extractors' DBCFile::open: map_extractor (strict) wants fieldCount * 4 ==
    recordSize and the whole data present; vmap4_extractor asserts fieldCount * 4 >= recordSize."""
    magic, records, fields, record_size, string_size = struct.unpack_from("<4sIIII", data)
    assert magic == b"WDBC"

    if strict:
        assert fields * 4 == record_size
        assert len(data) - 20 == record_size * records + string_size
    else:
        assert fields * 4 >= record_size

    return records, fields, record_size


class ExtractArchiveTests(unittest.TestCase):
    """server/extract/: the server-only archive for deploy/maps/install-map.sh."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dbc = os.path.join(self.tmp, "dbc")
        self.raw = synth_dbc.write_tables(self.dbc)
        self.terrain = os.path.join(self.tmp, "terrain")
        write_terrain(self.terrain)
        self.config = os.path.join(self.tmp, "map.json")

        with open(self.config, "w", encoding="utf-8") as f:
            json.dump(synth_dbc.default_config(), f)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def build(self, out: str, *extra) -> dict[str, bytes]:
        code, output = run("build", "--config", self.config, "--dbc", self.dbc, "--terrain", self.terrain,
                           "--out", out, *extra)
        self.assertEqual(code, 0, output)
        files = {}

        with mpqpack.MpqArchive(os.path.join(out, "server", "extract", "patch-5.MPQ")) as archive:
            self.assertEqual(archive.verify().problems, [])

            for name in archive.names():
                files[name] = archive.read(name)

        return files

    def test_fast_extract_is_the_default(self):
        out = os.path.join(self.tmp, "out")
        files = self.build(out)
        self.assertEqual(sorted(n for n in files if n.startswith("DBFilesClient\\")),
                         [layout.archive_name("GameObjectDisplayInfo"), MAP])
        # Only the tables the extractors read: no LiquidType (stock) and no AreaTable (neither extractor reads it).
        self.assertNotIn(layout.archive_name("AreaTable"), files)
        self.assertEqual(len([n for n in files if n.endswith(".adt")]), 4)

        # Map.dbc: the client's layout (66 columns, 264-byte rows), one row: this map, with its directory.
        self.assertEqual(extractor_open(files[MAP], strict=True), (1, 66, 264))
        extractor_open(files[MAP], strict=False)
        maps = DbcTable.from_bytes(files[MAP], layout.get("Map"))
        self.assertEqual(sorted(maps.ids()), [901])
        self.assertEqual(maps.get_str(maps.rows[0], "directory"), DIRECTORY)
        self.assertEqual(maps.get(maps.rows[0], "instanceType"), 3)

        # GameObjectDisplayInfo.dbc: the client's layout (19 columns, 76-byte rows), no rows.
        gdi = files[layout.archive_name("GameObjectDisplayInfo")]
        self.assertEqual(extractor_open(gdi, strict=False), (0, 19, 76))
        self.assertEqual(extractor_open(gdi, strict=True), (0, 19, 76))
        self.assertEqual(DbcTable.from_bytes(gdi, layout.get("GameObjectDisplayInfo")).rows, [])

        # The players' archive is untouched: the full Map.dbc, and no GameObjectDisplayInfo.dbc.
        with mpqpack.MpqArchive(os.path.join(out, "client", "patch-Q.MPQ")) as archive:
            self.assertEqual(sorted(DbcTable.from_bytes(archive.read(MAP), layout.get("Map")).ids()),
                             [0, 489, 532, 901])
            self.assertFalse(archive.has_file(layout.archive_name("GameObjectDisplayInfo")))

    def test_full_extract_flag_and_players_archive_unchanged(self):
        fast_out = os.path.join(self.tmp, "fast")
        full_out = os.path.join(self.tmp, "full")
        self.build(fast_out)
        files = self.build(full_out, "--full-extract-dbc")

        with open(os.path.join(full_out, "client", "DBFilesClient", "Map.dbc"), "rb") as f:
            self.assertEqual(files[MAP], f.read())

        self.assertNotIn(layout.archive_name("GameObjectDisplayInfo"), files)

        # The flag changes the server archive only: the players' archive is the same bytes either way.
        for name in ("patch-Q.MPQ",):
            with open(os.path.join(fast_out, "client", name), "rb") as a, \
                    open(os.path.join(full_out, "client", name), "rb") as b:
                self.assertEqual(a.read(), b.read(), name)

    def test_server_map_json(self):
        out = os.path.join(self.tmp, "out")
        self.build(out)
        path = os.path.join(out, "server", "extract", "server-map.json")

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        self.assertEqual(data, {"map_id": 901, "dir": DIRECTORY, "patch": "patch-5.MPQ"})
        # install-map.sh takes a relative patch from the JSON's folder.
        self.assertTrue(os.path.isfile(os.path.join(os.path.dirname(path), data["patch"])))

    def test_no_extract_archive_without_terrain(self):
        data = synth_dbc.default_config()
        data["world_map_area"]["bounds"] = [800.0, -800.0, 533.3, -533.3]  # "auto" needs the terrain's tiles

        with open(self.config, "w", encoding="utf-8") as f:
            json.dump(data, f)

        out = os.path.join(self.tmp, "out")
        code, output = run("build", "--config", self.config, "--dbc", self.dbc, "--out", out)
        self.assertEqual(code, 0, output)
        self.assertFalse(os.path.exists(os.path.join(out, "server", "extract")))


class ConfigFileTests(unittest.TestCase):
    def test_shipped_config_loads(self):
        from dbc import config as configmod

        cfg = configmod.load(os.path.join(TOOL_DIR, "bleakhold_royale.json"))
        self.assertEqual(cfg.map.instance_type, 3)
        self.assertLess(cfg.map.id, 1000)
        self.assertEqual(cfg.archives.map_archive, "patch-Q.MPQ")
        self.assertNotIn("Q", cfg.archives.reserved_letters)
        self.assertTrue(cfg.zone.set_flags & 0x80)
        self.assertEqual(cfg.warnings, [])


if __name__ == "__main__":
    unittest.main()
