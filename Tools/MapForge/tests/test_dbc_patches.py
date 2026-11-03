"""Patch archives: the client's load order, optional packs, reading third-party archives, the placement plan and
rebuilding an archive with replaced files."""

import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL_DIR = os.path.dirname(HERE)

if TOOL_DIR not in sys.path:
    sys.path.insert(0, TOOL_DIR)

from dbc import plan as planmod  # noqa: E402
from dbc.patches import (PatchArchive, PatchError, PatchSet, archive_contents, outranks, rebuild,  # noqa: E402
                         sort_key)
from tests import synth_dbc, synth_mpq  # noqa: E402

import mpqpack  # noqa: E402

PACKS = {"hd": ["Data/patch-[ABCDEGIMNPSU].MPQ", "Data/Patch-Y.MPQ"]}
MAP = "DBFilesClient\\Map.dbc"
AREA = "DBFilesClient\\AreaTable.dbc"


class OrderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def put(self, rel: str, files: dict | None = None, **options):
        synth_mpq.write(os.path.join(self.tmp, rel), files or {"readme.txt": rel.encode()}, **options)

    def test_sort_key_follows_strnicmp(self):
        names = ["Data\\patch-Z.MPQ", "Data\\patch-~.MPQ", "Data\\patch-a.MPQ", "Data\\Patch-3.MPQ",
                 "Data\\enUS\\patch-enUS-9.MPQ", "Data\\patch-Q.MPQ"]
        ordered = sorted(names, key=sort_key)
        self.assertEqual(ordered, ["Data\\enUS\\patch-enUS-9.MPQ", "Data\\Patch-3.MPQ", "Data\\patch-a.MPQ",
                                   "Data\\patch-Q.MPQ", "Data\\patch-Z.MPQ", "Data\\patch-~.MPQ"])

    def test_scan_orders_like_the_client(self):
        for rel in ("patch.MPQ", "patch-3.MPQ", "Patch-Y.MPQ", "patch-z.MPQ", "patch-A.MPQ", "patch-Q.MPQ",
                    os.path.join("enUS", "patch-enUS-4.MPQ"), "patch-AB.MPQ", "notes.txt"):
            self.put(rel)

        patchset = PatchSet.scan(self.tmp, PACKS)

        try:
            self.assertEqual([a.name for a in patchset.archives],
                             ["patch.MPQ", "patch-enUS-4.MPQ", "patch-3.MPQ", "patch-A.MPQ", "patch-Q.MPQ",
                              "Patch-Y.MPQ", "patch-z.MPQ"])
            self.assertEqual({a.name: a.pack for a in patchset.archives if a.pack},
                             {"patch-A.MPQ": "hd", "Patch-Y.MPQ": "hd"})
            self.assertEqual([label for label, _ in patchset.configurations()], ["all packs", "no packs"])
            self.assertTrue(outranks("Data\\patch-Q.MPQ", [patchset.find("patch-A.MPQ")]))
            self.assertFalse(outranks("Data\\patch-Q.MPQ", [patchset.find("patch-z.MPQ")]))
        finally:
            patchset.close()

    def test_game_folder_is_accepted(self):
        self.put(os.path.join("Data", "patch-R.MPQ"))
        patchset = PatchSet.scan(self.tmp)

        try:
            self.assertEqual([a.client_path for a in patchset.archives], ["Data\\patch-R.MPQ"])
        finally:
            patchset.close()

    def test_top_copy_per_pack_combination(self):
        self.put("patch-R.MPQ", {AREA: b"R"})
        self.put("Patch-Y.MPQ", {AREA: b"Y", MAP: b"Y"})
        patchset = PatchSet.scan(self.tmp, PACKS)

        try:
            on, off = [packs for _, packs in patchset.configurations()]
            self.assertEqual(patchset.top(AREA, on).name, "Patch-Y.MPQ")
            self.assertEqual(patchset.top(AREA, off).name, "patch-R.MPQ")
            self.assertEqual(patchset.top(MAP, on).name, "Patch-Y.MPQ")
            self.assertIsNone(patchset.top(MAP, off))
        finally:
            patchset.close()


