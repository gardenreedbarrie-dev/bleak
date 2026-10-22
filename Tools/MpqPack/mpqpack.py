#!/usr/bin/env python3
"""MpqPack: build MPQ archives that the 3.3.5a client (and this decompilation) loads as patch archives.

    python3 -I mpqpack.py pack <source folder> <out.mpq>
    python3 -I mpqpack.py list <archive.mpq>
    python3 -I mpqpack.py extract <archive.mpq> <out folder>
    python3 -I mpqpack.py verify <archive.mpq> [<source folder>]
    python3 -I mpqpack.py selftest

Only the Python standard library is used. Archive paths are the paths relative to the source folder, written with
backslashes (DBFilesClient\\ChrRaces.dbc). Files are stored uncompressed or zlib-compressed.

The layout follows what the client's reader in Engine/Source/BlizzardCore/Source/Packages/Mopaq checks:

- format version 0 with a 32-byte header at offset 0 (s_OpenArchive accepts version 0 only with m_headerSize 32);
- the hash table directly in front of the block table, and the block table last: InitializeTables takes the disk size
  of the hash table as blockTablePos - hashTablePos and that of the block table as archiveEnd - blockTablePos, and
  treats either as compressed when it differs from 16 bytes per entry;
- both tables encrypted with the keys of "(hash table)" and "(block table)" (0xC3AF3770, 0xEC83B3A3);
- a hash table size that is a power of two (SearchHashTable masks with size - 1), locale 0 and platform 0;
- block flags FILE_EXISTS, plus FILE_COMPRESS for zlib files (type byte 0x02 in front of each compressed sector,
  SComp::Decompress) or FILE_COMPRESS | FILE_SINGLE_UNIT; uncompressed files have equal sizes (SFileOpenFileEx);
- a "(listfile)" naming every file, each line ended by CR LF: patch archives are opened with flag 0x400, which
  rebuilds the lookup from the listfile (FillNewHashTable) and then drops the classic hash table, so a file missing
  from the listfile could not be found. The parser ignores a last line with no line end;
- an "(attributes)" file (CRC32 and MD5 of every block). FillNewHashTable also looks it up; without it the client
  falls back to the classic hash table, which works too, but every Blizzard archive has one.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import struct
import sys
import zlib
from dataclasses import dataclass, field

# --- format constants ---------------------------------------------------------------------------------------------

MPQ_MAGIC = 0x1A51504D  # 'MPQ\x1A'
MPQ_USERDATA_MAGIC = 0x1B51504D  # 'MPQ\x1B'
HEADER_SIZE_V0 = 32
HEADER_SIZE_V1 = 44

FILE_IMPLODE = 0x00000100
FILE_COMPRESS = 0x00000200
FILE_ENCRYPTED = 0x00010000
FILE_FIX_KEY = 0x00020000
FILE_SINGLE_UNIT = 0x01000000
FILE_DELETE_MARKER = 0x02000000
FILE_SECTOR_CRC = 0x04000000
FILE_EXISTS = 0x80000000

HASH_ENTRY_EMPTY = 0xFFFFFFFF
HASH_ENTRY_DELETED = 0xFFFFFFFE

COMPRESSION_ZLIB = 0x02

HASH_TABLE_INDEX = 0
HASH_NAME_A = 1
HASH_NAME_B = 2
HASH_FILE_KEY = 3

LISTFILE = "(listfile)"
ATTRIBUTES = "(attributes)"
SIGNATURE = "(signature)"
SPECIAL_FILES = (LISTFILE, ATTRIBUTES, SIGNATURE)

ATTRIBUTES_VERSION = 100
ATTRIBUTE_CRC32 = 0x1
ATTRIBUTE_FILETIME = 0x2
ATTRIBUTE_MD5 = 0x4

DEFAULT_SECTOR_SHIFT = 3  # 512 << 3 = 4096 bytes, what the stock 3.3.5a archives use
MAX_PATH_BYTES = 259  # the client hashes names into 260-byte buffers (HashEntryTable::CalculateHash)


class MpqError(Exception):
    pass


# --- crypt table, hashing and table encryption (System_MPQEncrypt) -------------------------------------------------


def _build_crypt_table() -> tuple[int, ...]:
    # The standard Storm table; the self-test compares it with the client's s_cryptTable (MPQEncrypt.cpp).
    table = [0] * 0x500
    seed = 0x00100001

    for index1 in range(0x100):
        index2 = index1

        for _ in range(5):
            seed = (seed * 125 + 3) % 0x2AAAAB
            high = (seed & 0xFFFF) << 16
            seed = (seed * 125 + 3) % 0x2AAAAB
            low = seed & 0xFFFF
            table[index2] = high | low
            index2 += 0x100

    return tuple(table)


CRYPT_TABLE = _build_crypt_table()


def _hash_char(c: int) -> int:
    # s_hashChars: ASCII lower case to upper case and '/' to '\'; every other byte is itself.
    if 0x61 <= c <= 0x7A:
        return c - 0x20
    if c == 0x2F:
        return 0x5C
    return c


def hash_string(name: str | bytes, hash_type: int) -> int:
    """System_MPQEncrypt::Hash. hash_type 0 = table index, 1/2 = name check values, 3 = encryption key."""
    data = name.encode("utf-8") if isinstance(name, str) else name
    seed1 = 0x7FED7FED
    seed2 = 0xEEEEEEEE

    for byte in data:
        ch = _hash_char(byte)
        seed1 = CRYPT_TABLE[hash_type * 0x100 + ch] ^ ((seed1 + seed2) & 0xFFFFFFFF)
        seed2 = (ch + seed1 + seed2 + (seed2 << 5) + 3) & 0xFFFFFFFF

    return seed1


HASH_TABLE_KEY = hash_string("(hash table)", HASH_FILE_KEY)
BLOCK_TABLE_KEY = hash_string("(block table)", HASH_FILE_KEY)


def encrypt_block(data: bytes, key: int) -> bytes:
    """System_MPQEncrypt::Encrypt over whole dwords; a trailing partial dword is left as is, like the client."""
    count = len(data) // 4
    words = struct.unpack_from(f"<{count}I", data)
    out = []
    seed = 0xEEEEEEEE

    for value in words:
        seed = (seed + CRYPT_TABLE[0x400 + (key & 0xFF)]) & 0xFFFFFFFF
        out.append(value ^ ((key + seed) & 0xFFFFFFFF))
        key = ((((~key) << 21) & 0xFFFFFFFF) + 0x11111111 & 0xFFFFFFFF) | (key >> 11)
        seed = (value + seed + (seed << 5) + 3) & 0xFFFFFFFF

    return struct.pack(f"<{count}I", *out) + data[count * 4:]


def decrypt_block(data: bytes, key: int) -> bytes:
    """System_MPQEncrypt::Decrypt."""
    count = len(data) // 4
    words = struct.unpack_from(f"<{count}I", data)
    out = []
    seed = 0xEEEEEEEE

    for value in words:
        seed = (seed + CRYPT_TABLE[0x400 + (key & 0xFF)]) & 0xFFFFFFFF
        plain = value ^ ((key + seed) & 0xFFFFFFFF)
        out.append(plain)
        key = ((((~key) << 21) & 0xFFFFFFFF) + 0x11111111 & 0xFFFFFFFF) | (key >> 11)
        seed = (plain + seed + (seed << 5) + 3) & 0xFFFFFFFF

    return struct.pack(f"<{count}I", *out) + data[count * 4:]


# --- archive names ------------------------------------------------------------------------------------------------


def normalize_archive_name(name: str) -> str:
    """Archive names use backslashes; the client hashes '/' and '\\' the same and ignores ASCII case."""
    name = name.replace("/", "\\")

    if not name or name.startswith("\\") or name.endswith("\\"):
        raise MpqError(f"bad archive name {name!r}")

    parts = name.split("\\")

    if any(part in ("", ".", "..") for part in parts):
        raise MpqError(f"bad archive name {name!r}")

    if any(ord(c) < 0x20 for c in name):
        raise MpqError(f"archive name {name!r} contains a control character")

    if len(name.encode("utf-8")) > MAX_PATH_BYTES:
        raise MpqError(f"archive name {name!r} is longer than {MAX_PATH_BYTES} bytes")

    return name


def name_key(name: str) -> bytes:
    """Two names with the same key are the same file to the client."""
    return bytes(_hash_char(b) for b in name.encode("utf-8"))


def collect_folder(src_dir: str) -> list[tuple[str, bytes]]:
    """Every regular file under src_dir as (archive name, data), sorted by archive name."""
    files = []
    src_dir = os.path.abspath(src_dir)

    if not os.path.isdir(src_dir):
        raise MpqError(f"{src_dir} is not a folder")

    for root, dirs, names in os.walk(src_dir):
        dirs.sort()

        for filename in sorted(names):
            path = os.path.join(root, filename)

            if os.path.islink(path) or not os.path.isfile(path):
                continue

            rel = os.path.relpath(path, src_dir)
            archive_name = normalize_archive_name(rel.replace(os.sep, "\\"))

            if archive_name in SPECIAL_FILES:
                raise MpqError(f"{path}: {archive_name} is written by MpqPack itself")

            with open(path, "rb") as f:
                files.append((archive_name, f.read()))

    files.sort(key=lambda item: name_key(item[0]))
    return files


# --- writer -------------------------------------------------------------------------------------------------------


@dataclass
class PackedFile:
    name: str
    data: bytes
    payload: bytes
    flags: int
    offset: int = 0


@dataclass
class PackStats:
    path: str
    file_count: int
    archive_size: int
    hash_table_size: int
    compressed: int
    stored: int


def _next_power_of_two(value: int) -> int:
    size = 1

    while size < value:
        size <<= 1

    return size


def _pack_payload(data: bytes, sector_size: int, compress: bool, single_unit: bool) -> tuple[bytes, int]:
    """The bytes stored for one file and its block flags."""
    if not data or not compress:
        # Uncompressed files go through the plain range path, which requires compressed size == file size.
        return data, FILE_EXISTS

    if single_unit:
        packed = bytes([COMPRESSION_ZLIB]) + zlib.compress(data, 9)

        # IOMpqReadUnit treats a single unit whose stored size equals the file size as uncompressed.
        if len(packed) < len(data):
            return packed, FILE_EXISTS | FILE_COMPRESS | FILE_SINGLE_UNIT

        return data, FILE_EXISTS

    sectors = []

    for start in range(0, len(data), sector_size):
        raw = data[start:start + sector_size]
        packed = bytes([COMPRESSION_ZLIB]) + zlib.compress(raw, 9)

        # A sector stored at its full size is read raw (CountCompressed/CountUncompressed), so only keep the
        # compressed form when it is strictly smaller.
        sectors.append(packed if len(packed) < len(raw) else raw)

    # Sector offset table: one offset per sector plus the end, the first one equal to the table size (a larger
    # first offset would announce a sector checksum table, LoadSectorTable).
    table_size = 4 * (len(sectors) + 1)
    offsets = [table_size]

    for sector in sectors:
        offsets.append(offsets[-1] + len(sector))

    payload = struct.pack(f"<{len(offsets)}I", *offsets) + b"".join(sectors)

    if len(payload) >= len(data):
        return data, FILE_EXISTS

    return payload, FILE_EXISTS | FILE_COMPRESS


def _attributes_payload(files: list[PackedFile]) -> bytes:
    # Version, flags, CRC32 per block, MD5 per block (ReadAdditionalAttributes reads the arrays in flag order).
    # The (attributes) block itself gets zeros, as StormLib writes it.
    crcs = []
    md5s = []

    for entry in files:
        if entry.name == ATTRIBUTES:
            crcs.append(0)
            md5s.append(bytes(16))
        else:
            crcs.append(zlib.crc32(entry.data) & 0xFFFFFFFF)
            md5s.append(hashlib.md5(entry.data).digest())

    return struct.pack("<II", ATTRIBUTES_VERSION, ATTRIBUTE_CRC32 | ATTRIBUTE_MD5) + struct.pack(f"<{len(crcs)}I", *crcs) + b"".join(md5s)


def make_listfile(names: list[str]) -> bytes:
    # Every line ends with CR LF, the last one too: ListfileParser::Next drops a last line with no line end. The
    # special files are not listed: FillNewHashTable adds them itself, and a name listed twice makes it give up.
    return "".join(name + "\r\n" for name in names).encode("utf-8")


def build_archive(files: list[tuple[str, bytes]], *, compress: bool = True, sector_shift: int = DEFAULT_SECTOR_SHIFT,
                  single_unit: bool = False, hash_table_size: int | None = None) -> bytes:
    """Return the bytes of an MPQ v1 (format 0) archive holding files, plus (listfile) and (attributes)."""
    if not 0 <= sector_shift <= 15:
        raise MpqError("sector shift must be between 0 and 15")

    sector_size = 512 << sector_shift
    seen = {}
    entries = []

    for name, data in files:
        name = normalize_archive_name(name)

        if name in SPECIAL_FILES:
            raise MpqError(f"{name} is written by MpqPack itself")

        key = name_key(name)

        if key in seen:
            raise MpqError(f"{name} and {seen[key]} are the same file to the client (case and slashes are ignored)")

        seen[key] = name
        entries.append((name, bytes(data)))

    entries.sort(key=lambda item: name_key(item[0]))

    if any(len(data) >= 0x100000000 for _, data in entries):
        raise MpqError("a file of 4 GB or more does not fit an MPQ v1 block entry")

    listfile = make_listfile([name for name, _ in entries])
    packed = [PackedFile(name, data, *_pack_payload(data, sector_size, compress, single_unit)) for name, data in entries]
    packed.append(PackedFile(LISTFILE, listfile, *_pack_payload(listfile, sector_size, compress, single_unit)))
    packed.append(PackedFile(ATTRIBUTES, b"", b"", FILE_EXISTS))

    attributes = _attributes_payload(packed)
    packed[-1] = PackedFile(ATTRIBUTES, attributes, *_pack_payload(attributes, sector_size, compress, single_unit))

    count = len(packed)

    if hash_table_size is None:
        # At most half full, so the linear probe in SearchHashTable stays short.
        hash_table_size = _next_power_of_two(max(16, count * 2))
    elif hash_table_size < count or hash_table_size & (hash_table_size - 1):
        raise MpqError("the hash table size must be a power of two and at least the number of files")

    # Layout: header, file data, hash table, block table (the block table must end the archive).
    offset = HEADER_SIZE_V0

    for entry in packed:
        entry.offset = offset
        offset += len(entry.payload)

    hash_table_pos = offset
    block_table_pos = hash_table_pos + 16 * hash_table_size
    archive_size = block_table_pos + 16 * count

    if archive_size >= 0x100000000:
        raise MpqError("the archive would be 4 GB or larger, which MPQ v1 cannot address")

    hash_table = [(HASH_ENTRY_EMPTY, HASH_ENTRY_EMPTY, 0xFFFF, 0xFF, 0xFF, HASH_ENTRY_EMPTY)] * hash_table_size
    mask = hash_table_size - 1

    for block_index, entry in enumerate(packed):
        index = hash_string(entry.name, HASH_TABLE_INDEX) & mask

        while hash_table[index][5] != HASH_ENTRY_EMPTY:
            index = (index + 1) & mask

        # Locale 0 (neutral) and platform 0: SearchHashTable matches them for every client locale.
        hash_table[index] = (hash_string(entry.name, HASH_NAME_A), hash_string(entry.name, HASH_NAME_B), 0, 0, 0, block_index)

    hash_bytes = b"".join(struct.pack("<IIHBBI", *row) for row in hash_table)
    block_bytes = b"".join(struct.pack("<IIII", e.offset, len(e.payload), len(e.data), e.flags) for e in packed)

    header = struct.pack("<IIIHHIIII", MPQ_MAGIC, HEADER_SIZE_V0, archive_size, 0, sector_shift,
                         hash_table_pos, block_table_pos, hash_table_size, count)

    out = bytearray(header)

    for entry in packed:
        out += entry.payload

    out += encrypt_block(hash_bytes, HASH_TABLE_KEY)
    out += encrypt_block(block_bytes, BLOCK_TABLE_KEY)

    assert len(out) == archive_size
    return bytes(out)


def write_archive(path: str, files: list[tuple[str, bytes]], **options) -> PackStats:
    """Build an archive and write it to path (through a temporary file, so a failed run leaves no half archive)."""
    data = build_archive(files, **options)
    tmp = path + ".tmp"

    with open(tmp, "wb") as f:
        f.write(data)

    os.replace(tmp, path)

    archive = MpqArchive(data)
    compressed = sum(1 for b in archive.blocks if b.flags & FILE_COMPRESS)

    return PackStats(path, len(files), len(data), archive.header.hash_table_size, compressed, len(archive.blocks) - compressed)


def pack_folder(src_dir: str, out_path: str, **options) -> PackStats:
    out_abs = os.path.abspath(out_path)
    src_abs = os.path.abspath(src_dir)

    if os.path.commonpath([out_abs, src_abs]) == src_abs:
        raise MpqError("the output archive must not be inside the source folder")

    return write_archive(out_path, collect_folder(src_dir), **options)


# --- reader -------------------------------------------------------------------------------------------------------


@dataclass
class Header:
    offset: int
    header_size: int
    archive_size: int
    format_version: int
    sector_shift: int
    hash_table_pos: int
    block_table_pos: int
    hash_table_size: int
    block_table_size: int
    hi_block_table_pos: int = 0
    hash_table_pos_hi: int = 0
    block_table_pos_hi: int = 0


@dataclass
class HashEntry:
    name_a: int
    name_b: int
    locale: int
    platform: int
    block_index: int


@dataclass
class BlockEntry:
    offset: int
    compressed_size: int
    file_size: int
    flags: int


@dataclass
class ArchiveReport:
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    lookup_mode: str = ""


class MpqArchive:
    """A reader for the archives MpqPack writes (and other zlib or uncompressed MPQ v1 archives).

    It applies the client's own acceptance rules, so verify() reports what the client would reject or misread.
    Implode, bzip2, LZMA and encrypted files are recognised but not decoded.
    """

    def __init__(self, source: str | bytes):
        if isinstance(source, (bytes, bytearray)):
            self.data = bytes(source)
            self.path = "<memory>"
        else:
            with open(source, "rb") as f:
                self.data = f.read()
            self.path = source

        self.header = self._find_header()
        self.archive_end = self._archive_end()
        self.sector_size = 512 << self.header.sector_shift
        self.hashes = self._read_hash_table()
        self.blocks = self._read_block_table()

    # s_OpenArchive: look for the header at offset 0, then every 512 bytes, following an 'MPQ\x1B' user data header.
    def _find_header(self) -> Header:
        offset = 0
        size = len(self.data)

        while offset + 44 < size:
            magic = struct.unpack_from("<I", self.data, offset)[0]

            if magic == MPQ_USERDATA_MAGIC:
                offset += struct.unpack_from("<I", self.data, offset + 8)[0]
                continue

            if magic == MPQ_MAGIC:
                fields = struct.unpack_from("<IIIHHIIII", self.data, offset)
                header = Header(offset, fields[1], fields[2], fields[3], fields[4], fields[5], fields[6], fields[7], fields[8])

                if header.format_version >= 1 and offset + HEADER_SIZE_V1 <= size:
                    header.hi_block_table_pos, header.hash_table_pos_hi, header.block_table_pos_hi = struct.unpack_from("<QHH", self.data, offset + 32)

                return header

            offset += 512

        raise MpqError(f"{self.path}: no MPQ header found (the client needs a file of more than 44 bytes)")

    def _archive_end(self) -> int:
        h = self.header
        block_end = ((h.block_table_pos_hi << 32) | h.block_table_pos) + 16 * h.block_table_size
        hi_block_end = h.hi_block_table_pos + 2 * h.block_table_size
        hash_end = ((h.hash_table_pos_hi << 32) | h.hash_table_pos) + 16 * h.hash_table_size
        end = max(hash_end, block_end, hi_block_end)
        return min(end, len(self.data)) + h.offset

    def _read_hash_table(self) -> list[HashEntry]:
        h = self.header
        raw = self.data[h.offset + h.hash_table_pos:h.offset + h.hash_table_pos + 16 * h.hash_table_size]

        if len(raw) != 16 * h.hash_table_size:
            raise MpqError(f"{self.path}: the hash table runs past the end of the file")

        raw = decrypt_block(raw, HASH_TABLE_KEY)
        return [HashEntry(*struct.unpack_from("<IIHBxI", raw, 16 * i)) for i in range(h.hash_table_size)]

    def _read_block_table(self) -> list[BlockEntry]:
        h = self.header
        raw = self.data[h.offset + h.block_table_pos:h.offset + h.block_table_pos + 16 * h.block_table_size]

        if len(raw) != 16 * h.block_table_size:
            raise MpqError(f"{self.path}: the block table runs past the end of the file")

        raw = decrypt_block(raw, BLOCK_TABLE_KEY)
        blocks = []

        for i in range(h.block_table_size):
            offset, compressed, size, flags = struct.unpack_from("<IIII", raw, 16 * i)
            blocks.append(BlockEntry(offset + h.offset, compressed, size, flags))

        return blocks

    # SearchHashTable with matchNeutral, for an archive whose locale and platform are 0.
    def find_block(self, name: str) -> int | None:
        size = len(self.hashes)

        if not size:
            return None

        mask = size - 1
        index = start = hash_string(name, HASH_TABLE_INDEX) & mask
        name_a = hash_string(name, HASH_NAME_A)
        name_b = hash_string(name, HASH_NAME_B)
        found = None

        while True:
            entry = self.hashes[index]

            if entry.block_index == HASH_ENTRY_EMPTY:
                break

            if entry.name_a == name_a and entry.name_b == name_b and entry.block_index != HASH_ENTRY_DELETED:
                if entry.locale == 0 and entry.platform == 0:
                    found = entry.block_index
                    break

                if found is None:
                    found = entry.block_index

            index = (index + 1) & mask

            if index == start:
                break

        return found

    def has_file(self, name: str) -> bool:
        return self.find_block(name) is not None

    def read_block(self, block_index: int, name: str = "") -> bytes:
        block = self.blocks[block_index]
        where = name or f"block {block_index}"

        if not block.flags & FILE_EXISTS:
            raise MpqError(f"{where}: block is not marked FILE_EXISTS (the client refuses it, error 1006)")

        if block.flags & FILE_DELETE_MARKER:
            raise MpqError(f"{where}: is a delete marker")

        stored = self.data[block.offset:block.offset + block.compressed_size]

        if len(stored) != block.compressed_size or block.offset + block.compressed_size > self.archive_end:
            raise MpqError(f"{where}: data runs past the end of the archive")

        if not block.flags & 0xFFF00:
            if block.compressed_size != block.file_size:
                raise MpqError(f"{where}: uncompressed file with different stored and file sizes (client error 1006)")
            return stored

        if block.flags & (FILE_ENCRYPTED | FILE_FIX_KEY):
            raise MpqError(f"{where}: encrypted files are not supported by this reader")

        if block.file_size == 0:
            return b""

        method = block.flags & 0xFF00

        if block.flags & FILE_SINGLE_UNIT:
            if block.compressed_size == block.file_size:
                return stored
            return self._decompress_unit(stored, block.file_size, method, where)

        # Sector table, checked like IOMpqReadUnit::LoadSectorTable.
        sector_count = (block.file_size + self.sector_size - 1) // self.sector_size
        table_size = 4 * (sector_count + 1)

        if len(stored) < table_size:
            raise MpqError(f"{where}: sector table is cut off")

        offsets = struct.unpack_from(f"<{sector_count + 1}I", stored)

        for i in range(1, sector_count + 1):
            if offsets[i] <= offsets[i - 1] or offsets[i] > block.compressed_size:
                raise MpqError(f"{where}: sector offsets are not increasing or run past the stored size")

        if offsets[0] != table_size:
            raise MpqError(f"{where}: first sector offset {offsets[0]} is not the table size {table_size} (sector CRCs are not supported)")

        out = bytearray()
        last_size = block.file_size % self.sector_size or self.sector_size

        for i in range(sector_count):
            expected = last_size if i == sector_count - 1 else self.sector_size
            chunk = stored[offsets[i]:offsets[i + 1]]

            if len(chunk) == expected:
                out += chunk
            else:
                out += self._decompress_unit(chunk, expected, method, f"{where} sector {i}")

        return bytes(out)

    @staticmethod
    def _decompress_unit(chunk: bytes, expected: int, method: int, where: str) -> bytes:
        if method != FILE_COMPRESS:
            raise MpqError(f"{where}: compression method 0x{method:X} is not supported (only FILE_COMPRESS)")

        if not chunk:
            raise MpqError(f"{where}: empty compressed unit")

        if chunk[0] != COMPRESSION_ZLIB:
            raise MpqError(f"{where}: compression type 0x{chunk[0]:02X} is not supported by this reader (zlib is 0x02)")

        try:
            data = zlib.decompress(chunk[1:])
        except zlib.error as e:
            raise MpqError(f"{where}: zlib data is corrupt ({e})") from e

        if len(data) != expected:
            raise MpqError(f"{where}: decompressed to {len(data)} bytes instead of {expected}")

        return data

    def read(self, name: str) -> bytes:
        block_index = self.find_block(name)

        if block_index is None:
            raise MpqError(f"{name}: not in the archive")

        return self.read_block(block_index, name)

    def listfile_names(self) -> list[str]:
        """The listfile split the way the client's ListfileParser does it (a last line with no line end is lost)."""
        if not self.has_file(LISTFILE):
            return []

        text = self.read(LISTFILE)
        names = []

        for match in re.finditer(rb"([^\r\n]*)(\r\n|\r|\n)", text):
            names.append(match.group(1).decode("utf-8", "surrogateescape"))

        return names

    def names(self) -> list[str]:
        """The files named by the listfile that exist in the archive, without the special files."""
        return [n for n in self.listfile_names() if n and n not in SPECIAL_FILES and self.has_file(n)]

    def verify(self) -> ArchiveReport:
        """Check the archive against the client's reader and report anything it would reject or misread."""
        report = ArchiveReport()
        h = self.header
        size = len(self.data)

        if h.offset != 0:
            report.notes.append(f"header found at offset {h.offset}, not 0")

        if h.format_version == 0 and h.header_size != HEADER_SIZE_V0:
            report.problems.append(f"format 0 header size is {h.header_size}, the client requires 32")
        elif h.format_version == 1 and h.header_size != HEADER_SIZE_V1:
            report.problems.append(f"format 1 header size is {h.header_size}, the client requires 44")
        elif h.format_version > 1:
            report.notes.append(f"format version {h.format_version}; MpqPack writes version 0")

        if size <= 44:
            report.problems.append("the file is 44 bytes or smaller; the client does not look for a header in it")

        if not (h.hash_table_pos < self.archive_end and h.block_table_pos < self.archive_end):
            report.problems.append("a table position lies past the end of the archive")

        if h.hash_table_size == 0 or h.hash_table_size & (h.hash_table_size - 1):
            report.problems.append(f"hash table size {h.hash_table_size} is not a power of two")

        if h.block_table_pos - h.hash_table_pos != 16 * h.hash_table_size:
            report.problems.append("the hash table is not directly in front of the block table; the client would read it as compressed")

        if h.hi_block_table_pos == 0 and self.archive_end - h.offset - h.block_table_pos != 16 * h.block_table_size:
            report.problems.append("the block table does not end the archive; the client would read it as compressed")

        if h.sector_shift > 15:
            report.problems.append(f"sector size shift {h.sector_shift} is out of range")

        referenced = set()

        for i, entry in enumerate(self.hashes):
            if entry.block_index in (HASH_ENTRY_EMPTY, HASH_ENTRY_DELETED):
                continue

            if entry.block_index >= len(self.blocks):
                report.problems.append(f"hash entry {i} points at block {entry.block_index}, past the block table")
                continue

            if entry.locale != 0 or entry.platform != 0:
                report.notes.append(f"hash entry {i} has locale {entry.locale} platform {entry.platform}")

            referenced.add(entry.block_index)

        if not any(e.block_index == HASH_ENTRY_EMPTY for e in self.hashes):
            report.notes.append("the hash table has no empty slot; lookups of missing files scan all of it")

        for i, block in enumerate(self.blocks):
            if i not in referenced:
                report.notes.append(f"block {i} is not referenced by the hash table")
                continue

            try:
                self.read_block(i)
            except MpqError as e:
                report.problems.append(str(e))

        # Listfile: patch archives are opened with flag 0x400, so the client rebuilds its lookup from the listfile.
        names = self.listfile_names() if self.has_file(LISTFILE) else []
        conversion_ok = self.has_file(LISTFILE)

        if not self.has_file(LISTFILE):
            report.problems.append("no (listfile): tools cannot list the archive")
        else:
            raw = self.read(LISTFILE)

            if raw and raw[-1:] not in (b"\r", b"\n"):
                report.problems.append("the (listfile) does not end with a line end; the client ignores its last name")

        listed_blocks = {}
        seen = set()

        for name in names:
            if not name:
                report.notes.append("the (listfile) has an empty line; the client then keeps the classic hash table")
                conversion_ok = False
                continue

            key = name_key(name)

            if key in seen or name in (LISTFILE, ATTRIBUTES):
                report.notes.append(f"the (listfile) names {name} twice (or names a special file); the client then keeps the classic hash table")
                conversion_ok = False

            seen.add(key)
            block_index = self.find_block(name)

            if block_index is None:
                report.notes.append(f"the (listfile) names {name}, which is not in the archive; the client then keeps the classic hash table")
                conversion_ok = False
            else:
                listed_blocks[block_index] = name

        for special in (LISTFILE, ATTRIBUTES):
            block_index = self.find_block(special)

            if block_index is not None:
                listed_blocks[block_index] = special

        if not self.has_file(ATTRIBUTES):
            report.notes.append("no (attributes): the client keeps the classic hash table")
            conversion_ok = False
        else:
            problem = self._check_attributes()

            if problem:
                report.problems.append(problem)

        for block_index in sorted(referenced):
            if block_index not in listed_blocks:
                report.problems.append(f"block {block_index} is not named by the (listfile); the client could not find it once it converts the lookup")

        report.lookup_mode = "listfile lookup (FillNewHashTable succeeds)" if conversion_ok else "classic hash table"
        return report

    def _check_attributes(self) -> str:
        # ReadAdditionalAttributes: 8 <= size <= count * 512 + 8, and with only known flags the arrays fill the rest.
        data = self.read(ATTRIBUTES)
        count = self.header.block_table_size

        if len(data) < 8 or len(data) > (count << 9) + 8:
            return "(attributes) has a size the client rejects"

        flags = struct.unpack_from("<I", data, 4)[0]
        needed = 0
        unknown = flags

        for bit, width in ((ATTRIBUTE_CRC32, 4), (ATTRIBUTE_FILETIME, 8), (ATTRIBUTE_MD5, 16)):
            if flags & bit:
                needed += width * count
                unknown &= ~bit

        remaining = len(data) - 8

        if remaining < needed or (not unknown and remaining != needed):
            return "(attributes) arrays do not match the block count"

        offset = 8

        if flags & ATTRIBUTE_CRC32:
            crcs = struct.unpack_from(f"<{count}I", data, offset)
            offset += 4 * count

            for i, crc in enumerate(crcs):
                if crc and self.blocks[i].flags & FILE_EXISTS:
                    try:
                        content = self.read_block(i)
                    except MpqError:
                        continue

                    if zlib.crc32(content) & 0xFFFFFFFF != crc:
                        return f"(attributes) CRC32 of block {i} does not match its data"

        if flags & ATTRIBUTE_FILETIME:
            offset += 8 * count

        if flags & ATTRIBUTE_MD5:
            for i in range(count):
                digest = data[offset + 16 * i:offset + 16 * (i + 1)]

                if digest != bytes(16):
                    try:
                        content = self.read_block(i)
                    except MpqError:
                        continue

                    if hashlib.md5(content).digest() != digest:
                        return f"(attributes) MD5 of block {i} does not match its data"

        return ""


