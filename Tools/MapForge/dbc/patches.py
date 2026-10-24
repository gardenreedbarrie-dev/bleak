r"""Which archive the client takes each file from, reading the realm's patches, and merging DBCs into one of them.

Archive order (WoW/Source/WowServices/PatchFiles.cpp, OpenArchives in WoW/Source/Client.cpp): the client lists
Data\patch-?.MPQ and Data\<locale>\patch-<locale>-?.MPQ ('?' is exactly one character, Blizzard::File::SimpleGlob),
sorts them by full path with SStrCmpI (MSVC _strnicmp: ASCII letters folded to lower case, then byte order) and
opens them so that the path sorting last gets the highest priority. Data\patch.MPQ and Data\<locale>\patch-
<locale>.MPQ come below all of those, and the base archives (common.MPQ, locale-<locale>.MPQ, ...) below that. When
several archives hold a file, the one with the highest priority wins. So:

- every Data\patch-<letter>.MPQ outranks every locale patch ("data\enus\..." < "data\patch-...");
- digits sort before letters, letters alphabetically, case ignored: patch-3 < Patch-A < patch-r < PATCH-Z;
- characters after 'z' in byte order ('{', '}', '~') sort after every letter.

A player's launcher may leave optional packs out (the launcher's config/packs.json, for instance the HD pack of
Reforged's patches and Patch-Y), so the order is worked out for every combination of packs.

The reader extends MpqPack's (zlib or stored files) with what third-party archives use for DBCs: bzip2, encrypted
files (with and without the fix-key flag) and sector checksums. Imploded (PKWARE) files, LZMA, Huffman and ADPCM are
recognised and refused with a message.
"""

from __future__ import annotations

import bz2
import fnmatch
import itertools
import os
import re
import shutil
import struct
import zlib
from dataclasses import dataclass, field

import mpqpack  # noqa: E402  (Tools/MpqPack, added to sys.path by the package)

COMPRESSION_BZIP2 = 0x10
COMPRESSION_LZMA = 0x12
LOCALES = ("enUS", "enGB", "deDE", "frFR", "esES", "esMX", "ruRU", "koKR", "zhCN", "zhTW", "enCN", "enTW", "ptBR",
           "ptPT", "itIT")
_SINGLE = re.compile(r"(?i)patch-(.)\.mpq")


class PatchError(Exception):
    pass


def sort_key(client_path: str) -> bytes:
    r"""SStrCmpI order of a path such as Data\patch-Z.MPQ."""
    return client_path.encode("utf-8").lower()


# --- reading ---------------------------------------------------------------------------------------------------


