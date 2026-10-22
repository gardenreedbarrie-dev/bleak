# MpqPack

Builds MPQ archives that the 3.3.5a client (and this decompilation) loads as patch archives. The client reads DBC
files only from archives, never from loose files under `Data\`, so data changes such as the Bleakhold races
(`Tools/RaceForge`) have to ship in one.

It needs Python 3.10 or newer and nothing else. Run it with `-I` (isolated mode); it does not depend on the current
folder or on installed packages.

No game data is in this folder. MpqPack only packs the files you give it.

## Commands

On Windows the Python launcher is `py -3`; elsewhere use `python3`.

```bat
:: Pack every file under a folder. Archive paths are the paths relative to that folder, with backslashes:
:: C:\bleakhold\mpq-src\DBFilesClient\ChrRaces.dbc becomes DBFilesClient\ChrRaces.dbc.
py -3 -I Tools\MpqPack\mpqpack.py pack C:\bleakhold\mpq-src C:\WoW335\Data\patch-R.MPQ

:: Check an archive against the rules of the client's reader, and that it holds exactly the folder's files.
py -3 -I Tools\MpqPack\mpqpack.py verify C:\WoW335\Data\patch-R.MPQ C:\bleakhold\mpq-src

:: List or extract an archive written by MpqPack.
py -3 -I Tools\MpqPack\mpqpack.py list C:\WoW335\Data\patch-R.MPQ
py -3 -I Tools\MpqPack\mpqpack.py extract C:\WoW335\Data\patch-R.MPQ C:\bleakhold\check

:: Built-in checks of the hashing, the encryption and a round trip.
py -3 -I Tools\MpqPack\mpqpack.py selftest
```

`pack` options: `--no-compress` stores every file as is, `--single-unit` compresses each file as one block instead
of 4 KB sectors, `--sector-shift N` sets the sector size to `512 << N` (default 3, the stock 4096). The reader in
`list`, `extract` and `verify` handles uncompressed and zlib files. It cannot read Blizzard's own archives, which use
other compression and encryption.

## Which name to use

The client opens every `Data\patch-?.MPQ` (one character) and `Data\<locale>\patch-<locale>-?.MPQ` as patch
archives, then `Data\patch.MPQ` and `Data\<locale>\patch-<locale>.MPQ` (`WoW/Source/WowServices/PatchFiles.cpp`,
`OpenArchives` in `WoW/Source/Client.cpp`). It sorts the first group by full path, case-insensitively, and the path
that sorts last gets the highest priority. When two archives hold the same file, the higher priority wins.

- Any `Data\patch-<letter>.MPQ` outranks every locale archive (`Data\enUS\...` sorts before `Data\patch-...`). The
  stock DBCs live in the locale archives, so a patch with DBCs in `Data\` replaces them.
- Digits sort before letters, and letters in alphabetical order: `patch-3` < `patch-A` < `patch-R` < `patch-Z`.
- Use one letter or digit. Use a name that sorts after every other patch holding the same files. RaceForge
  suggests `patch-R.MPQ`. If another patch of yours also holds `DBFilesClient\ChrRaces.dbc` (or any table RaceForge
  writes), build RaceForge from that patch's DBCs and give the race archive a later letter.

## What the client checks, and what MpqPack writes

From the reader in `Engine/Source/BlizzardCore/Source/Packages/Mopaq`:

| Client code | Requirement | MpqPack |
|---|---|---|
| `s_OpenArchive` | `MPQ\x1A` header; format 0 needs a header size of 32, format 1 a size of 44; both table positions inside the archive; a file larger than 44 bytes | Format 0 with a 32-byte header at offset 0 |
| `InitializeTables` | The hash table's size on disk is `blockTablePos - hashTablePos`; the block table's is `archiveEnd - blockTablePos`. If either differs from 16 bytes per entry, the client reads that table as compressed | The hash table directly before the block table, and the block table last |
| `InitializeTables` | Tables encrypted with the keys of `(hash table)` (0xC3AF3770) and `(block table)` (0xEC83B3A3) | Both encrypted with those keys |
| `SearchHashTable` | The table size is a power of two (indices are masked with `size - 1`); a slot with block index -1 ends a search | A power of two, at most half full, locale 0 and platform 0 on every entry |
| `SFileOpenFileEx` | `FILE_EXISTS` set; without compression flags the stored size must equal the file size | `FILE_EXISTS`, or `FILE_EXISTS \| FILE_COMPRESS` (`\| FILE_SINGLE_UNIT` with `--single-unit`) |
| `IOMpqReadUnit::LoadSectorTable` | Sector offsets increasing and inside the stored size; a first offset larger than the table announces sector checksums | One offset per sector plus the end, the first one equal to the table size, no checksums |
| `DecompressBlocks`, `SComp::Decompress` | A sector stored at its full size is raw; a smaller one starts with a compression type byte (0x02 = zlib) and must inflate to exactly the sector size | zlib with type byte 0x02, and only when that is smaller than the raw sector |
| `FillNewHashTable` | Patch archives are opened with flag 0x400. The client then rebuilds its lookup from `(listfile)` and drops the classic hash table, so a file that is not listed cannot be found. The parser ignores a last line with no line end. A name listed twice, or a missing `(attributes)`, makes it keep the classic table instead | A `(listfile)` naming every file once, each line ending with CR LF, and an `(attributes)` file with the CRC32 and MD5 of every block |

Patch archives are opened with flags `0xC00`, which runs both lookups: the classic hash table during
`FillNewHashTable`, and the listfile lookup afterwards.

## Tests

```bat
py -3 -I Tools\MpqPack\tests\run_tests.py
```

or `python3 -I -m unittest discover -s Tools/MpqPack/tests -t Tools/MpqPack`. The tests check the hash values
against the published ones, compare the crypt table with `s_cryptTable` in `MPQEncrypt.cpp`, and round-trip archives
in every packing mode. They also check the table layout field by field, and that `verify` catches a corrupt file, a
listfile with no final line end and a misplaced table.
