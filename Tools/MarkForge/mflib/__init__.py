"""MarkForge library: Bleakhold's own glowing body marks and eye sprites, drawn from a character model's own UVs.

Modules:
  model    the character M2 + skin as the compositor sees it (naked type-1 geosets, eye-glow geosets, 1703 texture)
  atlas    the 512x512 component atlas: per texel 3D position/normal/geoset, UV seams, keep-out zones, garment mask
  coords   per-island charts in metres (arms and legs wrap, torso mirrors, head is a front decal) and landmarks
  designs  designs/<RaceFile>.json -> signed distance fields of strokes and stamps on those charts
  draw     line core + halo, colour ramps, the mark and _Glow layers, mips and pal8 BLP bytes, the seam/keep-out gates
  eyes     eye sprites recoloured from each model's own deathKnightEyeGlow layout
  preview  texture sheets and front/back day/night renders (scratch only, never committed)
  archive  where files come from: a plain folder (dev) or the client's archive overlay (RaceForge's view), BLP decode

numpy is required (the VPS check tests for it); Pillow is not used.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.dirname(HERE)
REPO = os.path.normpath(os.path.join(TOOL, "..", ".."))
sys.dont_write_bytecode = True

# Read-only imports from sibling tools. ModelForge's package is also called mflib, so its m2check is loaded by file
# path in model.py, never through sys.path.
for _sub in ("Tools/BlpConvert", "Tools/RaceForge"):
    _p = os.path.join(REPO, _sub)
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.append(_p)

VERSION = 2  # bump when any output byte can change; recorded in marks_manifest.json (2: order-proof charts, cracks)


class MarkForgeError(Exception):
    pass


def need_numpy():
    try:
        import numpy  # noqa: F401
    except ImportError:
        raise MarkForgeError("MarkForge needs numpy (Debian/Ubuntu: apt install python3-numpy; or pip install "
                             "numpy)") from None
