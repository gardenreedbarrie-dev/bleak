"""The spell icons of section 5.7 (mflib/icons.py, `modelforge.py icons`): the SpellIcon table, the 64 x 64 DXT1
files with their full mip chain, full-bleed framing (the object inside the central 85 %), the 1-2 px darkened
edge, determinism, and the manifest's "icons" list. The model icons are rendered from the models built for this
run (MF_MODELS limits them); the painted ones always run. Drawn at 128 px here (256 in `modelforge.py icons`)."""

import json
import os
import unittest

import blpconvert as BC

import common as CM
from mflib import build as B
from mflib import icons as IC
from mflib import preview as P
from mflib import render as RD
from mflib import tex as T

SECTION_5_7 = [(19300, "Grinder"), (19301, "Espresso"), (19302, "Kettle"), (19303, "ColdBox"), (19304, "Blender"),
               (19305, "Shelf"), (19306, "Counter"), (19307, "Coffee"), (19308, "Tea"), (19309, "Shake"),
               (19310, "Shift"), (19311, "Tired"), (19312, "Crown"), (19313, "Speed")]
TEST_SIZE = 128


def _spec(name):
    return next(s for _i, n, s in IC.ICONS if n == name)


def _available():
    """{icon name: (models, textures)} for every icon this run can draw: the painted ones and those whose model
    is built in this run."""
    have = set(CM.tested_models())
    out = {}
    for _i, name, spec in IC.ICONS:
        if "model" in spec:
            if spec["model"] not in have:
                continue
            res = CM.built(spec["model"])
            out[name] = ({spec["model"]: P.load(res.m2)}, RD.TextureSet(os.path.join(CM.workdir(), "files")))
        else:
            out[name] = ({}, RD.TextureSet(os.path.join(CM.workdir(), "files")))
    return out


def _luma(img, x, y):
    i = y * img.w + x
    return 0.3 * img.r[i] + 0.59 * img.g[i] + 0.11 * img.b[i]


class Table(unittest.TestCase):
    def test_section_5_7_rows(self):
        self.assertEqual([(i, n) for i, n, _s in IC.ICONS], SECTION_5_7)
        self.assertEqual(list(IC.SPARE), list(range(19314, 19320)))
        for icon_id, name, _s in IC.ICONS:
            self.assertEqual(IC.client_path(name), "Interface\\Icons\\BH_Cafe_%s.blp" % name)

    def test_every_icon_has_one_source_and_a_background(self):
        from mflib import props as PR
        for _i, name, spec in IC.ICONS:
            with self.subTest(icon=name):
                self.assertEqual(sum(k in spec for k in ("model", "mesh", "paint")), 1)
                self.assertEqual(len(spec["bg"]), 2)
                if "model" in spec:
                    self.assertIn(spec["model"], PR.REGISTRY)
        self.assertEqual(IC.models_needed(), sorted({s["model"] for _i, _n, s in IC.ICONS if "model" in s}))


class Render(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.avail = _available()
        cls.done = {}
        for name, (models, tx) in cls.avail.items():
            cls.done[name] = IC.render_icon(name, models, tx, TEST_SIZE)

    def test_size_and_opaque(self):
        for name, (img, _bb) in self.done.items():
            with self.subTest(icon=name):
                self.assertEqual((img.w, img.h), (IC.SIZE, IC.SIZE))
                self.assertTrue(all(a >= 0.999 for a in img.a), "icons are opaque (DXT1, full bleed)")

    def test_content_inside_the_central_85_percent(self):
        lo, hi = TEST_SIZE * (1 - IC.FILL) / 2 - 2, TEST_SIZE * (1 + IC.FILL) / 2 + 2
        for name, (_img, bb) in self.done.items():
            spec = _spec(name)
            if spec.get("box") or spec.get("particles"):
                continue   # framed on part of a model (full bleed by design) or with a steam plume over the top
            with self.subTest(icon=name):
                self.assertIsNotNone(bb, "nothing drawn")
                x0, y0, x1, y1 = bb
                self.assertGreaterEqual(min(x0, y0), lo, bb)
                self.assertLessEqual(max(x1, y1), hi, bb)
                self.assertGreater(max(x1 - x0, y1 - y0), TEST_SIZE * 0.6, "the object fills the icon")

    def test_darkened_edge_and_not_flat(self):
        for name, (img, _bb) in self.done.items():
            with self.subTest(icon=name):
                edge = [_luma(img, x, 0) for x in range(2, IC.SIZE - 2)]
                inner = [_luma(img, x, 2) for x in range(2, IC.SIZE - 2)]
                self.assertLess(sum(edge), sum(inner) * 0.7)
                lum = [_luma(img, x, y) for y in range(8, 56, 4) for x in range(8, 56, 4)]
                self.assertGreater(max(lum) - min(lum), 0.2, "an object on its background, not a flat fill")

    def test_icons_differ(self):
        seen = {}
        for name, (img, _bb) in self.done.items():
            key = bytes(img.to_image().data)
            self.assertNotIn(key, seen, "%s looks exactly like %s" % (name, seen.get(key)))
            seen[key] = name

    def test_deterministic(self):
        for name in ("Crown", "Shift", "Speed"):
            a = IC.render_icon(name, {}, None, TEST_SIZE)[0].to_image().data
            self.assertEqual(a, self.done[name][0].to_image().data)

    def test_blp_dxt1_with_full_mips(self):
        out = os.path.join(CM.workdir(), "icons")
        for name in ("Crown", "Shift"):
            path = IC.write_icon(self.done[name][0], B.disk_path(out, IC.client_path(name)))
            h, levels, problems = BC.check_blp(path)
            self.assertEqual(problems, [])
            self.assertEqual((h["width"], h["height"], h["encoding"], h["alphaSize"]), (64, 64, 2, 0))
            self.assertEqual(h["preferredFormat"], BC.PIXEL_DXT1)
            self.assertEqual(levels, 7)
            self.assertEqual(sum(1 for s in h["sizes"] if s), 7)


class Edge(unittest.TestCase):
    def test_edge_rows(self):
        self.assertLessEqual(len(IC.EDGE), 2, "section 5.7: at most a 1-2 px darkened edge")
        img = IC._edge(T.Img(8, 8, (1.0, 1.0, 1.0, 1.0)))
        self.assertAlmostEqual(img.r[0], IC.EDGE[0])
        self.assertAlmostEqual(img.r[1 * 8 + 1], IC.EDGE[1])
        self.assertAlmostEqual(img.r[3 * 8 + 3], 1.0)


class Manifest(unittest.TestCase):
    def test_icons_are_kept_by_a_later_build(self):
        out = os.path.join(CM.workdir(), "icon_manifest")
        img = IC.render_icon("Speed", {}, None, TEST_SIZE)[0]
        cpath = IC.client_path("Speed")
        dpath = IC.write_icon(img, B.disk_path(out, cpath))
        B.write_manifest(out, [], [(cpath, dpath)], [{"id": 19313, "path": cpath}])
        B.write_manifest(out, [], [])     # a model build after `icons` keeps the icons
        with open(os.path.join(out, "manifest.json")) as f:
            man = json.load(f)
        self.assertEqual(man["icons"], [{"id": 19313, "path": cpath}])
        self.assertIn(cpath, man["files"])


if __name__ == "__main__":
    unittest.main()
