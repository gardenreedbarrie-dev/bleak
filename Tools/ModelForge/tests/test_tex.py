"""Textures, lettering, emblems, gutters and mips (section 5.5)."""

import os
import unittest

import blpconvert as B

import common as CM
from mflib import atlas as A
from mflib import emblem as E
from mflib import font as F
from mflib import geom as G
from mflib import mips as MP
from mflib import paint2d as P2
from mflib import tex as T


class Noise(unittest.TestCase):
    def test_deterministic_and_bounded(self):
        vals = [T.fbm3(x * 0.37, x * 0.11, 0.5, 7) for x in range(200)]
        self.assertEqual(vals, [T.fbm3(x * 0.37, x * 0.11, 0.5, 7) for x in range(200)])
        self.assertTrue(all(0.0 <= v <= 1.0 for v in vals))
        self.assertNotEqual(T.noise3(0.3, 0.2, 0.1, 1), T.noise3(0.3, 0.2, 0.1, 2))

    def test_low_frequency(self):
        """Nothing finer than 4 texels at mip 1: neighbouring texels of a 64 px generator image differ little."""
        img = T.wood(64, 64, 3, {"kind": "walnut"})
        diffs = [abs(img.r[i] - img.r[i + 1]) for i in range(len(img.r) - 1) if (i + 1) % 64]
        self.assertLess(sum(diffs) / len(diffs), 0.05)

    def test_generators_produce_images(self):
        for fn in (T.brass, T.copper, T.iron, T.enamel, T.wood, T.marble, T.stone, T.leather, T.hide, T.ceramic,
                   T.clay, T.fabric_stripes, T.glass, T.frost, T.env_gradient, T.steam_puff, T.fire, T.soot,
                   T.brushed_metal, T.gauge, T.label):
            img = fn(32, 32, 1, {})
            self.assertEqual((img.w, img.h), (32, 32), fn.__name__)
            self.assertTrue(all(0.0 <= v <= 1.5 for v in img.r), fn.__name__)

    def test_shadows_cool_lights_warm(self):
        c = (0.5, 0.5, 0.5)
        d = T.light(c, 0.6)
        self.assertGreater(d[2], d[0], "shadows shift toward blue")
        l = T.light(c, 1.3)
        self.assertGreater(l[0], l[2], "lights shift warm")


class Lettering(unittest.TestCase):
    def test_pixel_glyph_coverage(self):
        for ch in F.PIXEL_CHARSET:
            self.assertIn(ch, F.PIXEL_GLYPHS, repr(ch))
            w, bits = F.pixel_bits(ch)
            self.assertEqual(len(bits), 9)
            self.assertTrue(any(any(r) for r in bits), repr(ch))
            self.assertLessEqual(w, 7)
        self.assertEqual(F.pixel_measure("A A")[0], 5 + 1 + 3 + 5, "1 px between glyphs, 3 px for a space")

    def test_vector_glyph_coverage(self):
        for ch in F.VECTOR_CHARSET:
            self.assertIn(ch, F.VECTOR_GLYPHS, repr(ch))
            m = F.vector_mask(ch, 40)
            self.assertGreater(m.coverage(), 0.01, repr(ch))

    def test_texts_fit_their_regions(self):
        """Every text the M1 models carry fits the decal it is painted into (section 5.5.1)."""
        from mflib.props import espresso_sw as ES
        defn = ES.build({})
        res = CM.built("EspressoSW")
        pl = None
        # the plate's front chart as packed in the real build
        plate = [p for p in defn.parts if p.name == "plate"][0]
        charts = []
        owners = []
        for pi, part in enumerate(defn.parts):
            if part.texture == "atlas":
                for ci, ch in enumerate(part.mesh.charts):
                    charts.append(ch)
                    owners.append((pi, ci))
        pl, _d = A.pack(charts, (512, 512))
        pi = defn.parts.index(plate)
        ci = [i for i, ch in enumerate(plate.mesh.charts) if ch.name == "extrude_front"][0]
        p = pl[owners.index((pi, ci))]
        self.assertGreaterEqual(min(p.w, p.h), 96, "the lion plate region (about 128 px, section 5.8.1)")
        img = P2.plate(p.w, p.h, {"emblem": "lion_head", "text": "ROYAL BRASS", "banner": 0.25})
        self.assertEqual((img.w, img.h), (p.w, p.h))
        cap = F.fit_cap("ROYAL BRASS", p.w * 0.8, p.h * 0.25 * 0.92, min_cap=4.0)
        self.assertGreater(cap, 4.0)
        self.assertTrue(res.check[2]["ok"])

    def test_text_that_does_not_fit_fails(self):
        with self.assertRaises(ValueError):
            F.fit_cap("TUSK-O-MATIC", 20, 12)


class Emblems(unittest.TestCase):
    def test_every_emblem_renders(self):
        for name in E.EMBLEMS:
            m = E.silhouette(name, 64, 64)
            self.assertGreater(m.coverage(), 0.08, name)
            img = E.render_relief(name, 48, 48, P2.GOLD_RELIEF)
            self.assertGreater(sum(img.a) / len(img.a), 0.05, name)


