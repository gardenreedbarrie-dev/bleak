"""Drawing the emoji pictures: text emotes and Noto images (skipped without Pillow)."""

import os
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
TOOL_DIR = os.path.dirname(HERE)                          # Tools/EmojiForge
REPO = os.path.dirname(os.path.dirname(TOOL_DIR))
if TOOL_DIR not in sys.path:
    sys.path.insert(0, TOOL_DIR)
import emojiforge  # noqa: E402

try:
    from PIL import Image
except ImportError:
    Image = None


def opaque_bbox(img):
    return img.getchannel("A").point(lambda v: 255 if v == 255 else 0).getbbox()


@unittest.skipIf(Image is None, "needs Pillow")
class TextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cat = emojiforge.load_catalogue(emojiforge.CATALOGUE)
        cls.font = emojiforge.font_path(cls.cat)

    def draw(self, text):
        return emojiforge.draw_text(text, self.font, self.cat["font"]["fill"], self.cat["font"]["stroke"])

    def test_every_text_emote(self):
        texts = ["GLHF"] + [e["text"] for e in self.cat["emojis"] if "text" in e and e["text"] != "GLHF"]
        fill = emojiforge._rgba(self.cat["font"]["fill"])
        for text in texts:
            with self.subTest(text=text):
                img = self.draw(text)
                self.assertEqual((img.mode, img.size), ("RGBA", (256, 256)))
                for corner in ((0, 0), (255, 0), (0, 255), (255, 255)):
                    self.assertEqual(img.getpixel(corner)[3], 0)
                # Anything visible stays inside the Noto art box (room for Lanczos ringing), the opaque letters
                # inside the 12 px margin draw_text fits them into.
                left, top, right, bottom = img.getchannel("A").getbbox()
                self.assertTrue(left >= 8 and top >= 8 and right <= 248 and bottom <= 248, (left, top, right, bottom))
                left, top, right, bottom = opaque_bbox(img)
                self.assertTrue(left >= 12 and top >= 12 and right <= 244 and bottom <= 244, (left, top, right, bottom))
                # The letters are filled with the fill colour (the stroke is dark).
                near = sum(1 for p in img.getdata()
                           if p[3] == 255 and max(abs(a - b) for a, b in zip(p[:3], fill[:3])) <= 8)
                self.assertGreater(near, 2000)

    def test_fills_the_box(self):
        # The largest size that fits: one side of the opaque box reaches most of the 232 px space.
        for text in ("GG", "GLHF"):
            left, top, right, bottom = opaque_bbox(self.draw(text))
            self.assertGreater(max(right - left, bottom - top), 200, text)


@unittest.skipIf(Image is None, "needs Pillow")
class NotoTests(unittest.TestCase):
    def save(self, d, img, name="in.png"):
        path = os.path.join(d, name)
        img.save(path)
        return path

    def test_opaque_square(self):
        with tempfile.TemporaryDirectory() as d:
            out = emojiforge.prepare_noto(self.save(d, Image.new("RGBA", (512, 512), (200, 50, 50, 255))))
        self.assertEqual((out.mode, out.size), ("RGBA", (256, 256)))
        alpha = out.getchannel("A")
        self.assertEqual(alpha.getbbox(), (8, 8, 248, 248))  # an alpha-0 border exactly 8 px wide
        for x, y in ((8, 8), (247, 8), (8, 247), (247, 247), (128, 8)):
            self.assertGreater(alpha.getpixel((x, y)), 0)
        self.assertEqual(out.getpixel((128, 128)), (200, 50, 50, 255))

    def test_rgb_and_palette_become_rgba(self):
        with tempfile.TemporaryDirectory() as d:
            rgb = emojiforge.prepare_noto(self.save(d, Image.new("RGB", (512, 512), (10, 120, 30))))
            palette = Image.new("P", (512, 512), 0)
            palette.putpalette([10, 120, 30] + [0] * 765)
            pal = emojiforge.prepare_noto(self.save(d, palette, "p.png"))
        for out in (rgb, pal):
            self.assertEqual((out.mode, out.size), ("RGBA", (256, 256)))
            self.assertEqual(out.getpixel((128, 128)), (10, 120, 30, 255))
            self.assertEqual(out.getpixel((3, 3))[3], 0)

    def test_wrong_size(self):
        with tempfile.TemporaryDirectory() as d:
            path = self.save(d, Image.new("RGBA", (256, 256), (0, 0, 0, 255)))
            with self.assertRaises(ValueError):
                emojiforge.prepare_noto(path)

    def test_blp_round_trip(self):
        # What art writes: a 256x256 DXT5 BLP with all 9 levels that decodes to the picture.
        img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
        img.paste((40, 160, 220, 255), (64, 64, 192, 192))
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "Emoji000.blp")
            self.assertEqual(emojiforge.write_blp(img, path, jobs=1), [])
            header, levels, _ = emojiforge.bc.check_blp(path)
            decoded = emojiforge.bc.decode_blp(path, 0)
        self.assertEqual((header["encoding"], header["alphaSize"], header["preferredFormat"], levels), (2, 8, 7, 9))
        texel = lambda x, y: tuple(decoded.data[(y * 256 + x) * 4:(y * 256 + x) * 4 + 4])  # noqa: E731
        self.assertEqual(texel(0, 0)[3], 0)
        r, g, b, a = texel(128, 128)
        self.assertEqual(a, 255)
        self.assertTrue(abs(r - 40) <= 8 and abs(g - 160) <= 8 and abs(b - 220) <= 8, (r, g, b))


if __name__ == "__main__":
    unittest.main()
