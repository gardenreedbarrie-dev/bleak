"""Independent M2 v264 + .skin parser and validator (CAFE.SPEC.md section 5.3).

Written from Engine/Source/Model2/M2Data.h and the client's loader, not from the writer: it shares no code with
m2write.py / skinwrite.py. It mirrors

  M2Init (M2Shared.cpp:1541-1555)          header size, magic 'MD20', version exactly 0x108 (264), then every array
                                           of M2Data in the client's order, each with the client's bounds test
                                           `offset > size || offset + sizeof(T) * count > size` (M2Shared.cpp:141)
  M2Init<M2Track> (M2Shared.cpp:174-232)   a track with loopIndex 0xFFFF is relocated with NO bounds check and
                                           indexes data.m_sequences[i] for every outer entry with no bound check
                                           (here: hard errors), any other loopIndex is bounds checked and later
                                           read through m_loops[loopIndex] (CM2Model::FindKey, M2Model.cpp:2343)
  FinishLoadingSkinProfile (M2Shared.cpp:1308-1340) and InitializeSkinProfile (M2Shared.cpp:1137-1262)
  CM2Model::InitializeLoaded particle setup (M2Model.cpp:7281-7530)
  first-draw reads                         the particle part-track sampling (ParticleSystem2.cpp:85-188, 683-697)
                                           and the transparent-batch depth sort through m_boneMatrices
                                           [m_centerBoneIndex] (M2Scene.cpp:1890-1894)

Every finding is an error (exit 1): the codes starting with "client." are what the 3.3.5a client itself fails,
crashes or loops on; "contract." are the ModelForge writer contract of section 5.2 (things the client accepts
but that the café models must not do).
"""

import json
import math
import os
import struct

MD20 = 0x3032444D
HEADER = 0x138

# (name, header offset, element size), in M2Init's order (M2Shared.cpp:1554)
ARRAYS = [
    ("name", 0x08, 1), ("loops", 0x14, 4), ("sequences", 0x1C, 0x40), ("sequenceIdxHashById", 0x24, 2),
    ("bones", 0x2C, 0x58), ("boneIndicesById", 0x34, 2), ("vertices", 0x3C, 0x30), ("colors", 0x48, 0x28),
    ("textures", 0x50, 0x10), ("textureWeights", 0x58, 0x14), ("textureTransforms", 0x60, 0x3C),
    ("textureIndicesById", 0x68, 2), ("materials", 0x70, 4), ("boneCombos", 0x78, 2), ("textureCombos", 0x80, 2),
    ("textureCoordCombos", 0x88, 2), ("textureWeightCombos", 0x90, 2), ("textureTransformCombos", 0x98, 2),
    ("collisionIndices", 0xD8, 2), ("collisionPositions", 0xE0, 12), ("collisionFaceNormals", 0xE8, 12),
    ("attachments", 0xF0, 0x28), ("attachmentIndicesById", 0xF8, 2), ("events", 0x100, 0x24),
    ("lights", 0x108, 0x9C), ("cameras", 0x110, 0x64), ("cameraIndicesById", 0x118, 2), ("ribbons", 0x120, 0xB0),
    ("particles", 0x128, 0x1DC), ("textureCombinerCombos", 0x130, 2),
]

# tracks inside array elements: (array, [(offset in element, value size, kind)]) kind "track" or "base"
TRACKS = {
    "bones": [(0x10, 12, "track"), (0x24, 8, "track"), (0x38, 12, "track")],
    "colors": [(0x00, 12, "track"), (0x14, 2, "track")],
    "textureWeights": [(0x00, 2, "track")],
    "textureTransforms": [(0x00, 12, "track"), (0x14, 16, "track"), (0x28, 12, "track")],
    "attachments": [(0x14, 1, "track")],
    "events": [(0x18, 0, "base")],
    "lights": [(0x10, 12, "track"), (0x24, 4, "track"), (0x38, 12, "track"), (0x4C, 4, "track"),
               (0x60, 4, "track"), (0x74, 4, "track"), (0x88, 1, "track")],
    "cameras": [(0x10, 36, "track"), (0x30, 36, "track"), (0x50, 12, "track")],
    "ribbons": [(0x24, 12, "track"), (0x38, 2, "track"), (0x4C, 4, "track"), (0x60, 4, "track"),
                (0x84, 2, "track"), (0x98, 1, "track")],
    "particles": [(0x34, 4, "track"), (0x48, 4, "track"), (0x5C, 4, "track"), (0x70, 4, "track"),
                  (0x84, 4, "track"), (0x98, 4, "track"), (0xB0, 4, "track"), (0xC8, 4, "track"),
                  (0xDC, 4, "track"), (0xF0, 4, "track"), (0x1C8, 1, "track")],
}
# plain arrays inside elements: (array, [(offset, element size)])
SUBARRAYS = {
    "textures": [(0x08, 1)],
    "ribbons": [(0x14, 2), (0x1C, 2)],
    "particles": [(0x18, 1), (0x20, 1), (0x104, 2), (0x10C, 12), (0x114, 2), (0x11C, 2), (0x124, 2), (0x12C, 8),
                  (0x13C, 2), (0x144, 2), (0x14C, 2), (0x154, 2), (0x1C0, 12)],
}
PARTICLE_TRACK_NAMES = ["speed", "variation", "latitude", "longitude", "gravity", "life", "emissionRate", "width",
                        "length", "zsource", "visibility"]

SKIN_ARRAYS = [("vertices", 0x04, 2), ("indices", 0x0C, 2), ("bones", 0x14, 4), ("skinSections", 0x1C, 0x30),
               ("batches", 0x24, 0x18)]


class Findings:
    def __init__(self):
        self.items = []

    def add(self, code, msg):
        self.items.append({"code": code, "msg": msg})

    def codes(self):
        return [i["code"] for i in self.items]

    def __bool__(self):
        return bool(self.items)


def _u32(data, off):
    return struct.unpack_from("<I", data, off)[0]


def _arr(data, off):
    return struct.unpack_from("<II", data, off)


