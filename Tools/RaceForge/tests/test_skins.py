"""raceforge.py skins and install: the BLP recolouring of every format, the skin colours and their targets, the client's
archive order, the placement on made-up realms (one archive; an HD pack that replaces a texture, with and without a
pack archive above the realm's; CharSections in two archives), running again, a palette change, the way back, and
install (dry run, a linked destination, a destination that changed, --restore, update's output). Every texture, row
and archive here is made up (tests/synth_skins.py)."""

import contextlib
import hashlib
import io
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL_DIR = os.path.dirname(HERE)
TOOLS_DIR = os.path.dirname(TOOL_DIR)

for _path in (TOOL_DIR, os.path.join(TOOLS_DIR, "MpqPack")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import mpqpack  # noqa: E402

from rflib import blp, config as configmod, install, recolor, schema_access, skins  # noqa: E402
from rflib.dbc import DbcTable  # noqa: E402
from tests import synth_skins as ss  # noqa: E402

patches = skins.patches
CS = "DBFilesClient\\CharSections.dbc"
CR = "DBFilesClient\\ChrRaces.dbc"
HD_PACK = {"hd": ["Data/patch-[ABCDEGIMNPSU].MPQ", "Data/Patch-Y.MPQ"]}
TOOL = os.path.join(TOOL_DIR, "raceforge.py")
FEMALE_SKIN_0 = "Character\\BloodElf\\Female\\BloodElfFemaleS0V00C00_0.blp"


def run_tool(*args):
    return subprocess.run([sys.executable, "-I", TOOL, *args], capture_output=True, text=True)


def target_of(hex_colour: str) -> tuple[float, float, float]:
    L, C, h = recolor.lch(recolor.hex_to_oklab(hex_colour))
    return round(L, 6), round(C, 6), round(h, 4)


def fair_transform(target: str = "#846CAD", settings: dict | None = None) -> recolor.Transform:
    rgba = ss.skin_texture(32, 32, ss.SKIN, "body")
    settings = dict(recolor.DEFAULTS, **(settings or {}))
    return recolor.Transform(recolor.stats(32, 32, rgba, False, settings), target_of(target), settings)


def hue_of(rgb) -> float:
    return recolor.lch(recolor.srgb8_to_oklab(*rgb))[2]


def hue_gap(a: float, b: float) -> float:
    return abs(recolor.wrap_degrees(a - b))


def archive_names(path: str) -> list[str]:
    with mpqpack.MpqArchive(path) as archive:
        return archive.names()


def archive_read(path: str, name: str) -> bytes:
    with mpqpack.MpqArchive(path) as archive:
        return archive.read(name)


def sections_of(data: bytes) -> DbcTable:
    return DbcTable.from_bytes(data, schema_access.get("CharSections"))


def is_row(table: DbcTable, row: list[int], sex: int, section: int, colour: int) -> bool:
    found = (table.get(row, "sexID"), table.get(row, "baseSection"), table.get(row, "colorIndex"))
    return found == (sex, section, colour)


def names_of(table: DbcTable, row: list[int]) -> list[str]:
    return [table.get_str(row, f"textureName[{i}]") for i in range(3)]


# --- the BLP formats ---------------------------------------------------------------------------------------------


class BlpRecolourTests(unittest.TestCase):
    def setUp(self):
        self.t = fair_transform()
        self.target_hue = self.t.target[2]

    def assert_same_header(self, before: bytes, after: bytes, palette_too: bool = True):
        self.assertEqual(len(before), len(after))
        self.assertEqual(before[:blp.PALETTE_OFFSET], after[:blp.PALETTE_OFFSET])

        if palette_too:
            self.assertEqual(before[blp.PALETTE_OFFSET:blp.HEADER_SIZE], after[blp.PALETTE_OFFSET:blp.HEADER_SIZE])

    def skin_hues(self, rgba: bytes) -> list[float]:
        """Hues of the opaque, clearly coloured pixels."""
        out = []

        for o in range(0, len(rgba), 4):
            if rgba[o + 3] >= 128:
                L, C, h = recolor.lch(recolor.srgb8_to_oklab(*rgba[o:o + 3]))

                if C > 0.03 and 0.3 < L < 0.95:
                    out.append(h)

        return out

    def test_palette(self):
        # 8x8: shades of a fair skin, the eye's green and a grey-white, alpha 8 with a transparent edge
        colours = [tuple(int(c * f) for c in ss.SKIN) for f in (1.0, 0.95, 0.9, 0.85, 0.8, 0.75)]
        colours += [ss.GREEN, (226, 224, 218)]
        rgba = bytearray()

        for i in range(64):
            rgba += bytes(colours[i % len(colours)]) + bytes((0 if i % 9 == 0 else 255,))

        for alpha_size in (0, 1, 4, 8):
            data = ss.blp_palette(8, 8, rgba, alpha_size=alpha_size)
            new = blp.recolour(data, self.t, "test.blp")
            self.assert_same_header(data, new, palette_too=False)
            self.assertEqual(data[blp.HEADER_SIZE:], new[blp.HEADER_SIZE:], "the indices and the alpha stay")
            _, _, before = blp.decode(data, "test.blp")
            _, _, after = blp.decode(new, "test.blp")
            self.assertEqual(before[3::4], after[3::4], f"alpha {alpha_size} untouched")

            for o in range(0, len(before), 4):
                if tuple(before[o:o + 3]) == ss.GREEN:
                    self.assertEqual(tuple(after[o:o + 3]), ss.GREEN)
                elif tuple(before[o:o + 3]) in colours[:6]:
                    self.assertLess(hue_gap(hue_of(after[o:o + 3]), self.target_hue), 20)

    def test_bgra_every_level(self):
        rgba = ss.with_alpha_edge(ss.skin_texture(16, 16, ss.SKIN, "all"), 16, 16)
        data = ss.blp_bgra(16, 16, rgba)
        new = blp.recolour(data, self.t, "test.blp")
        self.assert_same_header(data, new)
        info = blp.parse(data, "test.blp")
        self.assertEqual(len(info.levels), 5)

        for level in info.levels:
            old_bytes = data[level.offset:level.offset + level.size]
            new_bytes = new[level.offset:level.offset + level.size]
            self.assertEqual(old_bytes[3::4], new_bytes[3::4], f"level {level.index}: alpha untouched")

            if level.width >= 4:
                self.assertNotEqual(old_bytes, new_bytes, f"level {level.index} recoloured")

        _, _, before = blp.decode(data, "test.blp")
        _, _, after = blp.decode(new, "test.blp")
        greens = [o for o in range(0, len(before), 4) if tuple(before[o:o + 3]) == ss.GREEN]
        self.assertTrue(greens)
        self.assertTrue(all(tuple(after[o:o + 3]) == ss.GREEN for o in greens), "the green iris keeps its colour")
        hues = self.skin_hues(after)
        self.assertGreater(len(hues), 100)
        self.assertLess(sorted(hue_gap(h, self.target_hue) for h in hues)[len(hues) // 2], 15)

    def dxt1(self, blocks: list[bytes]) -> tuple[bytes, bytes]:
        data = ss.blp_blocks(4 * len(blocks), 4, "DXT1", blocks)
        return data, blp.recolour(data, self.t, "test.blp")

    def block(self, data: bytes, i: int) -> tuple[int, int, int]:
        return struct.unpack_from("<HHI", data, blp.HEADER_SIZE + 8 * i)

    def texels(self, data: bytes, i: int) -> list[tuple]:
        w, h, rgba = blp.decode(data, "test.blp")
        return [tuple(rgba[4 * (y * w + 4 * i + x):4 * (y * w + 4 * i + x) + 4]) for y in range(4) for x in range(4)]

    def find_pair(self, flip: bool) -> tuple[int, int]:
        """Two 565 colours a > b whose order flips through the transform (flip) or that become one (neighbours: the
        transform darkens light skin, so neighbouring light colours can meet)."""
        skins = [ss.pack565(*c) for c in ((236, 196, 170), (232, 192, 164), (220, 176, 150), (200, 150, 120),
                                          (240, 200, 180), (250, 236, 226), (190, 190, 196), (180, 176, 184),
                                          (160, 150, 170), (150, 120, 100))]
        candidates = sorted({v + d for v in skins for d in range(-70, 71) if 0 <= v + d <= 0xFFFF})

        for a in candidates:
            for b in candidates:
                if a > b:
                    na, nb = self.t.c565(a), self.t.c565(b)

                    if (na < nb) if flip else (na == nb):
                        return a, b

        self.fail("no such pair among the candidates")

    def test_dxt1_four_colour_block(self):
        c0, c1 = ss.pack565(236, 196, 170), ss.pack565(170, 120, 96)
        self.assertGreater(c0, c1)
        indices = [0, 1, 2, 3] * 4
        data, new = self.dxt1([ss.dxt1_block(c0, c1, indices)])
        n0, n1, bits = self.block(new, 0)
        self.assertGreater(n0, n1, "still four-colour")
        self.assertEqual(bits, self.block(data, 0)[2])
        after = self.texels(new, 0)
        self.assertEqual(after[0][:3], blp.expand565(self.t.c565(c0)))
        self.assertEqual(after[1][:3], blp.expand565(self.t.c565(c1)))
        self.assertTrue(all(t[3] == 255 for t in after))
        self.assertLess(hue_gap(hue_of(after[0][:3]), self.target_hue), 20)

    def test_dxt1_three_colour_block_keeps_transparency(self):
        c0, c1 = ss.pack565(170, 120, 96), ss.pack565(236, 196, 170)
        self.assertLess(c0, c1)
        indices = [3, 0, 1, 2] * 4
        data, new = self.dxt1([ss.dxt1_block(c0, c1, indices)])
        n0, n1, _ = self.block(new, 0)
        self.assertLessEqual(n0, n1, "still three-colour")
        before, after = self.texels(data, 0), self.texels(new, 0)
        self.assertEqual([t[3] == 0 for t in before], [t[3] == 0 for t in after])
        self.assertEqual(sum(t[3] == 0 for t in after), 4)

    def test_dxt1_order_flip(self):
        a, b = self.find_pair(flip=True)
        indices = [0, 1, 2, 3, 3, 2, 1, 0, 0, 0, 1, 1, 2, 2, 3, 3]

        # four-colour mode (a > b): the endpoints swap, 0<->1 and 2<->3 follow; each texel shows what it showed
        data, new = self.dxt1([ss.dxt1_block(a, b, indices)])
        n0, n1, bits = self.block(new, 0)
        self.assertEqual((n0, n1), (self.t.c565(b), self.t.c565(a)))
        self.assertGreater(n0, n1)
        self.assertEqual([(bits >> (2 * k)) & 3 for k in range(16)], [i ^ 1 for i in indices])
        after = self.texels(new, 0)
        self.assertEqual({after[k][:3] for k in range(16) if indices[k] == 0}, {blp.expand565(self.t.c565(a))})
        self.assertEqual({after[k][:3] for k in range(16) if indices[k] == 1}, {blp.expand565(self.t.c565(b))})

        # three-colour mode (b < a as c0 < c1): 0<->1 swap, 2 and 3 (transparent) stay
        data, new = self.dxt1([ss.dxt1_block(b, a, indices)])
        n0, n1, bits = self.block(new, 0)
        self.assertLessEqual(n0, n1)
        self.assertEqual([(bits >> (2 * k)) & 3 for k in range(16)], [{0: 1, 1: 0}.get(i, i) for i in indices])
        after = self.texels(new, 0)
        self.assertEqual([t[3] == 0 for t in after], [i == 3 for i in indices])
        self.assertEqual({after[k][:3] for k in range(16) if indices[k] == 0}, {blp.expand565(self.t.c565(b))})

    def test_dxt1_endpoints_that_become_equal(self):
        a, b = self.find_pair(flip=False)
        indices = [3, 2, 1, 0] * 4
        _, new = self.dxt1([ss.dxt1_block(a, b, indices)])
        n0, n1, _ = self.block(new, 0)
        self.assertGreater(n0, n1, "a four-colour block stays four-colour (equal endpoints: index 3 transparent)")
        self.assertEqual(abs(n0 - n1), 1)
        self.assertIn(self.t.c565(a), (n0, n1))
        self.assertTrue(all(t[3] == 255 for t in self.texels(new, 0)))

    def test_dxt1_green_block_unchanged(self):
        c0, c1 = ss.pack565(*ss.GREEN), ss.pack565(28, 96, 38)
        block = ss.dxt1_block(max(c0, c1), min(c0, c1), [0, 1, 2, 3] * 4)
        data, new = self.dxt1([block])
        self.assertEqual(data, new)

    def test_dxt3_and_dxt5_keep_alpha_and_recolour_every_level(self):
        rgba = ss.with_alpha_edge(ss.skin_texture(16, 16, ss.SKIN, "upper"), 16, 16)

        for kind in ("DXT3", "DXT5"):
            data = ss.blp_dxt(16, 16, rgba, kind)
            new = blp.recolour(data, self.t, "test.blp")
            self.assert_same_header(data, new)
            info = blp.parse(data, "test.blp")
            self.assertEqual(info.kind, kind)

            for level in info.levels:
                for o in range(level.offset, level.offset + level.size, 16):
                    self.assertEqual(data[o:o + 8], new[o:o + 8], f"{kind} level {level.index}: alpha block untouched")

            smaller = info.levels[1].offset
            self.assertNotEqual(data[smaller:], new[smaller:], f"{kind}: the smaller levels too")
            _, _, before = blp.decode(data, "test.blp")
            _, _, after = blp.decode(new, "test.blp")
            self.assertEqual(before[3::4], after[3::4])
            hues = self.skin_hues(after)
            self.assertLess(sorted(hue_gap(h, self.target_hue) for h in hues)[len(hues) // 2], 20, kind)

    def test_unsupported_formats_name_the_texture(self):
        good = ss.blp_bgra(4, 4, bytes(64))

        def variant(**fields):
            header = list(ss.HEADER.unpack_from(good))
            names = ("magic", "version", "encoding", "alpha", "preferred", "mips", "width", "height")

            for key, value in fields.items():
                header[names.index(key)] = value

            return ss.HEADER.pack(*header) + good[ss.HEADER.size:]

        for data, text in ((variant(encoding=0), "JPEG"), (variant(magic=b"BLP1"), "BLP1"),
                           (variant(encoding=2, preferred=2), "preferredFormat 2"),
                           (variant(encoding=5), "unknown colorEncoding 5"), (variant(width=24, height=4), "cube map"),
                           (variant(version=2), "not a BLP2"), (good[:-8], "outside the file")):
            with self.assertRaises(blp.BlpError) as caught:
                blp.recolour(data, self.t, "Character\\Made\\Up.blp")

            self.assertIn("Character\\Made\\Up.blp", str(caught.exception))
            self.assertIn(text, str(caught.exception))

    def test_levels_as_the_client_walks_them(self):
        rgba = ss.skin_texture(8, 8, ss.SKIN, "body")
        data = bytearray(ss.blp_bgra(8, 8, rgba))
        # level 2 missing: the client stops there; levels 0 and 1 are recoloured, level 3's bytes are not
        struct.pack_into("<I", data, 0x54 + 4 * 2, 0)
        info = blp.parse(bytes(data), "test.blp")
        self.assertEqual((len(info.levels), info.missing), (2, 2))
        new = blp.recolour(bytes(data), self.t, "test.blp")
        level3 = struct.unpack_from("<I", data, 0x14 + 4 * 3)[0]
        self.assertEqual(new[level3:], bytes(data[level3:]))
        level1 = info.levels[1].offset
        self.assertNotEqual(new[level1:level1 + 64], bytes(data[level1:level1 + 64]))

        # a level that claims more bytes than CalcLevelSize: only the pixels are recoloured, never past its size
        data = bytearray(ss.blp_bgra(4, 4, ss.skin_texture(4, 4, ss.SKIN, "body"), mips=False)) + b"\x55" * 8
        struct.pack_into("<I", data, 0x54, 64 + 8)
        new = blp.recolour(bytes(data), self.t, "test.blp")
        self.assertEqual(new[-8:], b"\x55" * 8)


# --- colours -----------------------------------------------------------------------------------------------------


class ColourTests(unittest.TestCase):
    def test_stats_take_opaque_mid_lightness_pixels(self):
        skin, dark, light, hidden = (220, 180, 150), (10, 8, 8), (255, 255, 255), (20, 200, 30)
        rgba = bytearray()

        for colour, alpha, count in ((skin, 255, 40), ((200, 160, 130), 255, 20), (dark, 255, 30), (light, 255, 30),
                                     (hidden, 0, 60)):
            rgba += (bytes(colour) + bytes((alpha,))) * count

        result = recolor.stats(len(rgba) // 4, 1, rgba, True, recolor.DEFAULTS)
        self.assertEqual(result.pixels, 60)
        L, C, h = recolor.lch(recolor.srgb8_to_oklab(*skin))
        self.assertAlmostEqual(result.L, L, places=5)
        self.assertLess(hue_gap(result.h, h), 1)
        # without alpha the hidden green counts and outnumbers the skin
        self.assertGreater(recolor.stats(len(rgba) // 4, 1, rgba, False, recolor.DEFAULTS).pixels, 60)
        self.assertIsNone(recolor.stats(1, 1, bytes(dark) + b"\xff", True, recolor.DEFAULTS))

    def test_weighted_median(self):
        self.assertEqual(recolor.weighted_median([(3.0, 1), (1.0, 1), (2.0, 1)]), 2.0)
        self.assertEqual(recolor.weighted_median([(1.0, 1), (2.0, 1)]), 1.5)
        self.assertEqual(recolor.weighted_median([(1.0, 5), (9.0, 2)]), 1.0)

    def test_ranking_and_palette_sampling(self):
        palette = [recolor.hex_to_oklab(c) for c in ("#D3C4EC", "#846CAD", "#482E70")]
        colours = {k: recolor.SkinColour(L, 0.05, 50, 1) for k, L in ((0, 0.7), (1, 0.9), (2, 0.8))}
        goals = recolor.targets(colours, palette)
        # lightest first: colour 1 takes the first entry, colour 0 (darkest) the last, colour 2 the middle
        self.assertEqual(goals[1], target_of("#D3C4EC"))
        self.assertEqual(goals[2], target_of("#846CAD"))
        self.assertEqual(goals[0], target_of("#482E70"))
        # two colours over three entries: the ends; four over three: t = 1/3 lies between the first two (OKLab)
        two = recolor.targets({5: colours[0], 6: colours[1]}, palette)
        self.assertEqual((two[6], two[5]), (target_of("#D3C4EC"), target_of("#482E70")))
        four = recolor.targets({**colours, 3: recolor.SkinColour(0.85, 0.05, 50, 1)}, palette)
        mid = recolor.lch(recolor.sample(palette, 1 / 3))
        self.assertEqual(four[3], (round(mid[0], 6), round(mid[1], 6), round(mid[2], 4)))
        self.assertTrue(palette[0][0] > mid[0] > palette[1][0])
        # one colour alone: the middle; equal lightness: by index
        self.assertEqual(recolor.targets({4: colours[0]}, palette)[4], target_of("#846CAD"))
        tie = recolor.targets({8: colours[2], 7: colours[2]}, palette)
        self.assertEqual(tie[7], target_of("#D3C4EC"))

    def test_transform(self):
        t = fair_transform("#A38DC8")
        skin = t.skin
        self.assertTrue(recolor.DEFAULTS["gamma_min"] < t.gamma < recolor.DEFAULTS["gamma_max"])
        # the skin's own colour becomes the target exactly
        moved = t.lab(skin.L, skin.C * math.cos(math.radians(skin.h)), skin.C * math.sin(math.radians(skin.h)))
        self.assertAlmostEqual(recolor.lch(moved)[0], t.target[0], places=5)
        self.assertAlmostEqual(recolor.lch(moved)[1], t.target[1], places=5)
        self.assertLess(hue_gap(recolor.lch(moved)[2], t.target[2]), 0.01)
        # green: far in hue, unchanged in 8 bits and as a DXT endpoint
        self.assertEqual(t.rgb(*ss.GREEN), ss.GREEN)
        self.assertEqual(t.c565(ss.pack565(*ss.GREEN)), ss.pack565(*ss.GREEN))
        # the hue weight: full within 35 degrees, none beyond 65, linear between; the chroma weight likewise
        C = 2 * skin.C
        self.assertEqual(t.weight(C, skin.h + 30), 1.0)
        self.assertAlmostEqual(t.weight(C, skin.h - 50), 0.5)
        self.assertEqual(t.weight(C, skin.h + 70), 0.0)
        self.assertEqual(t.weight(0.3 * skin.C, skin.h + 120), 1.0, "a grey colour has no reliable hue")
        self.assertAlmostEqual(t.weight(skin.C + 0.10, skin.h), 0.5)
        self.assertEqual(t.weight(skin.C + 0.14, skin.h), 0.0)

    def test_eyes_keep_their_colour_on_a_grey_or_pale_skin(self):
        # a Death Knight's nearly grey skin (chroma below chroma_floor) and a very pale one: the eye's greens, the dark
        # pupil and iris rim and a muted iris too, keep their colour with every palette entry; the skin moves, and so
        # do the lips, which sit near the hue of the race's living skins
        config = configmod.load(os.path.join(TOOL_DIR, "races.json")).for_realm()
        race = skins.load(os.path.join(TOOL_DIR, "skins.json"), config)[0]
        eyes = [(18, 40, 22), (28, 96, 38), (90, 150, 100), ss.GREEN]
        lips = (214, 118, 126)
        living = recolor.living_hue([recolor.stats(32, 32, ss.skin_texture(32, 32, tone, "body"), False,
                                                   race.settings) for tone in ss.TONES], race.settings)
        self.assertLess(hue_gap(living, hue_of(ss.SKIN)), 10, "the grey Death Knight tone does not count")

        for tone, palette in ((ss.TONES[3], race.dk_palette), ((248, 238, 232), race.palette)):
            skin = recolor.stats(32, 32, ss.skin_texture(32, 32, tone, "body"), False, race.settings)
            self.assertLess(skin.C, race.settings["chroma_floor"], f"{tone} is nearly grey")

            for colour in palette:
                t = recolor.Transform(skin, target_of(colour), race.settings, living)
                self.assertEqual([t.rgb(*e) for e in eyes], eyes, f"{tone} -> {colour}")
                self.assertEqual([t.c565(ss.pack565(*e)) for e in eyes], [ss.pack565(*e) for e in eyes])
                self.assertNotEqual(t.rgb(*tone), tone)
                self.assertLess(hue_gap(hue_of(t.rgb(*lips)), t.target[2]), hue_gap(hue_of(lips), t.target[2]) - 15)

            # its own faint tints move whatever their hue; a colourful colour far from both hues does not
            self.assertEqual(t.weight(0.015, skin.h + 150), 1.0)
            self.assertEqual(t.weight(0.06, hue_of(ss.GREEN)), 0.0)

        # without the living skins' hue, the Death Knight's lips (far from its faint tint) would move much less
        dk = recolor.stats(32, 32, ss.skin_texture(32, 32, ss.TONES[3], "body"), False, race.settings)
        goal = target_of(race.dk_palette[0])
        alone, both = (recolor.Transform(dk, goal, race.settings, hue) for hue in (None, living))
        self.assertLess(hue_gap(hue_of(both.rgb(*lips)), both.target[2]) + 8,
                        hue_gap(hue_of(alone.rgb(*lips)), alone.target[2]))

        # a skin that is not nearly grey has a hue of its own: the living skins' hue plays no part
        t = recolor.Transform(fair_transform().skin, target_of("#846CAD"), race.settings, living + 90)
        self.assertIsNone(t.living_hue)
        self.assertEqual(t.params(), fair_transform(settings=race.settings).params())

    def test_settings_are_checked(self):
        for data, text in (({"hue_spread": "x"}, "must be a number"), ({"madeUp": 1}, "unknown setting"),
                           ({"gamma_min": 3.0}, "gamma_min"), ({"hue_full_within": 70.0}, "hue_full_within"),
                           ({"chroma_floor": 0}, "chroma_floor")):
            with self.assertRaises(recolor.RecolorError) as caught:
                recolor.settings_from(data, "skins.json")

            self.assertIn(text, str(caught.exception))

    def test_skins_json(self):
        config = configmod.load(os.path.join(TOOL_DIR, "races.json")).for_realm()
        races = skins.load(os.path.join(TOOL_DIR, "skins.json"), config)
        self.assertEqual([(r.race.id, r.name, r.sections) for r in races], [(15, "HighElf", [0, 1])])
        self.assertEqual((races[0].palette[0], races[0].palette[-1], len(races[0].palette)), ("#D3C4EC", "#482E70", 10))

        with open(os.path.join(TOOL_DIR, "skins.json"), encoding="utf-8") as f:
            data = json.load(f)

        def race(**values):
            return lambda d: d["races"][0].update(values)

        for mutate, text in ((race(client_file_string="Pandaren"), "is no race of races.json"),
                             (race(sections=[0, 3]), "hair and facial hair"),
                             (race(palette=["#12345"]), "not a colour"),
                             (race(dk_palette=[]), "dk_palette must be"),
                             (lambda d: d["races"].append(dict(d["races"][0])), "listed twice"),
                             (lambda d: d.update(extra=1), "unknown keys")):
            copy = json.loads(json.dumps(data))
            mutate(copy)

            with self.assertRaises(skins.SkinsError) as caught:
                skins.parse(copy, config)

            self.assertIn(text, str(caught.exception))


# --- the archives --------------------------------------------------------------------------------------------------


class ArchiveOrderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.data = os.path.join(self.tmp, "client", "Data")
        self.patches = os.path.join(self.tmp, "patches")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def put(self, folder: str, rel: str):
        ss.write_mpq(os.path.join(folder, *rel.split("/")), {"readme.txt": f"{folder} {rel}".encode()})

    def test_order(self):
        for rel in ("common.MPQ", "common-2.MPQ", "expansion.MPQ", "lichking.MPQ", "interface.MPQ",
                    "enUS/locale-enUS.MPQ", "enUS/lichking-locale-enUS.MPQ", "patch.MPQ", "patch-2.MPQ", "patch-3.MPQ",
                    "enUS/patch-enUS.MPQ", "enUS/patch-enUS-3.MPQ", "alternate.MPQ"):
            self.put(self.data, rel)

        for rel in ("Patch-R.MPQ", "Patch-3.MPQ", "enUS/patch-enUS-4.MPQ", "Patch-Y.MPQ", "patch-A.MPQ",
                    "deDE/patch-deDE-5.MPQ", "patch-AB.MPQ"):
            self.put(self.patches, rel)

        with open(os.path.join(self.patches, "notes.txt"), "w") as f:
            f.write("not an archive")

        game = skins.game_archives(os.path.join(self.tmp, "client"), self.patches, HD_PACK)

        try:
            order = [(a.client_path, a.origin, a.pack) for a in game.archives]
            self.assertEqual(order, [
                ("Data\\enUS\\lichking-locale-enUS.MPQ", "client", None),  # s_archives: a later one loads lower
                ("Data\\enUS\\locale-enUS.MPQ", "client", None),
                ("Data\\common-2.MPQ", "client", None),
                ("Data\\common.MPQ", "client", None),
                ("Data\\lichking.MPQ", "client", None),
                ("Data\\expansion.MPQ", "client", None),
                ("Data\\enUS\\patch-enUS.MPQ", "client", None),  # then patch-<locale>.MPQ and patch.MPQ
                ("Data\\patch.MPQ", "client", None),
                ("Data\\enUS\\patch-enUS-3.MPQ", "client", None),  # then patch-?.MPQ and the locale's, by path
                ("Data\\enUS\\patch-enUS-4.MPQ", "patches", None),
                ("Data\\patch-2.MPQ", "client", None),
                ("Data\\Patch-3.MPQ", "patches", None),  # the patch folder's copy replaces the game folder's
                ("Data\\patch-A.MPQ", "patches", "hd"),
                ("Data\\Patch-R.MPQ", "patches", None),
                ("Data\\Patch-Y.MPQ", "patches", "hd"),
            ])
            self.assertEqual(game.locale, "enUS")
            self.assertEqual(game.patchset.top("readme.txt", frozenset()).name, "Patch-R.MPQ")
            self.assertEqual(game.patchset.top("readme.txt", frozenset({"hd"})).name, "Patch-Y.MPQ")
            patch_3 = game.patchset.find("Patch-3.MPQ").path
            self.assertEqual(archive_read(patch_3, "readme.txt").decode(), f"{self.patches} Patch-3.MPQ")
            self.assertTrue(any("alternate.MPQ" in w for w in game.warnings))
            self.assertTrue(any("deDE" in n for n in game.notes))
            self.assertTrue(any("patch-AB.MPQ" in n for n in game.notes))
            self.assertFalse(any("interface.MPQ" in a.client_path for a in game.archives),
                             "the pre-2.0 archives load without common.MPQ only")
        finally:
            game.close()

    def test_locale(self):
        self.put(self.data, "common.MPQ")
        os.makedirs(self.patches)

        with self.assertRaises(skins.SkinsError) as caught:
            skins.game_archives(os.path.join(self.tmp, "client"), self.patches, {})

        self.assertIn("pass --locale", str(caught.exception))
        self.put(self.data, "enUS/locale-enUS.MPQ")
        self.put(self.data, "deDE/locale-deDE.MPQ")

        with self.assertRaises(skins.SkinsError):
            skins.game_archives(os.path.join(self.tmp, "client"), self.patches, {})

        game = skins.game_archives(os.path.join(self.tmp, "client"), self.patches, {}, "dede")
        self.assertEqual([a.client_path for a in game.archives], ["Data\\deDE\\locale-deDE.MPQ", "Data\\common.MPQ"])
        game.close()

    def test_rebuild_drops_files(self):
        folder = os.path.join(self.tmp, "in")
        ss.write_mpq(os.path.join(folder, "patch-Z.MPQ"), {"a.txt": b"a", "Old\\b.txt": b"b", "Old\\c.txt": b"c"})
        new = os.path.join(self.tmp, "new.txt")

        with open(new, "wb") as f:
            f.write(b"new")

        patchset = patches.PatchSet.scan(folder)
        out = os.path.join(self.tmp, "out.MPQ")
        patches.rebuild(patchset.find("patch-Z.MPQ"), {"Old\\c.txt": new}, out, os.path.join(self.tmp, "staging"),
                        drop=lambda n: n.lower().startswith("old\\"))
        patchset.close()
        self.assertEqual(sorted(archive_names(out)), ["Old\\c.txt", "a.txt"])
        self.assertEqual(archive_read(out, "Old\\c.txt"), b"new")


# --- the whole tool on made-up realms --------------------------------------------------------------------------------


class SkinsRealmTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.realm = ss.make_realm(self.tmp)
        self.patches = self.realm["patches"]

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def out(self, name: str = "out") -> str:
        return os.path.join(self.tmp, name)

    def skins(self, *extra, out: str = "out"):
        return run_tool("skins", "--patches", self.patches, "--client", self.realm["client"], "--out", self.out(out),
                        "--force", *extra)

    def written(self, out: str = "out") -> list[str]:
        folder = os.path.join(self.out(out), "client")
        return sorted(os.listdir(folder)) if os.path.isdir(folder) else []

    def install(self, out: str = "out"):
        for name in self.written(out):
            shutil.copyfile(os.path.join(self.out(out), "client", name), os.path.join(self.patches, name))

    def skins_json(self, mutate) -> str:
        with open(os.path.join(TOOL_DIR, "skins.json"), encoding="utf-8") as f:
            data = json.load(f)

        mutate(data)
        path = os.path.join(self.tmp, "skins-changed.json")

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)

        return path

    def high_elf_rows(self, table: DbcTable) -> list[list[int]]:
        return [r for r in table.rows if table.get(r, "raceID") == ss.HIGH_ELF]

    def test_one_archive_and_running_again(self):
        # (a) CharSections in Patch-R, the textures in a base archive, no pack replaces any: Patch-R gets everything
        result = self.skins("--preview")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.written(), ["Patch-R.MPQ"])
        self.assertIn("every player: CharSections.dbc from Patch-R.MPQ; 32 rows on 64 recoloured textures (32 rows "
                      "changed) -> Patch-R.MPQ", result.stdout)
        self.assertIn("6 checks, 0 failed", result.stdout)
        self.assertIn("raceforge.py install --from", result.stdout)
        rebuilt = os.path.join(self.out(), "client", "Patch-R.MPQ")
        names = archive_names(rebuilt)
        self.assertEqual(archive_read(rebuilt, "DBFilesClient\\ChrRaces.dbc"), self.realm["realm"]["ChrRaces"])
        self.assertEqual(archive_read(rebuilt, "Interface\\Glues\\Custom.blp"), b"the realm's own")
        before, after = sections_of(self.realm["realm"]["CharSections"]), sections_of(archive_read(rebuilt, CS))
        self.assertEqual(len(before.rows), len(after.rows))

        for old, new in zip(before.rows, after.rows):
            race, section = before.get(old, "raceID"), before.get(old, "baseSection")
            text = lambda t, r: [t.get_str(r, f"textureName[{i}]") for i in range(3)]  # noqa: E731
            numbers = [i for i, c in enumerate(before.schema.columns) if not c.is_string]
            self.assertEqual([old[i] for i in numbers], [new[i] for i in numbers])

            if race == ss.HIGH_ELF and section in (0, 1):
                for a, b in zip(text(before, old), text(after, new)):
                    if a:
                        pattern = r"^Character\\BleakholdSkins\\HighElf\\[0-9a-f]{10}\\"
                        self.assertRegex(b, pattern + a.replace("\\", "\\\\") + "$")
                        self.assertIn(b, names)
                        source = blp.parse(self.realm["textures"][a], a)
                        self.assertEqual(blp.check(archive_read(rebuilt, b), b, source.width, source.height), [])
            else:
                # the Blood Elf's rows (race 10), every other race's and the High Elf's hair: as they were
                self.assertEqual(text(before, old), text(after, new))

        # the Blood Elf's textures are not in the realm's archive: they stay in the base archive, untouched
        self.assertFalse(any(n.startswith("Character\\BloodElf") for n in names))
        previews = sorted(os.listdir(os.path.join(self.out(), "preview")))
        self.assertEqual(previews, ["HighElf-Female.png", "HighElf-Male.png"])

        with open(os.path.join(self.out(), "install.json"), encoding="utf-8") as f:
            manifest = json.load(f)

        self.assertEqual([(e["rel"], e["origin"]) for e in manifest["archives"]], [("Patch-R.MPQ", "patches")])
        self.assertTrue(manifest["checks_passed"])

        # installed and run again: nothing to change
        self.install()
        again = self.skins(out="again")
        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
        self.assertIn("already up to date", again.stdout)
        self.assertIn("(0 rows changed)", again.stdout)
        self.assertEqual(self.written("again"), [])

        # another palette: new names, and the old files leave the archive
        changed = self.skins_json(lambda d: d["races"][0].update(palette=["#B0A0E0", "#403070"],
                                                                 dk_palette=["#909098"]))
        third = self.skins("--skins", changed, out="third")
        self.assertEqual(third.returncode, 0, third.stdout + third.stderr)
        self.assertRegex(third.stdout, r"\(\d+\.\d GB; 64 added, 1 replaced, 64 dropped\)")
        old_names = {n for n in names if n.startswith("Character\\BleakholdSkins")}
        third_archive = os.path.join(self.out("third"), "client", "Patch-R.MPQ")
        new_names = {n for n in archive_names(third_archive) if n.startswith("Character\\BleakholdSkins")}
        self.assertEqual(len(new_names), 64)
        self.assertFalse(old_names & new_names)

        # the way back: no sections, every row on its original textures again and no file of the folder left
        self.install("third")
        back = self.skins("--skins", self.skins_json(lambda d: d["races"][0].update(sections=[])), out="back")
        self.assertEqual(back.returncode, 0, back.stdout + back.stderr)
        restored = os.path.join(self.out("back"), "client", "Patch-R.MPQ")
        table = sections_of(archive_read(restored, CS))

        for old, new in zip(before.rows, table.rows):
            self.assertEqual(names_of(before, old), names_of(table, new))

        self.assertFalse([n for n in archive_names(restored) if n.startswith("Character\\BleakholdSkins")])
        self.assertIn("32 rows changed", back.stdout)

    def hd_texture(self) -> bytes:
        # the HD pack's own Blood Elf skin under the same name: another (made-up) picture
        return ss.blp_bgra(64, 64, ss.skin_texture(64, 64, (240, 206, 182), "body"))

    def test_hd_pack_texture_goes_to_a_pack_archive_above(self):
        # (b) patch-D (HD pack, below Patch-R) replaces a Blood Elf skin; Patch-Y (HD pack, above Patch-R) is there:
        # the players without the pack keep Patch-R, the HD players get their CharSections and textures in Patch-Y
        ss.write_mpq(os.path.join(self.patches, "patch-D.MPQ"), {FEMALE_SKIN_0: self.hd_texture()})
        ss.write_mpq(os.path.join(self.patches, "Patch-Y.MPQ"), {"Character\\Made\\Up.m2": b"HD model"})
        result = self.skins()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.written(), ["Patch-R.MPQ", "Patch-Y.MPQ"])
        both = "CharSections.dbc from Patch-R.MPQ; 32 rows on 64 recoloured textures (32 rows changed)"
        self.assertIn(f"all packs: {both} -> Patch-Y.MPQ", result.stdout)
        self.assertIn(f"no packs: {both} -> Patch-R.MPQ", result.stdout)

        with open(os.path.join(self.out(), "report.txt"), encoding="utf-8") as f:
            report = f.read()

        self.assertIn(f"holds all packs's own CharSections.dbc and textures ({FEMALE_SKIN_0}", report)
        hd, plain = (os.path.join(self.out(), "client", n) for n in ("Patch-Y.MPQ", "Patch-R.MPQ"))
        self.assertEqual(archive_read(hd, "Character\\Made\\Up.m2"), b"HD model")
        hd_cs, plain_cs = sections_of(archive_read(hd, CS)), sections_of(archive_read(plain, CS))
        female_skin = lambda t: next(t.get_str(r, "textureName[0]") for r in self.high_elf_rows(t)  # noqa: E731
                                     if is_row(t, r, 1, 0, 0))
        self.assertNotEqual(female_skin(hd_cs), female_skin(plain_cs))
        self.assertIn(female_skin(hd_cs), archive_names(hd))
        self.assertEqual(blp.parse(archive_read(hd, female_skin(hd_cs)), "hd").width, 64)
        self.assertEqual(blp.parse(archive_read(plain, female_skin(plain_cs)), "plain").width, 32)

        marker = json.loads(archive_read(hd, skins.COPY_MARKER))
        self.assertEqual((marker["for"], marker["from"]), (["all packs"], ["Data\\Patch-R.MPQ"]))
        self.assertEqual(marker["sha1"], hashlib.sha1(archive_read(hd, CS)).hexdigest())
        self.assertNotIn(skins.COPY_MARKER, archive_names(plain))

        # installed and run again: Patch-Y's copy is passed over and made again from Patch-R, the same bytes
        self.install()
        again = self.skins(out="again")
        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
        self.assertIn("already up to date", again.stdout)
        self.assertIn("all packs: CharSections.dbc from Patch-R.MPQ", again.stdout)

        with open(os.path.join(self.out("again"), "report.txt"), encoding="utf-8") as f:
            self.assertIn("passing over Patch-Y.MPQ: its DBFilesClient\\CharSections.dbc is skins' own copy", f.read())

        # the race patch gets a new High Elf row (a new build of it): the HD players' copy must get it too
        patch_r, patch_y = (os.path.join(self.patches, n) for n in ("Patch-R.MPQ", "Patch-Y.MPQ"))
        table = sections_of(archive_read(patch_r, CS))
        hair = next(r for r in self.high_elf_rows(table) if table.get(r, "baseSection") == 3)
        extra = list(hair)
        table.set(extra, "id", table.max_id() + 1)
        table.set(extra, "variationIndex", 77)
        table.rows.insert(table.rows.index(hair) + 1, extra)
        files = {n: archive_read(patch_r, n) for n in archive_names(patch_r) if not n.startswith("(")}
        ss.write_mpq(patch_r, {**files, CS: table.to_bytes()})
        newer = self.skins(out="newer")
        self.assertEqual(newer.returncode, 0, newer.stdout + newer.stderr)
        self.assertEqual(self.written("newer"), ["Patch-Y.MPQ"], "Patch-R's own change needs nothing")
        copy = sections_of(archive_read(os.path.join(self.out("newer"), "client", "Patch-Y.MPQ"), CS))
        self.assertEqual(len(copy.rows), len(table.rows))
        self.assertTrue(any(copy.get(r, "variationIndex") == 77 for r in copy.rows))
        self.install("newer")
        self.assertIn("already up to date", self.skins(out="newer-again").stdout)

        # the way back: Patch-Y loses its copy, the marker and the textures; its own files stay
        back = self.skins("--skins", self.skins_json(lambda d: d["races"][0].update(sections=[])), out="back")
        self.assertEqual(back.returncode, 0, back.stdout + back.stderr)
        self.assertEqual(self.written("back"), ["Patch-R.MPQ", "Patch-Y.MPQ"])
        self.assertIn("all packs: CharSections.dbc from Patch-R.MPQ; 0 rows on 0 recoloured textures (32 rows changed) "
                      "-> Patch-R.MPQ", back.stdout)
        emptied = archive_names(os.path.join(self.out("back"), "client", "Patch-Y.MPQ"))
        self.assertIn("Character\\Made\\Up.m2", emptied)
        self.assertFalse([n for n in emptied if n == CS or n.startswith("Character\\BleakholdSkins")], emptied)
        self.assertRegex(back.stdout, r"client/Patch-R\.MPQ \(\d+\.\d GB; 0 added, 1 replaced, 64 dropped\)")
        self.assertRegex(back.stdout, r"client/Patch-Y\.MPQ \(\d+\.\d GB; 0 added, 0 replaced, 66 dropped\)")
        self.install("back")
        self.assertIn("already up to date", self.skins("--skins", self.skins_json(lambda d: d["races"][0].update(
            sections=[])), out="back-again").stdout)
        self.assertEqual(archive_read(patch_y, "Character\\Made\\Up.m2"), b"HD model")

    def test_hd_copy_goes_where_no_other_players_read_it(self):
        # a second pack x with Patch-Z above Patch-Y: Patch-Z ranks higher, but the players of x alone would read the
        # HD copy there, so it goes to Patch-Y; without Patch-Y, the refusal names the players in the way
        ss.write_mpq(os.path.join(self.patches, "patch-D.MPQ"), {FEMALE_SKIN_0: self.hd_texture()})
        ss.write_mpq(os.path.join(self.patches, "Patch-Y.MPQ"), {"Character\\Made\\Up.m2": b"HD model"})
        ss.write_mpq(os.path.join(self.patches, "Patch-Z.MPQ"), {"Interface\\Made\\Up.blp": b"pack x"})

        with open(os.path.join(TOOL_DIR, "races.json"), encoding="utf-8") as f:
            data = json.load(f)

        data["archives"]["optional_packs"] = {**HD_PACK, "x": ["Data/Patch-Z.MPQ"]}
        config = os.path.join(self.tmp, "races-two-packs.json")

        with open(config, "w", encoding="utf-8") as f:
            json.dump(data, f)

        result = self.skins("--config", config)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        for label, archive in (("all packs", "Patch-Y"), ("packs hd", "Patch-Y"), ("packs x", "Patch-R"),
                               ("no packs", "Patch-R")):
            self.assertRegex(result.stdout, rf"  {label}: CharSections\.dbc from Patch-R\.MPQ; .* -> {archive}\.MPQ")

        self.assertEqual(self.written(), ["Patch-R.MPQ", "Patch-Y.MPQ"])
        self.assertIn("18 checks, 0 failed", result.stdout)

        os.remove(os.path.join(self.patches, "Patch-Y.MPQ"))
        refused = self.skins("--config", config, out="refused")
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("Patch-Z.MPQ (pack x) is loaded by packs x too", refused.stderr)
        self.assertIn("Add an archive to a pack that only those players load", refused.stderr)
        self.assertFalse(os.path.exists(self.out("refused")))

    def test_hd_pack_texture_without_an_archive_above_is_refused(self):
        # (c) the same without Patch-Y: the HD players would need a pack archive above Patch-R; nothing is written
        ss.write_mpq(os.path.join(self.patches, "patch-D.MPQ"), {FEMALE_SKIN_0: self.hd_texture()})
        result = self.skins()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("all packs and no packs read the same CharSections.dbc (Patch-R.MPQ), but their skins differ",
                      result.stderr)
        self.assertIn("an archive of the pack hd that loads after Patch-R.MPQ", result.stderr)
        self.assertIn("Nothing was written", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse(os.path.exists(self.out()))

    def test_charsections_in_two_archives(self):
        # (d) the HD pack's Patch-Y has its own CharSections (an HD skin under its own name): each copy forged in place
        hd_name = "Character\\BloodElf\\Female\\HD\\BloodElfFemaleSkin00.blp"
        table = sections_of(self.realm["realm"]["CharSections"])

        for row in self.high_elf_rows(table) + [r for r in table.rows if table.get(r, "raceID") == ss.BLOOD_ELF]:
            if is_row(table, row, 1, 0, 0):
                table.set_str(row, "textureName[0]", hd_name)

        ss.write_mpq(os.path.join(self.patches, "Patch-Y.MPQ"), {CS: table.to_bytes(), hd_name: self.hd_texture()})
        result = self.skins()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.written(), ["Patch-R.MPQ", "Patch-Y.MPQ"])
        self.assertIn("all packs: CharSections.dbc from Patch-Y.MPQ; 32 rows on 64 recoloured textures (32 rows "
                      "changed) -> Patch-Y.MPQ", result.stdout)
        self.assertIn("no packs: CharSections.dbc from Patch-R.MPQ", result.stdout)
        hd_cs = sections_of(archive_read(os.path.join(self.out(), "client", "Patch-Y.MPQ"), CS))
        blood_elf = [hd_cs.get_str(r, "textureName[0]") for r in hd_cs.rows if hd_cs.get(r, "raceID") == ss.BLOOD_ELF]
        self.assertIn(hd_name, blood_elf, "the Blood Elf's rows keep the HD pack's names")
        hd_archive = os.path.join(self.out(), "client", "Patch-Y.MPQ")
        self.assertTrue(any(n.endswith("\\" + hd_name) for n in archive_names(hd_archive)))

    def test_race_patch_in_the_game_folder(self):
        # the race patch in the game folder (base/Data) instead of the patch folder: the rebuilt archive goes into the
        # patch folder, where it overrides the game folder's
        game_copy = os.path.join(self.realm["data"], "Patch-R.MPQ")
        shutil.move(os.path.join(self.patches, "Patch-R.MPQ"), game_copy)
        result = self.skins()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.written(), ["Patch-R.MPQ"])

        with open(os.path.join(self.out(), "install.json"), encoding="utf-8") as f:
            entry = json.load(f)["archives"][0]

        self.assertEqual((entry["rel"], entry["origin"], entry["source"]), ("Patch-R.MPQ", "client", game_copy))

        # a patch of that name in the patch folder since: refused
        shutil.copyfile(game_copy, os.path.join(self.patches, "Patch-R.MPQ"))
        refused = run_tool("install", "--from", self.out(), "--patches", self.patches)
        self.assertIn("exists now, but the tool read Patch-R.MPQ from the game folder", refused.stderr)
        os.remove(os.path.join(self.patches, "Patch-R.MPQ"))

        added = run_tool("install", "--from", self.out(), "--patches", self.patches)
        self.assertEqual(added.returncode, 0, added.stdout + added.stderr)
        self.assertIn(f"added: {os.path.join(self.patches, 'Patch-R.MPQ')}", added.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.out(), "old-patches", "Patch-R.MPQ")), "nothing replaced")
        self.assertFalse(install.load_record(self.out())["archives"]["Patch-R.MPQ"]["backup"])
        again = self.skins(out="again")
        self.assertIn("already up to date", again.stdout)

        # the way back removes the added archive
        restored = run_tool("install", "--restore", "--from", self.out(), "--patches", self.patches)
        self.assertEqual(restored.returncode, 0, restored.stdout + restored.stderr)
        self.assertIn(f"removed: {os.path.join(self.patches, 'Patch-R.MPQ')}", restored.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.patches, "Patch-R.MPQ")))

    def test_refusals(self):
        # CharSections only in a base archive: the realm's race patch has no copy
        patch_r = os.path.join(self.patches, "Patch-R.MPQ")
        races, sections = self.realm["realm"]["ChrRaces"], self.realm["realm"]["CharSections"]
        ss.write_mpq(patch_r, {CR: races})
        result = self.skins()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("from the base archive locale-enUS.MPQ", result.stderr)

        # no High Elf at 15
        ss.write_mpq(patch_r, {CS: sections})
        result = self.skins()
        self.assertIn("High Elf: the realm's ChrRaces.dbc (locale-enUS.MPQ, for every player) has Skeleton as race 15, "
                      "not HighElf", result.stderr)
        self.assertIn("then run skins", result.stderr)

        # a face of a skin colour no skin row has
        table = sections_of(sections)
        table.rows.remove(next(r for r in self.high_elf_rows(table) if is_row(table, r, 0, 0, 2)))
        ss.write_mpq(patch_r, {CS: table.to_bytes(), CR: races})
        result = self.skins()
        self.assertIn("has skin colour 2, but there is no skin row (section 0, variation 0) of colour 2 for Male",
                      result.stderr)

        # a JPEG texture, and a texture no archive has
        ss.write_mpq(patch_r, {CS: sections, CR: races})
        jpeg = bytearray(self.realm["textures"][FEMALE_SKIN_0])
        jpeg[8] = 0
        ss.write_mpq(os.path.join(self.patches, "patch-T.MPQ"), {FEMALE_SKIN_0: bytes(jpeg)})
        result = self.skins()
        self.assertIn(f"{FEMALE_SKIN_0}: a JPEG BLP2 texture", result.stderr)
        os.remove(os.path.join(self.patches, "patch-T.MPQ"))
        textures = dict(self.realm["textures"])
        del textures[FEMALE_SKIN_0]
        ss.write_mpq(os.path.join(self.realm["data"], "common.MPQ"), textures)
        result = self.skins()
        self.assertIn(f"{FEMALE_SKIN_0}, the texture of High Elf's row", result.stderr)
        self.assertIn("is in no archive for every player", result.stderr)

        # the output folder inside the patch folder (the launcher would publish it)
        result = run_tool("skins", "--patches", self.patches, "--client", self.realm["client"], "--out",
                          os.path.join(self.patches, "out"))
        self.assertIn("is inside --patches", result.stderr)
        self.assertFalse(os.path.exists(self.out()))

    def test_disk_space_is_checked_first(self):
        import raceforge  # noqa: E402

        stderr = io.StringIO()

        args = ["skins", "--patches", self.patches, "--client", self.realm["client"], "--out", self.out()]

        with mock.patch.object(skins, "free_space", return_value=1000), contextlib.redirect_stderr(stderr), \
                contextlib.redirect_stdout(io.StringIO()):
            code = raceforge.main(args)

        self.assertEqual(code, 1)
        self.assertRegex(stderr.getvalue(), r"needs \d+\.\d GB free for the rebuilt archives \(Patch-R\.MPQ\), "
                                            r"has 0\.0 GB")
        self.assertFalse(os.path.exists(self.out()))


