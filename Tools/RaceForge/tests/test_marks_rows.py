"""rflib/appearance.py and rflib/marksrows.py: the two encodings, the paste rule, the catalogue, MarkForge's manifest
and the mark (features) and eye (face) rows with their flags."""

import copy
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL_DIR = os.path.dirname(HERE)

if TOOL_DIR not in sys.path:
    sys.path.insert(0, TOOL_DIR)

from rflib import appearance as ap  # noqa: E402
from rflib import marksrows, schema_access  # noqa: E402
from rflib.dbc import DbcTable  # noqa: E402
from tests import synth_customize as sc  # noqa: E402

CATALOGUE = os.path.join(TOOL_DIR, "customize", "catalogue.json")


def package_tables():
    data = sc.tables(True)
    return (DbcTable.from_bytes(data["CharSections"], schema_access.get("CharSections")),
            DbcTable.from_bytes(data["CharacterFacialHairStyles"], schema_access.get("CharacterFacialHairStyles")))


class EncodingTests(unittest.TestCase):
    def test_features(self):
        self.assertEqual(ap.look_of(1, 1), 1)
        self.assertEqual(ap.look_of(4, 3), 12)
        self.assertEqual([ap.design_colour(look) for look in (1, 3, 4, 12)], [(1, 1), (1, 3), (2, 1), (4, 3)])
        self.assertEqual(ap.features_value(12, 18, 19), 246, "Night Elf female's largest value")
        self.assertEqual(ap.split_features(246, 19), (12, 18))

        for bad in ((0, 1), (5, 1), (1, 4)):
            with self.assertRaises(ValueError):
                ap.look_of(*bad)

        with self.assertRaises(ValueError):
            ap.features_value(1, 19, 19)

    def test_face(self):
        self.assertEqual(ap.face_value(38, 5), 238)
        self.assertEqual(ap.split_face(238), (5, 38))

        with self.assertRaises(ValueError):
            ap.face_value(40, 1)

    def test_paths(self):
        self.assertEqual(ap.mark_name("NightElf", 1, "MoonwellSigils", "EluneBlue"),
                         "Character\\BleakholdMarks\\NightElf\\Female\\MoonwellSigils_EluneBlue.blp")
        self.assertEqual(ap.glow_name("Character\\X\\A_B.blp"), "Character\\X\\A_B_Glow.blp")
        self.assertEqual(ap.eye_name("HighElf", 0, "Starlight"), "Character\\BleakholdEyes\\HighElf\\Male\\Eye_Starlight.blp")
        self.assertTrue(ap.is_ours("character/bleakholdeyes/x.blp"))
        self.assertFalse(ap.is_ours("Character\\BloodElf\\x.blp"))

    def test_flag_rules(self):
        cases = {  # flags: (creation player, creation DK, world player, world DK)
            0x11: (True, True, True, True),
            0x5: (False, True, False, True),
            0x1: (True, False, True, False),
            0x8: (False, False, False, False),
            0x12: (False, False, True, True),
            0x2: (False, False, True, False),
            0x19: (False, False, False, False),
        }

        for flags, want in cases.items():
            got = (ap.selectable(flags, ap.CREATION, False), ap.selectable(flags, ap.CREATION, True),
                   ap.selectable(flags, ap.WORLD, False), ap.selectable(flags, ap.WORLD, True))
            self.assertEqual(got, want, hex(flags))

    def test_paste_rule(self):
        self.assertIsNone(ap.paste_problem(512, 512, 10, "whole"))
        self.assertIsNone(ap.paste_problem(16, 16, 5, "whole"), "smaller in both directions: scaled")
        self.assertIsNone(ap.paste_problem(256, 128, 9, "face lower"))
        self.assertIsNone(ap.paste_problem(512, 256, 10, "face lower"))
        self.assertIn("loops for ever", ap.paste_problem(384, 384, 9, "whole"))
        self.assertIn("loops for ever", ap.paste_problem(24, 140, 5, "face lower"), "narrower but not shorter")
        self.assertIn("height", ap.paste_problem(256, 256, 9, "face lower"))
        self.assertIn("mip level", ap.paste_problem(512, 256, 1, "face lower"))


