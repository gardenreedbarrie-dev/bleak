"""Run the MapForge tests: python3 -I Tools/MapForge/tests/run_tests.py

The tests folder itself is the top level, so test modules import their helpers by plain name (test_terrain_support)
or through the tests package (tests.synth_dbc, with Tools/MapForge on sys.path); both work.
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(HERE))
    suite = unittest.defaultTestLoader.discover(HERE, top_level_dir=HERE)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
