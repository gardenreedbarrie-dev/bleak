"""Mountain ranges along the map edge (heightmap feature `mountains`): heights, peaks and saddles, ledges, the
cliff that keeps players in (the flood-fill check), determinism and the spec's limits."""

import copy
import math
import os
import statistics
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_terrain_support import built, validate  # noqa: E402

from terrain.build import border_check  # noqa: E402
from terrain.heightmap import HeightField, LatticeGrid  # noqa: E402
from terrain.spec import parse_spec  # noqa: E402
from terrain.spec_errors import SpecError  # noqa: E402

RANGE = {"type": "mountains", "width": 110, "height": [80, 160], "cliff": {"height": 30, "width": 12}, "layers": 3,
         "peak_scale": 90, "saddles": 0.45, "ledges": {"step": 14, "flat": 0.4, "coverage": 0.5}, "jitter": 14,
         "jitter_scale": 160, "corner_radius": 160, "seed": 3}

MOUNTAIN_SPEC = {
    "map": {"directory": "RangeT", "tiles": {"x": [32, 32], "y": [32, 32]}},
    "seed": 515,
    "area_id": 1,
    "heightmap": {"base": 10.0, "noise": [{"scale": 150, "amplitude": 3.0, "octaves": 2}],
                  "features": [RANGE]},
    "textures": [{"name": "g", "path": "Tileset\\Made\\Up\\G.blp"}, {"name": "r", "path": "Tileset\\Made\\Up\\R.blp"}],
    "texture_rules": [{"texture": "r", "slope": {"min": 30, "max": 45}}],
}
X0, X1, Y0, Y1 = -533.3333, 0.0, -533.3333, 0.0


def make(range_changes=None, **spec_changes):
    data = copy.deepcopy(MOUNTAIN_SPEC)
    data.update(spec_changes)
    data["heightmap"]["features"] = [dict(RANGE, **(range_changes or {}))]
    spec = parse_spec(data)
    field = HeightField(spec)
    return spec, field


def ray_crests(field, width, step=6.0, margin=170.0):
    """Highest point above the valley floor along inward rays from the middle part of each edge."""
    out = []
    for side in range(4):
        s = margin
        while s < (X1 - X0) - margin:
            if side == 0:
                ex, ey, nx, ny = X1, Y1 - s, -1.0, 0.0
            elif side == 1:
                ex, ey, nx, ny = X1 - s, Y0, 0.0, 1.0
            elif side == 2:
                ex, ey, nx, ny = X0, Y0 + s, 1.0, 0.0
            else:
                ex, ey, nx, ny = X0 + s, Y1, 0.0, -1.0
            top = max(field.raw(ex + nx * t, ey + ny * t) for t in range(0, int(width) + 30, 3))
            foot = field.raw(ex + nx * (width + 30), ey + ny * (width + 30))
            out.append(top - foot)
            s += step
    return out


