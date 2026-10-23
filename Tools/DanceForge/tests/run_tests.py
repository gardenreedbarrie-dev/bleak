#!/usr/bin/env python3
"""DanceForge tests: python3 -I Tools/DanceForge/tests/run_tests.py (exit code 0 = all passed).

The C++ half (Engine/Source/Model2/BleakDance.cpp, built here with g++ together with dance_core_test.cpp) is checked
against the Python reference (dflib/retarget.py) on made-up skeletons (synth.py): the same rig, and the same local
transform for every bone of every frame. No game data is used.
"""

import math
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.dirname(HERE)
REPO = os.path.normpath(os.path.join(TOOL, "..", ".."))
sys.dont_write_bytecode = True
for p in (TOOL, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

from dflib import catalogue as C  # noqa: E402
from dflib import choreo  # noqa: E402
from dflib import pack as P  # noqa: E402
from dflib import quat as Q  # noqa: E402
from dflib import retarget as RT  # noqa: E402
from dflib import rig  # noqa: E402
from dflib import skeleton as S  # noqa: E402
import synth  # noqa: E402

# Every released dance key, in id order. A key is never changed or removed (saved wheels hold dance:<key>, music
# files carry the key's name and ids go on the wire); new dances are appended here when they are added.
FROZEN_KEYS = [
    "string_swing", "running_man", "disco_fever", "twist_it", "raise_the_roof", "mech_bot",
]

KIND = {RT.MAP: 1, RT.SPINE: 2, RT.NECK: 3, RT.RIGID: 4, RT.PELVIS: 5, RT.ROOT: 6, RT.STILL: 7}
_BUILD = {}


def core_binary():
    """Path of the built dance_core_test, or None without a C++ compiler."""
    if "bin" in _BUILD:
        return _BUILD["bin"]
    cxx = os.environ.get("CXX") or shutil.which("g++") or shutil.which("clang++")
    if not cxx:
        _BUILD["bin"] = None
        return None
    out_dir = tempfile.mkdtemp(prefix="dance_core_")
    out = os.path.join(out_dir, "dance_core_test")
    cmd = [cxx, "-std=c++17", "-O1", "-Wall", "-Wextra", "-Werror", "-I", REPO,
           os.path.join(HERE, "dance_core_test.cpp"), os.path.join(REPO, "Engine", "Source", "Model2", "BleakDance.cpp"),
           "-o", out]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("building dance_core_test failed:\n" + r.stdout + r.stderr)
    _BUILD["bin"] = out
    return out


def sample_frames():
    """A few poses that move every joint."""
    d = choreo.Dance(bpm=120, beats=2)
    d.key(0, hand_l=(0.3, 0.3, 0.3), spine_twist=20, hips=(0.05, 0.03, -0.1), foot_r=(0.2, -0.15, 0.2),
          ik_r=0.0, arm_r=(40.0, 30.0, 60.0, 20.0))
    d.key(1, hand_r=(0.2, -0.1, 0.5), head_turn=-30, spine_bend=15, hips_yaw=25, foot_l=(-0.1, 0.2, 0.12),
          ik_r=1.0)
    return d.sample(4)


def qdist(a, b):
    return min(math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b))), math.sqrt(sum((x + y) ** 2 for x, y in zip(a, b))))


def run_core(*args):
    r = subprocess.run([core_binary()] + list(args), capture_output=True, text=True)
    return r.returncode, r.stdout.splitlines()


