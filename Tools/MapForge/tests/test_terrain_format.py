"""Round trip: write a map, parse it back with the independent validator, check the client's layout rules.

Offsets and sizes follow WoW/Source/WorldClient (CMap::LoadWdt, CMapArea::ProcessIffChunks,
CMapChunk::ProcessIffChunks, CMapLowDetail::Load) and AzerothCore's map_extractor (adt.h).
"""

import os
import struct
import unittest

import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_terrain_support import GOLDEN_SPEC, SEAM_SPEC, built, map_folder, validate

from terrain import coords


def chunks(data, start=0, end=None):
    end = len(data) if end is None else end
    out = []
    pos = start
    while pos + 8 <= end:
        magic = data[pos:pos + 4][::-1].decode("ascii")
        size = struct.unpack_from("<I", data, pos + 4)[0]
        out.append((magic, pos, size))
        pos += 8 + size
    return out


class TestRoundTrip(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result, cls.out = built("golden", GOLDEN_SPEC)
        cls.folder = map_folder(cls.out, "GoldenT")
        cls.rep = validate(cls.out)
        with open(os.path.join(cls.folder, "GoldenT_32_32.adt"), "rb") as f:
            cls.adt = f.read()

    def test_validator_clean(self):
        self.assertEqual(self.rep.errors, [])
        self.assertEqual(self.rep.warnings, [])

    def test_output_layout(self):
        names = sorted(os.listdir(self.folder))
        self.assertEqual(names, ["GoldenT.wdl", "GoldenT.wdt", "GoldenT_32_32.adt"])
        self.assertTrue(os.path.isfile(os.path.join(self.out, "pois.json")))
        self.assertTrue(os.path.isfile(os.path.join(self.out, "terrain_manifest.json")))

    def test_wdt_layout(self):
        with open(os.path.join(self.folder, "GoldenT.wdt"), "rb") as f:
            wdt = f.read()
        c = chunks(wdt)
        self.assertEqual([x[0] for x in c], ["MVER", "MPHD", "MAIN", "MWMO"])
        self.assertEqual(c[1][2], 32)
        self.assertEqual(c[2][2], 32768)
        self.assertEqual(c[3][2], 0)
        self.assertEqual(struct.unpack_from("<I", wdt, 20)[0], 0)  # MPHD flags: 4-bit alpha, no MCCV
        main = c[2][1] + 8
        for i in range(4096):
            flags = struct.unpack_from("<I", wdt, main + 8 * i)[0]
            self.assertEqual(flags, 1 if i == 64 * 32 + 32 else 0)
        self.assertEqual(len(wdt), 12 + 40 + 32776 + 8)

    def test_adt_header_offsets(self):
        adt = self.adt
        self.assertEqual(adt[:12], b"REVM\x04\x00\x00\x00\x12\x00\x00\x00")
        self.assertEqual(adt[12:20], b"RDHM\x40\x00\x00\x00")
        vals = struct.unpack_from("<12I", adt, 20)
        self.assertEqual(vals[0], 0)  # no MFBO
        self.assertEqual(vals[1], 64)  # MCIN at file offset 84 (AzerothCore subtracts 84)
        self.assertEqual(adt[84:92], b"NICM\x00\x10\x00\x00")
        expect = ["MCIN", "MTEX", "MMDX", "MMID", "MWMO", "MWID", "MDDF", "MODF", None, "MH2O", "MTXF"]
        for value, magic in zip(vals[1:], expect):
            if magic is None:
                self.assertEqual(value, 0)
                continue
            self.assertNotEqual(value, 0, magic)
            self.assertEqual(adt[20 + value:24 + value][::-1].decode(), magic)
        self.assertEqual(adt[20 + 0x30], 0)  # mamp_value

    def test_top_level_order(self):
        names = [c[0] for c in chunks(self.adt)]
        self.assertEqual(names[:11], ["MVER", "MHDR", "MCIN", "MTEX", "MMDX", "MMID", "MWMO", "MWID", "MDDF",
                                      "MODF", "MH2O"])
        self.assertEqual(names.count("MCNK"), 256)
        self.assertEqual(names[-1], "MTXF")

    def test_mcin_and_mcnk_layout(self):
        adt = self.adt
        for i in range(256):
            ofs, size, flags, async_id = struct.unpack_from("<4I", adt, 92 + 16 * i)
            self.assertEqual(adt[ofs:ofs + 4], b"KNCM")
            self.assertEqual(size, struct.unpack_from("<I", adt, ofs + 4)[0] + 8)
            self.assertEqual((flags, async_id), (0, 0))
            hdr = struct.unpack_from("<15IHH16s6I3f3I", adt, ofs + 8)
            self.assertEqual((hdr[1], hdr[2]), (i % 16, i // 16))
            self.assertEqual(hdr[0] & 0x8000, 0x8000)
            ofs_mcvt, ofs_mcnr, ofs_mcly, ofs_mcrf, ofs_mcal, size_alpha = hdr[5:11]
            self.assertEqual(ofs_mcvt, 136)
            self.assertEqual(adt[ofs + ofs_mcvt:ofs + ofs_mcvt + 8], b"TVCM" + struct.pack("<I", 580))
            self.assertEqual(adt[ofs + ofs_mcnr:ofs + ofs_mcnr + 8], b"RNCM" + struct.pack("<I", 435))
            self.assertEqual(ofs_mcly, ofs_mcnr + 8 + 448)  # 435 + 13 padding bytes
            self.assertEqual(adt[ofs + ofs_mcly:ofs + ofs_mcly + 4], b"YLCM")
            self.assertEqual(adt[ofs + ofs_mcrf:ofs + ofs_mcrf + 4], b"FRCM")
            self.assertEqual(adt[ofs + ofs_mcal:ofs + ofs_mcal + 4], b"LACM")
            mcal_size = struct.unpack_from("<I", adt, ofs + ofs_mcal + 4)[0]
            self.assertEqual(size_alpha, mcal_size + 8)
            self.assertEqual(mcal_size, 2048 * (hdr[3] - 1))
            ofs_mclq, size_liquid = hdr[22], hdr[23]
            self.assertEqual(adt[ofs + ofs_mclq:ofs + ofs_mclq + 8], b"QLCM\x00\x00\x00\x00")
            self.assertEqual(size_liquid, 8)
            px, py = hdr[24], hdr[25]
            top_x, top_y = coords.chunk_top_left(32, 32, i % 16, i // 16)
            self.assertAlmostEqual(px, top_x, places=2)
            self.assertAlmostEqual(py, top_y, places=2)

    def test_heights_round_trip(self):
        grid = self.result.context.grid
        info = self.rep.adts[(32, 32)]
        for (ix, iy), ch in info.chunks.items():
            row0 = (32 * 16 + iy) * 16
            col0 = (32 * 16 + ix) * 16
            k = 0
            for r in range(9):
                for c in range(9):
                    self.assertEqual(ch["heights"][k], struct.unpack("<f", struct.pack("<f", grid.get(
                        row0 + 2 * r, col0 + 2 * c)))[0])
                    k += 1
                if r < 8:
                    for c in range(8):
                        self.assertEqual(ch["heights"][k], struct.unpack("<f", struct.pack("<f", grid.get(
                            row0 + 2 * r + 1, col0 + 2 * c + 1)))[0])
                        k += 1

    def test_area_and_holes(self):
        info = self.rep.adts[(32, 32)]
        self.assertEqual({ch["area"] for ch in info.chunks.values()}, {77})
        holed = [k for k, ch in info.chunks.items() if ch["holes"]]
        self.assertTrue(holed)
        x, y = -470.0, -40.0
        tx, ty = coords.tile_of(x, y)
        u, v = coords.world_to_lattice(x, y)
        self.assertIn((int(v // 16) - tx * 256 // 16, int(u // 16) - ty * 256 // 16), holed)

    def test_water(self):
        info = self.rep.adts[(32, 32)]
        self.assertTrue(info.mh2o)
        for inst in info.mh2o.values():
            self.assertEqual(inst["type"], 1)
            self.assertEqual(inst["format"], 0)
            self.assertEqual(inst["min"], 0.0)
            self.assertLessEqual(inst["x"] + inst["w"], 8)
            self.assertLessEqual(inst["y"] + inst["h"], 8)
            self.assertNotEqual(inst["bits"], 0)
            self.assertTrue(all(h == 0.0 for h in inst["heights"]))

    def test_wdl(self):
        with open(os.path.join(self.folder, "GoldenT.wdl"), "rb") as f:
            wdl = f.read()
        c = chunks(wdl)
        self.assertEqual([x[0] for x in c], ["MVER", "MWMO", "MWID", "MODF", "MAOF", "MARE", "MAHO"])
        self.assertEqual(c[4][2], 16384)
        ofs = struct.unpack_from("<I", wdl, c[4][1] + 8 + 4 * (64 * 32 + 32))[0]
        self.assertEqual(ofs, c[5][1])
        self.assertEqual(c[5][2], 1090)
        self.assertEqual(c[6][2], 32)
        mare = struct.unpack_from("<545h", wdl, c[5][1] + 8)
        corner = self.rep.adts[(32, 32)].chunks[(0, 0)]["heights"][0]
        self.assertLessEqual(abs(mare[0] - corner), 0.5)


class TestSeams(unittest.TestCase):
    """Shared vertices must be identical across chunk and tile edges (no cracks, no lighting seams)."""

    @classmethod
    def setUpClass(cls):
        cls.result, cls.out = built("seam", SEAM_SPEC)
        cls.rep = validate(cls.out)

    def test_validator_clean(self):
        self.assertEqual(self.rep.errors, [])
        self.assertEqual(self.rep.warnings, [])

    def test_chunk_edges(self):
        for info in self.rep.adts.values():
            for (ix, iy), ch in info.chunks.items():
                right = info.chunks.get((ix + 1, iy))
                if right:
                    for r in range(9):
                        self.assertEqual(ch["heights"][r * 17 + 8], right["heights"][r * 17])
                        self.assertEqual(ch["normals"][r * 17 + 8], right["normals"][r * 17])
                below = info.chunks.get((ix, iy + 1))
                if below:
                    for c in range(9):
                        self.assertEqual(ch["heights"][136 + c], below["heights"][c])
                        self.assertEqual(ch["normals"][136 + c], below["normals"][c])

    def test_tile_edges(self):
        adts = self.rep.adts
        for (tx, ty), info in adts.items():
            east = adts.get((tx + 1, ty))
            south = adts.get((tx, ty + 1))
            for i in range(16):
                if east:
                    a = info.chunks[(15, i)]
                    b = east.chunks[(0, i)]
                    for r in range(9):
                        self.assertEqual(a["heights"][r * 17 + 8], b["heights"][r * 17])
                        self.assertEqual(a["normals"][r * 17 + 8], b["normals"][r * 17])
                if south:
                    a = info.chunks[(i, 15)]
                    b = south.chunks[(i, 0)]
                    for c in range(9):
                        self.assertEqual(a["heights"][136 + c], b["heights"][c])
                        self.assertEqual(a["normals"][136 + c], b["normals"][c])

    def test_normals_sane(self):
        worst = 0.0
        for info in self.rep.adts.values():
            for ch in info.chunks.values():
                for n in ch["normals"]:
                    length = (n[0] ** 2 + n[1] ** 2 + n[2] ** 2) ** 0.5
                    self.assertTrue(120.0 <= length <= 134.0, n)
                    self.assertGreater(n[2], 0)
                worst = max(worst, ch["normal_error"])
        # The normals follow the geometry: the angle to each quad's corner plane stays small.
        self.assertLess(worst, 15.0)

    def test_normal_direction_on_a_known_slope(self):
        # Terrain rising toward +X (north) must tilt normals toward -X (normal.x < 0).
        info = self.rep.adts[(32, 32)]
        grid = self.result.context.grid
        for (ix, iy), ch in info.chunks.items():
            row = (32 * 16 + iy) * 16 + 8
            col = (32 * 16 + ix) * 16 + 8
            gx, gy = grid.gradient(row, col)
            n = ch["normals"][4 * 17 + 4]
            if abs(gx) > 0.2:
                self.assertEqual(n[0] < 0, gx > 0)
            if abs(gy) > 0.2:
                self.assertEqual(n[1] < 0, gy > 0)

    def test_alpha_and_layers(self):
        layer_counts = set()
        for info in self.rep.adts.values():
            n_tex = len(info.textures)
            for ch in info.chunks.values():
                layers = ch["layers"]
                layer_counts.add(len(layers))
                self.assertTrue(1 <= len(layers) <= 4)
                self.assertEqual(layers[0]["flags"] & 0x100, 0)
                for k, layer in enumerate(layers):
                    self.assertLess(layer["texture"], n_tex)
                    if k:
                        self.assertEqual(layer["flags"], 0x100)
                        self.assertEqual(layer["ofs"], (k - 1) * 2048)
                self.assertEqual(len(ch["alpha"]), len(layers) - 1)
                for a in ch["alpha"]:
                    self.assertEqual(len(a), 2048)
                self.assertEqual(len({x["texture"] for x in layers}), len(layers))
                for row in range(8):
                    bits = ch["lq"][2 * row] | (ch["lq"][2 * row + 1] << 8)
                    for col in range(8):
                        self.assertLess((bits >> (2 * col)) & 3, len(layers))
        self.assertIn(4, layer_counts)  # the five-texture spec exercises the 4-layer cap

    def test_areas(self):
        areas = {ch["area"] for info in self.rep.adts.values() for ch in info.chunks.values()}
        self.assertEqual(areas, {12, 13})


if __name__ == "__main__":
    unittest.main(verbosity=2)
