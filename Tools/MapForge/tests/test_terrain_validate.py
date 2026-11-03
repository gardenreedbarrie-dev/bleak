"""The validator catches what the client and AzerothCore's tools reject. Each test corrupts a copy of a good map."""

import os
import shutil
import struct
import tempfile
import unittest

import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_terrain_support import GOLDEN_SPEC, SEAM_SPEC, built, copy_output, map_folder, validate


def read(path):
    with open(path, "rb") as f:
        return bytearray(f.read())


def write(path, data):
    with open(path, "wb") as f:
        f.write(bytes(data))


def top_chunk(data, magic):
    pos = 0
    while pos + 8 <= len(data):
        size = struct.unpack_from("<I", data, pos + 4)[0]
        if bytes(data[pos:pos + 4]) == magic[::-1].encode():
            return pos, size
        pos += 8 + size
    raise KeyError(magic)


def mcnk_offset(adt, index):
    return struct.unpack_from("<I", adt, 92 + 16 * index)[0]


def has(rep, text):
    return any(text in e for e in rep.errors)


class Corrupt(unittest.TestCase):
    name = "GoldenT"

    @classmethod
    def setUpClass(cls):
        _, cls.good = built("golden", GOLDEN_SPEC)

    def setUp(self):
        self.out = copy_output(self.good)
        self.folder = map_folder(self.out, self.name)
        self.adt_path = os.path.join(self.folder, f"{self.name}_32_32.adt")
        self.wdt_path = os.path.join(self.folder, f"{self.name}.wdt")

    def tearDown(self):
        shutil.rmtree(self.out, ignore_errors=True)

    def patch_adt(self, fn):
        data = read(self.adt_path)
        fn(data)
        write(self.adt_path, data)
        return validate(self.out)


class TestWdtRules(Corrupt):
    def test_good_map_is_clean(self):
        rep = validate(self.out)
        self.assertEqual(rep.errors, [])

    def test_missing_wdt_is_an_error(self):
        os.remove(self.wdt_path)
        rep = validate(self.out)
        self.assertTrue(has(rep, "SErrDisplayAppFatal"))
        self.assertFalse(rep.ok)

    def test_mphd_must_be_32_bytes(self):
        data = read(self.wdt_path)
        pos, _ = top_chunk(data, "MPHD")
        struct.pack_into("<I", data, pos + 4, 28)
        del data[pos + 8 + 28:pos + 8 + 32]
        write(self.wdt_path, data)
        self.assertTrue(has(validate(self.out), "MPHD size 28"))

    def test_main_must_be_32768_bytes(self):
        data = read(self.wdt_path)
        pos, _ = top_chunk(data, "MAIN")
        struct.pack_into("<I", data, pos + 4, 32760)
        del data[pos + 8 + 32760:pos + 8 + 32768]
        write(self.wdt_path, data)
        self.assertTrue(has(validate(self.out), "MAIN size 32760"))

    def test_mphd_and_main_order(self):
        data = read(self.wdt_path)
        mphd = data[12:12 + 40]
        main_pos, main_size = top_chunk(data, "MAIN")
        main = data[main_pos:main_pos + 8 + main_size]
        write(self.wdt_path, data[:12] + main + mphd + data[main_pos + 8 + main_size:])
        self.assertTrue(has(validate(self.out), "must start MVER, MPHD, MAIN"))

    def test_flagged_tile_without_adt(self):
        data = read(self.wdt_path)
        pos, _ = top_chunk(data, "MAIN")
        struct.pack_into("<I", data, pos + 8 + 8 * (64 * 32 + 33), 1)
        write(self.wdt_path, data)
        self.assertTrue(has(validate(self.out), "ErrorCube"))

    def test_adt_without_main_flag(self):
        shutil.copy(self.adt_path, os.path.join(self.folder, f"{self.name}_33_32.adt"))
        self.assertTrue(has(validate(self.out), "not flagged in MAIN"))

    def test_directory_name_length(self):
        long_name = "L" * 64
        folder = os.path.join(self.out, "World", "Maps", long_name)
        os.makedirs(folder)
        for f in os.listdir(self.folder):
            shutil.copy(os.path.join(self.folder, f), os.path.join(folder, f.replace(self.name, long_name)))
        shutil.rmtree(self.folder)
        self.assertTrue(has(validate(self.out, long_name), "64 or more"))


