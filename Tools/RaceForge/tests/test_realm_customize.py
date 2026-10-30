"""raceforge.py customize on a made-up realm (tests/synth_customize.py): the whole chain stage 1 -> install -> stage 2
with marks -> install -> skins --art-archive -> install, the curation, the barber id ledger, the model gates and the
refusals."""

import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL_DIR = os.path.dirname(HERE)
TOOLS_DIR = os.path.dirname(TOOL_DIR)

for _path in (TOOL_DIR, os.path.join(TOOLS_DIR, "MpqPack")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from rflib import appearance as ap  # noqa: E402
from rflib import curation as curmod  # noqa: E402
from rflib import geosets, marksrows, realm_customize as rc, schema_access, update  # noqa: E402
from rflib.dbc import DbcTable  # noqa: E402
from tests import synth_customize as sc  # noqa: E402

patches = update.patch_tools()
RACEFORGE = os.path.join(TOOL_DIR, "raceforge.py")
CATALOGUE = os.path.join(TOOL_DIR, "customize", "catalogue.json")


def run(*args):
    return subprocess.run([sys.executable, "-I", RACEFORGE, *args], capture_output=True, text=True)


def read_table(archive_path: str, name: str) -> DbcTable:
    reader = patches.PatchArchive(archive_path)

    try:
        return DbcTable.from_bytes(reader.read(rc.dbc_path(name)), schema_access.get(name))
    finally:
        reader.close()


def names_of(archive_path: str) -> list[str]:
    reader = patches.PatchArchive(archive_path)

    try:
        return reader.names()
    finally:
        reader.close()


def rows(table: DbcTable, race: int, sex: int | None = None, section: int | None = None) -> list[list[int]]:
    return [r for r in table.rows if table.get(r, "raceID") == race and (sex is None or table.get(r, "sexID") == sex)
            and (section is None or table.get(r, "baseSection") == section)]


def key(table: DbcTable, row) -> tuple:
    return tuple(table.get(row, c) for c in ap.KEY)


class Realm:
    """A made-up realm, its package and curation, in a temporary folder."""

    def __init__(self, tmp: str, **package):
        self.root = tmp
        self.realm = sc.make_realm(tmp)
        self.package = sc.make_package(tmp, **package)
        self.curation = sc.write_curation(os.path.join(tmp, "curation.json"))
        self.base = os.path.join(tmp, "base")

    def customize(self, out: str, *extra):
        return run("customize", "--package", self.package, "--patches", self.realm["patches"], "--client",
                   self.realm["client"], "--base", self.base, "--curation", self.curation,
                   "--out", os.path.join(self.root, out), "--keep-free-gb", "0", *extra)

    def install(self, out: str):
        result = run("install", "--from", os.path.join(self.root, out), "--patches", self.realm["patches"])
        assert result.returncode == 0, result.stdout + result.stderr
        return result

    def patch(self, name: str) -> str:
        return os.path.join(self.realm["patches"], name)

    def out(self, *parts: str) -> str:
        return os.path.join(self.root, *parts)


class ChainTests(unittest.TestCase):
    """Stage 1, stage 2 with marks, skins: once, then checked piece by piece."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.r = r = Realm(cls.tmp.name)
        cls.stage1 = r.customize("out1", "--run-id", "s1", "--move-art", "patch-O.MPQ")
        assert cls.stage1.returncode == 0, cls.stage1.stdout + cls.stage1.stderr
        cls.s1_tables = {n: read_table(r.out("out1", "client", "Patch-R.MPQ"), n) for n in rc.TABLES}
        cls.s1_r_names = {n.lower() for n in names_of(r.out("out1", "client", "Patch-R.MPQ"))}
        r.install("out1")
        cls.catalogue = marksrows.load_catalogue(CATALOGUE)
        cls.manifest = sc.write_manifest(r.out("marks"), cls.catalogue, {
            ("BloodElf", 0): (True, [1, 2, 3, 4, 5]), ("BloodElf", 1): (True, [1, 4]),
            ("HighElf", 1): (True, [1, 2, 3, 4, 5]), ("Human", 1): (True, [])}, markforge_form=True)
        cls.stage2 = r.customize("out2", "--run-id", "s2", "--marks", cls.manifest, "--marks-partial")
        assert cls.stage2.returncode == 0, cls.stage2.stdout + cls.stage2.stderr
        cls.s2_tables = {n: read_table(r.out("out2", "client", "Patch-R.MPQ"), n) for n in rc.TABLES}
        r.install("out2")
        cls.skins = run("skins", "--patches", r.realm["patches"], "--client", r.realm["client"], "--out",
                        r.out("skins"), "--art-archive", "patch-F.MPQ")
        assert cls.skins.returncode == 0, cls.skins.stdout + cls.skins.stderr
        r.install("skins")

        with open(r.out("out1", "summary.json"), encoding="utf-8") as f:
            cls.summary1 = json.load(f)

        with open(r.out("out1", "report.txt"), encoding="utf-8") as f:
            cls.report1 = f.read()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    # --- stage 1 ---

    def test_package_races_12_to_21_and_goblin_are_dropped(self):
        cs = self.s1_tables["CharSections"]
        textures = {cs.get_str(r, "textureName[0]") for r in cs.rows}
        self.assertFalse(any("Skeleton" in t or "Npc15" in t for t in textures), "the package's Skeleton rows")
        self.assertEqual(sorted({cs.get(r, "raceID") for r in cs.rows}), [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 15, 19])
        goblin = rows(cs, 9)
        self.assertTrue(goblin and all("Goblin" in cs.get_str(r, "textureName[0]") and
                                       not cs.get_str(r, "textureName[0]").startswith(ap.ASCENSION) for r in goblin),
                        "Goblin keeps the realm's rows")

        for name in ("CharHairGeosets", "CharacterFacialHairStyles", "BarberShopStyle"):
            table = self.s1_tables[name]
            column = "race" if name == "BarberShopStyle" else "raceID"
            self.assertFalse({table.get(r, column) for r in table.rows} & {12, 13, 14, 16, 17, 18, 20, 21}, name)

    def test_high_elf_and_eredar_are_the_clones_of_10_and_11(self):
        cs = self.s1_tables["CharSections"]
        self.assertEqual(rc.clone_problems(cs), [])

        for clone, source in ((15, 10), (19, 11)):
            a = {key(cs, r)[1:] for r in rows(cs, clone)}
            b = {key(cs, r)[1:] for r in rows(cs, source)}
            self.assertEqual(a, b)

        # the filters: the High Elf keeps only keep_skins, the Draenei loses its fel skin and the Eredar keeps it
        def hidden(race, sex, colour):
            row = next(r for r in rows(cs, race, sex, 0) if cs.get(r, "colorIndex") == colour)
            return bool(cs.get(row, "flags") & ap.HIDDEN)

        self.assertTrue(hidden(15, 1, 6) and hidden(15, 1, 7))
        self.assertFalse(hidden(10, 1, 6) or hidden(10, 1, 7) or hidden(15, 0, 6))
        self.assertTrue(hidden(11, 0, 7))
        self.assertFalse(hidden(19, 0, 7))
        self.assertTrue(hidden(1, 1, 6), "the curation's hidden Human female skin")

    def test_textures_are_renamed_and_shipped_in_patch_6(self):
        cs = self.s1_tables["CharSections"]
        art = {n.lower() for n in names_of(self.r.patch("patch-6.MPQ"))}
        named = {cs.get_str(r, f"textureName[{s}]") for r in cs.rows if cs.get(r, "raceID") in (1, 10, 11, 15, 19)
                 for s in range(3)} - {""}
        self.assertTrue(named)

        for name in named:
            if name.startswith(ap.ASCENSION):
                self.assertIn(name.lower(), art, name)

        self.assertFalse(any("goblin" in n or "bakednpc" in n for n in art), "Goblin and baked textures stay out")
        self.assertIn(ap.ASCENSION + "Character\\BloodElf\\Male\\BloodElfMaleSkin00_00.blp", named)

    def test_missing_texture_is_rebuilt_and_one_without_source_drops_its_paint(self):
        cs = self.s1_tables["CharSections"]
        scalp = next(r for r in rows(cs, 10, 1, ap.HAIR) if key(cs, r)[3:] == (0, 5))
        name = cs.get_str(scalp, "textureName[1]")
        self.assertTrue(name.startswith(ap.REBUILT), name)
        self.assertTrue(name.endswith(sc.MISSING_SCALP), name)
        self.assertIn(name.lower(), {n.lower() for n in names_of(self.r.patch("patch-6.MPQ"))})
        features = next(r for r in rows(cs, 1, 0, ap.FEATURES) if key(cs, r)[3:] == (2, 4))
        self.assertEqual(cs.get_str(features, "textureName[0]"), "", "no source: no paint")
        self.assertEqual(self.summary1["rebuilt_textures"], 1)
        self.assertIn("rebuilt textures: 1", self.report1)

    def test_repeated_rows_keep_the_last_and_the_table_is_sorted(self):
        cs = self.s1_tables["CharSections"]
        self.assertEqual(rc.section_problems(cs), [])
        repeated = next(r for r in rows(cs, 10, 0, ap.FEATURES) if key(cs, r)[3:] == (1, 0))
        self.assertEqual(cs.get(repeated, "flags"), 0x11, "the last row of the key, as the client uses")

    def test_helmet_bits(self):
        helmets = self.s1_tables["HelmetGeosetVisData"].by_id()
        table = self.s1_tables["HelmetGeosetVisData"]
        first = table.get(helmets[1], "hideGeoset[0]")
        self.assertTrue(first & (1 << 10) and first & (1 << 15), "bit 15 = bit 10")
        self.assertFalse(first & (1 << 20), "the package's bit 20 (Northrend Skeleton) is not taken")
        fourth = table.get(helmets[4], "hideGeoset[0]")
        self.assertTrue(fourth & (1 << 20), "the realm's Pandaren bit stays")
        second = table.get(helmets[2], "hideGeoset[0]")
        self.assertTrue(second & (1 << 19) and second & (1 << 11) and second & (1 << 1))
        self.assertIn(5, helmets, "a new package id is added")

    def test_barber_rows(self):
        barber = self.s1_tables["BarberShopStyle"]
        base = DbcTable.from_bytes(self.r.realm["realm"]["BarberShopStyle"], schema_access.get("BarberShopStyle"))
        realm_ids = {rc.BarberLedger.key(base.get(r, "race"), base.get(r, "sex"), base.get(r, "type"),
                                         base.get(r, "data")): r[0] for r in base.rows}
        now = {rc.BarberLedger.key(barber.get(r, "race"), barber.get(r, "sex"), barber.get(r, "type"),
                                   barber.get(r, "data")): r for r in barber.rows}

        for k, row_id in realm_ids.items():
            self.assertEqual(now[k][0], row_id, f"the realm's {k} keeps its id")

        top = max(realm_ids.values())
        new = [r for k, r in now.items() if k not in realm_ids]
        self.assertTrue(new and all(r[0] > top for r in new), "new rows above every id in use")
        skins = {(barber.get(r, "race"), barber.get(r, "sex"), barber.get(r, "data")) for r in barber.rows
                 if barber.get(r, "type") == 3}
        self.assertIn((10, 0, 8), skins, "Death Knight skins get a barber row")
        self.assertNotIn((10, 0, 4), skins, "an NPC-only skin does not")
        self.assertNotIn((15, 1, 7), skins, "a skin the High Elf filter hid does not")
        self.assertIn((19, 0, 7), skins)
        self.assertNotIn((11, 0, 7), skins)

        for row in barber.rows:
            factor = barber.float_value(row, "costModifier")
            self.assertAlmostEqual(factor, rc.COST[barber.get(row, "type")], msg=row[0])

        skin_row = next(r for r in barber.rows if barber.get(r, "type") == 3 and barber.get(r, "race") == 10)
        self.assertTrue(barber.get_str(skin_row, "displayName[0]").startswith("Skin Color "))
        package = DbcTable.from_bytes(sc.tables(True)["BarberShopStyle"], schema_access.get("BarberShopStyle"))
        self.assertTrue(any(package.get(r, "race") == 6 and package.get(r, "type") == 3
                            and not package.get_str(r, "displayName[0]") for r in package.rows),
                        "the synthetic package has a Tauren skin row without a name")
        tauren = [r for r in barber.rows if barber.get(r, "type") == 3 and barber.get(r, "race") == 6]
        self.assertTrue(tauren)
        self.assertEqual({barber.get_str(r, "displayName[0]") for r in tauren}, {"Skin Color 1"},
                         "the package's unnamed Tauren skin row gets a name")
        self.assertFalse([r for r in barber.rows if barber.get(r, "race") in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 15, 19)
                          and not barber.get_str(r, "displayName[0]")], "every style has a name")

        with open(os.path.join(self.r.base, "barber_ids.json"), encoding="utf-8") as f:
            ledger = json.load(f)["ids"]

        for k, r in now.items():
            if barber.get(r, "race") in (1, 2, 3, 4, 5, 6, 7, 8, 10, 11, 15, 19):
                self.assertEqual(ledger[k], r[0])

    def test_npc_looks_move_with_the_numbers(self):
        cdie = self.s1_tables["CreatureDisplayInfoExtra"]
        looks = {r[0]: tuple(cdie.get(r, c) for c in ("skinID", "faceID", "hairColorID")) for r in cdie.rows}
        self.assertEqual(looks[1], (8, 0, 1), "the old Death Knight skin 4 is 8 now")
        self.assertEqual(looks[2], (2, 1, 2), "the Human female hair colours the package swapped")
        self.assertEqual(looks[3], (0, 0, 0))
        self.assertEqual(looks[4], (3, 3, 3), "race 12 is left as it is")
        self.assertEqual(cdie.get_str(next(r for r in cdie.rows if r[0] == 1), "bakeName"), "Npc1.blp")

    def test_server_copies_and_hashes(self):
        for name in rc.TABLES:
            with open(self.r.out("out1", "server", "dbc", f"{name}.dbc"), "rb") as f:
                self.assertEqual(f.read(), self.s1_tables[name].to_bytes(), name)

        with open(self.r.out("out1", "server", "appearance-hashes.json"), encoding="utf-8") as f:
            hashes = json.load(f)

        self.assertEqual(hashes["charsections"], rc.charsections_hash(self.s1_tables["CharSections"]))
        self.assertEqual(hashes["barbershopstyle"], rc.barber_hash(self.s1_tables["BarberShopStyle"]))

    def test_models_archive(self):
        names = {n.lower() for n in names_of(self.r.patch("patch-~.MPQ"))}
        self.assertIn("character\\bloodelf\\female\\bloodelffemale.m2", names)
        self.assertIn("character\\bloodelf\\female\\bloodelffemale0004-00.anim", names)
        self.assertIn("character\\bloodelf\\female\\deathknighteyeglow.blp", names, "the model's own texture")
        self.assertFalse(any("goblin" in n for n in names))
        self.assertIn("patch-~.MPQ, 7 geoset(s) needed", self.report1)

    def test_moved_art_and_install_manifest(self):
        moved = {n.lower() for n in names_of(self.r.patch("patch-O.MPQ"))}
        self.assertIn("interface\\glues\\custom.blp", moved)
        r_names = self.s1_r_names
        self.assertNotIn("interface\\glues\\custom.blp", r_names, "moved out of Patch-R")
        self.assertTrue(any(n.startswith("character\\bleakholdskins\\") for n in r_names), "skins' files are left to it")

        with open(self.r.out("out1", "install.json"), encoding="utf-8") as f:
            entries = {e["rel"]: e["origin"] for e in json.load(f)["archives"]}

        self.assertEqual(entries, {"Patch-R.MPQ": "patches", "patch-6.MPQ": "new", "patch-~.MPQ": "new",
                                   "patch-O.MPQ": "new"})

    def test_saved_base(self):
        with open(os.path.join(self.r.base, "base.json"), encoding="utf-8") as f:
            records = json.load(f)["tables"]

        self.assertEqual(sorted(records), sorted(f"data\\patch-r.mpq|{n}" for n in rc.TABLES))
        self.assertEqual(records["data\\patch-r.mpq|CreatureDisplayInfoExtra"]["read_from"],
                         "Data\\enUS\\locale-enUS.MPQ", "a base archive's table: saved under the archive it goes into")
        saved = rc.Base(self.r.base).get("Data\\Patch-R.MPQ", "CharSections")
        self.assertEqual(saved, self.r.realm["realm"]["CharSections"], "the realm's table from before the package")

    def test_remap_sql_written(self):
        with open(self.r.out("out1", "server", "sql", "remap_characters.sql"), encoding="utf-8") as f:
            sql = f.read()

        self.assertIn("run s1", sql)
        self.assertNotIn("CREATE TABLE IF NOT EXISTS", sql, "the tables are remap_tables.sql's")

        with open(self.r.out("out1", "server", "sql", "remap_tables.sql"), encoding="utf-8") as f:
            self.assertIn("CREATE TABLE IF NOT EXISTS `bh_appearance_set_customize`", f.read())
        self.assertIn("(10, 0, 1, 4, 0, 8, 0, 0)", sql, "Blood Elf Death Knight skin 4 face 0 -> skin 8 face 0")
        self.assertIn("(15, 0, 1, 4, 1, 8, 0, 1)", sql, "High Elf takes Blood Elf's mapping; no exact face: customize")
        self.assertEqual(self.summary1["remap_customize_pairs"], 30)
        self.assertEqual((self.summary1["changed_styles"], self.summary1["changed_features"]), ([], []),
                         "the made-up package only adds hair styles and features")
        self.assertIn("Hair styles and features that changed their meaning: 0", self.report1)

    # --- stage 2 ---

    def test_stage_2_remap_moves_nobody(self):
        with open(self.r.out("out2", "server", "sql", "remap_characters.sql"), encoding="utf-8") as f:
            first, second, *rest = f.read().split("\n")

        self.assertTrue(first.startswith("-- raceforge.py customize, run s2: "), first)
        self.assertIn("Stage 2 (--marks): no character moves", second)
        self.assertIn("0 (skin, face) pair(s) and 0 hair colour(s) move", rest[1])
        self.assertFalse([line for line in rest if line.startswith("INSERT INTO `bh_remap_")],
                         "no move rows: stage 1 already moved them")

    def test_stage_2_keeps_every_stage_1_barber_id(self):
        def meaning(table):
            return {r[0]: (table.get(r, "race"), table.get(r, "sex"), table.get(r, "type"), table.get(r, "data"))
                    for r in table.rows}

        one, two = meaning(self.s1_tables["BarberShopStyle"]), meaning(self.s2_tables["BarberShopStyle"])

        for row_id, what in one.items():
            self.assertEqual(two.get(row_id), what, row_id)

        marks = [w for i, w in two.items() if i not in one]
        self.assertTrue(marks and all(w[2] == 2 for w in marks), "stage 2 adds features rows only")

    def test_marks_rows(self):
        cs, cfhs = self.s2_tables["CharSections"], self.s2_tables["CharacterFacialHairStyles"]

        # Blood Elf male: B = 3, 13 x 3 values, a row per value at every hair colour, the third texture the mark
        self.assertEqual(marksrows.base_count(cfhs, 10, 0), 13 * 3)
        features = rows(cs, 10, 0, ap.FEATURES)
        self.assertEqual(len(features), 13 * 3 * 6)
        mark = next(r for r in features if cs.get(r, "variationIndex") == ap.features_value(1, 2, 3))
        self.assertEqual(cs.get_str(mark, "textureName[2]"),
                         ap.mark_name("BloodElf", 0, "SunstriderFiligree", "SunwellGold"))
        base = next(r for r in features if key(cs, r)[3:] == (2, cs.get(mark, "colorIndex")))
        self.assertEqual(cs.get(mark, "flags"), cs.get(base, "flags"), "mark rows copy their base row's flags")
        self.assertEqual(cs.get_str(mark, "textureName[0]"), cs.get_str(base, "textureName[0]"))

        # Blood Elf female had no features rows: base rows at every hair colour, 0x11 for players, 0x5 for Death Knights
        female = rows(cs, 10, 1, ap.FEATURES)
        flags = {cs.get(r, "colorIndex"): cs.get(r, "flags") for r in female if cs.get(r, "variationIndex") == 0}
        self.assertEqual(flags, {0: 0x11, 1: 0x11, 2: 0x11, 3: 0x5, 4: 0x11, 5: 0x11})
        self.assertEqual(len(female), 13 * 2 * 6)

        # both kinds count every value at their hair colours (CRITIC 7)
        for dk, colour in ((False, 0), (True, 3), (True, 0)):
            count = sum(1 for r in female if cs.get(r, "colorIndex") == colour and
                        ap.selectable(cs.get(r, "flags"), ap.CREATION, dk))
            self.assertEqual(count, marksrows.base_count(cfhs, 10, 1), (dk, colour))

        # Human female has marks and no eyes; Human male nothing
        self.assertEqual(marksrows.base_count(cfhs, 1, 1), 26)
        self.assertEqual(marksrows.base_count(cfhs, 1, 0), 3)
        self.assertFalse(any(cs.get(r, "variationIndex") >= ap.EYE_STRIDE for r in rows(cs, 1, None, ap.FACE)))

    def test_eye_rows(self):
        cs = self.s2_tables["CharSections"]
        faces = rows(cs, 10, 0, ap.FACE)
        eyes = {}

        for r in faces:
            eye, base = ap.split_face(cs.get(r, "variationIndex"))
            eyes.setdefault(eye, []).append((base, cs.get(r, "colorIndex"), cs.get(r, "flags"),
                                             cs.get_str(r, "textureName[2]")))

        self.assertEqual(sorted(eyes), [0, 1, 2, 3, 4, 5])
        self.assertTrue(all(t == "" for *_, t in eyes[0]))
        # eyes 1-3 on the player faces only (0-3), flags without 0x10; eyes 4-5 on the Death Knight faces, 0x5
        self.assertEqual({b for b, *_ in eyes[1]}, {0, 1, 2, 3})
        self.assertTrue(all(f == 0x1 for _, _, f, _ in eyes[1]))
        self.assertEqual({b for b, *_ in eyes[4]}, {0, 2, 4, 5})
        self.assertTrue(all(f == 0x5 for _, _, f, _ in eyes[4]))
        self.assertEqual({t for *_, t in eyes[4]}, {ap.eye_name("BloodElf", 0, "BloodRed")})
        self.assertTrue(all(not ap.selectable(f, ap.CREATION, True) for _, _, f, _ in eyes[2]),
                        "no Holy Gold eyes for Death Knights")
        # the High Elf's own eyes
        high = {cs.get_str(r, "textureName[2]") for r in rows(cs, 15, 1, ap.FACE)} - {""}
        self.assertTrue(high and all("\\HighElf\\Female\\" in t for t in high))

    def test_marks_archive_and_rollback_sql(self):
        names = {n.lower() for n in names_of(self.r.patch("patch-K.MPQ"))}
        self.assertIn(ap.mark_name("BloodElf", 0, "SunstriderFiligree", "SunwellGold").lower(), names)
        self.assertIn(ap.glow_name(ap.mark_name("BloodElf", 0, "SunstriderFiligree", "SunwellGold")).lower(), names)
        self.assertNotIn(ap.glow_name(ap.mark_name("BloodElf", 0, "SunstriderFiligree", "PhoenixRed")).lower(), names)
        self.assertIn(ap.eye_name("HighElf", 1, "Starlight").lower(), names)

        with open(self.r.out("out2", "server", "sql", "marks_rollback.sql"), encoding="utf-8") as f:
            sql = f.read()

        self.assertIn("`facialStyle` = `facialStyle` % 3 WHERE `race` = 10 AND `gender` = 0", sql)
        self.assertIn("`face` = `face` % 40", sql)

        with open(os.path.join(self.r.base, "barber_ids.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["bases"]["10,0"], 3)

    def test_stage_1_art_is_unchanged_in_stage_2(self):
        out = self.stage2.stdout
        self.assertIn("patch-6.MPQ (art)", out)
        self.assertIn("(unchanged)", out)
        self.assertFalse(os.path.exists(self.r.out("out2", "client", "patch-6.MPQ")))

    # --- skins --art-archive after it ---

    def test_skins_puts_the_purple_textures_into_patch_f_and_leaves_eyes_and_marks(self):
        purple = [n for n in names_of(self.r.patch("patch-F.MPQ")) if n.lower().startswith("character\\bleakholdskins")]
        self.assertTrue(purple)
        self.assertFalse(any("bleakholdeyes" in n.lower() or "bleakholdmarks" in n.lower() for n in purple))
        r_names = [n for n in names_of(self.r.patch("Patch-R.MPQ")) if n.lower().startswith("character\\")]
        self.assertEqual(r_names, [], "Patch-R holds tables only")
        cs = read_table(self.r.patch("Patch-R.MPQ"), "CharSections")
        eye_rows = [r for r in rows(cs, 15, 1, ap.FACE) if cs.get(r, "variationIndex") >= ap.EYE_STRIDE]
        self.assertTrue(eye_rows)

        for row in eye_rows:
            self.assertTrue(cs.get_str(row, "textureName[2]").startswith(ap.EYES_FOLDER), "never recoloured")
            self.assertTrue(cs.get_str(row, "textureName[0]").startswith(ap.SKINS_FOLDER), "the face is")

        # the package's underwear is opaque (the skin with the garment in): the High Elf's is recoloured where it is
        # bare skin, the Blood Elf's stays
        for race, prefix in ((15, ap.SKINS_FOLDER), (10, ap.ASCENSION)):
            underwear = [r for r in rows(cs, race, section=4) if cs.get(r, "flags") & 0x3]
            self.assertTrue(underwear)

            for row in underwear:
                for slot in (0, 1):
                    self.assertTrue(cs.get_str(row, f"textureName[{slot}]").startswith(prefix), (race, slot))


class RefusalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def pack_archive_with_npc_looks(self, name: str) -> Realm:
        """The made-up realm with an archive of the HD pack that holds its own CreatureDisplayInfoExtra.dbc (as
        Reforged's *_HD NPC bakes would) above Patch-R."""
        r = Realm(self.tmp.name)
        sc.synth_skins.write_mpq(r.patch(name), {rc.dbc_path("CreatureDisplayInfoExtra"): sc.npc_looks(),
                                                 "Textures\\BakedNpcTextures\\HD.blp": b"made up"})
        return r

    def test_a_reforged_mirror_patch_holding_a_table_is_refused(self):
        r = self.pack_archive_with_npc_looks("patch-U.MPQ")
        result = r.customize("out")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("patch-U.MPQ (Reforged", result.stderr)
        self.assertIn("optional pack hd; not a realm archive) holds CreatureDisplayInfoExtra.dbc over Patch-R.MPQ",
                      result.stderr)
        self.assertIn("customize never rebuilds it", result.stderr)
        self.assertFalse(os.path.exists(r.out("out", "client", "patch-U.MPQ")), "nothing written")

    def test_the_realms_own_hd_patch_holding_a_table_is_merged(self):
        r = self.pack_archive_with_npc_looks("Patch-Y.MPQ")
        result = r.customize("out")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(os.path.exists(r.out("out", "client", "Patch-Y.MPQ")), "the realm's Patch-Y is rebuilt")

    def test_write_refuses_a_target_the_realm_does_not_own(self):
        class Archive:
            is_base, rel, client_path, pack, name = False, "patch-S.MPQ", "Data\\patch-S.MPQ", "hd", "patch-S.MPQ"

        groups = rc.patchnames.load_groups(rc.TAKEN_PATCHES)
        plan = rc.Plan(rc.Options(package="", patches="", client="", out="", base="", curation="", catalogue=""),
                       None, None, None, None, {}, {}, [])
        plan.realm_owned = rc.patchnames.realm_owned(groups)
        plan.foreign = rc.patchnames.foreign(groups)
        plan.targets = {"data\\patch-s.mpq": {rc.dbc_path("CharSections"): b""}}
        plan.target_archives = {"data\\patch-s.mpq": Archive()}

        with self.assertRaisesRegex(rc.CustomizeError, "never rebuilds an archive the realm does not own: "
                                                       "patch-S.MPQ \\(Reforged"):
            rc.write(plan, self.tmp.name)

        self.assertIn("patch-y.mpq", plan.realm_owned)
        self.assertNotIn("patch-y.mpq", plan.foreign)
        self.assertIn("patch-j.mpq", plan.foreign, "WoW Forever's login screen")
        self.assertIn("patch-q.mpq", plan.foreign, "MapForge")
        self.assertIn("patch-4.mpq", plan.foreign, "CafeForge")

    def test_unpinned_package_is_refused(self):
        r = Realm(self.tmp.name)
        sc.write_curation(r.curation, commit="f" * 40)
        result = r.customize("out")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("the curation is for ffffffffffff", result.stderr)

    def test_merged_tables_without_a_saved_base_are_refused(self):
        r = Realm(self.tmp.name)
        self.assertEqual(r.customize("out").returncode, 0)
        r.install("out")
        r.base = os.path.join(self.tmp.name, "another-base")
        result = r.customize("again")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("merged already", result.stderr)

    def test_a_lost_base_is_rebuilt_from_the_archives_of_before(self):
        r = Realm(self.tmp.name)
        self.assertEqual(r.customize("out", "--run-id", "a").returncode, 0)
        first = {n: read_table(r.out("out", "client", "Patch-R.MPQ"), n).to_bytes() for n in rc.TABLES}
        r.install("out")
        r.base = os.path.join(self.tmp.name, "new-base")
        result = r.customize("again", "--run-id", "b", "--base-from", r.out("out", "old-patches"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        second = {n: read_table(r.out("again", "client", "Patch-R.MPQ"), n).to_bytes() for n in rc.TABLES}
        self.assertEqual(first, second)

    def test_a_second_run_from_the_saved_base_gives_the_same_tables(self):
        r = Realm(self.tmp.name)
        self.assertEqual(r.customize("out", "--run-id", "a").returncode, 0)
        first = {n: read_table(r.out("out", "client", "Patch-R.MPQ"), n).to_bytes() for n in rc.TABLES}
        r.install("out")
        result = r.customize("again", "--run-id", "b")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        second = {n: read_table(r.out("again", "client", "Patch-R.MPQ"), n).to_bytes() for n in rc.TABLES}
        self.assertEqual(first, second)
        self.assertNotIn("patch-6.MPQ", os.listdir(r.out("again", "client")), "unchanged art is not written again")

    def test_texture_size_that_would_hang_the_client(self):
        def bad(data):
            return data

        r = Realm(self.tmp.name)
        name = sc.tex(10, 0, "FaceLower00_15")
        path = os.path.join(r.package, *name.split("\\"))
        # 24 wide: not 64 x 2^k at level 9 and not smaller than the target in both directions
        from tests import synth_skins
        with open(path, "wb") as f:
            f.write(synth_skins.blp_palette(24, 140, synth_skins.skin_texture(24, 140, (200, 160, 120)), alpha_size=0))

        result = r.customize("out")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("loops for ever", result.stderr)

    def test_a_changed_realm_table_after_the_saved_base_is_refused(self):
        r = Realm(self.tmp.name)
        self.assertEqual(r.customize("out", "--run-id", "a").returncode, 0)  # saves the base; never installed
        reader = patches.PatchArchive(r.patch("Patch-R.MPQ"))

        try:
            files = {n: reader.read(n) for n in reader.names()}
        finally:
            reader.close()

        # the team re-forges Patch-R: one more helmet row
        name = rc.dbc_path("HelmetGeosetVisData")
        helmets = DbcTable.from_bytes(files[name], schema_access.get("HelmetGeosetVisData"))
        row = list(helmets.rows[-1])
        helmets.rows.append(row)
        helmets.set(row, "id", max(helmets.get(x, "id") for x in helmets.rows) + 1)
        files[name] = helmets.to_bytes()
        os.remove(r.patch("Patch-R.MPQ"))
        sc.synth_skins.write_mpq(r.patch("Patch-R.MPQ"), files)
        result = r.customize("again", "--run-id", "b")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("HelmetGeosetVisData.dbc of Patch-R.MPQ changed since the saved base", result.stderr)
        self.assertIn("keep barber_ids.json", result.stderr)

    def test_a_features_value_that_changed_its_meaning_stops_the_run_unless_accepted(self):
        def regeoset(data):
            facial = DbcTable.from_bytes(data["CharacterFacialHairStyles"],
                                         schema_access.get("CharacterFacialHairStyles"))

            for row in facial.rows:
                if (facial.get(row, "raceID"), facial.get(row, "sexID"), facial.get(row, "variationID")) == (1, 0, 1):
                    facial.set(row, "geoset[4]", 0)

            data["CharacterFacialHairStyles"] = facial.to_bytes()
            return data

        r = Realm(self.tmp.name, extra_rows=regeoset)
        result = r.customize("out")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("race 1 Male: features value 1 changed its meaning (geosets (1, 0, 0, 0, 2) -> (1, 0, 0, 0, 0))",
                      result.stderr + result.stdout)
        sc.write_curation(r.curation, accepted_changes=[{"race": "Human", "sex": "Male", "kind": "feature",
                                                         "values": [1], "reason": "made up"}])
        result = r.customize("again", "--run-id", "acc")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        with open(r.out("again", "server", "sql", "remap_characters.sql"), encoding="utf-8") as f:
            self.assertIn("2 accepted features change(s)", f.read(), "a player and a Death Knight")

        with open(r.out("again", "server", "sql", "count_hidden.sql"), encoding="utf-8") as f:
            # no merged value means the old 1: its characters stay on it with a customize, so it is not counted
            # (count_hidden.sql runs right after the remap and must say 0)
            self.assertNotIn("`facialStyle` = 1", f.read())

    def test_model_without_a_needed_geoset(self):
        files = sc.model_files(10, 1, geosets=[0, 1, 2, 3, 101, 1702])  # no hair geoset 4 for style 3
        r = Realm(self.tmp.name, models={(10, 1): files})
        result = r.customize("out")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no geoset 4 (hair style 3)", result.stderr)

    def test_model_whose_anim_comes_from_another_archive(self):
        files = sc.model_files(10, 1)
        del files["Character\\BloodElf\\Female\\BloodElfFemale0004-00.anim"]
        r = Realm(self.tmp.name, models={(10, 1): files})
        result = r.customize("out")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("all packs: race 10 Female", result.stderr)
        self.assertIn("not in the model's patch-~.MPQ", result.stderr)

    def test_eyes_need_geoset_1703(self):
        files = sc.model_files(10, 0, geosets=[g for g in sc.GEOSETS if g != 1703])
        r = Realm(self.tmp.name, models={(10, 0): files})
        catalogue = marksrows.load_catalogue(CATALOGUE)
        manifest = sc.write_manifest(r.out("marks"), catalogue, {("BloodElf", 0): (False, [1])})
        result = r.customize("out", "--marks", manifest, "--marks-partial")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no geoset 1703 (eye rows)", result.stderr)

    def test_package_third_texture_is_refused(self):
        def tex3(data):
            cs = DbcTable.from_bytes(data["CharSections"], schema_access.get("CharSections"))
            row = next(r for r in cs.rows if cs.get(r, "baseSection") == 1)
            cs.set_str(row, "textureName[2]", "Character\\Something.blp")
            data["CharSections"] = cs.to_bytes()
            return data

        r = Realm(self.tmp.name, extra_rows=tex3)
        result = r.customize("out")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("has a third texture", result.stderr)

    def test_changed_b_after_marks_is_refused(self):
        ledger = rc.BarberLedger(bases={"10,0": 4})

        with self.assertRaisesRegex(rc.CustomizeError, "base features now"):
            ledger.check_bases({(10, 0): 3})

    def test_names_outside_customize_are_refused(self):
        r = Realm(self.tmp.name)
        result = r.customize("out", "--marks-archive", "patch-W.MPQ")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not a name taken_patches.json gives to customize", result.stderr)


class HiddenCountTests(unittest.TestCase):
    """count_hidden.sql keeps the skin colour of a hidden face row (a face is hidden on one skin, not on all)."""

    def test_hidden_looks_keep_the_skin_colour_of_a_face(self):
        hidden = [curmod.HiddenRow(11, 0, ap.FACE, v, 16, "broken") for v in range(3)] + \
                 [curmod.HiddenRow(1, 1, ap.SKIN, 0, 6, "painted"), curmod.HiddenRow(1, 1, 4, 0, 6, "underwear")]
        self.assertEqual(rc.hidden_looks(hidden), [(11, 0, "face", 0, 16), (11, 0, "face", 1, 16),
                                                   (11, 0, "face", 2, 16), (1, 1, "skin", 6, 6)])

    def test_written_count_sql_counts_a_hidden_face_only_on_its_skin(self):
        import sqlite3

        with tempfile.TemporaryDirectory() as tmp:
            r = Realm(tmp)
            hidden = [{"race": "Human", "sex": "Female", "section": "skin", "colours": [6],
                       "reason": "painted clothing (made up)"},
                      {"race": "Draenei", "sex": "Male", "section": "face", "colours": [5],
                       "reason": "broken faces at skin 5 (made up)"}]
            sc.write_curation(r.curation, hidden=hidden)
            result = r.customize("out", "--run-id", "h")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            with open(r.out("out", "server", "sql", "count_hidden.sql"), encoding="utf-8") as f:
                sql = f.read()

        selects = [line for line in sql.splitlines() if line.startswith("SELECT")]
        faces = [line for line in selects if "'face'" in line]
        self.assertTrue(faces)
        self.assertTrue(all("`skin` IN (5)" in line for line in faces), faces)
        db = sqlite3.connect(":memory:")
        db.execute("CREATE TABLE `characters` (`guid` INT, `race` INT, `class` INT, `gender` INT, `skin` INT, "
                   "`face` INT)")
        db.execute("INSERT INTO characters VALUES (1, 11, 1, 0, 3, 2)")  # an ordinary Draenei male

        def total():
            return sum(db.execute(line).fetchone()[-1] for line in selects)

        self.assertEqual(total(), 0)
        db.execute("INSERT INTO characters VALUES (2, 11, 1, 0, 5, 42)")  # face 2 + an eye on the hidden skin 5
        self.assertEqual(total(), 1)
        db.close()


class TextureCheckTests(unittest.TestCase):
    """check_textures() reads the file each combination resolves a stock name to, not only the first one's."""

    NAME = "Character\\Human\\Male\\HumanMaleSkin00_10.blp"

    @staticmethod
    def header(width: int, height: int) -> bytes:
        levels = rc.blp.level_count(width, height)
        sizes = [1] * levels + [0] * (16 - levels)
        return rc.blp.HEADER.pack(b"BLP2", 1, 1, 0, 0, 1, width, height, *([0] * 16), *sizes)

    class Archive:
        def __init__(self, name, data):
            self.name, self.data = name, data

        def read(self, _name):
            return self.data

    def plan(self, holders: dict) -> object:
        from types import SimpleNamespace
        cs = sc.synth.Packer("CharSections")
        cs.add(id=1, raceID=1, sexID=0, baseSection=ap.SKIN, flags=0x1, variationIndex=0, colorIndex=10,
               **{"textureName[0]": self.NAME})
        table = DbcTable.from_bytes(cs.pack(), schema_access.get("CharSections"))
        combos = []

        for label, packs_on in (("all packs", frozenset({"A"})), ("no packs", frozenset())):
            combo = rc.Combination(label, packs_on)
            combo.merged = SimpleNamespace(tables={"CharSections": table})
            combos.append(combo)

        patchset = SimpleNamespace(top=lambda name, packs_on: holders.get(bool(packs_on)))
        return SimpleNamespace(combos=combos, rebuilt={}, files={}, manifest=None, problems=[],
                               game=SimpleNamespace(patchset=patchset))

    def test_a_bad_copy_without_the_packs_is_reported(self):
        plan = self.plan({True: self.Archive("patch-A.MPQ", self.header(512, 512)),
                          False: self.Archive("common.MPQ", self.header(384, 384))})
        rc.check_textures(plan)
        self.assertEqual(len(plan.problems), 1, plan.problems)
        self.assertIn("no packs: " + self.NAME + " of common.MPQ: 384x384", plan.problems[0])
        self.assertIn("loops for ever", plan.problems[0])

    def test_a_copy_missing_without_the_packs_is_reported(self):
        plan = self.plan({True: self.Archive("patch-A.MPQ", self.header(512, 512))})
        rc.check_textures(plan)
        self.assertEqual(len(plan.problems), 1, plan.problems)
        self.assertIn("no packs: " + self.NAME, plan.problems[0])
        self.assertIn("is in no archive", plan.problems[0])

    def test_one_file_is_checked_once(self):
        bad = self.Archive("common.MPQ", self.header(384, 384))
        plan = self.plan({True: bad, False: bad})
        rc.check_textures(plan)
        self.assertEqual(len(plan.problems), 1, plan.problems)


class LedgerTests(unittest.TestCase):
    def test_ids_are_kept_and_new_ones_go_above(self):
        ledger = rc.BarberLedger()
        realm = {"10,0,0,0": 5, "10,0,0,1": 9}
        ids = ledger.assign(["10,0,0,0", "10,0,0,1", "10,0,3,0", "10,0,2,0"], realm, set())
        self.assertEqual(ids, {"10,0,0,0": 5, "10,0,0,1": 9, "10,0,2,0": 10, "10,0,3,0": 11})
        again = rc.BarberLedger(dict(ledger.ids))
        self.assertEqual(again.assign(["10,0,3,0", "10,0,2,0", "10,0,2,1"], realm, set()),
                         {"10,0,3,0": 11, "10,0,2,0": 10, "10,0,2,1": 12}, "the same ids, the next one above them")

    def test_new_ids_go_above_the_other_races_rows_too(self):
        ids = rc.BarberLedger().assign(["10,0,0,0", "10,0,2,0", "10,0,3,0"], {"10,0,0,0": 5}, {6, 7})
        self.assertEqual(ids, {"10,0,0,0": 5, "10,0,2,0": 8, "10,0,3,0": 9})

    def test_conflicts_are_refused(self):
        ledger = rc.BarberLedger({"10,0,0,0": 7})

        with self.assertRaisesRegex(rc.CustomizeError, "in the ledger but"):
            ledger.assign(["10,0,0,0"], {"10,0,0,0": 5}, set())

        with self.assertRaisesRegex(rc.CustomizeError, "is 10,0,0,0 in the ledger"):
            rc.BarberLedger({"10,0,0,0": 7}).assign(["10,0,0,1"], {"10,0,0,1": 7}, set())

        # a ledger id (or a realm id) that another race's row of the realm's table holds
        with self.assertRaisesRegex(rc.CustomizeError, "id 40 \\(10,0,2,5\\) is held by another race's row"):
            rc.BarberLedger({"10,0,2,5": 40}).assign(["10,0,2,5"], {}, {40})

        with self.assertRaisesRegex(rc.CustomizeError, "id 6 \\(10,0,0,0\\) is held by another race's row"):
            rc.BarberLedger().assign(["10,0,0,0"], {"10,0,0,0": 6}, {6})

    def test_repeated_ids_stop_the_run(self):
        barber = DbcTable.from_bytes(sc.tables(False)["BarberShopStyle"], schema_access.get("BarberShopStyle"))
        merged = rc.Merged({"CharSections": DbcTable.empty(schema_access.get("CharSections")),
                            "CharacterFacialHairStyles": DbcTable.empty(schema_access.get("CharacterFacialHairStyles")),
                            "BarberShopStyle": barber})
        self.assertFalse([p for p in rc.gates(merged) if "repeated id" in p])
        barber.rows.append(list(barber.rows[0]))
        self.assertIn("BarberShopStyle has 1 repeated id(s)", rc.gates(merged))

    def test_an_unnamed_style_of_a_customized_race_stops_the_run(self):
        barber = DbcTable.from_bytes(sc.tables(False)["BarberShopStyle"], schema_access.get("BarberShopStyle"))
        merged = rc.Merged({"CharSections": DbcTable.empty(schema_access.get("CharSections")),
                            "CharacterFacialHairStyles": DbcTable.empty(schema_access.get("CharacterFacialHairStyles")),
                            "BarberShopStyle": barber})
        self.assertFalse([p for p in rc.gates(merged) if "displayName" in p])
        row = list(barber.rows[0])
        barber.set(row, "id", barber.max_id() + 1)
        barber.set(row, "race", 19)
        barber.set(row, "type", 3)
        barber.set_loc(row, "displayName", [""] * 16)
        barber.rows.append(row)
        self.assertTrue([p for p in rc.gates(merged) if "1 row(s) of races 1-11, 15 and 19 have no displayName" in p])
        barber.set(row, "race", 20)  # a race customize does not take keeps its row as it is
        self.assertFalse([p for p in rc.gates(merged) if "displayName" in p])

    def test_another_races_row_at_the_top_id_keeps_it_and_new_ids_go_above(self):
        # the realm's Patch-R has a Pandaren (race 20) style at the top id, above every row of 1-11, 15 and 19
        with tempfile.TemporaryDirectory() as tmp:
            r = Realm(tmp)
            schema = schema_access.get("BarberShopStyle")
            barber = DbcTable.from_bytes(r.realm["realm"]["BarberShopStyle"], schema)
            top = barber.max_id() + 1
            pandaren = list(barber.rows[0])
            barber.set(pandaren, "id", top)
            barber.set(pandaren, "race", 20)
            barber.rows.append(pandaren)
            reader = patches.PatchArchive(r.patch("Patch-R.MPQ"))

            try:
                files = {name: reader.read(name) for name in reader.names() if not name.startswith("(")}
            finally:
                reader.close()

            files[rc.dbc_path("BarberShopStyle")] = barber.to_bytes()
            from tests import synth_skins
            synth_skins.write_mpq(r.patch("Patch-R.MPQ"), files)
            result = r.customize("out", "--run-id", "p")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            merged = read_table(r.out("out", "client", "Patch-R.MPQ"), "BarberShopStyle")

        ids = [r[0] for r in merged.rows]
        self.assertEqual(len(ids), len(set(ids)), "every id once")
        self.assertEqual([merged.get(row, "race") for row in merged.rows if row[0] == top], [20],
                         "the race-20 row keeps its id, and no other row has it")
        before = {row[0] for row in barber.rows}
        new = [i for i in ids if i not in before]
        self.assertTrue(new and min(new) > top, "every new id is above the race-20 row's")


class CurationTests(unittest.TestCase):
    def base(self, **changes):
        data = {"version": 1, "package": {"commit": sc.COMMIT}, "hidden": [], "race_filters": {}}
        data.update(changes)
        return data

    def test_the_repository_curation_loads(self):
        cur = curmod.load(os.path.join(TOOL_DIR, "customize", "curation.json"))
        self.assertEqual(cur.commit, "9d082f467d2e92376763454de2ec8ad3f3c921e3")
        self.assertTrue(all(h.reason for h in cur.hidden))
        self.assertEqual(cur.group("HighElf", 1, 61, 0x11), "fel", "the High Elf's groups are Blood Elf's")
        self.assertEqual(cur.group("BloodElf", 1, 63, 0x5), "deathknight")
        self.assertEqual(cur.filters["HighElf"].keep_skins[0], tuple(range(10)))

    def test_accepted_changes(self):
        cur = curmod.parse(self.base(accepted_changes=[
            {"race": "NightElf", "sex": "Female", "kind": "feature", "values": [9], "reason": "the blank moved to 18"},
            {"race": "Human", "kind": "style", "values": [3], "reason": "made up"}]))
        self.assertEqual(cur.accepted_keys({"NightElf": 4, "Human": 1}),
                         {(4, 1, "feature", 9), (1, 0, "style", 3), (1, 1, "style", 3)})

        for bad, why in (({"race": "Human", "kind": "style", "values": [1]}, "reason"),
                         ({"race": "Human", "kind": "hair", "values": [1], "reason": "x"}, "kind"),
                         ({"race": "Human", "kind": "style", "values": [], "reason": "x"}, "values")):
            with self.assertRaisesRegex(curmod.CurationError, why):
                curmod.parse(self.base(accepted_changes=[bad]))

    def test_features_rows_are_never_hidden(self):
        data = self.base(hidden=[{"race": "Human", "section": "features", "colours": [1], "reason": "x"}])

        with self.assertRaisesRegex(curmod.CurationError, "never hidden"):
            curmod.parse(data)

    def test_a_hidden_row_needs_a_reason(self):
        with self.assertRaisesRegex(curmod.CurationError, "reason"):
            curmod.parse(self.base(hidden=[{"race": "Human", "section": "skin", "colours": [1]}]))

        with self.assertRaisesRegex(curmod.CurationError, "reason"):
            curmod.parse(self.base(race_filters={"Draenei": {"hide_groups": ["fel"]}}))

    def test_bad_values(self):
        for bad in ({"race": "Goblin", "section": "skin", "colours": [1], "reason": "x"},
                    {"race": "Human", "section": "skin", "colours": [300], "reason": "x"},
                    {"race": "Human", "section": "skin", "variations": [2], "reason": "x"},
                    {"race": "Human", "section": "skin", "sex": "Other", "reason": "x"}):
            with self.assertRaises(curmod.CurationError, msg=bad):
                curmod.parse(self.base(hidden=[bad]))

        with self.assertRaisesRegex(curmod.CurationError, "pinned package commit"):
            curmod.parse(self.base(package={"commit": "abc"}))

    def test_near_duplicates_and_thinning(self):
        colours = {0: (0.70, 0.02, 0.0), 1: (0.705, 0.02, 0.0), 2: (0.60, 0.03, 0.0)}
        self.assertEqual(curmod.near_duplicates(colours, 2.0), [(0, 1, 0.5)])
        order = [0, 1, 2]
        self.assertEqual(curmod.thin(order, colours, 2.0), [0, 2])
        self.assertAlmostEqual(curmod.delta_e((0.5, 0, 0), (0.52, 0, 0)), 2.0)


class ModelTests(unittest.TestCase):
    def test_parse(self):
        files = sc.model_files(10, 1)
        info = geosets.parse_m2(files["Character\\BloodElf\\Female\\BloodElfFemale.m2"], "m2")
        self.assertEqual(info.version, 264)
        self.assertEqual(geosets.anim_names("Character\\BloodElf\\Female\\BloodElfFemale.mdx", info),
                         ["Character\\BloodElf\\Female\\BloodElfFemale0004-00.anim"], "not in-file, not an alias")
        self.assertEqual(geosets.own_textures(info), ["Character\\BloodElf\\Female\\deathKnightEyeGlow.blp"])
        self.assertEqual(geosets.parse_skin(files["Character\\BloodElf\\Female\\BloodElfFemale00.skin"], "skin"),
                         set(sc.GEOSETS))

        with self.assertRaises(geosets.ModelError):
            geosets.parse_m2(b"MD21" + bytes(400), "bad")

        bad = bytearray(files["Character\\BloodElf\\Female\\BloodElfFemale.m2"])
        struct.pack_into("<I", bad, 4, 272)

        with self.assertRaisesRegex(geosets.ModelError, "version 272"):
            geosets.parse_m2(bytes(bad), "x")

    def test_required_geosets(self):
        package = DbcTable.from_bytes(sc.tables(True)["CharSections"], schema_access.get("CharSections"))
        tables = sc.tables(True)
        hair = DbcTable.from_bytes(tables["CharHairGeosets"], schema_access.get("CharHairGeosets"))
        facial = DbcTable.from_bytes(tables["CharacterFacialHairStyles"], schema_access.get("CharacterFacialHairStyles"))
        need = geosets.required(package, hair, facial, 10, 0)
        self.assertEqual(sorted(need), [1, 2, 3, 4, 101, 102, 1702])


if __name__ == "__main__":
    unittest.main()
