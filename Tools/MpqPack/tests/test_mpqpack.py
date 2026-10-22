"""Tests for MpqPack. Run from the repository root with

    python3 -I -m unittest discover -s Tools/MpqPack/tests -t Tools/MpqPack

or with python3 -I Tools/MpqPack/tests/run_tests.py.
"""

import hashlib
import os
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL_DIR = os.path.dirname(HERE)

if TOOL_DIR not in sys.path:
    sys.path.insert(0, TOOL_DIR)

import mpqpack  # noqa: E402

SAMPLE_FILES = [
    ("DBFilesClient\\Empty.dbc", b""),
    ("DBFilesClient\\Tiny.dbc", b"abc"),
    ("DBFilesClient\\Four.dbc", b"abcd"),
    ("DBFilesClient\\OneSector.dbc", b"A" * 4096),
    ("DBFilesClient\\SectorPlusOne.dbc", bytes(i % 7 for i in range(4097))),
    ("DBFilesClient\\Incompressible.dbc", hashlib.sha256(b"seed").digest() * 700),
    ("DBFilesClient\\Large.dbc", b"".join(struct.pack("<I", i) for i in range(50000))),
    ("Interface\\Glues\\Deep\\Path\\Text.txt", b"line\r\n" * 3000),
]

MODES = [
    {"compress": True},
    {"compress": False},
    {"compress": True, "single_unit": True},
    {"compress": True, "sector_shift": 0},
    {"compress": True, "sector_shift": 6},
]


def raw_tables(data):
    """Header fields plus the decrypted hash and block tables, read independently of MpqArchive."""
    magic, header_size, archive_size, version, shift, hash_pos, block_pos, hash_size, block_size = struct.unpack_from("<IIIHHIIII", data, 0)
    hashes = mpqpack.decrypt_block(data[hash_pos:hash_pos + 16 * hash_size], mpqpack.hash_string("(hash table)", 3))
    blocks = mpqpack.decrypt_block(data[block_pos:block_pos + 16 * block_size], mpqpack.hash_string("(block table)", 3))
    hash_rows = [struct.unpack_from("<IIHBBI", hashes, 16 * i) for i in range(hash_size)]
    block_rows = [struct.unpack_from("<IIII", blocks, 16 * i) for i in range(block_size)]
    return (magic, header_size, archive_size, version, shift, hash_pos, block_pos, hash_size, block_size), hash_rows, block_rows


class CryptoTests(unittest.TestCase):
    def test_known_hash_values(self):
        for name, kind, expected in mpqpack.KNOWN_HASHES:
            self.assertEqual(mpqpack.hash_string(name, kind), expected, (name, kind))

    def test_attributes_hash_values(self):
        # Name hashes StormLib and the format documentation give for "(attributes)".
        self.assertEqual(mpqpack.hash_string("(attributes)", 1), 0xD38437CB)
        self.assertEqual(mpqpack.hash_string("(attributes)", 2), 0x07DFEAEC)

    def test_crypt_table_matches_client(self):
        source = mpqpack.find_client_crypt_source()

        if not source:
            self.skipTest("MPQEncrypt.cpp of the decompilation not found")

        self.assertEqual(mpqpack.parse_client_crypt_table(source), list(mpqpack.CRYPT_TABLE))

    def test_hash_ignores_case_and_slash(self):
        for kind in range(4):
            self.assertEqual(mpqpack.hash_string("dbfilesclient/chrraces.dbc", kind), mpqpack.hash_string("DBFilesClient\\ChrRaces.dbc", kind))

    def test_encrypt_round_trip(self):
        data = os.urandom(1000) + b"xy"

        for key in (0, 1, 0xC3AF3770, 0xFFFFFFFF):
            encrypted = mpqpack.encrypt_block(data, key)
            self.assertNotEqual(encrypted[:16], data[:16])
            self.assertEqual(encrypted[-2:], b"xy")  # a partial dword is left alone, like the client
            self.assertEqual(mpqpack.decrypt_block(encrypted, key), data)


