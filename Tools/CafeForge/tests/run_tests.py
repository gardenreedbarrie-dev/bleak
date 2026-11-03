"""Run the CafeForge tests: python3 -I Tools/CafeForge/tests/run_tests.py

Every test_*.py here: the catalogue and generated files (test_catalog.py, test_gen.py) and the packaging side (the
spell wrapper, doctor on synthetic patch sets, the build, its archives, checks and art with ModelForge's real output,
the server SQL, the CLI). The tests folder is the top level, so test modules import their helpers by plain name
(cafe_synth); each one puts Tools/CafeForge on sys.path itself.
Set CAFEFORGE_SERVER_SRC when the bleakserv checkout is not next to this repository.
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True  # no tests/__pycache__ in the repository

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(HERE))
    suite = unittest.defaultTestLoader.discover(HERE, pattern="test_*.py", top_level_dir=HERE)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
