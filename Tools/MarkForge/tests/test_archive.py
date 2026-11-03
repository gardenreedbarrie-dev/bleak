"""Reading the inputs: numpy BLP decoding against RaceForge's decoder, folder sources, CharSections filters."""

import os
import unittest

import common
import numpy as np

import blpconvert
from mflib import archive as AR
from rflib import blp as rfblp


class Decode(unittest.TestCase):
    def test_every_format_matches_raceforge(self):
        rs = np.random.RandomState(2)
        d = common.temp_dir("dec")
        rgba = rs.randint(0, 256, (32, 64, 4)).astype(np.uint8)
        img = blpconvert.Image(64, 32, bytearray(rgba.tobytes()))
        for fmt in ("dxt1", "dxt5", "bgra", "pal8"):
            path = os.path.join(d, fmt + ".blp")
            blpconvert.convert(img, path, fmt, True, jobs=1)
            with open(path, "rb") as f:
                data = f.read()
            for level in (0, 2):
                w, h, px = rfblp.decode(data, fmt, level)
                ours = AR.decode_blp(data, level)
                self.assertEqual(ours.shape, (h, w, 4), fmt)
                self.assertTrue(np.array_equal(ours, np.frombuffer(bytes(px), np.uint8).reshape(h, w, 4)), fmt)


class Sources(unittest.TestCase):
    def test_folder_is_case_insensitive(self):
        d = common.temp_dir("src")
        os.makedirs(os.path.join(d, "Character", "Orc"))
        with open(os.path.join(d, "Character", "Orc", "OrcMALE.m2"), "wb") as f:
            f.write(b"x")
        s = AR.FolderSource(d)
        self.assertTrue(s.has("character\\orc\\orcmale.M2"))
        self.assertTrue(s.has("Character/Orc/OrcMale.m2"))
        self.assertEqual(s.read("CHARACTER\\ORC\\ORCMALE.M2"), b"x")
        self.assertFalse(s.has("Character\\Orc\\OrcFemale.m2"))

    def test_visible_skins_rules(self):
        rows = []

        def r(sec, var, col, flags, tex):
            rows.append({"raceID": 2, "sexID": 0, "baseSection": sec, "variationIndex": var, "colorIndex": col,
                         "flags": flags, "textures": tex + [""] * (3 - len(tex))})

        r(0, 0, 0, 0x11, ["s0"])
        r(0, 0, 1, 0x18, ["npc"])      # hidden
        r(0, 0, 2, 0x5, ["dk"])        # Death Knight: visible
        r(0, 0, 3, 0x0, ["none"])      # neither 0x1 nor 0x2
        r(0, 0, 4, 0x11, ["old"])
        r(0, 0, 4, 0x11, ["new"])      # a repeated key: the last wins, as in the client
        r(4, 0, 0, 0x11, ["pelvis0", "torso0"])
        got = AR.visible_skins(rows, 2, 0)
        self.assertEqual([s["colour"] for s in got], [0, 2, 4])
        self.assertEqual(got[0]["pelvis"], "pelvis0")
        self.assertEqual(got[0]["torso"], "torso0")
        self.assertEqual(got[2]["skin"], "new")

    def test_rows_race_and_prefix(self):
        class F:
            kind = "folder"

        class G:
            kind = "game"

        self.assertEqual(AR.rows_race(F(), 15), 10)
        self.assertEqual(AR.rows_race(F(), 19), 11)
        self.assertEqual(AR.rows_race(G(), 15), 15)
        self.assertEqual(AR.rows_race(F(), 4), 4)
        self.assertEqual(AR.strip_skins_prefix("Character\\BleakholdSkins\\HighElf\\0123456789\\Character\\BloodElf\\"
                                               "Female\\X.blp"), "Character\\BloodElf\\Female\\X.blp")
        self.assertEqual(AR.strip_skins_prefix("Character\\BloodElf\\Female\\X.blp"), "Character\\BloodElf\\Female\\X.blp")
        self.assertEqual(AR.strip_ascension_prefix("Character\\Ascension\\Character\\Orc\\Male\\A.blp"),
                         "Character\\Orc\\Male\\A.blp")


def _client_files(root):
    """{client path: bytes} of every file under a package folder."""
    out = {}
    for dirpath, _, names in os.walk(root):
        for n in names:
            full = os.path.join(dirpath, n)
            out[os.path.relpath(full, root).replace(os.sep, "\\")] = open(full, "rb").read()
    return out