class Mips(unittest.TestCase):
    def _fringe(self, size=128):
        """A parasol-like scalloped fringe: solid cloth above, round scallops and thin tassels below."""
        img = B.Image(size, size)
        d = img.data
        for y in range(size):
            for x in range(size):
                o = 4 * (y * size + x)
                on = y < 56
                if not on and y < 88:
                    cx = (x // 32) * 32 + 16
                    on = (x - cx) ** 2 + (y - 56) ** 2 < 16 ** 2
                if not on and y < 110:
                    on = x % 16 in (7, 8) and y < 104
                d[o:o + 4] = bytes((200, 150, 60, 255 if on else 0))
        return img

    def test_cutout_coverage_preserved(self):
        """Cutout coverage at mip 3 stays within +-15 % of mip 0 (section 5.9)."""
        img = self._fringe()
        plain = B.build_mips(img, True)
        kept = MP.build_chain(img, cutout=True)
        c0 = MP.coverage(kept[0])
        self.assertGreater(c0, 0.2)
        self.assertLess(abs(MP.coverage(kept[3]) - c0) / c0, 0.15)
        self.assertLess(abs(MP.coverage(kept[3]) - c0), abs(MP.coverage(plain[3]) - c0),
                        "the box-filtered chain erodes the fringe more")

    def test_cutout_mask_leaves_shared_glass_alone(self):
        """A cutout grille sharing an atlas with opaque and glass islands: with the cutout mask only the grille is
        rescaled, so the glass keeps its alpha at every mip and the grille keeps its coverage."""
        n = 128
        img = B.Image(n, n)
        owner = [-1] * (n * n)
        mask = bytearray(n * n)
        for y in range(n):
            for x in range(n):
                i = y * n + x
                if x < 56:
                    rgba, o = (200, 100, 50, 255), 0                      # opaque
                elif 64 <= x < 92:
                    rgba, o = (180, 200, 220, 90), 1                      # glass
                elif x >= 100:
                    on = (x - 100) % 16 < 5 or y % 16 < 5
                    rgba, o = (60, 60, 60, 255 if on else 0), 2          # grille (cutout)
                else:
                    continue
                img.data[4 * i:4 * i + 4] = bytes(rgba)
                owner[i] = o
        filled = MP.dilate_islands(img, owner)
        for i, o in enumerate(filled):
            mask[i] = 1 if o == 2 else 0
        kept = MP.build_chain(B.Image(n, n, bytearray(img.data)), cutout=mask, alpha=True)
        whole = MP.build_chain(B.Image(n, n, bytearray(img.data)), cutout=True, alpha=True)

        def glass_alpha(lv):
            s = n // lv.width
            return lv.data[4 * ((64 // s) * lv.width + 78 // s) + 3]

        def grille_cov(lv):
            s = n // lv.width
            a = [lv.data[4 * (y * lv.width + x) + 3] for y in range(lv.height) for x in range(104 // s, lv.width)]
            return sum(1 for v in a if v >= MP.ALPHA_REF) / float(len(a))

        for li in range(1, 4):
            self.assertEqual(glass_alpha(kept[li]), 90, "glass alpha at mip %d" % li)
        self.assertTrue(any(glass_alpha(whole[li]) != 90 for li in range(1, 4)),
                        "rescaling the whole level changes the glass (the case the mask exists for)")
        c0 = grille_cov(kept[0])
        self.assertLess(abs(grille_cov(kept[3]) - c0) / c0, 0.15, "grille coverage at mip 3 (section 5.9)")
        self.assertLess(abs(grille_cov(kept[3]) - c0), abs(grille_cov(whole[3]) - c0),
                        "measured over the whole level, the opaque texels dilute the grille's correction")

    def test_gutters_keep_islands_apart_at_mip2(self):
        """No island's colour appears in another island's texels at mip 2."""
        charts = [G.Chart(0.2 + 0.03 * i, 0.15 + 0.02 * (i % 3)) for i in range(12)]
        pl, _d = A.pack(charts, (512, 512))
        img = B.Image(512, 512)
        owner = [-1] * (512 * 512)
        cols = [((37 * i) % 256, (91 * i) % 256, (151 * i) % 256) for i in range(1, 13)]
        for k, p in enumerate(pl):
            for y in range(p.y, p.y + p.h):
                for x in range(p.x, p.x + p.w):
                    o = 4 * (y * 512 + x)
                    img.data[o:o + 4] = bytes(cols[k] + (255,))
                    owner[y * 512 + x] = k
        MP.dilate_islands(img, owner)
        lv = B.build_mips(img, True)
        m2 = lv[2]
        for k, p in enumerate(pl):
            for y in range(p.y // 4, (p.y + p.h) // 4):
                for x in range(p.x // 4, (p.x + p.w) // 4):
                    o = 4 * (y * m2.width + x)
                    self.assertEqual(tuple(m2.data[o:o + 3]), cols[k], "island %d at mip 2 (%d, %d)" % (k, x, y))

    def test_sizes(self):
        MP.check_size(512, 512)
        MP.check_size(512, 1024)
        for w, h in ((300, 256), (384, 64), (512, 64)):
            with self.assertRaises(ValueError):
                MP.check_size(w, h)

    def test_blp_round_trip(self):
        d = CM.workdir()
        img = T.image_from(T.g_steam_puff, 32, 32, 3, {}).to_image()
        p = os.path.join(d, "puff.blp")
        MP.write(p, img, "dxt5")
        h, levels, problems = B.check_blp(p)
        self.assertEqual(problems, [])
        self.assertEqual(levels, 6)
        back = B.decode_blp(p)
        self.assertEqual((back.width, back.height), (32, 32))


class BuiltTextures(unittest.TestCase):
    def test_every_built_texture_is_valid(self):
        for name in ("Cube", "EspressoSW"):
            res = CM.built(name)
            for client, disk in res.textures:
                h, levels, problems = B.check_blp(disk)
                self.assertEqual(problems, [], client)
                self.assertTrue(B.is_pow2(h["width"]) and B.is_pow2(h["height"]), client)
                self.assertNotEqual(h["width"], 6 * h["height"], client)
                fmt = "dxt5" if h["preferredFormat"] == 7 else "dxt1"
                if "Steam" in client or "Fire" in client:
                    self.assertEqual(fmt, "dxt5", client)


if __name__ == "__main__":
    unittest.main()
