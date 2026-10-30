"""package.py build: the map art of the client patch (spec ROYALE-UX 2.13). The world map tiles (--worldmap), the
minimap tiles with the merged md5translate.trs (--minimap, --trs), the art a rebuild keeps from the realm's current
patch-Q, and what validate and doctor say about it. Made-up tiles and archives only."""

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
from dbc import minimap  # noqa: E402
from tests import synth_dbc, synth_mpq  # noqa: E402
from tests.test_package import run, write_terrain  # noqa: E402

import blpconvert  # noqa: E402
import mpqpack  # noqa: E402

AREA = "BleakholdRoyale"
TRS = "Textures\\Minimap\\md5translate.trs"
STOCK_TRS = b"dir: Azeroth\r\nAzeroth\\map30_30.blp\t0a1b2c3d.blp\r\nAzeroth\\map30_31.blp\t4e5f6a7b.blp\r\n"


def world_name(n: int) -> str:
    return f"Interface\\WorldMap\\{AREA}\\{AREA}{n}.blp"


def mini_name(tile) -> str:
    return f"Textures\\Minimap\\{AREA}\\map{tile[0]}_{tile[1]:02d}.blp"


def colour(n: int) -> tuple[int, int, int]:
    """A colour per tile that survives DXT1 (5-6-5 levels) well enough to tell the tiles apart."""
    return ((n * 40) % 256, (255 - n * 20) % 256, (n * 72 + 30) % 256)


def write_png(path: str, rgb, size=(256, 256)):
    img = blpconvert.Image(size[0], size[1], bytearray(bytes(rgb + (255,)) * (size[0] * size[1])))
    blpconvert.write_png(path, img)


def write_blp(path: str, rgb, fmt="dxt1", size=256, mips=False):
    img = blpconvert.Image(size, size, bytearray(bytes(rgb + (255,)) * (size * size)))
    blpconvert.convert(img, path, fmt=fmt, mips=mips, jobs=1)


def write_world_tiles(folder: str, skip=(), extra=(), shift=0):
    os.makedirs(folder, exist_ok=True)

    for n in range(1, 13):
        if n not in skip:
            write_png(os.path.join(folder, f"{AREA}{n}.png"), colour(n + shift))

    for name in extra:
        write_png(os.path.join(folder, name), (1, 2, 3))


def write_minimap_tiles(folder: str, tiles=synth_dbc.TILES):
    os.makedirs(folder, exist_ok=True)

    for tx, ty in tiles:
        write_png(os.path.join(folder, f"map{tx}_{ty:02d}.png"), (tx * 4, ty * 4, 90))


