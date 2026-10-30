"""Eye sprites (alpha, size and encoding kept, hue taken) and the garment mask (cloth found, union of colours)."""

import colorsys
import os
import unittest

import common
import numpy as np

from mflib import archive as AR, atlas as A, eyes as E


class Eyes(unittest.TestCase):
    def test_recolour_keeps_layout(self):
        src = E.synthetic_source()
        info = AR.blp_info(src)
        out = E.sprite_blp(src, "#FF3B1E")
        oi = AR.blp_info(out)
        for k in ("width", "height", "encoding", "preferred", "alpha"):
            self.assertEqual(info[k], oi[k], k)
        a_src = AR.decode_blp(src)[..., 3].astype(int)
        a_out = AR.decode_blp(out)[..., 3].astype(int)
        self.assertLessEqual(int(np.abs(a_src - a_out).max()), 4)  # DXT5 alpha re-encoded: within its steps
        rgba = E.recolour(AR.decode_blp(src), "#FF3B1E")
        self.assertTrue(np.array_equal(rgba[..., 3], AR.decode_blp(src)[..., 3]))  # before encoding: exact

    def test_hue(self):
        src = AR.decode_blp(E.synthetic_source())
        for hexc in ("#FF3B1E", "#4FB0FF", "#7CFF3A", "#B06CFF"):
            out = E.recolour(src, hexc).astype(float) / 255
            ring = (src[..., 3] > 60) & (src[..., 3] < 200)
            mean = out[ring][:, :3].mean(0)
            want = [int(hexc[i:i + 2], 16) / 255 for i in (1, 3, 5)]
            h1 = colorsys.rgb_to_hsv(*mean)[0]
            h2 = colorsys.rgb_to_hsv(*want)[0]
            self.assertLess(min(abs(h1 - h2), 1 - abs(h1 - h2)), 0.04, hexc)