def _in_bounds(off, elem, count, size):
    """The client's test (unsigned 32-bit arithmetic) and the true one; both must pass."""
    end32 = (off + elem * count) & 0xFFFFFFFF
    client_ok = not (off > size or end32 > size)
    true_ok = off <= size and off + elem * count <= size
    return client_ok, true_ok


def _check_array(f, data, name, off, elem, count, where):
    size = len(data)
    client_ok, true_ok = _in_bounds(off, elem, count, size)
    if not client_ok:
        f.add("client.array_bounds", "%s: %s (count %d, offset 0x%X, %d bytes each) lies outside the %d-byte file;"
              " M2Init fails the model" % (where, name, count, off, elem, size))
        return False
    if not true_ok:
        f.add("client.array_wraps", "%s: %s end wraps 32 bits; the client's test passes but reads past the file"
              % (where, name))
        return False
    return True


def _check_track(f, data, base_off, value_size, kind, nseq, nloops, seq_flags, where):
    """Mirrors M2Init(M2Track) for the not-low-priority path (s_sequenceIndex == 0xFFFFFFFF)."""
    size = len(data)
    _ttype, loop = struct.unpack_from("<HH", data, base_off)
    tcount, toff = _arr(data, base_off + 4)
    keyed = kind == "track"
    if keyed:
        kcount, koff = _arr(data, base_off + 12)
    info = {"loop": loop, "outer": tcount, "keys": []}
    if tcount > 0 and loop != 0xFFFF and loop >= nloops:
        f.add("client.track_loop_index", "%s: loopIndex %d but the model has %d loops (global sequences); FindKey"
              " reads m_loops[loopIndex] (M2Model.cpp:2343-2344)" % (where, loop, nloops))
    if tcount > nseq:
        f.add("client.track_outer_count", "%s: %d per-sequence time arrays but %d sequences; M2Init indexes"
              " data.m_sequences[i] with no bound check (M2Shared.cpp:176-215)" % (where, tcount, nseq))
    if keyed and kcount != tcount:
        f.add("client.track_key_count", "%s: %d key arrays for %d time arrays" % (where, kcount, tcount))
    if loop == 0xFFFF:
        # the client relocates without any bounds check: everything must be inside the file
        if tcount and not (_in_bounds(toff, 8, tcount, size)[1]):
            f.add("client.track_unchecked_bounds", "%s: time arrays outside the file (loopIndex 0xFFFF is relocated"
                  " without a bounds check)" % where)
            return info
        if keyed and kcount and not _in_bounds(koff, 8, kcount, size)[1]:
            f.add("client.track_unchecked_bounds", "%s: key arrays outside the file" % where)
            return info
    else:
        if not _check_array(f, data, "track time arrays", toff, 8, tcount, where):
            return info
        if keyed and not _check_array(f, data, "track key arrays", koff, 8, kcount, where):
            return info
    for i in range(min(tcount, nseq)):
        if loop == 0xFFFF and not (seq_flags[i] & 0x20):
            continue  # its keys live in an .anim file
        c, o = _arr(data, toff + 8 * i)
        ok = _in_bounds(o, 4, c, size)
        if not (ok[0] if loop != 0xFFFF else ok[1]):
            f.add("client.track_unchecked_bounds" if loop == 0xFFFF else "client.array_bounds",
                  "%s: sequence %d times (count %d, offset 0x%X) outside the file" % (where, i, c, o))
            continue
        if keyed:
            kc, ko = _arr(data, koff + 8 * i) if i < kcount else (0, 0)
            ok = _in_bounds(ko, value_size, kc, size)
            if not (ok[0] if loop != 0xFFFF else ok[1]):
                f.add("client.track_unchecked_bounds" if loop == 0xFFFF else "client.array_bounds",
                      "%s: sequence %d keys outside the file" % (where, i))
                continue
            if kc != c:
                f.add("client.track_key_count", "%s: sequence %d has %d times and %d keys" % (where, i, c, kc))
            info["keys"].append((c, ko))
    return info


def _sequence_hash_ok(f, hashes, seq_ids):
    """FindSequenceIndex (M2Model.cpp:1154-1181): quadratic probing until 0xFFFF or a match. An absent id loops
    forever unless every probe sequence reaches a 0xFFFF slot."""
    n = len(hashes)
    if n == 0:
        return
    for k, v in enumerate(hashes):
        if v != 0xFFFF and v >= len(seq_ids):
            f.add("client.sequence_hash", "sequenceIdxHashById[%d] = %d but there are %d sequences" % (k, v,
                                                                                                    len(seq_ids)))
            return
    for start in range(n):
        # state (slot, step mod n): (step + n)^2 = step^2 (mod n), so a repeated state is an endless loop
        slot = start
        seen = set()
        reached = False
        step = 1
        while (slot, step % n) not in seen:
            seen.add((slot, step % n))
            if hashes[slot] == 0xFFFF:
                reached = True
                break
            slot = (slot + step * step) % n
            step += 1
        if not reached:
            f.add("client.sequence_hash", "sequenceIdxHashById has no reachable 0xFFFF from slot %d: looking up an"
                  " animation the model lacks loops forever in FindSequenceIndex" % start)
            return


