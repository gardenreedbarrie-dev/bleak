"""Extra assets in the terrain build: {"modern", "fallback", "kind"} paths, the offline fallback, a resolution
file's choices, the server's extract copy without modern doodads, and the validator's path rules."""

import copy
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_terrain_support import map_folder, validate  # noqa: E402

from terrain import build as tbuild  # noqa: E402
from terrain.extra_assets import Resolution  # noqa: E402
from terrain.spec import parse_spec  # noqa: E402
from terrain.spec_errors import SpecError  # noqa: E402

HD_SAND = "Tileset\\Modern\\HD_Sand.blp"
HD_TREE = "World\\Modern\\HD_Tree.m2"
HD_FALL = "World\\Modern\\HD_Fall.m2"
SAND = "Tileset\\Made\\Up\\Sand.blp"
TREE = "World\\Made\\Up\\Tree.m2"
FALL = "World\\Made\\Up\\Fall.m2"

ASSET_SPEC = {
    "map": {"directory": "AssetT", "tiles": {"x": [32, 32], "y": [32, 32]}},
    "seed": 77,
    "area_id": 1,
    "heightmap": {"base": 20.0, "noise": [{"scale": 100, "amplitude": 2.0}]},
    "textures": [{"name": "g", "path": "Tileset\\Made\\Up\\Grass.blp"},
                 {"name": "s", "path": {"modern": HD_SAND, "fallback": SAND, "kind": "texture"}, "mtxf_flags": 1}],
    "texture_rules": [{"texture": "s", "shape": {"circle": {"center": [-266, -266], "radius": 120}}, "fade": 20}],
    "doodads": [{"model": {"modern": HD_TREE, "fallback": TREE, "kind": "doodad"}, "position": [-100, -100],
                 "radius": 4, "label": "hd tree"},
                {"model": "World\\Made\\Up\\Rock.m2", "position": [-120, -100], "radius": 3}],
    "wmos": [{"model": "World\\wmo\\Made\\Up\\Hut.wmo", "position": [-400, -100], "radius": 12}],
    "rivers": [{"name": "r", "width": 10, "reaches": [{"level": 18, "path": [[-50, -300], [-150, -300]]},
                                                      {"level": 12, "path": [[-260, -300]]}],
                "waterfall": {"model": {"modern": HD_FALL, "fallback": FALL}, "height": 6}}],
    "scatter": [{"name": "trees", "seed": 5, "density": 6,
                 "models": [{"model": {"modern": HD_TREE, "fallback": TREE, "kind": "doodad"}, "radius": 3},
                            {"model": "World\\Made\\Up\\Bush.m2", "radius": 2}]}],
}


