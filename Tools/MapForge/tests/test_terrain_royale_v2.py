"""Bleakhold Royale v2: the bright atmosphere config (bleakhold_royale_v2.json) and the demo spec that uses every v2
terrain feature (specs/royale_v2_demo.json), built once and checked end to end."""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_terrain_support import TOOL_DIR, built, validate  # noqa: E402
from test_terrain_water import emulate_ac, expected_level, sloped_cells  # noqa: E402

from dbc import config as configmod  # noqa: E402

DEMO = os.path.join(TOOL_DIR, "specs", "royale_v2_demo.json")


class TestAtmosphereConfig(unittest.TestCase):
    def test_bright_fixed_noon(self):
        cfg = configmod.load(os.path.join(TOOL_DIR, "bleakhold_royale_v2.json"))
        self.assertEqual(cfg.map.time_of_day_override, 720)  # a fixed noon: never dark
        self.assertEqual(cfg.light.params_from_light, 1690)  # Sholazar's whole light set
        self.assertIsNone(cfg.light.skybox)
        self.assertEqual(cfg.zone.template, 490)  # Un'Goro: brighter character lighting
        # Stranglethorn's jungle ambience and music over the template's own
        self.assertEqual((cfg.zone.ambience_id, cfg.zone.zone_music, cfg.zone.intro_sound), (32, 3, 0))

    def test_only_the_atmosphere_differs_from_v1(self):
        with open(os.path.join(TOOL_DIR, "bleakhold_royale.json"), encoding="utf-8") as f:
            v1 = json.load(f)
        with open(os.path.join(TOOL_DIR, "bleakhold_royale_v2.json"), encoding="utf-8") as f:
            v2 = json.load(f)
        self.assertEqual(set(v1), set(v2))
        for key in v1:
            if key in ("_comment", "light"):
                continue
            a, b = dict(v1[key]) if isinstance(v1[key], dict) else v1[key], v2[key]
            if key == "map":
                a = dict(a, time_of_day_override=720)
            if key == "archives":
                a = dict(a, marker_texture="Interface\\Bleakhold\\Royale\\MarkerV2.blp")
            if key == "zone":
                # the atmosphere (template and sounds) and the subzone names differ; the ids stay
                self.assertEqual([z["id"] for z in a["subzones"]], [z["id"] for z in b["subzones"]])
                a = dict(a, template=490, ambience_id=32, zone_music=3, intro_sound=0, subzones=b["subzones"])
            self.assertEqual(a, b, key)

    def test_own_patch_marker(self):
        # The addon's patch gate (Royale.lua R.MARKER) tests v2's marker, so a client that still has v1's patch-Q
        # (Marker.blp, v1 terrain under the same map id) cannot queue onto v2.
        v1 = configmod.load(os.path.join(TOOL_DIR, "bleakhold_royale.json"))
        v2 = configmod.load(os.path.join(TOOL_DIR, "bleakhold_royale_v2.json"))
        self.assertEqual(v1.archives.marker_texture, "Interface\\Bleakhold\\Royale\\Marker.blp")
        self.assertEqual(v2.archives.marker_texture, "Interface\\Bleakhold\\Royale\\MarkerV2.blp")
        lua = os.path.join(TOOL_DIR, "..", "..", "Interface", "AddOns", "Bleakhold", "Royale.lua")
        with open(lua, encoding="utf-8") as f:
            self.assertIn('R.MARKER = "Interface\\\\Bleakhold\\\\Royale\\\\MarkerV2"', f.read())


class TestDemoSpec(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(DEMO, encoding="utf-8") as f:
            cls.data = json.load(f)
        cls.result, cls.out = built("royale_v2_demo", cls.data)
        cls.ctx = cls.result.context
        cls.spec = cls.ctx.spec
        cls.manifest = cls.result.manifest

    def test_uses_every_v2_feature(self):
        self.assertEqual(len(self.spec.mountain_features()), 1)
        self.assertEqual(len(self.spec.lakes), 2)
        self.assertEqual(len(self.spec.rivers), 1)
        self.assertEqual(len(self.spec.rivers[0]["falls"]), 2)
        self.assertEqual(len(self.spec.generated), 4)  # two waterfalls and their splashes
        self.assertIsNotNone(self.spec.beaches)
        self.assertGreaterEqual(len(self.spec.assets), 3)
        self.assertTrue(all(not u.modern_used for u in self.spec.assets))  # offline: every one falls back

    def test_clean_build(self):
        self.assertEqual(self.manifest["warnings"], [])
        border = self.manifest["border"]
        self.assertTrue(border["closed"])
        self.assertFalse(border["mountains"]["past_cliff"])
        rep = validate(self.out)
        self.assertEqual(rep.errors, [])
        self.assertEqual(rep.warnings, [])

    def test_water_levels_cell_by_cell(self):
        rep = validate(self.out)
        levels = set()
        for (tx, ty), info in rep.adts.items():
            for (row, col), level in emulate_ac(info).items():
                self.assertEqual(level, expected_level(self.spec, ty * 256 + 2 * row, tx * 256 + 2 * col),
                                 (tx, ty, row, col))
                levels.add(level)
            # Both falls step inside a chunk: the cells below each lip stay dry rather than slope between levels.
            self.assertEqual(sloped_cells(info), [], (tx, ty))
        self.assertEqual(levels, {46.0, 24.0, 24.5, 4.0})

    def test_peaks_and_valley(self):
        lo, hi = self.manifest["height_range"]
        self.assertGreater(hi, 120.0)
        self.assertLess(hi, 160.0 + 15.0)
        self.assertLess(lo, 4.0)  # the lagoon floor


if __name__ == "__main__":
    unittest.main(verbosity=2)
