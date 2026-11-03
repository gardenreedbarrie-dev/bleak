"""The shared library the section 5.8.1 designs build on: materials, paint helpers, emblems, glyphs, line icons,
lettering, the chalkboard face, geometry helpers, part kits, emitter presets, non-square atlases, size rules and
the registry's naming."""

import math
import os
import unittest

import common as CM
from mflib import build as B
from mflib import emblem as E
from mflib import emitters as EM
from mflib import font as F
from mflib import geom as G
from mflib import kit as K
from mflib import m2write as W
from mflib import paint2d as P2
from mflib import props as PR
from mflib import sizes as SZ
from mflib import tex as T

NEW_GENERATORS = ["bone", "planks", "slabs", "slate", "bottle_glass", "frosted_glass", "glaze", "rope", "lacquer",
                  "fire_glow", "embers", "frost_rune", "beans", "shake", "cream", "coffee", "silver",
                  "hammered_iron"]


def outward(mesh):
    """Triangles whose face normal disagrees with their vertex normals (0 for a well-wound mesh)."""
    bad = 0
    for t in mesh.t:
        fn = G.norm(G.face_normal(mesh, t))
        vn = G.norm(G.add(G.add(mesh.n[t[0]], mesh.n[t[1]]), mesh.n[t[2]]))
        if G.dot(fn, vn) < 0.0:
            bad += 1
    return bad


class Materials(unittest.TestCase):
    def test_new_generators(self):
        for name in NEW_GENERATORS:
            with self.subTest(gen=name):
                self.assertIn(name, T.GENERATORS)
                img = getattr(T, name)(48, 48, 3, {})
                again = getattr(T, name)(48, 48, 3, {})
                self.assertEqual(img.r, again.r, "deterministic")
                self.assertTrue(all(0.0 <= v <= 1.5 for v in img.r + img.g + img.b))
                self.assertTrue(all(0.0 <= v <= 1.0 for v in img.a))
                self.assertGreater(max(img.r) - min(img.r) + max(img.g) - min(img.g), 0.02, "not flat")

    def test_low_frequency(self):
        """Nothing finer than 4 texels at mip 1 (section 5.5): neighbouring texels differ little on average."""
        for name in ("bone", "planks", "slabs", "slate", "lacquer", "hide", "glaze", "shake"):
            with self.subTest(gen=name):
                img = getattr(T, name)(64, 64, 5, {})
                diffs = [abs(img.r[i] - img.r[i + 1]) for i in range(len(img.r) - 1) if (i + 1) % 64]
                self.assertLess(sum(diffs) / len(diffs), 0.07)

    def test_bottle_glass_level(self):
        liquid = T.hexc("E0A030")
        below = T.g_bottle_glass(T.Ctx(0.135, 0.2, (0, 0, 0.1), (1, 0, 0), cw=0.3, ch=0.3), 1,
                                 {"liquid": liquid, "level_z": 0.2})
        above = T.g_bottle_glass(T.Ctx(0.135, 0.05, (0, 0, 0.25), (1, 0, 0), cw=0.3, ch=0.3), 1,
                                 {"liquid": liquid, "level_z": 0.2})
        self.assertGreaterEqual(below[3], 0.85)
        self.assertLess(above[3], 0.6)
        self.assertGreater(below[0], below[2], "the honey colour shows below the level")

    def test_coffee_heart(self):
        mid = T.Ctx(0.05, 0.05, (0, 0, 0), (0, 0, 1), cw=0.1, ch=0.1)
        plain = T.g_coffee(mid, 1, {})
        heart = T.g_coffee(mid, 1, {"heart": True})
        self.assertGreater(T.lum(heart), T.lum(plain) + 0.1, "a pale heart in the middle")

    def test_glows_carry_alpha(self):
        for name in ("fire_glow", "frost_rune"):
            img = getattr(T, name)(32, 32, 1, {})
            self.assertGreater(max(img.a), 0.9, name)
            self.assertLess(min(img.a), max(img.a), name)

    def test_paint_helpers(self):
        c = (0.5, 0.5, 0.5)
        self.assertEqual(T.rivet_dot(c, 0.05, 0.05, 0.012), c, "untouched outside the rivet")
        self.assertNotEqual(T.rivet_dot(c, -0.003, -0.003, 0.012), c)
        corner = T.Ctx(0.02, 0.02, (0, 0, 0), (1, 0, 0), cw=0.5, ch=0.3)
        self.assertNotEqual(T.frame_rivets(corner, c, 0.02, 0.1, 0.012), c, "a rivet in every corner")
        self.assertNotEqual(T.rivet_lines(T.Ctx(0.04, 0.1, cw=1, ch=1), c, rows=(0.1,), step=0.08), c)
        edge = T.Ctx(0.25, 0.025, (0, 0, 0), (1, 0, 0), cw=0.5, ch=0.3)
        marks = [T.stitches(T.Ctx(s / 100.0, 0.025, cw=0.5, ch=0.3), c, 0.025) != c for s in range(5, 45)]
        self.assertTrue(any(marks) and not all(marks), "dashes, not a solid line")
        self.assertAlmostEqual(T.edge_dist(edge), 0.025)
        self.assertEqual(T.ramp([(0.0, (0, 0, 0)), (1.0, (1, 1, 1))], 0.5), (0.5, 0.5, 0.5))

    def test_image_lowres_matches_image_from(self):
        a = T.image_from(T.g_slate, 32, 32, 2, {}, (0.5, 0.5))
        b = T.image_lowres(T.g_slate, 32, 32, 2, {}, (0.5, 0.5), 4)
        err = sum(abs(x - y) for x, y in zip(a.r, b.r)) / len(a.r)
        self.assertLess(err, 0.02)