class GameSourceTests(unittest.TestCase):
    """The client's archives as the VPS build reads them (--client and --patches, no --config: deploy/customize/
    customize.sh passes none, so the launcher's optional packs come from RaceForge's races.json)."""

    @classmethod
    def setUpClass(cls):
        import sys
        mpq_dir = os.path.join(common.mflib.REPO, "Tools", "MpqPack")
        if mpq_dir not in sys.path:
            sys.path.append(mpq_dir)
        import mpqpack
        cls.root = common.temp_dir("game")
        pkg = common.temp_dir("gamepkg")
        common.write_package(pkg)
        files = _client_files(pkg)
        # the stock model tables: race 1's model, High Elf (15) on the Blood Elf's
        files.update(common.model_tables([(1, "Human", "Human"), (10, "BloodElf", "BloodElf"),
                                          (15, "HighElf", "BloodElf")]))
        cls.eye = "Character\\Human\\Male\\deathKnightEyeGlow.blp"
        cls.client = os.path.join(cls.root, "client")
        data = os.path.join(cls.client, "Data")
        os.makedirs(os.path.join(data, "enUS"))
        mpqpack.write_archive(os.path.join(data, "common.MPQ"),
                              sorted((k, v) for k, v in files.items() if not k.startswith("DBFilesClient")))
        mpqpack.write_archive(os.path.join(data, "enUS", "locale-enUS.MPQ"),
                              sorted((k, v) for k, v in files.items() if k.startswith("DBFilesClient")))
        cls.patches = os.path.join(cls.root, "patches")
        os.makedirs(cls.patches)
        # the realm's own patch holds the table again (the same bytes): the top copy is read
        cs = "DBFilesClient\\CharSections.dbc"
        mpqpack.write_archive(os.path.join(cls.patches, "Patch-R.MPQ"), [(cs, files[cs])])
        # a second patches folder whose HD pack (Patch-Y, optional in races.json) has another eye glow
        cls.patches_hd = os.path.join(cls.root, "patches-hd")
        os.makedirs(cls.patches_hd)
        mpqpack.write_archive(os.path.join(cls.patches_hd, "Patch-R.MPQ"), [(cs, files[cs])])
        from mflib import eyes as E
        cls.hd_eye = E.synthetic_source(16)
        mpqpack.write_archive(os.path.join(cls.patches_hd, "Patch-Y.MPQ"), [(cls.eye, cls.hd_eye)])
        cls.files = files
        cls.mpqpack = mpqpack

    def hd_patches(self, tag: str, files: dict) -> str:
        """A patches folder: Patch-R with the realm's CharSections, Patch-Y (the HD pack, optional) with these."""
        folder = os.path.join(self.root, f"patches-{tag}")
        os.makedirs(folder)
        cs = "DBFilesClient\\CharSections.dbc"
        self.mpqpack.write_archive(os.path.join(folder, "Patch-R.MPQ"), [(cs, self.files[cs])])
        self.mpqpack.write_archive(os.path.join(folder, "Patch-Y.MPQ"), sorted(files.items()))
        return folder

    def char_sections_copy(self, change):
        from rflib import schema_access
        from rflib.dbc import DbcTable
        t = DbcTable.from_bytes(self.files["DBFilesClient\\CharSections.dbc"], schema_access.get("CharSections"))
        change(t)
        return {"DBFilesClient\\CharSections.dbc": t.to_bytes()}

    def build(self, patches):
        import io
        from contextlib import redirect_stdout, redirect_stderr
        import markforge as MF
        out = os.path.join(common.temp_dir("gameout"), "staging")
        buf = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(buf):
            rc = MF.main(["build", "--client", self.client, "--patches", patches, "--out", out,
                          "--races", "Human:Male"])
        return rc, buf.getvalue()

    def test_a_table_copy_with_other_strings_or_other_races_agrees(self):
        # RaceForge writes one copy of CharSections per archive, each with its archive's own string block: the HD
        # pack's copy has the same playable rows but another string and a row of a race MarkForge never reads
        def change(t):
            t.add_string("Character\\Goblin\\Male\\NotRead.blp")
            row = list(t.rows[0])
            t.set(row, "id", 900)
            t.set(row, "raceID", 9)
            t.rows.append(row)

        patches = self.hd_patches("strings", self.char_sections_copy(change))
        g = AR.GameSource(self.client, patches)
        try:
            self.assertEqual(len(g.configs), 2)
            self.assertTrue(AR.char_sections(g))
        finally:
            g.close()
        rc, out = self.build(patches)
        self.assertEqual(rc, 0, out)

    def test_a_playable_row_that_differs_between_the_combinations_is_refused(self):
        def change(t):
            row = next(r for r in t.rows if t.get(r, "baseSection") == 0)
            t.set_str(row, "textureName[0]", "Character\\Human\\Male\\HumanMaleSkin00_99.blp")

        patches = self.hd_patches("texture", self.char_sections_copy(change))
        g = AR.GameSource(self.client, patches)
        try:
            with self.assertRaises(AR.MarkForgeError) as cm:
                AR.char_sections(g)
            self.assertIn("differs between pack combinations", str(cm.exception))
        finally:
            g.close()
        rc, out = self.build(patches)
        self.assertNotEqual(rc, 0)
        self.assertIn("differs between pack combinations", out)

    def test_a_model_table_that_differs_stops_instead_of_the_stock_model(self):
        tables = common.model_tables([(1, "Human", "Human"), (10, "BloodElf", "BloodElf"),
                                      (15, "HighElf", "HighElfHD")])
        patches = self.hd_patches("models", {"DBFilesClient\\ChrRaces.dbc": tables["DBFilesClient\\ChrRaces.dbc"],
                                             "DBFilesClient\\CreatureModelData.dbc":
                                                 tables["DBFilesClient\\CreatureModelData.dbc"]})
        g = AR.GameSource(self.client, patches)
        try:
            with self.assertRaises(AR.MarkForgeError) as cm:
                AR.model_paths(g, 15, 0)
            self.assertIn("differs between pack combinations", str(cm.exception))
        finally:
            g.close()
        g = AR.GameSource(self.client, self.patches)
        try:
            self.assertEqual(AR.model_paths(g, 15, 0), ("Character\\BloodElf\\Male\\BloodElfMale.m2",
                                                        "Character\\BloodElf\\Male\\BloodElfMale00.skin"))
        finally:
            g.close()

    def test_a_game_source_without_model_tables_stops(self):
        folder = os.path.join(self.root, "client-bare")
        os.makedirs(os.path.join(folder, "Data", "enUS"))
        cs = "DBFilesClient\\CharSections.dbc"
        self.mpqpack.write_archive(os.path.join(folder, "Data", "enUS", "locale-enUS.MPQ"), [(cs, self.files[cs])])
        g = AR.GameSource(folder, self.patches)
        try:
            with self.assertRaises(AR.MarkForgeError) as cm:
                AR.model_paths(g, 15, 0)
            self.assertIn("model tables cannot be read", str(cm.exception))
        finally:
            g.close()

    def test_reads_through_the_overlay_without_a_config(self):
        g = AR.GameSource(self.client, self.patches)
        try:
            self.assertEqual(g.kind, "game")
            self.assertTrue(g.has(self.eye))
            self.assertEqual(g.read(self.eye), self.files[self.eye])
            self.assertFalse(g.has("Character\\Nope\\Nothing.blp"))
            with self.assertRaises(AR.MarkForgeError):
                g.read("Character\\Nope\\Nothing.blp")
            self.assertEqual(len(AR.char_sections(g)), 6)
        finally:
            g.close()

    def test_pack_combinations_must_agree(self):
        g = AR.GameSource(self.client, self.patches_hd)
        try:
            with self.assertRaises(AR.MarkForgeError) as cm:
                g.read(self.eye)
            self.assertIn("differs between pack combinations", str(cm.exception))
        finally:
            g.close()
        labels = [c[0] for c in AR.GameSource(self.client, self.patches_hd).configs]
        self.assertEqual(labels, ["all packs", "no packs"])
        for label, want in (("no packs", self.files[self.eye]), ("all packs", self.hd_eye)):
            g = AR.GameSource(self.client, self.patches_hd, combination=label)
            try:
                self.assertEqual(g.read(self.eye), want)
            finally:
                g.close()
        with self.assertRaises(AR.MarkForgeError):
            AR.GameSource(self.client, self.patches_hd, combination="packs nothing")

    def test_a_bad_config_is_a_clear_error(self):
        with self.assertRaises(AR.MarkForgeError) as cm:
            AR.GameSource(self.client, self.patches, config=os.path.join(self.root, "missing.json"))
        self.assertIn("--config", str(cm.exception))

    def test_build_from_the_client(self):
        import io
        import json
        from contextlib import redirect_stdout, redirect_stderr
        import markforge as MF
        out = os.path.join(common.temp_dir("gameout"), "staging")
        buf = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(buf):
            rc = MF.main(["build", "--client", self.client, "--patches", self.patches, "--out", out,
                          "--races", "Human:Male"])
        self.assertEqual(rc, 0, buf.getvalue())
        man = json.load(open(os.path.join(out, "marks_manifest.json")))
        self.assertEqual(man["source"], "game")
        self.assertTrue(man["gates"]["passed"])
        rs = man["race_sexes"][0]
        self.assertEqual(rs["model"], "Character\\Human\\Male\\HumanMale.m2")
        self.assertEqual(rs["eye_source"]["texture"].casefold(), self.eye.casefold())
        self.assertEqual(len(rs["marks"]), 12)


if __name__ == "__main__":
    unittest.main()
