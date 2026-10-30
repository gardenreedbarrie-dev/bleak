"""The built models: registry, budgets, sizes, readability, collision, particles, decals, golden hashes,
cross-checks (section 5.9). Every registered model is covered; MF_MODELS limits the run to some of them."""

import hashlib
import json
import os
import pkgutil
import struct
import unittest

import common as CM
from mflib import atlas as A
from mflib import build as B
from mflib import geom as G
from mflib import m2check as C
from mflib import props as PR
from mflib import sizes as SZ

GOLDEN = os.path.join(CM.HERE, "golden.json")
WALKABLE_NZ = 0.64278764   # cos 50 degrees: Movement.cpp:471 (a facet with n.z above this is walkable)
MODELS = CM.tested_models()


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def tracks_of(data):
    """(where, loopIndex, outer count) of every track of every array, from the checker's tables."""
    out = []
    nseq = struct.unpack_from("<I", data, 0x1C)[0]
    for name, off, elem in C.ARRAYS:
        n, o = struct.unpack_from("<II", data, off)
        for t_off, _vs, _kind in C.TRACKS.get(name, []):
            for i in range(n):
                base = o + elem * i + t_off
                loop = struct.unpack_from("<H", data, base + 2)[0]
                outer = struct.unpack_from("<I", data, base + 4)[0]
                out.append(("%s[%d]+0x%X" % (name, i, t_off), loop, outer, nseq))
    return out


def own_slots(defn):
    slots = []
    for part in defn.parts:
        if part.texture not in slots and part.texture not in B.SHARED:
            slots.append(part.texture)
    return slots


def decal_regions(defn):
    """[(part name, decal key, fn, w, h)]: every decal at the size of its chart in the full-size atlas."""
    out = []
    for slot in own_slots(defn):
        size = B.tex_dims(defn.atlas.get(slot, 512))
        charts, owners = [], []
        for pi, part in enumerate(defn.parts):
            if part.texture == slot:
                for ci, ch in enumerate(part.mesh.charts):
                    charts.append(ch)
                    owners.append((pi, ci))
        pl, _d = A.pack(charts, size)
        place = dict(zip(owners, pl))
        for pi, part in enumerate(defn.parts):
            if part.texture != slot:
                continue
            for key, fn in part.decals.items():
                ci = key if isinstance(key, int) else B.chart_index(part, key)
                p = place[(pi, ci)]
                out.append((part.name, key, fn, max(1, int(round(p.w))), max(1, int(round(p.h)))))
    return out


class Registry(unittest.TestCase):
    def test_selected_models_are_registered(self):
        """Every model named in MF_MODELS has a module that loads and registers it."""
        self.assertEqual(CM.selection_problems(), [])

    def test_no_broken_modules(self):
        """No module of mflib/props fails to import (with MF_MODELS: none of the selected models' modules)."""
        broken = PR.broken_for(CM.selected_models()) if CM.limited() else PR.BROKEN
        self.assertEqual(sorted(broken), [], "\n".join("%s.py:\n%s" % kv for kv in sorted(broken.items())))

    def test_discovery(self):
        """Every props module that defines NAME and build is registered under NAME, in the deterministic order:
        test models first, then the section 5.8 order."""
        names = []
        for info in pkgutil.iter_modules(PR.__path__):
            if info.name.startswith("_") or info.name in PR.BROKEN:
                continue
            mod = __import__("mflib.props." + info.name, fromlist=["x"])
            if isinstance(getattr(mod, "NAME", None), str) and callable(getattr(mod, "build", None)):
                names.append(mod.NAME)
                self.assertIs(PR.REGISTRY[mod.NAME], mod)
        self.assertEqual(sorted(names), sorted(PR.REGISTRY))
        order = list(PR.REGISTRY)
        rank = {n: k for k, n in enumerate(PR.CATALOGUE_NAMES)}
        self.assertEqual(order, sorted(order, key=lambda n: (n in rank, rank.get(n, 0), n)))
        self.assertEqual(order[:2], ["Cube", "EspressoSW"])

    def test_module_conventions(self):
        """Module file = snake-case NAME; a café model is a CATALOGUE row with its display and budget; build()
        returns a PropDef with that name, display and budget and a known kind."""
        cat = SZ.catalogue()
        for name in MODELS:
            with self.subTest(model=name):
                mod = PR.REGISTRY[name]
                self.assertEqual(mod.__name__.split(".")[-1], PR.module_name(name))
                defn = mod.build({})
                self.assertEqual(defn.name, name)
                self.assertIn(defn.kind, SZ.KINDS)
                if name in cat:
                    self.assertEqual(getattr(mod, "DISPLAY", None), cat[name]["display"])
                    self.assertEqual(defn.display, cat[name]["display"])
                    self.assertEqual(defn.budget, cat[name]["budget"])
                else:
                    self.assertIsNone(getattr(mod, "DISPLAY", None), "%s is not in CATALOGUE: a test model" % name)
                    self.assertEqual(defn.kind, "test")


