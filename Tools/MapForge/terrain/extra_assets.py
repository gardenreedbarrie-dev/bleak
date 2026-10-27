"""Extra assets: art from later expansions, with a 3.3.5 fallback for every use.

A spec names one wherever a texture or doodad path goes:

    {"modern": "<path in a later expansion's layout>", "fallback": "<3.3.5a listfile path>", "kind": "texture"}

`package.py resolve-assets --spec SPEC --sources ...` runs where the art is (the VPS: the launcher's patches
folder, Reforged MPQs, loose folders). For every modern path it looks for the file and everything the file needs
(a texture's `_s.blp`; a model's skins, textures and .anim files), copies what it finds into `<out>/files/` and
writes `<out>/asset_resolution.json`. `terrain/build.py --resolution <that file>` then uses each modern file that
was found complete and the fallback for the rest; without a resolution file every use falls back, so the build
works offline. The build copies the files it used into `extra_assets/` of its output and `package.py build` packs
them into the map archive (patch-Q), which every player has, HD pack or not.

Modern doodads are decoration only: the build writes them into the client tiles and leaves them out of the tiles
the server extracts (`server/World/Maps/<Dir>/`), so vmap4_extractor only ever sees 3.3.5 models. The server has
no collision or line-of-sight for them.

What resolve-assets accepts (anything else falls back, with the reason in the resolution file):

- textures: BLP files (BLP1/BLP2 magic). `<name>_s.blp` is copied when a source has it; without one the build
  sets the texture's MTXF flag 1, so a client with specular terrain loads the plain file;
- doodads: path-named M2s the client can load: `MD20` version 264 (loaded as it is), or version 272-274 as `MD20`
  or inside an `MD21` chunk (converted at load: Engine/Source/ModernAssets/ModernAssets.cpp MayTransform and
  WarcraftXL's Downport take only kSourceVersionMin..Max of shared/models/m2/Contract.hpp, and M2Init in
  Engine/Source/Model2/M2Shared.cpp refuses anything but an MD20 at 264, so any other version would be invisible),
  with their `<name>NN.skin` files (one per skin profile), the textures their texture table names (type 0
  entries) and the `<name>IIII-VV.anim` files of sequences that keep their keys outside the model (flag 0x20
  clear, no alias 0x40). An M2 that names files by FileDataID (SFID, TXID, AFID, SKID, BFID chunks) falls back:
  the client resolves those through listfile.csv (Engine/Source/ModernAssets/ModernAssetsListfile.cpp), which
  players without the HD pack do not have, and a partial one in patch-Q would replace the HD pack's.

A dependency that a 3.3.5 listfile holds (`--listfile`) is in every client and is not copied. Every name a model
brings is checked to be a plain relative client path (`unsafe_path`) before it is looked up or written anywhere.
"""

from __future__ import annotations

import json
import os
import struct

FORMAT = "mapforge-assets/1"
FILES_DIR = "files"
RESOLUTION_FILE = "asset_resolution.json"
FDID_CHUNKS = ("SFID", "TXID", "AFID", "SKID", "BFID", "PFID", "LDV1", "RPID", "GPID")


class ResolutionError(ValueError):
    pass


def norm(path: str) -> str:
    """The lookup key for a client path: backslashes, lower case."""
    return path.replace("/", "\\").lower()


def file_rel(path: str) -> str:
    """Where a client path's copy sits under files/ (forward slashes, the spelling kept)."""
    return FILES_DIR + "/" + path.replace("\\", "/")


def unsafe_path(name: str) -> str | None:
    """Why a client path is not a plain relative one (None when it is): names come from model files and source
    archives, and each becomes a file under the output folder and a name in the map archive."""
    if not isinstance(name, str) or not name:
        return "empty"
    if not name.isascii() or any(ch < " " or ch in '<>|*?"' for ch in name):
        return "a non-ASCII, control or reserved character"
    path = name.replace("/", "\\")
    if path.startswith("\\") or ":" in path:
        return "an absolute path or a drive"
    if any(part in ("", ".", "..") for part in path.split("\\")):
        return "an empty, '.' or '..' component"
    return None


