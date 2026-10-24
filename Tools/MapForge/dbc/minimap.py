r"""Minimap tiles and md5translate.trs.

The client asks for the key "<Map.directory>\map<X>_<YY>.blp" in Textures\Minimap\md5translate.trs and loads
Textures\Minimap\<value> (MinimapBuildSource, LoadMD5Names in WoW/Source/Ui/MinimapFrame.cpp). The value can be any
path below Textures\Minimap; it does not have to be an MD5 name. The trs is one global file: a patch that ships it
replaces the stock copy, so the written file is always the current trs (extracted from the realm's archives) with
this map's lines added. The parser (SStrTokenize over "\r\n") loses a last line with no line end, so every line,
the last one too, ends with CR LF.
"""

from __future__ import annotations

import os
import re

_TILE = re.compile(r"(?i)map(\d+)_(\d+)\.blp")


class TrsError(Exception):
    pass


def parse(data: bytes, where: str = "md5translate.trs") -> list[tuple[str, str]]:
    """(key, value) pairs the way the client reads them: dir: lines and lines without a tab are skipped, and a last
    line without a line end is lost."""
    out = []
    text = data.decode("utf-8", "surrogateescape")

    if text and not text.endswith(("\n", "\r")):
        cut = text.rfind("\n")
        lost = text[cut + 1:]

        if "\t" in lost:
            raise TrsError(f"{where}: the last line ({lost[:40]!r}) has no line end; the client would drop it")

        text = text[:cut + 1] if cut >= 0 else ""

    for line in re.split(r"\r\n|\r|\n", text):
        if not line or line.startswith("dir:"):
            continue

        key, tab, value = line.partition("\t")

        if tab:
            out.append((key, value))

    return out


def build(base_entries: list[tuple[str, str]], directory: str, tiles: list[tuple[int, int]]) -> bytes:
    """The merged trs: the realm's entries, minus this map's old lines, plus one line per tile. Keys are
    case-insensitive to the client (HASHKEY_STRI)."""
    prefix = f"{directory.lower()}\\"
    lines = [f"dir: {directory}"]
    seen = set()

    for key, value in base_entries:
        if key.lower().startswith(prefix):
            continue

        if key.lower() in seen:
            raise TrsError(f"md5translate.trs names {key} twice")

        seen.add(key.lower())
        lines.append(f"{key}\t{value}")

    for tx, ty in sorted(tiles):
        key = f"{directory}\\map{tx}_{ty:02d}.blp"
        lines.append(f"{key}\t{directory}\\map{tx}_{ty:02d}.blp")

    # Every line ends with CR LF; SStrTokenize would drop a last line without one.
    return "".join(line + "\r\n" for line in lines).encode("utf-8", "surrogateescape")


def collect_tiles(folder: str) -> dict[tuple[int, int], str]:
    """{(tx, ty): path} of the map<X>_<Y>.blp (or .png, to be converted) files in folder."""
    out = {}

    if not os.path.isdir(folder):
        raise TrsError(f"{folder} is not a folder")

    for entry in sorted(os.listdir(folder)):
        stem, ext = os.path.splitext(entry)

        if ext.lower() not in (".blp", ".png"):
            continue

        match = _TILE.fullmatch(stem + ".blp")

        if not match:
            raise TrsError(f"{folder}/{entry}: minimap tiles are named map<X>_<Y>.blp (or .png)")

        tile = (int(match.group(1)), int(match.group(2)))

        if tile in out:
            raise TrsError(f"{folder}: tile {tile} appears twice (.png and .blp)")

        out[tile] = os.path.join(folder, entry)

    return out