class TestRigMaths(unittest.TestCase):
    def test_rest_pose_is_identity(self):
        hips, rots = rig.solve({"hips": (0, 0, 0), "hand_l": (0, 0.895, 0.2), "hand_r": (0, -0.895, 0.2),
                                "foot_l": S.REST[S.INDEX["FootL"]], "foot_r": S.REST[S.INDEX["FootR"]],
                                "foot_yaw_l": 0.0, "foot_yaw_r": 0.0, "knee_l": (1, 0, 0), "knee_r": (1, 0, 0)})
        for j in ("Hips", "Spine", "Chest", "Head", "FootL", "ToeR"):
            self.assertLess(Q.qangle(rots[S.INDEX[j]], Q.IDENTITY), 1e-6, j)

    def test_feet_reach_their_targets(self):
        for target in ((0.1, 0.15, 0.105), (-0.2, 0.25, 0.2), (0.3, 0.1, 0.4)):
            hips, rots = rig.solve({"foot_l": target, "hips": (0.0, 0.0, -0.1)})
            pos = S.positions(hips, rots)
            self.assertLess(Q.length(Q.sub(pos[S.INDEX["FootL"]], target)), 1e-6, target)

    def test_hands_reach_their_targets(self):
        hips, rots = rig.solve({"hand_r": (0.35, -0.2, 0.1)})
        pos = S.positions(hips, rots)
        chest = pos[S.INDEX["Chest"]]
        self.assertLess(Q.length(Q.sub(pos[S.INDEX["HandR"]], Q.add(chest, (0.35, -0.2, 0.1)))), 1e-6)

    def test_out_of_reach_limbs_stay_bent_a_little(self):
        hips, rots = rig.solve({"foot_l": (0.0, 0.115, -1.0)})
        pos = S.positions(hips, rots)
        reach = Q.length(Q.sub(pos[S.INDEX["FootL"]], pos[S.INDEX["ThighL"]]))
        self.assertLess(reach, S.THIGH + S.CALF)
        self.assertGreater(reach, (S.THIGH + S.CALF) * 0.98)

    def test_mirror_is_symmetric(self):
        pose = {"hand_l": (0.3, 0.4, 0.2), "hips": (0.02, 0.05, -0.08), "hips_yaw": 20.0, "spine_side": 10.0,
                "foot_r": (0.1, -0.2, 0.15), "ik_l": 0.0, "arm_l": (30.0, 20.0, 40.0, 10.0)}
        mirrored = dict(rig.mirror_control(k, v) for k, v in pose.items())
        h1, r1 = rig.solve(pose)
        h2, r2 = rig.solve(mirrored)
        p1, p2 = S.positions(h1, r1), S.positions(h2, r2)
        for name in S.JOINTS:
            a = p1[S.INDEX[name]]
            b = p2[S.INDEX[S.mirror_name(name)]]
            self.assertLess(Q.length(Q.sub(a, (b[0], -b[1], b[2]))), 1e-6, name)

    def test_fk_arm_points_where_asked(self):
        for swing, raise_, expect in ((0, 0, (0, 1, 0)), (90, 0, (1, 0, 0)), (0, 90, (0, 0, 1)), (-90, 0, (-1, 0, 0))):
            hips, rots = rig.solve({"ik_l": 0.0, "arm_l": (swing, raise_, 0.0, 0.0)})
            pos = S.positions(hips, rots)
            d = Q.normalize(Q.sub(pos[S.INDEX["ForearmL"]], pos[S.INDEX["UpperArmL"]]))
            self.assertLess(Q.length(Q.sub(d, expect)), 1e-6, (swing, raise_))


