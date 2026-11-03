"""Scatter: deterministic cover placement with weights, density, spacing and masks (royale-spec.md 2.4)."""

import copy
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_terrain_support import built, validate  # noqa: E402

from terrain import coords  # noqa: E402
from terrain.heightmap import HeightField, LatticeGrid  # noqa: E402
from terrain.placements import scatter_placements  # noqa: E402
from terrain.spec import parse_spec  # noqa: E402
from terrain.spec_errors import SpecError  # noqa: E402

RIVER = [[0, -100], [-533.3, -130]]
ROAD = [[-50, -300], [-480, -300]]

SCATTER_SPEC = {
    "map": {"directory": "ScatterT", "tiles": {"x": [32, 32], "y": [32, 32]}},
    "seed": 7,
    "area_id": 1,
    "uid_base": 500,
    "heightmap": {
        "base": 10.0,
        "noise": [{"scale": 120, "amplitude": 3.0}],
        "features": [
            {"type": "hill", "center": [-400, -400], "radius": 40, "height": 60, "shape": "cone"},
            {"type": "river", "path": RIVER, "width": 12, "bank": 10, "bed": 1.0},
        ],
    },
    "textures": [{"name": "a", "path": "Tileset\\X\\A.blp"}, {"name": "b", "path": "Tileset\\X\\B.blp"}],
    "roads": [{"name": "road", "points": ROAD, "width": 8, "texture": "b"}],
    "water": [{"height": 4.0, "shape": {"polyline": {"points": RIVER, "width": 30}}}],
    "wmos": [{"model": "World\\wmo\\X\\Hut.wmo", "position": [-100, -420], "radius": 15}],
    "doodads": [{"model": "World\\X\\Totem.m2", "position": [-60, -60], "radius": 4}],
    "pois": [{"name": "site", "kind": "landmark", "position": [-250, -450], "radius": 30},
             {"name": "box", "kind": "crate", "param": 1, "position": [-150, -200], "radius": 2}],
    "scatter": [
        {"name": "g1", "seed": 1, "density": 30, "min_spacing": 6,
         "models": [{"model": "World\\X\\Tree.m2", "weight": 3, "radius": 4, "body": 1.5},
                    {"model": "World\\X\\Rock.m2", "weight": 1, "radius": 6, "body": 3, "scale": [0.5, 1.5]}],
         "slope": {"max": 30}, "height": {"min": 4.5, "max": 60},
         "clearance": {"roads": 3, "river": 5, "pois": 4, "placements": 2}},
        {"name": "g2", "seed": 2, "density": 200, "count": 10, "min_spacing": 4, "facing": 45,
         "models": [{"model": "World\\X\\Bush.m2", "radius": 2, "body": 1}],
         "shape": {"circle": {"center": [-300, -150], "radius": 40}},
         "exclude": [{"circle": {"center": [-300, -150], "radius": 10}}]},
    ],
}


def make(data=None):
    spec = parse_spec(copy.deepcopy(data or SCATTER_SPEC))
    grid = LatticeGrid(spec, HeightField(spec))
    placements, stats = scatter_placements(spec, grid)
    return spec, grid, placements, stats


def slope_deg(grid, x, y):
    u, v = coords.world_to_lattice(x, y)
    worst = 0.0
    for r in (math.floor(u), math.floor(u) + 1):
        for c in (math.floor(v), math.floor(v) + 1):
            worst = max(worst, math.degrees(math.acos(min(1.0, grid.normal(r, c)[2]))))
    return worst


def seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def line_dist(points, x, y):
    return min(seg_dist(x, y, *a, *b) for a, b in zip(points, points[1:]))


