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


class SeamFadeTests(unittest.TestCase):
    """An HD model whose charts end where a design does not: the design is faded out at that seam, not refused."""

    def setUp(self):
        import numpy as np
        from types import SimpleNamespace
        from mflib import atlas as AT, draw as DR
        self.np, self.DR = np, DR
        # a wrap seam: x = 100 on one side, x = 300 on the other, same 3D edge (rows 50-150)
        seam = AT.Seam("wrap", ((100.0, 50.0), (100.0, 150.0)), ((300.0, 50.0), (300.0, 150.0)))
        self.at = SimpleNamespace(seams=[seam])
        self.core = np.zeros((512, 512))
        self.core[40:160, 60:140] = 1.0   # ink across one side of the seam only: a hard line at x = 300's side
        self.halo = np.zeros((512, 512))

    def test_a_hard_seam_is_faded_under_the_limit(self):
        np, DR = self.np, self.DR
        before = DR.seam_report(self.at, np.clip(self.core, 0, 1))["max"]
        self.assertGreater(before, 0.1)
        core, halo, faded = DR.seam_fade(self.at, self.core, self.halo, ("wrap",), None, 0.1)
        self.assertGreaterEqual(faded, 1)
        self.assertLessEqual(DR.seam_report(self.at, np.clip(core + 0.45 * halo, 0, 1))["max"], 0.1)
        self.assertTrue((core[40:160, 60:80] > 0.9).any(), "ink away from the seam stays")

    def test_a_clean_seam_is_left_alone(self):
        np, DR = self.np, self.DR
        core = np.zeros((512, 512))
        core[400:450, 400:450] = 1.0  # nowhere near the seam
        out, _, faded = DR.seam_fade(self.at, core, self.halo, ("wrap",), None, 0.1)
        self.assertEqual(faded, 0)
        self.assertTrue(np.array_equal(out, core))


if __name__ == "__main__":
    unittest.main()