def parse_skin(data):
    f = Findings()
    out = {"ok": False}
    if len(data) < 0x30:
        f.add("client.skin_size", "skin is %d bytes, shorter than M2SkinProfile (0x30)" % len(data))
        return out, f
    if data[:4] != b"SKIN":
        f.add("contract.skin_magic", "skin magic %r (written as 'SKIN')" % data[:4])
    arrays = {}
    ok = True
    for name, off, elem in SKIN_ARRAYS:
        c, o = _arr(data, off)
        arrays[name] = (c, o)
        if not _check_array(f, data, name, o, elem, c, "skin"):
            ok = False
    out["arrays"] = arrays
    out["boneCountMax"] = _u32(data, 0x2C)
    if not ok:
        return out, f
    vc, vo = arrays["vertices"]
    out["lookup"] = list(struct.unpack_from("<%dH" % vc, data, vo)) if vc else []
    ic, io = arrays["indices"]
    out["indices"] = list(struct.unpack_from("<%dH" % ic, data, io)) if ic else []
    bc, bo = arrays["bones"]
    out["bones"] = [tuple(data[bo + 4 * i: bo + 4 * i + 4]) for i in range(bc)]
    sc, so = arrays["skinSections"]
    secs = []
    for i in range(sc):
        v = struct.unpack_from("<IHHHHHHHH3f3ff", data, so + 0x30 * i)
        secs.append({"id": v[0], "vertexStart": v[1], "vertexCount": v[2], "indexStart": v[3], "indexCount": v[4],
                     "boneCount": v[5], "boneComboIndex": v[6], "boneInfluences": v[7], "centerBoneIndex": v[8],
                     "center": v[9:12], "sortCenter": v[12:15], "sortRadius": v[15]})
    out["sections"] = secs
    nb, bo2 = arrays["batches"]
    bats = []
    for i in range(nb):
        v = struct.unpack_from("<BbHHHHHHHHHHH", data, bo2 + 0x18 * i)
        bats.append({"flags": v[0], "priorityPlane": v[1], "shader": v[2], "skinSectionIndex": v[3],
                     "geosetIndex": v[4], "colorIndex": v[5], "materialIndex": v[6], "materialLayer": v[7],
                     "textureCount": v[8], "textureComboIndex": v[9], "textureCoordComboIndex": v[10],
                     "textureWeightComboIndex": v[11], "textureTransformComboIndex": v[12]})
    out["batches"] = bats
    out["ok"] = True
    return out, f


def _floats(data, off, n):
    return struct.unpack_from("<%df" % n, data, off)