class TestScatter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec, cls.grid, cls.placements, cls.stats = make()
        cls.g1 = [p for p in cls.placements if p.label.startswith("g1 ")]
        cls.g2 = [p for p in cls.placements if p.label.startswith("g2 ")]

    def test_places_something_and_reports(self):
        self.assertGreater(len(self.g1), 100)
        self.assertEqual([s["name"] for s in self.stats], ["g1", "g2"])
        self.assertEqual(self.stats[0]["placed"], len(self.g1))
        self.assertEqual(self.stats[1]["placed"], len(self.g2))
        self.assertTrue(all(p.kind == "doodad" and p.z is None and p.uid is None for p in self.placements))
        self.assertEqual(self.g1[0].label, "g1 #1")

    def test_deterministic(self):
        _, _, again, _ = make()
        self.assertEqual([(p.model, p.x, p.y, p.rotation, p.scale) for p in again],
                         [(p.model, p.x, p.y, p.rotation, p.scale) for p in self.placements])

    def test_seeds_change_the_layout(self):
        data = copy.deepcopy(SCATTER_SPEC)
        data["scatter"][0]["seed"] = 99
        _, _, other, _ = make(data)
        self.assertNotEqual([(p.x, p.y) for p in other if p.label.startswith("g1 ")],
                            [(p.x, p.y) for p in self.g1])
        data = copy.deepcopy(SCATTER_SPEC)
        data["seed"] = 8
        _, _, other, _ = make(data)
        self.assertNotEqual([(p.x, p.y) for p in other], [(p.x, p.y) for p in self.placements])

    def test_masks(self):
        rivers = RIVER
        for p in self.g1:
            body = 1.5 if p.model.endswith("Tree.m2") else 3.0 * p.scale
            self.assertLessEqual(slope_deg(self.grid, p.x, p.y), 30.0 + 1e-6, p.label)
            ground = self.grid.ground_height(p.x, p.y)
            self.assertTrue(4.5 <= ground <= 60.0, p.label)
            self.assertGreaterEqual(line_dist(ROAD, p.x, p.y) - 4.0, 3.0 + body - 1e-6, p.label)
            self.assertGreaterEqual(line_dist(rivers, p.x, p.y) - 6.0, 5.0 + body - 1e-6, p.label)
            self.assertGreaterEqual(math.hypot(p.x + 250, p.y + 450), 30 + 4 + body - 1e-6, p.label)
            self.assertGreaterEqual(math.hypot(p.x + 150, p.y + 200), 2 + 4 + body - 1e-6, p.label)
            self.assertGreaterEqual(math.hypot(p.x + 100, p.y + 420), 15 + 2 + body - 1e-6, p.label)
            self.assertGreaterEqual(math.hypot(p.x + 60, p.y + 60), 2 + 2 + body - 1e-6, p.label)

    def test_dry(self):
        for p in self.placements:
            wet = line_dist(RIVER, p.x, p.y) <= 15.0 and self.grid.ground_height(p.x, p.y) < 4.25
            self.assertFalse(wet, p.label)

    def test_spacing(self):
        def body(p):
            return (1.5 if p.model.endswith("Tree.m2") else 1.0 if p.model.endswith("Bush.m2") else 3.0) * p.scale

        for i, a in enumerate(self.placements):
            for b in self.placements[i + 1:]:
                d = math.hypot(a.x - b.x, a.y - b.y)
                need = body(a) + body(b)
                if a.label.split()[0] == b.label.split()[0]:
                    need = max(need, 6.0 if a.label.startswith("g1") else 4.0)
                self.assertGreaterEqual(d, need - 1e-6, (a.label, b.label))

    def test_count_shape_exclude_and_facing(self):
        self.assertEqual(len(self.g2), 10)
        for p in self.g2:
            d = math.hypot(p.x + 300, p.y + 150)
            self.assertTrue(10.0 <= d <= 40.0, p.label)
            self.assertEqual(p.rotation, (0.0, 225.0, 0.0))  # facing 45 -> rotation.y = facing - 180

    def test_weights_scale_and_radius(self):
        trees = [p for p in self.g1 if p.model.endswith("Tree.m2")]
        rocks = [p for p in self.g1 if p.model.endswith("Rock.m2")]
        self.assertGreater(len(trees), len(rocks) * 1.5)
        self.assertTrue(rocks)
        self.assertTrue(all(0.5 <= p.scale <= 1.5 for p in rocks))
        self.assertTrue(all(p.scale == 1.0 for p in trees))
        self.assertTrue(all(abs(p.radius - 6 * p.scale) < 1e-9 for p in rocks))
        facings = {round(p.rotation[1]) for p in self.g1}
        self.assertGreater(len(facings), 50)  # random facing without "facing"

    def test_placement_clearance_uses_model_bounds(self):
        data = copy.deepcopy(SCATTER_SPEC)
        data["wmos"] = [{"model": "World\\wmo\\X\\Hut.wmo", "position": [-200, -330],
                         "bounds": [[-20, -20, 0], [20, 20, 10]]}]  # radius stays at its default, 32
        data["scatter"] = data["scatter"][:1]
        data["scatter"][0]["clearance"] = {"placements": 2}
        _, _, placements, _ = make(data)
        gaps = [math.hypot(p.x + 200, p.y + 330) - (1.5 if p.model.endswith("Tree.m2") else 3.0 * p.scale)
                for p in placements]
        self.assertGreaterEqual(min(gaps), 22.0 - 1e-6)
        self.assertLess(min(gaps), 34.0)  # closer than the default radius would allow

    def test_noise_mask_thins_out(self):
        data = copy.deepcopy(SCATTER_SPEC)
        data["scatter"][0]["noise"] = {"scale": 80, "threshold": 0.4, "fade": 0.1}
        _, _, thin, stats = make(data)
        self.assertLess(len([p for p in thin if p.label.startswith("g1 ")]), len(self.g1) * 0.7)
        self.assertGreater(stats[0]["rejected"]["noise"], 0)


class TestScatterBuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result, cls.out = built("scatter", SCATTER_SPEC)
        cls.rep = validate(cls.out)

    def test_validator_clean_and_counts(self):
        self.assertEqual(self.rep.errors, [])
        m = self.result.manifest
        scattered = sum(g["placed"] for g in m["scatter"])
        self.assertEqual(m["doodad_count"], 1 + scattered)
        self.assertEqual(self.rep.summary["unique_objects"], 2 + scattered)

    def test_scattered_ids_come_after_the_spec_placements(self):
        fixed = [p["uid"] for p in self.result.manifest["placements"] if not p["label"].startswith(("g1 ", "g2 "))]
        scattered = [p["uid"] for p in self.result.manifest["placements"] if p["label"].startswith(("g1 ", "g2 "))]
        self.assertEqual(sorted(fixed), [500, 501])
        self.assertGreater(min(scattered), max(fixed))

    def test_roads_in_manifest(self):
        (road,) = self.result.manifest["roads"]
        self.assertEqual((road["name"], road["width"]), ("road", 8.0))


class TestScatterErrors(unittest.TestCase):
    def bad(self, **group):
        data = copy.deepcopy(SCATTER_SPEC)
        g = {"name": "x", "density": 1, "models": [{"model": "World\\X\\A.m2"}]}
        g.update(group)
        data["scatter"] = [g]
        with self.assertRaises(SpecError):
            parse_spec(data)

    def test_rejects(self):
        self.bad(models=[])
        self.bad(models=[{"model": "World\\X\\A.m2", "weight": 0}])
        self.bad(models=[{"model": "World\\X\\A.wmo"}])
        self.bad(models=[{"model": "World\\X\\A.m2", "scale": [2, 1]}])
        self.bad(models=[{"model": "World\\X\\A.m2", "extra": 1}])
        self.bad(bogus=1)
        self.bad(density=0)
        self.bad(density=10000)  # 1-yard cells over a whole tile: too many candidates
        self.bad(clearance={"lakes": 2})
        self.bad(dry="yes")
        self.bad(slope={"max": 95})
        self.bad(height={"min": 5, "max": 1})
        self.bad(poi_kinds="crate")
        self.bad(count=0)
        self.bad(name="has space")

    def test_duplicate_group_names(self):
        data = copy.deepcopy(SCATTER_SPEC)
        data["scatter"][1]["name"] = "g1"
        with self.assertRaises(SpecError):
            parse_spec(data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
