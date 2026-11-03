"""raceforge.py picker-data: package_counts.json, the model of the client's lists, the generated Lua (schema, width,
Lua 5.1), --check, and that the numbers equal what customize's own merge gives."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL_DIR = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(TOOL_DIR))

if TOOL_DIR not in sys.path:
    sys.path.insert(0, TOOL_DIR)

from rflib import appearance as ap  # noqa: E402
from rflib import curation as curmod  # noqa: E402
from rflib import marksrows, picker, realm_customize as rc, schema_access  # noqa: E402
from rflib.dbc import DbcTable  # noqa: E402
from tests import synth_customize as sc  # noqa: E402

RACEFORGE = os.path.join(TOOL_DIR, "raceforge.py")
CUSTOMIZE = os.path.join(TOOL_DIR, "customize")
WOWLUA = os.path.join(REPO, "Tools", "UiLint", "build", "wowlua")


def run(*args):
    return subprocess.run([sys.executable, "-I", RACEFORGE, *args], capture_output=True, text=True)


def lookup(count, key):
    """A list index of the data: a number, or {default, key: index}."""
    return count if isinstance(count, int) else count.get(key, count["default"])


def synthetic_counts() -> dict:
    data = sc.tables(True)
    cs = DbcTable.from_bytes(data["CharSections"], schema_access.get("CharSections"))
    cfhs = DbcTable.from_bytes(data["CharacterFacialHairStyles"], schema_access.get("CharacterFacialHairStyles"))
    return json.loads(picker.counts_text(picker.counts_from_tables(cs, cfhs, sc.COMMIT)))


class CountsTests(unittest.TestCase):
    def test_round_trip(self):
        counts = synthetic_counts()
        cs, cfhs = picker.tables_from_counts(counts)
        package = DbcTable.from_bytes(sc.tables(True)["CharSections"], schema_access.get("CharSections"))
        want = {}

        for row in package.rows:
            if package.get(row, "raceID") in ap.TAKEN_RACES:
                want[tuple(package.get(row, c) for c in ap.KEY)] = package.get(row, "flags")

        got = {tuple(cs.get(r, c) for c in ap.KEY): cs.get(r, "flags") for r in cs.rows}
        self.assertEqual(got, want, "every key with the flags of its last row")
        self.assertEqual(counts["features"]["10,0"], 3)
        self.assertNotIn("9,0", counts["features"], "Goblin is not taken")

    def test_ranges(self):
        self.assertEqual(picker._ranges([5, 1, 2, 3, 7, 8]), "1-3,5,7-8")
        self.assertEqual(picker._expand("1-3,5,7-8"), [1, 2, 3, 5, 7, 8])

    def test_the_repository_counts_are_numbers_of_the_pinned_package(self):
        counts = picker.load_counts(os.path.join(CUSTOMIZE, "package_counts.json"))
        cur = curmod.load(os.path.join(CUSTOMIZE, "curation.json"))
        self.assertEqual(counts["package"], cur.commit)
        text = json.dumps(counts["rows"]) + json.dumps(counts["features"])
        self.assertNotIn("Character", text)
        self.assertNotIn(".blp", text.lower())


class ModelTests(unittest.TestCase):
    """The lists against the client's rules, on the repository's numbers of the real package."""

    @classmethod
    def setUpClass(cls):
        cls.counts = picker.load_counts(os.path.join(CUSTOMIZE, "package_counts.json"))
        cls.cur = curmod.load(os.path.join(CUSTOMIZE, "curation.json"))
        cls.catalogue = marksrows.load_catalogue(os.path.join(CUSTOMIZE, "catalogue.json"))
        cls.staged = picker.stage_two(cls.counts, cls.cur, cls.catalogue)
        cls.glue = picker.model(cls.counts, cls.cur, cls.catalogue, ap.CREATION, cls.staged)

    def test_counts_of_the_study(self):
        glue = self.glue
        self.assertEqual(len(glue["BloodElf"][1]["normal"]["skins"]), 53)
        self.assertEqual(len(glue["BloodElf"][1]["deathKnight"]["skins"]), 56)
        self.assertEqual(len(glue["Draenei"][1]["normal"]["skins"]), 28, "skin 21 is barbershop-only and hidden")
        self.assertEqual(len(glue["Human"][1]["normal"]["skins"]), 18, "skin 22 hidden: painted clothing")
        self.assertEqual(glue["NightElf"][1]["normal"]["features"], 13 * 19)
        self.assertEqual(glue["Tauren"][0]["normal"]["hairColors"], 3)

    def test_high_elf_and_eredar(self):
        high = self.glue["HighElf"]

        for sex in (0, 1):
            self.assertEqual(high[sex]["normal"]["skins"], list(range(10)), "keep_skins")
            self.assertEqual(high[sex]["deathKnight"]["skins"], list(range(10)) + [63, 64, 65])
            self.assertEqual(high[sex]["B"], self.glue["BloodElf"][sex]["B"])

        self.assertEqual(self.glue["Eredar"][0]["normal"]["skins"], self.glue["Draenei"][0]["normal"]["skins"])
        self.assertEqual(high[0]["designs"][0], "Silver Covenant Sigils")

    def test_faces_and_eyes(self):
        human = self.glue["Human"][0]
        normal = human["normal"]
        faces = normal["faceWalks"][lookup(normal["faceWalkOfSkin"], 0) - 1]
        bases = sorted({v % 40 for v in faces})
        self.assertEqual(len(bases), 15)
        self.assertEqual(sorted({v // 40 for v in faces}), [0, 1, 2, 3], "players: eyes 0-3")
        dk = human["deathKnight"]
        self.assertEqual(sorted({v // 40 for w in dk["faceWalks"] for v in w}), [0, 4, 5], "Death Knights: 0, 4, 5")
        self.assertEqual(sorted({v % 40 for v in dk["skinSets"][lookup(dk["skinSetOfFace"], 0) - 1]}), [26, 27, 28])

    def test_death_knight_walks(self):
        """The review's Human male Death Knight: the face arrows reach the faces of the normal skins (12-23, 36-38) and
        of the Death Knight skins (0, 2, 11) with eyes 0, 4 and 5 from any skin they can pick; the skin arrows reach the
        13 normal skins with face 12 and skins 26-28 with face 0."""
        dk = self.glue["Human"][0]["deathKnight"]

        for skin in dk["skins"]:
            walk = dk["faceWalks"][lookup(dk["faceWalkOfSkin"], skin) - 1]
            self.assertEqual(len(walk), 54, skin)
            self.assertEqual(sorted({v % 40 for v in walk}), [0, 2, 11] + list(range(12, 24)) + [36, 37, 38], skin)

        def skins_of(face):
            return dk["skinSets"][lookup(dk["skinSetOfFace"], face) - 1]

        self.assertEqual(skins_of(12), list(range(10)) + [15, 16, 17])
        self.assertEqual(skins_of(12 + 40 * 4), skins_of(12))
        self.assertEqual(skins_of(0), [26, 27, 28])
        self.assertEqual(skins_of(11 + 40 * 5), [26, 27, 28])
        self.assertEqual(dk["skins"], list(range(10)) + [15, 16, 17, 26, 27, 28])
        barber = picker.model(self.counts, self.cur, self.catalogue, ap.WORLD, self.staged)["Human"][0]["deathKnight"]
        self.assertEqual(sorted(barber["skinSets"]), [list(range(10)) + [15, 16, 17], [26, 27, 28]])

    def test_count_tables(self):
        self.assertEqual(picker._count({1: 5, 2: 5}), 5)
        self.assertEqual(picker._count({1: 5, 2: 5, 3: 2}), {"default": 5, 3: 2})
        self.assertEqual(picker._count({}), 0)

    def test_barber_rules(self):
        barber = picker.model(self.counts, self.cur, self.catalogue, ap.WORLD, self.staged)
        text = picker.render(self.counts, self.cur, self.catalogue, "barber", self.staged)
        self.assertNotIn("faceWalks", text)
        self.assertNotIn("skinSetOfFace", text, "the barbershop cannot read the face")
        draenei = barber["Draenei"][1]["normal"]["skins"]
        self.assertNotIn(21, draenei, "hidden, so not even the barbershop")
        self.assertIn(63, barber["BloodElf"][1]["deathKnight"]["skins"])


# --- the client's arrows, written again from CharacterComponent.cpp for the check below (not picker.Walk) ----------


def flags_match(flags: int, selection: int) -> bool:
    """ComponentFlagsMatch (WoW/Common/ComponentCore/ComponentUtils.cpp) for COMPONENT_SELECTION_0 to _3:
    GetSelectionFromContext gives 0 / 1 at creation (COMPONENT_CONTEXT_0) and 2 / 3 at the barbershop
    (COMPONENT_CONTEXT_1), the second of each for a Death Knight."""
    if selection == 0:
        return bool(flags & 0x1) and not flags & 0xC
    if selection == 1:
        return bool(flags & 0x1) and bool(flags & 0x14) and not flags & 0x8
    if selection == 2:
        return bool(flags & 0x3) and not flags & 0xC
    return bool(flags & 0x3) and bool(flags & 0x14) and not flags & 0x8


class ClientTable:
    """One race and sex of BuildComponentArray's lookup, from a CharSections table in key order: a section's
    variations run to its highest variation, a variation's colours to its highest colour, and a (variation, colour)
    holds the last row of its key (ComponentGetSectionsRecord: nothing out of range, nothing where no row is)."""

    def __init__(self, cs: DbcTable, race: int, sex: int):
        self.variations, self.colours, self.records = {}, {}, {}

        for row in cs.rows:
            if cs.get(row, "raceID") != race or cs.get(row, "sexID") != sex:
                continue

            section, variation, colour = (cs.get(row, c) for c in ("baseSection", "variationIndex", "colorIndex"))
            self.variations[section] = max(self.variations.get(section, 0), variation + 1)
            self.colours[(section, variation)] = max(self.colours.get((section, variation), 0), colour + 1)
            self.records[(section, variation, colour)] = cs.get(row, "flags")

    def num_colors(self, section: int, variation: int) -> int:
        return self.colours.get((section, variation), 0)

    def fits(self, selection: int, section: int, variation: int, colour: int) -> bool:
        if variation >= self.variations.get(section, 0) or colour >= self.num_colors(section, variation):
            return False

        flags = self.records.get((section, variation, colour))
        return flags is not None and flags_match(flags, selection)


def set_next_skin_fits(t: ClientTable, selection: int, face: int, skin: int) -> bool:
    """SetNextSkin's test of a skin: its skin row, the current face on it and its underwear (COMPONENT_CONTEXT_0
    and _1 check the underwear)."""
    return t.fits(selection, ap.SKIN, 0, skin) and t.fits(selection, ap.FACE, face, skin) \
        and t.fits(selection, ap.UNDERWEAR, 0, skin)


def set_next_face_fits(t: ClientTable, selection: int, face: int, color_offset: int) -> bool:
    """SetNextFace's inner loop for faceID = face: for (i = 0; i < numColors; i = skinID + 1) with
    skinID = (i + colorOffset) % numColors, until a skin fits the face (with the guard of BleakholdCustomize.h)."""
    num_colors = t.num_colors(ap.FACE, face)
    i, guard = 0, 0

    while i < num_colors and guard <= num_colors:
        skin_id = (i + color_offset) % num_colors

        if t.fits(selection, ap.FACE, face, skin_id) and t.fits(selection, ap.SKIN, 0, skin_id) \
                and t.fits(selection, ap.UNDERWEAR, 0, skin_id):
            return True

        i, guard = skin_id + 1, guard + 1

    return False


def mock_tables(cs: DbcTable) -> str:
    """The glue mock's tables (Tools/UiLint/glue/customize_stock.lua, CZ.tables) of every race, sex and class kind at
    creation, from ClientTable: skins (skin and underwear rows fit and some face fits on it), fits[skin][face],
    faceColors (each face's colour count, whoever may pick its rows), numFaces and numSkins. A Lua chunk returning a
    list."""
    out = ["return {"]

    for race in sorted(set(ap.TAKEN_RACES) | set(ap.CLONES)):
        for sex in ap.SEXES:
            t = ClientTable(cs, race, sex)
            num_faces, num_skins = t.variations.get(ap.FACE, 0), t.num_colors(ap.SKIN, 0)

            for kind, selection in (("normal", 0), ("deathknight", 1)):
                fits = {s: [f for f in range(num_faces) if t.fits(selection, ap.FACE, f, s)] for s in range(num_skins)
                        if t.fits(selection, ap.SKIN, 0, s) and t.fits(selection, ap.UNDERWEAR, 0, s)}
                skins = [s for s, faces in fits.items() if faces]
                out.append(f'{{ race = "{ap.RACE_FILES[race]}", sex = {sex}, kind = "{kind}", '
                           f'numFaces = {num_faces}, numSkins = {num_skins},')
                out.append("  skins = { " + ", ".join(map(str, skins)) + " },")
                out.append("  fits = {")
                out += [f"    [{s}] = {{ " + ", ".join(f"[{f}] = true" for f in fits[s]) + " }," for s in skins]
                out.append("  },")
                out.append("  faceColors = { " + ", ".join(f"[{f}] = {t.num_colors(ap.FACE, f)}"
                                                         for f in range(num_faces)) + " } },")

    out.append("}")
    return "\n".join(out) + "\n"


class WalkTests(unittest.TestCase):
    """For every race, sex, class kind and screen, the data's face walk from every start skin and skin walk with every
    face are what the client's arrows reach on the stage-2 tables (the review's check, here for every view)."""

    @classmethod
    def setUpClass(cls):
        cls.counts = picker.load_counts(os.path.join(CUSTOMIZE, "package_counts.json"))
        cls.cur = curmod.load(os.path.join(CUSTOMIZE, "curation.json"))
        cls.catalogue = marksrows.load_catalogue(os.path.join(CUSTOMIZE, "catalogue.json"))
        cls.staged = picker.stage_two(cls.counts, cls.cur, cls.catalogue)
        cls.models = {where: picker.model(cls.counts, cls.cur, cls.catalogue, where, cls.staged) for where in ap.WHERE}

    def test_every_view(self):
        cs = self.staged[0]
        views = 0

        for race in sorted(set(ap.TAKEN_RACES) | set(ap.CLONES)):
            for sex in ap.SEXES:
                t = ClientTable(cs, race, sex)
                num_faces, num_skins = t.variations.get(ap.FACE, 0), t.num_colors(ap.SKIN, 0)
                # a BarberShopStyle row for every skin a player or Death Knight can pick in the world
                barber_row = {s for s in range(num_skins) if t.fits(2, ap.SKIN, 0, s) or t.fits(3, ap.SKIN, 0, s)}

                for dk in (False, True):
                    for where in ap.WHERE:
                        selection = (2 if where == ap.WORLD else 0) + (1 if dk else 0)
                        view = self.models[where][ap.RACE_FILES[race]][sex]["deathKnight" if dk else "normal"]
                        at = (ap.RACE_FILES[race], sex, dk, where)
                        walks = set()

                        for face in range(num_faces):
                            want = [s for s in range(num_skins) if set_next_skin_fits(t, selection, face, s)
                                    and (where == ap.CREATION or s in barber_row)]

                            if want:
                                walks.add(tuple(want))
                                got = view["skinSets"][lookup(view["skinSetOfFace"], face) - 1]
                                self.assertEqual(got, want, (*at, "skins of face", face))

                        self.assertEqual(sorted(walks), sorted(tuple(w) for w in view["skinSets"]), at)
                        self.assertEqual(view["skins"], sorted({s for w in walks for s in w}), at)

                        if where == ap.CREATION:
                            walks = set()

                            for start in range(num_skins):
                                want = [f for f in range(num_faces) if set_next_face_fits(t, selection, f, start)]
                                walks.add(tuple(want))
                                got = view["faceWalks"][lookup(view["faceWalkOfSkin"], start) - 1]
                                self.assertEqual(got, want, (*at, "faces from skin", start))

                            self.assertEqual(sorted(walks - {()}), sorted(tuple(w) for w in view["faceWalks"]), at)

                        views += 1

        self.assertEqual(views, len(set(ap.TAKEN_RACES) | set(ap.CLONES)) * 2 * 2 * 2)

    def test_the_walk_starts_where_the_last_skin_was_chosen(self):
        """From a skin a player cannot pick (Human male 12, hidden) the face loop of the faces whose colours run to
        skin 12 visits skin 12 only: those faces drop out of the walk."""
        normal = self.models[ap.CREATION]["Human"][0]["normal"]
        from_0 = normal["faceWalks"][lookup(normal["faceWalkOfSkin"], 0) - 1]
        from_12 = normal["faceWalks"][lookup(normal["faceWalkOfSkin"], 12) - 1]
        self.assertLess(len(from_12), len(from_0))
        self.assertTrue(set(from_12) < set(from_0))


class AgreementTests(unittest.TestCase):
    """picker-data's numbers equal the lists of customize's own merge (made-up package and realm)."""

    def test_same_lists(self):
        with tempfile.TemporaryDirectory() as tmp:
            cur = curmod.load(sc.write_curation(os.path.join(tmp, "curation.json")))

        catalogue = marksrows.load_catalogue(os.path.join(CUSTOMIZE, "catalogue.json"))
        package = {n: DbcTable.from_bytes(b, schema_access.get(n)) for n, b in sc.tables(True).items()}
        base = {n: DbcTable.from_bytes(b, schema_access.get(n)) for n, b in sc.tables(False, realm=True).items()}
        base["CreatureDisplayInfoExtra"] = DbcTable.from_bytes(sc.npc_looks(),
                                                               schema_access.get("CreatureDisplayInfoExtra"))
        merged = rc.merge(base, package, cur, rc.BarberLedger(), marks=marksrows.full_manifest(catalogue),
                          catalogue=catalogue)
        cs, cfhs = merged.tables["CharSections"], merged.tables["CharacterFacialHairStyles"]
        counts = synthetic_counts()
        p_cs, p_cfhs = picker.stage_two(counts, cur, catalogue)

        for race in sorted(set(ap.TAKEN_RACES) | set(ap.CLONES)):
            for sex in (0, 1):
                for dk in (False, True):
                    for where in ap.WHERE:
                        self.assertEqual(picker.lists(cs, cfhs, race, sex, dk, where),
                                         picker.lists(p_cs, p_cfhs, race, sex, dk, where), (race, sex, dk, where))


class LuaTests(unittest.TestCase):
    def test_render_fits_the_line_limit_and_the_schema(self):
        counts = picker.load_counts(os.path.join(CUSTOMIZE, "package_counts.json"))
        cur = curmod.load(os.path.join(CUSTOMIZE, "curation.json"))
        catalogue = marksrows.load_catalogue(os.path.join(CUSTOMIZE, "catalogue.json"))
        texts = picker.outputs(REPO, counts, cur, catalogue)
        glue, barber = texts[os.path.join(REPO, picker.GLUE_FILE)], texts[os.path.join(REPO, picker.BARBER_FILE)]

        for which, text in (("glue", glue), ("barber", barber)):
            self.assertTrue(all(len(line) <= 120 for line in text.splitlines()), which)
            self.assertIn("eyeStride = 40", text)
            self.assertIn('groups = { "plain", "marked", "fel", "deathknight" }', text)

        self.assertIn("BleakholdCustomizeData = {", glue)
        self.assertIn("ns.BarberData = {", barber)
        self.assertEqual(picker.lua_value({"a b": [1, 2], 3: "x\"y"}, 0),
                         '{\n    ["a b"] = { 1, 2 },\n    [3] = "x\\"y",\n}')

    @unittest.skipUnless(os.path.isfile(WOWLUA), "Tools/UiLint/build/wowlua is not built")
    def test_the_client_lua_reads_them(self):
        for path in (picker.GLUE_FILE, picker.BARBER_FILE):
            result = subprocess.run([WOWLUA, "-p", os.path.join(REPO, path)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    @unittest.skipUnless(os.path.isfile(WOWLUA), "Tools/UiLint/build/wowlua is not built")
    def test_the_glue_rows_follow_the_arrows_on_the_real_tables(self):
        """The glue's own self-test (every race, sex and class) on the shipped BleakholdCustomizeData.lua, with the glue
        mock walking the stage-2 tables of the repository's numbers (Tools/UiLint/glue/customize_realdata.lua): every
        row follows its arrows, every view has the Eyes row and skin groups, and a Death Knight reaches the Death
        Knight skins with the face arrows and keeps to them with the skin arrows (the review's Human male Death Knight:
        54 faces and 13 skins on a normal skin, where the data once had 45 and 16)."""
        counts = picker.load_counts(os.path.join(CUSTOMIZE, "package_counts.json"))
        cur = curmod.load(os.path.join(CUSTOMIZE, "curation.json"))
        catalogue = marksrows.load_catalogue(os.path.join(CUSTOMIZE, "catalogue.json"))
        cs, _ = picker.stage_two(counts, cur, catalogue)
        glue = os.path.join(REPO, "Tools", "UiLint", "glue")

        with tempfile.TemporaryDirectory() as tmp:
            tables = os.path.join(tmp, "tables.lua")

            with open(tables, "w", encoding="utf-8") as f:
                f.write(mock_tables(cs))

            result = subprocess.run([WOWLUA, os.path.join(glue, "customize_realdata.lua"), glue,
                                     os.path.join(REPO, "Interface", "Bleakhold", "Glue"), tables],
                                    capture_output=True, text=True)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(", 0 failed", result.stdout)
        self.assertIn("12 races, 48 contexts, 384 rows OK", result.stdout)


class CommandTests(unittest.TestCase):
    def test_check_on_the_repository(self):
        result = run("picker-data", "--check")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("up to date", result.stdout)

    def test_check_finds_a_stale_file_and_writing_fixes_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            for path in (picker.GLUE_FILE, picker.BARBER_FILE):
                os.makedirs(os.path.dirname(os.path.join(tmp, path)), exist_ok=True)
                shutil.copy(os.path.join(REPO, path), os.path.join(tmp, path))

            curation = os.path.join(tmp, "curation.json")

            with open(os.path.join(CUSTOMIZE, "curation.json"), encoding="utf-8") as f:
                data = json.load(f)

            data["hidden"].append({"race": "Orc", "sex": "Male", "section": "skin", "colours": [25],
                                   "reason": "a test"})

            with open(curation, "w", encoding="utf-8") as f:
                json.dump(data, f)

            result = run("picker-data", "--check", "--repo", tmp, "--curation", curation)
            self.assertEqual(result.returncode, 1)
            self.assertIn("BleakholdCustomizeData.lua is not what picker-data makes", result.stderr)
            self.assertEqual(run("picker-data", "--repo", tmp, "--curation", curation).returncode, 0)
            self.assertEqual(run("picker-data", "--check", "--repo", tmp, "--curation", curation).returncode, 0)

            with open(os.path.join(tmp, picker.GLUE_FILE), encoding="utf-8") as f:
                self.assertNotIn(" 24, 25, 26,", f.read().split("Orc = {")[1].split("deathKnight")[0])

    def test_counts_of_another_package_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            curation = sc.write_curation(os.path.join(tmp, "curation.json"))
            result = run("picker-data", "--check", "--curation", curation)
            self.assertEqual(result.returncode, 1)
            self.assertIn("made from package commit", result.stderr)

    def test_package_counts_from_a_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            package = sc.make_package(tmp)
            curation = sc.write_curation(os.path.join(tmp, "curation.json"))
            counts = os.path.join(tmp, "counts.json")
            result = run("picker-data", "--package", package, "--curation", curation, "--counts", counts,
                         "--repo", tmp)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            with open(counts, encoding="utf-8") as f:
                self.assertEqual(json.load(f), synthetic_counts())

            self.assertTrue(os.path.isfile(os.path.join(tmp, picker.GLUE_FILE)))


if __name__ == "__main__":
    unittest.main()