class TestAdtRules(Corrupt):
    def test_mver_must_be_first(self):
        def fn(d):
            d[0:4] = b"XXXX"
        self.assertTrue(has(self.patch_adt(fn), "must start MVER, MHDR"))

    def test_mhdr_size(self):
        def fn(d):
            struct.pack_into("<I", d, 16, 60)
        rep = self.patch_adt(fn)
        self.assertFalse(rep.ok)

    def test_mhdr_offsets_must_hit_chunks(self):
        for field in range(1, 9):
            def fn(d, field=field):
                v = struct.unpack_from("<I", d, 20 + 4 * field)[0]
                struct.pack_into("<I", d, 20 + 4 * field, v + 4)
            rep = self.patch_adt(fn)
            self.assertFalse(rep.ok, field)
            self.setUp()

    def test_required_offset_zero(self):
        def fn(d):
            struct.pack_into("<I", d, 20 + 4 * 6, 0)  # MHDR.mwid
        self.assertTrue(has(self.patch_adt(fn), "MHDR.mwid is 0"))

    def test_mamp_value(self):
        def fn(d):
            d[20 + 0x30] = 1
        self.assertTrue(has(self.patch_adt(fn), "mamp_value"))

    def test_mcin_flags_must_be_zero(self):
        def fn(d):
            struct.pack_into("<I", d, 92 + 16 * 5 + 8, 1)
        self.assertTrue(has(self.patch_adt(fn), "MCIN flags/asyncId must be 0"))

    def test_mcin_must_start_at_84(self):
        def fn(d):
            struct.pack_into("<I", d, 24, 60)
        self.assertTrue(has(self.patch_adt(fn), "file offset 84"))

    def test_size_alpha(self):
        def fn(d):
            ofs = mcnk_offset(d, 40)
            v = struct.unpack_from("<I", d, ofs + 8 + 0x28)[0]
            struct.pack_into("<I", d, ofs + 8 + 0x28, v + 16)
        self.assertTrue(has(self.patch_adt(fn), "sizeAlpha"))

    def test_big_alpha_needs_flag_8000(self):
        data = read(self.wdt_path)
        struct.pack_into("<I", data, 20, 0x4)
        write(self.wdt_path, data)

        def fn(d):
            ofs = mcnk_offset(d, 0)
            flags = struct.unpack_from("<I", d, ofs + 8)[0]
            struct.pack_into("<I", d, ofs + 8, flags & ~0x8000)
        self.assertTrue(has(self.patch_adt(fn), "Bad genformat"))

    def test_rle_alpha_in_4bit_map(self):
        def fn(d):
            for i in range(256):
                ofs = mcnk_offset(d, i)
                n_layers = struct.unpack_from("<I", d, ofs + 8 + 0x0C)[0]
                if n_layers > 1:
                    mcly = ofs + struct.unpack_from("<I", d, ofs + 8 + 0x1C)[0] + 8
                    struct.pack_into("<I", d, mcly + 16 + 4, 0x300)
                    return
        self.assertTrue(has(self.patch_adt(fn), "RLE-compressed"))

    def test_mcvt_size(self):
        def fn(d):
            ofs = mcnk_offset(d, 7)
            mcvt = ofs + struct.unpack_from("<I", d, ofs + 8 + 0x14)[0]
            struct.pack_into("<I", d, mcvt + 4, 576)
        self.assertFalse(self.patch_adt(fn).ok)

    def test_mcnr_size(self):
        def fn(d):
            ofs = mcnk_offset(d, 9)
            mcnr = ofs + struct.unpack_from("<I", d, ofs + 8 + 0x18)[0]
            struct.pack_into("<I", d, mcnr + 4, 440)
        self.assertTrue(has(self.patch_adt(fn), "MCNR size 440"))

    def test_too_many_layers(self):
        def fn(d):
            ofs = mcnk_offset(d, 3)
            struct.pack_into("<I", d, ofs + 8 + 0x0C, 5)
        self.assertTrue(has(self.patch_adt(fn), "5 layers"))

    def test_texture_id_range(self):
        def fn(d):
            ofs = mcnk_offset(d, 3)
            mcly = ofs + struct.unpack_from("<I", d, ofs + 8 + 0x1C)[0] + 8
            struct.pack_into("<I", d, mcly, 9)
        self.assertTrue(has(self.patch_adt(fn), "texture 9"))

    def test_low_quality_map_layer_range(self):
        def fn(d):
            for i in range(256):
                ofs = mcnk_offset(d, i)
                if struct.unpack_from("<I", d, ofs + 8 + 0x0C)[0] == 1:
                    d[ofs + 8 + 0x40] = 0x03
                    return
        self.assertTrue(has(self.patch_adt(fn), "low-quality texture map"))

    def test_seam_mismatch(self):
        def fn(d):
            ofs = mcnk_offset(d, 0)
            mcvt = ofs + struct.unpack_from("<I", d, ofs + 8 + 0x14)[0] + 8
            v = struct.unpack_from("<f", d, mcvt + 8 * 4)[0]
            struct.pack_into("<f", d, mcvt + 8 * 4, v + 2.0)
        self.assertTrue(has(self.patch_adt(fn), "chunk edges do not match"))

    def test_mddf_name_id_range(self):
        def fn(d):
            pos, _ = top_chunk(d, "MDDF")
            struct.pack_into("<I", d, pos + 8, 7)
        self.assertTrue(has(self.patch_adt(fn), "name id 7"))

    def test_mcrf_reference_range(self):
        def fn(d):
            for i in range(256):
                ofs = mcnk_offset(d, i)
                if struct.unpack_from("<I", d, ofs + 8 + 0x10)[0]:
                    mcrf = ofs + struct.unpack_from("<I", d, ofs + 8 + 0x20)[0] + 8
                    struct.pack_into("<I", d, mcrf, 50)
                    return
        self.assertTrue(has(self.patch_adt(fn), "doodad reference 50"))

    def test_mmid_order(self):
        def fn(d):
            pos, size = top_chunk(d, "MMID")
            a, b = struct.unpack_from("<2I", d, pos + 8)
            struct.pack_into("<2I", d, pos + 8, b, a)
        self.assertTrue(has(self.patch_adt(fn), "in order"))

    def test_destructible_wmo_flag(self):
        def fn(d):
            pos, _ = top_chunk(d, "MODF")
            struct.pack_into("<H", d, pos + 8 + 0x38, 1)
        self.assertTrue(has(self.patch_adt(fn), "destructible"))

    def test_uid_covering_two_objects(self):
        def fn(d):
            pos, _ = top_chunk(d, "MDDF")
            wpos, _ = top_chunk(d, "MODF")
            wmo_uid = struct.unpack_from("<I", d, wpos + 12)[0]
            struct.pack_into("<I", d, pos + 12, wmo_uid)
        self.assertTrue(has(self.patch_adt(fn), "repeats within this tile"))

    def test_liquid_type_must_be_stock(self):
        def fn(d):
            pos, _ = top_chunk(d, "MH2O")
            for i in range(256):
                inst, layers, _ = struct.unpack_from("<3I", d, pos + 8 + 12 * i)
                if layers:
                    struct.pack_into("<H", d, pos + 8 + inst, 99)
                    return
        self.assertTrue(has(self.patch_adt(fn), "liquid type 99"))


