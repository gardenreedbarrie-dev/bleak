"""Royale POI kinds and ids, z_from, roads, the flatten offset (mesa), the 4-layer warning, the pois.json checks."""

import copy
import json
import os
import shutil
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_terrain_support import built, copy_output, validate  # noqa: E402

from terrain import build as tbuild  # noqa: E402
from terrain import validate as tvalidate  # noqa: E402
from terrain.heightmap import HeightField, LatticeGrid  # noqa: E402
from terrain.spec import parse_spec  # noqa: E402
from terrain.spec_errors import SpecError  # noqa: E402
from terrain.texturing import TexturePainter  # noqa: E402

POI_SPEC = {
    "map": {"id": 950, "directory": "PoiT", "tiles": {"x": [32, 32], "y": [32, 32]}},
    "seed": 3,
    "area_id": 1,
    "heightmap": {"base": 6.0, "noise": [{"scale": 150, "amplitude": 2.0}], "features": [
        {"type": "flatten", "shape": {"circle": {"center": [-80, -80], "radius": 20}}, "height": None, "offset": 25,
         "falloff": 6, "mode": "raise"},
    ]},
    "textures": [{"name": "grass", "path": "Tileset\\X\\G.blp"}, {"name": "dirt", "path": "Tileset\\X\\D.blp"},
                 {"name": "stone", "path": "Tileset\\X\\S.blp"}],
    "roads": [{"name": "main", "points": [[-300, -40], [-300, -500]], "width": 8, "fade": 4, "texture": "dirt"}],
    "texture_rules": [{"texture": "stone", "shape": {"rect": {"min": [-320, -300], "max": [-280, -250]}}},
                      {"roads": True}],
    "wmos": [{"label": "hall", "model": "World\\wmo\\X\\Hall.wmo", "position": [-400, -400, 20.0], "radius": 10}],
    "pois": [
        {"name": "lobby", "kind": "lobby", "id": 900, "title": "The Overlook", "position": [-80, -80], "radius": 20},
        {"name": "keep", "kind": "landmark", "id": 5101, "title": "The Bleak Hold", "position": [-266, -266],
         "radius": 60},
        {"name": "c1", "kind": "crate", "param": 1, "position": [-200, -200], "radius": 2},
        {"name": "c2", "kind": "crate", "param": 2, "position": [-400, -400], "z_from": "hall", "z_offset": 0.3},
        {"name": "orb", "kind": "orb_buff", "param": 3, "position": [-150, -350], "radius": 5, "flatten": True},
        {"name": "shadow", "kind": "orb_shadow", "position": [-350, -150, 9.5]},
        {"name": "final", "kind": "final_site", "weight": 12, "position": [-260, -270], "radius": 35},
        {"name": "ford", "kind": "crossing", "title": "Old Ford", "position": [-450, -100], "facing": 103},
        {"name": "drop", "kind": "supply_site", "position": [-120, -450], "radius": 8, "flatten": True},
        {"name": "free", "kind": "storm_center", "param": -4, "weight": 3, "position": [-30, -30]},
    ],
}


def parse(**changes):
    data = copy.deepcopy(POI_SPEC)
    data.update(changes)
    return parse_spec(data)


def with_pois(*pois):
    data = copy.deepcopy(POI_SPEC)
    data["pois"] = list(pois)
    return data