class Resolution:
    """A resolution file: for each modern path, whether it was found and which files it brings."""

    def __init__(self, doc: dict, folder: str):
        if not isinstance(doc, dict) or doc.get("format") != FORMAT or not isinstance(doc.get("assets"), list):
            raise ResolutionError(f"not a {FORMAT} resolution file")
        self.doc = doc
        self.folder = folder
        self.entries = {}
        for entry in doc["assets"]:
            if not isinstance(entry, dict) or not isinstance(entry.get("modern"), str):
                raise ResolutionError("an asset entry without a 'modern' path")
            for f in entry.get("files", []):
                # A hand-edited or foreign file must not make the build read or write outside its folders.
                path, rel = (f.get("path"), f.get("file")) if isinstance(f, dict) else (None, None)
                why = unsafe_path(path) or unsafe_path(rel)
                if not why and not rel.startswith(FILES_DIR + "/"):
                    why = f"not under {FILES_DIR}/"
                if why:
                    raise ResolutionError(f"{entry['modern']}: the file entry {f!r} is not a plain path under "
                                          f"{FILES_DIR}/ ({why})")
            self.entries[norm(entry["modern"])] = entry

    @classmethod
    def load(cls, path: str) -> "Resolution":
        if os.path.isdir(path):
            path = os.path.join(path, RESOLUTION_FILE)
        try:
            with open(path, encoding="utf-8") as f:
                doc = json.load(f)
        except OSError as e:
            raise ResolutionError(f"{path}: {e.strerror}") from None
        except json.JSONDecodeError as e:
            raise ResolutionError(f"{path}: invalid JSON: {e}") from None
        return cls(doc, os.path.dirname(os.path.abspath(path)))

    def lookup(self, modern: str) -> dict | None:
        return self.entries.get(norm(modern))

    def files_for(self, modern: str) -> list[dict]:
        """The files a resolved modern path brings: [{path, file (absolute), sha256, size}]."""
        entry = self.lookup(modern)
        if entry is None or entry.get("status") != "resolved":
            return []
        out = []
        for f in entry.get("files", []):
            out.append(dict(f, file=os.path.join(self.folder, *f["file"].split("/"))))
        return out


def load_listfile(path: str) -> set[str]:
    """Lower-case backslash paths from a 3.3.5 listfile: plain lines, `path<TAB>archives` lines, or an asset kit
    JSON (every "path" and "specular" value, except under "modern_candidates": those are not 3.3.5 files). A
    retail listfile.csv (`id;path` lines) is refused: it names later expansions' files, which not every client
    has."""
    with open(path, "rb") as f:
        data = f.read()
    out = set()
    text = data.decode("utf-8", "replace")
    if path.lower().endswith(".json"):
        def walk(node):
            if isinstance(node, dict):
                for key, value in node.items():
                    if key == "modern_candidates":
                        continue
                    if key in ("path", "specular") and isinstance(value, str):
                        out.add(norm(value))
                    else:
                        walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)
        walk(json.loads(text))
        return out
    for number, line in enumerate(text.splitlines(), 1):
        line = line.strip().lstrip("﻿")
        if not line or line.startswith("#"):
            continue
        name = line.split("\t", 1)[0]
        head, sep, _tail = name.partition(";")
        if sep and head.strip().isdigit():
            raise ResolutionError(f"line {number}: 'id;path' is a retail listfile.csv (later expansions' files), not "
                                  "a 3.3.5a listfile; pass listfile_wotlk_merged.tsv or the asset kit")
        out.add(norm(name.strip()))
    return out


# --- what a file needs --------------------------------------------------------------------------------------------


def blp_problem(data: bytes) -> str | None:
    if data[:4] not in (b"BLP2", b"BLP1"):
        return "not a BLP file (no BLP1/BLP2 magic)"
    return None


