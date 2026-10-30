"""The client's emoji header (WoW/Common/BleakholdEmoji.h): kit range and bubble timeline, checked by compiling
client_header_test.cpp with the host C++ compiler (skipped when there is none)."""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
TOOL_DIR = os.path.dirname(HERE)                          # Tools/EmojiForge
REPO = os.path.dirname(os.path.dirname(TOOL_DIR))
if TOOL_DIR not in sys.path:
    sys.path.insert(0, TOOL_DIR)

HEADER = os.path.join(REPO, "WoW", "Common", "BleakholdEmoji.h")
SOURCE = os.path.join(HERE, "client_header_test.cpp")


def find_compiler():
    for name in (os.environ.get("CXX"), "c++", "g++", "clang++"):
        if name and shutil.which(name):
            return shutil.which(name)
    return None


class ClientHeaderTest(unittest.TestCase):
    def test_header_compiles_and_checks_pass(self):
        self.assertTrue(os.path.isfile(HEADER), HEADER)
        cxx = find_compiler()
        if not cxx:
            self.skipTest("no C++ compiler (c++, g++, clang++ or $CXX)")
        with tempfile.TemporaryDirectory() as tmp:
            exe = os.path.join(tmp, "client_header_test" + (".exe" if os.name == "nt" else ""))
            build = subprocess.run([cxx, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-I" + REPO, SOURCE, "-o", exe],
                                   capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, "compile failed:\n" + build.stdout + build.stderr)
            run = subprocess.run([exe], capture_output=True, text=True, timeout=60)
            self.assertEqual(run.returncode, 0, "checks failed:\n" + run.stdout + run.stderr)


if __name__ == "__main__":
    unittest.main()
