"""blpconvert --format pal8 and pack_pal8: the palette BLP the character compositor pastes."""

import hashlib
import os
import struct
import unittest

import common
import numpy as np

import blpconvert
from rflib import blp as rfblp


def picture(w, h, colours=None, seed=1):
    rs = np.random.RandomState(seed)
    if colours:
        pal = rs.randint(0, 256, (colours, 3))
        idx = rs.randint(0, colours, (h, w))
        rgb = pal[idx]
    else:
        rgb = rs.randint(0, 256, (h, w, 3))
    a = rs.randint(0, 256, (h, w))
    return blpconvert.Image(w, h, bytearray(np.dstack([rgb, a]).astype(np.uint8).tobytes()))


class Pal8(unittest.TestCase):
    def write(self, img, mips=True):
        d = common.temp_dir("pal8")
        path = os.path.join(d, "t.blp")
        blpconvert.convert(img, path, "pal8", mips, jobs=1)
        with open(path, "rb") as f:
            return path, f.read()

    def test_header_and_levels(self):
        path, data = self.write(picture(64, 32, colours=40))
        magic, ver, enc, asz, pref, mips, w, h = struct.unpack_from("<4sIBBBBII", data)
        self.assertEqual((magic, ver, enc, asz, pref, mips, w, h), (b"BLP2", 1, 1, 8, 8, 1, 64, 32))
        offs = struct.unpack_from("<16I", data, 0x14)
        sizes = struct.unpack_from("<16I", data, 0x54)
        self.assertEqual(sizes[:7], tuple(2 * max(1, 64 >> i) * max(1, 32 >> i) for i in range(7)))
        self.assertEqual(sizes[7], 0)
        self.assertEqual(offs[0], 0x494)
        self.assertEqual(blpconvert.check_blp(path)[2], [])
        info = rfblp.parse(data, "t")
        self.assertEqual((info.kind, info.alpha_size, len(info.levels), info.missing), ("palette", 8, 7, 0))

    def test_exact_colours_round_trip(self):
        img = picture(32, 32, colours=200, seed=3)
        _, data = self.write(img)
        w, h, px = rfblp.decode(data, "t")
        self.assertEqual(bytes(px), bytes(img.data))
        path, _ = self.write(img)
        self.assertEqual(bytes(blpconvert.decode_blp(path).data), bytes(img.data))

    def test_many_colours_and_numpy_path_agree(self):
        img = picture(64, 64, colours=None, seed=5)
        levels = blpconvert.build_mips(img, True)
        pal, idx = blpconvert.quantize_pal8(levels)
        self.assertLessEqual(len(pal), 256)
        missing = sorted({(img.data[o], img.data[o + 1], img.data[o + 2]) for o in range(0, len(img.data), 4)})[:500]
        fast = blpconvert._nearest_indices(pal, missing)
        slow = [blpconvert._nearest_index(pal, c) for c in missing]
        self.assertEqual(fast, slow)

    def test_deterministic(self):
        img = picture(128, 128, colours=None, seed=7)
        _, a = self.write(img)
        _, b = self.write(picture(128, 128, colours=None, seed=7))
        self.assertEqual(hashlib.sha1(a).hexdigest(), hashlib.sha1(b).hexdigest())

    def test_no_mips(self):
        path, data = self.write(picture(16, 16, colours=4), mips=False)
        self.assertEqual(struct.unpack_from("<B", data, 11)[0], 0)
        self.assertEqual(blpconvert.check_blp(path)[1], 1)

    def test_pack_rejects_what_the_client_rejects(self):
        lv = [bytes(max(1, 8 >> i) ** 2) for i in range(4)]
        ok = blpconvert.pack_pal8(8, 8, [(0, 0, 0)], lv, lv)
        self.assertEqual(ok[:4], b"BLP2")
        with self.assertRaises(ValueError):
            blpconvert.pack_pal8(8, 8, [(0, 0, 0)], lv[:3], lv[:3])  # a level missing
        with self.assertRaises(ValueError):
            blpconvert.pack_pal8(12, 8, [(0, 0, 0)], lv, lv)  # not a power of two
        bad = [bytes([5]) * len(x) for x in lv]
        with self.assertRaises(ValueError):
            blpconvert.pack_pal8(8, 8, [(0, 0, 0)], bad, lv)  # index past the palette
        with self.assertRaises(ValueError):
            blpconvert.pack_pal8(8, 8, [(0, 0, 0)] * 257, lv, lv)

    def test_cli(self):
        d = common.temp_dir("pal8cli")
        png = os.path.join(d, "in.png")
        img = picture(32, 16, colours=10)
        blpconvert.write_png(png, img)
        out = os.path.join(d, "out.blp")
        self.assertEqual(blpconvert.main([png, out, "--format", "pal8", "--jobs", "1"]), 0)
        self.assertEqual(blpconvert.main(["--info", out]), 0)


if __name__ == "__main__":
    unittest.main()