class PatchArchive(mpqpack.MpqArchive):
    """mpqpack's reader plus bzip2, encryption and sector checksums."""

    def read_block(self, block_index: int, name: str = "") -> bytes:
        block = self.blocks[block_index]
        flags = block.flags
        where = name or f"block {block_index}"

        if not flags & mpqpack.FILE_EXISTS:
            raise mpqpack.MpqError(f"{where}: block is not marked FILE_EXISTS")

        if flags & mpqpack.FILE_DELETE_MARKER:
            raise mpqpack.MpqError(f"{where}: is a delete marker")

        if flags & mpqpack.FILE_IMPLODE:
            raise mpqpack.MpqError(f"{where}: imploded (PKWARE) files are not supported; extract it with an MPQ tool")

        stored = bytes(self.data[block.offset:block.offset + block.compressed_size])

        if len(stored) != block.compressed_size:
            raise mpqpack.MpqError(f"{where}: data runs past the end of the archive")

        key = None

        if flags & mpqpack.FILE_ENCRYPTED:
            if not name:
                raise mpqpack.MpqError(f"{where}: an encrypted file needs its name")

            key = mpqpack.hash_string(name.replace("/", "\\").split("\\")[-1], mpqpack.HASH_FILE_KEY)

            if flags & mpqpack.FILE_FIX_KEY:
                key = ((key + block.offset - self.header.offset) ^ block.file_size) & 0xFFFFFFFF

        def plain(data: bytes, index: int) -> bytes:
            return mpqpack.decrypt_block(data, (key + index) & 0xFFFFFFFF) if key is not None else data

        if block.file_size == 0:
            return b""

        compressed = bool(flags & mpqpack.FILE_COMPRESS)

        if flags & mpqpack.FILE_SINGLE_UNIT:
            data = plain(stored, 0)

            if compressed and block.compressed_size < block.file_size:
                return self._unit(data, block.file_size, where)

            return data

        sector_count = (block.file_size + self.sector_size - 1) // self.sector_size

        if not compressed:
            if block.compressed_size != block.file_size:
                raise mpqpack.MpqError(f"{where}: uncompressed file with different stored and file sizes")

            if key is None:
                return stored

            return b"".join(plain(stored[i * self.sector_size:(i + 1) * self.sector_size], i)
                            for i in range(sector_count))

        entries = sector_count + 1 + (1 if flags & mpqpack.FILE_SECTOR_CRC else 0)
        table = stored[:4 * entries]

        if len(table) != 4 * entries:
            raise mpqpack.MpqError(f"{where}: sector table is cut off")

        if key is not None:
            table = mpqpack.decrypt_block(table, (key - 1) & 0xFFFFFFFF)

        offsets = struct.unpack(f"<{entries}I", table)

        for i in range(1, sector_count + 1):
            if offsets[i] < offsets[i - 1] or offsets[i] > block.compressed_size:
                raise mpqpack.MpqError(f"{where}: sector offsets are not increasing or run past the stored size")

        out = bytearray()
        last = block.file_size - (sector_count - 1) * self.sector_size

        for i in range(sector_count):
            expected = last if i == sector_count - 1 else self.sector_size
            chunk = plain(stored[offsets[i]:offsets[i + 1]], i)
            out += chunk if len(chunk) == expected else self._unit(chunk, expected, f"{where} sector {i}")

        return bytes(out)

    @staticmethod
    def _unit(chunk: bytes, expected: int, where: str) -> bytes:
        if not chunk:
            raise mpqpack.MpqError(f"{where}: empty compressed unit")

        method = chunk[0]

        try:
            if method == mpqpack.COMPRESSION_ZLIB:
                data = zlib.decompress(chunk[1:])
            elif method == COMPRESSION_BZIP2:
                data = bz2.decompress(chunk[1:])
            elif method == COMPRESSION_LZMA:
                raise mpqpack.MpqError(f"{where}: LZMA-compressed files are not supported; extract it with an MPQ tool")
            else:
                raise mpqpack.MpqError(f"{where}: compression 0x{method:02X} is not supported (zlib 0x02 and bzip2 0x10"
                                       " are); extract it with an MPQ tool")
        except (zlib.error, OSError, ValueError) as e:
            raise mpqpack.MpqError(f"{where}: compressed data is corrupt ({e})") from None

        if len(data) != expected:
            raise mpqpack.MpqError(f"{where}: decompressed to {len(data)} bytes instead of {expected}")

        return data

    def hash_entries(self, name: str) -> list[mpqpack.HashEntry]:
        """Every live hash entry of name (one per locale and platform)."""
        a = mpqpack.hash_string(name, mpqpack.HASH_NAME_A)
        b = mpqpack.hash_string(name, mpqpack.HASH_NAME_B)
        return [e for e in self.hashes if e.name_a == a and e.name_b == b
                and e.block_index not in (mpqpack.HASH_ENTRY_EMPTY, mpqpack.HASH_ENTRY_DELETED)]


# --- the realm's archives --------------------------------------------------------------------------------------


@dataclass
class Archive:
    path: str  # on disk
    client_path: str  # Data\patch-Z.MPQ, Data\enUS\patch-enUS-4.MPQ
    group: int  # 1: patch-?.MPQ group, 0: patch.MPQ / patch-<locale>.MPQ (below every group-1 archive)
    pack: str | None  # the optional pack it belongs to
    reader: PatchArchive | None = None
    error: str = ""

    @property
    def name(self) -> str:
        return self.client_path.split("\\")[-1]

    def rank(self) -> tuple:
        return (self.group, sort_key(self.client_path))

    def has(self, name: str) -> bool:
        return bool(self.reader) and self.reader.has_file(name)

    def read(self, name: str) -> bytes:
        if self.reader is None:
            raise PatchError(f"{self.name}: {self.error}")

        try:
            return self.reader.read(name)
        except mpqpack.MpqError as e:
            raise PatchError(f"{self.name}: {e}") from None


def pack_of(client_path: str, packs: dict[str, list[str]]) -> str | None:
    rel = client_path.replace("\\", "/").casefold()
    base = rel.split("/")[-1]

    for pack, patterns in packs.items():
        for pattern in patterns:
            pattern = pattern.replace("\\", "/").casefold()

            if fnmatch.fnmatchcase(rel if "/" in pattern else base, pattern):
                return pack

    return None