class Built(unittest.TestCase):
    def test_round_trip_and_check(self):
        for name in MODELS:
            with self.subTest(model=name):
                res = CM.built(name)
                m, f, s = res.check
                self.assertTrue(s["ok"], (name, f.items))
                self.assertEqual(s["counts"]["triangles"], sum(p.mesh.triangles for p in res.defn.parts))
                self.assertEqual(s["crosscheck"]["problems"], [], name)
                self.assertTrue(s["crosscheck"]["available"])

    def test_tracks_loop_and_outer_count(self):
        for name in MODELS:
            with self.subTest(model=name):
                data = CM.read(CM.built(name).m2)
                tr = tracks_of(data)
                self.assertTrue(tr)
                for where, loop, outer, nseq in tr:
                    self.assertEqual(loop, 0xFFFF, "%s %s" % (name, where))
                    self.assertLessEqual(outer, nseq, "%s %s" % (name, where))

    def test_empty_sequence_hash_and_one_profile(self):
        for name in MODELS:
            with self.subTest(model=name):
                m = CM.built(name).check[0]
                self.assertEqual(m["counts"]["sequenceIdxHashById"], 0)
                self.assertEqual(m["numSkinProfiles"], 1)
                self.assertEqual(len(m["sequences"]), 1)
                self.assertEqual(m["sequences"][0]["flags"], 0x20)

    def test_particles(self):
        for name in MODELS:
            with self.subTest(model=name):
                m = CM.built(name).check[0]
                self.assertLessEqual(len(m["particles"]), 2, "budget: at most two emitters")
                for p in m["particles"]:
                    self.assertTrue(p["flags"] & 0x60000)
                    self.assertFalse(p["flags"] & 0x40000)
                    self.assertEqual(p["twinkle"], (10.0, 1.0, 1.0, 1.0))
                    self.assertIn(p["emitterType"], (1, 2, 3))
                    self.assertIsNotNone(p["tracks"]["emissionRate"])
                    lo, hi = C.plume_box(p)
                    b = m["bounds"]
                    for k in range(3):
                        self.assertGreaterEqual(lo[k], b["min"][k] - 1e-4)
                        self.assertLessEqual(hi[k], b["max"][k] + 1e-4)

    def test_collision(self):
        """Section 5.2.6: the 3:1 ratio, the kind's budget, a closed hull where the kind needs one (none for
        walk-through table props), and no walkable facet on top of a sloped-top piece."""
        for name in MODELS:
            with self.subTest(model=name):
                res = CM.built(name)
                kind = SZ.kind(res.defn)
                col = res.check[0]["collision"]
                self.assertEqual(len(col["indices"]), 3 * len(col["normals"]))
                self.assertLessEqual(len(col["normals"]), min(res.defn.collision_max, kind["collision_max"]))
                if kind["hull"]:
                    self.assertTrue(col["normals"], "kind %s needs a collision hull" % res.defn.kind)
                if not col["normals"]:
                    continue
                mesh = G.Mesh()
                mesh.p = list(col["positions"])
                mesh.t = [tuple(col["indices"][k:k + 3]) for k in range(0, len(col["indices"]), 3)]
                self.assertGreater(G.signed_volume(mesh), 0, "the hull is closed and wound outward")
                if res.defn.sloped_top:
                    for k, n in enumerate(col["normals"]):
                        c = [sum(col["positions"][col["indices"][3 * k + j]][i] for j in range(3)) / 3
                             for i in range(3)]
                        if c[2] > 0.1:
                            self.assertLessEqual(n[2], WALKABLE_NZ, "walkable collision face %d on top" % k)


