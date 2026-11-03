"""specs/royale_v1.json, the Bleakhold Royale v1 map (royale-spec.md 2.1-2.4), and its packaging config.

Builds the heights and the scatter once (no ADTs: the full build and validator run is the WP0 verification step).
"""

import json
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_terrain_support import TOOL_DIR  # noqa: E402

from terrain import build as tbuild  # noqa: E402
from terrain import coords  # noqa: E402
from terrain.spec import load_spec  # noqa: E402

SPEC = os.path.join(TOOL_DIR, "specs", "royale_v1.json")
CONFIG = os.path.join(TOOL_DIR, "bleakhold_royale.json")
C = (-266.6667, -266.6667)
FINAL_WEIGHTS = {"keep": 20, "mill": 6, "siege": 12, "crows_rise": 14, "caravan": 16, "mirefen": 14, "graves": 12,
                 "old_ford": 6}
LANDMARKS = {5201: (-266, -266, 88), 5202: (120, 80, 62), 5203: (180, -760, 54), 5204: (-620, -600, 40),
             5205: (-700, 60, 26), 5206: (220, -250, 60), 5207: (60, -420, 60), 5208: (-80, -120, 60),
             5209: (-520, -260, 70), 5210: (-480, 170, 60)}


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


class TestRoyaleV1(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = load_spec(SPEC)
        cls.ctx = tbuild.Context(cls.spec)
        cls.pois = cls.ctx.pois
        cls.by_kind = {}
        for p in cls.pois:
            cls.by_kind.setdefault(p["kind"], []).append(p)
        with open(CONFIG, encoding="utf-8") as f:
            cls.cfg = json.load(f)

    def test_poi_counts(self):
        counts = tbuild.poi_counts(self.pois)
        self.assertEqual(counts["crate:1"], 44)  # 30 at the sites + 14 by the roads
        self.assertEqual(counts["crate:2"], 6)
        self.assertEqual(counts["orb_shadow"], 2)
        self.assertEqual((counts["orb_buff:1"], counts["orb_buff:2"], counts["orb_buff:3"]), (3, 2, 3))
        self.assertEqual(counts["supply_site"], 6)
        self.assertEqual(counts["lobby"], 1)
        self.assertEqual(counts["landmark"], 10)
        self.assertEqual(counts["crossing"], 3)
        self.assertEqual(counts["final_site"], 8)
        self.assertEqual(len({p["id"] for p in self.pois}), len(self.pois))
        self.assertEqual(len([p for p in self.pois if p["name"].startswith("crate_roadside")]), 14)

    def test_landmarks_lobby_and_crossings(self):
        landmarks = {p["id"]: p for p in self.by_kind["landmark"]}
        self.assertEqual(set(landmarks), set(LANDMARKS))
        for pid, (x, y, r) in LANDMARKS.items():
            p = landmarks[pid]
            self.assertEqual((p["x"], p["y"], p["radius"]), (x, y, r), pid)
            self.assertTrue(p["title"])
        (lobby,) = self.by_kind["lobby"]
        self.assertEqual((lobby["id"], lobby["x"], lobby["y"], lobby["radius"]), (5213, 455, 455, 32))
        self.assertEqual({p["id"] for p in self.by_kind["crossing"]}, {5211, 5212, 5214})
        pit = next(p for p in self.by_kind["crossing"] if p["id"] == 5214)
        self.assertEqual((pit["x"], pit["y"], pit["facing"]), (150, -665, 103))
        self.assertEqual(pit["z_source"], "placement:pit bridge")

    def test_final_sites(self):
        weights = {}
        for p in self.by_kind["final_site"]:
            self.assertLessEqual(dist((p["x"], p["y"]), C), 490.0, p["name"])
            weights[p["name"][len("final_"):]] = p["weight"]
            ground = self.ctx.grid.ground_height(p["x"], p["y"])
            wet = [w for w in self.spec.water if w["shape"].contains(p["x"], p["y"]) and ground < w["height"]]
            if p["name"] != "final_old_ford":  # the ford is a wading crossing by design
                self.assertEqual(wet, [], p["name"])
        self.assertEqual(weights, FINAL_WEIGHTS)
        # Farm, Pit and Shrine are never final (early game only).
        for pid in (5202, 5203, 5205):
            x, y, r = LANDMARKS[pid]
            self.assertFalse(any(dist((p["x"], p["y"]), (x, y)) < r + 35 for p in self.by_kind["final_site"]))

    def test_final_site_cover_kit(self):
        placed = [(p.world[0], p.world[1]) for p in self.ctx.doodads + self.ctx.wmos]
        for p in self.by_kind["final_site"]:
            near = sum(1 for q in placed if dist(q, (p["x"], p["y"])) <= 40.0)
            self.assertGreaterEqual(near, 6, p["name"])

    def test_orbs_and_crates(self):
        shadow = sorted((p["x"], p["y"]) for p in self.by_kind["orb_shadow"])
        self.assertEqual(shadow, [(-712, 48), (-266, -266)])
        in_wmo = [p for p in self.by_kind["crate"] if p["z_source"].startswith("placement:")]
        self.assertGreaterEqual(len(in_wmo), 10)
        for p in in_wmo:
            self.assertGreaterEqual(p["z"], p["ground"] - 0.25, p["name"])
        crates = self.by_kind["crate"]
        for i, a in enumerate(crates):
            for b in crates[i + 1:]:
                self.assertGreater(dist((a["x"], a["y"]), (b["x"], b["y"])), 8.0, (a["name"], b["name"]))
        for p in crates + self.by_kind["supply_site"]:
            self.assertLessEqual(abs(p["x"] - C[0]), 730.0, p["name"])  # inside Bounds.HalfSize 750 - 20
            self.assertLessEqual(abs(p["y"] - C[1]), 730.0, p["name"])

    def test_supply_sites(self):
        sites = sorted((p["x"], p["y"]) for p in self.by_kind["supply_site"])
        self.assertEqual(sites, sorted([(-80, -180), (380, -300), (-300, 200), (300, -450), (-950, -250),
                                        (-850, -820)]))
        for p in self.by_kind["supply_site"]:
            self.assertFalse(any(w["shape"].contains(p["x"], p["y"]) and p["ground"] < w["height"]
                                 for w in self.spec.water), p["name"])  # on dry land

    def test_doodad_floor_and_scatter(self):
        self.assertGreaterEqual(len(self.ctx.doodads), 600)
        self.assertGreaterEqual(sum(s["placed"] for s in self.ctx.scatter_stats), 400)
        names = {s["name"] for s in self.ctx.scatter_stats}
        for group in ("cover_trees", "cover_rocks", "cover_brush", "farm_corn", "mill_pines"):
            self.assertIn(group, names)
        self.assertEqual(next(s for s in self.ctx.scatter_stats if s["name"] == "mill_pines")["placed"], 25)

    def test_overlook_mesa(self):
        grid = self.ctx.grid
        top = grid.ground_height(455, 455)
        for ang in range(0, 360, 30):
            ax, ay = 455 + 31 * coords.dcos(ang), 455 + 31 * coords.dsin(ang)
            bx, by = 455 + 42 * coords.dcos(ang), 455 + 42 * coords.dsin(ang)
            self.assertAlmostEqual(grid.ground_height(ax, ay), top, delta=1.0)
            self.assertGreater(top - grid.ground_height(bx, by), 18.0, ang)  # a cliff all round
        walls = [p for p in self.ctx.doodads if p.label.startswith("overlook wall")]
        self.assertEqual(len(walls), 16)
        self.assertTrue(all(p.model.endswith("CollisionWallPvP01.m2") for p in walls))

    def test_dressing_from_the_look_brief(self):
        models = {p.model.rsplit("\\", 1)[-1].lower() for p in self.ctx.doodads + self.ctx.wmos}
        for name in ("ruinedfountain.m2", "humanbraziercorrupt.m2", "stratholmesmokeemitter.m2", "silo.wmo",
                     "alteracwatertower.m2", "corncropdead.m2", "goldmine.m2", "goldminetracks.m2",
                     "duskwoodabandoned_lumbermill.wmo", "gh_trapperbuilding_01.wmo", "grizzlyhills_tree01.m2",
                     "uthershrine.wmo", "o_crystal_large.m2", "sc_castingcircle_01.m2", "gh_trappertower_01.wmo",
                     "arcoftriumphplagued01.m2", "dustwallowgroundfog.m2", "arathistonebridge01.wmo",
                     "collisionwallpvp01.m2", "bonfirenorthrend_01.m2", "hu_tent01.m2"):
            self.assertIn(name, models)
        self.assertNotIn("mausoleumactive.wmo", models)  # removed from the Pit
        bridge = next(p for p in self.ctx.wmos if p.label == "pit bridge")
        self.assertEqual(bridge.rotation, (0.0, 283.0, 0.0))  # facing 103

    def test_roads_and_textures(self):
        self.assertGreaterEqual(len(self.spec.roads), 6)
        for road in self.spec.roads:
            self.assertTrue(6.0 <= road["width"] <= 8.0, road["name"])
            self.assertEqual(road["fade"], 4.0)
            self.assertEqual(self.spec.textures[road["texture"]].name, "dirt")
        self.assertEqual([t.name for t in self.spec.textures[:3]], ["grass", "dirt", "rock"])
        self.assertLessEqual(len(self.spec.textures), 6)

    def test_subzones_and_atmosphere_config(self):
        zone = self.cfg["zone"]
        self.assertEqual(zone["template"], 10)
        self.assertEqual(self.cfg["map"]["time_of_day_override"], 1050)
        subzones = {z["id"]: z["name"] for z in zone["subzones"]}
        self.assertEqual(sorted(subzones), list(range(5201, 5214)))
        self.assertEqual(subzones[5213], "The Overlook")
        self.assertEqual({a for a, _ in self.spec.areas}, set(subzones))
        for flag in ("ALLOW_DUELS", "INSIDE", "SANCTUARY", "OUTLAND", "NEED_FLY"):
            self.assertIn(flag, zone["clear_flags"])
        self.assertEqual(self.cfg["archives"]["marker_texture"], "Interface\\Bleakhold\\Royale\\Marker.blp")
        titles = {p["id"]: p["title"] for p in self.pois if p["id"] in subzones}
        for pid, title in titles.items():
            self.assertEqual(title, subzones[pid], pid)


if __name__ == "__main__":
    unittest.main(verbosity=2)