@dataclass
class PatchSet:
    archives: list[Archive] = field(default_factory=list)  # lowest priority first
    packs: dict[str, list[str]] = field(default_factory=dict)
    folder: str = ""

    @classmethod
    def scan(cls, folder: str, packs: dict[str, list[str]] | None = None) -> "PatchSet":
        r"""The patch archives in folder: the realm's patch folder (patch-?.MPQ, <locale>\patch-<locale>-?.MPQ) or a
        game's Data folder (a folder holding a Data folder is taken as the game folder)."""
        if os.path.isdir(os.path.join(folder, "Data")):
            folder = os.path.join(folder, "Data")

        if not os.path.isdir(folder):
            raise PatchError(f"{folder} is not a folder")

        packs = packs or {}
        found = []

        def add(path: str, client_path: str, group: int):
            if os.path.isfile(path):
                found.append(Archive(path, client_path, group, pack_of(client_path, packs)))

        for entry in sorted(os.listdir(folder)):
            path = os.path.join(folder, entry)

            if _SINGLE.fullmatch(entry):
                add(path, f"Data\\{entry}", 1)
            elif entry.lower() == "patch.mpq":
                add(path, f"Data\\{entry}", 0)
            elif os.path.isdir(path) and entry.lower() in {c.lower() for c in LOCALES}:
                for sub in sorted(os.listdir(path)):
                    if re.fullmatch(rf"(?i)patch-{entry}-.\.mpq", sub):
                        add(os.path.join(path, sub), f"Data\\{entry}\\{sub}", 1)
                    elif sub.lower() == f"patch-{entry.lower()}.mpq":
                        add(os.path.join(path, sub), f"Data\\{entry}\\{sub}", 0)

        for archive in found:
            try:
                archive.reader = PatchArchive(archive.path)
            except (mpqpack.MpqError, OSError, struct.error) as e:
                archive.error = f"cannot be opened ({e})"

        found.sort(key=Archive.rank)
        return cls(found, dict(packs), folder)

    def close(self):
        for archive in self.archives:
            if archive.reader:
                archive.reader.close()

    def find(self, name: str) -> Archive | None:
        for archive in self.archives:
            if archive.name.lower() == name.lower():
                return archive

        return None

    def configurations(self) -> list[tuple[str, frozenset[str]]]:
        """(label, packs on) for every combination of the packs that have archives here, all packs on first."""
        present = sorted({a.pack for a in self.archives if a.pack})
        out = []

        for count in range(len(present), -1, -1):
            for combo in itertools.combinations(present, count):
                label = "all packs" if count == len(present) else ("no packs" if not combo else
                                                                   "packs " + "+".join(combo))
                out.append((label if present else "every player", frozenset(combo)))

        return out

    def active(self, packs_on: frozenset[str]) -> list[Archive]:
        return [a for a in self.archives if a.pack is None or a.pack in packs_on]

    def holders(self, name: str, packs_on: frozenset[str] | None = None) -> list[Archive]:
        """Archives holding name, lowest priority first (all archives when packs_on is None)."""
        pool = self.archives if packs_on is None else self.active(packs_on)
        return [a for a in pool if a.has(name)]

    def top(self, name: str, packs_on: frozenset[str]) -> Archive | None:
        holders = self.holders(name, packs_on)
        return holders[-1] if holders else None

    def unreadable(self) -> list[Archive]:
        return [a for a in self.archives if a.reader is None]


def outranks(candidate_client_path: str, others: list[Archive]) -> bool:
    """Whether an archive at candidate_client_path (in the patch-?.MPQ group) loads above every one of others."""
    key = (1, sort_key(candidate_client_path))
    return all(key > a.rank() for a in others if a.client_path.lower() != candidate_client_path.lower())


# --- rebuilding an archive with replaced files -----------------------------------------------------------------


def archive_contents(reader: PatchArchive, where: str) -> list[str]:
    """Every file of an archive by its (listfile) name, refusing archives MapForge could not copy whole."""
    names = reader.names()

    if not reader.has_file(mpqpack.LISTFILE):
        raise PatchError(f"{where} has no (listfile), so its files cannot be listed")

    listed = set()

    for name in names:
        entries = reader.hash_entries(name)

        if len({(e.locale, e.platform) for e in entries}) != len(entries) or any(e.locale or e.platform
                                                                               for e in entries):
            raise PatchError(f"{where}: {name} has locale-specific copies; MapForge keeps archives neutral")

        listed.update(e.block_index for e in entries)

    for special in mpqpack.SPECIAL_FILES:
        listed.update(e.block_index for e in reader.hash_entries(special))

    live = {e.block_index for e in reader.hashes
            if e.block_index not in (mpqpack.HASH_ENTRY_EMPTY, mpqpack.HASH_ENTRY_DELETED)}
    unlisted = live - listed

    if unlisted:
        raise PatchError(f"{where} holds {len(unlisted)} file(s) its (listfile) does not name; rebuilding it would "
                         "lose them")

    return names


def rebuild(source: Archive, replacements: dict[str, str], out_path: str, staging: str) -> list[str]:
    """Write out_path: every file of source, with replacements {archive name: file on disk} replacing or adding
    files. Returns the names that were replaced (the others were added)."""
    if source.reader is None:
        raise PatchError(f"{source.name}: {source.error}")

    names = archive_contents(source.reader, source.name)
    keys = {mpqpack.name_key(n): n for n in names}
    replaced = [keys[mpqpack.name_key(n)] for n in replacements if mpqpack.name_key(n) in keys]

    if os.path.isdir(staging):
        shutil.rmtree(staging)

    os.makedirs(staging)
    items = []

    try:
        for i, name in enumerate(names):
            if mpqpack.name_key(name) in {mpqpack.name_key(n) for n in replacements}:
                continue

            path = os.path.join(staging, f"{i:06d}")

            with open(path, "wb") as f:
                f.write(source.read(name))

            items.append((name, path))

        items += list(replacements.items())
        mpqpack.write_archive_streaming(out_path, items)
    except mpqpack.MpqError as e:
        raise PatchError(f"writing {out_path}: {e}") from None
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    return replaced
