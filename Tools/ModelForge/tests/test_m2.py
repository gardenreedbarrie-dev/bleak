"""Writer -> checker round trips and every section 5.3 invariant violated on purpose."""

import os
import struct
import unittest

import common as CM
from mflib import m2check as C
from mflib import m2write as W


def codes(data, skin):
    _m, f = C.parse(data, skin, "BH_Cafe_Tiny.m2")
    return f.codes()


def particle_ofs(data):
    return struct.unpack_from("<II", data, 0x128)[1]


class TinyModel(unittest.TestCase):
    def setUp(self):
        self.m2, self.skin, self.mod, self.sk = CM.tiny_model()

    def test_round_trip_clean(self):
        m, f = C.parse(self.m2, self.skin, "x.m2")
        self.assertEqual(f.items, [])
        self.assertEqual(len(m["vertices"]), len(self.mod.vertices))
        self.assertEqual(m["version"], 264)
        self.assertEqual(m["counts"]["sequenceIdxHashById"], 0, "the sequence hash must stay empty")
        self.assertEqual(m["textureCoordCombos"], [0, 0xFFFF])
        self.assertEqual(m["textureTransformCombos"], [0xFFFF])
        self.assertEqual(m["textureWeights"], [0x7FFF])
        self.assertEqual(m["numSkinProfiles"], 1)
        self.assertEqual(len(m["collision"]["indices"]), 3 * len(m["collision"]["normals"]))
        p = m["particles"][0]
        self.assertEqual(p["twinkle"], (10.0, 1.0, 1.0, 1.0))
        self.assertTrue(p["flags"] & 0x60000)
        self.assertEqual(struct.unpack_from("<I", self.m2, 0x10)[0], 0, "global flags")
        self.assertEqual(self.m2[0x130:0x140], bytes(16), "0x130-0x13F is zero")

    def test_alignment(self):
        for name, off, _e in C.ARRAYS:
            n, o = struct.unpack_from("<II", self.m2, off)
            if n:
                self.assertEqual(o % 16, 0, "%s at 0x%X is not 16-byte aligned" % (name, o))
            else:
                self.assertEqual(o, 0, "%s: count 0 must have offset 0" % name)

    # ---- section 5.3 hard errors, the particle flags 0 one first
    def test_particle_flags_zero(self):
        po = particle_ofs(self.m2)
        self.assertIn("client.particle_style", codes(CM.patch(self.m2, po + 4, "<I", 0), self.skin))

    def test_particle_tail_quads(self):
        po = particle_ofs(self.m2)
        self.assertIn("contract.particle_tail", codes(CM.patch(self.m2, po + 4, "<I", 0x40000), self.skin))

    def test_magic_version_size(self):
        self.assertIn("client.magic", codes(b"MD21" + self.m2[4:], self.skin))
        self.assertIn("client.version", codes(CM.patch(self.m2, 4, "<I", 263), self.skin))
        self.assertIn("client.version", codes(CM.patch(self.m2, 4, "<I", 265), self.skin))
        self.assertIn("client.header_size", codes(self.m2[:0x100], self.skin))

    def test_array_bounds_and_wrap(self):
        n, o = CM.header_array(self.m2, 0x3C)
        self.assertIn("client.array_bounds", codes(CM.patch(self.m2, 0x40, "<I", len(self.m2) + 16), self.skin))
        # count chosen so that 0x30 * count wraps 32 bits: the client's test passes, the read would not
        self.assertIn("client.array_wraps", codes(CM.patch(self.m2, 0x3C, "<I", 0x05555556), self.skin))
        # a count-0 array with an offset past the end also fails M2Init
        self.assertIn("client.array_bounds", codes(CM.patch(self.m2, 0x14, "<II", 0, len(self.m2) + 64), self.skin))

    def test_sequence_flag_0x20(self):
        _n, so = CM.header_array(self.m2, 0x1C)
        self.assertIn("client.sequence_not_inline", codes(CM.patch(self.m2, so + 0x0C, "<I", 0), self.skin))

    def test_no_bones_no_sequences(self):
        self.assertIn("client.no_bones", codes(CM.patch(self.m2, 0x2C, "<I", 0), self.skin))
        self.assertIn("client.no_sequences", codes(CM.patch(self.m2, 0x1C, "<I", 0), self.skin))

    def test_skin_profiles(self):
        self.assertIn("contract.skin_profiles", codes(CM.patch(self.m2, 0x44, "<I", 2), self.skin))
        self.assertIn("client.skin_profiles", codes(CM.patch(self.m2, 0x44, "<I", 5), self.skin))

    def test_sequence_hash_loops_forever(self):
        _n, bc = CM.header_array(self.m2, 0x78)      # boneCombos holds a single 0
        bad = CM.patch(self.m2, 0x24, "<II", 1, bc)  # hash count 1 with [0]
        self.assertIn("client.sequence_hash", codes(bad, self.skin))

    def test_texture_weights(self):
        self.assertIn("client.texture_weights", codes(CM.patch(self.m2, 0x58, "<II", 0, 0), self.skin))
        _n, tw = CM.header_array(self.m2, 0x58)
        _kc, ko = struct.unpack_from("<II", self.m2, tw + 12)
        _ic, io = struct.unpack_from("<II", self.m2, ko)
        self.assertIn("client.texture_weight_zero", codes(CM.patch(self.m2, io, "<h", 0), self.skin))
        self.assertIn("client.texture_weight_empty", codes(CM.patch(self.m2, tw + 12, "<II", 0, 0), self.skin))

    def test_blend_mode(self):
        _n, mo = CM.header_array(self.m2, 0x70)
        self.assertIn("client.blend_mode", codes(CM.patch(self.m2, mo + 2, "<H", 7), self.skin))

    def test_emitter_type_texture_cells_rate_twinkle(self):
        po = particle_ofs(self.m2)
        for t in (0, 4):
            self.assertIn("client.emitter_type", codes(CM.patch(self.m2, po + 0x29, "<B", t), self.skin))
        self.assertIn("client.particle_texture", codes(CM.patch(self.m2, po + 0x16, "<H", 2), self.skin))
        for v in (0, 3):
            self.assertIn("client.particle_cells", codes(CM.patch(self.m2, po + 0x30, "<H", v), self.skin))
        self.assertIn("contract.particle_twinkle", codes(CM.patch(self.m2, po + 0x160, "<f", 2.0), self.skin))
        self.assertIn("contract.particle_twinkle", codes(CM.patch(self.m2, po + 0x164, "<f", 0.5), self.skin))
        self.assertIn("contract.particle_rate", codes(CM.patch(self.m2, po + 0xB0 + 4, "<IIII", 0, 0, 0, 0),
                                                       self.skin))

    def test_particle_part_tracks(self):
        """Colour, alpha and scale are sampled for every particle (ParticleSystem2.cpp:683-684): an empty one
        sends PartTrackSearch to times[0x7FFFFFFF], fewer values than times reads past the values."""
        po = particle_ofs(self.m2)
        for off in (0x104, 0x114, 0x124):
            self.assertIn("client.particle_part_track", codes(CM.patch(self.m2, po + off, "<IIII", 0, 0, 0, 0),
                                                              self.skin), hex(off))
            vc = struct.unpack_from("<I", self.m2, po + off + 8)[0]
            self.assertIn("client.particle_part_track", codes(CM.patch(self.m2, po + off + 8, "<I", vc - 1),
                                                              self.skin), hex(off))
        # three values with no times: PartTrackKeys runs on an empty times array
        self.assertIn("client.particle_part_track", codes(CM.patch(self.m2, po + 0x104, "<II", 0, 0), self.skin))
        # one value with no times is sampled as is: the client copes, the writer contract does not
        _tcn, tof = struct.unpack_from("<II", self.m2, po + 0x104)
        one = CM.patch(CM.patch(self.m2, po + 0x104, "<II", 0, 0), po + 0x10C, "<I", 1)
        c = codes(one, self.skin)
        self.assertNotIn("client.particle_part_track", c)
        self.assertIn("contract.particle_part_track", c)
        # head / tail cells: sampled only when they have times, then values must follow the times
        for off in (0x13C, 0x14C):
            self.assertIn("client.particle_part_track", codes(CM.patch(self.m2, po + off, "<II", 2, tof),
                                                              self.skin), hex(off))
        self.assertEqual(codes(self.m2, self.skin), [])

    def test_writer_refuses_empty_part_tracks(self):
        for field in ("colors", "alphas", "scales"):
            _m2, _skin, mod, _sk = CM.tiny_model()
            setattr(mod.particles[0], field, ())
            with self.assertRaises(ValueError, msg=field):
                W.write_m2(mod)
        _m2, _skin, mod, _sk = CM.tiny_model()
        mod.particles[0].alphas = (0, 100)
        with self.assertRaises(ValueError):
            W.write_m2(mod)

    def test_writer_without_rate_key_is_caught(self):
        m2, skin, mod, sk = CM.tiny_model()
        mod.particles[0].write_emission_rate = False
        self.assertIn("contract.particle_rate", codes(W.write_m2(mod), skin))

    def test_track_loop_index_and_outer_count(self):
        _n, tw = CM.header_array(self.m2, 0x58)
        self.assertIn("client.track_loop_index", codes(CM.patch(self.m2, tw + 2, "<H", 5), self.skin))
        bad = CM.patch(CM.patch(self.m2, tw + 4, "<I", 2), tw + 12, "<I", 2)
        self.assertIn("client.track_outer_count", codes(bad, self.skin))

    def test_plume_and_bounds(self):
        po = particle_ofs(self.m2)
        self.assertIn("contract.plume_bounds", codes(CM.patch(self.m2, po + 8 + 8, "<f", 5.0), self.skin))
        self.assertIn("contract.bounds", codes(CM.patch(self.m2, 0xA0 + 20, "<f", 0.1), self.skin))
        self.assertIn("contract.bounds_radius", codes(CM.patch(self.m2, 0xA0 + 24, "<f", 0.01), self.skin))

    def test_name(self):
        _n, no = CM.header_array(self.m2, 0x08)
        self.assertIn("contract.name", codes(CM.patch(self.m2, no, "<2s", b"XX"), self.skin))
        probs = C.check_unique_names([("a/BH_Cafe_A.m2", "BH_Cafe_A"), ("b/bh_cafe_a.m2", "BH_Cafe_A"),
                                      ("c/Other.m2", "Other")])
        self.assertTrue(any("repeats" in p for p in probs))
        self.assertTrue(any("prefix" in p for p in probs))

    def test_collision(self):
        n, o = CM.header_array(self.m2, 0xD8)
        self.assertIn("client.collision_ratio", codes(CM.patch(self.m2, 0xD8, "<I", n - 3), self.skin))
        self.assertIn("client.collision_index", codes(CM.patch(self.m2, o, "<H", 99), self.skin))

    # ---- skin
    def test_skin_errors(self):
        sk = self.skin
        _n, lo = struct.unpack_from("<II", sk, 0x04)
        self.assertIn("client.skin_lookup", codes(self.m2, CM.patch(sk, lo, "<H", 9999)))
        nb, _o = struct.unpack_from("<II", sk, 0x14)
        self.assertIn("client.skin_bones", codes(self.m2, CM.patch(sk, 0x14, "<I", nb - 1)))
        _n, so = struct.unpack_from("<II", sk, 0x1C)
        self.assertIn("client.section_bone_count", codes(self.m2, CM.patch(sk, so + 0x0C, "<H", 0)))
        self.assertIn("client.bone_count_max", codes(self.m2, CM.patch(sk, 0x2C, "<I", 0)))
        self.assertIn("client.section_level", codes(self.m2, CM.patch(sk, so, "<I", 0x00010000)))
        self.assertIn("client.section_center_bone", codes(self.m2, CM.patch(sk, so + 0x12, "<H", 7)))
        self.assertIn("client.section_center_bone", codes(self.m2, CM.patch(sk, so + 0x12, "<H", 1)))
        vc = struct.unpack_from("<H", sk, so + 6)[0]
        self.assertIn("client.section_index_range", codes(self.m2, CM.patch(sk, so + 6, "<H", vc // 2)))
        _n, bo = struct.unpack_from("<II", sk, 0x24)
        self.assertIn("client.batch_material", codes(self.m2, CM.patch(sk, bo + 0x0A, "<H", 5)))
        self.assertIn("client.batch_texture_combo", codes(self.m2, CM.patch(sk, bo + 0x10, "<H", 9)))
        self.assertIn("contract.batch_flags", codes(self.m2, CM.patch(sk, bo, "<B", 0x14)))
        self.assertIn("client.skin_size", codes(self.m2, sk[:0x20]))
        m, f = C.parse(self.m2, None, "BH_Cafe_Tiny.m2")
        self.assertIn("client.skin_missing", f.codes())


@unittest.skipUnless(CM.native_harness(), "g++ not available")
class NativeHarness(unittest.TestCase):
    """The client's own M2Init (copied into tests/native/m2init_harness.cpp) agrees with m2check."""

    def write(self, m2, skin, tag):
        d = os.path.join(CM.workdir(), "native_" + tag)
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, "BH_Cafe_Tiny.m2")
        with open(p, "wb") as f:
            f.write(m2)
        with open(os.path.join(d, "BH_Cafe_Tiny00.skin"), "wb") as f:
            f.write(skin)
        return p

    def test_clean_passes(self):
        m2, skin, _m, _s = CM.tiny_model()
        rc, out = CM.run_harness(self.write(m2, skin, "clean"))
        self.assertEqual(rc, 0, out)
        self.assertIn("OK", out)

    def test_violations_fail(self):
        m2, skin, _m, _s = CM.tiny_model()
        po = particle_ofs(m2)
        _n, so = struct.unpack_from("<II", skin, 0x1C)
        _n, bc = CM.header_array(m2, 0x78)
        cases = {
            "flags0": (CM.patch(m2, po + 4, "<I", 0), skin, "m_vertsPerParticle"),
            "version": (CM.patch(m2, 4, "<I", 265), skin, "M2Init failed"),
            "emitter": (CM.patch(m2, po + 0x29, "<B", 4), skin, "emitterType"),
            "bonecount": (m2, CM.patch(skin, so + 0x0C, "<H", 0), "divides by zero"),
            "hash": (CM.patch(m2, 0x24, "<II", 1, bc), skin, "never ends"),
            "bounds": (CM.patch(m2, 0x40, "<I", len(m2) + 16), skin, "M2Init failed"),
            "centerbone": (m2, CM.patch(skin, so + 0x12, "<H", 7), "centerBoneIndex"),
            "colourtrack": (CM.patch(m2, po + 0x104, "<IIII", 0, 0, 0, 0), skin, "colour track"),
            "alphatrack": (CM.patch(m2, po + 0x114, "<IIII", 0, 0, 0, 0), skin, "alpha track"),
            "scaletrack": (CM.patch(m2, po + 0x124 + 8, "<I", 2), skin, "scale track"),
            "headcell": (CM.patch(m2, po + 0x13C, "<II", 2, struct.unpack_from("<I", m2, po + 0x108)[0]), skin,
                         "head cell"),
        }
        for tag, (a, b, want) in cases.items():
            rc, out = CM.run_harness(self.write(a, b, tag))
            self.assertNotEqual(rc, 0, "%s: %s" % (tag, out))
            self.assertIn(want, out, tag)


if __name__ == "__main__":
    unittest.main()