class TestPoiSpec(unittest.TestCase):
    def test_kinds_params_and_weights(self):
        spec = parse()
        by_name = {p["name"]: p for p in spec.pois}
        self.assertEqual(by_name["c2"]["param"], 2)
        self.assertEqual(by_name["final"]["weight"], 12)
        self.assertEqual(by_name["free"]["param"], -4)  # free-form kinds take any param and weight

        bad = [
            {"name": "x", "kind": "crate", "position": [-10, -10]},  # param 0
            {"name": "x", "kind": "crate", "param": 3, "position": [-10, -10]},
            {"name": "x", "kind": "orb_buff", "param": 0, "position": [-10, -10]},
            {"name": "x", "kind": "orb_buff", "param": 4, "position": [-10, -10]},
            {"name": "x", "kind": "final_site", "position": [-10, -10]},  # no weight
            {"name": "x", "kind": "final_site", "weight": 1.5, "position": [-10, -10]},  # weights are integers
            {"name": "x", "kind": "landmark", "weight": 2, "position": [-10, -10]},
            {"name": "x", "kind": "lobby", "param": 1, "position": [-10, -10]},
            {"name": "x", "kind": "crate", "param": 1, "title": "Bad;Title", "position": [-10, -10]},
            {"name": "x", "kind": "crate", "param": 1, "id": 0, "position": [-10, -10]},
            {"name": "x", "kind": "crate", "param": 1, "z_from": "hall", "position": [-10, -10, 3]},
            {"name": "x", "kind": "crate", "param": 1, "z_from": "hall", "radius": 3, "flatten": True,
             "position": [-10, -10]},
            {"name": "x", "kind": "crate", "param": 1, "bogus": 1, "position": [-10, -10]},
        ]
        for poi in bad:
            with self.assertRaises(SpecError, msg=json.dumps(poi)):
                parse_spec(with_pois(poi))

    def test_ids_explicit_unique_and_assigned(self):
        spec = parse()
        ids = [p["id"] for p in spec.pois]
        self.assertEqual(ids[:2], [900, 5101])
        self.assertEqual(ids[2:], [1, 2, 3, 4, 5, 6, 7, 8])
        data = with_pois({"name": "a", "kind": "crate", "param": 1, "id": 2, "position": [-10, -10]},
                         {"name": "b", "kind": "crate", "param": 1, "position": [-20, -20]},
                         {"name": "c", "kind": "crate", "param": 1, "position": [-30, -30]})
        self.assertEqual([p["id"] for p in parse_spec(data).pois], [2, 1, 3])
        dup = with_pois({"name": "a", "kind": "crate", "param": 1, "id": 7, "position": [-10, -10]},
                        {"name": "b", "kind": "crate", "param": 1, "id": 7, "position": [-20, -20]})
        with self.assertRaises(SpecError):
            parse_spec(dup)

    def test_flatten_offset_makes_a_mesa(self):
        spec = parse()
        field = HeightField(spec)
        bare = HeightField(parse(heightmap={"base": 6.0, "noise": [{"scale": 150, "amplitude": 2.0}]}))
        self.assertAlmostEqual(field.raw(-80, -80), bare.raw(-80, -80) + 25.0, places=6)
        self.assertAlmostEqual(field.raw(-80, -95), bare.raw(-80, -80) + 25.0, places=6)  # flat top
        self.assertAlmostEqual(field.raw(-80, -110), bare.raw(-80, -110), places=6)  # beyond the falloff
        with self.assertRaises(SpecError):
            parse(heightmap={"features": [{"type": "flatten", "shape": {"circle": {"center": [0, 0], "radius": 1}},
                                           "offset": "high"}]})

    def test_roads_paint_at_the_marker(self):
        spec = parse()
        # Rule order: stone rect, then the road (the marker) paints over it.
        self.assertEqual([r["texture"] for r in spec.texture_rules], [2, 1])
        grid = LatticeGrid(spec, HeightField(spec))
        weights = TexturePainter(spec, grid).weights_for_tile(32, 32)

        def at(x, y):
            from terrain import coords
            u, v = coords.world_to_lattice(x, y)
            i = (int(u) - 32 * 256) * 257 + (int(v) - 32 * 256)
            return [w[i] for w in weights]

        self.assertGreater(at(-300.0, -275.0)[1], 0.99)  # the road wins inside the stone rect
        self.assertGreater(at(-300.0, -400.0)[1], 0.99)
        self.assertGreater(at(-200.0, -400.0)[0], 0.99)  # away from the road: grass
        # Without a marker the roads paint first, so the stone rect wins over them.
        data = copy.deepcopy(POI_SPEC)
        data["texture_rules"] = data["texture_rules"][:1]
        self.assertEqual([r["texture"] for r in parse_spec(data).texture_rules], [1, 2])
        for bad in ([{"roads": True}, {"roads": True}], [{"roads": False}], [{"roads": True, "texture": "dirt"}]):
            data["texture_rules"] = bad
            with self.assertRaises(SpecError):
                parse_spec(data)
        data = copy.deepcopy(POI_SPEC)
        data["roads"][0]["texture"] = "lava"
        with self.assertRaises(SpecError):
            parse_spec(data)