def mean_colour(blob: bytes, tmp: str) -> tuple[int, int, int]:
    path = os.path.join(tmp, "decode.blp")

    with open(path, "wb") as f:
        f.write(blob)

    img = blpconvert.decode_blp(path)
    pixels = img.width * img.height
    return tuple(sum(img.data[c::4]) // pixels for c in range(3))


def archive_files(path: str) -> dict[str, bytes]:
    with mpqpack.MpqArchive(path) as archive:
        return {name: archive.read(name) for name in archive.names()}


class MapArtCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dbc = os.path.join(self.tmp, "dbc")
        synth_dbc.write_tables(self.dbc)
        self.terrain = os.path.join(self.tmp, "terrain")
        write_terrain(self.terrain)
        self.config = os.path.join(self.tmp, "map.json")
        self.write_config(synth_dbc.default_config())
        self.patches = os.path.join(self.tmp, "patches")
        os.makedirs(self.patches)
        self.out = os.path.join(self.tmp, "out")
        self.world = os.path.join(self.tmp, "tiles", "worldmap")
        self.mini = os.path.join(self.tmp, "tiles", "minimap")
        self.trs = os.path.join(self.tmp, "md5translate.trs")

        with open(self.trs, "wb") as f:
            f.write(STOCK_TRS)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def write_config(self, data):
        with open(self.config, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def build(self, *extra, out=None) -> tuple[int, str]:
        return run("build", "--config", self.config, "--dbc", self.dbc, "--terrain", self.terrain,
                   "--patches", self.patches, "--out", out or self.out, "--force", *extra)

    def patch_q(self, out=None) -> dict[str, bytes]:
        return archive_files(os.path.join(out or self.out, "client", "patch-Q.MPQ"))

    def report(self, out=None) -> str:
        with open(os.path.join(out or self.out, "report.txt"), encoding="utf-8") as f:
            return f.read()

    def install(self, out=None):
        """The build's patch-Q goes into the realm's patches, as build-royale.sh (or the owner) does."""
        shutil.copyfile(os.path.join(out or self.out, "client", "patch-Q.MPQ"),
                        os.path.join(self.patches, "patch-Q.MPQ"))


class WorldMapTests(MapArtCase):
    def test_world_map_tiles_go_into_patch_q(self):
        write_world_tiles(self.world)
        code, output = self.build("--worldmap", self.world)
        self.assertEqual(code, 0, output)
        files = self.patch_q()

        for n in range(1, 13):
            blob = files[world_name(n)]
            self.assertEqual(package.tile_blp_problems(blob), [], n)
            header = blpconvert.read_blp_header(blob)
            # DXT1, one level: interface textures are drawn without mips
            self.assertEqual((header["encoding"], header["preferredFormat"], header["hasMips"]), (2, 0, 0))
            got = mean_colour(blob, self.tmp)

            for a, b in zip(got, colour(n)):
                self.assertLessEqual(abs(a - b), 8, (n, got, colour(n)))

        self.assertEqual(len([n for n in files if n.startswith("Interface\\WorldMap\\")]), 12)
        self.assertIn(f"Interface\\WorldMap\\{AREA}\\: {AREA}1-12 (DXT1 256 x 256", output)
        record = package.read_art_record(files[package.MAP_ART_FILE].decode())
        self.assertEqual(record["worldmap"][0], 12)
        self.assertNotIn("minimap", record)
        self.assertNotIn(TRS, files)  # no minimap art given: the global trs is not shipped

        code, output = run("validate", "--config", self.config, "--out", self.out)
        self.assertEqual(code, 0, output)
        self.assertIn(f"[PASS] patch-Q.MPQ holds the world map tiles ({AREA}1-12, DXT1 256 x 256)", output)
        self.assertIn("[NOTE] patch-Q.MPQ has no minimap tiles", output)

    def test_names_are_the_world_map_area_s_and_complete(self):
        cases = [
            ({"skip": (7,)}, f"lacks {AREA}7"),
            ({"extra": (f"{AREA}13.png",)}, f"{AREA}1 to {AREA}12"),
            ({"extra": (f"{AREA}0.png",)}, f"{AREA}1 to {AREA}12"),
            ({"skip": (5,), "extra": (f"{AREA}05.png",)}, f"{AREA}1 to {AREA}12"),
            ({"extra": ("Azeroth1.png",)}, "named after the config's world_map_area"),
        ]

        for kwargs, message in cases:
            shutil.rmtree(self.world, ignore_errors=True)
            write_world_tiles(self.world, **kwargs)
            code, output = self.build("--worldmap", self.world)
            self.assertEqual(code, 2, (kwargs, output))
            self.assertIn(message, output, kwargs)

        # .png and .blp of the same tile
        shutil.rmtree(self.world)
        write_world_tiles(self.world)
        write_blp(os.path.join(self.world, f"{AREA}4.blp"), colour(4))
        code, output = self.build("--worldmap", self.world)
        self.assertEqual(code, 2, output)
        self.assertIn("tile 4 is there twice", output)

        # a bad folder stops the build before the output folder is touched
        os.makedirs(self.out, exist_ok=True)

        with open(os.path.join(self.out, "report.txt"), "w", encoding="utf-8") as f:
            f.write("an earlier build\n")

        os.remove(os.path.join(self.world, f"{AREA}4.blp"))
        os.remove(os.path.join(self.world, f"{AREA}9.png"))
        code, output = self.build("--worldmap", self.world)
        self.assertEqual(code, 2, output)
        self.assertEqual(self.report(), "an earlier build\n")

        # the file names' case does not matter; the archive spells them like the config
        os.rename(os.path.join(self.world, f"{AREA}3.png"), os.path.join(self.world, f"{AREA.lower()}3.png"))
        write_png(os.path.join(self.world, f"{AREA}9.png"), colour(9))
        code, output = self.build("--worldmap", self.world)
        self.assertEqual(code, 0, output)

        with mpqpack.MpqArchive(os.path.join(self.out, "client", "patch-Q.MPQ")) as archive:
            self.assertIn(world_name(3), archive.names())

    def test_tiles_are_256_dxt1(self):
        write_world_tiles(self.world, skip=(2, 6, 8))
        write_png(os.path.join(self.world, f"{AREA}2.png"), colour(2), size=(512, 512))
        write_blp(os.path.join(self.world, f"{AREA}6.blp"), colour(6))
        write_blp(os.path.join(self.world, f"{AREA}8.blp"), colour(8), mips=True)
        code, output = self.build("--worldmap", self.world)
        self.assertEqual(code, 2, output)
        self.assertIn(f"{AREA}2.png is 512 x 512", output)  # never resampled: it is a piece of one picture

        write_png(os.path.join(self.world, f"{AREA}2.png"), colour(2))
        write_blp(os.path.join(self.world, f"{AREA}6.blp"), colour(6), fmt="dxt5")
        code, output = self.build("--worldmap", self.world)
        self.assertEqual(code, 2, output)
        self.assertIn("not DXT1", output)

        write_blp(os.path.join(self.world, f"{AREA}6.blp"), colour(6), size=128)
        code, output = self.build("--worldmap", self.world)
        self.assertEqual(code, 2, output)
        self.assertIn("128 x 128, not 256 x 256", output)

        path = os.path.join(self.world, f"{AREA}6.blp")
        write_blp(path, colour(6))

        with open(path, "rb") as f:
            blob = f.read()

        with open(path, "wb") as f:
            f.write(blob[:-100])

        code, output = self.build("--worldmap", self.world)
        self.assertEqual(code, 2, output)
        self.assertIn("level 0 is missing or cut off", output)

        # a good BLP goes in as it is (with or without mips)
        with open(path, "wb") as f:
            f.write(blob)

        code, output = self.build("--worldmap", self.world)
        self.assertEqual(code, 0, output)
        files = self.patch_q()
        self.assertEqual(files[world_name(6)], blob)

        with open(os.path.join(self.world, f"{AREA}8.blp"), "rb") as f:
            self.assertEqual(files[world_name(8)], f.read())

    def test_collisions_with_realm_archives(self):
        write_world_tiles(self.world)

        for spelling in (world_name(3), world_name(3).lower()):
            synth_mpq.write(os.path.join(self.patches, "patch-X.MPQ"), {spelling: b"someone else's"})
            code, output = self.build("--worldmap", self.world)
            self.assertEqual(code, 1, output)
            self.assertIn(f"[FAIL] map archive paths: {world_name(3)} is already in patch-X.MPQ", output)

    def test_needs_a_world_map_area(self):
        data = synth_dbc.default_config()
        data["world_map_area"] = None
        self.write_config(data)
        write_world_tiles(self.world)
        code, output = self.build("--worldmap", self.world)
        self.assertEqual(code, 2, output)
        self.assertIn("the config has no world_map_area", output)


class MinimapTrsTests(MapArtCase):
    def merged_lines(self) -> list[tuple[str, str]]:
        return minimap.parse(self.patch_q()[TRS])

    def test_tiles_and_the_trs_merged_from_a_realm_patch(self):
        write_minimap_tiles(self.mini)
        realm = STOCK_TRS + b"Kalimdor\\map20_20.blp\tfeedface.blp\r\n"
        synth_mpq.write(os.path.join(self.patches, "patch-H.MPQ"), {TRS: realm})  # (under patch-Q)
        code, output = self.build("--minimap", self.mini)
        self.assertEqual(code, 0, output)
        files = self.patch_q()
        lines = minimap.parse(files[TRS])
        self.assertEqual(lines[:3], minimap.parse(realm))
        self.assertEqual(sorted(k for k, _ in lines[3:]),
                         sorted(f"{AREA}\\map{tx}_{ty:02d}.blp" for tx, ty in synth_dbc.TILES))
        self.assertTrue(files[TRS].endswith(b"\r\n"))
        self.assertIn("md5translate.trs: merged from patch-H.MPQ plus 4 tile lines", output)

        for tile in synth_dbc.TILES:
            self.assertEqual(package.tile_blp_problems(files[mini_name(tile)]), [], tile)

        record = package.read_art_record(files[package.MAP_ART_FILE].decode())
        self.assertEqual(record["minimap"][0], 4)
        code, output = run("validate", "--config", self.config, "--out", self.out)
        self.assertEqual(code, 0, output)
        self.assertIn("[PASS] patch-Q.MPQ holds the minimap tiles its md5translate.trs lists (4)", output)
        self.assertIn("[NOTE] patch-Q.MPQ has no world map tiles", output)

        # the tiles must be the WDT's, checked before the output folder is touched
        os.remove(os.path.join(self.mini, "map32_32.png"))
        code, output = self.build("--minimap", self.mini)
        self.assertEqual(code, 2, output)
        self.assertIn("do not match the WDT", output)

    def test_the_realm_s_trs_wins_over_our_earlier_merge(self):
        write_minimap_tiles(self.mini)
        code, output = self.build("--minimap", self.mini, "--trs", self.trs)
        self.assertEqual(code, 0, output)
        self.install()

        # only our earlier merge holds one: it is the base (its own lines are replaced)
        code, output = self.build("--minimap", self.mini)
        self.assertEqual(code, 0, output)
        self.assertIn("merged from patch-Q.MPQ (its earlier merge)", output)
        self.assertEqual(self.merged_lines()[:2], minimap.parse(STOCK_TRS))
        self.assertEqual(len(self.merged_lines()), 6)

        # a realm patch with a trs of its own (under patch-Q) is the base from then on
        newer = STOCK_TRS + b"Northrend\\map10_10.blp\tbeef.blp\r\n"
        synth_mpq.write(os.path.join(self.patches, "patch-L.MPQ"), {TRS: newer})
        code, output = self.build("--minimap", self.mini)
        self.assertEqual(code, 0, output)
        self.assertIn("merged from patch-L.MPQ plus 4 tile lines", output)
        self.assertEqual(self.merged_lines()[:3], minimap.parse(newer))

        # one that loads over patch-Q would hide the merged trs
        synth_mpq.write(os.path.join(self.patches, "Patch-Z.MPQ"), {TRS: newer})
        code, output = self.build("--minimap", self.mini)
        self.assertEqual(code, 1, output)
        self.assertIn("Patch-Z.MPQ loads over patch-Q.MPQ; the merged trs would lose", output)

    def test_trs_from_a_client_data_folder(self):
        write_minimap_tiles(self.mini)
        game = os.path.join(self.tmp, "game")
        data = os.path.join(game, "Data")
        lichking = STOCK_TRS + b"Northrend\\map1_1.blp\tlk.blp\r\n"
        synth_mpq.write(os.path.join(data, "common.MPQ"), {TRS: b"dir: Azeroth\r\nold\tcommon.blp\r\n"})
        synth_mpq.write(os.path.join(data, "lichking.MPQ"), {TRS: lichking})
        synth_mpq.write(os.path.join(data, "enUS", "locale-enUS.MPQ"), {"x.txt": b"x"})
        synth_mpq.write(os.path.join(data, "patch-R.MPQ"), {"y.txt": b"y"})

        # no patch holds it: the base archives in the client's order (lichking over common)
        code, output = self.build("--minimap", self.mini, "--trs", game)
        self.assertEqual(code, 0, output)
        self.assertIn("merged from Data\\lichking.MPQ", output)
        self.assertEqual(self.merged_lines()[:3], minimap.parse(lichking))

        # a patch holds it: the top patch wins, and the map archive's own copy is left out
        patch3 = STOCK_TRS + b"Northrend\\map1_1.blp\tp3.blp\r\n"
        synth_mpq.write(os.path.join(data, "patch-3.MPQ"), {TRS: patch3})
        synth_mpq.write(os.path.join(data, "patch-Q.MPQ"), {TRS: b"dir: x\r\nours\told.blp\r\n",
                                                            package.MARKER_FILE: b"MapForge"})
        code, output = self.build("--minimap", self.mini, "--trs", data)
        self.assertEqual(code, 0, output)
        self.assertIn("merged from Data\\patch-3.MPQ", output)
        self.assertEqual(self.merged_lines()[:3], minimap.parse(patch3))

        # an archive that cannot be read could hold a newer one
        with open(os.path.join(data, "patch-T.MPQ"), "wb") as f:
            f.write(b"not an archive")

        code, output = self.build("--minimap", self.mini, "--trs", data)
        self.assertEqual(code, 2, output)
        self.assertIn("patch-T.MPQ cannot be read", output)

        # none at all
        empty = os.path.join(self.tmp, "empty", "Data")
        synth_mpq.write(os.path.join(empty, "common.MPQ"), {"z.txt": b"z"})
        code, output = self.build("--minimap", self.mini, "--trs", empty)
        self.assertEqual(code, 2, output)
        self.assertIn("no archive there holds Textures\\Minimap\\md5translate.trs", output)

    def test_no_trs_anywhere(self):
        write_minimap_tiles(self.mini)
        code, output = self.build("--minimap", self.mini)
        self.assertEqual(code, 2, output)
        self.assertIn("give --trs", output)


class KeptArtTests(MapArtCase):
    """A rebuild (a new MapForge, a changed realm patch: build-royale.sh does them by itself) keeps the map art of
    the patch-Q in the realm's patches, so the island stays on the players' minimap and world map."""

    def build_and_install(self):
        write_world_tiles(self.world)
        write_minimap_tiles(self.mini)
        code, output = self.build("--worldmap", self.world, "--minimap", self.mini, "--trs", self.trs)
        self.assertEqual(code, 0, output)
        self.install()
        return self.patch_q()

    def test_a_rebuild_keeps_the_art(self):
        first = self.build_and_install()
        again = os.path.join(self.tmp, "again")
        code, output = self.build(out=again)
        self.assertEqual(code, 0, output)
        self.assertIn("[NOTE] kept the 4 minimap tiles of the realm's patch-Q.MPQ", output)
        self.assertIn("[NOTE] kept the 12 world map tiles of the realm's patch-Q.MPQ", output)
        self.assertNotIn("made for other terrain", self.report(again))
        # the same archive, byte for byte: build-royale.sh then finds nothing to replace
        with open(os.path.join(self.out, "client", "patch-Q.MPQ"), "rb") as a, \
                open(os.path.join(again, "client", "patch-Q.MPQ"), "rb") as b:
            self.assertEqual(a.read(), b.read())

        self.assertEqual(self.patch_q(again), first)
        code, output = run("doctor", "--patches", self.patches, "--config", self.config)
        self.assertEqual(code, 0, output)
        self.assertIn("Map art in patch-Q.MPQ: 4 minimap tiles, 12 of 12 world map tiles", output)

    def test_new_tiles_replace_the_kept_ones(self):
        first = self.build_and_install()
        shutil.rmtree(self.world)
        write_world_tiles(self.world, shift=3)
        code, output = self.build("--worldmap", self.world)
        self.assertEqual(code, 0, output)
        self.assertIn("kept the 4 minimap tiles", output)
        self.assertNotIn("kept the 12 world map tiles", output)
        files = self.patch_q()
        self.assertNotEqual(files[world_name(1)], first[world_name(1)])
        self.assertEqual(files[mini_name((31, 31))], first[mini_name((31, 31))])
        self.assertEqual(files[TRS], first[TRS])

    def test_drop_map_art(self):
        self.build_and_install()
        code, output = self.build("--drop-map-art")
        self.assertEqual(code, 0, output)
        files = self.patch_q()
        self.assertFalse([n for n in files if n.startswith(("Interface\\WorldMap\\", "Textures\\Minimap\\"))])
        self.assertNotIn(package.MAP_ART_FILE, files)
        self.assertIn("[NOTE] no minimap or world map tiles", output)

    def test_art_made_for_other_terrain_warns(self):
        self.build_and_install()
        maps = os.path.join(self.terrain, "World", "Maps", AREA)

        with open(os.path.join(maps, f"{AREA}_31_31.adt"), "ab") as f:
            f.write(b"changed")

        code, output = self.build()
        self.assertEqual(code, 0, output)
        self.assertIn("[WARN] the minimap tiles kept from patch-Q.MPQ were made for other terrain", output)
        self.assertIn("[WARN] the world map tiles kept from patch-Q.MPQ were made for other terrain", output)
        # the record keeps the terrain they were made for, so every later rebuild warns until they are made again
        record = package.read_art_record(self.patch_q()[package.MAP_ART_FILE].decode())
        self.assertNotEqual(record["worldmap"][1], package.terrain_digest(
            [(f"World\\Maps\\{AREA}\\{e}", os.path.join(maps, e)) for e in os.listdir(maps)]))

    def test_partial_art_is_not_kept(self):
        files = {package.MARKER_FILE: b"MapForge", f"World\\Maps\\{AREA}\\{AREA}.wdt": b"x"}
        files.update({world_name(n): b"tile" for n in range(1, 6)})
        files.update({mini_name(t): b"tile" for t in [(31, 31), (31, 32)]})
        files[TRS] = minimap.build([], AREA, [(31, 31), (31, 32)])
        synth_mpq.write(os.path.join(self.patches, "patch-Q.MPQ"), files)
        code, output = self.build()
        self.assertEqual(code, 0, output)
        self.assertIn("[WARN] patch-Q.MPQ holds only 5 of the 12 world map tiles: they are not kept", output)
        self.assertIn("[WARN] patch-Q.MPQ holds only 2 of the 4 minimap tiles: they are not kept", output)
        self.assertFalse([n for n in self.patch_q() if n.startswith(("Interface\\WorldMap\\", "Textures\\"))])

    def test_an_archive_not_written_by_mapforge_gives_nothing(self):
        synth_mpq.write(os.path.join(self.patches, "patch-Q.MPQ"), {world_name(n): b"t" for n in range(1, 13)})
        code, output = self.build()
        self.assertEqual(code, 1, output)  # check_map_archive_name refuses it anyway
        self.assertNotIn("kept the", output)


class ValidateTests(MapArtCase):
    def test_partial_art_fails_validate(self):
        write_world_tiles(self.world)
        code, output = self.build("--worldmap", self.world)
        self.assertEqual(code, 0, output)
        path = os.path.join(self.out, "client", "patch-Q.MPQ")
        files = archive_files(path)
        del files[world_name(11)]
        files[world_name(4)] = b"BLP2" + bytes(8)
        files[TRS] = STOCK_TRS + f"{AREA}\\map31_31.blp\t{AREA}\\map31_31.blp\r\n".encode()
        os.remove(path)
        package.pack(self.staged(files), path)
        code, output = run("validate", "--config", self.config, "--out", self.out)
        self.assertEqual(code, 1, output)
        self.assertIn(f"{world_name(11)} is missing", output)
        self.assertIn(f"{world_name(4)}: ", output)
        self.assertIn(f"[FAIL] patch-Q.MPQ holds the minimap tiles its md5translate.trs lists (1): "
                      f"{mini_name((31, 31))} is missing", output)

    def staged(self, files: dict[str, bytes]) -> dict[str, str]:
        out = {}

        for i, (name, blob) in enumerate(sorted(files.items())):
            path = os.path.join(self.tmp, f"staged{i}")

            with open(path, "wb") as f:
                f.write(blob)

            out[name] = path

        return out


class TileBlpTests(unittest.TestCase):
    def test_tile_blp_problems(self):
        self.assertEqual(package.tile_blp_problems(b"short"), ["file is shorter than the 0x494-byte BLP2 header"])
        header = bytearray(struct.pack("<4sIBBBBII16I16I", b"BLP1", 1, 2, 0, 0, 0, 256, 256, *([0] * 32)))
        header += bytes(1024)
        self.assertIn("not a BLP2 file", package.tile_blp_problems(bytes(header))[0])


if __name__ == "__main__":
    unittest.main()
