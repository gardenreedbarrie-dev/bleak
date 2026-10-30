"""The dance pack file Bleakhold.exe reads (Interface\\Bleakhold\\Dances\\Dances.bdc; Engine/Source/Model2/BleakDance.h).

    char magic[4] "BHDC", uint16 version 1, uint16 joint count 22, uint16 clip count, uint16 0
    clip count entries of 24 bytes: uint16 id, flags, frame count, fps, bpm * 100, key length,
                                    uint32 key offset, data offset, data size (from the start of the file)
    the keys (ASCII, no terminator), then each clip's frames: int16 hips x, y, z (* 8192) and int16 x, y, z, w of
    every joint's world rotation (* 32767). Little-endian.
"""

import re
import struct

from . import quat as Q
from . import skeleton as S

MAGIC = b"BHDC"
VERSION = 1
FLAG_LOOP = 1
MAX_ID = 1023
MAX_FRAMES = 8192
HIPS_SCALE = 8192.0
QUAT_SCALE = 32767.0
KEY_RE = re.compile(r"^[a-z0-9_]{1,32}$")
VALUES_PER_FRAME = 3 + S.COUNT * 4


def _i16(v, scale):
    n = int(round(v * scale))
    return max(-32767, min(32767, n))


def encode_frames(frames):
    out = bytearray()
    prev = None
    for hips, rots in frames:
        out += struct.pack("<3h", *(_i16(c, HIPS_SCALE) for c in hips))
        cur = []
        for j, q in enumerate(rots):
            q = Q.qnormalize(q)
            # keep neighbouring frames in the same hemisphere so a reader's lerp never takes the long way
            if prev is not None and Q.qdot(prev[j], q) < 0.0:
                q = (-q[0], -q[1], -q[2], -q[3])
            elif prev is None and q[3] < 0.0:
                q = (-q[0], -q[1], -q[2], -q[3])
            cur.append(q)
            out += struct.pack("<4h", *(_i16(c, QUAT_SCALE) for c in q))
        prev = cur
    return bytes(out)


def write(clips):
    """clips: [(id, key, fps, bpm, frames, loops)] -> bytes of a pack."""
    ids = set()
    for cid, key, fps, bpm, frames, loops in clips:
        if not 0 <= cid <= MAX_ID or cid in ids:
            raise ValueError("bad or repeated clip id %r" % cid)
        ids.add(cid)
        if not KEY_RE.match(key):
            raise ValueError("bad clip key %r" % key)
        if not 1 <= fps <= 120 or not 2 <= len(frames) <= MAX_FRAMES:
            raise ValueError("clip %s: bad fps or frame count" % key)
    header = struct.pack("<4sHHHH", MAGIC, VERSION, S.COUNT, len(clips), 0)
    table_size = 24 * len(clips)
    keys = b"".join(k.encode("ascii") for _, k, _, _, _, _ in clips)
    data_start = len(header) + table_size + len(keys)
    data_start += data_start & 1
    entries = []
    blobs = []
    key_off = len(header) + table_size
    data_off = data_start
    for cid, key, fps, bpm, frames, loops in clips:
        blob = encode_frames(frames)
        entries.append(struct.pack("<6H3I", cid, FLAG_LOOP if loops else 0, len(frames), fps,
                                   int(round(bpm * 100)), len(key), key_off, data_off, len(blob)))
        key_off += len(key)
        data_off += len(blob)
        blobs.append(blob)
    out = header + b"".join(entries) + keys
    out += b"\0" * (data_start - len(out))
    return out + b"".join(blobs)


def read(data):
    """-> [dict(id, key, flags, fps, bpm, frames=[(hips, rotations)])]; raises ValueError on a bad pack."""
    if len(data) < 12 or data[:4] != MAGIC:
        raise ValueError("not a dance pack")
    magic, version, joints, count, _ = struct.unpack_from("<4sHHHH", data, 0)
    if version != VERSION or joints != S.COUNT:
        raise ValueError("unsupported pack")
    out = []
    for i in range(count):
        cid, flags, nframes, fps, bpm100, klen, koff, doff, dsize = struct.unpack_from("<6H3I", data, 12 + 24 * i)
        if dsize != nframes * VALUES_PER_FRAME * 2 or doff + dsize > len(data) or koff + klen > len(data):
            raise ValueError("bad clip entry")
        key = data[koff:koff + klen].decode("ascii")
        values = struct.unpack_from("<%dh" % (nframes * VALUES_PER_FRAME), data, doff)
        frames = []
        for f in range(nframes):
            v = values[f * VALUES_PER_FRAME:(f + 1) * VALUES_PER_FRAME]
            hips = tuple(x / HIPS_SCALE for x in v[:3])
            rots = [Q.qnormalize(tuple(x / QUAT_SCALE for x in v[3 + 4 * j:7 + 4 * j])) for j in range(S.COUNT)]
            frames.append((hips, rots))
        out.append(dict(id=cid, key=key, flags=flags, fps=fps, bpm=bpm100 / 100.0, frames=frames))
    return out
