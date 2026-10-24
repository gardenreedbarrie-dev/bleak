"""Placements: name tables, MDDF/MODF records, MCRF ranges, unique ids, coordinates, tile spanning, POIs."""

import json
import os
import unittest

import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_terrain_support import GOLDEN_SPEC, SEAM_SPEC, built, validate

from terrain import coords
from terrain.placements import world_extents


class TestPlacements(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result, cls.out = built("golden", GOLDEN_SPEC)
        cls.rep = validate(cls.out)
        cls.info = cls.rep.adts[(32, 32)]

    def test_name_tables(self):
        self.assertEqual(self.info.m2_names, ["World\\Made\\Up\\Tree.m2", "World\\Made\\Up\\Rock.m2"])
        self.assertEqual(self.info.wmo_names, ["World\\wmo\\Made\\Up\\Hut.wmo"])
        self.assertEqual(self.info.textures, ["Tileset\\Made\\Up\\GrassA.blp", "Tileset\\Made\\Up\\RockA.blp",
                                              "Tileset\\Made\\Up\\SandA.blp"])
        self.assertEqual(self.info.mtxf, [0, 0, 1])

    def test_doodad_records(self):
        tree, rock = self.info.mddf
        self.assertEqual((tree["uid"], rock["uid"]), (900, 901))
        self.assertEqual(tree["scale"], 1280)  # 1.25 * 1024
        self.assertEqual(rock["scale"], 1024)
        # Positions are float32 around 17066 in the file, so they round-trip to about 0.002 yards.
        self.assertAlmostEqual(tree["world"][0], -120.0, delta=0.002)
        self.assertAlmostEqual(tree["world"][1], -260.0, delta=0.002)
        ground = self.result.context.grid.ground_height(-120.0, -260.0)
        self.assertAlmostEqual(tree["world"][2], ground, delta=0.001)
        self.assertAlmostEqual(rock["world"][2], 12.5, places=4)
        self.assertEqual(tuple(round(v, 4) for v in rock["rot"]), (5.0, 40.0, -3.0))
        # facing 30 (server orientation) = rotation.y facing - 180 (the client adds 180, CMap::CreateDoodadDef).
        self.assertAlmostEqual(tree["rot"][1], 210.0, places=4)

    def test_wmo_record_and_extents(self):
        (hut,) = self.info.modf
        self.assertEqual(hut["uid"], 902)
        self.assertEqual(hut["scale"], 1024)
        self.assertEqual(hut["flags"], 0)
        lo, hi = world_extents(hut["world"], hut["rot"], 1.0, ((-6, -5, -1), (7, 5, 9)))
        want_lo = (coords.ZERO - hi[1], lo[2], coords.ZERO - hi[0])
        want_hi = (coords.ZERO - lo[1], hi[2], coords.ZERO - lo[0])
        for a, b in zip(want_lo + want_hi, hut["lo"] + hut["hi"]):
            self.assertAlmostEqual(a, b, places=2)

    def test_extents_rotation_matches_client(self):
        # facing 90 -> rotation.y = 270 -> the client turns by 270 + 180 = 90 degrees about Z: model +X points to
        # world +Y. The box spans model x -6..7, so world y spans -6..7 around the position.
        lo, hi = world_extents((0.0, 0.0, 0.0), (0.0, 270.0, 0.0), 1.0, ((-6, -5, -1), (7, 5, 9)))
        self.assertAlmostEqual(lo[1], -6.0, places=6)
        self.assertAlmostEqual(hi[1], 7.0, places=6)
        self.assertAlmostEqual(lo[0], -5.0, places=6)
        self.assertAlmostEqual(hi[0], 5.0, places=6)

    def test_mcrf_ranges(self):
        n_doodad = len(self.info.mddf)
        n_wmo = len(self.info.modf)
        refd = set()
        refw = set()
        for ch in self.info.chunks.values():
            d = ch["refs"][:ch["n_doodad_refs"]]
            w = ch["refs"][ch["n_doodad_refs"]:]
            self.assertEqual(len(w), ch["n_wmo_refs"])
            self.assertTrue(all(0 <= r < n_doodad for r in d))
            self.assertTrue(all(0 <= r < n_wmo for r in w))
            self.assertEqual(d, sorted(d))
            refd.update(d)
            refw.update(w)
        self.assertEqual(refd, set(range(n_doodad)))
        self.assertEqual(refw, set(range(n_wmo)))

    def test_chunk_holding_object_references_it(self):
        x, y = -400.0, -400.0
        u, v = coords.world_to_lattice(x, y)
        key = (int(v) // 16 - 32 * 16, int(u) // 16 - 32 * 16)
        self.assertIn(0, self.info.chunks[key]["refs"][self.info.chunks[key]["n_doodad_refs"]:])

    def test_pois_json(self):
        with open(os.path.join(self.out, "pois.json"), encoding="ascii") as f:
            doc = json.load(f)
        self.assertEqual(doc["map_directory"], "GoldenT")
        (poi,) = doc["pois"]
        self.assertEqual((poi["name"], poi["kind"], poi["radius"]), ("drop", "crate_drop", 5.0))
        ground = self.result.context.grid.ground_height(-300.0, -100.0)
        self.assertAlmostEqual(poi["z"], round(ground, 3), places=3)

    def test_poi_spot_is_flat(self):
        # The whole stated radius (5) is flat ground, out to its rim.
        grid = self.result.context.grid
        pts = [(0.0, 0.0)] + [(4.95 * coords.dcos(a), 4.95 * coords.dsin(a)) for a in range(0, 360, 15)]
        heights = [grid.ground_height(-300.0 + dx, -100.0 + dy) for dx, dy in pts]
        self.assertLess(max(heights) - min(heights), 1e-9)


class TestSpanning(unittest.TestCase):
    """Objects on tile seams appear in every tile they reach, with the same unique id and data."""

    @classmethod
    def setUpClass(cls):
        cls.result, cls.out = built("seam", SEAM_SPEC)
        cls.rep = validate(cls.out)

    def test_wmo_in_all_four_tiles(self):
        found = {}
        for tile, info in self.rep.adts.items():
            for e in info.modf:
                found.setdefault(e["uid"], []).append((tile, e["pos"], e["rot"], e["lo"], e["hi"]))
        (uid, copies), = found.items()
        self.assertEqual(sorted(t for t, *_ in copies), [(31, 31), (31, 32), (32, 31), (32, 32)])
        self.assertEqual(len({tuple(c[1:]) for c in copies}), 1)

    def test_doodad_in_all_four_tiles(self):
        tiles = sorted(t for t, info in self.rep.adts.items() if info.mddf)
        self.assertEqual(tiles, [(31, 31), (31, 32), (32, 31), (32, 32)])
        uids = {e["uid"] for info in self.rep.adts.values() for e in info.mddf}
        self.assertEqual(len(uids), 1)

    def test_unique_ids_disjoint(self):
        d = {e["uid"] for info in self.rep.adts.values() for e in info.mddf}
        w = {e["uid"] for info in self.rep.adts.values() for e in info.modf}
        self.assertFalse(d & w)


if __name__ == "__main__":
    unittest.main(verbosity=2)