class TestPoisJson(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result, cls.out = built("pois", POI_SPEC)
        with open(os.path.join(cls.out, "pois.json"), encoding="ascii") as f:
            cls.doc = json.load(f)
        cls.by_name = {p["name"]: p for p in cls.doc["pois"]}

    def test_fields(self):
        self.assertEqual(self.doc["map_id"], 950)
        self.assertEqual(self.doc["world_bounds"], {"min_x": -533.333, "max_x": 0.0, "min_y": -533.333,
                                                    "max_y": 0.0})
        lobby = self.by_name["lobby"]
        self.assertEqual((lobby["id"], lobby["kind"], lobby["title"], lobby["radius"]),
                         (900, "lobby", "The Overlook", 20.0))
        ford = self.by_name["ford"]
        self.assertEqual((ford["facing"], ford["param"], ford["weight"]), (103.0, 0, 0))
        self.assertEqual(self.by_name["final"]["weight"], 12)
        self.assertEqual(self.doc["counts"]["crate"], 2)
        self.assertEqual(self.doc["counts"]["crate:2"], 1)
        self.assertEqual(self.doc["counts"]["orb_buff:3"], 1)

    def test_z_sources(self):
        c2 = self.by_name["c2"]
        self.assertEqual(c2["z_source"], "placement:hall")
        self.assertAlmostEqual(c2["z"], 20.3, places=3)
        self.assertEqual(self.by_name["shadow"]["z_source"], "explicit")
        self.assertEqual(self.by_name["shadow"]["z"], 9.5)
        c1 = self.by_name["c1"]
        self.assertEqual(c1["z_source"], "ground")
        self.assertEqual(c1["z"], c1["ground"])
        lobby = self.by_name["lobby"]
        self.assertGreater(lobby["z"], 25.0)  # on the mesa

    def test_z_from_must_name_one_placement(self):
        data = copy.deepcopy(POI_SPEC)
        data["pois"][3]["z_from"] = "nothing"
        with self.assertRaises(SpecError):
            tbuild.build_from_dict(data)
        data = copy.deepcopy(POI_SPEC)
        data["wmos"].append(dict(data["wmos"][0], position=[-420, -420, 20.0]))
        with self.assertRaises(SpecError):
            tbuild.build_from_dict(data)

    def test_poi_below_ground_warns(self):
        data = copy.deepcopy(POI_SPEC)
        data["pois"][5]["position"] = [-350, -150, -20.0]
        data["scatter"] = []
        result = tbuild.build_from_dict(data)
        self.assertTrue(any("'shadow' is" in w and "below the terrain" in w for w in result.manifest["warnings"]))

    def test_validator_reads_pois(self):
        rep = validate(self.out)
        self.assertEqual(rep.errors, [])
        self.assertEqual(rep.summary["pois_by_kind"]["crate"], 2)


class TestPoisJsonCorruption(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, cls.good = built("pois", POI_SPEC)

    def setUp(self):
        self.out = copy_output(self.good)
        with open(os.path.join(self.out, "pois.json"), encoding="ascii") as f:
            self.doc = json.load(f)

    def tearDown(self):
        shutil.rmtree(self.out, ignore_errors=True)

    def check(self, change, text):
        doc = copy.deepcopy(self.doc)
        change(doc)
        with open(os.path.join(self.out, "pois.json"), "w", encoding="ascii") as f:
            json.dump(doc, f)
        rep = validate(self.out)
        self.assertTrue(any(text in e for e in rep.errors), (text, rep.errors))

    def poi(self, doc, name):
        return next(p for p in doc["pois"] if p["name"] == name)

    def test_catches(self):
        self.check(lambda d: self.poi(d, "c1").update(param=5), "takes param")
        self.check(lambda d: self.poi(d, "final").update(weight=0), "needs an integer weight")
        self.check(lambda d: self.poi(d, "c1").update(weight=2), "only final_site")
        self.check(lambda d: self.poi(d, "c1").update(id=900), "is not a unique integer")
        self.check(lambda d: self.poi(d, "c1").update(name="lobby"), "used twice")
        self.check(lambda d: self.poi(d, "c1").update(x=50.0), "outside the map's tiles")
        self.check(lambda d: self.poi(d, "c1").update(z=self.poi(d, "c1")["ground"] - 3), "below the terrain")
        self.check(lambda d: d.update(map_directory="Other"), "is not this map")

    def test_final_site_reach(self):
        # The reach rule needs a block wider than 490 yd from its centre: check a 3 x 3 block's pois.json alone.
        doc = copy.deepcopy(self.doc)
        doc["map_directory"] = "Big"
        far = self.poi(doc, "final")
        far.update(x=200.0, y=200.0)  # 660 yd from the centre of tiles 31..33
        near = dict(far, name="near", id=999, x=-266.0, y=200.0)  # 466 yd
        doc["pois"].append(near)
        path = os.path.join(self.out, "big.json")
        with open(path, "w", encoding="ascii") as f:
            json.dump(doc, f)
        rep = tvalidate.Report()
        rep.main = {(tx, ty) for tx in (31, 32, 33) for ty in (31, 32, 33)}
        tvalidate._check_pois(rep, path, "Big")
        self.assertEqual(len([e for e in rep.errors if "final site" in e]), 1, rep.errors)
        self.assertIn("pois.json final", [e.split(":")[0] for e in rep.errors if "final site" in e])


class TestTextureOverflow(unittest.TestCase):
    def test_five_textures_in_a_chunk_warn(self):
        data = copy.deepcopy(POI_SPEC)
        data["textures"] += [{"name": "t4", "path": "Tileset\\X\\T4.blp"}, {"name": "t5", "path": "Tileset\\X\\T5.blp"}]
        data["texture_rules"] = [{"texture": t, "strength": 0.5, "shape": {"circle": {"center": [-200, -200],
                                                                                       "radius": 40}}}
                                 for t in ("dirt", "stone", "t4", "t5")]
        data["roads"] = []
        result = tbuild.build_from_dict(data)
        self.assertGreater(result.manifest["texture_overflow_chunks"], 0)
        self.assertTrue(any("more than 4 textures" in w for w in result.manifest["warnings"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