class ScaledBuild(unittest.TestCase):
    def test_tex_scale_no_particles_no_bake(self):
        """The fast path (section 5.5): textures at 64 px, --no-particles, --no-bake, one job: still valid, no
        emitters, and the textures only the emitters used are gone."""
        for name in MODELS:
            with self.subTest(model=name):
                defn = PR.REGISTRY[name].build({})
                if not defn.particles:
                    continue
                out = os.path.join(CM.workdir(), "scaled")
                res = B.build_prop(defn, out, 0.125, False, False, 1, False, lambda *_a: None)
                m, f, s = res.check
                self.assertTrue(s["ok"], f.items)
                self.assertEqual(s["counts"]["particles"], 0)
                only = {pd.texture for pd in defn.particles} - {p.texture for p in defn.parts}
                for t in only:
                    self.assertNotIn(B.shared_path(t), [c for c, _d in res.textures])


class Budgets(unittest.TestCase):
    def test_triangles(self):
        cat = SZ.catalogue()
        for name in MODELS:
            with self.subTest(model=name):
                res = CM.built(name)
                tris = res.check[2]["counts"]["triangles"]
                self.assertLessEqual(tris, res.defn.budget, name)
                if name in cat:
                    self.assertLessEqual(tris, cat[name]["budget"], "section 5.8 budget")

    def test_sizes(self):
        """Every model's size, render extents and collision hull match cafe.json `size` (else section 5.8)
        within 2 cm (sizes.size_problems), and no model rises above its kind's height limit."""
        for name in MODELS:
            with self.subTest(model=name):
                self.assertEqual(SZ.size_problems(CM.built(name).defn), [])

    def test_readability(self):
        """Every named visible part is at least 0.06 yd across, and none is a hairline thinner than 0.03 yd in
        two directions (section 5.8: about 6 px, and 3 px, at 10 yd)."""
        for name in MODELS:
            with self.subTest(model=name):
                for part in CM.built(name).defn.parts:
                    if not part.visible:
                        continue
                    (x0, y0, z0), (x1, y1, z1) = part.mesh.bounds()
                    dims = sorted((x1 - x0, y1 - y0, z1 - z0))
                    self.assertGreaterEqual(dims[2], 0.06, "%s.%s" % (name, part.name))
                    # a plate may be thin in depth, but no visible part is a hairline in two directions
                    self.assertGreaterEqual(dims[1], 0.03, "%s.%s %r" % (name, part.name, dims))


class Decals(unittest.TestCase):
    def test_decals_render_at_full_size(self):
        """Every decal renders into its full-size atlas region without raising: a text that does not fit its
        region fails here (section 5.5.1), even though the CI build paints the atlas at 64 px. The cube and
        EspressoSW are built at full size, so their build already did this."""
        for name in MODELS:
            if name in CM.FULL:
                continue
            with self.subTest(model=name):
                defn = PR.REGISTRY[name].build({})
                for pname, key, fn, w, h in decal_regions(defn):
                    img = fn(w, h)
                    self.assertEqual((img.w, img.h), (w, h), "%s decal %r" % (pname, key))


class Textures(unittest.TestCase):
    def test_every_built_texture_is_valid(self):
        import blpconvert as BC
        for name in MODELS:
            with self.subTest(model=name):
                res = CM.built(name)
                for client, disk in res.textures:
                    h, levels, problems = BC.check_blp(disk)
                    self.assertEqual(problems, [], client)
                    self.assertTrue(BC.is_pow2(h["width"]) and BC.is_pow2(h["height"]), client)
                    self.assertNotEqual(h["width"], 6 * h["height"], client)
                    fmt = "dxt5" if h["preferredFormat"] == 7 else "dxt1"
                    if "Steam" in client or "Fire" in client:
                        self.assertEqual(fmt, "dxt5", client)


