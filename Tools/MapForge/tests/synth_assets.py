"""Made-up model and texture files for the extra-asset tests: just enough of an M2 header (MD20, version 264, the
layout in ThirdParty/WarcraftXL/include/structure/m2/M2Format.hpp) and a BLP magic for resolve-assets to read.
No game data."""

from __future__ import annotations

import os
import struct

HEADER = 0x130


def m2(textures=(), skins: int = 1, sequences=(), collision: int = 0, version: int = 264,
       bounds=((-1.0, -1.0, 0.0), (1.0, 1.0, 4.0))) -> bytes:
    """An MD20 model naming `textures` (type 0 file names), with `skins` skin profiles and `sequences` given as
    (id, variation, flags) records."""
    data = bytearray(HEADER)
    data[0:4] = b"MD20"
    struct.pack_into("<I", data, 0x04, version)
    seq_ofs = len(data)
    for seq_id, variation, flags in sequences:
        rec = bytearray(0x40)
        struct.pack_into("<HH", rec, 0, seq_id, variation)
        struct.pack_into("<I", rec, 0x0C, flags)
        data += rec
    struct.pack_into("<II", data, 0x1C, len(sequences), seq_ofs if sequences else 0)
    struct.pack_into("<I", data, 0x44, skins)
    tex_ofs = len(data)
    data += bytes(16 * len(textures))
    for i, name in enumerate(textures):
        raw = name.encode("ascii") + b"\0"
        struct.pack_into("<IIII", data, tex_ofs + 16 * i, 0, 0, len(raw), len(data))
        data += raw
    struct.pack_into("<II", data, 0x50, len(textures), tex_ofs if textures else 0)
    struct.pack_into("<6f", data, 0xA0, *bounds[0], *bounds[1])
    struct.pack_into("<I", data, 0xD8, collision)
    return bytes(data)


def md21(inner: bytes, chunks: dict[str, bytes] | None = None) -> bytes:
    """A chunked (MD21) file around an MD20 block, with further chunks after it."""
    out = b"MD21" + struct.pack("<I", len(inner)) + inner
    for magic, payload in (chunks or {}).items():
        out += magic.encode("ascii") + struct.pack("<I", len(payload)) + payload
    return out


def m2_fdid(skins: int = 1) -> bytes:
    """A chunked (MD21, version 274) model whose skins are named by FileDataID (an SFID chunk)."""
    sfid = struct.pack(f"<{skins}I", *range(4000000, 4000000 + skins))
    return md21(m2(skins=skins, version=274), {"SFID": sfid})


def blp() -> bytes:
    return b"BLP2" + bytes(144)


def write(root: str, files: dict[str, bytes]) -> None:
    """Loose files under root at their client paths."""
    for path, data in files.items():
        full = os.path.join(root, *path.split("\\"))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as f:
            f.write(data)