def make_resolution(folder, specular=True, tree_status="resolved", tree_collision=False):
    """A hand-written resolution: the HD sand (with or without its _s) and the HD tree resolved, the fall not."""
    files = {HD_SAND: b"BLP2" + bytes(60), HD_TREE: b"MD20" + bytes(300), "World\\Modern\\HD_Tree00.skin": b"SKIN"}
    if specular:
        files[HD_SAND[:-4] + "_s.blp"] = b"BLP2" + bytes(61)
    listed = {}
    for path, data in files.items():
        rel = "files/" + path.replace("\\", "/")
        full = os.path.join(folder, *rel.split("/"))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as f:
            f.write(data)
        listed[path] = {"path": path, "file": rel, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    sand_files = [listed[HD_SAND]] + ([listed[HD_SAND[:-4] + "_s.blp"]] if specular else [])
    doc = {"format": "mapforge-assets/1", "assets": [
        {"modern": HD_SAND, "fallback": SAND, "kind": "texture", "status": "resolved", "reason": "",
         "files": sand_files, "specular": specular},
        {"modern": HD_TREE, "fallback": TREE, "kind": "doodad", "status": tree_status,
         "reason": "" if tree_status == "resolved" else "not in the sources", "collision": tree_collision,
         "files": [listed[HD_TREE], listed["World\\Modern\\HD_Tree00.skin"]] if tree_status == "resolved" else []},
        {"modern": HD_FALL, "fallback": FALL, "kind": "doodad", "status": "fallback",
         "reason": "not in the sources", "files": []}]}
    path = os.path.join(folder, "asset_resolution.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f)
    return path


def write_listfile(folder, extra=()):
    """A 3.3.5 listfile stand-in with every plain path and fallback of ASSET_SPEC (and the _s companions)."""
    paths = ["Tileset\\Made\\Up\\Grass.blp", "Tileset\\Made\\Up\\Grass_s.blp", SAND, TREE, FALL,
             "World\\Made\\Up\\Rock.m2", "World\\wmo\\Made\\Up\\Hut.wmo", "World\\Made\\Up\\Bush.m2", *extra]
    path = os.path.join(folder, "listfile.tsv")
    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(f"{p}\tcommon\n" for p in paths))
    return path


def adt_models(path):
    from terrain import validate as tvalidate
    rep = tvalidate.Report()
    info = tvalidate.parse_adt(path, 32, 32, rep)
    return info


class TestOffline(unittest.TestCase):
    def test_everything_falls_back(self):
        result = tbuild.build_from_dict(copy.deepcopy(ASSET_SPEC))
        m = result.manifest
        self.assertEqual(len(m["extra_assets"]), 4)
        self.assertTrue(all(not u["modern_used"] and "offline" in u["reason"] for u in m["extra_assets"]))
        self.assertEqual(m["extra_files"], [])
        self.assertIsNone(m["server_tiles"])
        self.assertFalse(any(name.startswith(("server/", "extra_assets/")) for name in result.files))
        spec = result.context.spec
        self.assertEqual(spec.textures[1].path, SAND)
        self.assertEqual(spec.textures[1].mtxf_flags, 1)  # the fallback keeps the spec's flags
        self.assertTrue(all(not d.modern for d in result.context.doodads))


class TestResolved(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="mapforge-assets-")
        cls.res_path = make_resolution(os.path.join(cls.tmp, "res"))
        cls.listfile = write_listfile(cls.tmp)
        cls.result = tbuild.build_from_dict(copy.deepcopy(ASSET_SPEC), Resolution.load(cls.res_path))
        cls.out = os.path.join(cls.tmp, "out")
        tbuild.write(cls.result, cls.out, force=True, preview=False)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def copy(self):
        dst = tempfile.mkdtemp(prefix="mapforge-assets-copy-")
        shutil.copytree(self.out, dst, dirs_exist_ok=True)
        self.addCleanup(shutil.rmtree, dst, True)
        return dst

    def check(self, out, **kw):
        kw.setdefault("listfiles", [self.listfile])
        kw.setdefault("resolution", self.res_path)
        return validate(out, **kw)

    def test_modern_paths_where_resolved(self):
        spec = self.result.context.spec
        self.assertEqual(spec.textures[1].path, HD_SAND)
        self.assertEqual(spec.textures[1].mtxf_flags, 0)  # its _s.blp ships
        used = {u.where: u.modern_used for u in spec.assets}
        self.assertEqual(used, {"textures[1].path": True, "doodads[0].model": True,
                                "rivers[0].waterfall.model": False, "scatter[0].models[0].model": True})
        modern = [d for d in self.result.context.doodads if d.modern]
        self.assertTrue(any(d.label == "hd tree" for d in modern))
        self.assertTrue(any(d.label.startswith("trees #") for d in modern))
        self.assertFalse(any(d.label.startswith("r fall") for d in modern))

    def test_scatter_layout_does_not_depend_on_the_resolution(self):
        offline = tbuild.build_from_dict(copy.deepcopy(ASSET_SPEC))
        a = [(d.label, d.world, d.uid) for d in offline.context.doodads]
        b = [(d.label, d.world, d.uid) for d in self.result.context.doodads]
        self.assertEqual(a, b)

    def test_extra_files_and_manifest(self):
        m = self.result.manifest
        paths = sorted(e["path"] for e in m["extra_files"])
        self.assertEqual(paths, sorted([HD_SAND, HD_SAND[:-4] + "_s.blp", HD_TREE, "World\\Modern\\HD_Tree00.skin"]))
        for e in m["extra_files"]:
            with open(os.path.join(self.out, *e["file"].split("/")), "rb") as f:
                self.assertEqual(hashlib.sha256(f.read()).hexdigest(), e["sha256"])
        self.assertEqual(m["server_tiles"], "server/World/Maps/AssetT")
        self.assertEqual(m["server_doodads_left_out"], len([d for d in self.result.context.doodads if d.modern]))

    def test_server_copy_leaves_out_modern_doodads(self):
        client = adt_models(os.path.join(map_folder(self.out, "AssetT"), "AssetT_32_32.adt"))
        server = adt_models(os.path.join(self.out, "server", "World", "Maps", "AssetT", "AssetT_32_32.adt"))
        self.assertIn(HD_TREE, client.m2_names)
        self.assertNotIn(HD_TREE, server.m2_names)
        modern = {d.uid for d in self.result.context.doodads if d.modern}
        self.assertEqual({e["uid"] for e in server.mddf}, {e["uid"] for e in client.mddf} - modern)
        self.assertEqual(server.modf, client.modf)
        self.assertEqual(server.textures, client.textures)
        for ext in ("wdt", "wdl"):
            with open(os.path.join(map_folder(self.out, "AssetT"), f"AssetT.{ext}"), "rb") as a, \
                    open(os.path.join(self.out, "server", "World", "Maps", "AssetT", f"AssetT.{ext}"), "rb") as b:
                self.assertEqual(a.read(), b.read())

    def test_validator_accepts(self):
        rep = self.check(self.out)
        self.assertEqual(rep.errors, [])
        extra = rep.summary["extra_assets"]
        self.assertEqual(extra["server_tiles"], 1)
        self.assertGreater(extra["server_doodads_left_out"], 1)
        self.assertEqual(extra["resolution"], {"resolved": 2, "fell_back": 1})

    def test_validator_catches(self):
        cases = {
            "unshipped": "neither a 3.3.5 listfile path nor an extra asset",
            "server_modern": "places the extra asset",
            "no_server": "no server/World/Maps/AssetT",
            "changed": "differs from the resolution's copy",
            "listfile": "neither a 3.3.5 listfile path",
            "fell_back": "fell back in the resolution",
        }
        for case, text in cases.items():
            with self.subTest(case):
                out = self.copy()
                kw = {}
                if case == "unshipped":
                    os.remove(os.path.join(out, "extra_assets", "World", "Modern", "HD_Tree.m2"))
                elif case == "server_modern":
                    shutil.copy(os.path.join(map_folder(out, "AssetT"), "AssetT_32_32.adt"),
                                os.path.join(out, "server", "World", "Maps", "AssetT", "AssetT_32_32.adt"))
                elif case == "no_server":
                    shutil.rmtree(os.path.join(out, "server"))
                elif case == "changed":
                    with open(os.path.join(out, "extra_assets", "Tileset", "Modern", "HD_Sand.blp"), "ab") as f:
                        f.write(b"x")
                elif case == "listfile":
                    short = os.path.join(out, "short.tsv")
                    with open(short, "w", encoding="utf-8") as f:
                        f.write("Tileset\\Made\\Up\\Grass.blp\n")
                    kw["listfiles"] = [short]
                elif case == "fell_back":
                    kw["resolution"] = make_resolution(os.path.join(out, "res2"), tree_status="fallback")
                    shutil.rmtree(os.path.join(out, "extra_assets", "World"))
                rep = self.check(out, **kw)
                self.assertTrue(any(text in e for e in rep.errors), (case, rep.errors[:5]))

    def test_modern_texture_without_specular_gets_mtxf_1(self):
        folder = os.path.join(self.tmp, "nospec")
        res = Resolution.load(make_resolution(folder, specular=False))
        spec = parse_spec(copy.deepcopy(ASSET_SPEC), res)
        self.assertEqual(spec.textures[1].path, HD_SAND)
        self.assertEqual(spec.textures[1].mtxf_flags, 1)

    def test_modern_doodad_with_collision_warns(self):
        folder = os.path.join(self.tmp, "coll")
        res = Resolution.load(make_resolution(folder, tree_collision=True))
        result = tbuild.build_from_dict(copy.deepcopy(ASSET_SPEC), res)
        self.assertTrue(any("collision geometry" in w for w in result.manifest["warnings"]))


class TestListfiles(unittest.TestCase):
    def test_kit_modern_candidates_are_not_335_paths(self):
        from terrain import extra_assets
        from terrain import validate as tvalidate
        kit = {"tilesets": {"sand": [{"path": SAND, "specular": SAND[:-4] + "_s.blp"}]},
               "doodads": {"trees": [{"path": TREE}]},
               "modern_candidates": {"doodads": [{"path": HD_TREE, "fallback": TREE}]}}
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        path = os.path.join(tmp, "kit.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(kit, f)
        want = {SAND.lower(), SAND[:-4].lower() + "_s.blp", TREE.lower()}
        self.assertEqual(extra_assets.load_listfile(path), want)
        self.assertEqual(tvalidate.load_listfile(path), want)
        tsv = os.path.join(tmp, "list.tsv")
        with open(tsv, "w", encoding="utf-8") as f:
            f.write(f"{SAND}\tcommon\n{TREE}\n")
        self.assertEqual(tvalidate.load_listfile(tsv), {SAND.lower(), TREE.lower()})
        self.assertEqual(extra_assets.load_listfile(tsv), {SAND.lower(), TREE.lower()})


class TestAssetSpecErrors(unittest.TestCase):
    def bad(self, mutate, text):
        data = copy.deepcopy(ASSET_SPEC)
        mutate(data)
        with self.assertRaisesRegex(SpecError, text):
            parse_spec(data)

    def test_rejects(self):
        self.bad(lambda d: d["textures"][1]["path"].update(kind="doodad"), "takes a texture")
        self.bad(lambda d: d["doodads"][0]["model"].update(kind="texture"), "takes a doodad")
        self.bad(lambda d: d["doodads"][0]["model"].update(kind="wmo"), "'texture' or 'doodad'")
        self.bad(lambda d: d["doodads"][0]["model"].update(fallback=HD_TREE), "the same path")
        self.bad(lambda d: d["doodads"][0]["model"].update(extra=1), "unknown keys")
        wmo = {"modern": "World\\wmo\\M\\X.wmo", "fallback": "World\\wmo\\Made\\Up\\Hut.wmo"}
        self.bad(lambda d: d["wmos"][0].update(model=wmo), "3.3.5 files only")
        self.bad(lambda d: d["textures"][1]["path"].update(modern="Tileset\\Modern\\HD.png"), "must end with")


if __name__ == "__main__":
    unittest.main(verbosity=2)