def parse(data, skin=None, path=None):
    """Parses and validates. Returns (model dict, Findings). The model dict is what render.py draws."""
    f = Findings()
    m = {"path": path, "size": len(data)}
    if len(data) < HEADER:
        f.add("client.header_size", "file is %d bytes, shorter than M2Data (0x138); M2Init refuses it" % len(data))
        return m, f
    magic, version = struct.unpack_from("<II", data, 0)
    m["version"] = version
    if magic != MD20:
        f.add("client.magic", "magic %r is not 'MD20'" % data[:4])
        return m, f
    if version != 0x108:
        f.add("client.version", "version %d; M2Init accepts exactly 264 (0x108)" % version)
        return m, f
    flags = _u32(data, 0x10)
    m["flags"] = flags
    arrays = {}
    for name, off, elem in ARRAYS:
        c, o = _arr(data, off)
        arrays[name] = (c, o, elem)
    m["counts"] = {k: v[0] for k, v in arrays.items()}
    nseq = arrays["sequences"][0]
    nloops = arrays["loops"][0]
    structural_ok = True
    seq_flags = []
    for name, off, elem in ARRAYS:
        if name == "textureCombinerCombos" and not (flags & 8):
            continue
        c, o, _ = arrays[name]
        if not _check_array(f, data, name, o, elem, c, "m2"):
            structural_ok = False
            continue
        if name == "sequences":
            seq_flags = [_u32(data, o + 0x40 * i + 0x0C) for i in range(c)]
        for sub_off, sub_elem in SUBARRAYS.get(name, []):
            for i in range(c):
                sc, so = _arr(data, o + elem * i + sub_off)
                if not _check_array(f, data, "%s[%d]+0x%X" % (name, i, sub_off), so, sub_elem, sc, "m2"):
                    structural_ok = False
        for t_off, vsize, kind in TRACKS.get(name, []):
            for i in range(c):
                where = "%s[%d] track +0x%X" % (name, i, t_off)
                if name == "particles":
                    where = "particles[%d].%s" % (i, PARTICLE_TRACK_NAMES[TRACKS["particles"].index(
                        (t_off, vsize, kind))])
                _check_track(f, data, o + elem * i + t_off, vsize, kind, nseq, nloops,
                             seq_flags + [0] * 64, where)
    if not structural_ok:
        return m, f

    # ---------------------------------------------------------------------------------------- contents
    nc, no = arrays["name"][:2]
    raw = data[no:no + nc]
    m["name"] = raw.split(b"\0", 1)[0].decode("ascii", "replace")
    if not raw.endswith(b"\0") or b"\0" in raw[:-1]:
        f.add("contract.name", "the name must be NUL terminated with the NUL counted")
    if not m["name"].startswith("BH_Cafe_"):
        f.add("contract.name", "name %r lacks the BH_Cafe_ prefix" % m["name"])
    if flags != 0:
        f.add("contract.global_flags", "global flags 0x%X (written as 0; never 0x8, 0x10, 0x20 or 0x40)" % flags)
    if nloops:
        f.add("contract.loops", "%d global sequences (the café models have none)" % nloops)

    if arrays["bones"][0] < 1:
        f.add("client.no_bones", "no bones: the skin's bone lookups and the batched draws need bone 0")
    if nseq < 1:
        f.add("client.no_sequences", "no sequences: the model has nothing to play (Stand is sequence id 0)")
    seqs = []
    so = arrays["sequences"][1]
    for i in range(nseq):
        sid, var, dur, ms, sfl, freq, r0, r1, blend = struct.unpack_from("<HHIfIIiiI", data, so + 0x40 * i)
        b = _floats(data, so + 0x40 * i + 0x20, 7)
        vn, an = struct.unpack_from("<HH", data, so + 0x40 * i + 0x3C)
        seqs.append({"id": sid, "variation": var, "duration": dur, "flags": sfl, "frequency": freq,
                     "blendTime": blend, "bounds": b, "variationNext": vn, "aliasNext": an})
        if not sfl & 0x20:
            f.add("client.sequence_not_inline", "sequence %d (id %d) lacks flag 0x20: the client then loads its"
                  " keys from %04d-%02d.anim, which the café never ships" % (i, sid, sid, var))
        if vn != 0xFFFF and vn >= nseq:
            f.add("client.sequence_variation", "sequence %d variationNext %d out of range" % (i, vn))
        if an >= nseq:
            f.add("client.sequence_alias", "sequence %d aliasNext %d out of range" % (i, an))
    m["sequences"] = seqs
    hc, ho = arrays["sequenceIdxHashById"][:2]
    hashes = list(struct.unpack_from("<%dH" % hc, data, ho)) if hc else []
    _sequence_hash_ok(f, hashes, [s["id"] for s in seqs])

    nsp = _u32(data, 0x44)
    m["numSkinProfiles"] = nsp
    if nsp != 1:
        f.add("contract.skin_profiles", "numSkinProfiles %d (written as 1: profile 0 with 21 bones)" % nsp)
    if nsp == 0 or nsp > 4:
        f.add("client.skin_profiles", "numSkinProfiles %d: GetSkinProfileIndex reads s_skinProfileBoneCounts"
              "[4 - n + i] (M2Shared.cpp:1652-1660)" % nsp)

    nbones = arrays["bones"][0]
    bo = arrays["bones"][1]
    for i in range(nbones):
        parent = struct.unpack_from("<H", data, bo + 0x58 * i + 8)[0]
        if parent != 0xFFFF and parent >= nbones:
            f.add("client.bone_parent", "bone %d parent %d out of range" % (i, parent))

    # vertices
    vc, vo = arrays["vertices"][:2]
    verts = []
    for i in range(vc):
        p = _floats(data, vo + 0x30 * i, 3)
        w = tuple(data[vo + 0x30 * i + 12: vo + 0x30 * i + 16])
        bi = tuple(data[vo + 0x30 * i + 16: vo + 0x30 * i + 20])
        n = _floats(data, vo + 0x30 * i + 0x14, 3)
        uv0 = _floats(data, vo + 0x30 * i + 0x20, 2)
        uv1 = _floats(data, vo + 0x30 * i + 0x28, 2)
        verts.append((p, n, uv0, uv1))
        if i < 100000 and sum(w) != 255:
            f.add("contract.vertex_weights", "vertex %d bone weights sum to %d (written as 255,0,0,0)" % (i, sum(w)))
        if any(b >= max(1, nbones) for b, wt in zip(bi, w) if wt):
            f.add("client.vertex_bone", "vertex %d uses a bone index past %d bones" % (i, nbones))
        ln = math.sqrt(sum(x * x for x in n))
        if not all(math.isfinite(x) for x in p + n + uv0) or abs(ln - 1.0) > 0.01:
            f.add("contract.vertex", "vertex %d has a non-finite value or a normal of length %.3f" % (i, ln))
    m["vertices"] = verts

    # textures
    tc, to = arrays["textures"][:2]
    texs = []
    for i in range(tc):
        ttype, tflags, fc, fo = struct.unpack_from("<IIII", data, to + 0x10 * i)
        fn = data[fo:fo + fc]
        name = fn.split(b"\0", 1)[0].decode("ascii", "replace")
        texs.append({"type": ttype, "flags": tflags, "path": name})
        if ttype == 0:
            if fc < 2 or not fn.endswith(b"\0"):
                f.add("contract.texture_name", "texture %d (type 0) has no NUL-terminated file name; the client"
                      " would draw it solid white (M2Shared.cpp:1716-1724)" % i)
            if "/" in name:
                f.add("contract.texture_name", "texture %d path %r uses '/' (written with backslashes)" % (i, name))
            if not name.lower().endswith(".blp"):
                f.add("contract.texture_name", "texture %d path %r is not a .blp" % (i, name))
        if tflags & ~3:
            f.add("contract.texture_flags", "texture %d flags 0x%X (only wrap bits 0x1, 0x2)" % (i, tflags))
    m["textures"] = texs

    # texture weights
    wc, wo = arrays["textureWeights"][:2]
    weights = []
    if wc == 0:
        f.add("client.texture_weights", "no texture weights: every batch's weight combo reads past the array and"
              " an empty weight makes the model invisible")
    for i in range(wc):
        t_off = wo + 0x14 * i
        loop = struct.unpack_from("<H", data, t_off + 2)[0]
        tcn, tof = _arr(data, t_off + 4)
        kcn, kof = _arr(data, t_off + 12)
        val = None
        if tcn >= 1 and kcn >= 1:
            ic, io = _arr(data, kof)
            if ic >= 1 and _in_bounds(io, 2, ic, len(data))[1]:
                val = struct.unpack_from("<h", data, io)[0]
        weights.append(val)
        if val is None:
            f.add("client.texture_weight_empty", "texture weight %d has no key: the batches using it are invisible"
                  % i)
        elif val == 0:
            f.add("client.texture_weight_zero", "texture weight %d is 0: the batches using it are invisible" % i)
        if loop != 0xFFFF:
            f.add("contract.track_loop", "texture weight %d loopIndex %d (written as 0xFFFF)" % (i, loop))
    m["textureWeights"] = weights

    # materials
    mc, mo = arrays["materials"][:2]
    mats = []
    for i in range(mc):
        mf, mb = struct.unpack_from("<HH", data, mo + 4 * i)
        mats.append({"flags": mf, "blend": mb})
        if mb > 6:
            f.add("client.blend_mode", "material %d blendMode %d > 6: s_blendModes[pass][blend] (M2Scene.cpp:30)"
                  " reads past its 7 entries" % (i, mb))
    m["materials"] = mats

    def u16list(name):
        c, o = arrays[name][:2]
        return list(struct.unpack_from("<%dH" % c, data, o)) if c else []

    m["boneCombos"] = u16list("boneCombos")
    m["textureCombos"] = u16list("textureCombos")
    m["textureCoordCombos"] = u16list("textureCoordCombos")
    m["textureWeightCombos"] = u16list("textureWeightCombos")
    m["textureTransformCombos"] = u16list("textureTransformCombos")
    for i, v in enumerate(m["boneCombos"]):
        if v >= max(1, nbones):
            f.add("client.bone_combo", "boneCombos[%d] = %d past %d bones" % (i, v, nbones))
    for i, v in enumerate(m["textureCombos"]):
        if v >= tc and v != 0xFFFF:
            f.add("client.texture_combo", "textureCombos[%d] = %d past %d textures" % (i, v, tc))
    for i, v in enumerate(m["textureWeightCombos"]):
        if v >= wc:
            f.add("client.weight_combo", "textureWeightCombos[%d] = %d past %d weights" % (i, v, wc))
    for i, v in enumerate(m["textureTransformCombos"]):
        if v != 0xFFFF and v >= arrays["textureTransforms"][0]:
            f.add("client.transform_combo", "textureTransformCombos[%d] = %d past the transforms" % (i, v))

    # bounds
    b = _floats(data, 0xA0, 7)
    cb = _floats(data, 0xBC, 7)
    m["bounds"] = {"min": list(b[0:3]), "max": list(b[3:6]), "radius": b[6]}
    m["collisionBounds"] = {"min": list(cb[0:3]), "max": list(cb[3:6]), "radius": cb[6]}

    # collision
    cic, cio = arrays["collisionIndices"][:2]
    cpc, cpo = arrays["collisionPositions"][:2]
    cnc, cno = arrays["collisionFaceNormals"][:2]
    cind = list(struct.unpack_from("<%dH" % cic, data, cio)) if cic else []
    cpos = [_floats(data, cpo + 12 * i, 3) for i in range(cpc)]
    cnrm = [_floats(data, cno + 12 * i, 3) for i in range(cnc)]
    m["collision"] = {"indices": cind, "positions": cpos, "normals": cnrm}
    if cic != 3 * cnc:
        f.add("client.collision_ratio", "%d collision indices for %d face normals (must be 3:1)" % (cic, cnc))
    for k, v in enumerate(cind):
        if v >= cpc:
            f.add("client.collision_index", "collision index %d = %d past %d positions" % (k, v, cpc))
            break
    for k in range(min(cnc, cic // 3)):
        n = cnrm[k]
        ln = math.sqrt(sum(x * x for x in n))
        if abs(ln - 1.0) > 1e-3:
            f.add("contract.collision_normal", "collision normal %d has length %.4f" % (k, ln))
            continue
        ia, ib, ic2 = cind[3 * k: 3 * k + 3]
        if max(ia, ib, ic2) < cpc:
            pa, pb, pc = cpos[ia], cpos[ib], cpos[ic2]
            e1 = [pb[i] - pa[i] for i in range(3)]
            e2 = [pc[i] - pa[i] for i in range(3)]
            cr = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])
            if sum(cr[i] * n[i] for i in range(3)) <= 0:
                f.add("contract.collision_normal", "collision face %d normal points against its winding" % k)
    for p in cpos:
        if any(p[i] < cb[i] - 1e-4 or p[i] > cb[3 + i] + 1e-4 for i in range(3)):
            f.add("contract.collision_bounds", "collision position %s outside the collision bounds" % (p,))
            break

    # particles
    pc, po = arrays["particles"][:2]
    parts = []
    for i in range(pc):
        e = po + 0x1DC * i
        pid, pfl = struct.unpack_from("<II", data, e)
        pos = _floats(data, e + 8, 3)
        bone, texi = struct.unpack_from("<HH", data, e + 0x14)
        blend, etype = data[e + 0x28], data[e + 0x29]
        prio = struct.unpack_from("<h", data, e + 0x2E)[0]
        rows, cols = struct.unpack_from("<HH", data, e + 0x30)
        vals = {}
        for (t_off, vsize, kind), tname in zip(TRACKS["particles"], PARTICLE_TRACK_NAMES):
            vals[tname] = _first_key(data, e + t_off, vsize)
        life_var = _floats(data, e + 0xAC, 1)[0]
        rate_var = _floats(data, e + 0xC4, 1)[0]
        ptr = {}
        for nm, off, fmt, sz in (("color", 0x104, "3f", 12), ("alpha", 0x114, "h", 2), ("scale", 0x124, "2f", 8)):
            tcn, tof = _arr(data, e + off)
            vcn, vof = _arr(data, e + off + 8)
            ptr[nm] = {"times": list(struct.unpack_from("<%dh" % tcn, data, tof)) if tcn else [],
                       "values": [struct.unpack_from("<" + fmt, data, vof + sz * k) for k in range(vcn)]}
        tw_fps, tw_onoff, tw_l, tw_h = _floats(data, e + 0x160, 4)
        part = {"flags": pfl, "position": pos, "bone": bone, "textureIndex": texi, "blend": blend,
                "emitterType": etype, "priorityPlane": prio, "rows": rows, "cols": cols, "tracks": vals,
                "lifeVariation": life_var, "emissionRateVariation": rate_var, "partTracks": ptr,
                "twinkle": (tw_fps, tw_onoff, tw_l, tw_h)}
        parts.append(part)
        w = "particle %d" % i
        if etype not in (1, 2, 3):
            f.add("client.emitter_type", "%s emitterType %d: InitializeLoaded creates no emitter for it and then"
                  " dereferences the null pointer (M2Model.cpp:7298-7310)" % (w, etype))
        if texi >= tc:
            f.add("client.particle_texture", "%s textureIndex %d past %d textures (M2Model.cpp:7470)" % (w, texi, tc))
        if bone >= max(1, nbones):
            f.add("client.particle_bone", "%s bone %d past %d bones" % (w, bone, nbones))
        if not pfl & 0x60000:
            f.add("client.particle_style", "%s flags 0x%X have neither 0x20000 (head) nor 0x40000 (tail): "
                  "m_vertsPerParticle stays 0 (ParticleSystem2.cpp:301-332) and the render paths divide by it "
                  "(ParticleSystem2.cpp:2336, 2362; CM2SceneRender.cpp:748-780)" % (w, pfl))
        if pfl & 0x40000:
            f.add("contract.particle_tail", "%s uses tail quads (0x40000); the café emitters use head quads" % w)
        if blend > 6:
            f.add("client.particle_blend", "%s blendMode %d > 6" % (w, blend))
        for nm, v in (("rows", rows), ("cols", cols)):
            if v == 0 or v & (v - 1):
                f.add("client.particle_cells", "%s %s %d is not a non-zero power of two; SetTextureDimensions "
                      "refuses it (ParticleSystem2.cpp:281-285) and the cell size stays undefined" % (w, nm, v))
        if vals["emissionRate"] is None:
            f.add("contract.particle_rate", "%s emissionRate has no key: nothing is ever emitted" % w)
        if (tw_fps, tw_onoff, tw_l, tw_h) != (10.0, 1.0, 1.0, 1.0):
            f.add("contract.particle_twinkle", "%s twinkle (fps %g, on/off %g, scale %g-%g); written as 10, 1, 1-1:"
                  " lower values cull or shrink particles (ParticleSystem2.cpp:875-909)" % (w, tw_fps, tw_onoff,
                                                                                         tw_l, tw_h))
        # InterpolateAllTracks samples colour, alpha and scale for every live particle (ParticleSystem2.cpp:
        # 434-445, 683-684, 905-907). With one value the value is used as is; otherwise PartTrackKeys picks the
        # keys from the times (115-140) and, with no times, PartTrackSearch starts at hi = count - 1 = 0xFFFFFFFF
        # and reads times[0x7FFFFFFF] (85-112). DetermineIfSimple (1757-1772) never takes an emitter with an
        # empty track off that path, so an empty colour, alpha or scale track crashes the first draw.
        for nm in ("color", "alpha", "scale"):
            nt, nv = len(ptr[nm]["times"]), len(ptr[nm]["values"])
            if nv == 0 or (nv != 1 and (nt < 2 or nv < nt)):
                f.add("client.particle_part_track", "%s %s track has %d times and %d values: InterpolateAllTracks "
                      "samples it for every particle, PartTrackKeys takes key indices from the times and reads "
                      "the values with them, and with no times PartTrackSearch reads times[0x7FFFFFFF] "
                      "(ParticleSystem2.cpp:85-188, 683-684)" % (w, nm, nt, nv))
            elif nt != nv:
                f.add("contract.particle_part_track", "%s %s track has %d times and %d values (written with one "
                      "value per time)" % (w, nm, nt, nv))
        # head and tail cell tracks are sampled only when they have times (ParticleSystem2.cpp:689-697), then
        # through PartTrackSample<uint16_t> (178-188), which reads values[key0] and values[key1]
        for nm, off in (("headCell", 0x13C), ("tailCell", 0x14C)):
            nt = _arr(data, e + off)[0]
            nv = _arr(data, e + off + 8)[0]
            if nt and nv != 1 and (nt < 2 or nv < nt):
                f.add("client.particle_part_track", "%s %s track has %d times and %d values: PartTrackSample "
                      "reads values by the key indices of the times (ParticleSystem2.cpp:178-188, 689-697)"
                      % (w, nm, nt, nv))
            elif nt and nt != nv:
                f.add("contract.particle_part_track", "%s %s track has %d times and %d values (written empty)"
                      % (w, nm, nt, nv))
        plume = plume_box(part)
        if plume is not None:
            lo, hi = plume
            if any(lo[k] < b[k] - 1e-4 or hi[k] > b[3 + k] + 1e-4 for k in range(3)):
                f.add("contract.plume_bounds", "%s plume %s-%s is not inside the header bounds" % (
                    w, tuple(round(x, 3) for x in lo), tuple(round(x, 3) for x in hi)))
    m["particles"] = parts

    # every vertex inside the bounds; radius
    if verts:
        c = [(b[k] + b[3 + k]) / 2 for k in range(3)]
        far = 0.0
        for p, _n, _u0, _u1 in verts:
            if any(p[k] < b[k] - 1e-4 or p[k] > b[3 + k] + 1e-4 for k in range(3)):
                f.add("contract.bounds", "vertex %s outside the header bounds" % (p,))
                break
            far = max(far, math.sqrt(sum((p[k] - c[k]) ** 2 for k in range(3))))
        if b[6] + 1e-4 < far:
            f.add("contract.bounds_radius", "bounding radius %.4f < %.4f (farthest vertex from the box centre)" % (
                b[6], far))
        for i, s in enumerate(seqs):
            if any(abs(s["bounds"][k] - b[k]) > 1e-5 for k in range(7)):
                f.add("contract.sequence_bounds", "sequence %d bounds differ from the header bounds" % i)

    # skin
    if skin is None:
        f.add("client.skin_missing", "no %s00.skin: LoadSkinProfile fails (M2Shared.cpp:1609-1617)" % (
            os.path.splitext(path or "model")[0]))
        return m, f
    sk, sf = parse_skin(skin)
    f.items.extend(sf.items)
    m["skin"] = sk
    if not sk.get("ok"):
        return m, f
    _check_skin(f, m, sk)
    return m, f


