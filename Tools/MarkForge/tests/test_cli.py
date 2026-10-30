"""markforge.py end to end: the fixture, a build of a synthetic package (gates, manifest, validate, --check), the
manifest fields RaceForge's customize --marks reads, and the refusal to write into the repository."""

import io
import json
import os
import shutil
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest import mock

import common

import markforge as MF
from mflib import draw as W


def run(args):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = MF.main(args)
    return rc, out.getvalue() + err.getvalue()


class Cli(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pkg = common.temp_dir("pkg")
        common.write_package(cls.pkg)
        cls.out = os.path.join(common.temp_dir("out"), "staging")
        cls.rc, cls.log = run(["build", "--package", cls.pkg, "--out", cls.out, "--races", "Human:Male"])

    def test_build_passes_its_gates(self):
        self.assertEqual(self.rc, 0, self.log)
        self.assertIn("RESULT ok", self.log)
        man = json.load(open(os.path.join(self.out, "marks_manifest.json")))
        self.assertTrue(man["gates"]["passed"])
        self.assertEqual(man["gates"]["keepout_ink"], 0)
        self.assertEqual(man["gates"]["garment_ink"], 0)
        self.assertLessEqual(man["gates"]["seam_max"], MF.SEAM_LIMIT)

    def test_manifest_fields_customize_reads(self):
        man = json.load(open(os.path.join(self.out, "marks_manifest.json")))
        self.assertEqual(man["format"], "bleakhold-marks/1")
        if os.path.isfile(MF.CATALOGUE):
            self.assertEqual(man["catalogue_version"], json.load(open(MF.CATALOGUE))["version"])
        self.assertNotIn("fixture", man)
        rs = man["race_sexes"][0]
        for k in ("race", "race_file", "sex", "sex_name"):
            self.assertIn(k, rs)
        self.assertEqual((rs["race"], rs["race_file"], rs["sex"], rs["sex_name"]), (1, "Human", 0, "Male"))
        self.assertEqual([m["look"] for m in rs["marks"]], list(range(1, 13)))
        for m in rs["marks"]:
            for k in ("look", "design", "colour", "design_key", "design_name", "colour_key", "colour_name", "hex",
                      "glow", "texture", "sha1", "glow_texture", "glow_sha1"):
                self.assertIn(k, m)
            self.assertEqual(m["look"], 3 * (m["design"] - 1) + m["colour"])
            self.assertEqual(m["glow"], m["colour"] != 3)
            self.assertEqual(m["glow_texture"] is not None, m["glow"])
            self.assertTrue(os.path.isfile(os.path.join(self.out, "files", *m["texture"].split("\\"))))
        self.assertEqual([e["eye"] for e in rs["eyes"]], [1, 2, 3, 4, 5])
        self.assertEqual([e["dk_only"] for e in rs["eyes"]], [False, False, False, True, True])
        for e in rs["eyes"]:
            for k in ("eye", "key", "name", "hex", "dk_only", "texture", "sha1"):
                self.assertIn(k, e)
            self.assertTrue(e["texture"].startswith("Character\\BleakholdEyes\\Human\\Male\\Eye_"))

    def test_manifest_names_its_source_races_and_garment(self):
        man = json.load(open(os.path.join(self.out, "marks_manifest.json")))
        self.assertEqual(man["source"], "folder")
        self.assertEqual(man["races_requested"], "Human:Male")
        self.assertEqual(man["race_sexes"][0]["garment_missing"], 0, "the synthetic package has all its underwear")

    def test_a_folder_build_that_did_not_read_an_underwear_fails_its_gate(self):
        """A --package build reads on past a texture it cannot read (a dev folder may lack art), but the garment
        mask then misses that underwear: the gate fails and the manifest says so (customize --marks refuses it)."""
        pkg = common.temp_dir("pkg-missing")
        common.write_package(pkg)
        os.remove(os.path.join(pkg, "Character", "Human", "Male", "HumanMaleNakedTorsoSkin00_01.blp"))
        out = os.path.join(common.temp_dir("missing-out"), "staging")
        rc, log = run(["build", "--package", pkg, "--out", out, "--races", "Human:Male", "--no-eyes"])
        self.assertEqual(rc, 1, log)
        self.assertIn("RESULT FAILED", log)
        self.assertIn("Human Male: garment: colour 1: the torso underwear was not read", log)
        man = json.load(open(os.path.join(out, "marks_manifest.json")))
        self.assertFalse(man["gates"]["passed"])
        self.assertEqual(man["race_sexes"][0]["garment_missing"], 1)

    def test_validate_and_check(self):
        rc, log = run(["validate", self.out])
        self.assertEqual(rc, 0, log)
        rc, log = run(["build", "--package", self.pkg, "--out", self.out, "--races", "Human:Male", "--check"])
        self.assertEqual(rc, 0, log)
        self.assertIn("0 problem(s)", log)

    def test_check_finds_a_changed_file(self):
        copy = os.path.join(common.temp_dir("copy"), "staging")
        shutil.copytree(self.out, copy)
        man = json.load(open(os.path.join(copy, "marks_manifest.json")))
        path = os.path.join(copy, "files", *man["race_sexes"][0]["marks"][0]["texture"].split("\\"))
        data = bytearray(open(path, "rb").read())
        data[-1] ^= 1
        open(path, "wb").write(bytes(data))
        rc, log = run(["build", "--package", self.pkg, "--out", copy, "--races", "Human:Male", "--check"])
        self.assertEqual(rc, 1)
        self.assertIn("differs:", log)
        rc, log = run(["validate", copy])
        self.assertEqual(rc, 1)

    def test_a_file_breaking_the_rules_fails_the_build(self):
        """The file rules are a gate: a _Glow whose alpha differs from its mark's fails the build and the manifest
        says gates.passed false (customize --marks refuses that)."""
        from unittest import mock
        real = W.Look.blp

        def bad_glow(look, glow=False):
            data = real(look, glow)
            if not glow:
                return data
            data = bytearray(data)
            data[-1] ^= 0xFF  # the alpha byte of the 1x1 level
            return bytes(data)

        out = os.path.join(common.temp_dir("badglow"), "staging")
        with mock.patch.object(W.Look, "blp", bad_glow):
            rc, log = run(["build", "--package", self.pkg, "--out", out, "--races", "Human:Male", "--no-eyes"])
        self.assertEqual(rc, 1, log)
        self.assertIn("RESULT FAILED", log)
        self.assertIn("alpha of level 9 differs", log)
        man = json.load(open(os.path.join(out, "marks_manifest.json")))
        self.assertFalse(man["gates"]["passed"])

    def test_build_preview_prepares_one_race_sex_at_a_time(self):
        # the previews come after the gated output, from each race-sex prepared again; the build keeps no Prepared
        out = os.path.join(common.temp_dir("bpv"), "staging")
        alive, peak, calls = [0], [0], [0]
        real = MF.prepare

        def counted(*a, **k):
            p = real(*a, **k)
            calls[0] += 1
            alive[0] += 1
            peak[0] = max(peak[0], alive[0])
            import weakref
            weakref.finalize(p, lambda: alive.__setitem__(0, alive[0] - 1))
            return p

        with mock.patch.object(MF, "prepare", counted):
            rc, log = run(["build", "--package", self.pkg, "--out", out, "--races", "Human:Male", "--no-eyes",
                           "--preview"])
        self.assertEqual(rc, 0, log)
        names = os.listdir(os.path.join(out, "previews"))
        self.assertTrue(any(n.startswith("Human_Male_") and n.endswith("_sheet.png") for n in names), names)
        self.assertEqual(calls[0], 2, "the build's Prepared, then the previews' own")
        self.assertEqual(peak[0], 1, "the build's is let go before the previews make theirs")

    def test_refuses_the_repository(self):
        rc, log = run(["build", "--package", self.pkg, "--out", os.path.join(MF.mflib.REPO, "staging-test"),
                       "--races", "Human:Male"])
        self.assertEqual(rc, 2)
        self.assertIn("inside the repository", log)
        self.assertFalse(os.path.exists(os.path.join(MF.mflib.REPO, "staging-test")))

    def test_fixture(self):
        out = os.path.join(common.temp_dir("fx"), "fx")
        rc, log = run(["fixture", "--out", out])
        self.assertEqual(rc, 0, log)
        man = json.load(open(os.path.join(out, "marks_manifest.json")))
        self.assertTrue(man["fixture"])
        self.assertTrue(man["gates"]["passed"])
        self.assertEqual(len(man["race_sexes"][0]["marks"]), 12)
        rc, log = run(["validate", out])
        self.assertEqual(rc, 0, log)
        rc, log = run(["fixture", "--out", out, "--check"])
        self.assertEqual(rc, 0, log)
        grid = open(os.path.join(out, "files", "Character", "BleakholdMarks", "Fixture", "SectionGrid.blp"), "rb").read()
        self.assertEqual(W.mark_problems(grid, "grid"), [])
        bad = os.path.join(out, "files", "Character", "BleakholdMarks", "Fixture", "Bad")
        names = sorted(os.listdir(bad))
        self.assertIn("NotPalettized.blp", names)
        for n in ("NotPalettized", "WrongSize384", "NotSquare", "NoMips", "MissingLevel", "Alpha2", "Truncated"):
            data = open(os.path.join(bad, n + ".blp"), "rb").read()
            self.assertTrue(W.mark_problems(data, n), n)
        g = open(os.path.join(bad, "GlowAlphaMismatch.blp"), "rb").read()
        gg = open(os.path.join(bad, "GlowAlphaMismatch_Glow.blp"), "rb").read()
        self.assertTrue(W.glow_problems(g, gg, "x"))
        # each Bad file says what the exe does with it: skipped, or pasted (the VPS gates catch those)
        expect = {b["texture"].rsplit("\\", 1)[-1]: b["expect"] for b in man["bad_files"]}
        self.assertTrue(expect["WrongSize384.blp"].startswith("skipped"))
        self.assertTrue(expect["GlowAlphaMismatch.blp"].startswith("pasted"), expect)
        self.assertIn("_Glow is skipped", expect["GlowSizeMismatch.blp"])

    def test_bad_file_facts_for_the_exe_test_are_current(self):
        # test_marks_core.cpp holds these against BleakMarks.h: the .inc must be what the fixture makes today
        import make_fixture_facts
        with open(make_fixture_facts.PATH, encoding="utf-8") as f:
            self.assertEqual(f.read(), make_fixture_facts.text(),
                             "run python3 -I Tools/MarkForge/tests/make_fixture_facts.py")

    def test_preview_writes_pictures(self):
        out = common.temp_dir("pv")
        rc, log = run(["preview", "--package", self.pkg, "--out", out, "--look", "Human:Male:LightsOath:HolyGold",
                       "--eye", "TidalTeal"])
        self.assertEqual(rc, 0, log)
        names = sorted(os.listdir(out))
        self.assertEqual(len([n for n in names if n.endswith(".png")]), 3)
        for n in names:
            self.assertEqual(open(os.path.join(out, n), "rb").read(8), b"\x89PNG\r\n\x1a\n")

    def test_doctor(self):
        rc, log = run(["doctor"])
        self.assertEqual(rc, 0, log)
        self.assertIn("numpy", log)


if __name__ == "__main__":
    unittest.main()
