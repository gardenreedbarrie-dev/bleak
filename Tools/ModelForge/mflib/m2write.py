"""Static M2 v264 writer (CAFE.SPEC.md section 5.2.3).

Layouts are Engine/Source/Model2/M2Data.h (sizes checked with g++: M2Data 0x138, M2Sequence 0x40, M2CompBone 0x58,
M2Vertex 0x30, M2Texture 0x10, M2Particle 0x1DC, M2Track 0x14, M2Material 4). Offsets in the file are absolute;
the client's M2Array::Relocate turns them into pointers (M2Data.h:379-386). Every array starts on a 16-byte
boundary, zero padded, and the body starts at 0x140.

Body order: name, sequences, bones, vertices, textures and their names, texture-weight track blocks, materials,
lookups, collision, particles and their track blocks.
"""

import struct

from . import geom as G

HEADER_SIZE = 0x138
BODY_START = 0x140
VERSION = 264
NO_LOOP = 0xFFFF


class Blob:
    def __init__(self, start):
        self.buf = bytearray(start)

    def align(self, a=16):
        pad = (-len(self.buf)) % a
        self.buf += b"\0" * pad

    def put(self, data):
        """Appends data on a 16-byte boundary; returns its absolute offset."""
        self.align()
        off = len(self.buf)
        self.buf += data
        return off

    def patch(self, off, fmt, *vals):
        struct.pack_into(fmt, self.buf, off, *vals)


def arr(count, offset):
    return (count, offset if count else 0)


class Sequence:
    def __init__(self, seq_id=0, variation=0, duration=3000, flags=0x20, frequency=32767, blend_time=150):
        self.id = seq_id
        self.variation = variation
        self.duration = duration
        self.flags = flags
        self.frequency = frequency
        self.blend_time = blend_time
        self.variation_next = 0xFFFF
        self.alias_next = None  # its own index


class Particle:
    """One emitter with single-key tracks (section 5.2.7). Defaults are the wand steam."""

    def __init__(self, position, texture_index):
        self.position = tuple(position)
        self.texture_index = texture_index
        self.flags = 0x20000
        self.blend = 2
        self.emitter_type = 1
        self.rows = 1
        self.cols = 1
        self.priority_plane = 0
        self.speed = 0.35
        self.variation = 0.3
        self.latitude = 0.25
        self.longitude = 3.14159265
        self.gravity = -0.15
        self.life = 1.6
        self.life_variation = 0.3
        self.emission_rate = 14.0
        self.emission_rate_variation = 0.0
        self.width = 0.08
        self.length = 0.08
        self.zsource = 0.0
        self.part_times = (0, 16384, 32767)
        self.colors = ((255.0, 255.0, 255.0),) * 3
        self.alphas = (0, 18000, 0)
        self.scales = ((0.05, 0.05), (0.18, 0.18), (0.32, 0.32))
        self.twinkle_fps = 10.0
        self.twinkle_onoff = 1.0
        self.twinkle_scale = (1.0, 1.0)
        self.write_emission_rate = True  # tests switch keys off to prove the checker catches it

    def validate(self):
        """Refuses part tracks the client cannot sample: colour, alpha and scale each need one value per time
        and at least one (an empty track crashes the first draw, ParticleSystem2.cpp:85-112, 683-684)."""
        for what, vals in (("colour", self.colors), ("alpha", self.alphas), ("scale", self.scales)):
            if not vals or len(vals) != len(self.part_times):
                raise ValueError("particle %s track: %d times and %d values (needs one value per time, at least "
                                 "one)" % (what, len(self.part_times), len(vals)))

    def plume_height(self):
        """Section 5.2.7: speed*life*(1 + variation) + 1/2 |gravity| life^2 + max scale above the emitter."""
        smax = max(max(s) for s in self.scales)
        return self.speed * self.life * (1 + self.variation) + 0.5 * abs(self.gravity) * self.life ** 2 + smax

    def plume_box(self):
        """The volume the particles can reach: the section 5.2.7 height above the emitter, the birth scale
        below it (or the fall of a sinking emitter), sideways the spread plus the largest scale."""
        import math
        smax = max(max(s) for s in self.scales)
        s0 = max(self.scales[0])
        x, y, z = self.position
        side = smax + self.speed * self.life * (1 + self.variation) * math.sin(min(abs(self.latitude), math.pi / 2))
        if self.gravity <= 0:
            return ((x - side, y - side, z - s0), (x + side, y + side, z + self.plume_height()))
        drop = 0.5 * self.gravity * self.life ** 2 + smax
        return ((x - side, y - side, z - drop), (x + side, y + side, z + smax))


