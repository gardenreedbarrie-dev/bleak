"""A character customization package merged before the races are added (raceforge.py build --customization)."""

import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL_DIR = os.path.dirname(HERE)
MPQPACK_DIR = os.path.join(os.path.dirname(TOOL_DIR), "MpqPack")

for path in (TOOL_DIR, MPQPACK_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

import mpqpack  # noqa: E402
from rflib import customize, schema_access  # noqa: E402
from rflib.dbc import DbcTable, to_signed  # noqa: E402
from tests import synth  # noqa: E402


def run_tool(*args):
    return subprocess.run([sys.executable, "-I", os.path.join(TOOL_DIR, "raceforge.py"), *args], capture_output=True, text=True)


def read(out_dir, name, kind="client"):
    folder = os.path.join(out_dir, "client", "DBFilesClient") if kind == "client" else os.path.join(out_dir, "server", "dbc")
    return DbcTable.read(os.path.join(folder, f"{name}.dbc"), schema_access.get(name))


def textures(table, race):
    return sorted(table.get_str(r, "textureName[0]") for r in table.rows if table.get(r, "raceID") == race)


# A made-up package: more Blood Elf and Human faces (rows out of order on purpose), rows for a race the user does not
# have (30) and for one RaceForge adds (22), a Blood Elf barber style whose id clashes with a kept Orc row, a helmet
# mask with stray high bits, NPC display extras, and art.
def write_package(root):
    dbc = os.path.join(root, "DBFilesClient")
    os.makedirs(dbc)
    sections = synth.Packer("CharSections")
    section_id = 50000

    for race, name in ((10, "BloodElf"), (1, "Human")):
        for sex in (1, 0):
            for variation in (2, 0, 1):
                sections.add(id=section_id, raceID=race, sexID=sex, baseSection=1, flags=1, variationIndex=variation, colorIndex=0,
                             **{"textureName[0]": f"Character\\{name}\\HD\\Face{sex}{variation}.blp"})
                section_id += 1

            sections.add(id=section_id, raceID=race, sexID=sex, baseSection=0, flags=1, variationIndex=0, colorIndex=0,
                         **{"textureName[0]": f"Character\\{name}\\HD\\Skin{sex}.blp", "textureName[1]": f"Character\\{name}\\HD\\Tattoo{sex}.blp"})
            section_id += 1

    sections.add(id=section_id, raceID=30, sexID=0, baseSection=0, **{"textureName[0]": "Character\\Other\\Skin.blp"})
    sections.add(id=section_id + 1, raceID=22, sexID=0, baseSection=0, **{"textureName[0]": "Character\\Clash\\Skin.blp"})

    hair = synth.Packer("CharHairGeosets")
    hair.add(id=7, raceID=10, sexID=0, variationID=0, geosetID=0, showscalp=1)
    hair.add(id=8, raceID=10, sexID=0, variationID=1, geosetID=5)

    barber = synth.Packer("BarberShopStyle")
    barber.add(id=1, type=0, costModifier=1.0, race=10, sex=0, data=0, **synth.loc("displayName", "HD Braid"), **synth.loc("description", "Long"))
    barber.add(id=999, type=0, costModifier=1.0, race=10, sex=1, data=0, **synth.loc("displayName", "HD Bun"), **synth.loc("description", ""))

    helmets = synth.Packer("HelmetGeosetVisData")
    helmets.add(id=1, **{"hideGeoset[0]": 0xFFFFFAEF})  # every race but a few: bit 22 set, Blood Elf's (10) not
    helmets.add(id=500, **{"hideGeoset[0]": 1 << 10})

    extras = synth.Packer("CreatureDisplayInfoExtra")
    extras.add(id=40, displayRaceID=10, displaySexID=1, skinID=2, bakeName="BakedNpc40.blp")

    for packer in (sections, hair, barber, helmets, extras):
        with open(os.path.join(dbc, packer.filename.split("\\")[-1]), "wb") as f:
            f.write(packer.pack())

    art = {
        "Character\\BloodElf\\HD\\Face10.blp": b"face" * 100,
        "Character\\BloodElf\\Male\\BloodElfMale.m2": b"MD20" + bytes(400),
        "Textures\\BakedNPCTextures\\BakedNpc40.blp": b"npc" * 50,
    }

    for name, data in art.items():
        path = os.path.join(root, *name.split("\\"))
        os.makedirs(os.path.dirname(path), exist_ok=True)

        with open(path, "wb") as f:
            f.write(data)

    with open(os.path.join(root, "README.md"), "w") as f:
        f.write("not art")

    os.makedirs(os.path.join(root, ".git"))

    with open(os.path.join(root, ".git", "HEAD"), "w") as f:
        f.write("not art either")

    return art


class CustomizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.stock = os.path.join(cls.tmp.name, "stock")
        cls.package = os.path.join(cls.tmp.name, "package")
        cls.out = os.path.join(cls.tmp.name, "out")
        synth.write_folder(cls.stock)
        cls.art = write_package(cls.package)
        cls.result = run_tool("build", "--dbc", cls.stock, "--out", cls.out, "--mpq", "--customization", cls.package)

        with open(os.path.join(cls.out, "report.txt"), encoding="utf-8") as f:
            cls.report = f.read()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def stock_table(self, name):
        return DbcTable.read(os.path.join(self.stock, f"{name}.dbc"), schema_access.get(name))

    def test_build_passes_every_check(self):
        self.assertEqual(self.result.returncode, 0, self.result.stdout + self.result.stderr)
        self.assertNotIn("[FAIL]", self.report)

        for name in customize.TABLES:
            if name not in ("CharacterFacialHairStyles", "EmotesTextSound"):
                self.assertIn(f"[PASS] customization: {name} merged", self.report)

    def test_package_races_replace_the_users_rows(self):
        sections = read(self.out, "CharSections")
        self.assertEqual(textures(sections, 10), sorted(f"Character\\BloodElf\\HD\\{n}" for n in
                                                        ["Face00.blp", "Face01.blp", "Face02.blp", "Face10.blp", "Face11.blp", "Face12.blp", "Skin0.blp", "Skin1.blp"]))
        self.assertEqual(textures(sections, 1), sorted(t.replace("BloodElf", "Human") for t in textures(sections, 10)))
        self.assertEqual(textures(sections, 2), textures(self.stock_table("CharSections"), 2), "races the package lacks keep their rows")
        self.assertNotIn("Character\\Other\\Skin.blp", textures(sections, 30))
        self.assertNotIn("Character\\Clash\\Skin.blp", textures(sections, 22))
        self.assertIn("left out", self.report)

    def test_new_races_get_the_merged_options(self):
        sections = read(self.out, "CharSections")
        self.assertEqual(textures(sections, 22), textures(sections, 10))
        tattoo = [sections.get_str(r, "textureName[1]") for r in sections.rows if sections.get(r, "raceID") == 22 and sections.get(r, "baseSection") == 0]
        self.assertIn("Character\\BloodElf\\HD\\Tattoo0.blp", tattoo)

        hair = read(self.out, "CharHairGeosets")
        self.assertEqual(sorted((hair.get(r, "variationID"), hair.get(r, "geosetID")) for r in hair.rows if hair.get(r, "raceID") == 22), [(0, 0), (1, 5)])

        barber = read(self.out, "BarberShopStyle")
        names = sorted(barber.get_loc(r, "displayName")[0] for r in barber.rows if barber.get(r, "race") == 22)
        self.assertEqual(names, ["HD Braid", "HD Bun"])

    def test_sorted_and_unique(self):
        sections = read(self.out, "CharSections")
        key = [tuple(to_signed(sections.get(r, c)) for c in customize.CHAR_SECTIONS_KEY) for r in sections.rows]
        self.assertEqual(key, sorted(key))

        for name in ("CharSections", "CharHairGeosets", "BarberShopStyle", "HelmetGeosetVisData", "CreatureDisplayInfoExtra"):
            table = read(self.out, name)
            ids = [to_signed(r[0]) for r in table.rows]
            self.assertEqual(len(ids), len(set(ids)), name)

    def test_clashing_barber_id_is_renumbered(self):
        barber = read(self.out, "BarberShopStyle")
        by_id = barber.by_id()
        orc_row_1 = by_id[1]
        self.assertEqual(barber.get(orc_row_1, "race"), 1, "the user's row 1 is kept")
        braid = [r for r in barber.rows if barber.get_loc(r, "displayName")[0] == "HD Braid" and barber.get(r, "race") == 10]
        self.assertEqual(len(braid), 1)
        self.assertGreater(to_signed(braid[0][0]), 999)
        self.assertEqual(barber.get_loc(braid[0], "description")[0], "Long", "strings moved into the merged string block")
        self.assertIn(999, by_id)

    def test_helmet_bits_follow_the_template_exactly(self):
        helmets = read(self.out, "HelmetGeosetVisData").by_id()
        mask = helmets[1][1]
        self.assertFalse(mask & (1 << 22), "stray High Elf bit cleared: Blood Elves do not hide this")
        self.assertEqual(mask & ~((1 << 22) | (1 << 23)), 0xFFFFFAEF & ~((1 << 22) | (1 << 23)))
        self.assertTrue(helmets[500][1] & (1 << 22))
        self.assertIn(4, helmets, "the user's other rows are kept")

    def test_npc_display_extras_are_written_for_client_and_server(self):
        for kind in ("client", "server"):
            extras = read(self.out, "CreatureDisplayInfoExtra", kind)
            self.assertEqual(extras.get_str(extras.by_id()[40], "bakeName"), "BakedNpc40.blp")

    def test_dbc_archive_and_art_archive(self):
        with mpqpack.MpqArchive(os.path.join(self.out, "client", "patch-R.MPQ")) as archive:
            names = archive.names()
            self.assertIn("DBFilesClient\\CreatureDisplayInfoExtra.dbc", names)
            self.assertFalse(any(n.startswith("Character") for n in names))

        # The default art name is a digit: no realm or Reforged patch uses one, and it loads after the stock patch-3.
        with mpqpack.MpqArchive(os.path.join(self.out, "client", "patch-6.MPQ")) as archive:
            self.assertEqual(archive.verify().problems, [])
            self.assertEqual(sorted(archive.names()), sorted(self.art))

            for name, data in self.art.items():
                self.assertEqual(archive.read(name), data)

        self.assertEqual(sorted(os.listdir(os.path.join(self.out, "client"))), ["DBFilesClient", "patch-6.MPQ", "patch-R.MPQ"])
        self.assertIn("patch-6.MPQ: 3 art files", self.report)
        self.assertIn("[PASS] art archive names (patch-6.MPQ) checked against taken_patches.json", self.report)

    def test_validate_command_uses_the_merged_starting_point(self):
        result = run_tool("validate", "--dbc", self.stock, "--out", self.out)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("merged starting point", result.stdout)

    def test_bad_uses_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = os.path.join(tmp, "empty")
            os.makedirs(empty)
            result = run_tool("build", "--dbc", self.stock, "--out", os.path.join(tmp, "out"), "--customization", empty)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("no customization tables", result.stderr)

            result = run_tool("build", "--dbc", self.stock, "--out", os.path.join(self.package, "out"), "--customization", self.package)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("must not be inside", result.stderr)

            result = run_tool("build", "--dbc", self.stock, "--out", os.path.join(tmp, "out2"), "--mpq", "--customization", self.package, "--art-letters", "")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--art-letters", result.stderr)

    def test_tables_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "out")
            result = run_tool("build", "--dbc", self.stock, "--out", out, "--mpq", "--customization", self.package, "--no-art")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(sorted(os.listdir(os.path.join(out, "client"))), ["DBFilesClient", "patch-R.MPQ"])


if __name__ == "__main__":
    unittest.main()
