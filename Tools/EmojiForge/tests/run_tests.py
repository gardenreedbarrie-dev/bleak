"""Run the EmojiForge tests: python3 -I Tools/EmojiForge/tests/run_tests.py"""

import os
import sys
import unittest

sys.dont_write_bytecode = True  # keep the repository free of __pycache__

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL_DIR = os.path.dirname(HERE)

if __name__ == "__main__":
    suite = unittest.defaultTestLoader.discover(HERE, pattern="test_*.py", top_level_dir=TOOL_DIR)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