class Golden(unittest.TestCase):
    def test_golden_hashes(self):
        """Byte-identical output: every file of tests/golden.json that the tested models write keeps its sha256
        (the cube and EspressoSW since M1; the other models from the integration step on). A model with no
        golden entries yet passes; `run_tests.py --update-golden` records them (it keeps the entries of models
        not tested in this run)."""
        got = {}
        for name in MODELS:
            res = CM.built(name)
            for client, disk in res.files:
                got[client] = sha(disk)
        with open(GOLDEN) as f:
            want = json.load(f)
        dirs = tuple(B.client_dir(n) + "\\" for n in MODELS)
        if os.environ.get("MODELFORGE_UPDATE_GOLDEN") == "1":
            new = {k: v for k, v in want.items() if not k.startswith(dirs)}
            new.update(got)
            with open(GOLDEN, "w") as f:
                json.dump(new, f, indent=1, sort_keys=True)
                f.write("\n")
            want = new
        changed = sorted(k for k in want if k in got and got[k] != want[k])
        missing = sorted(k for k in want if k not in got and k.startswith(dirs))
        self.assertEqual(changed + missing, [],
                         "changed or missing outputs (run tests/run_tests.py --update-golden only if intended)")


class Manifest(unittest.TestCase):
    def test_manifest_shape(self):
        cat = SZ.catalogue()
        entries, files = [], []
        for name in MODELS:
            with self.subTest(model=name):
                res = CM.built(name)
                e = res.manifest
                for k in ("name", "display", "m2", "skin", "textures", "bounds", "size", "parts", "triangles",
                          "collisionTriangles", "particles", "customAnims", "modelFrame"):
                    self.assertIn(k, e)
                self.assertEqual(e["display"], cat[name]["display"] if name in cat else None)
                self.assertEqual(e["m2"], B.client_dir(name) + "\\BH_Cafe_%s.m2" % name)
                self.assertEqual(e["skin"], B.client_dir(name) + "\\BH_Cafe_%s00.skin" % name)
                self.assertEqual(sum(e["parts"].values()), e["triangles"])
                entries.append(e)
                files += res.files
        if "EspressoSW" in MODELS:
            e = CM.built("EspressoSW").manifest
            self.assertEqual(e["m2"], "World\\Bleakhold\\Cafe\\EspressoSW\\BH_Cafe_EspressoSW.m2")
            self.assertIn("World\\Bleakhold\\Cafe\\Shared\\BH_Cafe_ChromeEnv.blp", e["textures"])
        if entries:
            path = B.write_manifest(CM.workdir(), entries, files)
            with open(path) as f:
                man = json.load(f)
            self.assertEqual(man["tool"], "ModelForge")
            self.assertEqual(len(man["files"]), len({c for c, _d in files}))
            self.assertEqual(C.check_unique_names([(CM.built(n).m2, CM.built(n).check[0].get("name"))
                                                   for n in MODELS]), [])


@unittest.skipUnless(CM.native_harness(), "g++ not available")
class Native(unittest.TestCase):
    def test_built_models_pass_the_client_m2init(self):
        if not MODELS:
            self.skipTest("no models selected")
        rc, out = CM.run_harness(*[CM.built(n).m2 for n in MODELS])
        self.assertEqual(rc, 0, out)
        self.assertEqual(out.count("OK "), len(MODELS), out)



class TestPatch(unittest.TestCase):
    def test_testpatch_packs_any_set_of_built_models(self):
        """`modelforge.py testpatch --from DIR --only ...` packs models already built (no rebuild); the default is
        every registered model."""
        import contextlib
        import io
        import modelforge as MF
        names = [n for n in MODELS if n in ("Cube", "CupSW", "TipJar")] or MODELS[:1]
        if not names:
            self.skipTest("no models selected")
        for n in names:
            CM.built(n)
        out = os.path.join(CM.workdir(), "testpatch")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            MF.main(["testpatch", "--from", CM.workdir(), "--only", ",".join(names), "--out", out])
        self.assertTrue(os.path.getsize(os.path.join(out, "patch-4.MPQ")) > 0)
        self.assertIn("%d models (%s)" % (len(names), ", ".join(names)), buf.getvalue())
        if not PR.BROKEN:
            self.assertEqual(MF._names(MF.argparse.Namespace(only=None)), list(PR.REGISTRY))

if __name__ == "__main__":
    unittest.main()
