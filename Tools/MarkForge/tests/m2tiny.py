"""A minimal M2 v264 + .skin writer for the tests: enough for ModelForge's m2check (which MarkForge reads models with)
to give back the vertices, textures, texture combos, sections and batches of a synthetic model. No bones, no
animation: the files are never meant for the client."""

import struct

import numpy as np

HEADER = 0x138
# (header offset of each M2Array MarkForge needs) - the rest stay empty
OFF = {"name": 0x08, "sequences": 0x1C, "bones": 0x2C, "vertices": 0x3C, "textures": 0x50, "textureWeights": 0x58,
       "materials": 0x70, "boneCombos": 0x78, "textureCombos": 0x80, "textureCoordCombos": 0x88,
       "textureWeightCombos": 0x90, "textureTransformCombos": 0x98}


class Blob:
    def __init__(self, size):
        self.b = bytearray(size)

    def put(self, data):
        while len(self.b) % 16:
            self.b.append(0)
        off = len(self.b)
        self.b += data
        return off

    def arr(self, field, count, data):
        off = self.put(data) if count else 0
        struct.pack_into("<II", self.b, OFF[field], count, off)
        return off


def write(model):
    """(m2 bytes, skin bytes) of a mflib.model.Model: one section and one batch per geoset (type-1 texture), the
    1703 eye quads with a type-0 file texture."""
    b = Blob(HEADER)
    struct.pack_into("<II", b.b, 0, 0x3032444D, 264)
    name = b"MarkForgeTest\0"
    b.arr("name", len(name), name)
    nv = len(model.pos)
    verts = bytearray()
    for p, n, t in zip(model.pos, model.nrm, model.uv):
        nn = np.asarray(n, float)
        nn = nn / (np.linalg.norm(nn) or 1.0)
        verts += struct.pack("<3f4B4B3f2f2f", *p, 255, 0, 0, 0, 0, 0, 0, 0, *nn, t[0], t[1], 0.0, 0.0)
    b.arr("vertices", nv, bytes(verts))
    eye = (model.eye_texture or "Character\\Test\\deathKnightEyeGlow.blp").encode("ascii") + b"\0"
    # textures: 0 the character skin (type 1), 1 the eye glow file (type 0)
    tex_hdr_size = 2 * 0x10
    tex_off = b.put(bytes(tex_hdr_size))
    name_off = b.put(eye)
    struct.pack_into("<IIII", b.b, tex_off, 1, 0, 0, 0)
    struct.pack_into("<IIII", b.b, tex_off + 0x10, 0, 0, len(eye), name_off)
    struct.pack_into("<II", b.b, OFF["textures"], 2, tex_off)
    b.arr("materials", 2, struct.pack("<HHHH", 0, 0, 0x11, 4))
    b.arr("textureCombos", 2, struct.pack("<HH", 0, 1))
    b.arr("boneCombos", 1, struct.pack("<H", 0))
    b.arr("textureCoordCombos", 1, struct.pack("<H", 0))
    b.arr("textureWeightCombos", 1, struct.pack("<H", 0))
    b.arr("textureTransformCombos", 1, struct.pack("<H", 0xFFFF))
    m2 = bytes(b.b)

    # skin
    groups = [(g, t) for g, t in sorted(model.skin_tris.items())] + [(g, t) for g, t in sorted(model.eye_tris.items())]
    indices = []
    sections, batches = [], []
    for si, (g, t) in enumerate(groups):
        start = len(indices)
        flat = [int(v) for v in np.asarray(t).reshape(-1)]
        indices += flat
        if start > 0xFFFF:
            raise ValueError("too many indices for a 16-bit indexStart: use a coarser tube body")
        sections.append(struct.pack("<IHHHHHHHH3f3ff", g, 0, nv, start, len(flat), 1, 0, 1, 0, 0, 0, 0, 0, 0, 0, 1.0))
        eye_batch = g in (1702, 1703)
        batches.append(struct.pack("<BbHHHHHHHHHHH", 0, 0, 0, si, si, 0xFFFF, 1 if eye_batch else 0, 0, 1,
                                   1 if eye_batch else 0, 0, 0, 0))
    sk = Blob(0x30)
    sk.b[0:4] = b"SKIN"

    def sarr(off, count, data):
        o = sk.put(data) if count else 0
        struct.pack_into("<II", sk.b, off, count, o)

    sarr(0x04, nv, struct.pack("<%dH" % nv, *range(nv)))
    sarr(0x0C, len(indices), struct.pack("<%dH" % len(indices), *indices))
    sarr(0x14, nv, bytes(4 * nv))
    sarr(0x1C, len(sections), b"".join(sections))
    sarr(0x24, len(batches), b"".join(batches))
    struct.pack_into("<I", sk.b, 0x2C, 1)
    return m2, bytes(sk.b)
