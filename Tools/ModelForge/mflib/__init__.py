"""ModelForge library: original procedural M2 props for the Bleakhold café (CAFE.SPEC.md section 5).

Modules:
  geom       mesh primitives, deformers, charts (UV islands in yards)
  material   material presets (blend mode, flags, coord combo)
  m2write    static M2 v264 writer          skinwrite  the matching <Name>00.skin
  m2check    independent parser/validator that mirrors the client's M2Init
  tex        procedural texture generators   font  lettering   emblem  original emblem shapes
  atlas      chart packing                   bake  texture-space light bake    mips  gutters, mips, BLP output
  render     software rasterizer             preview  the preview modes and contact sheets
  build      turns a prop (props/*.py) into files, manifest entries and previews
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.dirname(HERE)
REPO = os.path.normpath(os.path.join(TOOL, "..", ".."))
sys.dont_write_bytecode = True

# Read-only imports from sibling tools (section 7.1: WS-G never edits them).
for _sub in ("Tools/BlpConvert", "Tools/UiLint", "Tools/MpqPack", "Tools/MapForge"):
    _p = os.path.join(REPO, _sub)
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.append(_p)
