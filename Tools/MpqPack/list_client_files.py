#!/usr/bin/env python3
"""Dump WMO (and optionally any) file paths from the retail WoW 3.3.5a MPQs.

MpqPack's reader refuses Blizzard's archives because their files carry a sector-CRC block: the sector offset
table then has one EXTRA entry (pointing at a trailing CRC sector), so offsets[0] is table_size + 4 and
read_block raises "sector CRCs are not supported". This script patches read_block at runtime to accept that
layout (and to skip the trailing CRC sector); it also accepts bzip2 and stored sectors, which Blizzard mixes in.

Nothing in the repository is modified.

Usage:
    python3 -I list_client_wmos.py /srv/bleakhold-launcher/base/Data            # WMO roots only
    python3 -I list_client_wmos.py /srv/bleakhold-launcher/base/Data --all      # every listed path
    python3 -I list_client_wmos.py /srv/bleakhold-launcher/base/Data --grep onyx
"""

from __future__ import annotations

import argparse
import bz2
import os
import re
import struct
import sys
import zlib

MPQPACK_DIR = os.environ.get("MPQPACK_DIR", os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, MPQPACK_DIR)

try:
    import mpqpack  # noqa: E402
except Exception as exc:  # pragma: no cover - environment specific
    sys.exit(f"could not import mpqpack from {MPQPACK_DIR}: {exc}\nSet MPQPACK_DIR to the folder holding mpqpack.py")

MpqError = mpqpack.MpqError

COMPRESSION_ZLIB = 0x02
COMPRESSION_BZIP2 = 0x10


def _decompress(chunk: bytes, expected: int, where: str) -> bytes:
    """One compressed unit. Blizzard mixes zlib and bzip2; a chunk already at size is stored as-is."""
    if not chunk:
        raise MpqError(f"{where}: empty compressed unit")

    mask = chunk[0]
    body = chunk[1:]

    if mask == COMPRESSION_ZLIB:
        data = zlib.decompress(body)
    elif mask == COMPRESSION_BZIP2:
        data = bz2.decompress(body)
    else:
        raise MpqError(f"{where}: compression 0x{mask:02X} not supported by this script (zlib 0x02, bzip2 0x10)")

    if len(data) != expected:
        raise MpqError(f"{where}: decompressed to {len(data)} instead of {expected}")
    return data


def read_block_crc_tolerant(self, block_index: int, name: str = "") -> bytes:
    block = self.blocks[block_index]
    where = name or f"block {block_index}"

    if not block.flags & mpqpack.FILE_EXISTS:
        raise MpqError(f"{where}: block is not marked FILE_EXISTS")
    if block.flags & mpqpack.FILE_DELETE_MARKER:
        raise MpqError(f"{where}: is a delete marker")

    stored = self.data[block.offset:block.offset + block.compressed_size]
    if len(stored) != block.compressed_size or block.offset + block.compressed_size > self.archive_end:
        raise MpqError(f"{where}: data runs past the end of the archive")

    if not block.flags & 0xFFF00:
        return stored
    if block.flags & (mpqpack.FILE_ENCRYPTED | mpqpack.FILE_FIX_KEY):
        raise MpqError(f"{where}: encrypted files are not supported")
    if block.file_size == 0:
        return b""

    if block.flags & mpqpack.FILE_SINGLE_UNIT:
        if block.compressed_size == block.file_size:
            return stored
        return _decompress(stored, block.file_size, where)

    sector_count = (block.file_size + self.sector_size - 1) // self.sector_size
    plain_table = 4 * (sector_count + 1)
    crc_table = 4 * (sector_count + 2)

    if len(stored) < plain_table:
        raise MpqError(f"{where}: sector table is cut off")

    first = struct.unpack_from("<I", stored)[0]
    # A sector-CRC file has one extra offset entry; the data then starts at crc_table.
    entries = sector_count + 2 if first == crc_table else sector_count + 1
    offsets = struct.unpack_from(f"<{entries}I", stored)

    if offsets[0] not in (plain_table, crc_table):
        raise MpqError(f"{where}: first sector offset {offsets[0]} is neither {plain_table} nor {crc_table}")

    out = bytearray()
    last_size = block.file_size % self.sector_size or self.sector_size

    for i in range(sector_count):  # the trailing CRC sector, if any, is simply not read
        expected = last_size if i == sector_count - 1 else self.sector_size
        chunk = stored[offsets[i]:offsets[i + 1]]
        out += chunk if len(chunk) == expected else _decompress(chunk, expected, f"{where} sector {i}")

    return bytes(out)


mpqpack.MpqArchive.read_block = read_block_crc_tolerant


def names_of(path: str) -> list[str]:
    try:
        archive = mpqpack.MpqArchive(path)
    except Exception as exc:
        print(f"  ! {os.path.basename(path)}: cannot open ({exc})", file=sys.stderr)
        return []

    if not archive.has_file(mpqpack.LISTFILE):
        print(f"  ! {os.path.basename(path)}: no (listfile)", file=sys.stderr)
        return []

    try:
        text = archive.read(mpqpack.LISTFILE)
    except Exception as exc:
        print(f"  ! {os.path.basename(path)}: listfile unreadable ({exc})", file=sys.stderr)
        return []

    return [m.group(1).decode("utf-8", "replace") for m in re.finditer(rb"([^\r\n]+)", text)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("data_dir", help="the client's Data folder (holds common.MPQ ...)")
    ap.add_argument("--all", action="store_true", help="print every listed path, not only WMO roots")
    ap.add_argument("--grep", help="case-insensitive substring/regex filter")
    args = ap.parse_args()

    archives = []
    for root, _dirs, files in os.walk(args.data_dir):
        for f in files:
            if f.lower().endswith(".mpq"):
                archives.append(os.path.join(root, f))
    archives.sort()

    if not archives:
        return print(f"no .MPQ under {args.data_dir}") or 2

    group_re = re.compile(r"_\d{3}\.wmo$", re.I)
    pattern = re.compile(args.grep, re.I) if args.grep else None

    found: set[str] = set()
    for path in archives:
        got = names_of(path)
        print(f"{os.path.basename(path):34} {len(got):7} names", file=sys.stderr)
        for n in got:
            if not args.all:
                if not n.lower().endswith(".wmo") or group_re.search(n):
                    continue
            if pattern and not pattern.search(n):
                continue
            found.add(n)

    for n in sorted(found):
        print(n)
    print(f"\n-- {len(found)} path(s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
