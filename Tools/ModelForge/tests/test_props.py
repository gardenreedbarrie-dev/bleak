"""The built models: budgets, sizes, readability, collision, particles, golden hashes, cross-checks (section 5.9)."""

import hashlib
import json
import os
import struct
import unittest

import common as CM
from mflib import build as B
from mflib import geom as G
from mflib import m2check as C
from mflib import sizes as SZ

GOLDEN = os.path.join(CM.HERE, "golden.json")
WALKABLE_NZ = 0.64278764   # cos 50 degrees: Movement.cpp:471 (a facet with n.z above this is walkable)
MODELS = ["Cube", "EspressoSW"]


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


class Built(unittest.TestCase):
    def test_round_trip_and_check(self):
        for name in MODELS:
            res = CM.built(name)
            m, f, s = res.check
            self.assertTrue(s["ok"], (name, f.items))
            self.assertEqual(s["counts"]["triangles"], sum(p.mesh.triangles for p in res.defn.parts))
            self.assertEqual(s["crosscheck"]["problems"], [], name)
            self.assertTrue(s["crosscheck"]["available"])

    def test_tracks_loop_and_outer_count(self):
        for name in MODELS:
            data = CM.read(CM.built(name).m2)
            tr = tracks_of(data)
            self.assertTrue(tr)
            for where, loop, outer, nseq in tr:
                self.assertEqual(loop, 0xFFFF, "%s %s" % (name, where))
                self.assertLessEqual(outer, nseq, "%s %s" % (name, where))

    def test_empty_sequence_hash_and_one_profile(self):
        for name in MODELS:
            m = CM.built(name).check[0]
            self.assertEqual(m["counts"]["sequenceIdxHashById"], 0)
            self.assertEqual(m["numSkinProfiles"], 1)
            self.assertEqual(len(m["sequences"]), 1)
            self.assertEqual(m["sequences"][0]["flags"], 0x20)

    def test_particles(self):
        for name in MODELS:
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
        for name in MODELS:
            res = CM.built(name)
            m = res.check[0]
            col = m["collision"]
            self.assertEqual(len(col["indices"]), 3 * len(col["normals"]))
            self.assertLessEqual(len(col["normals"]), res.defn.collision_max)
            # a closed hull: positive volume
            mesh = G.Mesh()
            mesh.p = list(col["positions"])
            mesh.t = [tuple(col["indices"][k:k + 3]) for k in range(0, len(col["indices"]), 3)]
            self.assertGreater(G.signed_volume(mesh), 0, name)
            if res.defn.sloped_top:
                for k, n in enumerate(col["normals"]):
                    c = [sum(col["positions"][col["indices"][3 * k + j]][i] for j in range(3)) / 3 for i in range(3)]
                    if c[2] > 0.1:
                        self.assertLessEqual(n[2], WALKABLE_NZ, "%s: walkable collision face %d on top" % (name, k))


class ScaledBuild(unittest.TestCase):
    def test_tex_scale_no_particles_no_bake(self):
        """The CI path for the other props (section 5.5): textures at 64 px, no particles, no bake, one job."""
        import os as _os
        from mflib import props as PR
        out = _os.path.join(CM.workdir(), "scaled")
        res = B.build_prop(PR.REGISTRY["EspressoSW"].build({}), out, 0.125, False, False, 1, False,
                           lambda *_a: None)
        m, f, s = res.check
        self.assertTrue(s["ok"], f.items)
        self.assertEqual(s["counts"]["particles"], 0)
        self.assertNotIn("World\\Bleakhold\\Cafe\\Shared\\BH_Cafe_Steam.blp", [c for c, _d in res.textures])