class TestChoreo(unittest.TestCase):
    def test_keys_are_hit_exactly(self):
        d = choreo.Dance(bpm=120, beats=4)
        d.key(0, ease="inout", spine_bend=0.0)
        d.key(1, ease="snap", spine_bend=20.0)
        d.key(2, ease="pop", spine_bend=-10.0)
        d.key(3, ease="smooth", spine_bend=5.0)
        for beat, v in ((0, 0.0), (1, 20.0), (2, -10.0), (3, 5.0)):
            self.assertAlmostEqual(d.controls_at(beat)["spine_bend"], v, places=9)

    def test_channels_loop(self):
        d = choreo.Dance(bpm=100, beats=2)
        d.key(0.5, ease="linear", head_turn=10.0)
        d.key(1.5, ease="linear", head_turn=30.0)
        self.assertAlmostEqual(d.controls_at(1.0)["head_turn"], 20.0)
        self.assertAlmostEqual(d.controls_at(0.0)["head_turn"], 20.0)     # back from 30 at 1.5 to 10 at 2.5
        self.assertAlmostEqual(d.controls_at(1.9)["head_turn"], 30.0 - 20.0 * 0.4)

    def test_hold_and_lift(self):
        d = choreo.Dance(bpm=120, beats=2)
        d.key(0, foot_l=(0.0, 0.13, 0.105))
        d.key(1, ease="linear", lift=0.2, foot_l=(0.2, 0.13, 0.105))
        mid = d.controls_at(0.5)["foot_l"]
        self.assertAlmostEqual(mid[2], 0.305, places=6)
        h = choreo.Dance(bpm=120, beats=2)
        h.key(0, head_nod=0.0)
        h.key(1, ease="hold", head_nod=10.0)
        self.assertEqual(h.controls_at(0.99)["head_nod"], 0.0)

    def test_bad_input_is_refused(self):
        d = choreo.Dance(bpm=120, beats=2)
        self.assertRaises(ValueError, d.key, 0, nope=1.0)
        self.assertRaises(ValueError, d.key, 2.0, head_nod=1.0)
        self.assertRaises(ValueError, d.key, 0, ease="wobble", head_nod=1.0)
        self.assertRaises(ValueError, d.key, 0, hand_l=(1.0, 2.0))

    def test_follow_lags(self):
        d = choreo.Dance(bpm=120, beats=4)
        d.key(0, ease="snap", spine_side=0.0)
        d.key(2, ease="snap", spine_side=20.0)
        d.follow("head_tilt", "spine_side", gain=1.0)
        frames = d.sample(30)
        self.assertEqual(len(frames), 60)


