"""<Name>00.skin writer (CAFE.SPEC.md section 5.2.4; M2SkinProfile 0x30, M2SkinSection 0x30, M2Batch 0x18).

The client picks profile 0 when the model has one profile (s_skinProfileBoneCounts[3] = 21, M2Shared.cpp:31,
GetSkinProfileIndex), divides boneCountMax by every section's boneCount (InitializeSkinProfile,
M2Shared.cpp:1141-1145: boneCount 0 divides by zero) and reads one ubyte4 of bone indices per skin vertex.
SetIndices (M2Shared.cpp:340-388) subtracts each section's vertexStart from its indices, so indices are absolute
skin-vertex indices that must lie inside their section's vertex range.
"""

import struct

from .m2write import Blob


class Section:
    def __init__(self, geoset, vertex_start, vertex_count, index_start, index_count, center, sort_center,
                 sort_radius):
        self.geoset = geoset
        self.vertex_start = vertex_start
        self.vertex_count = vertex_count
        self.index_start = index_start
        self.index_count = index_count
        self.center = center
        self.sort_center = sort_center
        self.sort_radius = sort_radius
        self.bone_count = 1


class Batch:
    def __init__(self, section, material, texture_combo, coord_combo=0, priority=0):
        self.flags = 0x10
        self.priority = priority
        self.shader = 0
        self.section = section
        self.geoset = section
        self.color = 0xFFFF
        self.material = material
        self.layer = 0
        self.texture_count = 1
        self.texture_combo = texture_combo
        self.coord_combo = coord_combo
        self.weight_combo = 0
        self.transform_combo = 0


class Skin:
    def __init__(self, vertex_count):
        self.lookup = list(range(vertex_count))
        self.indices = []
        self.sections = []
        self.batches = []
        self.bone_count_max = 21


def write_skin(skin):
    blob = Blob(0x30)
    nv = len(skin.lookup)
    look = blob.put(b"".join(struct.pack("<H", v) for v in skin.lookup)) if nv else 0
    ind = blob.put(b"".join(struct.pack("<H", v) for v in skin.indices)) if skin.indices else 0
    bones = blob.put(bytes(4 * nv)) if nv else 0
    sec = bytearray()
    for s in skin.sections:
        sec += struct.pack("<IHHHHHHHH3f3ff", s.geoset & 0xFFFF, s.vertex_start, s.vertex_count, s.index_start,
                           s.index_count, s.bone_count, 0, 1, 0, *s.center, *s.sort_center, s.sort_radius)
    secs = blob.put(bytes(sec)) if skin.sections else 0
    bat = bytearray()
    for b in skin.batches:
        bat += struct.pack("<BbHHHHHHHHHHH", b.flags, b.priority, b.shader, b.section, b.geoset, b.color,
                           b.material, b.layer, b.texture_count, b.texture_combo, b.coord_combo, b.weight_combo,
                           b.transform_combo)
    bats = blob.put(bytes(bat)) if skin.batches else 0
    blob.align()
    head = struct.pack("<4sIIIIIIIIIII", b"SKIN", nv, look, len(skin.indices), ind, nv, bones,
                       len(skin.sections), secs, len(skin.batches), bats, skin.bone_count_max)
    assert len(head) == 0x30
    blob.buf[0:0x30] = head
    return bytes(blob.buf)
