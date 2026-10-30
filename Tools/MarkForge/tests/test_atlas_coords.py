"""The atlas of the tube body: islands, the crotch row, seams, keep-out zones; the charts and their landmarks."""

import math
import unittest

import common
import numpy as np

from mflib import atlas as A, draw as W


class Atlas(unittest.TestCase):
    def setUp(self):
        self.m, self.at, self.ch, self.eye, self.sep = common.tube()

    def test_islands_and_crotch(self):
        at = self.at
        self.assertGreater(at.valid.mean(), 0.8)
        self.assertTrue(abs(at.crotch - 253) <= 3, at.crotch)
        self.assertTrue((at.island[at.valid] > 0).all())
        self.assertTrue(at.ext.any())
        self.assertFalse((at.ext & at.valid).any())

    def test_wrap_seams_are_found_on_limbs_only(self):
        wraps = [s for s in self.at.seams if s.kind == "wrap"]
        self.assertGreater(len(wraps), 50)
        for s in wraps:
            for (u0, v0), (u1, v1) in (s.a, s.b):
                if u0 < 256:
                    self.assertLess(v0, 320)  # the arm
                else:
                    self.assertGreaterEqual(v0, self.at.crotch - 2)  # the legs
        # both ends of an arm row and of a leg row are one 3D point
        arm = [s for s in wraps if s.a[0][0] < 256]
        leg = [s for s in wraps if s.a[0][0] >= 256]
        self.assertTrue(arm and leg)

    def test_keepout_covers_eyes_and_mouth(self):
        k = self.at.keepout_parts
        self.assertGreater(k["eyes"].sum(), 50)
        self.assertGreater(k["mouth"].sum(), 20)
        self.assertIsNotNone(k.get("mouth_centre"))
        P = self.at.pos.copy()
        P[..., 1] = np.abs(P[..., 1])
        e = np.asarray(self.eye)
        # the head surface straight in front of and behind the eye centre (which sits inside the eye geometry)
        across = np.hypot(P[..., 1] - e[1], P[..., 2] - e[2])
        near = (across < 0.1 * self.sep) & (np.abs(P[..., 0] - e[0]) < 0.5 * self.sep) \
            & (self.at.island_ext == A.ISLAND_HEAD)
        self.assertTrue(near.any())
        self.assertTrue(self.at.keepout[near].all())

    def test_cut_distance_is_3d(self):
        cd = self.at.cut_dist
        self.assertEqual(cd.shape, (512, 512))
        # the tube's head meets no other island: its own open edges (the eye and mouth cuts) never fade it
        self.assertTrue((cd[self.at.island_ext == A.ISLAND_HEAD] == cd.max()).all())

    def test_a_face_line_fades_out_at_a_head_to_body_cut(self):
        """The real models' chin and neck seam: a cut whose sides are in the head and the body islands. A face line
        that reaches it fades out in 3D on the head side too, so the glow does not end in a hard line there."""
        import copy
        from mflib import draw as W
        at = copy.deepcopy(self.at)
        P = at.pos.copy()
        P[..., 1] = np.abs(P[..., 1])
        # the head side on the head island's lower border (the chin), the body side on the torso's top row
        seam = A.Seam("cut", ((70.0, 511.0), (96.0, 511.0)), ((257.0, 1.0), (283.0, 1.0)),
                      (P[510, 70].copy(), P[510, 96].copy()))
        at.seams.append(seam)
        at.cut_dist = A.cut_distance(at)
        self.assertLess(float(at.cut_dist[510, 83]), 3.0, "the head side is near the cut")
        self.assertEqual(float(at.cut_dist[400, 128]), 24.0, "the middle of the face is not")
        _, _, ch, _, _ = common.tube()
        fade, _, dead = W.fade_field(at, ch, None)
        line = np.zeros((512, 512))
        line[470:512, 76:91] = 1.0  # down the chin to the head island's border
        core, halo = W.design_fields(at, ch, line, np.zeros_like(line), fade, dead)
        glow = np.clip(core + 0.45 * halo, 0, 1)
        self.assertGreater(float(glow[492:500, 76:91].max()), 0.9, "the line is there above the seam")
        report = W.seam_report(at, glow, ("cut",))
        self.assertEqual(report["samples"], 3)
        self.assertLess(report["max"], 0.1, report)
        for side in (seam.a, seam.b):
            (u0, v0), (u1, v1) = side
            self.assertLess(W.bilinear(glow, (u0 + u1) / 2, (v0 + v1) / 2), 0.1, side)


