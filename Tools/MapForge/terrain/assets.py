"""Optional real-asset lookups: model bounds from extracted 3.3.5a client files.

MapForge ships no Blizzard data. On a machine that has the client's files extracted to a folder (the VPS), pass
`--assets DIR` and placements without explicit `bounds` get them from the models themselves:

- WMO root: MOHD (SMOHeader in WoW/Source/WorldClient/MapObj.h) bounding box at +0x24, min xyz then max xyz;
- M2: header bounding box at +0xA0 (ThirdParty/WarcraftXL/include/structure/m2/M2Format.hpp). A ".mdx" name is
  looked up as ".m2", like the client's model loader.

Paths are matched case-insensitively with backslashes or slashes.
"""

from __future__ import annotations

import os
import struct


class AssetFolder:
    def __init__(self, root: str):
        self.root = root
        self._index: dict[str, str] | None = None

    def _build_index(self) -> dict[str, str]:
        index = {}
        for base, _dirs, files in os.walk(self.root):
            for f in files:
                full = os.path.join(base, f)
                rel = os.path.relpath(full, self.root).replace(os.sep, "\\").lower()
                index[rel] = full
        return index

    def find(self, client_path: str) -> str | None:
        if self._index is None:
            self._index = self._build_index()
        key = client_path.replace("/", "\\").lower()
        hit = self._index.get(key)
        if hit is None and key.endswith(".mdx"):
            hit = self._index.get(key[:-4] + ".m2")
        return hit

    def model_bounds(self, client_path: str):
        """((min x, y, z), (max x, y, z)) in model space, or None."""
        path = self.find(client_path)
        if path is None:
            return None
        with open(path, "rb") as f:
            data = f.read()
        if client_path.lower().endswith(".wmo"):
            return wmo_bounds(data)
        return m2_bounds(data)


def wmo_bounds(data: bytes):
    pos = 0
    while pos + 8 <= len(data):
        magic = data[pos:pos + 4][::-1]
        size = struct.unpack_from("<I", data, pos + 4)[0]
        if magic == b"MOHD" and size >= 0x3C and pos + 8 + 0x3C <= len(data):
            v = struct.unpack_from("<6f", data, pos + 8 + 0x24)
            return (v[0:3], v[3:6])
        pos += 8 + size
    return None


def m2_bounds(data: bytes):
    if len(data) < 0xB8 or data[:4] != b"MD20":
        return None
    v = struct.unpack_from("<6f", data, 0xA0)
    return (v[0:3], v[3:6])