class Budgets(unittest.TestCase):
    def test_triangles_and_textures(self):
        for name in MODELS:
            res = CM.built(name)
            tris = res.check[2]["counts"]["triangles"]
            self.assertLessEqual(tris, res.defn.budget, name)
        cat = SZ.catalogue()
        self.assertEqual(CM.built("EspressoSW").defn.budget, cat["EspressoSW"]["budget"])

    def test_sizes(self):
        """Every built café model's collision footprint matches its size (cafe.json when present, else the
        section 5.8 table) within 2 cm; the render depth includes the portafilter handles."""
        res = CM.built("EspressoSW")
        want, source = SZ.expected_size("EspressoSW", 19300)
        coll, rend = SZ.footprint(res.defn)
        for k in range(3):
            self.assertLessEqual(abs(coll[k] - want[k]), SZ.TOLERANCE, "collision %r vs %r (%s)" % (coll, want,
                                                                                                   source))
        self.assertLessEqual(abs(rend[0] - want[0]), SZ.TOLERANCE)
        self.assertLessEqual(abs(rend[1] - res.defn.depth_with_handles), SZ.TOLERANCE, rend)
        self.assertLessEqual(abs(rend[2] - want[2]), SZ.TOLERANCE, rend)
        self.assertLessEqual(rend[2], res.defn.max_height, "machine height above its base")

    def test_readability(self):
        """Every named visible part is at least 0.06 yd across, and none is a hairline thinner than 0.03 yd in
        two directions (section 5.8: about 6 px, and 3 px, at 10 yd)."""
        for name in MODELS:
            for part in CM.built(name).defn.parts:
                if not part.visible:
                    continue
                (x0, y0, z0), (x1, y1, z1) = part.mesh.bounds()
                dims = sorted((x1 - x0, y1 - y0, z1 - z0))
                self.assertGreaterEqual(dims[2], 0.06, "%s.%s" % (name, part.name))
                # a plate may be thin in depth, but no visible part is a hairline in two directions
                self.assertGreaterEqual(dims[1], 0.03, "%s.%s %r" % (name, part.name, dims))


class Golden(unittest.TestCase):
    def test_golden_hashes(self):
        """Byte-identical output: a golden sha256 for the unit cube and EspressoSW (run_tests.py --update-golden
        rewrites tests/golden.json after an intended change)."""
        got = {}
        for name in MODELS:
            res = CM.built(name)
            for client, disk in res.files:
                got[client] = sha(disk)
        if os.environ.get("MODELFORGE_UPDATE_GOLDEN") == "1":
            with open(GOLDEN, "w") as f:
                json.dump(got, f, indent=1, sort_keys=True)
                f.write("\n")
        with open(GOLDEN) as f:
            want = json.load(f)
        diff = sorted(k for k in set(got) | set(want) if got.get(k) != want.get(k))
        self.assertEqual(diff, [], "changed outputs (run tests/run_tests.py --update-golden if intended)")


class Manifest(unittest.TestCase):
    def test_manifest_shape(self):
        res = CM.built("EspressoSW")
        e = res.manifest
        for k in ("name", "display", "m2", "skin", "textures", "bounds", "size", "parts", "triangles",
                  "collisionTriangles", "particles", "customAnims", "modelFrame"):
            self.assertIn(k, e)
        self.assertEqual(e["display"], 19300)
        self.assertEqual(e["m2"], "World\\Bleakhold\\Cafe\\EspressoSW\\BH_Cafe_EspressoSW.m2")
        self.assertEqual(e["skin"], "World\\Bleakhold\\Cafe\\EspressoSW\\BH_Cafe_EspressoSW00.skin")
        self.assertIn("World\\Bleakhold\\Cafe\\Shared\\BH_Cafe_ChromeEnv.blp", e["textures"])
        self.assertEqual(sum(e["parts"].values()), e["triangles"])
        path = B.write_manifest(CM.workdir(), [e], res.files)
        with open(path) as f:
            man = json.load(f)
        self.assertEqual(man["tool"], "ModelForge")
        self.assertEqual(len(man["files"]), len(res.files))


@unittest.skipUnless(CM.native_harness(), "g++ not available")
class Native(unittest.TestCase):
    def test_built_models_pass_the_client_m2init(self):
        rc, out = CM.run_harness(*[CM.built(n).m2 for n in MODELS])
        self.assertEqual(rc, 0, out)
        self.assertEqual(out.count("OK "), len(MODELS), out)


if __name__ == "__main__":
    unittest.main()