class EmblemsAndGlyphs(unittest.TestCase):
    def test_tusk_crest_relief(self):
        img = E.render_relief("tusk_crest", 96, 96, P2.IRON_RELIEF)
        self.assertGreater(sum(img.a) / len(img.a), 0.25)
        m = E.silhouette("tusk_crest", 100, 100)
        self.assertGreater(m.get(15, 50), 0.5, "the left tusk")
        self.assertGreater(m.get(85, 50), 0.5, "the right tusk")
        self.assertGreater(m.get(50, 60), 0.5, "the cup")

    def test_syrup_glyphs(self):
        """Section 5.5.1: drop, flower, leaf, bean, berry, cinnamon stick, mint leaf, swirl (and the Orgrimmar
        cactus apple, the cream rosette), one per bottle in shelf order, each a big readable shape."""
        for g in ("drop", "flower", "leaf", "bean", "berry", "cinnamon", "mint", "swirl", "cactus", "cream"):
            self.assertIn(g, E.GLYPHS)
            self.assertGreater(E.silhouette(g, 64, 64).coverage(), 0.12, g)
        self.assertEqual([r[0] for r in E.SYRUPS], ["honey", "vanilla", "caramel", "cinnamon", "chocolate", "berry",
                                                    "mint", "cream"])
        for key, col, glyph, col2 in E.SYRUPS + E.SYRUPS_ORG:
            self.assertIn(glyph, E.GLYPHS)
        self.assertEqual(E.SYRUPS_ORG[5][1:], ("88C070", "cactus", "D46A8C"))

    def test_labels(self):
        band = T.hexc("7FD1B9")
        img = P2.label(64, 96, {"color": band, "glyph": "mint"})
        cols = {(round(img.r[i], 2), round(img.g[i], 2)) for i in range(len(img.r))}
        self.assertIn((round(band[0], 2), round(band[1], 2)), cols)
        self.assertGreater(len(cols), 20, "a glyph and its outline on the band")
        two = P2.label(64, 96, {"color": T.hexc("88C070"), "color2": T.hexc("D46A8C"), "glyph": "cactus"})
        self.assertGreater(two.r[90 * 64 + 2], two.g[90 * 64 + 2], "the lower half is the second colour")

    def test_line_icons(self):
        for name in ("coffee", "tea", "shake", "lion_head", "tusk_crest"):
            m = E.line_mask(name, 64, 64)
            self.assertTrue(0.04 < m.coverage() < 0.45, (name, m.coverage()))