class TestPack(unittest.TestCase):
    def test_round_trip(self):
        d = choreo.Dance(bpm=120, beats=2)
        d.key(0, spine_twist=30.0)
        d.key(1, spine_twist=-30.0, hips=(0.1, -0.1, -0.2))
        frames = d.sample(30)
        data = P.write([(3, "test_clip", 30, 120.0, frames, True)])
        clips = P.read(data)
        self.assertEqual(len(clips), 1)
        c = clips[0]
        self.assertEqual((c["id"], c["key"], c["fps"], len(c["frames"])), (3, "test_clip", 30, len(frames)))
        for (h0, r0), (h1, r1) in zip(frames, c["frames"]):
            self.assertLess(Q.length(Q.sub(h0, h1)), 1.0 / 8192)
            for a, b in zip(r0, r1):
                self.assertLess(qdist(a, b), 1e-4)

    def test_bad_clips_are_refused(self):
        frames = [((0, 0, 1), [Q.IDENTITY] * S.COUNT)] * 2
        self.assertRaises(ValueError, P.write, [(1024, "a", 30, 120, frames, True)])
        self.assertRaises(ValueError, P.write, [(1, "Bad Key", 30, 120, frames, True)])
        self.assertRaises(ValueError, P.write, [(1, "a", 30, 120, frames[:1], True)])
        self.assertRaises(ValueError, P.write, [(1, "a", 30, 120, frames, True), (1, "b", 30, 120, frames, True)])

    def test_core_samples_like_python(self):
        if not core_binary():
            self.skipTest("no C++ compiler")
        self.assertEqual(run_core("--selftest")[0], 0)
        d = choreo.Dance(bpm=97, beats=3)
        d.key(0, hand_l=(0.3, 0.3, 0.3), spine_twist=40)
        d.key(1.5, ease="snap", hand_r=(0.2, -0.1, 0.5), head_turn=-30, hips_yaw=60)
        frames = d.sample(30)
        data = P.write([(9, "core_check", 30, 97.0, frames, True)])
        clip = P.read(data)[0]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "p.bdc")
            with open(path, "wb") as f:
                f.write(data)
            n = len(frames)
            length = n * 1000 // 30
            times = [0, 17, 250, length // 2, length - 1, length, length + 120, 3 * length + 77]
            rc, out = run_core("--pack", path, "9", *map(str, times))
        self.assertTrue(out[0].startswith("clip core_check %d 30 9700 %d" % (n, length)), out[0])
        for line, t in zip(out[1:], times):
            v = [float(x) for x in line.split()[2:]]
            whole, frac = divmod(t * 30, 1000)
            f0, a = whole % n, frac / 1000.0
            h0, r0 = clip["frames"][f0]
            h1, r1 = clip["frames"][(f0 + 1) % n]
            hips = Q.lerp(h0, h1, a)
            self.assertLess(Q.length(Q.sub(hips, v[:3])), 1e-5)
            for j in range(S.COUNT):
                self.assertLess(qdist(Q.qslerp(r0[j], r1[j], a), v[3 + 4 * j:7 + 4 * j]), 1e-5)


class TestRig(unittest.TestCase):
    VARIANTS = {
        "human": {},
        "gnome": {"scale": 0.35},
        "tall": {"scale": 1.6},
        "hunched": {"hunch": 0.6},
        "hooves": {"digitigrade": True},
        "arms_out": {"arm_drop": 0.0},
        "arms_down": {"arm_drop": 0.9},
        "three_fingers": {"fingers": 3},
        "short_neck": {"neck_bones": 1},
        "long_spine": {"spine_bones": 5},
        "no_helpers": {"helpers": False},
        "shifted": {"forward": 0.2},
    }

    def test_python_rig_maps_every_part(self):
        for name, opts in self.VARIANTS.items():
            bones, keys = synth.skeleton(**opts)
            r = RT.build_rig(bones, keys)
            self.assertTrue(r.ok, "%s: %s" % (name, r.reason))
            self.assertTrue(r.has_legs, name)
            joints = {rule[1] for rule in r.rules.values() if rule[0] == RT.MAP}
            for j in ("Head", "ClavL", "UpperArmL", "ForearmL", "HandL", "ClavR", "HandR", "ThighL", "CalfR",
                      "FootL", "ToeR"):
                self.assertIn(S.INDEX[j], joints, "%s: %s" % (name, j))

    def test_rest_pose_keeps_the_bind_directions(self):
        # The clip's rest pose aligned onto a skeleton points every mapped bone where the canonical rest pose does.
        bones, keys = synth.skeleton(arm_drop=0.0)
        r = RT.build_rig(bones, keys)
        targets, offset = RT.pose_bones(r, S.REST[0], [Q.IDENTITY] * S.COUNT)
        for bone, rule in r.rules.items():
            if rule[0] != RT.MAP or rule[1] not in (S.INDEX["UpperArmL"], S.INDEX["ThighR"]):
                continue
            child = [i for i, b in enumerate(bones) if b["parent"] == bone and r.rules.get(i, (None,))[0] == RT.MAP]
            d = Q.normalize(Q.sub(bones[child[0]]["pivot"], bones[bone]["pivot"]))
            self.assertLess(Q.length(Q.sub(Q.qrot(targets[bone], d), S.DIRECTION[rule[1]])), 1e-6)

    def test_models_that_cannot_dance(self):
        for key in (0, 1, 2, 3, 4, 6, 26):
            bones, keys = synth.skeleton(drop_key=key)
            self.assertFalse(RT.build_rig(bones, keys).ok, "key bone %d" % key)
        bones, keys = synth.skeleton(fingers=1)
        self.assertFalse(RT.build_rig(bones, keys).ok, "one finger")
        bones, keys = synth.skeleton()
        r = RT.build_rig(bones, keys[:5])
        self.assertFalse(r.ok, "a short key-bone lookup")

    def test_a_tail_dances_the_upper_body(self):
        bones, keys = synth.skeleton(legs=False)
        r = RT.build_rig(bones, keys)
        self.assertTrue(r.ok, r.reason)
        self.assertFalse(r.has_legs)

    def test_core_agrees_with_python(self):
        if not core_binary():
            self.skipTest("no C++ compiler")
        frames = sample_frames()
        variants = dict(self.VARIANTS)
        variants.update({"tail": {"legs": False}, "no_head_key": {"drop_key": 6}, "one_finger": {"fingers": 1}})
        with tempfile.TemporaryDirectory() as tmp:
            for name, opts in variants.items():
                bones, keys = synth.skeleton(**opts)
                path = os.path.join(tmp, name + ".txt")
                with open(path, "w") as f:
                    f.write(synth.to_text(bones, keys, frames))
                rc, out = run_core("--rig", path)
                self.assertEqual(rc, 0, name)
                ref = RT.build_rig(bones, keys)
                self.assertEqual(out[0] == "ok 1", ref.ok, "%s: %s / %s" % (name, out[:2], ref.reason))
                if not ref.ok:
                    continue
                self._compare(name, out, ref, frames)

    def _compare(self, name, out, ref, frames):
        rules, locals_ = {}, []
        for line in out:
            p = line.split()
            if p[0] == "root":
                self.assertEqual(int(p[1]), ref.root, name)
                self.assertAlmostEqual(float(p[3]), ref.scale, places=5, msg=name)
                self.assertEqual(p[5] == "1", ref.has_legs, name)
            elif p[0] == "rule":
                rules[int(p[1])] = (int(p[2]), int(p[3]), int(p[4]), float(p[5]), tuple(map(float, p[6:10])))
            elif p[0] == "frame":
                locals_.append({})
            elif p[0] == "local":
                locals_[-1][int(p[1])] = (tuple(map(float, p[2:6])), tuple(map(float, p[6:9])))
        self.assertEqual(set(rules), set(ref.rules), name)
        for bone, rule in ref.rules.items():
            kind, joint, owner, fraction, align = rules[bone]
            self.assertEqual(kind, KIND[rule[0]], "%s bone %d" % (name, bone))
            if rule[0] == RT.RIGID:
                self.assertEqual(owner, rule[1], "%s bone %d" % (name, bone))
            else:
                self.assertLess(qdist(align, rule[2]), 1e-4, "%s bone %d" % (name, bone))
            if rule[0] in (RT.SPINE, RT.NECK):
                self.assertAlmostEqual(fraction, rule[1], places=5)
            elif rule[0] in (RT.MAP, RT.ROOT, RT.PELVIS):
                self.assertEqual(joint, rule[1])
        for f, (hips, rots) in enumerate(frames):
            targets, offset = RT.pose_bones(ref, hips, rots)
            mine = RT.local_overrides(ref, targets, offset, lambda i: (Q.IDENTITY, (0.0, 0.0, 0.0)))
            for i, (q, t) in enumerate(mine):
                cq, ct = locals_[f][i]
                self.assertLess(qdist(q, cq), 2e-5, "%s frame %d bone %d" % (name, f, i))
                self.assertLess(Q.length(Q.sub(t, ct)), 2e-5, "%s frame %d bone %d" % (name, f, i))


class TestCatalogue(unittest.TestCase):
    def setUp(self):
        self.cat = C.load(os.path.join(TOOL, "dances.json"))

    def test_keys_are_append_only(self):
        keys = [d["key"] for d in self.cat["dances"]]
        self.assertEqual(keys[:len(FROZEN_KEYS)], FROZEN_KEYS, "a released dance key changed or moved")
        self.assertEqual(len(keys), len(FROZEN_KEYS), "add new dance keys to FROZEN_KEYS")

    def test_validation(self):
        import copy
        bad = copy.deepcopy(self.cat)
        bad["dances"][1]["id"] = 7
        self.assertRaises(C.CatalogueError, C.validate, bad)
        bad = copy.deepcopy(self.cat)
        bad["dances"][1]["command"] = "dance"
        self.assertRaises(C.CatalogueError, C.validate, bad)
        bad = copy.deepcopy(self.cat)
        bad["dances"][1]["key"] = bad["dances"][0]["key"]
        self.assertRaises(C.CatalogueError, C.validate, bad)
        bad = copy.deepcopy(self.cat)
        bad["kitBase"] = 900000
        self.assertRaises(C.CatalogueError, C.validate, bad)

    def test_every_dance_builds_loops_and_stays_on_the_ground(self):
        built = C.build(self.cat, os.path.join(TOOL, "dances"))
        for d in self.cat["dances"]:
            dance = built[d["key"]]
            frames = dance.sample(self.cat["fps"])
            self.assertLess(choreo.check_loop(frames), 72.0, d["key"])
            for hips, rots in frames:
                pos = S.positions(hips, rots)
                for toe in ("ToeL", "ToeR"):
                    self.assertGreater(pos[S.INDEX[toe]][2], -0.03, "%s: a toe goes into the ground" % d["key"])

    def test_generated_files_are_current(self):
        r = subprocess.run([sys.executable, "-I", os.path.join(TOOL, "danceforge.py"), "generate", "--check"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=1)