# --- self-test ----------------------------------------------------------------------------------------------------

# Published values: the client's own table keys (InitializeTables decrypts with them) and the well-known hash of
# "(listfile)" from the MPQ format documentation.
KNOWN_HASHES = (
    ("(hash table)", HASH_FILE_KEY, 0xC3AF3770),
    ("(block table)", HASH_FILE_KEY, 0xEC83B3A3),
    ("(listfile)", HASH_TABLE_INDEX, 0x5F3DE859),
    ("(listfile)", HASH_NAME_A, 0xFD657910),
    ("(listfile)", HASH_NAME_B, 0x4E9B98A7),
)

CLIENT_CRYPT_SOURCE = os.path.join("Engine", "Source", "BlizzardCore", "Source", "Packages", "Mopaq", "MPQEncrypt.cpp")


def find_client_crypt_source() -> str | None:
    """MPQEncrypt.cpp of the decompilation, when MpqPack runs from Tools/MpqPack of a checkout."""
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = os.path.join(root, CLIENT_CRYPT_SOURCE)
    return path if os.path.isfile(path) else None


def parse_client_crypt_table(path: str) -> list[int]:
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    start = text.index("s_cryptTable[1280] = {")
    end = text.index("};", start)
    return [int(v, 16) for v in re.findall(r"0x([0-9A-Fa-f]{8})", text[start:end])]


