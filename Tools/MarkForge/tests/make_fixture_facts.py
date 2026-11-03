#!/usr/bin/env python3
"""Writes tests/fixture_bad_facts.inc: the facts of markforge.py fixture's Bad files (size, mip count, alpha bits,
palette, mip offsets, file size) and what the fixture manifest says the exe does with each, as C++ initialisers for
test_marks_core.cpp. Numbers only, no art. test_cli.py checks that the file is what this writes.

    python3 -I Tools/MarkForge/tests/make_fixture_facts.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.dont_write_bytecode = True

import mflib  # noqa: E402,F401  (puts BlpConvert on sys.path)
from mflib import fixture as FX  # noqa: E402

PATH = os.path.join(HERE, "fixture_bad_facts.inc")


def files() -> dict:
    grid, grid_glow = FX.section_grid()
    return {f"Character\\BleakholdMarks\\Fixture\\Bad\\{name}.blp": data
            for name, data in FX.bad_files(grid, grid_glow).items()}


def text() -> str:
    return FX.facts_cpp(files())


if __name__ == "__main__":
    with open(PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write(text())
    print(f"wrote {PATH}")