def _first_key(data, off, vsize):
    tcn, tof = _arr(data, off + 4)
    kcn, kof = _arr(data, off + 12)
    if tcn < 1 or kcn < 1:
        return None
    ic, io = _arr(data, kof)
    if ic < 1 or io + vsize > len(data):
        return None
    if vsize == 4:
        return struct.unpack_from("<f", data, io)[0]
    if vsize == 1:
        return data[io]
    return data[io:io + vsize]


def plume_box(part):
    """Section 5.2.7: a rising emitter reaches speed*life*(1+variation) + 1/2|gravity|life^2 + max scale above
    its position and its birth scale below it; a sinking one falls 1/2 gravity life^2 + max scale. Sideways:
    the largest scale plus speed*life*(1+variation)*sin(latitude)."""
    t = part["tracks"]
    if t.get("speed") is None or t.get("life") is None:
        return None
    speed, life = t["speed"], t["life"]
    var = t.get("variation") or 0.0
    grav = t.get("gravity") or 0.0
    lat = t.get("latitude") or 0.0
    scales = part["partTracks"]["scale"]["values"]
    smax = max([max(s) for s in scales] or [0.0])
    sbirth = max(scales[0]) if scales else 0.0
    x, y, z = part["position"]
    side = smax + speed * life * (1 + var) * math.sin(min(abs(lat), math.pi / 2))
    if grav <= 0:
        up = speed * life * (1 + var) + 0.5 * abs(grav) * life * life + smax
        return ((x - side, y - side, z - sbirth), (x + side, y + side, z + up))
    drop = 0.5 * grav * life * life + smax
    return ((x - side, y - side, z - drop), (x + side, y + side, z + smax))