def selftest(verbose: bool = True) -> list[str]:
    """Run the built-in checks; return a list of failures (empty when everything passed)."""
    failures = []

    def check(condition: bool, message: str):
        if not condition:
            failures.append(message)
        elif verbose:
            print(f"ok    {message}")

    for name, kind, expected in KNOWN_HASHES:
        got = hash_string(name, kind)
        check(got == expected, f"Hash({name!r}, {kind}) = 0x{got:08X}, expected 0x{expected:08X}")

    check(hash_string("dbfilesclient/chrraces.dbc", 1) == hash_string("DBFilesClient\\ChrRaces.dbc", 1), "names hash without regard to case and slash direction")
    check(CRYPT_TABLE[0] == 0x55C636E2 and CRYPT_TABLE[0x4FF] == 0x7303286C, "crypt table first and last entries")

    client_source = find_client_crypt_source()

    if client_source:
        check(parse_client_crypt_table(client_source) == list(CRYPT_TABLE), f"crypt table equals s_cryptTable in {CLIENT_CRYPT_SOURCE}")
    elif verbose:
        print(f"skip  crypt table against the client source ({CLIENT_CRYPT_SOURCE} not found)")

    sample = bytes(range(256)) * 3 + b"xyz"
    check(decrypt_block(encrypt_block(sample, 0x12345678), 0x12345678) == sample, "encrypt/decrypt round trip")

    files = [
        ("DBFilesClient\\Empty.dbc", b""),
        ("DBFilesClient\\Tiny.dbc", b"abc"),
        ("DBFilesClient\\OneSector.dbc", b"A" * 4096),
        ("DBFilesClient\\SectorPlusOne.dbc", bytes(i % 7 for i in range(4097))),
        ("DBFilesClient\\Random.dbc", os.urandom(20000)),
        ("Interface\\Glues\\Long\\Path\\File.txt", b"line\r\n" * 5000),
    ]

    for options in ({"compress": True}, {"compress": False}, {"compress": True, "single_unit": True}, {"compress": True, "sector_shift": 0}):
        data = build_archive(files, **options)
        archive = MpqArchive(data)
        report = archive.verify()
        label = ", ".join(f"{k}={v}" for k, v in options.items())
        check(not report.problems, f"verify finds no problems ({label}): {report.problems}")
        check(report.lookup_mode.startswith("listfile"), f"listfile lookup would be used ({label})")
        check(all(archive.read(name) == content for name, content in files), f"every file reads back unchanged ({label})")
        check(sorted(archive.names()) == sorted(name for name, _ in files), f"listfile names every file ({label})")
        check(archive.has_file("dbfilesclient/tiny.DBC"), f"case and slash insensitive lookup ({label})")

    return failures