class TestMountainHeights(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec, cls.field = make()
        cls.crests = ray_crests(cls.field, RANGE["width"])

    def test_valley_untouched_and_edge_high(self):
        flat_spec = parse_spec(dict(copy.deepcopy(MOUNTAIN_SPEC), heightmap={
            "base": 10.0, "noise": MOUNTAIN_SPEC["heightmap"]["noise"]}))
        flat = HeightField(flat_spec)
        for x, y in ((-266.7, -266.7), (-200.0, -320.0), (-330.0, -180.0)):
            self.assertEqual(self.field.raw(x, y), flat.raw(x, y))
        self.assertGreater(self.field.raw(-266.7, -2.0) - flat.raw(-266.7, -2.0), 60.0)

    def test_peaks_between_80_and_160(self):
        peaks = [self.crests[i] for i in range(1, len(self.crests) - 1)
                 if self.crests[i] >= self.crests[i - 1] and self.crests[i] >= self.crests[i + 1]]
        self.assertGreater(len(peaks), 6)
        self.assertGreaterEqual(min(peaks), 80.0 * 0.85)
        self.assertLessEqual(max(self.crests), 160.0 + 8.0)  # plus the base noise
        self.assertGreater(statistics.pstdev(self.crests), 4.0)  # varied along the range

    def test_saddles_dip_between_peaks(self):
        c = self.crests
        dips = [i for i in range(1, len(c) - 1) if c[i] < c[i - 1] and c[i] < c[i + 1]]
        self.assertTrue(dips)
        self.assertTrue(any(max(c[max(0, i - 6):i]) - c[i] > 5.0 and max(c[i + 1:i + 7]) - c[i] > 5.0
                            for i in dips))

    def test_saddles_setting_deepens_dips(self):
        _, smooth = make({"saddles": 0.0})
        _, deep = make({"saddles": 0.9})
        def dip_depth(c):
            # How far each ray's crest lies below the highest crest within 4 rays either side.
            return statistics.mean(max(c[max(0, i - 4):i + 5]) - c[i] for i in range(len(c)))
        a = ray_crests(smooth, RANGE["width"], step=6.0)
        b = ray_crests(deep, RANGE["width"], step=6.0)
        self.assertGreater(dip_depth(b), dip_depth(a) + 1.0)

    def test_ledges_make_shelves(self):
        def shelves(field):
            spec_flat = 0
            for i in range(0, 400, 2):
                for t in range(30, 100, 2):
                    x, y = X1 - t, Y1 - 60 - i
                    h0 = field.raw(x, y)
                    if abs(field.raw(x - 1.0, y) - h0) < 0.15 and abs(field.raw(x, y - 1.0) - h0) < 0.15:
                        spec_flat += 1
            return spec_flat
        _, without = make({"ledges": None})
        self.assertGreater(shelves(self.field), shelves(without) + 20)

    def test_cliff_at_the_foot_is_steep(self):
        rng = next(f for f in self.field.features if f.kind == "mountains").data["range"]
        steep = 0
        total = 0
        for i in range(0, 300, 7):
            y = Y1 - 120 - i
            # Find the foot along this row: the first point inward of the range (depth crosses 0).
            x_foot = next(X1 - t * 0.5 for t in range(0, 600) if rng.depth(X1 - t * 0.5, y) <= 0.0)
            best = 0.0
            for k in range(0, 24):
                x = x_foot + k * 0.5
                g = (self.field.raw(x + 0.5, y) - self.field.raw(x - 0.5, y)) / 1.0
                best = max(best, g)
            total += 1
            steep += best > math.tan(math.radians(55.0))
        self.assertEqual(steep, total)

    def test_corners_are_rounded(self):
        rng = next(f for f in self.field.features if f.kind == "mountains").data["range"]
        r = rng.radius
        # On the corner's diagonal the distance in is measured to a rounded rectangle.
        d = rng.inside_distance(X1 - 40.0, Y1 - 40.0)
        self.assertAlmostEqual(d, r - math.hypot(r - 40.0, r - 40.0), places=6)
        self.assertAlmostEqual(rng.inside_distance(X1 - 40.0, -266.0), 40.0, places=6)

    def test_deterministic_and_seeded(self):
        _, again = make()
        _, other = make({"seed": 4})
        pts = [(X1 - 30.0, -200.0 - 7 * i) for i in range(20)]
        self.assertEqual([self.field.raw(*p) for p in pts], [again.raw(*p) for p in pts])
        self.assertNotEqual([self.field.raw(*p) for p in pts], [other.raw(*p) for p in pts])


class TestMountainBorder(unittest.TestCase):
    def test_players_cannot_leave(self):
        for seed in (1, 2, 3):
            with self.subTest(seed=seed):
                spec, field = make({"seed": seed}, seed=900 + seed)
                result = border_check(spec, LatticeGrid(spec, field), field=field)
                self.assertTrue(result["closed"], result)
                self.assertTrue(result["surface_slope_checked"])
                self.assertFalse(result["mountains"]["past_cliff"], result)
                self.assertLessEqual(result["mountains"]["deepest_yards"], RANGE["cliff"]["width"])

    def test_a_low_cliff_lets_players_out(self):
        spec, field = make({"cliff": {"height": 4, "width": 12}, "height": [9, 12], "ledges": None})
        result = border_check(spec, LatticeGrid(spec, field), field=field)
        self.assertTrue(result["mountains"]["past_cliff"] or not result["closed"])

    # A 24-yard ramp from the valley up the south range (or wall) to the tile edge: a way out the check must find.
    RAMP = {"type": "ramp", "from": [-266.0, -380.0, None], "to": [-266.0, -533.3, 70.0], "width": 24, "falloff": 6}
    MOAT = {"name": "moat", "width": 12, "depth": 8, "bank": 4, "freeboard": 0.6,
            "reaches": [{"level": 8.0, "path": [[-30.0, -340.0], [-503.0, -340.0]]}]}

    def escape(self, features, **spec_changes):
        data = copy.deepcopy(MOUNTAIN_SPEC)
        data["heightmap"]["features"] = features
        data.update(spec_changes)
        spec = parse_spec(data)
        field = HeightField(spec)
        return border_check(spec, LatticeGrid(spec, field), field=field)

    def assert_escape(self, result):
        self.assertTrue(not result["closed"] or result["mountains"]["past_cliff"], result)

    def test_a_river_across_the_valley_does_not_hide_a_way_out(self):
        # The carved channel's sides are steeper than walking allows, but only the 0.6-yard lip stands above the
        # water: players swim across and walk up the ramp.
        self.assert_escape(self.escape([dict(RANGE), self.RAMP]))
        self.assert_escape(self.escape([dict(RANGE), self.RAMP, {"type": "water_bodies"}], rivers=[self.MOAT]))

    def test_a_steep_spot_at_the_centre_does_not_hide_a_way_out(self):
        # Players can be dropped anywhere in the valley, not only on the mesa at the centre.
        mesa = {"type": "flatten", "shape": {"circle": {"center": [-266.67, -266.67], "radius": 30}}, "height": None,
                "offset": 25, "falloff": 6, "mode": "raise"}
        self.assert_escape(self.escape([dict(RANGE), self.RAMP, mesa]))
        closed = self.escape([dict(RANGE), mesa])
        self.assertTrue(closed["closed"])
        self.assertFalse(closed["mountains"]["past_cliff"])

    def test_swimming_crosses_a_river_without_mountains(self):
        wall = {"type": "border", "inset": 10, "width": 25, "height": 50}
        ramp = dict(self.RAMP, **{"from": [-266.0, -420.0, None]})
        moat = dict(self.MOAT, reaches=[{"level": 8.0, "path": [[-15.0, -380.0], [-518.0, -380.0]]}])
        self.assertTrue(self.escape([wall, {"type": "water_bodies"}], rivers=[moat])["closed"])
        self.assertFalse(self.escape([wall, ramp, {"type": "water_bodies"}], rivers=[moat])["closed"])

    def test_specs_without_mountains_keep_the_rise_check(self):
        data = copy.deepcopy(MOUNTAIN_SPEC)
        data["heightmap"]["features"] = [{"type": "border", "inset": 10, "width": 25, "height": 50}]
        spec = parse_spec(data)
        field = HeightField(spec)
        result = border_check(spec, LatticeGrid(spec, field), field=field)
        self.assertNotIn("surface_slope_checked", result)
        self.assertNotIn("mountains", result)


class TestMountainBuild(unittest.TestCase):
    def test_build_validates_and_reports(self):
        result, out = built("range", MOUNTAIN_SPEC)
        rep = validate(out)
        self.assertEqual(rep.errors, [])
        m = result.manifest
        self.assertEqual(m["mountains"][0]["height"], [80.0, 160.0])
        self.assertTrue(m["border"]["closed"])
        self.assertFalse(any("walk" in w for w in m["warnings"]))
        self.assertGreater(m["height_range"][1], 80.0)


class TestMountainSpecErrors(unittest.TestCase):
    def bad(self, changes, text):
        with self.assertRaisesRegex(SpecError, text):
            make(changes)

    def test_rejects(self):
        self.bad({"width": 230}, "leaves less than 100 yards of valley")
        self.bad({"height": [160, 80]}, "lowest <= highest")
        self.bad({"cliff": {"height": 90, "width": 12}}, "below the lowest peaks")
        self.bad({"layers": 6}, "layers")
        self.bad({"saddles": 1.5}, "saddles")
        self.bad({"ledges": {"step": 10, "shelf": 1}}, "unknown keys")
        self.bad({"peaks": 3}, "unknown keys")

    def test_single_height_and_defaults(self):
        spec, _ = make({"height": 100, "cliff": {}, "ledges": None})
        f = spec.mountain_features()[0]
        self.assertEqual(f["height"], (100.0, 100.0))
        self.assertEqual(f["cliff_height"], 30.0)
        self.assertIsNone(f["ledges"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