class Lettering(unittest.TestCase):
    def test_lower_case(self):
        for ch in "abcdefghijklmnopqrstuvwxyzé":
            self.assertIn(ch, F.VECTOR_CHARSET)
            self.assertGreater(F.vector_mask(ch, 40).coverage(), 0.01, ch)

    def test_caps_masks_unchanged_and_descenders_get_room(self):
        """A text without descenders keeps its M1 mask size (EspressoSW's plate is golden); one with
        descenders is taller by the descent."""
        k = 20 / 100.0
        m = F.vector_mask("ROYAL BRASS", 20)
        self.assertEqual(m.h, math.ceil(20 + 2 * 16 * k))
        self.assertEqual(F.vector_mask("Roast", 20).h, m.h)
        self.assertEqual(F.vector_mask("Shakes, gyp", 20).h, math.ceil(20 + 2 * 16 * k + F.DESCENT * k))
        self.assertLess(F.fit_cap("Roasty", 4000, 100), F.fit_cap("Roast", 4000, 100) - 10.0)

    def test_squeeze(self):
        self.assertAlmostEqual(F.vector_measure("Tusk", 50, 0.7), F.vector_measure("Tusk", 50) * 0.7)
        self.assertLess(F.vector_mask("The Grinding", 40, squeeze=0.7).w, F.vector_mask("The Grinding", 40).w)

    def test_chalk_mask(self):
        img = T.Img(80, 40, (0.1, 0.1, 0.1, 1.0))
        F.chalk_mask(img, F.vector_mask("Tea", 24), 4, 4, 3)
        lit = [v for v in img.r if v > 0.5]
        self.assertTrue(lit, "chalk strokes")
        self.assertGreater(max(lit) - min(lit), 0.1, "grainy, not flat")

    def test_chalkboard_faces_fit(self):
        """Section 5.5.1: the three board faces fit (at half size, which is harder than the 512 x 1024 board),
        and a text that cannot fit raises."""
        for spec in ({"title": ["The Lion's", "Roast"], "emblem": "lion_head", "icons": ["coffee", "tea", "shake"],
                      "caption": "Coffee · Tea · Shakes", "lines": ["Fresh every morning"]},
                     {"title": ["The Grinding", "Tusk"], "icons": ["coffee", "tea", "shake"],
                      "caption": "Coffee · Tea · Shakes", "lines": ["Strong brews for strong backs."]}):
            img = P2.chalkboard_face(256, 512, 3, dict(spec, strict=True))
            self.assertEqual((img.w, img.h), (256, 512))
        P2.chalkboard_face(256, 256, 3, {"title": ["Welcome!"], "lines": ["by the Cathedral steps"], "strict": True})
        with self.assertRaises(ValueError):
            P2.chalkboard_face(64, 64, 1, {"title": ["Welcome!"], "lines": ["a line far too long for a tiny board"],
                                           "strict": True})

    def test_engraved_lines(self):
        img = T.Img(60, 30, (0.8, 0.6, 0.2, 1.0))
        P2.engraved_lines(img, 5, 5, 50, 20, 3, 2)
        dark = [i for i in range(len(img.r)) if img.r[i] < 0.4]
        self.assertTrue(dark)
        self.assertTrue(all(5 <= i % 60 < 56 and 5 <= i // 60 < 26 for i in dark), "inside the box")


class Geometry(unittest.TestCase):
    def test_new_shapes_are_outward(self):
        shapes = {
            "spike": G.spike((0, 0, 0), (1, 0, 1), 0.04, 0.1),
            "spike_ring": G.spike_ring((0, 0, 0.5), 0.2, 8, 0.03, 0.08, tilt=0.3),
            "spike_row": G.spike_row((0, -0.3, 0.5), (0, 0.3, 0.5), 6, (0, 0, 1), 0.035, 0.11),
            "horn": G.horn((0, 0, 0), (0.3, 0.2, 0.5), (1, 0, 0), 0.3, 0.06, 0.0),
            "wheel": G.wheel(0.1, 0.014, 6),
            "planks_y": G.planks(1.0, 0.3, 0.05, 3, "y"),
            "planks_z": G.planks(0.9, 0.05, 1.2, 4, "z"),
        }
        for name, m in shapes.items():
            with self.subTest(shape=name):
                self.assertGreater(G.signed_volume(m), 0)
                self.assertEqual(outward(m), 0)

    def test_planks_keep_their_size(self):
        (x0, y0, z0), (x1, y1, z1) = G.planks(1.0, 0.3, 0.05, 3, "y", wobble_amp=0.0).bounds()
        self.assertLessEqual(y1 - y0, 1.0 + 1e-9, "ragged ends only shorten the boards")
        self.assertGreater(y1 - y0, 0.95)

    def test_facing_matrices(self):
        for a, b in zip(G.mat_disc_facing((1, 0, 0)), G.MAT_DISC_FRONT):
            for u, v in zip(a, b):
                self.assertAlmostEqual(u, v, 9)
        self.assertEqual(G.mat_extrude_facing((1, 0, 0)), G.MAT_EXTRUDE_FRONT)
        # a gauge facing +Y: the dial's top (chart t = 0) is up, its right side (chart s) toward -X
        m = G.transform(G.cylinder(0.1, 0.02, 12, (False, True)), G.mat_disc_facing((0, 1, 0)))
        cap = [i for i in range(len(m.p)) if m.charts[m.c[i]].name == "cyl_top"]
        top = min(cap, key=lambda i: m.st[i][1])
        right = max(cap, key=lambda i: m.st[i][0])
        self.assertGreater(m.p[top][2], 0.05)
        self.assertLess(m.p[right][0], -0.05)
        self.assertTrue(all(m.n[i][1] > 0.99 for i in cap))

    def test_disc_chart(self):
        d = G.disc(0.05, 8, 0.1)
        self.assertEqual(len(d.charts), 1)
        front = max(range(len(d.p)), key=lambda i: d.p[i][0])
        self.assertGreater(d.st[front][1], 0.09, "the model's front is at the chart's bottom")
        self.assertTrue(all(n == (0.0, 0.0, 1.0) for n in d.n))


class Hulls(unittest.TestCase):
    def test_hulls_closed_and_outward(self):
        hulls = {"box": G.hull_box(0.5, 0.4, 0.8, 0.1, 0.0, 0.2), "gable": G.hull_gable(1.3, 0.7, 0.45, 0.9),
                 "cylinder": G.hull_cylinder(0.05, 3.0, 0.3, -0.2, 0.0, 8),
                 "merged": G.merge_hulls(G.hull_box(1, 1, 1), G.hull_cylinder(0.07, 1.7, 0.2))}
        for name, (pos, tris) in hulls.items():
            with self.subTest(hull=name):
                m = G.Mesh()
                m.p, m.t = list(pos), list(tris)
                self.assertGreater(G.signed_volume(m), 0)
                self.assertEqual(len(B.hull_normals(pos, tris)), len(tris))
        pos, tris = G.hull_gable(1.3, 0.7, 0.45, 0.9)
        for n, t in zip(B.hull_normals(pos, tris), tris):
            if min(pos[i][2] for i in t) > 0.4:
                self.assertLess(n[2], 0.6428, "the roof is too steep to stand on")
        self.assertEqual(len(G.hull_cylinder(0.05, 3.0)[1]), 28)


class Kits(unittest.TestCase):
    def test_closed_parts_are_outward(self):
        parts = []
        c = K.cup(0.07, 0.1, 0.11)
        parts += [("cup", c["cup"]), ("saucer", c["saucer"]), ("handle", c["handle"])]
        mg = K.mug()
        parts += [("mug", mg["mug"]), ("mug handle", mg["handle"])]
        for key in K.BOTTLES:
            bt = K.bottle(key)
            parts += [("bottle " + key, bt["glass"]), ("cap " + key, bt["cap"])]
        j = K.jar()
        parts += [("jar contents", j["contents"]), ("jar lid", j["lid"])]
        kt = K.kettle()
        parts += [("kettle lid", kt["lid"]), ("kettle spout", kt["spout"]), ("kettle handle", kt["handle"])]
        bl = K.bell()
        parts += [("bell base", bl["base"]), ("bell dome", bl["dome"]), ("bell button", bl["button"])]
        for name, m in parts:
            with self.subTest(part=name):
                self.assertTrue(m.t)
                self.assertEqual(outward(m), 0)
                (x0, y0, z0), (x1, y1, z1) = m.bounds()
                self.assertGreaterEqual(max(x1 - x0, y1 - y0, z1 - z0), 0.06, "readable (section 5.8)")
        for key in ("cup", "saucer"):
            self.assertGreater(G.signed_volume(c[key]), 0, key)
        self.assertGreater(G.signed_volume(K.bottle("honey")["glass"]), 0)

    def test_bottles_differ(self):
        shapes = {tuple(p) for p, _band in K.BOTTLES.values()}
        self.assertGreaterEqual(len(shapes), 8, "each bottle a different shape (section 5.8.1)")
        for key, _c, glyph, _c2 in E.SYRUPS_ORG:
            self.assertIn(key, K.BOTTLES)

    def test_kettle_spout_tip(self):
        kt = K.kettle()
        tip = kt["at_spout"]
        (x0, y0, z0), (x1, y1, z1) = kt["spout"].bounds()
        self.assertAlmostEqual(tip[0], x1, delta=0.03)
        self.assertGreater(tip[2], kt["body"].bounds()[1][2] * 0.6)

    def test_canopy_two_shells(self):
        cn = K.canopy(1.4, 2.55, 3.1, 8)
        top, under = cn["top"], cn["under"]
        self.assertEqual(sorted({ch.name for ch in top.charts}), sorted("panel%d" % i for i in range(8)))
        self.assertEqual(sorted({ch.name for ch in under.charts}), sorted("under%d" % i for i in range(8)))
        self.assertTrue(all(G.face_normal(top, t)[2] > 0 for t in top.t), "the top faces up")
        self.assertTrue(all(G.face_normal(under, t)[2] < 0 for t in under.t), "the underside faces down")
        (x0, y0, z0), (x1, y1, z1) = top.bounds()
        self.assertAlmostEqual(x1 - x0, 2.8, delta=0.05)
        self.assertAlmostEqual(z0, 2.55 - 0.04, delta=0.05)
        org = K.canopy(1.4, 2.9, 3.3, 6, irregular=1.0, sag_points=[(0.8, 0), (-0.4, 0.7), (-0.4, -0.7)],
                       sag=0.08, seed=4)
        self.assertEqual(len(org["at_ribs"]), 6)

    def test_gauge_faces_its_direction(self):
        g = K.gauge((0.3, 0.2, 0.5), (1, 1, 0), 0.08)
        cap = [i for i in range(len(g["case"].p)) if g["case"].charts[g["case"].c[i]].name == "cyl_top"]
        n = g["case"].n[cap[0]]
        self.assertAlmostEqual(n[0], math.sqrt(0.5), 4)
        self.assertAlmostEqual(n[1], math.sqrt(0.5), 4)


class MoreHelpers(unittest.TestCase):
    def test_inset_panel(self):
        c = (0.5, 0.4, 0.3)
        mk = lambda s_, t_: T.Ctx(s_, t_, cw=0.5, ch=0.4)  # noqa: E731
        self.assertEqual(T.inset_panel(mk(0.25, 0.2), c, 0.05), c, "the panel's middle is untouched")
        upper = T.inset_panel(mk(0.25, 0.044), c, 0.05)
        lower = T.inset_panel(mk(0.25, 0.4 - 0.044), c, 0.05)
        self.assertLess(T.lum(upper), T.lum(c))
        self.assertGreater(T.lum(lower), T.lum(c))

    def test_gear_and_flutes(self):
        gear = G.extrude(G.gear_polygon(12, 0.12, 0.09), 0.03, 0.005)
        self.assertGreater(G.signed_volume(gear), 0)
        self.assertEqual(len(G.gear_polygon(12, 0.12, 0.09)), 48)
        glass = G.lathe([(0.0, 0.0), (0.05, 0.0), (0.08, 0.4), (0.0, 0.4)], 16)
        fl = G.flutes(glass, 8, 0.08)
        self.assertGreater(G.signed_volume(fl), 0)
        self.assertEqual(outward(fl), 0)
        r = [math.hypot(x, y) for x, y, z in fl.p if abs(z - 0.4) < 1e-6]
        self.assertGreater(max(r) - min(r), 0.008, "ribs")

    def test_exhaust(self):
        ex = K.exhaust((0.1, 0.2, 0.3), 0.35, 0.06, 6)
        self.assertAlmostEqual(ex["at_top"][2], 0.3 + 0.35 + 0.036, 3)
        for key in ("pipe", "mouth", "collar"):
            self.assertTrue(ex[key].t, key)
            self.assertEqual(outward(ex[key]), 0, key)
        bent = K.exhaust((0.0, 0.0, 0.0), 0.25, 0.04, 4, bend=(0.0, 0.2))
        self.assertGreater(bent["at_top"][1], 0.15, "it curves over sideways")

    def test_bottle_label_band(self):
        bt = K.bottle("cinnamon", 0.3)
        (x0, y0, z0), (x1, y1, z1) = bt["label"].bounds()
        b0, b1 = bt["band"]
        self.assertAlmostEqual(z0, b0, 6)
        self.assertAlmostEqual(z1, b1, 6)
        gx = bt["glass"].bounds()[1][0]
        self.assertGreater(x1, gx * 0.9, "the band sits on the wall")
        self.assertEqual(outward(bt["label"]), 0)

    def test_wrap_front(self):
        f = P2.wrap_front(lambda w, h: T.Img(w, h, (1.0, 0.0, 0.0, 1.0)), 0.3)
        img = f(100, 20)
        self.assertEqual(img.a[10 * 100 + 50], 1.0, "drawn at the front (the strip's middle)")
        self.assertEqual(img.a[10 * 100 + 5], 0.0, "nothing round the back")

    def test_tile_is_seamless(self):
        img = T.tile_image(T.g_wood, 64, 64, 3, {"kind": "walnut"}, (0.5, 0.5))
        across = sum(abs(img.r[y * 64] - img.r[y * 64 + 63]) for y in range(64)) / 64.0
        inside = sum(abs(img.r[y * 64 + 31] - img.r[y * 64 + 32]) for y in range(64)) / 64.0
        self.assertLess(across, inside * 2.0 + 0.02, "the right edge runs on into the left one")
        down = sum(abs(img.r[x] - img.r[63 * 64 + x]) for x in range(64)) / 64.0
        self.assertLess(down, 0.08)

    def test_tiled_part_builds(self):
        """PropDef.tiles: a repeating texture (the counters' 256² wrap), UVs beyond 1, wrap flags, no bake."""
        d = B.PropDef("TileTest")
        d.kind, d.size, d.budget, d.atlas = "test", (3.0, 0.5, 1.0), 200, {"atlas": 64}
        d.tiles = {"wood": {"paint": ("planks", {"kind": "dark"}), "size": 64, "yards": 1.0}}
        d.add(B.Part("front", G.box(3.0, 0.5, 1.0, faces="+x -x +y -y"), texture="wood"))
        d.add(B.Part("top", G.box(3.0, 0.5, 0.02, faces="+z", z0=1.0), paint=("marble", {})))
        res = B.build_prop(d, os.path.join(CM.workdir(), "tile"), 1.0, True, False, 1, False, lambda *_a: None)
        self.assertTrue(res.check[2]["ok"], res.check[1].items)
        us = [v[2][0] for v in res.check[0]["vertices"]]
        self.assertGreater(max(us), 2.5, "the 3 yd front repeats the 1 yd tile")
        flags = {t["path"].split("\\")[-1]: t["flags"] for t in res.check[0]["textures"]}
        self.assertEqual(flags["BH_Cafe_TileTest_Wood.blp"], 3)


class Emitters(unittest.TestCase):
    def test_presets_keep_the_contract(self):
        for name, fn in EM.PRESETS.items():
            with self.subTest(preset=name):
                pd = fn((0.1, 0.0, 0.5))
                p = W.Particle(pd.position, 0)
                for k, v in pd.overrides.items():
                    self.assertTrue(hasattr(p, k), k)
                    setattr(p, k, v)
                p.validate()
                self.assertTrue(p.flags & 0x20000)
                self.assertFalse(p.flags & 0x40000)
                self.assertEqual(p.emitter_type, 1)
                self.assertEqual((p.twinkle_fps, p.twinkle_onoff, p.twinkle_scale), (10.0, 1.0, (1.0, 1.0)))
                lo, hi = p.plume_box()
                self.assertTrue(all(lo[k] <= pd.position[k] <= hi[k] for k in range(3)))
        mist = EM.frost_mist((0, 0, 1.0)).overrides
        self.assertGreater(mist["gravity"], 0, "the mist sinks")
        self.assertLess(mist["speed"], 0.05)
        emb = EM.embers((0, 0, 0)).overrides
        self.assertEqual((emb["flags"], emb["blend"]), (0x20001, 4))
        self.assertEqual(EM.exhaust_smoke((0, 0, 0)).overrides["colors"][0], (90.0, 90.0, 90.0))
        self.assertEqual(EM.kettle_steam((0, 0, 0)).overrides["emission_rate"], 8.0)

    def test_presets_in_a_built_model(self):
        """Every preset written into a model passes m2check (plume inside the bounds included)."""
        d = B.PropDef("EmitterTest")
        d.kind, d.size, d.budget, d.atlas = "test", (0.3, 0.3, 0.3), 200, {"atlas": 64}
        d.add(B.Part("box", G.box(0.3, 0.3, 0.3), paint=("flat", {"color": (0.5, 0.5, 0.5)})))
        res = None
        for name, fn in EM.PRESETS.items():
            d.particles = [fn((0.0, 0.0, 0.3)), EM.steam((0.1, 0.0, 0.3))]
            res = B.build_prop(d, os.path.join(CM.workdir(), "emitters"), 1.0, False, True, 1, False,
                               lambda *_a: None)
            self.assertTrue(res.check[2]["ok"], (name, res.check[1].items))


class Atlases(unittest.TestCase):
    def test_non_square_texture_and_clamp_flags(self):
        """A chalkboard face gets its own 512 x 1024-style texture (here 64 x 128) with clamp flags."""
        d = B.PropDef("FaceTest")
        d.kind, d.size, d.budget = "test", (0.5, 0.1, 0.8), 200
        d.atlas = {"atlas": 64, "face": (64, 128)}
        d.tex_flags = {"face": 0}
        face = G.box(0.5, 0.1, 0.8, faces="+x")
        G.uv_region(face, (0, 0, 64, 128))
        d.add(B.Part("body", G.box(0.5, 0.1, 0.8, faces="-x +y -y +z -z"), paint=("flat", {"color": (0.4, 0.3, 0.2)})))
        d.add(B.Part("face", face, texture="face", paint=("slate", {}),
                     decals={"+x": lambda w, h: P2.chalkboard_face(w, h, 1, {"title": ["Hi"], "strict": False})}))
        res = B.build_prop(d, os.path.join(CM.workdir(), "face"), 1.0, False, False, 1, False, lambda *_a: None)
        self.assertTrue(res.check[2]["ok"], res.check[1].items)
        import blpconvert as BC
        sizes = {c.split("\\")[-1]: BC.check_blp(p)[0] for c, p in res.textures}
        self.assertEqual((sizes["BH_Cafe_FaceTest_Face.blp"]["width"], sizes["BH_Cafe_FaceTest_Face.blp"]["height"]),
                         (64, 128))
        flags = {t["path"].split("\\")[-1]: t["flags"] for t in res.check[0]["textures"]}
        self.assertEqual(flags["BH_Cafe_FaceTest_Face.blp"], 0)
        self.assertEqual(flags["BH_Cafe_FaceTest_Atlas.blp"], 3)


class SizeRules(unittest.TestCase):
    def _defn(self, kind="machine", size=(0.5, 0.5, 0.85), hull=True, h=0.85):
        d = B.PropDef("GrinderSW")
        d.display, d.kind, d.size = 19302, kind, size
        d.add(B.Part("body", G.box(0.5, 0.5, h), paint=("flat", {})))
        if hull:
            m = G.box(0.5, 0.5, h)
            d.collision = (m.p, m.t)
        return d

    def test_size_problems(self):
        self.assertEqual(SZ.size_problems(self._defn()), [])
        self.assertTrue(SZ.size_problems(self._defn(size=(0.5, 0.5, 0.9))), "declared size off the table")
        self.assertTrue(SZ.size_problems(self._defn(hull=False)), "a machine needs a hull")
        self.assertTrue(SZ.size_problems(self._defn(kind="table")), "a table prop has no hull")
        tall = self._defn(size=(0.5, 0.5, 0.85), h=0.97)
        tall.render_size = tall.collision_size = (0.5, 0.5, 0.97)
        self.assertTrue(any("height" in p for p in SZ.size_problems(tall)), "0.95 above the bar at most")

    def test_kinds(self):
        self.assertEqual(SZ.KINDS["parasol"]["collision_max"], 32)
        self.assertEqual(SZ.KINDS["table"]["collision_max"], 0)
        self.assertEqual(SZ.KINDS["counter"]["base_z"], 0.0)


class RegistryNames(unittest.TestCase):
    def test_module_name(self):
        self.assertEqual(PR.module_name("EspressoSW"), "espresso_sw")
        self.assertEqual(PR.module_name("KettleStoveOrg"), "kettle_stove_org")
        self.assertEqual(PR.module_name("BackBarSW"), "back_bar_sw")
        self.assertEqual(PR.module_name("TipJar"), "tip_jar")
        self.assertEqual(PR.module_name("Cube"), "cube")
        self.assertEqual(len({PR.module_name(n) for n in PR.CATALOGUE_NAMES}), len(PR.CATALOGUE_NAMES))


if __name__ == "__main__":
    unittest.main()