class M2Model:
    """Everything the writer needs. vertices: [(pos, normal, uv)] in skin order (the skin's lookup is the
    identity). textures: [(client path, flags)]. materials: [(flags, blend)]."""

    def __init__(self, name):
        self.name = name
        self.global_flags = 0
        self.sequences = [Sequence()]
        self.vertices = []
        self.textures = []
        self.materials = []
        self.texture_combos = None      # default [0..T-1]
        self.coord_combos = [0, 0xFFFF]
        self.collision_positions = []
        self.collision_tris = []
        self.collision_normals = []
        self.particles = []
        self.bounds = None              # (min, max, radius); computed when None
        self.collision_bounds = None
        self.sequence_hash = []          # must stay empty (count 1 with [0] loops forever)
        self.texture_weight = 0x7FFF

    # ------------------------------------------------------------------------------------- derived values
    def compute_bounds(self):
        pts = [v[0] for v in self.vertices]
        for p in self.particles:
            lo, hi = p.plume_box()
            pts.append(lo)
            pts.append(hi)
        if not pts:
            return ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), 0.0)
        lo = tuple(min(p[i] for p in pts) for i in range(3))
        hi = tuple(max(p[i] for p in pts) for i in range(3))
        c = tuple((lo[i] + hi[i]) / 2 for i in range(3))
        r = max(G.length(G.sub(p, c)) for p in pts)
        return (lo, hi, r)

    def compute_collision_bounds(self):
        pts = self.collision_positions
        if not pts:
            return ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), 0.0)
        lo = tuple(min(p[i] for p in pts) for i in range(3))
        hi = tuple(max(p[i] for p in pts) for i in range(3))
        c = tuple((lo[i] + hi[i]) / 2 for i in range(3))
        r = max(G.length(G.sub(p, c)) for p in pts)
        return (lo, hi, r)


def _bounds_bytes(b):
    lo, hi, r = b
    return struct.pack("<7f", lo[0], lo[1], lo[2], hi[0], hi[1], hi[2], r)


def _track(blob, fmt, values, nseq):
    """A track with one key per sequence: returns the 0x14-byte M2Track (interpolation 0, loop 0xFFFF).
    values: one value (a tuple for struct) used for every sequence, or None for an empty track."""
    if values is None:
        return struct.pack("<HHIIII", 0, NO_LOOP, 0, 0, 0, 0)
    times = []
    keys = []
    for _ in range(nseq):
        times.append(blob.put(struct.pack("<I", 0)))
        keys.append(blob.put(struct.pack("<" + fmt, *values)))
    t_outer = blob.put(b"".join(struct.pack("<II", 1, o) for o in times))
    k_outer = blob.put(b"".join(struct.pack("<II", 1, o) for o in keys))
    return struct.pack("<HHIIII", 0, NO_LOOP, nseq, t_outer, nseq, k_outer)


def _part_track(blob, fmt, times, values, what):
    """A colour, alpha or scale part track: one value per time. The client samples these three for every
    particle, and an empty one makes PartTrackSearch read times[0x7FFFFFFF] (ParticleSystem2.cpp:85-112), so an
    empty or mismatched track is refused here rather than written."""
    if not values or len(values) != len(times):
        raise ValueError("particle %s track: %d times and %d values (needs one value per time, at least one)"
                         % (what, len(times), len(values)))
    t = blob.put(b"".join(struct.pack("<h", v) for v in times))
    v = blob.put(b"".join(struct.pack("<" + fmt, *(val if isinstance(val, tuple) else (val,))) for val in values))
    return struct.pack("<IIII", len(times), t, len(values), v)


