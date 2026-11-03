#!/usr/bin/env python3
"""ModelForge tests: python3 -I Tools/ModelForge/tests/run_tests.py [--models A,B] [--jobs N] [--update-golden]
                                                                 [-v] [pattern ...]

Builds every registered model (mflib/props; the cube and EspressoSW with textures at full size, section 5.9, the
others at --tex-scale 0.125), then runs test_*.py: writer -> checker round trips, every section 5.3 invariant
violated on purpose, the native harness (the client's own M2Init) when g++ exists, geometry, textures, gutters
and mips, lettering, emblems and the shared library, the rasterizer's pixel checks, budgets, sizes, readability,
decals at full size and the golden hashes. Exit code 0 = all passed. No game data is used.

  --models A,B   test only these models (sets MF_MODELS; the library tests still run)
  --jobs N       worker processes for the bake and the paint (sets MF_JOBS; default 2)
  pattern        only the test modules whose name contains it (e.g. props, shared, tex)
"""

import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True
if HERE not in sys.path:
    sys.path.insert(0, HERE)


def main(argv):
    argv = list(argv)
    for flag, env in (("--models", "MF_MODELS"), ("--jobs", "MF_JOBS")):
        if flag in argv:
            i = argv.index(flag)
            if i + 1 >= len(argv):
                raise SystemExit("%s needs a value" % flag)
            os.environ[env] = argv[i + 1]
            del argv[i:i + 2]
    verbosity = 2 if "-v" in argv else 1
    if "--update-golden" in argv:
        os.environ["MODELFORGE_UPDATE_GOLDEN"] = "1"
    patterns = [a for a in argv if not a.startswith("-")]
    import common  # noqa: E402  (after MF_MODELS / MF_JOBS are set)
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
    print("ModelForge tests: %d run in %.1fs, %d failures, %d errors, %d skipped; models: %s" % (
        result.testsRun, time.time() - t, len(result.failures), len(result.errors), len(result.skipped),
        ", ".join(common.selected_models()) or "none"))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
