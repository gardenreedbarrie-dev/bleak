r"""Where `package.py resolve-assets` looks for the modern files of a spec's extra assets.

Each --sources argument is one of:

- an MPQ file (a Reforged archive, say);
- a folder: its patch archives in the client's load order (patch-?.MPQ, <locale>\patch-<locale>-?.MPQ and
  patch.MPQ, as dbc/patches.py orders them; a game folder's Data folder is used when it has one), then any other
  top-level *.MPQ (by name, the last one first), then the loose files under it (an extracted pack).

Sources are searched in the order given and the first one holding a file wins; within a folder the archive the
client would load the file from wins. Reading reuses dbc/patches.py's reader (zlib, bzip2, encrypted files, sector
checksums). When the winning copy cannot be read (an imploded or LZMA file, a damaged sector), `read` raises
SourceReadError instead of taking a lower source's copy, which may be another version of the file.
"""

from __future__ import annotations

import os
import struct

import mpqpack  # noqa: E402  (Tools/MpqPack, added to sys.path by the package)

from .patches import PatchArchive, PatchError, PatchSet


class SourceReadError(Exception):
    """The source that holds a file (the copy that wins) cannot read it."""


class _Layer:
    def __init__(self, label: str, reader=None, index: dict | None = None):
        self.label = label
        self.reader = reader  # a PatchArchive, or None for loose files
        self.index = index  # lower-case backslash path -> file on disk (loose files)

    def find(self, key: str, name: str) -> bool:
        if self.reader is not None:
            return self.reader.has_file(name)
        return key in self.index

    def read(self, key: str, name: str) -> bytes:
        if self.reader is not None:
            return self.reader.read(name)
        with open(self.index[key], "rb") as f:
            return f.read()


class SourceSet:
    def __init__(self, paths: list[str]):
        self.layers: list[_Layer] = []
        self.problems: list[str] = []
        self.labels: list[str] = []
        self._patchsets: list[PatchSet] = []
        for path in paths:
            self._add(path)

    def _open(self, path: str, label: str) -> None:
        try:
            self.layers.append(_Layer(label, PatchArchive(path)))
        except (mpqpack.MpqError, OSError, struct.error) as e:
            self.problems.append(f"{label}: cannot be opened ({e})")

    def _add(self, path: str) -> None:
        self.labels.append(path)
        if os.path.isfile(path):
            if path.lower().endswith(".mpq"):
                self._open(path, path)
            else:
                self.problems.append(f"{path}: not an MPQ or a folder")
            return
        if not os.path.isdir(path):
            self.problems.append(f"{path}: no such file or folder")
            return
        taken = set()
        try:
            patchset = PatchSet.scan(path)
        except PatchError as e:
            self.problems.append(str(e))
            patchset = None
        if patchset is not None:
            self._patchsets.append(patchset)
            for archive in reversed(patchset.archives):  # highest priority first
                taken.add(os.path.normcase(os.path.abspath(archive.path)))
                if archive.reader is None:
                    self.problems.append(f"{archive.path}: {archive.error}")
                    continue
                self.layers.append(_Layer(f"{path}: {archive.client_path}", archive.reader))
        others = sorted((e for e in os.listdir(path) if e.lower().endswith(".mpq")
                         and os.path.isfile(os.path.join(path, e))
                         and os.path.normcase(os.path.abspath(os.path.join(path, e))) not in taken),
                        key=str.lower, reverse=True)
        for entry in others:
            self._open(os.path.join(path, entry), f"{path}: {entry}")
        index = {}
        for base, _dirs, files in os.walk(path):
            for f in files:
                if f.lower().endswith(".mpq"):
                    continue
                full = os.path.join(base, f)
                index[os.path.relpath(full, path).replace(os.sep, "\\").lower()] = full
        if index:
            self.layers.append(_Layer(f"{path} (loose files)", index=index))

    def find(self, name: str) -> str | None:
        """The label of the source that holds a client path, or None."""
        key = name.replace("/", "\\").lower()
        name = name.replace("/", "\\")
        for layer in self.layers:
            if layer.find(key, name):
                return layer.label
        return None

    def read(self, name: str) -> tuple[bytes, str] | None:
        """(bytes, source label) of a client path, or None when no source holds it. The first source holding it
        decides: when its copy cannot be read, SourceReadError (also noted in `problems`); a lower source's copy is
        never used in its place, since it may be another version (an older model with the newer one's skins)."""
        key = name.replace("/", "\\").lower()
        name = name.replace("/", "\\")
        for layer in self.layers:
            if layer.find(key, name):
                try:
                    return layer.read(key, name), layer.label
                except (mpqpack.MpqError, PatchError, OSError) as e:
                    problem = f"{layer.label}: {name} cannot be read ({e})"
                    self.problems.append(problem)
                    raise SourceReadError(problem) from None
        return None

    def close(self) -> None:
        for patchset in self._patchsets:
            patchset.close()
        for layer in self.layers:
            if layer.reader is not None:
                try:
                    layer.reader.close()
                except Exception:  # noqa: BLE001 (already closed through its patch set)
                    pass
