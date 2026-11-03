"""MPQ archives for the tests, including the kinds MpqPack does not write: bzip2 sectors, encrypted files (with the
fix-key flag) and sector checksum tables, as third-party tools write them. Made-up contents only."""

from __future__ import annotations

import bz2
import os
import struct
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL_DIR = os.path.dirname(HERE)

if TOOL_DIR not in sys.path:
    sys.path.insert(0, TOOL_DIR)

import dbc  # noqa: E402,F401  (puts Tools/MpqPack on sys.path)

import mpqpack  # noqa: E402

SECTOR = 4096


def _payload(name: str, data: bytes, offset: int, compression: str, encrypt: bool, fix_key: bool,
             sector_crc: bool) -> tuple[bytes, int]:
    flags = mpqpack.FILE_EXISTS
    sectors = [data[i:i + SECTOR] for i in range(0, len(data), SECTOR)] or [b""]

    if compression != "none":
        flags |= mpqpack.FILE_COMPRESS
        packed = []

        for raw in sectors:
            if compression == "bzip2":
                candidate = b"\x10" + bz2.compress(raw)
            else:
                candidate = b"\x02" + zlib.compress(raw)

            packed.append(candidate if len(candidate) < len(raw) else raw)

        sectors = packed

    key = None

    if encrypt:
        flags |= mpqpack.FILE_ENCRYPTED
        key = mpqpack.hash_string(name.split("\\")[-1], mpqpack.HASH_FILE_KEY)

        if fix_key:
            flags |= mpqpack.FILE_FIX_KEY
            key = ((key + offset) ^ len(data)) & 0xFFFFFFFF

    if compression == "none":
        body = b"".join(mpqpack.encrypt_block(s, (key + i) & 0xFFFFFFFF) if key is not None else s
                        for i, s in enumerate(sectors))
        return body, flags

    if sector_crc:
        flags |= mpqpack.FILE_SECTOR_CRC

    entries = len(sectors) + 1 + (1 if sector_crc else 0)
    offsets = [4 * entries]

    for sector in sectors:
        offsets.append(offsets[-1] + len(sector))

    crc_block = b""

    if sector_crc:
        crc_block = b"".join(struct.pack("<I", zlib.adler32(s)) for s in sectors)
        offsets.append(offsets[-1] + len(crc_block))

    table = struct.pack(f"<{entries}I", *offsets)
    body = [mpqpack.encrypt_block(s, (key + i) & 0xFFFFFFFF) if key is not None else s for i, s in enumerate(sectors)]

    if key is not None:
        table = mpqpack.encrypt_block(table, (key - 1) & 0xFFFFFFFF)

    return table + b"".join(body) + crc_block, flags


def build(files: dict[str, bytes], compression: str = "zlib", encrypt: bool = False, fix_key: bool = False,
          sector_crc: bool = False, listfile: bool = True) -> bytes:
    """An MPQ v1 archive holding files, with a (listfile) unless listfile is False."""
    entries = list(files.items())

    if listfile:
        entries.append((mpqpack.LISTFILE, mpqpack.make_listfile([n for n, _ in files.items()])))

    blocks = []
    data = bytearray()
    offset = mpqpack.HEADER_SIZE_V0

    for name, content in entries:
        special = name == mpqpack.LISTFILE
        payload, flags = _payload(name, content, offset, "zlib" if special else compression,
                                  encrypt and not special, fix_key, sector_crc and not special)
        blocks.append((name, offset, len(payload), len(content), flags))
        data += payload
        offset += len(payload)

    header, tables, size = mpqpack._tables(blocks, offset, mpqpack.DEFAULT_SECTOR_SHIFT, None)
    out = header + bytes(data) + tables
    assert len(out) == size
    return out


def write(path: str, files: dict[str, bytes], **options) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)

    with open(path, "wb") as f:
        f.write(build(files, **options))
