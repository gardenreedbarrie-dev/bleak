"""The build's gates on the tube body for all 48 designs: glow across wrap seams within 0.1, no ink in keep-out
zones or the garment at the 512, 256 and 128 levels, and the file rules of every mark and _Glow."""

import unittest

import common
import numpy as np

import markforge as MF
from mflib import designs as D, draw as W


class Gates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = common.prepared()
        cls.pal, cls.races = MF.load_data()

    def test_all_designs_pass(self):
        p = self.p
        worst = 0.0
        for rf, r in self.races.items():
            for d in r["designs"]["designs"]:
                core0, halo0 = D.paint_design(p.charts, d, "Female")
                core, halo = W.design_fields(p.atlas, p.charts, core0, halo0, p.fade, p.dead)
                glow = np.clip(core + 0.45 * halo, 0, 1)
                rep = W.seam_report(p.atlas, glow)
                worst = max(worst, rep["max"])
                self.assertLessEqual(rep["max"], MF.SEAM_LIMIT, f"{rf} {d['key']}: {rep}")
                for c in r["palette"]["colours"]:
                    look = W.compose(core, halo, c)
                    self.assertEqual(W.ink_inside(look, p.blocked), [0, 0, 0], f"{rf} {d['key']} {c['key']}")
        print(f"\n  worst wrap-seam glow difference on the tube body: {worst:.3f}")

    def test_files_follow_the_contract(self):
        p = self.p
        r = self.races["NightElf"]
        d = r["designs"]["designs"][0]
        core0, halo0 = D.paint_design(p.charts, d, "Female")
        core, halo = W.design_fields(p.atlas, p.charts, core0, halo0, p.fade, p.dead)
        glowing = W.compose(core, halo, r["palette"]["colours"][0])
        paint = W.compose(core, halo, r["palette"]["colours"][2])
        m, g = glowing.blp(False), glowing.blp(True)
        self.assertEqual(W.mark_problems(m, "mark"), [])
        self.assertEqual(W.glow_problems(m, g, "glow"), [])
        self.assertIsNone(paint.glow_palette)
        self.assertEqual(W.mark_problems(paint.blp(False), "paint"), [])
        self.assertEqual(len(m), 0x494 + sum(2 * (512 >> i) ** 2 for i in range(10)))
        # a glow whose alpha differs is caught
        bad = bytearray(g)
        bad[0x494 + 512 * 512 + 100] ^= 0xFF
        self.assertTrue(W.glow_problems(m, bytes(bad), "glow"))
        # the glow palette's peak channel is 255 (bloom catches it), the mark keeps the colour
        self.assertEqual(max(glowing.glow_palette[0]), 255)

    def test_fade_is_zero_in_blocked_and_dead_zones(self):
        p = self.p
        self.assertTrue((p.fade[p.blocked] == 0).all())
        self.assertTrue((p.fade[p.dead] == 0).all())
        self.assertTrue(p.dead[p.blocked].all())

    def test_minimum_line_width(self):
        """Every stroke is at least 2.5 local texels wide, so it survives the 256 bake."""
        p = self.p
        d = {"key": "Thin", "elements": [{"on": "arm", "kind": "line", "pts": [[0.5, 0.0], [1.5, 0.0]], "w": 0.001}]}
        core, _ = D.paint_design(p.charts, d, "Male")
        rows = (core > 0.5).sum(axis=1)
        self.assertGreaterEqual(int(rows[100]), 2)


if __name__ == "__main__":
    unittest.main()