class Charts(unittest.TestCase):
    def setUp(self):
        self.m, self.at, self.ch, self.eye, self.sep = common.tube()

    def test_landmarks_ordered(self):
        L = self.ch.landmarks
        self.assertEqual(sorted(L["arm"]), L["arm"])
        self.assertEqual(sorted(L["torso"]), L["torso"])
        self.assertEqual(sorted(L["leg"]), L["leg"])
        self.assertGreater(L["bu"], 0)
        self.assertAlmostEqual(L["torso"][3], L["leg"][0], places=6)

    def test_limb_charts_wrap_at_the_inner_line(self):
        ch = self.ch
        for name in ("arm", "leg"):
            r = ch.regions[name]
            ratio = r.U / r.period
            self.assertLessEqual(ratio.max(), 0.5 + 1e-6)
            self.assertGreaterEqual(ratio.min(), -0.5 - 1e-6)
            self.assertGreater(ratio.max(), 0.45)
            self.assertLess(ratio.min(), -0.45)

    def test_seam_sides_get_the_same_chart(self):
        """U/C and V on both sides of every wrap seam: one 3D point, one chart value (up to the half texel)."""
        ch = self.ch
        worst_v, worst_u = 0.0, 0.0
        for s in self.at.seams:
            if s.kind != "wrap":
                continue
            vals = []
            for (u0, v0), (u1, v1) in (s.a, s.b):
                x, y = int((u0 + u1) / 2), int((v0 + v1) / 2)
                x = min(max(x, 0), 511)
                if np.isnan(ch.U[y, x]):
                    continue
                vals.append((ch.U[y, x] / ch.C_tex[y, x], ch.V[y, x]))
            if len(vals) == 2:
                du = abs(((vals[0][0] - vals[1][0]) + 0.5) % 1.0 - 0.5)
                worst_u = max(worst_u, du)
                worst_v = max(worst_v, abs(vals[0][1] - vals[1][1]))
        self.assertLess(worst_u, 0.03)
        self.assertLess(worst_v, 0.02)

    def test_to_metres(self):
        ch = self.ch
        p = ch.to_metres("arm", [[0.0, 0.0], [2.0, 0.25]])
        self.assertAlmostEqual(p[0, 1], ch.arm_knots[0])
        self.assertAlmostEqual(p[1, 1], ch.arm_knots[2])
        self.assertAlmostEqual(p[1, 0], 0.25 * ch.ring_at("arm", ch.arm_knots[2]), places=6)
        f = ch.to_metres("head", [[0.5, 0.0]])
        self.assertAlmostEqual(f[0, 0], 0.5 * self.sep)

    def test_texel_size_is_symmetric_across_seams(self):
        ch = self.ch
        worst = 0.0
        for s in self.at.seams:
            if s.kind != "wrap":
                continue
            v = []
            for (u0, v0), (u1, v1) in (s.a, s.b):
                v.append(ch.texel_map[int((v0 + v1) / 2), min(511, int((u0 + u1) / 2))])
            worst = max(worst, abs(v[0] - v[1]) / max(v))
        self.assertLess(worst, 0.25)


class SeamReport(unittest.TestCase):
    def test_a_step_at_the_seam_is_caught(self):
        m, at, ch, eye, sep = common.tube()
        field = np.zeros((512, 512))
        field[:, :128] = 1.0  # the left half of the arm island only: its u=0 edge inked, the u=255 edge not
        rep = W.seam_report(at, field)
        self.assertGreater(rep["max"], 0.9)
        rep = W.seam_report(at, np.ones((512, 512)))
        self.assertEqual(rep["max"], 0.0)


if __name__ == "__main__":
    unittest.main()