# --- install -------------------------------------------------------------------------------------------------------


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.realm = ss.make_realm(self.tmp)
        self.patches = self.realm["patches"]
        # the realm's Patch-R.MPQ is a link to the download site's copy
        self.site = os.path.join(self.tmp, "site", "Patch-R.MPQ")
        os.makedirs(os.path.dirname(self.site))
        shutil.move(os.path.join(self.patches, "Patch-R.MPQ"), self.site)
        os.symlink(self.site, os.path.join(self.patches, "Patch-R.MPQ"))
        self.out = os.path.join(self.tmp, "out")
        result = run_tool("skins", "--patches", self.patches, "--client", self.realm["client"], "--out", self.out)
        assert result.returncode == 0, result.stdout + result.stderr

        with open(self.site, "rb") as f:
            self.old = f.read()

        with open(os.path.join(self.out, "client", "Patch-R.MPQ"), "rb") as f:
            self.new = f.read()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def install(self, *extra):
        return run_tool("install", "--from", self.out, "--patches", self.patches, *extra)

    def site_bytes(self) -> bytes:
        with open(self.site, "rb") as f:
            return f.read()

    def test_dry_run_changes_nothing(self):
        result = self.install("--dry-run")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f"would replace {self.site} with {os.path.join(self.out, 'client', 'Patch-R.MPQ')}",
                      result.stdout)
        self.assertIn(f"would back up {self.site} to {os.path.join(self.out, 'old-patches', 'Patch-R.MPQ')}",
                      result.stdout)
        self.assertIn("Dry run: nothing was changed.", result.stdout)
        self.assertEqual(self.site_bytes(), self.old)
        self.assertTrue(os.path.isfile(os.path.join(self.out, "client", "Patch-R.MPQ")))
        self.assertFalse(os.path.exists(os.path.join(self.out, "old-patches")))

    def test_install_through_a_link_and_back(self):
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f"replaced: {self.site}", result.stdout)
        self.assertIn(install.PUBLISH, result.stdout)
        link = os.path.join(self.patches, "Patch-R.MPQ")
        self.assertTrue(os.path.islink(link))
        self.assertEqual(os.readlink(link), self.site)
        self.assertEqual(self.site_bytes(), self.new)
        self.assertFalse(os.path.exists(self.site + ".new"))
        backup = os.path.join(self.out, "old-patches", "Patch-R.MPQ")

        with open(backup, "rb") as f:
            self.assertEqual(f.read(), self.old)

        self.assertFalse(os.path.exists(os.path.join(self.out, "client", "Patch-R.MPQ")), "moved, not copied")

        # again: already in place; the realm is up to date for skins too
        again = self.install()
        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
        self.assertIn(f"already installed: {self.site}", again.stdout)
        check = run_tool("skins", "--patches", self.patches, "--client", self.realm["client"], "--out",
                         os.path.join(self.tmp, "check"))
        self.assertIn("already up to date", check.stdout)

        # the way back
        restored = self.install("--restore")
        self.assertEqual(restored.returncode, 0, restored.stdout + restored.stderr)
        self.assertIn(f"restored: {self.site}", restored.stdout)
        self.assertEqual(self.site_bytes(), self.old)
        self.assertTrue(os.path.islink(link))

    def test_refused_when_the_patch_changed(self):
        os.utime(self.site, ns=(os.stat(self.site).st_atime_ns, os.stat(self.site).st_mtime_ns + 10 ** 9))
        result = self.install()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(f"{self.site} changed since the tool read it", result.stderr)
        self.assertIn("Run the tool again", result.stderr)
        self.assertEqual(self.site_bytes(), self.old)
        self.assertTrue(os.path.isfile(os.path.join(self.out, "client", "Patch-R.MPQ")))
        self.assertFalse(os.path.exists(os.path.join(self.out, "old-patches")))

    def test_without_install_json(self):
        os.remove(os.path.join(self.out, "install.json"))
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("the check that the patch folder did not change since the tool read it is skipped", result.stdout)
        self.assertEqual(self.site_bytes(), self.new)

    def test_failed_checks_are_not_installed(self):
        path = os.path.join(self.out, "install.json")

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        data["checks_passed"] = False

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)

        result = self.install()
        self.assertIn("failed some checks", result.stderr)
        self.assertEqual(self.site_bytes(), self.old)

    def test_update_output(self):
        # update writes install.json too, and install takes its output (a made-up realm patch without the racials)
        from tests import synth
        stock = os.path.join(self.tmp, "stock")
        synth.write_folder(stock)
        with open(os.path.join(TOOL_DIR, "races.json"), encoding="utf-8") as f:
            data = json.load(f)

        for race in data["races"]:
            race.pop("realm_id", None)

        old = json.loads(json.dumps(data))

        for race in old["races"]:
            race.pop("racials", None)

        old.pop("spells", None)
        config_old, config = os.path.join(self.tmp, "old.json"), os.path.join(self.tmp, "build.json")
        for path, value in ((config_old, old), (config, data)):
            with open(path, "w", encoding="utf-8") as f:
                json.dump(value, f)
        built = os.path.join(self.tmp, "built")
        result = run_tool("build", "--dbc", stock, "--out", built, "--mpq", "--config", config_old)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        realm = os.path.join(self.tmp, "realm-patches")
        os.makedirs(realm)
        shutil.copyfile(os.path.join(built, "client", "patch-R.MPQ"), os.path.join(realm, "patch-R.MPQ"))
        out = os.path.join(self.tmp, "racials")
        result = run_tool("update", "--patches", realm, "--dbc", stock, "--out", out, "--config", config)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        # the line to paste names the real folders (a placeholder such as <this folder> would be a shell redirection)
        self.assertIn(f"raceforge.py install --from {out} --patches {realm}\n", result.stdout)
        self.assertNotIn("<this folder>", result.stdout)

        with open(os.path.join(out, "install.json"), encoding="utf-8") as f:
            manifest = json.load(f)

        self.assertEqual([(e["rel"], e["origin"], e["size"]) for e in manifest["archives"]],
                         [("patch-R.MPQ", "patches", os.path.getsize(os.path.join(realm, "patch-R.MPQ")))])
        result = run_tool("install", "--from", out, "--patches", realm)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f"replaced: {os.path.join(realm, 'patch-R.MPQ')}", result.stdout)
        again = run_tool("update", "--patches", realm, "--dbc", stock, "--out", os.path.join(self.tmp, "racials-again"),
                         "--config", config)
        self.assertEqual(again.stdout.count("already up to date"), 3)