class Garment(unittest.TestCase):
    def test_cloth_is_found_and_a_tone_shift_is_not(self):
        skin = common.skin_picture((200, 160, 140), 1)[0:128, 256:512]
        uw = skin.copy()
        uw[30:60, 40:200] = (90, 30, 30)
        g, thr = A.garment_from(np.dstack([uw, np.full(uw.shape[:2], 255)]), np.dstack([skin, np.full(uw.shape[:2], 255)]))
        self.assertTrue(g[35:55, 45:195].all())
        self.assertFalse(g[90:120, :].any())
        shifted = np.clip(skin.astype(int) + 30, 0, 255).astype(np.uint8)
        g2, _ = A.garment_from(np.dstack([shifted, np.full(uw.shape[:2], 255)]), np.dstack([skin, np.full(uw.shape[:2], 255)]))
        self.assertLess(g2.mean(), 0.02)

    @staticmethod
    def opaque(rgb):
        return np.dstack([rgb, np.full(rgb.shape[:2], 255, np.uint8)])

    def test_cloth_over_more_than_half_the_section_is_found(self):
        # shorts over 60% of the section: the median is a cloth value, so a threshold over the whole section misses it
        skin = common.skin_picture((200, 160, 140), 1)[0:128, 256:512]
        uw = skin.copy()
        cloth = np.zeros(skin.shape[:2], bool)
        cloth[:, :int(0.6 * skin.shape[1])] = True
        uw[cloth] = (90, 30, 30)
        g, thr = A.garment_from(self.opaque(uw), self.opaque(skin))
        self.assertGreaterEqual(float(g[cloth].mean()), 0.95, thr)
        self.assertLess(thr, 60)
        self.assertLess(float(g[:, int(0.6 * skin.shape[1]) + 4:].mean()), 0.02, "the bare skin stays free")
        ref = A.garment_reference_pct(self.opaque(uw), self.opaque(skin))
        self.assertGreater(100 * float(g.mean()), AR.GARMENT_GATE * ref, "the gate passes the found cloth")

    def test_a_stock_underwear_with_transparent_black_is_found(self):
        # the stock kind: layered over the skin, cloth opaque on 22% of the section, the rest transparent black
        skin = common.skin_picture((200, 160, 140), 1)[0:128, 256:512]
        uw = np.zeros(skin.shape[:2] + (4,), np.uint8)
        cloth = np.zeros(skin.shape[:2], bool)
        cloth[40:68, :] = True
        self.assertAlmostEqual(float(cloth.mean()), 0.22, delta=0.01)
        uw[cloth] = (60, 50, 140, 255)
        g, _ = A.garment_from(uw, self.opaque(skin))
        self.assertGreaterEqual(float(g[cloth].mean()), 0.95)
        self.assertFalse(g[:30].any() or g[80:].any(), "transparent texels are not cloth")

    def test_the_gate_fails_a_mask_that_lost_the_cloth(self):
        skin = common.skin_picture((200, 160, 140), 1)[0:128, 256:512]
        uw = skin.copy()
        uw[:, :180] = (90, 30, 30)
        ref = A.garment_reference_pct(self.opaque(uw), self.opaque(skin))
        self.assertGreater(ref, 60)
        shifted = np.clip(skin.astype(int) + 30, 0, 255).astype(np.uint8)
        self.assertLess(A.garment_reference_pct(self.opaque(shifted), self.opaque(skin)), 2,
                        "a copy a shade off everywhere is no cloth for the gate either")
        report = [{"colour": 3, "pelvis": {"texture": "x.blp", "cover_pct": 0.0, "threshold": 125.0,
                                           "reference_pct": round(ref, 1), "short": True}}]
        problems = AR.garment_problems(report)
        self.assertEqual(len(problems), 1)
        self.assertIn("the cloth was not found", problems[0])

    def test_the_gate_fails_a_skin_or_underwear_that_was_not_read(self):
        report = [{"colour": 4, "skipped": "x.blp: missing"},
                  {"colour": 5, "skin": "s.blp", "pelvis": "skipped: p.blp: missing",
                   "torso": {"texture": "t.blp", "cover_pct": 30.0, "threshold": 40.0, "reference_pct": 31.0}}]
        problems = AR.garment_problems(report)
        self.assertEqual(len(problems), 2, problems)
        self.assertIn("colour 4: the skin was not read", problems[0])
        self.assertIn("colour 5: the pelvis underwear was not read", problems[1])

    def test_union_over_skin_colours(self):
        d = common.temp_dir("pkg")
        bands = common.write_package(d)
        src = AR.FolderSource(d)
        rows = AR.char_sections(src)
        union, rep = AR.garment_union(src, rows, 1, 0)
        self.assertEqual(len(rep), 2)
        for colour, (lo, hi) in bands.items():
            for sec in ("TU", "LU"):
                x, y, w, h = A.SECTIONS[sec]
                self.assertTrue(union[y + lo + 3:y + hi - 3, x + 35:x + 215].all(), (colour, sec))
        x, y, w, h = A.SECTIONS["TU"]
        self.assertFalse(union[y + 115:y + 128, x:x + w].any())

    def test_recoloured_underwear_is_paired_with_its_original(self):
        # raceforge.py skins puts the High Elf's skin and its opaque underwear on Character\BleakholdSkins\ names:
        # the cloth is found from the two originals (the recoloured underwear is not the original skin's copy)
        d = common.temp_dir("pkg-purple")
        common.write_package(d)
        src = AR.FolderSource(d)
        rows = AR.char_sections(src)
        plain, _ = AR.garment_union(src, rows, 1, 0)
        prefix = "Character\\BleakholdSkins\\HighElf\\0123456789\\"
        for r in rows:
            if AR._col(r, "baseSection", "section") in (0, 4):
                r["textures"] = [prefix + t if t else t for t in r["textures"]]
        union, rep = AR.garment_union(src, rows, 1, 0)
        self.assertFalse([e for e in rep if "skipped" in e or any("skipped" in str(v) for v in e.values())], rep)
        self.assertTrue(np.array_equal(union, plain))


if __name__ == "__main__":
    unittest.main()
