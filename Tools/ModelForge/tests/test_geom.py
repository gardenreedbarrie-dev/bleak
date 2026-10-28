"""Mesh library: outward winding, normals, charts, deformers, UV helpers (section 5.4)."""

import math
import unittest

import common  # noqa: F401  (sys.path)
from mflib import atlas as A
from mflib import geom as G


def closed_meshes():
    return {
        "box": G.box(1.0, 0.5, 0.3, 0.05),
        "box_sharp": G.box(1.0, 0.5, 0.3),
        "cylinder": G.cylinder(0.1, 0.3),
        "cone": G.cone(0.2, 0.05, 0.3),
        "sphere": G.sphere(0.2),
        "capsule": G.capsule(0.05, 0.3),
        "torus": G.torus(0.3, 0.05),
        "torus_elliptic": G.torus(0.3, 0.05, rz=0.03),
        "extrude_star": G.extrude(G.star_polygon(12, 0.1, 0.07), 0.05, 0.01),
        "sweep_capped": G.sweep([(0, 0, 0), (0, 0, 0.2), (0.1, 0, 0.3)], 0.03, caps=(True, True)),
        "lathe_capped": G.lathe([(0.2, 0), (0.2, 0.2), (0.15, 0.3), (0, 0.35)], cap_bottom=True),
        "dome": G.lathe([(0.24, 0)] + [(0.24 * math.cos(a), 0.12 * math.sin(a))
                                       for a in [k * math.pi / 8 for k in range(1, 5)]], cap_bottom=True),
    }


class Winding(unittest.TestCase):
    def test_closed_meshes_have_positive_volume(self):
        for name, m in closed_meshes().items():
            self.assertGreater(G.signed_volume(m), 0, name)

    def test_box_volume(self):
        self.assertAlmostEqual(G.signed_volume(G.box(1.0, 0.5, 0.3)), 0.15, 6)
        v = G.signed_volume(G.box(1.0, 0.5, 0.3, 0.05))
        self.assertTrue(0.140 < v < 0.150, v)

    def test_face_normals_agree_with_vertex_normals(self):
        for name, m in closed_meshes().items():
            bad = 0
            for t in m.t:
                fn = G.norm(G.face_normal(m, t))
                vn = G.norm(G.add(G.add(m.n[t[0]], m.n[t[1]]), m.n[t[2]]))
                if G.dot(fn, vn) < 0.0:
                    bad += 1
            self.assertEqual(bad, 0, name)

    def test_mirror_and_transform_keep_outward(self):
        m = G.box(1.0, 0.5, 0.3, 0.05)
        self.assertGreater(G.signed_volume(G.mirror_y(m)), 0)
        r = G.transform(m, G.mat_chain(G.mat_translate(1, 2, 3), G.mat_rot_z(0.7), G.mat_scale(1.0, 2.0, 0.5)))
        self.assertGreater(G.signed_volume(r), 0)

    def test_deformers_keep_outward(self):
        m = G.box(1.0, 0.5, 0.3, 0.05)
        for d in (G.taper(m, 0.08), G.lean(m, 0.1), G.wobble(m, 0.01, 3), G.bend(m, 0.3),
                  G.plank_edges(m, 2), G.sag(m, [(0.25, 0.5), (-0.25, -0.5)], 0.02)):
            self.assertGreater(G.signed_volume(d), 0)

    def test_wobble_keeps_seams_closed(self):
        """Vertices that share a position before the wobble (chart seams, hard edges) share it after."""
        m = G.cylinder(0.2, 0.4)
        w = G.wobble(m, 0.02, 5)
        before = {}
        for p in m.p:
            k = (round(p[0], 6), round(p[1], 6), round(p[2], 6))
            before[k] = before.get(k, 0) + 1
        moved = {}
        for p in w.p:
            k = (round(p[0], 6), round(p[1], 6), round(p[2], 6))
            moved[k] = moved.get(k, 0) + 1
        self.assertEqual(len(before), len(moved))
        self.assertGreater(G.signed_volume(w), 0)

    def test_degenerate_triangles_dropped(self):
        for name, m in closed_meshes().items():
            for t in m.t:
                self.assertGreater(G.length(G.face_normal(m, t)), 1e-12, name)


