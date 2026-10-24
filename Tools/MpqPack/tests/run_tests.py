"""Run the MpqPack tests: python3 -I Tools/MpqPack/tests/run_tests.py"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))

if __name__ == "__main__":
    suite = unittest.defaultTestLoader.discover(HERE, top_level_dir=os.path.dirname(HERE))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
