"""The two markers of patch-4.MPQ (section 6.2): the addon's patch marker texture and CafeForge's own marker file.

- Interface\\Bleakhold\\Cafe\\Marker.blp: a tiny texture CafeForge draws itself (no game data). An addon cannot list
  archive contents, but Texture:SetTexture(path) only succeeds for a file the client can open, so a file that exists
  nowhere else proves the player has the café's patch (CAFE.SPEC.md 4.8; Tools/MapForge/dbc/marker.py does the same
  for the map patch). The picture: a dark roast ring around a crema core on a transparent background, 8 x 8, DXT5
  with every mip level (Tools/BlpConvert), the same bytes on every run.
- Bleakhold\\Cafe\\cafeforge.txt: says that CafeForge wrote the archive (the tool and its version, the build time and
  the host) and lists the sha256 of every other file in it. A patch-4.MPQ without it is another patch's name and is
  never replaced; ModelForge's test patch has one that says only "test", which is refused too (cflib/plan.py).
"""

import hashlib
import os
import socket
import sys
import time

from . import config as cfgmod

_BLP = os.path.join(cfgmod.TOOLS_DIR, "BlpConvert")
if os.path.isdir(_BLP) and _BLP not in sys.path:
    sys.path.append(_BLP)

import blpconvert  # noqa: E402  (Tools/BlpConvert)

TOOL = "CafeForge"
VERSION = 1
TEXTURE = cfgmod.MARKER_TEXTURE
SIZE = 8
RING = (74, 44, 26)
CORE = (216, 185, 138)  # the café's crema accent, D8B98A


def _coverage(distance, inner, outer):
    """1 inside [inner, outer], fading to 0 over one pixel outside it."""
    if distance < inner:
        return max(0.0, 1.0 - (inner - distance))
    if distance > outer:
        return max(0.0, 1.0 - (distance - outer))
    return 1.0


def marker_image():
    img = blpconvert.Image(SIZE, SIZE)
    centre = SIZE / 2.0
    for y in range(SIZE):
        for x in range(SIZE):
            dx = x + 0.5 - centre
            dy = y + 0.5 - centre
            d = (dx * dx + dy * dy) ** 0.5
            ring = _coverage(d, 2.4, 3.6)
            core = _coverage(d, -1.0, 1.6)
            alpha = max(ring, core)
            rgb = CORE if core >= ring else RING
            i = (y * SIZE + x) * 4
            img.data[i:i + 4] = bytes((rgb[0], rgb[1], rgb[2], int(alpha * 255.0 + 0.5)))
    return img


def write_marker_blp(path):
    """The marker texture as a BLP2 file the 3.3.5a client loads; returns path."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    blpconvert.convert(marker_image(), path, fmt="dxt5", jobs=1)
    return path


def blp_problems(path):
    """What the client would refuse in a BLP file (Tools/BlpConvert check_blp)."""
    try:
        _, _, problems = blpconvert.check_blp(path)
    except (OSError, ValueError) as ex:
        return [str(ex)]
    return problems


def sha256_of(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def marker_text(files, built=None, host=None, what="cafeforge.py build"):
    """The marker file: files is {archive path: sha256} of every other file of the archive."""
    built = built or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    host = host or socket.gethostname()
    lines = ["Written by Tools/CafeForge (%s). CafeForge rebuilds this archive on every build that changes it;" % what,
             "nothing else may write it.",
             "tool %s %d" % (TOOL, VERSION),
             "built %s" % built,
             "host %s" % host]
    lines += ["sha256 %s %s" % (sha, name) for name, sha in sorted(files.items(), key=lambda kv: kv[0].lower())]
    return "\n".join(lines) + "\n"


def parse_marker(text):
    """{"tool", "version", "built", "host", "files": {archive path: sha256}} of a marker file; None when it is not
    CafeForge's (ModelForge's test patch says only "test")."""
    out = {"tool": "", "version": 0, "built": "", "host": "", "files": {}}
    for line in text.splitlines():
        key, _, rest = line.strip().partition(" ")
        if key == "tool":
            name, _, version = rest.partition(" ")
            out["tool"] = name
            out["version"] = int(version) if version.isdigit() else 0
        elif key in ("built", "host"):
            out[key] = rest
        elif key == "sha256":
            sha, _, name = rest.partition(" ")
            if name:
                out["files"][name] = sha
    return out if out["tool"] == TOOL else None