class CatalogueTests(unittest.TestCase):
    def setUp(self):
        with open(CATALOGUE, encoding="utf-8") as f:
            self.data = json.load(f)

    def test_the_repository_catalogue(self):
        cat = marksrows.load_catalogue(CATALOGUE)
        self.assertEqual(sorted(cat.races), sorted(ap.RACE_FILES.values()))

        for race in cat.races.values():
            self.assertFalse(race.colours[2].glow, f"{race.race}: colour 3 is the paint colour")
            self.assertTrue(race.colours[0].glow and race.colours[1].glow)

        self.assertEqual(cat.eye_names("BloodElf")[3:], ["Blood Red", "Unholy Green"])
        self.assertEqual(len(cat.sha1), 40)

    def test_errors(self):
        for change, message in (
                (lambda d: d["races"].pop("Eredar"), "no entry for Eredar"),
                (lambda d: d["races"]["Human"]["designs"].pop(), "exactly 4 designs"),
                (lambda d: d["races"]["Human"]["colours"][2].update(glow=True), "never glows"),
                (lambda d: d["races"]["Human"]["designs"][0].update(key="Bad Key"), "letters and digits"),
                (lambda d: d["races"]["Human"]["designs"][1].update(key=d["races"]["Human"]["designs"][0]["key"]),
                 "twice"),
                (lambda d: d["races"]["Human"]["eyes"][0].update(hex="red"), "#RRGGBB"),
                (lambda d: d.update(death_knight_eyes=[]), "eyes 4 and 5")):
            data = copy.deepcopy(self.data)
            change(data)

            with self.assertRaisesRegex(marksrows.MarksError, message):
                marksrows.parse_catalogue(data)


class ManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.catalogue = marksrows.load_catalogue(CATALOGUE)
        cls.path = sc.write_manifest(cls.tmp.name, cls.catalogue, {("NightElf", 1): (True, [1, 2, 4]),
                                                                   ("Orc", 0): (False, [5])})

        with open(cls.path, encoding="utf-8") as f:
            cls.data = json.load(f)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_loads_and_checks_the_files(self):
        manifest = marksrows.load_manifest(self.path, self.catalogue, partial=True)
        night = manifest.entries[("NightElf", 1)]
        self.assertEqual(sorted(night.looks), list(range(1, 13)))
        self.assertEqual(night.looks[1].texture, ap.mark_name("NightElf", 1, "MoonwellSigils", "EluneBlue"))
        self.assertIsNone(night.looks[3].glow, "the paint colour")
        self.assertEqual(sorted(night.eyes), [1, 2, 4])
        self.assertEqual(manifest.entries[("Orc", 0)].looks, {})

    def bad(self, change, message):
        data = copy.deepcopy(self.data)
        change(data)
        path = os.path.join(self.tmp.name, "bad.json")

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)

        with self.assertRaisesRegex(marksrows.MarksError, message):
            marksrows.load_manifest(path, self.catalogue, partial=True)

    def test_errors(self):
        night = 0 if self.data["races"][0]["race"] == "NightElf" else 1
        self.bad(lambda d: d.update(catalogue_sha1="0" * 40), "another catalogue")
        self.bad(lambda d: d["races"][night]["looks"].pop(), "all 12 or none")
        self.bad(lambda d: d["races"][night]["looks"][0].update(look=2), "look 1")
        self.bad(lambda d: d["races"][night]["looks"][0].update(texture="Character\\Other.blp"), "texture must be")
        self.bad(lambda d: d["races"][night]["looks"][2].update(glow="x_Glow.blp"), "paint colour")
        self.bad(lambda d: d["races"][night]["looks"][0].update(sha1="0" * 40), "not the file")
        self.bad(lambda d: d["races"][night]["looks"][0].update(file="../escape.blp"), "relative path")
        self.bad(lambda d: d["races"][night]["eyes"][0].update(colour="BloodRed"), "eye 1 is")
        self.bad(lambda d: d["races"].append(dict(d["races"][night])), "listed twice")

    def test_markforge_form(self):
        """markforge.py build's own manifest (bleakhold-marks/1) reads as the same marks, its names checked against
        the catalogue."""
        folder = os.path.join(self.tmp.name, "markforge")
        entries = {("NightElf", 1): (True, [1, 2, 4]), ("Orc", 0): (False, [5])}
        path = sc.write_manifest(folder, self.catalogue, entries, markforge_form=True)
        contract = marksrows.load_manifest(self.path, self.catalogue, partial=True)
        mine = marksrows.load_manifest(path, self.catalogue, partial=True)
        self.assertEqual(sorted(mine.entries), sorted(contract.entries))

        for key, marks in contract.entries.items():
            have = mine.entries[key]
            self.assertEqual({n: (k.texture, k.glow, k.sha1) for n, k in have.looks.items()},
                             {n: (k.texture, k.glow, k.sha1) for n, k in marks.looks.items()})
            self.assertEqual({n: (e.colour, e.texture) for n, e in have.eyes.items()},
                             {n: (e.colour, e.texture) for n, e in marks.eyes.items()})

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        night = 0 if data["race_sexes"][0]["race_file"] == "NightElf" else 1

        def bad(change, message):
            changed = copy.deepcopy(data)
            change(changed)
            other = os.path.join(folder, "bad.json")

            with open(other, "w", encoding="utf-8") as f:
                json.dump(changed, f)

            with self.assertRaisesRegex(marksrows.MarksError, message):
                marksrows.load_manifest(other, self.catalogue, partial=True)

        bad(lambda d: d.update(fixture=True), "fixture")
        bad(lambda d: d["gates"].update(passed=False), "gates did not pass")
        bad(lambda d: d.update(catalogue_version=99), "catalogue_version")
        bad(lambda d: d["race_sexes"][night]["marks"][0].update(colour_name="Other"), "colour_name")
        bad(lambda d: d["race_sexes"][night]["marks"][0].update(hex="#000000"), "hex")
        bad(lambda d: d["race_sexes"][night]["marks"][2].update(glow_texture="x_Glow.blp"), "paint colour")
        bad(lambda d: d["race_sexes"][night]["marks"][0].update(design=2), "design_key")
        bad(lambda d: d["race_sexes"][night]["eyes"][2].update(dk_only=False), "dk_only")
        bad(lambda d: d["race_sexes"][night].update(race=1), "race 1")
        bad(lambda d: d["race_sexes"][night]["marks"][0].update(sha1="0" * 40), "not the file")
        # a dev build from a package folder, or one that did not read every underwear, is never shipped
        bad(lambda d: d.update(source="folder"), "built from 'folder', not the realm's client and patches")
        bad(lambda d: d.pop("source"), "built from None")
        bad(lambda d: d["race_sexes"][night].update(garment_missing=31), "garment_missing 31")
        bad(lambda d: d["race_sexes"][night].pop("garment_missing"), "garment_missing None")

    def test_a_partial_manifest_needs_marks_partial(self):
        """customize --marks needs every race-sex of the catalogue with all 12 looks and eyes 1-5 (the picker data
        offers them all); --marks-partial (a dev run) takes fewer."""
        for form in (False, True):
            folder = os.path.join(self.tmp.name, f"partial-{form}")
            path = sc.write_manifest(folder, self.catalogue, {("NightElf", 1): (True, [1, 2, 3, 4, 5])},
                                     markforge_form=form)

            with self.assertRaisesRegex(marksrows.MarksError, "1 of 24 race-sexes have all 12 looks and eyes 1-5 "
                                                              ".*--marks-partial"):
                marksrows.load_manifest(path, self.catalogue)

            self.assertEqual(sorted(marksrows.load_manifest(path, self.catalogue, partial=True).entries),
                             [("NightElf", 1)])

    def test_a_full_manifest_loads_without_marks_partial(self):
        entries = {(race, sex): (True, list(range(1, ap.EYES + 1))) for race in self.catalogue.races
                   for sex in ap.SEXES}
        folder = os.path.join(self.tmp.name, "full")
        path = sc.write_manifest(folder, self.catalogue, entries, markforge_form=True)
        manifest = marksrows.load_manifest(path, self.catalogue)
        self.assertEqual(len(manifest.entries), 24)
        self.assertEqual(marksrows.coverage_problems(manifest, self.catalogue), [])
        entries[("Eredar", 1)] = (True, [1, 2, 3])  # no Death Knight eyes
        path = sc.write_manifest(os.path.join(self.tmp.name, "full-but"), self.catalogue, entries, markforge_form=True)

        with self.assertRaisesRegex(marksrows.MarksError, "23 of 24 .*Eredar Female: 12 looks, eyes \\[1, 2, 3\\]"):
            marksrows.load_manifest(path, self.catalogue)

    def test_mark_file_rules(self):
        good = sc.mark_blp()
        marksrows.check_mark_file(good, "mark")
        marksrows.check_glow_file(good, sc.mark_blp(9, glow=True), "mark")
        small = sc.eye_blp((1, 2, 3))

        with self.assertRaisesRegex(marksrows.MarksError, "512x512 palette"):
            marksrows.check_mark_file(small, "mark")

        other = bytearray(sc.mark_blp(9, glow=True))
        other[-1] ^= 0xFF  # one alpha byte of the last level

        with self.assertRaisesRegex(marksrows.MarksError, "alpha"):
            marksrows.check_glow_file(good, bytes(other), "mark")

    def test_full_manifest(self):
        full = marksrows.full_manifest(self.catalogue)
        self.assertEqual(len(full.entries), 24)
        self.assertEqual(sorted(full.entries[("HighElf", 0)].eyes), [1, 2, 3, 4, 5])
        self.assertIsNone(full.entries[("HighElf", 0)].looks[3].glow)