def specular_name(texture: str) -> str:
    return texture[:-4] + "_s.blp" if texture.lower().endswith(".blp") else texture + "_s.blp"


def _md20(data: bytes) -> tuple[bytes, list[str]]:
    """(the MD20 block, FileDataID chunks) of an M2 file."""
    if data[:4] == b"MD20":
        return data, []
    if data[:4] != b"MD21":
        raise ResolutionError("not an M2 file (no MD20/MD21 magic)")
    pos = 0
    md20 = None
    fdid = []
    while pos + 8 <= len(data):
        magic = data[pos:pos + 4].decode("latin-1")
        size = struct.unpack_from("<I", data, pos + 4)[0]
        if magic == "MD21":
            md20 = data[pos + 8:pos + 8 + size]
        elif magic in FDID_CHUNKS and size:
            fdid.append(magic)
        pos += 8 + size
    if md20 is None or md20[:4] != b"MD20":
        raise ResolutionError("MD21 file without an MD20 block")
    return md20, fdid


def m2_dependencies(path: str, data: bytes) -> dict:
    """What a path-named M2 needs: {"skins", "textures", "anims", "collision", "version", "fdid"}.

    Header offsets from ThirdParty/WarcraftXL/include/structure/m2/M2Format.hpp (M2Header): version +0x04,
    sequences +0x1C (0x40 bytes each: id u16, variation u16, flags u32 at +0x0C), numSkinProfiles +0x44, textures
    +0x50 (0x10 bytes each: type, flags, filename count/offset), collisionIndices +0xD8.
    """
    wrapped = data[:4] == b"MD21"
    md20, fdid = _md20(data)
    if len(md20) < 0xE0:
        raise ResolutionError("M2 header is truncated")
    version = struct.unpack_from("<I", md20, 4)[0]
    if version < 264:
        raise ResolutionError(f"M2 version {version} (before 264) keeps its skins inside; MapForge copies 264+ models")
    if not ((not wrapped and version == 264) or 272 <= version <= 274):
        raise ResolutionError(f"M2 version {version}{' in an MD21 chunk' if wrapped else ''}: the client loads MD20 "
                              "264 as it is and converts 272-274 (MD20 or MD21) at load; anything else would be "
                              "invisible")
    base = path[:-3] if path.lower().endswith(".m2") else path.rsplit(".", 1)[0]
    n_seq, ofs_seq = struct.unpack_from("<II", md20, 0x1C)
    n_skins = struct.unpack_from("<I", md20, 0x44)[0]
    n_tex, ofs_tex = struct.unpack_from("<II", md20, 0x50)
    n_coll = struct.unpack_from("<I", md20, 0xD8)[0]
    if n_skins > 8 or n_tex > 512 or n_seq > 4096:
        raise ResolutionError("M2 header counts are implausible")
    skins = [f"{base}{i:02d}.skin" for i in range(n_skins)]
    textures = []
    for i in range(n_tex):
        at = ofs_tex + 16 * i
        if at + 16 > len(md20):
            raise ResolutionError("M2 texture table runs past the file")
        kind, _flags, count, ofs = struct.unpack_from("<IIII", md20, at)
        if kind != 0 or count == 0:
            continue
        if ofs + count > len(md20):
            raise ResolutionError("M2 texture name runs past the file")
        name = md20[ofs:ofs + count].split(b"\0", 1)[0].decode("ascii", "replace")
        if name:
            textures.append(name.replace("/", "\\"))
    anims = []
    for i in range(n_seq):
        at = ofs_seq + 0x40 * i
        if at + 0x40 > len(md20):
            raise ResolutionError("M2 sequence table runs past the file")
        seq_id, variation = struct.unpack_from("<HH", md20, at)
        flags = struct.unpack_from("<I", md20, at + 0x0C)[0]
        if not flags & 0x20 and not flags & 0x40:
            anims.append(f"{base}{seq_id:04d}-{variation:02d}.anim")
    return {"skins": skins, "textures": textures, "anims": anims, "collision": n_coll > 0, "version": version,
            "fdid": fdid}
