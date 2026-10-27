"""Beaches (spec `beaches`): sand and wet sand along every water edge by distance and height, river and lake beds
under the water, kept off cliffs, waterfalls and excluded shapes."""

import copy
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_terrain_support import built, validate  # noqa: E402

from terrain import coords  # noqa: E402
from terrain.heightmap import HeightField, LatticeGrid  # noqa: E402
from terrain.spec import parse_spec  # noqa: E402
from terrain.spec_errors import SpecError  # noqa: E402
from terrain.texturing import TexturePainter  # noqa: E402

BEACH_SPEC = {
    "map": {"directory": "BeachT", "tiles": {"x": [32, 32], "y": [32, 32]}},
    "seed": 8,
    "area_id": 1,
    "heightmap": {"base": 10.0, "features": [
        {"type": "hill", "center": [-200, -170], "radius": 30, "height": 40, "shape": "cone"},
        {"type": "water_bodies"}]},
    "textures": [{"name": "grass", "path": "Tileset\\Made\\Up\\Grass.blp"},
                 {"name": "sand", "path": "Tileset\\Made\\Up\\Sand.blp"},
                 {"name": "wet", "path": "Tileset\\Made\\Up\\Wet.blp"},
                 {"name": "riverbed", "path": "Tileset\\Made\\Up\\Riverbed.blp"},
                 {"name": "lakebed", "path": "Tileset\\Made\\Up\\Lakebed.blp"}],
    "lakes": [{"name": "lake", "level": 6.0, "depth": 5, "shelf": 20, "shore": 40,
               "shape": {"circle": {"center": [-266, -266], "radius": 90}}}],
    "rivers": [{"name": "stream", "width": 10, "depth": 2, "bank": 12, "fall_run": 3,
                "reaches": [{"level": 9, "path": [[-60, -460], [-140, -420]]},
                            {"level": 6, "path": [[-240, -330]]}]}],
    "beaches": {"sand": "sand", "wet_sand": "wet", "riverbed": "riverbed", "lakebed": "lakebed", "width": 14,
                "fade": 4, "height": 2.5, "wet_width": 3, "edge_noise": 0.0, "slope_max": 30,
                "exclude": [{"circle": {"center": [-266, -176], "radius": 16}}]},
}
SAND, WET, RIVERBED, LAKEBED = 1, 2, 3, 4