class RowTests(unittest.TestCase):
    def setUp(self):
        self.cs, self.cfhs = package_tables()
        self.looks = marksrows.full_manifest(marksrows.load_catalogue(CATALOGUE)).entries[("BloodElf", 0)].looks

    def test_marks_on_a_race_with_features_rows(self):
        before = len(self.cs.rows)
        added = marksrows.add_marks(self.cs, self.cfhs, 10, 0, 3, self.looks)
        base_rows = 3 * 6 + 1  # 3 values at 6 hair colours, plus the repeated row
        self.assertEqual(added.feature_rows, 12 * base_rows)
        self.assertEqual(added.base_rows, 0)
        self.assertEqual(len(self.cs.rows), before + 12 * base_rows)
        self.assertEqual(marksrows.base_count(self.cfhs, 10, 0), 39)
        values = sorted({self.cfhs.get(r, "variationID") for r in self.cfhs.rows if self.cfhs.get(r, "raceID") == 10
                         and self.cfhs.get(r, "sexID") == 0})
        self.assertEqual(values, list(range(39)))
        geosets = {self.cfhs.get(r, "variationID"): self.cfhs.get(r, "geoset[0]") for r in self.cfhs.rows
                   if self.cfhs.get(r, "raceID") == 10 and self.cfhs.get(r, "sexID") == 0}
        self.assertEqual(geosets[ap.features_value(7, 2, 3)], geosets[2], "the base value's geosets")

    def test_marks_on_a_race_without_features_rows(self):
        added = marksrows.add_marks(self.cs, self.cfhs, 10, 1, 2, self.looks)
        self.assertEqual(added.base_rows, 2 * 6)
        flags = marksrows.hair_colour_flags(self.cs, 10, 1)
        self.assertEqual(flags, {0: 0x11, 1: 0x11, 2: 0x11, 3: 0x5, 4: 0x11, 5: 0x11})
        self.assertEqual(marksrows.features_problems(self.cs, self.cfhs, {10}), [])

    def test_counts_for_both_kinds_equal_the_styles(self):
        marksrows.add_marks(self.cs, self.cfhs, 10, 1, 2, self.looks)

        for dk in (False, True):
            for colour in range(6):
                rows = [r for r in self.cs.rows if (self.cs.get(r, "raceID"), self.cs.get(r, "sexID"),
                                                    self.cs.get(r, "baseSection"), self.cs.get(r, "colorIndex"))
                        == (10, 1, 2, colour) and ap.selectable(self.cs.get(r, "flags"), ap.CREATION, dk)]

                if dk or colour != 3:
                    self.assertEqual(len(rows), 26, (dk, colour))

    def test_refusals(self):
        with self.assertRaisesRegex(marksrows.MarksError, "all 12 or none"):
            marksrows.add_marks(self.cs, self.cfhs, 10, 0, 3, {1: self.looks[1]})

        with self.assertRaisesRegex(marksrows.MarksError, "above 255"):
            big = DbcTable.empty(self.cfhs.schema)
            marksrows.add_marks(self.cs, big, 10, 0, 20, self.looks)

        marksrows.add_marks(self.cs, self.cfhs, 10, 0, 3, self.looks)

        with self.assertRaisesRegex(marksrows.MarksError, "already there"):
            marksrows.add_marks(self.cs, self.cfhs, 10, 0, 3, self.looks)

    def test_eyes(self):
        eyes = marksrows.full_manifest(marksrows.load_catalogue(CATALOGUE)).entries[("BloodElf", 0)].eyes
        added = marksrows.add_eyes(self.cs, 10, 0, eyes)
        faces = [r for r in self.cs.rows if (self.cs.get(r, "raceID"), self.cs.get(r, "sexID"),
                                             self.cs.get(r, "baseSection")) == (10, 0, 1)]
        player_faces = 4 * 7  # faces 0-3 on the seven player skins
        dk_faces = 2 * 7 + 2 * 3  # faces 4-5 on the player skins, 0 and 2 on the Death Knight skins
        self.assertEqual(added.eye_rows, 3 * player_faces + 2 * dk_faces)
        self.assertTrue(all(self.cs.get(r, "variationIndex") <= 5 * 40 + 39 for r in faces))

        with self.assertRaisesRegex(marksrows.MarksError, "already there"):
            marksrows.add_eyes(self.cs, 10, 0, eyes)

    def test_features_gate(self):
        hole = next(r for r in self.cs.rows if (self.cs.get(r, "raceID"), self.cs.get(r, "sexID"),
                                                self.cs.get(r, "baseSection"), self.cs.get(r, "variationIndex"),
                                                self.cs.get(r, "colorIndex")) == (11, 0, 2, 2, 4))
        self.cs.rows.remove(hole)
        problems = marksrows.features_problems(self.cs, self.cfhs, {11})
        self.assertEqual(len(problems), 1)
        self.assertIn("(2, 4)", problems[0])


if __name__ == "__main__":
    unittest.main()
