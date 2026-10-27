"""package.py resolve-assets (which modern files the sources hold, and everything they need) and how package.py build
ships extra assets: the modern files go into the map archive, the server's extract patch gets the tiles without
modern doodads. Made-up files only (tests/synth_assets.py, tests/synth_mpq.py)."""

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL_DIR = os.path.dirname(HERE)

if TOOL_DIR not in sys.path:
    sys.path.insert(0, TOOL_DIR)

import package  # noqa: E402
from dbc.patches import PatchArchive  # noqa: E402
from dbc.sources import SourceSet  # noqa: E402
from terrain import build as tbuild  # noqa: E402
from terrain import validate as tvalidate  # noqa: E402
from terrain.extra_assets import Resolution, ResolutionError, m2_dependencies  # noqa: E402
from tests import synth_assets, synth_dbc, synth_mpq  # noqa: E402

import mpqpack  # noqa: E402

HD_SAND = "Tileset\\Modern\\HD_Sand.blp"
HD_TREE = "World\\Modern\\Trees\\HD_Palm.m2"
HD_LEAF = "World\\Modern\\Trees\\HD_PalmLeaf.blp"
HD_BUSH = "World\\Modern\\Bushes\\HD_Bush.m2"  # its skin is missing everywhere
HD_FDID = "World\\Modern\\Trees\\HD_Retail.m2"  # names its skin by FileDataID
HD_NOBLP = "Tileset\\Modern\\HD_Broken.blp"
STOCK_TEX = "Tileset\\Made\\Up\\Stock.blp"

SPEC = {
    "map": {"directory": "BleakholdRoyale", "tiles": {"x": [32, 32], "y": [32, 32]}, "id": 901},
    "seed": 3,
    "area_id": 5100,
    "heightmap": {"base": 12.0},
    "textures": [{"name": "g", "path": "Tileset\\Made\\Up\\Grass.blp"},
                 {"name": "s", "path": {"modern": HD_SAND, "fallback": "Tileset\\Made\\Up\\Sand.blp"}},
                 {"name": "b", "path": {"modern": HD_NOBLP, "fallback": "Tileset\\Made\\Up\\Rock.blp"}},
                 {"name": "k", "path": {"modern": STOCK_TEX, "fallback": "Tileset\\Made\\Up\\Dirt.blp"}}],
    "texture_rules": [{"texture": "s", "shape": {"circle": {"center": [-200, -200], "radius": 80}}},
                      {"texture": "b", "shape": {"circle": {"center": [-400, -400], "radius": 60}}},
                      {"texture": "k", "shape": {"circle": {"center": [-100, -420], "radius": 60}}}],
    "doodads": [{"model": {"modern": HD_TREE, "fallback": "World\\Made\\Up\\Palm.m2"}, "position": [-100, -100],
                 "label": "palm"},
                {"model": {"modern": HD_BUSH, "fallback": "World\\Made\\Up\\Bush.m2"}, "position": [-150, -100]},
                {"model": {"modern": HD_FDID, "fallback": "World\\Made\\Up\\Palm2.m2"}, "position": [-200, -100]},
                {"model": "World\\Made\\Up\\Rock.m2", "position": [-250, -100]}],
}


def run(*argv) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = package.main(list(argv))
    return code, out.getvalue()


def make_sources(root: str) -> tuple[str, str]:
    """A loose folder (the sand and its _s, an older palm) and a patch folder in client order (patch-A holds a stale
    palm, patch-S the current one with its skins, leaf texture and anim, plus the broken models)."""
    loose = os.path.join(root, "loose")
    synth_assets.write(loose, {HD_SAND: synth_assets.blp(), HD_SAND[:-4] + "_s.blp": synth_assets.blp(),
                               HD_NOBLP: b"not a blp"})
    patches = os.path.join(root, "patches")
    os.makedirs(patches)
    palm = synth_assets.m2(textures=[HD_LEAF, STOCK_TEX], skins=2,
                           sequences=[(0, 0, 0x20), (4, 0, 0), (5, 1, 0x40)], collision=12, version=272)
    stale = synth_assets.m2(textures=[HD_LEAF], skins=1)
    synth_mpq.write(os.path.join(patches, "patch-A.MPQ"), {HD_TREE: stale})
    synth_mpq.write(os.path.join(patches, "patch-S.MPQ"), {
        HD_TREE: palm,
        HD_TREE[:-3] + "00.skin": b"SKIN0", HD_TREE[:-3] + "01.skin": b"SKIN1",
        HD_TREE[:-3] + "0004-00.anim": b"ANIM",
        HD_LEAF: synth_assets.blp(),
        HD_BUSH: synth_assets.m2(skins=1),
        HD_FDID: synth_assets.m2_fdid(),
    })
    return loose, patches