class TestBeaches(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = parse_spec(copy.deepcopy(BEACH_SPEC))
        cls.grid = LatticeGrid(cls.spec, HeightField(cls.spec))
        cls.painter = TexturePainter(cls.spec, cls.grid)
        cls.weights = cls.painter.weights_for_tile(32, 32)

    def at(self, x, y):
        u, v = coords.world_to_lattice(x, y)
        r = int(round(u)) - 32 * 256
        c = int(round(v)) - 32 * 256
        i = r * 257 + c
        return [w[i] for w in self.weights], self.grid.get(32 * 256 + r, 32 * 256 + c)

    def waterline(self, angle):
        """The first dry lattice point walking out from the lake centre along `angle` degrees."""
        for k in range(0, 200):
            d = 50.0 + k * 0.5
            x, y = -266 + d * coords.dcos(angle), -266 + d * coords.dsin(angle)
            if self.at(x, y)[1] >= 6.0:
                return d
        raise AssertionError("no waterline")

    def test_lake_floor_and_river_bed(self):
        w, h = self.at(-266, -300)
        self.assertLess(h, 6.0 - 2.0)
        self.assertGreater(w[LAKEBED], 0.95)
        w, h = self.at(-100, -440)  # mid-reach of the stream, on the centre line
        self.assertLess(h, 9.0 - 1.0)
        self.assertGreater(w[RIVERBED], 0.95)
        self.assertLess(w[LAKEBED], 0.01)

    def test_sand_band_and_wet_sand_at_the_waterline(self):
        for angle in (200.0, 250.0):
            d = self.waterline(angle)
            x, y = -266 + (d + 1.0) * coords.dcos(angle), -266 + (d + 1.0) * coords.dsin(angle)
            w, _ = self.at(x, y)
            self.assertGreater(w[WET], 0.5, angle)
            x, y = -266 + (d + 8.0) * coords.dcos(angle), -266 + (d + 8.0) * coords.dsin(angle)
            w, h = self.at(x, y)
            self.assertLess(h - 6.0, 2.5)
            self.assertGreater(w[SAND], 0.9, angle)
            x, y = -266 + (d + 30.0) * coords.dcos(angle), -266 + (d + 30.0) * coords.dsin(angle)
            w, _ = self.at(x, y)
            self.assertLess(w[SAND] + w[WET], 0.01, angle)

    def test_no_sand_high_above_the_water_or_on_cliffs(self):
        # The cone hill rises steeply right by the shore: no sand on its flank.
        for d in range(8, 26, 3):
            w, h = self.at(-200 + d * 0.0, -170 - d)
            if h > 6.0 + 2.5 + 1.5:
                self.assertLess(w[SAND], 0.01, (d, h))

    def test_sand_stays_off_steep_ground(self):
        sand = next(r for r in self.painter.rules if getattr(r, "part", None) == "sand")
        d = self.waterline(220.0) + 6.0
        x, y = -266 + d * coords.dcos(220.0), -266 + d * coords.dsin(220.0)
        u, v = coords.world_to_lattice(x, y)
        i = (int(round(u)) - self.grid.row0) * self.grid.cols + int(round(v)) - self.grid.col0
        h = self.grid.h[i]
        self.assertGreater(sand.coverage_at(i, x, y, h, 1.0), 0.9)
        self.assertGreater(sand.coverage_at(i, x, y, h, coords.dcos(25.0)), 0.9)
        self.assertEqual(sand.coverage_at(i, x, y, h, coords.dcos(36.0)), 0.0)  # slope_max 30 (+- 4)

    def test_excluded_shape_and_fall_clearance(self):
        d = self.waterline(90.0)  # the exclude circle sits on the shore at +Y
        w, _ = self.at(-266, -266 + d + 4.0)
        self.assertLess(w[SAND] + w[WET], 0.01)
        fall = self.spec.rivers[0]["falls"][0]
        self.assertEqual(self.spec.beaches["falls"], [(fall["x"], fall["y"])])
        for dx, dy in ((8.0, 6.0), (-6.0, 9.0)):
            w, _ = self.at(fall["x"] + dx, fall["y"] + dy)
            self.assertLess(w[SAND] + w[WET], 0.01)

    def test_water_field_nearest_matches_brute_force(self):
        field = self.painter.field
        grid = self.grid
        wet = [i for i in range(grid.rows * grid.cols) if field.level[i] == field.level[i]]
        self.assertTrue(wet)
        cols = grid.cols
        far = coords.world_to_lattice(-266.0, -40.0)
        self.assertIsNone(field.nearest((int(round(far[0])) - grid.row0) * cols + int(round(far[1])) - grid.col0))
        for angle, out in ((0.0, 3.0), (200.0, 9.0), (300.0, 15.0)):
            d = self.waterline(angle) + out
            x, y = -266 + d * coords.dcos(angle), -266 + d * coords.dsin(angle)
            u, v = coords.world_to_lattice(x, y)
            r, c = int(round(u)) - grid.row0, int(round(v)) - grid.col0
            near = field.nearest(r * cols + c)
            self.assertIsNotNone(near)
            best = min(math.hypot(r - j // cols, c - j % cols) for j in wet) * coords.HALF_UNIT
            self.assertAlmostEqual(near[0], best, delta=coords.HALF_UNIT)

    def test_build_validates(self):
        result, out = built("beach", BEACH_SPEC)
        self.assertEqual(validate(out).errors, [])
        self.assertEqual(result.manifest["beaches"]["sand"], "sand")
        self.assertEqual(result.manifest["beaches"]["lakebed"], "lakebed")


class TestBeachSpec(unittest.TestCase):
    def test_marker_and_defaults(self):
        data = copy.deepcopy(BEACH_SPEC)
        data["texture_rules"] = [{"beaches": True}, {"texture": "grass", "height": {"min": 30}}]
        spec = parse_spec(data)
        kinds = [r.get("kind", "rule") for r in spec.texture_rules]
        self.assertEqual(kinds, ["beach", "beach", "beach", "beach", "rule"])
        data = copy.deepcopy(BEACH_SPEC)
        data["beaches"] = {"sand": "sand", "riverbed": "riverbed"}
        spec = parse_spec(data)
        self.assertEqual(spec.beaches["lakebed"], spec.beaches["riverbed"])  # lakebed defaults to the riverbed
        self.assertEqual([r["part"] for r in spec.texture_rules], ["sand", "riverbed"])

    def test_rejects(self):
        data = copy.deepcopy(BEACH_SPEC)
        data["beaches"]["sand"] = "nope"
        with self.assertRaisesRegex(SpecError, "unknown texture"):
            parse_spec(data)
        data = copy.deepcopy(BEACH_SPEC)
        del data["beaches"]
        data["texture_rules"] = [{"beaches": True}]
        with self.assertRaisesRegex(SpecError, "needs a 'beaches' section"):
            parse_spec(data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