class Normals(unittest.TestCase):
    def test_unit_length(self):
        for name, m in closed_meshes().items():
            for n in m.n:
                self.assertAlmostEqual(G.length(n), 1.0, 4, name)

    def test_recompute_hard_and_smooth(self):
        cube = G.recompute_normals(G.box(1, 1, 1), 40.0)
        self.assertEqual(len(cube.p), 24, "a sharp cube keeps 4 vertices per face")
        cyl = G.recompute_normals(G.cylinder(0.3, 0.5, 16, False), 40.0)
        side = [n for n in cyl.n if abs(n[2]) < 1e-6]
        self.assertTrue(side, "cylinder sides stay smooth")


class Charts(unittest.TestCase):
    def test_st_inside_chart(self):
        for name, m in closed_meshes().items():
            for v in range(len(m.p)):
                ch = m.charts[m.c[v]]
                s, t = m.st[v]
                self.assertTrue(-1e-6 <= s <= ch.w + 1e-6 and -1e-6 <= t <= ch.h + 1e-6,
                                "%s vertex %d (%f, %f) outside %s %fx%f" % (name, v, s, t, ch.name, ch.w, ch.h))

    def test_box_face_orientation(self):
        """Seen from outside, s runs right and t down (texture rows top to bottom, UV origin top-left)."""
        m = G.box(1.0, 1.0, 1.0)
        for v in range(len(m.p)):
            ch = m.charts[m.c[v]]
            s, t = m.st[v]
            x, y, z = m.p[v]
            if ch.name == "+x":
                self.assertAlmostEqual(s, y + 0.5, 6)
                self.assertAlmostEqual(t, 1.0 - z, 6)
            if ch.name == "+z":
                self.assertAlmostEqual(s, y + 0.5, 6)
                self.assertAlmostEqual(t, x + 0.5, 6)

    def test_merge_and_uv_helpers(self):
        m = G.merge([G.box(0.2, 0.2, 0.2), G.cylinder(0.1, 0.2)])
        self.assertEqual(len(m.charts), 6 + 3)
        p = G.uv_planar(G.cylinder(0.1, 0.2), "x")
        self.assertEqual(len(p.charts), 1)
        b = G.uv_box(G.sphere(0.2))
        self.assertLessEqual(len(b.charts), 6)
        c = G.uv_cyl(G.cylinder(0.1, 0.2, caps=False))
        self.assertEqual(len(c.charts), 1)
        G.uv_region(p, (0, 0, 64, 64))
        self.assertEqual(p.charts[0].fixed, (0, 0, 64, 64))

    def test_default_sides(self):
        self.assertEqual(G.default_sides(0.02), 6)
        self.assertEqual(G.default_sides(0.05), 8)
        self.assertIn(G.default_sides(0.15), (12, 16))
        self.assertIn(G.default_sides(0.25), (12, 16))
        self.assertGreaterEqual(G.default_sides(0.4), 20)


class Packing(unittest.TestCase):
    def test_pack_unique_aligned_with_gutters(self):
        charts = [G.Chart(0.3, 0.2), G.Chart(0.1, 0.5), G.Chart(1.0, 0.1), G.Chart(0.05, 0.05)] * 5
        for size, gut in ((512, 8), (256, 4), (128, 2)):
            pl, dens = A.pack(charts, (size, size))
            self.assertGreater(dens, 0)
            rects = [(p.x, p.y, p.w, p.h) for p in pl]
            for x, y, w, h in rects:
                self.assertEqual(x % 4, 0)
                self.assertEqual(y % 4, 0)
                self.assertEqual(w % 4, 0)
                self.assertEqual(h % 4, 0)
                self.assertTrue(0 < x and x + w <= size and 0 < y and y + h <= size)
            for i, a in enumerate(rects):
                for b in rects[i + 1:]:
                    sep = max(b[0] - (a[0] + a[2]), a[0] - (b[0] + b[2]), b[1] - (a[1] + a[3]), a[1] - (b[1] + b[3]))
                    self.assertGreaterEqual(sep, gut, (a, b))

    def test_deterministic(self):
        charts = [G.Chart(0.3 + 0.01 * i, 0.2) for i in range(30)]
        a = [(p.x, p.y, p.w, p.h) for p in A.pack(charts)[0]]
        b = [(p.x, p.y, p.w, p.h) for p in A.pack(charts)[0]]
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