class ResolveAssets(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.spec = os.path.join(self.tmp, "spec.json")
        with open(self.spec, "w", encoding="utf-8") as f:
            json.dump(SPEC, f)
        self.loose, self.patches = make_sources(self.tmp)
        self.listfile = os.path.join(self.tmp, "listfile.txt")
        with open(self.listfile, "w", encoding="utf-8") as f:
            f.write(f"{STOCK_TEX}\n{STOCK_TEX[:-4]}_s.blp\n")
        self.out = os.path.join(self.tmp, "resolved")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def resolve(self, *sources, extra=()):
        return run("resolve-assets", "--spec", self.spec, "--out", self.out, "--listfile", self.listfile,
                   "--sources", *sources, *extra)

    def entries(self):
        with open(os.path.join(self.out, "asset_resolution.json"), encoding="utf-8") as f:
            return {e["modern"]: e for e in json.load(f)["assets"]}

    def test_resolution(self):
        code, output = self.resolve(self.patches, self.loose)
        self.assertEqual(code, 0, output)
        e = self.entries()
        self.assertEqual(set(e), {HD_SAND, HD_NOBLP, STOCK_TEX, HD_TREE, HD_BUSH, HD_FDID})
        sand = e[HD_SAND]
        self.assertEqual((sand["status"], sand["specular"]), ("resolved", True))
        self.assertEqual(sorted(f["path"] for f in sand["files"]), sorted([HD_SAND, HD_SAND[:-4] + "_s.blp"]))
        palm = e[HD_TREE]
        self.assertEqual(palm["status"], "resolved", palm["reason"])
        self.assertIn("patch-S.MPQ", palm["source"])  # the archive the client would load, not patch-A
        self.assertTrue(palm["collision"])
        self.assertEqual(palm["format"], "M2 version 272")
        # Skins by profile count, the texture table's names (the stock one is not copied), the streamed anim only.
        self.assertEqual(sorted(f["path"] for f in palm["files"]),
                         sorted([HD_TREE, HD_TREE[:-3] + "00.skin", HD_TREE[:-3] + "01.skin",
                                 HD_TREE[:-3] + "0004-00.anim", HD_LEAF]))
        self.assertEqual(palm["stock"], [STOCK_TEX])
        self.assertEqual(e[HD_BUSH]["status"], "fallback")
        self.assertIn("HD_Bush00.skin", e[HD_BUSH]["reason"])
        self.assertIn("FileDataID", e[HD_FDID]["reason"])
        self.assertIn("not a BLP", e[HD_NOBLP]["reason"])
        self.assertEqual((e[STOCK_TEX]["status"], e[STOCK_TEX]["files"]), ("resolved", []))
        # Every shipped file is copied (an HD-pack file must end up in the map archive), with its hash.
        for entry in e.values():
            for f in entry["files"]:
                with open(os.path.join(self.out, *f["file"].split("/")), "rb") as fh:
                    self.assertEqual(len(fh.read()), f["size"])

    def test_first_source_wins(self):
        stale = os.path.join(self.tmp, "stale")
        synth_assets.write(stale, {HD_SAND: synth_assets.blp()})
        sources = SourceSet([stale, self.loose])
        try:
            self.assertIn("stale", sources.find(HD_SAND))
            self.assertIsNone(sources.find("Nope\\Missing.blp"))
        finally:
            sources.close()

    def test_an_unreadable_top_copy_falls_back(self):
        # patch-S holds the current palm as an LZMA sector (Storm reads it, MapForge does not): the client loads that
        # copy, so patch-A's older palm must not be shipped with patch-S's skins in its place.
        path = os.path.join(self.patches, "patch-S.MPQ")
        reader = PatchArchive(path)
        try:
            sector = b"\x02" + zlib.compress(reader.read(HD_TREE))
        finally:
            reader.close()
        with open(path, "rb") as f:
            data = f.read()
        self.assertEqual(data.count(sector), 1)
        with open(path, "wb") as f:
            f.write(data.replace(sector, b"\x12" + sector[1:]))
        code, output = self.resolve(self.patches, self.loose)
        self.assertEqual(code, 0, output)
        palm = self.entries()[HD_TREE]
        self.assertEqual((palm["status"], palm["files"]), ("fallback", []), palm)
        self.assertIn("patch-S.MPQ", palm["reason"])
        self.assertIn("cannot be read", palm["reason"])
        self.assertIn("warning:", output)
        self.assertFalse(os.path.exists(os.path.join(self.out, "files", *HD_TREE.split("\\"))))

    def test_a_texture_two_models_spell_differently_is_one_file(self):
        a, b = "World\\Modern\\Trees\\A_Tree.m2", "World\\Modern\\Trees\\B_Tree.m2"
        leaf = "World\\Modern\\Trees\\Leaf.blp"
        folder = os.path.join(self.tmp, "cased")
        synth_assets.write(folder, {a: synth_assets.m2(textures=[leaf]), a[:-3] + "00.skin": b"SKINA",
                                    b: synth_assets.m2(textures=[leaf.upper()]), b[:-3] + "00.skin": b"SKINB",
                                    leaf: synth_assets.blp()})
        data = dict(SPEC, textures=SPEC["textures"][:1], texture_rules=[],
                    doodads=[{"model": {"modern": b, "fallback": "World\\Made\\Up\\B.m2"}, "position": [-100, -100]},
                             {"model": {"modern": a, "fallback": "World\\Made\\Up\\A.m2"}, "position": [-150, -100]}])
        with open(self.spec, "w", encoding="utf-8") as f:
            json.dump(data, f)
        code, output = self.resolve(folder)
        self.assertEqual(code, 0, output)
        e = self.entries()
        files = {f["path"]: f["file"] for x in (e[a], e[b]) for f in x["files"] if f["path"].lower() == leaf.lower()}
        self.assertEqual(set(files), {leaf, leaf.upper()})
        self.assertEqual(len(set(files.values())), 1)  # both point at the one copy under files/
        self.assertTrue(os.path.isfile(os.path.join(self.out, *next(iter(files.values())).split("/"))))
        result = tbuild.build_from_file(self.spec, Resolution.load(self.out))  # B (upper case) is used first
        self.assertEqual([e["path"].lower() for e in result.manifest["extra_files"]].count(leaf.lower()), 1)

    def test_a_retail_listfile_is_refused(self):
        retail = os.path.join(self.tmp, "listfile.csv")
        with open(retail, "w", encoding="utf-8") as f:
            f.write(f"530035;{HD_TREE.replace(chr(92), '/')}\n")
        code, output = run("resolve-assets", "--spec", self.spec, "--out", self.out, "--listfile", retail,
                           "--sources", self.patches)
        self.assertEqual(code, 2)
        self.assertIn("retail listfile.csv", output)
        self.assertFalse(os.path.exists(self.out))

    def test_a_dependency_outside_the_folders_falls_back(self):
        # A third-party archive whose model names '..\..\escaped.blp' (and holds a file of that name).
        escape = "..\\..\\escaped.blp"
        archive = os.path.join(self.tmp, "Reforged.MPQ")
        synth_mpq.write(archive, {HD_TREE: synth_assets.m2(textures=[escape]), HD_TREE[:-3] + "00.skin": b"SKIN",
                                  escape: synth_assets.blp()})
        self.out = os.path.join(self.tmp, "work", "resolved")
        code, output = self.resolve(archive)
        self.assertEqual(code, 0, output)
        palm = self.entries()[HD_TREE]
        self.assertEqual(palm["status"], "fallback")
        self.assertIn("not a plain relative client path", palm["reason"])
        self.assertEqual(os.listdir(os.path.join(self.tmp, "work")), ["resolved"])
        self.assertFalse(os.path.exists(os.path.join(self.out, "escaped.blp")))
        # A resolution file that names such a path (edited by hand) is refused before the build reads or writes.
        doc = {"format": "mapforge-assets/1", "assets": [
            {"modern": HD_TREE, "kind": "doodad", "status": "resolved",
             "files": [{"path": escape, "file": "files/../../escaped.blp", "sha256": "", "size": 0}]}]}
        with self.assertRaisesRegex(ResolutionError, "not a plain path"):
            Resolution(doc, self.tmp)

    def test_a_stock_model_stays_in_the_server_copy(self):
        # A modern path the 3.3.5 listfile holds resolves as stock: every client and the server's extractors have
        # it, so the server copy keeps it (collision and line of sight), unlike a shipped modern model.
        stock_m2 = "World\\Made\\Up\\StockTree.m2"
        data = dict(SPEC, doodads=SPEC["doodads"] + [
            {"model": {"modern": stock_m2, "fallback": "World\\Made\\Up\\Palm3.m2"}, "position": [-300, -100]}])
        with open(self.spec, "w", encoding="utf-8") as f:
            json.dump(data, f)
        with open(self.listfile, "a", encoding="utf-8") as f:
            f.write(f"{stock_m2}\n")
        self.assertEqual(self.resolve(self.patches, self.loose)[0], 0)
        entry = self.entries()[stock_m2]
        self.assertEqual((entry["status"], entry["source"]), ("resolved", "stock"))
        result = tbuild.build_from_file(self.spec, Resolution.load(self.out))
        stock = [d for d in result.context.doodads if d.model == stock_m2]
        self.assertEqual(len(stock), 1)
        self.assertFalse(stock[0].modern)
        self.assertEqual(result.manifest["server_doodads_left_out"], 1)  # the HD palm only
        terrain = os.path.join(self.tmp, "terrain")
        tbuild.write(result, terrain, preview=False)
        rep = tvalidate.validate_map(terrain)
        self.assertEqual(rep.errors, [])
        server = tvalidate.parse_adt(os.path.join(terrain, "server", "World", "Maps", "BleakholdRoyale",
                                                  "BleakholdRoyale_32_32.adt"), 32, 32, tvalidate.Report())
        self.assertIn(stock_m2, server.m2_names)
        self.assertNotIn(HD_TREE, server.m2_names)

    def test_offline_and_force(self):
        code, output = run("resolve-assets", "--spec", self.spec, "--out", self.out)
        self.assertEqual(code, 0, output)
        e = self.entries()
        self.assertTrue(all(x["status"] == "fallback" and "offline" in x["reason"] for x in e.values()))
        code, output = run("resolve-assets", "--spec", self.spec, "--out", self.out)
        self.assertEqual(code, 2)
        self.assertIn("--force", output)

    def test_the_terrain_build_takes_it(self):
        self.assertEqual(self.resolve(self.patches, self.loose)[0], 0)
        result = tbuild.build_from_file(self.spec, Resolution.load(self.out))
        used = {u.modern: u.modern_used for u in result.context.spec.assets}
        self.assertEqual(used, {HD_SAND: True, HD_NOBLP: False, STOCK_TEX: True, HD_TREE: True, HD_BUSH: False,
                                HD_FDID: False})
        self.assertTrue(any("collision geometry" in w for w in result.manifest["warnings"]))
        shipped = sorted(e["path"] for e in result.manifest["extra_files"])
        self.assertNotIn(STOCK_TEX, shipped)
        self.assertIn(HD_LEAF, shipped)


class ModelVersions(unittest.TestCase):
    """The client loads an MD20 at 264 as it is and converts 272-274 (MD20 or MD21) at load (ModernAssets.cpp
    MayTransform, WarcraftXL Contract.hpp); M2Init refuses everything else, so it must fall back."""

    def test_versions(self):
        for version in (264, 272, 273, 274):
            with self.subTest(version=version):
                self.assertEqual(m2_dependencies(HD_TREE, synth_assets.m2(version=version))["version"], version)
        self.assertEqual(m2_dependencies(HD_TREE, synth_assets.md21(synth_assets.m2(version=274)))["version"], 274)
        for data, text in ((synth_assets.m2(version=263), "before 264"), (synth_assets.m2(version=268), "268"),
                           (synth_assets.m2(version=275), "275"),
                           (synth_assets.md21(synth_assets.m2(version=264)), "264 in an MD21 chunk")):
            with self.subTest(text=text):
                with self.assertRaisesRegex(ResolutionError, text):
                    m2_dependencies(HD_TREE, data)


class BuildShipsExtraAssets(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        spec = os.path.join(self.tmp, "spec.json")
        with open(spec, "w", encoding="utf-8") as f:
            json.dump(SPEC, f)
        loose, patches = make_sources(self.tmp)
        listfile = os.path.join(self.tmp, "listfile.txt")
        with open(listfile, "w", encoding="utf-8") as f:
            f.write(f"{STOCK_TEX}\n")
        resolved = os.path.join(self.tmp, "resolved")
        code, output = run("resolve-assets", "--spec", spec, "--out", resolved, "--listfile", listfile,
                           "--sources", patches, loose)
        self.assertEqual(code, 0, output)
        self.terrain = os.path.join(self.tmp, "terrain")
        tbuild.write(tbuild.build_from_file(spec, Resolution.load(resolved)), self.terrain, preview=False)
        self.dbc = os.path.join(self.tmp, "dbc")
        synth_dbc.write_tables(self.dbc)
        self.config = os.path.join(self.tmp, "map.json")
        with open(self.config, "w", encoding="utf-8") as f:
            json.dump(synth_dbc.default_config(), f)
        self.realm = os.path.join(self.tmp, "realm")
        os.makedirs(self.realm)
        self.out = os.path.join(self.tmp, "out")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def build(self):
        return run("build", "--config", self.config, "--dbc", self.dbc, "--terrain", self.terrain,
                   "--patches", self.realm, "--out", self.out)

    def test_map_archive_and_extract_patch(self):
        with open(os.path.join(self.terrain, "extra_assets", *HD_LEAF.split("\\")), "rb") as f:
            leaf = f.read()
        # The HD pack holds the leaf texture already (same bytes) and an older palm (other bytes, loads over Q).
        synth_mpq.write(os.path.join(self.realm, "patch-S.MPQ"), {HD_LEAF: leaf, HD_TREE: b"MD20old"})
        code, output = self.build()
        self.assertEqual(code, 0, output)
        self.assertIn(f"{HD_LEAF}: also in patch-S.MPQ (pack hd), same bytes", output)
        self.assertIn(f"[WARN] {HD_TREE}: patch-S.MPQ (pack hd) holds a different copy and loads over", output)
        with open(os.path.join(self.terrain, "terrain_manifest.json"), encoding="utf-8") as f:
            manifest = json.load(f)
        with mpqpack.MpqArchive(os.path.join(self.out, "client", "patch-Q.MPQ")) as archive:
            for e in manifest["extra_files"]:
                with open(os.path.join(self.terrain, *e["file"].split("/")), "rb") as f:
                    self.assertEqual(archive.read(e["path"]), f.read(), e["path"])
            client_adt = archive.read("World\\Maps\\BleakholdRoyale\\BleakholdRoyale_32_32.adt")
        with mpqpack.MpqArchive(os.path.join(self.out, "server", "extract", "patch-5.MPQ")) as archive:
            server_adt = archive.read("World\\Maps\\BleakholdRoyale\\BleakholdRoyale_32_32.adt")
            self.assertFalse(any(n.lower().startswith("world\\modern") for n in archive.names()))
        with open(os.path.join(self.terrain, "server", "World", "Maps", "BleakholdRoyale",
                               "BleakholdRoyale_32_32.adt"), "rb") as f:
            self.assertEqual(server_adt, f.read())
        self.assertIn(HD_TREE.encode("ascii"), client_adt)
        self.assertNotIn(HD_TREE.encode("ascii"), server_adt)

    def test_tampered_extra_file_stops_the_build(self):
        with open(os.path.join(self.terrain, "extra_assets", *HD_LEAF.split("\\")), "ab") as f:
            f.write(b"x")
        code, output = self.build()
        self.assertEqual(code, 2)
        self.assertIn("differs from the terrain manifest", output)


if __name__ == "__main__":
    unittest.main(verbosity=2)
