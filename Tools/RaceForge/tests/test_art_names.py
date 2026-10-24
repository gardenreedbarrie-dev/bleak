"""The names of the customization art archives: the default, the guard against taken names, the patch folder scan,
the --art-letters override and --force-letters."""

import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL_DIR = os.path.dirname(HERE)
MPQPACK_DIR = os.path.join(os.path.dirname(TOOL_DIR), "MpqPack")

for path in (TOOL_DIR, MPQPACK_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

import raceforge  # noqa: E402
from rflib import patchnames  # noqa: E402
from tests import synth  # noqa: E402
from tests.test_customize import run_tool, write_package  # noqa: E402

TAKEN = patchnames.load_taken(raceforge.TAKEN_PATCHES)


def client_order(name):
    r"""Where Data\<name> sorts among the client's patch archives (SStrCmpI: lower case, then byte order)."""
    return f"data\\{name}".lower()


class NameTests(unittest.TestCase):
    def test_taken_list_holds_every_patch_in_use(self):
        realm = "HLRTVXYZ"
        reforged = "ABCDEGIMNPSU"

        for c in realm + reforged + "JQ" + "235":
            self.assertIn(patchnames.name_key(f"patch-{c}.MPQ"), TAKEN, c)

        self.assertIn(patchnames.name_key("enUS/patch-enUS-8.MPQ"), TAKEN)
        self.assertIn("Reforged", TAKEN[patchnames.name_key("patch-S.MPQ")])
        self.assertEqual(patchnames.free_characters(TAKEN, None, raceforge.DEFAULT_MPQ), "46789FKOW")

    def test_default_names_are_free_and_load_after_the_stock_patches(self):
        names = patchnames.art_archive_names(raceforge.DEFAULT_ART_LETTERS, raceforge.DEFAULT_MPQ)
        self.assertEqual(names, ["patch-6.MPQ", "patch-7.MPQ", "patch-8.MPQ", "patch-9.MPQ"])
        self.assertEqual(patchnames.problems(names, TAKEN), [])

        for name in names:
            self.assertGreater(client_order(name), client_order("patch-3.MPQ"), "outranks the stock patches")
            self.assertLess(client_order(name), client_order("patch-A.MPQ"), "below every lettered patch")

    def test_case_is_ignored(self):
        self.assertEqual(patchnames.problems(["patch-y.MPQ"], TAKEN), ["patch-y.MPQ is taken by " + TAKEN["patch-y.mpq"]])
        self.assertEqual(patchnames.art_archive_names("w", None), ["patch-W.MPQ"])

    def test_bad_characters_are_refused(self):
        for letters in ("", "0", "1", "2", "3", "SS", "~", "A-"):
            with self.assertRaises(patchnames.PatchNameError, msg=letters):
                patchnames.art_archive_names(letters, None)

        with self.assertRaisesRegex(patchnames.PatchNameError, "DBC archive"):
            patchnames.art_archive_names("R", "patch-R.MPQ")

    def test_taken_file_is_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "taken.json")

            with self.assertRaisesRegex(patchnames.PatchNameError, "missing"):
                patchnames.load_taken(path)

            for data, message in (({"taken": [{"names": ["patch-A.MPQ"]}]}, "comment"),
                                  ({"taken": [{"comment": "x", "names": []}]}, "names"),
                                  ({"taken": [{"comment": "x", "names": ["patch-A.MPQ"]}, {"comment": "y", "names": ["Patch-a.mpq"]}]}, "twice"),
                                  ({}, "taken")):
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f)

                with self.assertRaisesRegex(patchnames.PatchNameError, message):
                    patchnames.load_taken(path)

    def test_scan_reads_a_patch_folder_and_a_client_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "data", "enUS"))
            open(os.path.join(tmp, "patch-7.mpq"), "wb").close()
            open(os.path.join(tmp, "data", "Patch-8.MPQ"), "wb").close()
            os.makedirs(os.path.join(tmp, "patch-9.MPQ"))  # the client opens a folder of that name as an archive
            present = patchnames.scan_patches_dir(tmp)
            found = patchnames.problems(["patch-6.MPQ", "patch-7.MPQ", "patch-8.MPQ", "patch-9.MPQ"], {}, present)
            self.assertEqual([p.split()[0] for p in found], ["patch-7.MPQ", "patch-8.MPQ", "patch-9.MPQ"])

            with self.assertRaisesRegex(patchnames.PatchNameError, "not a folder"):
                patchnames.scan_patches_dir(os.path.join(tmp, "nothing"))


class BuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.stock = os.path.join(cls.tmp.name, "dbc")
        cls.package = os.path.join(cls.tmp.name, "package")
        synth.write_folder(cls.stock)
        write_package(cls.package)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def build(self, out, *args):
        return run_tool("build", "--dbc", self.stock, "--out", os.path.join(self.tmp.name, out), "--mpq", "--customization", self.package, *args)

    def client_files(self, out):
        return sorted(os.listdir(os.path.join(self.tmp.name, out, "client")))

    def test_taken_letters_are_refused_before_anything_is_written(self):
        for letters in ("S", "y", "6Z"):
            result = self.build(f"taken-{letters}", "--art-letters", letters)
            self.assertNotEqual(result.returncode, 0, letters)
            self.assertIn("refusing to write the customization art", result.stderr)
            self.assertIn("is taken by", result.stderr)
            self.assertIn("free: 4 6 7 8 9 F K O W", result.stderr)
            self.assertFalse(os.path.exists(os.path.join(self.tmp.name, f"taken-{letters}")), "refused before the output folder")

    def test_free_letter_override(self):
        result = self.build("override", "--art-letters", "W")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.client_files("override"), ["DBFilesClient", "patch-R.MPQ", "patch-W.MPQ"])

    def test_patches_dir_scan(self):
        patches = os.path.join(self.tmp.name, "realm-patches")
        os.makedirs(patches)

        for name in ("patch-6.mpq", "Patch-Y.MPQ", "patch-R.MPQ"):
            open(os.path.join(patches, name), "wb").close()

        result = self.build("scan", "--patches-dir", patches)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("patch-6.MPQ is already in the patch folder", result.stderr)
        self.assertIn("free: 4 7 8 9 F K O W", result.stderr)

        result = self.build("scan-ok", "--patches-dir", patches, "--art-letters", "7")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.client_files("scan-ok"), ["DBFilesClient", "patch-7.MPQ", "patch-R.MPQ"])

        with open(os.path.join(self.tmp.name, "scan-ok", "report.txt"), encoding="utf-8") as f:
            self.assertIn(f"--patches-dir {patches} (3 names)", f.read())

        result = self.build("scan-missing", "--patches-dir", os.path.join(self.tmp.name, "nowhere"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not a folder", result.stderr)

    def test_force_letters_writes_with_a_warning(self):
        result = self.build("forced", "--art-letters", "S", "--force-letters")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("WARNING: --force-letters", result.stderr)
        self.assertEqual(self.client_files("forced"), ["DBFilesClient", "patch-R.MPQ", "patch-S.MPQ"])

        with open(os.path.join(self.tmp.name, "forced", "report.txt"), encoding="utf-8") as f:
            report = f.read()

        self.assertIn("[WARN] art archive names (patch-S.MPQ)", report)
        self.assertIn("- --force-letters: patch-S.MPQ is taken by Reforged", report)

        # It never bypasses the character rule: the stock patches stay out of reach.
        result = self.build("forced-stock", "--art-letters", "3", "--force-letters")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--art-letters", result.stderr)

    def test_archive_size_limit(self):
        result = self.build("too-big", "--art-max-mb", str(raceforge.MAX_ART_MB + 1))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--art-max-mb", result.stderr)

    def test_art_spreads_over_the_default_names_in_order(self):
        package = os.path.join(self.tmp.name, "big-package")
        write_package(package)

        # Five files of 0.6 MB with 1 MB per archive: five archives, one more than the four default names.
        for i in range(5):
            with open(os.path.join(package, "Character", f"Big{i}.blp"), "wb") as f:
                f.write(bytes([i]) * 600_000)

        result = run_tool("build", "--dbc", self.stock, "--out", os.path.join(self.tmp.name, "big"), "--mpq", "--customization", package, "--art-max-mb", "1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("needs 5 archives", result.stderr)
        self.assertIn("patch-6.MPQ, patch-7.MPQ, patch-8.MPQ, patch-9.MPQ", result.stderr)

        result = run_tool("build", "--dbc", self.stock, "--out", os.path.join(self.tmp.name, "big2"), "--mpq", "--customization", package, "--art-max-mb", "1",
                          "--art-letters", "46789FW")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.client_files("big2"), ["DBFilesClient", "patch-4.MPQ", "patch-6.MPQ", "patch-7.MPQ", "patch-8.MPQ", "patch-9.MPQ",
                                                     "patch-R.MPQ"])

    def test_easy_mode_uses_the_default_names(self):
        result = run_tool(self.stock, self.package)
        out = os.path.join(self.tmp.name, raceforge.EASY_OUT)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(sorted(os.listdir(os.path.join(out, "client"))), ["DBFilesClient", "patch-6.MPQ", "patch-R.MPQ"])
        self.assertIn("client\\patch-6.MPQ -> the customization art", result.stdout)


if __name__ == "__main__":
    unittest.main()
