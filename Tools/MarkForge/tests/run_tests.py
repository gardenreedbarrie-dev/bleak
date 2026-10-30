#!/usr/bin/env python3
"""MarkForge tests: python3 -I Tools/MarkForge/tests/run_tests.py [-v] [pattern ...]

Synthetic data only (the tube body, synthetic skins, underwear and CharSections): the pal8 BLP writer, BLP decoding,
the atlas, seams and keep-out zones, the charts, every design of the twelve races, the seam and keep-out gates, the
garment mask, eye sprites, the fixture, an end-to-end build of a synthetic package with --check and validate, and
the refusal to write inside the repository. Needs numpy. Exit code 0 = all passed.
"""

import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True
if HERE not in sys.path:
    sys.path.insert(0, HERE)

try:
    import numpy  # noqa: F401
except ImportError:
    print("MarkForge tests need numpy (apt install python3-numpy)")
    sys.exit(1)

import common  # noqa: E402


def main(argv):
    verbosity = 2 if "-v" in argv else 1
    patterns = [a for a in argv if not a.startswith("-")]
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for fn in sorted(os.listdir(HERE)):
        if fn.startswith("test_") and fn.endswith(".py"):
            mod = fn[:-3]
            if patterns and not any(p in mod for p in patterns):
                continue
            suite.addTests(loader.loadTestsFromName(mod))
    t = time.time()
    try:
        result = unittest.TextTestRunner(verbosity=verbosity).run(suite)
    finally:
        common.cleanup()
    print("MarkForge tests: %d run in %.1fs, %d failures, %d errors, %d skipped" % (
        result.testsRun, time.time() - t, len(result.failures), len(result.errors), len(result.skipped)))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