class WriterTests(unittest.TestCase):
    def test_round_trip_every_mode(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                archive = mpqpack.MpqArchive(mpqpack.build_archive(SAMPLE_FILES, **mode))
                report = archive.verify()
                self.assertEqual(report.problems, [])
                self.assertTrue(report.lookup_mode.startswith("listfile"))

                for name, content in SAMPLE_FILES:
                    self.assertEqual(archive.read(name), content, name)
                    self.assertEqual(archive.read(name.lower().replace("\\", "/")), content, name)

                self.assertFalse(archive.has_file("DBFilesClient\\Missing.dbc"))

    def test_layout_matches_client_reader(self):
        data = mpqpack.build_archive(SAMPLE_FILES)
        header, hashes, blocks = raw_tables(data)
        magic, header_size, archive_size, version, shift, hash_pos, block_pos, hash_size, block_size = header

        self.assertEqual(magic, 0x1A51504D)
        self.assertEqual((header_size, version, shift), (32, 0, 3))
        self.assertEqual(archive_size, len(data))
        self.assertEqual(hash_size & (hash_size - 1), 0)
        # Hash table directly before the block table, block table last (InitializeTables' disk size rules).
        self.assertEqual(block_pos - hash_pos, 16 * hash_size)
        self.assertEqual(len(data) - block_pos, 16 * block_size)
        self.assertEqual(block_size, len(SAMPLE_FILES) + 2)

        used = [row for row in hashes if row[5] != 0xFFFFFFFF]
        self.assertEqual(len(used), block_size)

        for name_a, name_b, locale, platform, reserved, block_index in used:
            self.assertEqual((locale, platform), (0, 0))
            self.assertLess(block_index, block_size)

        for row in hashes:
            if row[5] == 0xFFFFFFFF:
                self.assertEqual(row[:4], (0xFFFFFFFF, 0xFFFFFFFF, 0xFFFF, 0xFF))

        for offset, compressed, size, flags in blocks:
            self.assertTrue(flags & mpqpack.FILE_EXISTS)
            self.assertEqual(flags & ~(mpqpack.FILE_EXISTS | mpqpack.FILE_COMPRESS), 0)

            if not flags & mpqpack.FILE_COMPRESS:
                self.assertEqual(compressed, size)

            self.assertLessEqual(offset + compressed, hash_pos)

    def test_sector_table_and_zlib_type_byte(self):
        content = b"0123456789" * 2000
        data = mpqpack.build_archive([("A\\B.txt", content)])
        archive = mpqpack.MpqArchive(data)
        block = archive.blocks[archive.find_block("A\\B.txt")]
        self.assertEqual(block.flags, mpqpack.FILE_EXISTS | mpqpack.FILE_COMPRESS)

        stored = data[block.offset:block.offset + block.compressed_size]
        sectors = (len(content) + 4095) // 4096
        offsets = struct.unpack_from(f"<{sectors + 1}I", stored)
        self.assertEqual(offsets[0], 4 * (sectors + 1))
        self.assertEqual(offsets[-1], block.compressed_size)

        for i in range(sectors):
            chunk = stored[offsets[i]:offsets[i + 1]]
            self.assertEqual(chunk[0], 0x02)
            self.assertEqual(zlib.decompress(chunk[1:]), content[4096 * i:4096 * (i + 1)])

    def test_listfile_and_attributes(self):
        archive = mpqpack.MpqArchive(mpqpack.build_archive(SAMPLE_FILES))
        listfile = archive.read("(listfile)")
        self.assertTrue(listfile.endswith(b"\r\n"))
        self.assertEqual(sorted(archive.listfile_names()), sorted(name for name, _ in SAMPLE_FILES))

        attributes = archive.read("(attributes)")
        count = len(archive.blocks)
        version, flags = struct.unpack_from("<II", attributes)
        self.assertEqual((version, flags), (100, 5))
        self.assertEqual(len(attributes), 8 + 20 * count)

        crcs = struct.unpack_from(f"<{count}I", attributes, 8)
        md5s = [attributes[8 + 4 * count + 16 * i:8 + 4 * count + 16 * (i + 1)] for i in range(count)]
        attributes_block = archive.find_block("(attributes)")

        for i in range(count):
            if i == attributes_block:
                self.assertEqual((crcs[i], md5s[i]), (0, bytes(16)))
            else:
                content = archive.read_block(i)
                self.assertEqual(crcs[i], zlib.crc32(content))
                self.assertEqual(md5s[i], hashlib.md5(content).digest())

    def test_output_is_deterministic(self):
        self.assertEqual(mpqpack.build_archive(SAMPLE_FILES), mpqpack.build_archive(list(reversed(SAMPLE_FILES))))

    def test_duplicates_and_bad_names_rejected(self):
        with self.assertRaises(mpqpack.MpqError):
            mpqpack.build_archive([("DBFilesClient\\A.dbc", b"1"), ("dbfilesclient/a.DBC", b"2")])

        for bad in ("", "\\A", "A\\", "A\\\\B", "A\\..\\B", "(listfile)", "A\x01B", "x" * 300):
            with self.subTest(name=bad), self.assertRaises(mpqpack.MpqError):
                mpqpack.build_archive([(bad, b"1")])

    def test_many_files(self):
        files = [(f"Dir{i % 7}\\File{i:05d}.bin", struct.pack("<I", i) * (i % 50)) for i in range(3000)]
        archive = mpqpack.MpqArchive(mpqpack.build_archive(files))
        self.assertEqual(archive.verify().problems, [])
        self.assertEqual(archive.header.hash_table_size, 8192)

        for name, content in files[::97]:
            self.assertEqual(archive.read(name), content)


class VerifyTests(unittest.TestCase):
    def test_listfile_without_line_end_is_reported(self):
        original = mpqpack.make_listfile

        try:
            mpqpack.make_listfile = lambda names: "\r\n".join(names).encode("utf-8")
            data = mpqpack.build_archive(SAMPLE_FILES)
        finally:
            mpqpack.make_listfile = original

        problems = mpqpack.MpqArchive(data).verify().problems
        self.assertTrue(any("line end" in p for p in problems), problems)
        self.assertTrue(any("not named by the (listfile)" in p for p in problems), problems)

    def test_corrupt_data_is_reported(self):
        data = bytearray(mpqpack.build_archive(SAMPLE_FILES))
        archive = mpqpack.MpqArchive(bytes(data))
        block = archive.blocks[archive.find_block("DBFilesClient\\Large.dbc")]
        data[block.offset + 100] ^= 0xFF
        problems = mpqpack.MpqArchive(bytes(data)).verify().problems
        self.assertTrue(problems)

    def test_misplaced_tables_are_reported(self):
        # Bytes after the block table do not matter: the client ends the archive at the end of its last table.
        data = mpqpack.build_archive(SAMPLE_FILES) + b"\0" * 64
        self.assertEqual(mpqpack.MpqArchive(data).verify().problems, [])

        swapped = bytearray(mpqpack.build_archive(SAMPLE_FILES))
        fields = list(struct.unpack_from("<IIIHHIIII", swapped, 0))
        fields[7] //= 2  # claim a smaller hash table: its disk size no longer matches
        struct.pack_into("<IIIHHIIII", swapped, 0, *fields)
        problems = mpqpack.MpqArchive(bytes(swapped)).verify().problems
        self.assertTrue(any("hash table is not directly in front" in p for p in problems), problems)


class CommandLineTests(unittest.TestCase):
    def run_tool(self, *args):
        return subprocess.run([sys.executable, "-I", os.path.join(TOOL_DIR, "mpqpack.py"), *args], capture_output=True, text=True)

    def test_pack_verify_extract(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "src")

            for name, content in SAMPLE_FILES:
                path = os.path.join(src, *name.split("\\"))
                os.makedirs(os.path.dirname(path), exist_ok=True)

                with open(path, "wb") as f:
                    f.write(content)

            out = os.path.join(tmp, "patch-R.MPQ")
            result = self.run_tool("pack", src, out)
            self.assertEqual(result.returncode, 0, result.stderr)

            result = self.run_tool("verify", out, src)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("OK", result.stdout)

            result = self.run_tool("list", out)
            self.assertEqual(result.returncode, 0)
            self.assertIn("DBFilesClient\\Large.dbc", result.stdout)

            dest = os.path.join(tmp, "dest")
            result = self.run_tool("extract", out, dest)
            self.assertEqual(result.returncode, 0, result.stderr)

            for name, content in SAMPLE_FILES:
                with open(os.path.join(dest, *name.split("\\")), "rb") as f:
                    self.assertEqual(f.read(), content)

            # The output must not land inside the folder being packed.
            result = self.run_tool("pack", src, os.path.join(src, "x.MPQ"))
            self.assertNotEqual(result.returncode, 0)

    def test_selftest_command(self):
        result = self.run_tool("selftest")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("selftest passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