# --- command line -------------------------------------------------------------------------------------------------


def _flag_text(flags: int) -> str:
    parts = []

    for bit, text in ((FILE_COMPRESS, "zlib"), (FILE_IMPLODE, "implode"), (FILE_SINGLE_UNIT, "single"),
                      (FILE_ENCRYPTED, "encrypted"), (FILE_SECTOR_CRC, "sectorcrc"), (FILE_DELETE_MARKER, "deleted")):
        if flags & bit:
            parts.append(text)

    return ",".join(parts) or "stored"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mpqpack.py", description="Build and check MPQ patch archives for the 3.3.5a client.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("pack", help="pack every file of a folder into an archive")
    p.add_argument("source", help="folder whose relative paths become the archive paths (e.g. it holds DBFilesClient\\)")
    p.add_argument("archive", help="archive to write, e.g. patch-R.MPQ")
    p.add_argument("--no-compress", action="store_true", help="store every file uncompressed")
    p.add_argument("--single-unit", action="store_true", help="compress each file as one unit instead of 4 KB sectors")
    p.add_argument("--sector-shift", type=int, default=DEFAULT_SECTOR_SHIFT, help="sector size is 512 << shift (default 3)")

    p = sub.add_parser("list", help="list the files of an archive")
    p.add_argument("archive")

    p = sub.add_parser("extract", help="extract every listed file")
    p.add_argument("archive")
    p.add_argument("dest")

    p = sub.add_parser("verify", help="check an archive against the client's reader, optionally against a folder")
    p.add_argument("archive")
    p.add_argument("source", nargs="?", help="folder the archive was packed from; every file must match")

    sub.add_parser("selftest", help="run the built-in format checks")

    args = parser.parse_args(argv)

    try:
        if args.command == "pack":
            stats = pack_folder(args.source, args.archive, compress=not args.no_compress, single_unit=args.single_unit, sector_shift=args.sector_shift)
            report = MpqArchive(args.archive).verify()

            if report.problems:
                for problem in report.problems:
                    print(f"error: {problem}", file=sys.stderr)
                return 1

            print(f"wrote {stats.path}: {stats.file_count} files, {stats.archive_size} bytes, hash table {stats.hash_table_size}, lookup: {report.lookup_mode}")
            return 0

        if args.command == "list":
            archive = MpqArchive(args.archive)

            for name in archive.listfile_names():
                block_index = archive.find_block(name) if name else None

                if block_index is None:
                    print(f"{'?':>10} {'?':>10} {'missing':<8} {name}")
                    continue

                block = archive.blocks[block_index]
                print(f"{block.file_size:>10} {block.compressed_size:>10} {_flag_text(block.flags):<8} {name}")

            return 0

        if args.command == "extract":
            archive = MpqArchive(args.archive)
            dest = os.path.abspath(args.dest)

            for name in archive.names():
                path = os.path.join(dest, *name.split("\\"))

                if os.path.commonpath([os.path.abspath(path), dest]) != dest:
                    raise MpqError(f"{name}: would be written outside {dest}")

                os.makedirs(os.path.dirname(path), exist_ok=True)

                with open(path, "wb") as f:
                    f.write(archive.read(name))

                print(name)

            return 0

        if args.command == "verify":
            archive = MpqArchive(args.archive)
            report = archive.verify()

            if args.source:
                expected = collect_folder(args.source)
                listed = {name_key(n) for n in archive.names()}

                for name, content in expected:
                    if not archive.has_file(name):
                        report.problems.append(f"{name}: missing from the archive")
                    elif archive.read(name) != content:
                        report.problems.append(f"{name}: differs from the source folder")

                    listed.discard(name_key(name))

                for key in sorted(listed):
                    report.problems.append(f"{key.decode('utf-8', 'replace')}: in the archive but not in the source folder")

            for note in report.notes:
                print(f"note: {note}")

            for problem in report.problems:
                print(f"error: {problem}")

            print(f"{args.archive}: {len(archive.blocks)} blocks, lookup: {report.lookup_mode}, {'OK' if not report.problems else 'FAILED'}")
            return 1 if report.problems else 0

        if args.command == "selftest":
            failures = selftest()

            for failure in failures:
                print(f"FAIL  {failure}")

            print("selftest passed" if not failures else f"selftest: {len(failures)} failures")
            return 1 if failures else 0
    except (MpqError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    return 2


if __name__ == "__main__":
    sys.exit(main())