def _check_skin(f, m, sk):
    nverts = len(m["vertices"])
    lookup = sk["lookup"]
    for i, v in enumerate(lookup):
        if v >= nverts:
            f.add("client.skin_lookup", "skin vertex %d looks up model vertex %d of %d" % (i, v, nverts))
            break
    if len(sk["bones"]) != len(lookup):
        f.add("client.skin_bones", "%d skin bone entries for %d skin vertices (one ubyte4 per vertex, read by"
              " SetVertices and InitializeSkinProfile)" % (len(sk["bones"]), len(lookup)))
    if sk["boneCountMax"] < 1:
        f.add("client.bone_count_max", "boneCountMax 0: InitializeSkinProfile computes 0 instances")
    ind = sk["indices"]
    if len(ind) % 3:
        f.add("client.skin_indices", "%d indices is not a triangle list" % len(ind))
    if len(ind) > 65535:
        f.add("contract.skin_indices", "%d indices (more than 65535)" % len(ind))
    secs = sk["sections"]
    nbc = len(m["boneCombos"])
    nbones = m["counts"]["bones"]
    sec_tris = []
    for si, s in enumerate(secs):
        w = "section %d" % si
        if s["id"] >> 16:
            f.add("client.section_level", "%s skinSectionId 0x%X has high bits set: M2SkinSectionIndexStart then "
                  "reads them as a wide index start (M2Modern.cpp:1032-1041)" % (w, s["id"]))
        if s["boneCount"] < 1:
            f.add("client.section_bone_count", "%s boneCount 0: InitializeSkinProfile divides boneCountMax by it "
                  "(M2Shared.cpp:1143)" % w)
        if s["boneInfluences"] > 4:
            f.add("client.section_influences", "%s boneInfluences %d > 4" % (w, s["boneInfluences"]))
        if s["centerBoneIndex"] >= max(1, nbones):
            f.add("client.section_center_bone", "%s centerBoneIndex %d past %d bones: every transparent or fading "
                  "batch is depth sorted through m_boneMatrices[m_centerBoneIndex] with no bound check "
                  "(M2Scene.cpp:1890, 1894; the array holds one matrix per bone, M2Model.cpp:7084)"
                  % (w, s["centerBoneIndex"], nbones))
        vs, vc = s["vertexStart"], s["vertexCount"]
        if vs + vc > len(lookup):
            f.add("client.section_vertices", "%s vertices %d..%d past %d skin vertices" % (w, vs, vs + vc,
                                                                                          len(lookup)))
        is_, ic = s["indexStart"], s["indexCount"]
        if is_ + ic > len(ind):
            f.add("client.section_indices", "%s indices %d..%d past %d" % (w, is_, is_ + ic, len(ind)))
            sec_tris.append(0)
            continue
        if ic % 3:
            f.add("client.section_indices", "%s indexCount %d is not a multiple of 3" % (w, ic))
        bad = [v for v in ind[is_:is_ + ic] if not vs <= v < vs + vc]
        if bad:
            f.add("client.section_index_range", "%s index %d outside its vertex range %d..%d: SetIndices subtracts "
                  "vertexStart (M2Shared.cpp:361-367)" % (w, bad[0], vs, vs + vc - 1))
        for j in range(vs, min(vs + vc, len(sk["bones"]))):
            if max(sk["bones"][j][:max(1, s["boneInfluences"])]) + s["boneComboIndex"] >= max(1, nbc):
                f.add("client.section_bone_combo", "%s skin bone index past the bone combos" % w)
                break
        sec_tris.append(ic // 3)
    m["sectionTriangles"] = sec_tris
    for bi, b in enumerate(sk["batches"]):
        w = "batch %d" % bi
        if b["skinSectionIndex"] >= len(secs):
            f.add("client.batch_section", "%s skinSectionIndex %d past %d sections" % (w, b["skinSectionIndex"],
                                                                                      len(secs)))
        if b["materialIndex"] >= len(m["materials"]):
            f.add("client.batch_material", "%s materialIndex %d past %d materials" % (w, b["materialIndex"],
                                                                                     len(m["materials"])))
        tcount = max(1, b["textureCount"])
        if b["textureComboIndex"] + tcount > len(m["textureCombos"]):
            f.add("client.batch_texture_combo", "%s textureComboIndex %d (+%d) past %d texture combos" % (
                w, b["textureComboIndex"], tcount, len(m["textureCombos"])))
        if b["textureCoordComboIndex"] + tcount > len(m["textureCoordCombos"]):
            f.add("client.batch_coord_combo", "%s textureCoordComboIndex %d past the coord combos" % (
                w, b["textureCoordComboIndex"]))
        if b["textureWeightComboIndex"] + tcount > len(m["textureWeightCombos"]):
            f.add("client.batch_weight_combo", "%s textureWeightComboIndex %d past the weight combos" % (
                w, b["textureWeightComboIndex"]))
        if b["textureTransformComboIndex"] + tcount > len(m["textureTransformCombos"]):
            f.add("client.batch_transform_combo", "%s textureTransformComboIndex %d past the transform combos" % (
                w, b["textureTransformComboIndex"]))
        if b["colorIndex"] != 0xFFFF and b["colorIndex"] >= m["counts"]["colors"]:
            f.add("client.batch_color", "%s colorIndex %d past the colours" % (w, b["colorIndex"]))
        if b["flags"] & (0x04 | 0x08 | 0x40):
            f.add("contract.batch_flags", "%s flags 0x%X (written as 0x10; never 0x04, 0x08 or 0x40)" % (
                w, b["flags"]))
        if b["materialLayer"] != 0 or b["textureCount"] != 1:
            f.add("contract.batch_layers", "%s materialLayer %d textureCount %d (v1 writes one layer, one texture)"
                  % (w, b["materialLayer"], b["textureCount"]))
        if b["shader"] != 0:
            f.add("contract.batch_shader", "%s shader 0x%X (written as 0; the client derives it)" % (w, b["shader"]))
        if b["textureCount"] > 2:
            f.add("client.batch_texture_count", "%s textureCount %d > 2" % (w, b["textureCount"]))


def summary(m, f, parts_map=None):
    """The JSON summary of section 5.3."""
    out = {"ok": not f, "errors": f.items, "name": m.get("name"), "version": m.get("version")}
    if "vertices" not in m:
        return out
    tris = sum(m.get("sectionTriangles", []))
    out["counts"] = {"vertices": len(m["vertices"]), "triangles": tris,
                     "sections": len(m.get("skin", {}).get("sections", [])),
                     "batches": len(m.get("skin", {}).get("batches", [])), "textures": len(m["textures"]),
                     "materials": len(m["materials"]), "particles": len(m["particles"]),
                     "collisionTriangles": len(m["collision"]["normals"])}
    out["bounds"] = m["bounds"]
    out["collisionBounds"] = m["collisionBounds"]
    out["textures"] = [t["path"] for t in m["textures"]]
    secs = []
    sk = m.get("skin", {})
    for si, s in enumerate(sk.get("sections", [])):
        bat = [b for b in sk.get("batches", []) if b["skinSectionIndex"] == si]
        entry = {"section": si, "geoset": s["id"] & 0xFFFF, "triangles": s["indexCount"] // 3}
        if bat:
            b = bat[0]
            mat = m["materials"][b["materialIndex"]] if b["materialIndex"] < len(m["materials"]) else {}
            combo = b["textureComboIndex"]
            tex = m["textureCombos"][combo] if combo < len(m["textureCombos"]) else None
            entry.update({"blend": mat.get("blend"), "materialFlags": mat.get("flags"),
                          "texture": m["textures"][tex]["path"] if tex is not None and tex < len(m["textures"])
                          else None, "env": b["textureCoordComboIndex"] == 1})
        secs.append(entry)
    out["sections"] = secs
    if parts_map:
        parts = {}
        for name, ranges in parts_map.items():
            n = 0
            for si, first, count in ranges:
                if si < len(sk.get("sections", [])) and first + count <= sk["sections"][si]["indexCount"] // 3:
                    n += count
                else:
                    f.add("contract.parts_map", "part %s range (%d, %d, %d) outside its section" % (name, si, first,
                                                                                                 count))
            parts[name] = n
        out["parts"] = parts
        out["ok"] = not f
        out["errors"] = f.items
    return out


def crosscheck(path, data, m):
    """Agreement with Tools/MapForge/terrain/extra_assets.py:m2_dependencies and assets.py:m2_bounds."""
    out = {"available": False, "problems": []}
    try:
        from terrain import assets as A  # noqa: WPS433
        from terrain import extra_assets as E  # noqa: WPS433
    except Exception as e:  # pragma: no cover - MapForge missing
        out["problems"].append("MapForge not importable: %s" % e)
        return out
    out["available"] = True
    client = path.replace("/", "\\")
    deps = E.m2_dependencies(client, data)
    base = client[:-3]
    if deps["skins"] != [base + "00.skin"]:
        out["problems"].append("m2_dependencies skins %r" % deps["skins"])
    want = [t["path"] for t in m["textures"] if t["type"] == 0 and t["path"]]
    if deps["textures"] != want:
        out["problems"].append("m2_dependencies textures %r != %r" % (deps["textures"], want))
    if deps["anims"]:
        out["problems"].append("m2_dependencies wants .anim files %r" % deps["anims"])
    if deps["collision"] != bool(m["collision"]["indices"]):
        out["problems"].append("m2_dependencies collision %r" % deps["collision"])
    if deps["version"] != 264:
        out["problems"].append("m2_dependencies version %r" % deps["version"])
    bb = A.m2_bounds(data)
    if bb is None or any(abs(bb[0][k] - m["bounds"]["min"][k]) > 1e-6 or abs(bb[1][k] - m["bounds"]["max"][k]) > 1e-6
                         for k in range(3)):
        out["problems"].append("m2_bounds %r != header bounds" % (bb,))
    return out


def check_files(m2_path, parts_map=None, client_path=None):
    with open(m2_path, "rb") as fh:
        data = fh.read()
    skin_path = os.path.splitext(m2_path)[0] + "00.skin"
    skin = None
    if os.path.exists(skin_path):
        with open(skin_path, "rb") as fh:
            skin = fh.read()
    m, f = parse(data, skin, m2_path)
    s = summary(m, f, parts_map)
    if "vertices" in m and client_path:
        cc = crosscheck(client_path, data, m)
        s["crosscheck"] = cc
        for p in cc["problems"]:
            if cc["available"]:
                f.add("contract.crosscheck", p)
        s["ok"] = not f
        s["errors"] = f.items
    return m, f, s


def check_unique_names(models):
    """Section 5.3: file names unique with the BH_Cafe_ prefix. models: [(path, parsed name)]."""
    seen = {}
    problems = []
    for path, name in models:
        base = os.path.splitext(os.path.basename(path))[0]
        if not base.startswith("BH_Cafe_"):
            problems.append("%s: file name lacks the BH_Cafe_ prefix" % path)
        key = base.lower()
        if key in seen:
            problems.append("%s: file name repeats %s" % (path, seen[key]))
        seen[key] = path
        if name and name != base:
            problems.append("%s: internal name %r differs from the file name" % (path, name))
    return problems


def dumps(obj):
    return json.dumps(obj, indent=2, sort_keys=True, default=lambda o: list(o) if isinstance(o, tuple) else str(o))