class TestDataChecks(Corrupt):
    """--dbc and --assets: data-free tools that use real client data when it is there (the VPS)."""

    @staticmethod
    def dbc(path, ids):
        body = b"".join(struct.pack("<4I", i, 0, 0, 0) for i in ids)
        write(path, b"WDBC" + struct.pack("<4I", len(ids), 4, 16, 1) + body + b"\0")

    def test_liquid_type_row_missing(self):
        d = tempfile.mkdtemp()
        self.dbc(os.path.join(d, "LiquidType.dbc"), [2, 3, 4])
        self.dbc(os.path.join(d, "AreaTable.dbc"), [77])
        rep = validate(self.out, dbc=d)
        self.assertTrue(has(rep, "has no LiquidType row"))
        self.assertFalse(has(rep, "AreaTable"))
        shutil.rmtree(d)

    def test_area_row_missing(self):
        d = tempfile.mkdtemp()
        self.dbc(os.path.join(d, "LiquidType.dbc"), [1, 2, 3, 4])
        self.dbc(os.path.join(d, "AreaTable.dbc"), [1, 2])
        rep = validate(self.out, dbc=d)
        self.assertTrue(has(rep, "area id 77 has no AreaTable row"))
        shutil.rmtree(d)

    def make_assets(self, wmo_box, with_specular=True, skip=()):
        root = tempfile.mkdtemp()

        def put(path, data=b"x"):
            if path in skip:
                return
            full = os.path.join(root, *path.split("\\"))
            os.makedirs(os.path.dirname(full), exist_ok=True)
            write(full, data)
        for t in ("GrassA", "RockA", "SandA"):
            put(f"Tileset\\Made\\Up\\{t}.blp")
            if with_specular and t != "SandA":
                put(f"Tileset\\Made\\Up\\{t}_s.blp")
        put("World\\Made\\Up\\Tree.m2")
        put("World\\Made\\Up\\Rock.m2")
        mohd = struct.pack("<9I6f2H", 0, 1, 0, 0, 0, 0, 1, 0, 0, *wmo_box[0], *wmo_box[1], 0, 0)
        put("World\\wmo\\Made\\Up\\Hut.wmo", b"REVM" + struct.pack("<II", 4, 17) + b"DHOM" +
            struct.pack("<I", len(mohd)) + mohd)
        return root

    def test_real_extents_match(self):
        root = self.make_assets(((-6, -5, -1), (7, 5, 9)))
        rep = validate(self.out, assets=root)
        self.assertEqual(rep.errors, [])
        shutil.rmtree(root)

    def test_wrong_extents(self):
        root = self.make_assets(((-12, -5, -1), (7, 5, 30)))
        self.assertTrue(has(validate(self.out, assets=root), "extents are off"))
        shutil.rmtree(root)

    def test_missing_specular_companion(self):
        root = self.make_assets(((-6, -5, -1), (7, 5, 9)), with_specular=False)
        rep = validate(self.out, assets=root)
        self.assertTrue(has(rep, "GrassA_s.blp"))
        self.assertFalse(has(rep, "SandA_s.blp"))  # MTXF flag 1: the client loads the plain name
        shutil.rmtree(root)

    def test_missing_model(self):
        root = self.make_assets(((-6, -5, -1), (7, 5, 9)), skip=("World\\Made\\Up\\Rock.m2",))
        self.assertTrue(has(validate(self.out, assets=root), "Rock.m2' is not in the client files"))
        shutil.rmtree(root)

    def test_trs_rules(self):
        trs_dir = os.path.join(self.out, "Textures", "Minimap")
        os.makedirs(trs_dir)
        write(os.path.join(trs_dir, "md5translate.trs"), b"GoldenT\\map32_32.blp\tabc.blp\n")
        rep = validate(self.out)
        self.assertTrue(has(rep, "CR LF"))
        self.assertTrue(has(rep, "global"))
        write(os.path.join(trs_dir, "md5translate.trs"),
              b"dir: Azeroth\r\nAzeroth\\map32_48.blp\tx.blp\r\nGoldenT\\map32_32.blp\tabc.blp\r\n")
        rep = validate(self.out)
        self.assertFalse(has(rep, "CR LF"))
        self.assertFalse(has(rep, "global"))


class TestSpanningRule(unittest.TestCase):
    def test_spanning_wmo_missing_from_a_tile(self):
        _, good = built("seam", SEAM_SPEC)
        out = copy_output(good)
        path = os.path.join(map_folder(out, "SeamT"), "SeamT_32_32.adt")
        data = read(path)
        pos, _ = top_chunk(data, "MODF")
        struct.pack_into("<I", data, pos + 12, 777777)  # this tile now lists a different object
        write(path, data)
        rep = validate(out)
        self.assertTrue(has(rep, "is not listed there"))
        self.assertTrue(has(rep, "names different placements") or has(rep, "is not listed there"))
        shutil.rmtree(out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