class InstallRecordTests(unittest.TestCase):
    """install's backups and --restore over several runs and output folders: Patch-R.MPQ links to a site copy, and
    each tool run is what it leaves behind with --force (client/Patch-R.MPQ made from the patch folder as it is, and
    install.json; old-patches stays). The archives are a few made-up bytes."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.patches = os.path.join(self.tmp, "patches")
        self.link = os.path.join(self.patches, "Patch-R.MPQ")
        self.site = os.path.join(self.tmp, "site", "Patch-R.MPQ")
        self.write(self.site, b"P0: the realm's")
        os.makedirs(self.patches)
        os.symlink(self.site, self.link)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def write(self, path: str, data: bytes):
        os.makedirs(os.path.dirname(path), exist_ok=True)

        with open(path, "wb") as f:
            f.write(data)

    def read(self, path: str) -> bytes:
        with open(path, "rb") as f:
            return f.read()

    def produce(self, name: str, data: bytes | None, tool: str = "skins", checks: bool = True) -> str:
        """A run of skins (or update) into tmp/<name> with --force; data None: "already up to date"."""
        from rflib import update
        out = os.path.join(self.tmp, name)
        os.makedirs(out, exist_ok=True)
        update.clean_out_dir(out, True, skins.OUT_ENTRIES if tool == "skins" else update.OUT_ENTRIES)
        entries = []

        if data is not None:
            size, mtime = install.fingerprint(self.link)
            path = os.path.join(out, "client", "Patch-R.MPQ")
            self.write(path, data)
            entries.append(install.entry("Patch-R.MPQ", "Data\\Patch-R.MPQ", "patches", self.link, size, mtime, path))

        install.write_manifest(out, f"raceforge.py {tool}", self.patches, None, entries, checks)
        return out

    def run_install(self, out: str, restore: bool = False) -> str:
        lines = []
        self.assertEqual(install.run(out, self.patches, restore=restore, say=lines.append), 0)
        return "\n".join(lines)

    def test_an_added_archive_replaced_by_the_next_install_is_still_removed_by_restore(self):
        # a tool adds patch-4.MPQ (origin "new"); its next run into the same folder finds its own archive in the patch
        # folder and replaces it (origin "patches"): --restore must remove it, not put the first copy back
        out = os.path.join(self.tmp, "cafe")
        new = os.path.join(self.patches, "patch-4.MPQ")

        def produce(data: bytes, origin: str):
            from rflib import update
            update.clean_out_dir(out, True, ("client", "install.json"))
            path = os.path.join(out, "client", "patch-4.MPQ")
            self.write(path, data)
            size, mtime = install.fingerprint(new) if origin == "patches" else (None, None)
            entries = [install.entry("patch-4.MPQ", "Data\\patch-4.MPQ", origin, new if origin == "patches" else "",
                                     size, mtime, path)]
            install.write_manifest(out, "cafeforge.py build", self.patches, None, entries, True)

        produce(b"cafe v1", "new")
        self.assertIn(f"added: {new}", self.run_install(out))
        produce(b"cafe v2", "patches")
        text = self.run_install(out)
        self.assertIn(f"no backup: an earlier install from this folder added {new}", text)
        self.assertIn(f"replaced: {new}", text)
        self.assertFalse(os.path.exists(os.path.join(out, "old-patches", "patch-4.MPQ")))
        self.assertEqual(self.read(new), b"cafe v2")
        text = self.run_install(out, restore=True)
        self.assertIn(f"removed: {new}", text)
        self.assertFalse(os.path.exists(new))                       # before the fix: "cafe v1" was put back
        self.assertEqual(sorted(os.listdir(self.patches)), ["Patch-R.MPQ"])

    def test_running_again_into_the_folder_keeps_the_way_back(self):
        # after the install, skins runs again into the same folder: up to date (install.json without archives), then
        # with a new archive it does not install, then cut off (checks_passed false): --restore still goes back
        out = self.produce("skins", b"S1: P0 + skins")
        self.run_install(out)
        self.assertEqual(self.read(self.site), b"S1: P0 + skins")

        for data, checks in ((None, True), (b"S2: P0 + other skins", True), (b"S3: cut off", False)):
            self.produce("skins", data, checks=checks)

        text = self.run_install(out, restore=True)
        self.assertIn(f"restored: {self.site}", text)
        self.assertEqual(self.read(self.site), b"P0: the realm's")
        self.assertTrue(os.path.islink(self.link))

        # a second --restore (pasted again): already put back, nothing to do
        text = self.run_install(out, restore=True)
        self.assertIn(f"already put back: {self.site}", text)
        self.assertIn("Nothing to do: every archive is already put back.", text)
        self.assertEqual(self.read(self.site), b"P0: the realm's")

    def test_the_same_folder_twice_keeps_the_first_backup(self):
        out = self.produce("skins", b"S1: P0 + skins")
        self.run_install(out)
        out = self.produce("skins", b"S2: P0 + tuned skins!")
        self.assertIn("backup already there", self.run_install(out))
        self.assertEqual(self.read(os.path.join(out, "old-patches", "Patch-R.MPQ")), b"P0: the realm's")
        self.run_install(out, restore=True)
        self.assertEqual(self.read(self.site), b"P0: the realm's")

    def test_another_install_in_between(self):
        # skins, then the racials from their own folder, then skins again into its folder: going back from the skins'
        # folder keeps the racials, and the racials' folder refuses while the skins' archive is in place
        skins_out = self.produce("skins", b"S1: P0 + skins")
        self.run_install(skins_out)
        racials = self.produce("racials", b"R1: S1 + racials", tool="update")
        self.run_install(racials)
        skins_out = self.produce("skins", b"S2: R1 + tuned skins")
        text = self.run_install(skins_out)
        aside = os.path.join(skins_out, "old-patches-1", "Patch-R.MPQ")
        self.assertIn(f"older backup moved to {aside}: another install replaced {self.site}", text)
        self.assertEqual(self.read(aside), b"P0: the realm's")
        self.assertEqual(self.read(os.path.join(skins_out, "old-patches", "Patch-R.MPQ")), b"R1: S1 + racials")

        with self.assertRaises(install.InstallError) as caught:
            install.run(racials, self.patches, restore=True, say=lambda _: None)

        self.assertIn(f"{self.site} is not the archive install put there: another install has replaced it since",
                      str(caught.exception))
        self.assertEqual(self.read(self.site), b"S2: R1 + tuned skins")

        self.run_install(skins_out, restore=True)
        self.assertEqual(self.read(self.site), b"R1: S1 + racials")
        self.run_install(racials, restore=True)
        self.assertEqual(self.read(self.site), b"S1: P0 + skins")

    def test_restore_of_a_folder_installed_by_hand(self):
        # the runbooks' old shell loop: client/ copied into place, old-patches/ a copy of the file before, no record
        racials = os.path.join(self.tmp, "racials")
        self.write(os.path.join(racials, "client", "Patch-R.MPQ"), b"R1: P0 + racials")
        os.makedirs(os.path.join(racials, "old-patches"))
        shutil.copy2(self.site, os.path.join(racials, "old-patches", "Patch-R.MPQ"))
        shutil.copyfile(os.path.join(racials, "client", "Patch-R.MPQ"), self.site)

        # a later install (the skins') replaced it: refused, nothing changes
        skins_out = self.produce("skins", b"S1: R1 + skins")
        self.run_install(skins_out)

        with self.assertRaises(install.InstallError) as caught:
            install.run(racials, self.patches, restore=True, say=lambda _: None)

        self.assertIn("has no record of what was installed from it", str(caught.exception))
        self.assertIn("is not byte for byte", str(caught.exception))
        self.assertEqual(self.read(self.site), b"S1: R1 + skins")

        # the skins undone, the racials' archive is in place again: now it goes back
        self.run_install(skins_out, restore=True)
        text = self.run_install(racials, restore=True)
        self.assertIn(f"No old-patches/installed.json in {racials}", text)
        self.assertIn(f"restored: {self.site}", text)
        self.assertEqual(self.read(self.site), b"P0: the realm's")


if __name__ == "__main__":
    unittest.main()
