#!/usr/bin/env python3
"""ModelForge tests: python3 -I Tools/ModelForge/tests/run_tests.py [--update-golden] [-v] [pattern ...]

Builds the unit cube and EspressoSW in full (section 5.9: textures at full size for these two), then runs
test_*.py: writer -> checker round trips, every section 5.3 invariant violated on purpose, the native harness
(the client's own M2Init) when g++ exists, geometry, textures, gutters and mips, lettering, the rasterizer's pixel
checks, budgets, sizes, readability and the golden hashes. Exit code 0 = all passed. No game data is used.
"""

import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import common  # noqa: E402


def main(argv):
    verbosity = 2 if "-v" in argv else 1
    if "--update-golden" in argv:
        os.environ["MODELFORGE_UPDATE_GOLDEN"] = "1"
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
    print("ModelForge tests: %d run in %.1fs, %d failures, %d errors, %d skipped" % (
        result.testsRun, time.time() - t, len(result.failures), len(result.errors), len(result.skipped)))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