def _particle(blob, p, nseq):
    tr = lambda fmt, v: _track(blob, fmt, v, nseq)  # noqa: E731
    speed = tr("f", (p.speed,))
    variation = tr("f", (p.variation,))
    latitude = tr("f", (p.latitude,))
    longitude = tr("f", (p.longitude,))
    gravity = tr("f", (p.gravity,))
    life = tr("f", (p.life,))
    rate = tr("f", (p.emission_rate,)) if p.write_emission_rate else tr("f", None)
    width = tr("f", (p.width,))
    length = tr("f", (p.length,))
    zsource = tr("f", (p.zsource,))
    color = _part_track(blob, "3f", p.part_times, list(p.colors), "colour")
    alpha = _part_track(blob, "h", p.part_times, list(p.alphas), "alpha")
    scale = _part_track(blob, "2f", p.part_times, list(p.scales), "scale")
    out = bytearray()
    out += struct.pack("<II3fHH", 0xFFFFFFFF, p.flags, *p.position, 0, p.texture_index)
    out += struct.pack("<IIII", 0, 0, 0, 0)               # geometryMdl, recursionMdl
    out += struct.pack("<BBHHhHH", p.blend, p.emitter_type, 0, 0, p.priority_plane, p.rows, p.cols)
    out += speed + variation + latitude + longitude + gravity + life
    out += struct.pack("<f", p.life_variation)
    out += rate
    out += struct.pack("<f", p.emission_rate_variation)
    out += width + length + zsource
    out += color + alpha + scale
    out += struct.pack("<2f", 0.0, 0.0)                    # scaleVariation
    out += struct.pack("<IIII", 0, 0, 0, 0)                # headCellTrack
    out += struct.pack("<IIII", 0, 0, 0, 0)                # tailCellTrack
    out += struct.pack("<f", 0.0)                          # tailLength
    out += struct.pack("<fff", p.twinkle_fps, p.twinkle_onoff, p.twinkle_scale[0])
    out += struct.pack("<f", p.twinkle_scale[1])
    out += struct.pack("<6f", 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)  # ivelScale, drag, spins
    out += struct.pack("<6f", 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)  # tumble
    out += struct.pack("<3f", 0.0, 0.0, 0.0)                 # windVector
    out += struct.pack("<5f", 0.0, 0.0, 0.0, 0.0, 0.0)       # windTime, follow
    out += struct.pack("<II", 0, 0)                          # spline
    out += _track(blob, "B", None, nseq)                    # visibility: empty (InitializeLoaded sets 1)
    assert len(out) == 0x1DC, hex(len(out))
    return bytes(out)