class ReaderTests(unittest.TestCase):
    DATA = bytes(range(256)) * 70 + b"tail"  # several sectors, the last one short

    def read(self, **options) -> bytes:
        name = "DBFilesClient\\Map.dbc"
        archive = PatchArchive(synth_mpq.build({name: self.DATA}, **options))
        return archive.read(name)

    def test_zlib(self):
        self.assertEqual(self.read(compression="zlib"), self.DATA)

    def test_bzip2(self):
        self.assertEqual(self.read(compression="bzip2"), self.DATA)

    def test_encrypted_with_fix_key_and_sector_checksums(self):
        self.assertEqual(self.read(compression="bzip2", encrypt=True, fix_key=True, sector_crc=True), self.DATA)
        self.assertEqual(self.read(compression="zlib", encrypt=True), self.DATA)
        self.assertEqual(self.read(compression="none", encrypt=True), self.DATA)

    def test_mpqpack_reader_refuses_what_ours_reads(self):
        data = synth_mpq.build({"a\\b.dbc": self.DATA}, compression="bzip2", encrypt=True)

        with self.assertRaises(mpqpack.MpqError):
            mpqpack.MpqArchive(data).read("a\\b.dbc")

        self.assertEqual(PatchArchive(data).read("a\\b.dbc"), self.DATA)

    def test_unsupported_compression_is_named(self):
        data = bytearray(synth_mpq.build({"x.dbc": self.DATA}, compression="bzip2"))
        archive = PatchArchive(bytes(data))
        block = archive.blocks[archive.find_block("x.dbc")]
        # The first sector's compression byte follows the sector table.
        sectors = (len(self.DATA) + 4095) // 4096
        data[block.offset + 4 * (sectors + 1)] = 0x08  # PKWARE implode

        with self.assertRaisesRegex(mpqpack.MpqError, "compression 0x08 is not supported"):
            PatchArchive(bytes(data)).read("x.dbc")


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.tables = synth_dbc.build_tables()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def plan(self, archives: dict[str, dict[str, bytes]], mode="auto", merge_into=None):
        for name, files in archives.items():
            synth_mpq.write(os.path.join(self.tmp, name), files)

        patchset = PatchSet.scan(self.tmp, PACKS)
        self.addCleanup(patchset.close)
        return patchset, planmod.plan(patchset, ["Map", "AreaTable"], "patch-Q.MPQ", mode, merge_into)

    def test_no_patch_holds_the_files(self):
        _, plan = self.plan({"patch-R.MPQ": {"DBFilesClient\\ChrRaces.dbc": b"x"}})
        self.assertEqual(plan.targets, [])
        self.assertEqual(sorted(plan.map_archive_tables()), ["AreaTable", "Map"])
        self.assertEqual(plan.problems, [])

    def test_merge_into_the_winning_realm_patch(self):
        _, plan = self.plan({"Patch-Z.MPQ": {MAP: self.tables["Map"]}, "Patch-Y.MPQ": {MAP: self.tables["Map"]}})
        self.assertEqual(plan.files["Map"].targets, ["Patch-Z.MPQ"])
        self.assertFalse(plan.files["Map"].in_map_archive)
        # AreaTable: nobody holds it, so the map archive carries it.
        self.assertTrue(plan.files["AreaTable"].in_map_archive)

    def test_pack_only_holder_needs_both(self):
        _, plan = self.plan({"Patch-Y.MPQ": {MAP: self.tables["Map"]}, "patch-R.MPQ": {AREA: b"R"},
                             "patch-V.MPQ": {AREA: b"V"}, "patch-A.MPQ": {AREA: b"A"}})
        # Map.dbc: players with the HD pack read Patch-Y's, players without it read the map archive's.
        self.assertEqual(plan.files["Map"].targets, ["Patch-Y.MPQ"])
        self.assertTrue(plan.files["Map"].in_map_archive)
        # AreaTable: patch-V wins for everybody (patch-A is lower even with the pack on).
        self.assertEqual(plan.files["AreaTable"].targets, ["patch-V.MPQ"])
        self.assertFalse(plan.files["AreaTable"].in_map_archive)

    def test_map_mode_refuses_a_losing_letter(self):
        _, plan = self.plan({"Patch-Z.MPQ": {MAP: b"z"}}, mode="map")
        self.assertTrue(any("Patch-Z.MPQ would load over patch-Q.MPQ" in p for p in plan.problems))

    def test_merge_mode_refuses_a_target_below_the_winner(self):
        _, plan = self.plan({"Patch-Z.MPQ": {MAP: b"z"}, "patch-X.MPQ": {"x.txt": b"x"}}, mode="merge",
                            merge_into="patch-X.MPQ")
        self.assertTrue(any("loads over patch-X.MPQ" in p for p in plan.problems))

    def test_our_own_earlier_archive_is_not_a_winner(self):
        # An earlier MapForge patch-Q.MPQ holding Map.dbc is skipped: patch-H's copy is the realm's, so the rows
        # are forged into patch-H (the realm's DBC baseline), and patch-Q carries only what nobody else holds.
        _, plan = self.plan({"patch-Q.MPQ": {MAP: b"old", "MapForge\\mapforge.txt": b"x"},
                             "patch-H.MPQ": {MAP: self.tables["Map"]}})
        self.assertEqual(plan.files["Map"].targets, ["patch-H.MPQ"])
        self.assertFalse(plan.files["Map"].in_map_archive)
        self.assertTrue(plan.files["AreaTable"].in_map_archive)
        self.assertEqual(plan.problems, [])

    def test_inputs_must_be_the_winning_copy(self):
        patchset, plan = self.plan({"Patch-Z.MPQ": {MAP: self.tables["Map"]}})
        self.assertEqual(planmod.check_inputs_current(patchset, plan, {"Map": self.tables["Map"]}), [])
        stale = planmod.check_inputs_current(patchset, plan, {"Map": self.tables["Map"] + b"!"})
        self.assertEqual(len(stale), 1)
        self.assertIn("differs from the winning copy in Patch-Z.MPQ", stale[0])

    def test_foreign_archive_with_the_map_archive_name(self):
        _, _ = self.plan({"patch-Q.MPQ": {"Interface\\x.blp": b"x"}})
        patchset = PatchSet.scan(self.tmp, PACKS)
        self.addCleanup(patchset.close)
        problems = planmod.check_map_archive_name("patch-Q.MPQ", patchset, "ABCDEGHIJLMNPRSTUVWXYZ")
        self.assertTrue(any("not written by MapForge" in p for p in problems))
        problems = planmod.check_map_archive_name("patch-W.MPQ", patchset, "ABCDEGHIJLMNPRSTUVWXYZ")
        self.assertTrue(any("reserved" in p for p in problems))


class RebuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_rebuild_keeps_every_other_file(self):
        files = {MAP: b"old map", "DBFilesClient\\Spell.dbc": b"spells" * 1000, "Interface\\a.blp": b"art"}
        synth_mpq.write(os.path.join(self.tmp, "in", "Patch-Z.MPQ"), files, compression="bzip2", encrypt=True,
                        fix_key=True, sector_crc=True)
        new_map = os.path.join(self.tmp, "Map.dbc")
        new_area = os.path.join(self.tmp, "AreaTable.dbc")

        with open(new_map, "wb") as f:
            f.write(b"new map")

        with open(new_area, "wb") as f:
            f.write(b"new area")

        patchset = PatchSet.scan(os.path.join(self.tmp, "in"))
        self.addCleanup(patchset.close)
        out = os.path.join(self.tmp, "Patch-Z.MPQ")
        replaced = rebuild(patchset.find("Patch-Z.MPQ"), {MAP: new_map, AREA: new_area}, out,
                           os.path.join(self.tmp, "staging"))
        self.assertEqual(replaced, [MAP])

        with mpqpack.MpqArchive(out) as archive:
            self.assertEqual(archive.verify().problems, [])
            self.assertEqual(sorted(archive.names()), sorted([MAP, AREA, "DBFilesClient\\Spell.dbc",
                                                              "Interface\\a.blp"]))
            self.assertEqual(archive.read(MAP), b"new map")
            self.assertEqual(archive.read(AREA), b"new area")
            self.assertEqual(archive.read("DBFilesClient\\Spell.dbc"), b"spells" * 1000)

        self.assertFalse(os.path.exists(os.path.join(self.tmp, "staging")))

    def test_archive_without_listfile_is_refused(self):
        synth_mpq.write(os.path.join(self.tmp, "in", "Patch-Z.MPQ"), {MAP: b"m"}, listfile=False)
        patchset = PatchSet.scan(os.path.join(self.tmp, "in"))
        self.addCleanup(patchset.close)

        with self.assertRaisesRegex(PatchError, "no \\(listfile\\)"):
            archive_contents(patchset.find("Patch-Z.MPQ").reader, "Patch-Z.MPQ")


if __name__ == "__main__":
    unittest.main()