def write_m2(model):
    """Returns the .m2 file bytes."""
    nseq = len(model.sequences)
    for p in model.particles:
        p.validate()
    bounds = model.bounds or model.compute_bounds()
    cbounds = model.collision_bounds or model.compute_collision_bounds()
    blob = Blob(BODY_START)
    hdr = {}

    name = model.name.encode("ascii") + b"\0"
    hdr["name"] = arr(len(name), blob.put(name))

    seqs = bytearray()
    for i, s in enumerate(model.sequences):
        alias = i if s.alias_next is None else s.alias_next
        seqs += struct.pack("<HHIfIIiiI", s.id, s.variation, s.duration, 0.0, s.flags, s.frequency, 0, 0,
                            s.blend_time)
        seqs += _bounds_bytes(bounds)
        seqs += struct.pack("<HH", s.variation_next, alias)
    hdr["sequences"] = arr(nseq, blob.put(bytes(seqs)))
    if model.sequence_hash:
        hdr["seqhash"] = arr(len(model.sequence_hash),
                             blob.put(b"".join(struct.pack("<H", v) for v in model.sequence_hash)))
    else:
        hdr["seqhash"] = (0, 0)

    empty = struct.pack("<HHIIII", 0, NO_LOOP, 0, 0, 0, 0)
    bone = struct.pack("<IIHHI", 0xFFFFFFFF, 0, 0xFFFF, 0, 0) + empty * 3 + struct.pack("<3f", 0.0, 0.0, 0.0)
    assert len(bone) == 0x58
    hdr["bones"] = arr(1, blob.put(bone))

    vb = bytearray()
    for pos, nrm, uv in model.vertices:
        vb += struct.pack("<3f4B4B3f2f2f", pos[0], pos[1], pos[2], 255, 0, 0, 0, 0, 0, 0, 0,
                          nrm[0], nrm[1], nrm[2], uv[0], uv[1], uv[0], uv[1])
    hdr["vertices"] = arr(len(model.vertices), blob.put(bytes(vb)))

    # textures: the table, then each name
    tex_tab_off = blob.put(bytes(0x10 * len(model.textures))) if model.textures else 0
    for i, (path, flags) in enumerate(model.textures):
        fn = path.replace("/", "\\").encode("ascii") + b"\0"
        noff = blob.put(fn)
        blob.patch(tex_tab_off + 0x10 * i, "<IIII", 0, flags, len(fn), noff)
    hdr["textures"] = arr(len(model.textures), tex_tab_off)

    tw = _track(blob, "h", (model.texture_weight,), nseq) if model.texture_weight is not None else None
    hdr["texweights"] = arr(1, blob.put(tw)) if tw is not None else (0, 0)

    mats = b"".join(struct.pack("<HH", f, b) for f, b in model.materials)
    hdr["materials"] = arr(len(model.materials), blob.put(mats))

    def u16s(vals):
        return b"".join(struct.pack("<H", v) for v in vals)

    combos = model.texture_combos if model.texture_combos is not None else list(range(len(model.textures)))
    hdr["bonecombos"] = arr(1, blob.put(u16s([0])))
    hdr["texcombos"] = arr(len(combos), blob.put(u16s(combos)))
    hdr["coordcombos"] = arr(len(model.coord_combos), blob.put(u16s(model.coord_combos)))
    hdr["weightcombos"] = arr(1, blob.put(u16s([0])))
    hdr["transformcombos"] = arr(1, blob.put(u16s([0xFFFF])))

    if model.collision_tris:
        idx = b"".join(struct.pack("<3H", *t) for t in model.collision_tris)
        hdr["cindices"] = arr(3 * len(model.collision_tris), blob.put(idx))
        hdr["cpositions"] = arr(len(model.collision_positions),
                                blob.put(b"".join(struct.pack("<3f", *p) for p in model.collision_positions)))
        hdr["cnormals"] = arr(len(model.collision_normals),
                              blob.put(b"".join(struct.pack("<3f", *n) for n in model.collision_normals)))
    else:
        hdr["cindices"] = hdr["cpositions"] = hdr["cnormals"] = (0, 0)

    if model.particles:
        tab = blob.put(bytes(0x1DC * len(model.particles)))
        for i, p in enumerate(model.particles):
            body = _particle(blob, p, nseq)
            blob.buf[tab + 0x1DC * i: tab + 0x1DC * (i + 1)] = body
        hdr["particles"] = arr(len(model.particles), tab)
    else:
        hdr["particles"] = (0, 0)
    blob.align()

    h = bytearray(HEADER_SIZE)
    struct.pack_into("<4sI", h, 0, b"MD20", VERSION)
    struct.pack_into("<II", h, 0x08, *hdr["name"])
    struct.pack_into("<I", h, 0x10, model.global_flags)
    struct.pack_into("<II", h, 0x14, 0, 0)                   # loops
    struct.pack_into("<II", h, 0x1C, *hdr["sequences"])
    struct.pack_into("<II", h, 0x24, *hdr["seqhash"])
    struct.pack_into("<II", h, 0x2C, *hdr["bones"])
    struct.pack_into("<II", h, 0x34, 0, 0)                   # boneIndicesById
    struct.pack_into("<II", h, 0x3C, *hdr["vertices"])
    struct.pack_into("<I", h, 0x44, 1)                       # numSkinProfiles
    struct.pack_into("<II", h, 0x48, 0, 0)                   # colors
    struct.pack_into("<II", h, 0x50, *hdr["textures"])
    struct.pack_into("<II", h, 0x58, *hdr["texweights"])
    struct.pack_into("<II", h, 0x60, 0, 0)                   # textureTransforms
    struct.pack_into("<II", h, 0x68, 0, 0)                   # replaceable texture lookup
    struct.pack_into("<II", h, 0x70, *hdr["materials"])
    struct.pack_into("<II", h, 0x78, *hdr["bonecombos"])
    struct.pack_into("<II", h, 0x80, *hdr["texcombos"])
    struct.pack_into("<II", h, 0x88, *hdr["coordcombos"])
    struct.pack_into("<II", h, 0x90, *hdr["weightcombos"])
    struct.pack_into("<II", h, 0x98, *hdr["transformcombos"])
    h[0xA0:0xBC] = _bounds_bytes(bounds)
    h[0xBC:0xD8] = _bounds_bytes(cbounds)
    struct.pack_into("<II", h, 0xD8, *hdr["cindices"])
    struct.pack_into("<II", h, 0xE0, *hdr["cpositions"])
    struct.pack_into("<II", h, 0xE8, *hdr["cnormals"])
    # attachments .. ribbons empty
    struct.pack_into("<II", h, 0x128, *hdr["particles"])
    struct.pack_into("<II", h, 0x130, 0, 0)                  # textureCombinerCombos (flag 0x8 never set)
    blob.buf[0:HEADER_SIZE] = h
    return bytes(blob.buf)
