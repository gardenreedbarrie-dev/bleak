"""Where the fit check's files come from: a folder, or a .7z archive read one map at a time.

A .7z is never unpacked whole. Its listing (`7z l -slt`) names every file; only one map's root ADTs and WDT (or
the DBCs asked for) are extracted, with an exact file list (`7z x ... @list`), into a temporary folder made inside
the work folder, in batches that fit the free disk (each batch is deleted before the next one). Several small maps
can come out in one 7z pass (prefetch), since every pass over a big solid archive takes minutes. Every temporary
folder this module makes is removed again, also after an error; nothing outside them is written or deleted.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

import fitcheck_formats as ff

MB = 1024 * 1024


class SourceError(Exception):
    pass


def free_bytes(path: str) -> int:
    st = os.statvfs(path)
    return st.f_bavail * st.f_frsize


def find_7z(explicit: str | None = None) -> str | None:
    if explicit:
        return explicit if (os.path.isfile(explicit) or shutil.which(explicit)) else None
    for name in ("7z", "7zz", "7za"):
        p = shutil.which(name)
        if p:
            return p
    return None


def _split(path: str) -> list[str]:
    return [p for p in path.replace("\\", "/").split("/") if p]


def _maps_index(paths: list[str]) -> dict[str, dict[str, str]]:
    """{map folder (lower case): {file name: path as given}} for every <...>/world/maps/<map>/<file>."""
    out: dict[str, dict[str, str]] = {}
    for p in paths:
        parts = _split(p)
        low = [x.lower() for x in parts]
        for i in range(len(low) - 3):
            if low[i] == "world" and low[i + 1] == "maps" and i + 4 == len(low):
                out.setdefault(low[i + 2], {})[parts[i + 3]] = p
                break
    return out


def _dbc_index(paths: list[str]) -> dict[str, str]:
    out = {}
    for p in paths:
        parts = _split(p)
        if len(parts) >= 2 and parts[-2].lower() == "dbfilesclient":
            out.setdefault(parts[-1].lower(), p)
    return out


class MapFiles:
    """One map's files from a source: root ADT tiles and the WDT. `open()` yields batches of local paths."""

    def __init__(self, source, folder_name: str, tiles: dict[tuple[int, int], str], sizes: dict[str, int],
                 wdt: str | None):
        self.source = source
        self.folder_name = folder_name
        self.tiles = tiles  # (tx, ty) -> path in the source
        self.sizes = sizes  # path in the source -> bytes
        self.wdt = wdt
        self.local: dict[str, str] | None = None  # path in the source -> local path, once prefetched

    def total_bytes(self) -> int:
        return sum(self.sizes.get(p, 0) for p in self.tiles.values()) + self.sizes.get(self.wdt or "", 0)


class FolderSource:
    """A folder holding world/maps/<map>/ somewhere below it (the pack's patch-z.MPQ folder, a client's extracted
    files), or a map folder itself."""

    kind = "folder"

    def __init__(self, root: str):
        if not os.path.isdir(root):
            raise SourceError(f"{root} is not a folder")
        self.root = root
        self.paths = []
        for base, dirs, files in os.walk(root):
            depth = len(_split(os.path.relpath(base, root)))
            if depth > 6:
                dirs[:] = []
                continue
            for f in files:
                self.paths.append(os.path.join(base, f))
        self._maps = _maps_index([os.path.relpath(p, root) for p in self.paths])
        if not self._maps:
            # a map folder itself: <name>_<x>_<y>.adt next to each other
            names = {}
            for p in self.paths:
                if os.path.dirname(p) == root:
                    m = ff.ROOT_ADT_RE.match(os.path.basename(p))
                    if m:
                        names.setdefault(m.group("name").lower(), {})
            for n in names:
                self._maps[n] = {f: f for f in os.listdir(root)}
        self._dbcs = _dbc_index([os.path.relpath(p, root) for p in self.paths])

    def describe(self) -> str:
        return f"folder {self.root}"

    def map_names(self) -> list[str]:
        return sorted(self._maps)

    def map_files(self, name: str) -> MapFiles | None:
        files = self._maps.get(name.lower())
        if files is None:
            return None
        tiles, sizes, wdt = {}, {}, None
        for fname, rel in files.items():
            path = os.path.join(self.root, rel)
            t = ff.is_root_adt_name(fname, name)
            if t is not None:
                tiles[t] = path
                sizes[path] = os.path.getsize(path)
            elif fname.lower() == f"{name.lower()}.wdt":
                wdt = path
                sizes[path] = os.path.getsize(path)
        return MapFiles(self, name, tiles, sizes, wdt)

    def batches(self, mf: MapFiles, work: str, budget: int, log=print):
        """Yield one batch: {(tx, ty): local path}, plus the WDT's local path (or None). As with an archive, the WDT
        comes with the first batch, so it is read before any tile."""
        yield dict(mf.tiles), mf.wdt

    def has_dbc(self, file_name: str) -> bool:
        return file_name.lower() in self._dbcs

    def dbc(self, file_name: str, work: str) -> "TempFile | None":
        rel = self._dbcs.get(file_name.lower())
        if rel is None:
            return None
        return TempFile(os.path.join(self.root, rel), None)

    def dbcs(self, file_names: list[str], work: str) -> "TempFiles":
        """The DBCs of these names that the folder has (in DBFilesClient/), as they are."""
        return TempFiles({n.lower(): os.path.join(self.root, self._dbcs[n.lower()]) for n in file_names
                          if n.lower() in self._dbcs}, None)

    def prefetch(self, mfs: list, work: str, log=print) -> None:
        """Nothing to do for a folder: its files are local already."""
        return None


class TempFile:
    """A local file, and the temporary folder to remove with it (None for a file that stays)."""

    def __init__(self, path: str, tmp: str | None):
        self.path = path
        self.tmp = tmp

    def close(self):
        if self.tmp:
            shutil.rmtree(self.tmp, ignore_errors=True)
            self.tmp = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class TempFiles(TempFile):
    """Several local files ({lower-case name: path}) and the one temporary folder they are in (or None)."""

    def __init__(self, paths: dict[str, str], tmp: str | None):
        super().__init__("", tmp)
        self.paths = paths

    def get(self, file_name: str) -> str | None:
        return self.paths.get(file_name.lower())


class SevenZipSource:
    """A .7z archive (Maps.7z: patch-z.MPQ/world/maps/<map>/...), read with the system's 7z."""

    kind = "7z"

    def __init__(self, archive: str, seven_zip: str | None = None, min_free: int = 0, log=print):
        if not os.path.isfile(archive):
            raise SourceError(f"{archive} does not exist")
        exe = find_7z(seven_zip)
        if exe is None:
            raise SourceError("7z is not installed (Debian/Ubuntu: apt install 7zip, or p7zip-full)")
        self.archive = os.path.abspath(archive)
        self.exe = exe
        self.min_free = min_free
        self.log = log
        log(f"listing {self.archive} ...")
        self.entries = self._list()
        paths = [p for p, (_s, is_dir) in self.entries.items() if not is_dir]
        self._maps = _maps_index(paths)
        self._dbcs = _dbc_index(paths)

    def describe(self) -> str:
        return f"archive {self.archive}"

    def _list(self) -> dict[str, tuple[int, bool]]:
        try:
            run = subprocess.run([self.exe, "l", "-slt", self.archive], capture_output=True,
                                 text=True, errors="replace", timeout=3600)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise SourceError(f"7z could not list {self.archive}: {e}") from e
        if run.returncode != 0:
            raise SourceError(f"7z could not list {self.archive} (exit code {run.returncode}): "
                              f"{(run.stderr or run.stdout).strip()[-400:]}")
        return parse_7z_listing(run.stdout)

    def map_names(self) -> list[str]:
        return sorted(self._maps)

    def map_files(self, name: str) -> MapFiles | None:
        files = self._maps.get(name.lower())
        if files is None:
            return None
        tiles, sizes, wdt = {}, {}, None
        for fname, path in files.items():
            t = ff.is_root_adt_name(fname, name)
            if t is not None:
                tiles[t] = path
            elif fname.lower() == f"{name.lower()}.wdt":
                wdt = path
            else:
                continue
            sizes[path] = self.entries[path][0]
        return MapFiles(self, name, tiles, sizes, wdt)

    def _extract(self, members: list[str], work: str) -> tuple[str, dict[str, str]]:
        """Extract exactly these archive paths into a new temporary folder in `work`. Returns (folder, member ->
        local path). The caller removes the folder (rmtree) when done."""
        if not members:
            # an empty list must never reach 7z: `7z x archive @empty` could extract the whole archive
            raise SourceError("nothing to extract (an empty file list)")
        need = sum(self.entries[m][0] for m in members)
        free = free_bytes(work)
        if free - need < self.min_free:
            raise SourceError(f"not enough free disk in {work} for {len(members)} file(s) of {need // MB} MB: "
                              f"{free // MB} MB free, and {self.min_free // MB} MB must stay free")
        tmp = tempfile.mkdtemp(prefix="fitcheck-7z-", dir=work)
        try:
            lst = os.path.join(tmp, "files.txt")
            with open(lst, "w", encoding="utf-8") as fh:
                for m in members:
                    fh.write(m + "\n")
            out = os.path.join(tmp, "x")
            os.mkdir(out)
            run = subprocess.run([self.exe, "x", "-y", "-bd", "-scsUTF-8", f"-o{out}", self.archive,
                                  f"@{lst}"], capture_output=True, text=True, errors="replace", timeout=6 * 3600)
            if run.returncode != 0:
                raise SourceError(f"7z could not extract from {self.archive} (exit code {run.returncode}): "
                                  f"{(run.stderr or run.stdout).strip()[-400:]}")
            local = {}
            for m in members:
                p = os.path.join(out, *_split(m))
                if not os.path.isfile(p):
                    raise SourceError(f"7z did not extract {m}")
                local[m] = p
            return tmp, local
        except BaseException:
            shutil.rmtree(tmp, ignore_errors=True)
            raise

    def prefetch(self, mfs: list, work: str, log=print) -> str | None:
        """Extract the root ADTs and WDTs of several maps in one 7z pass (each pass over a big solid archive takes
        minutes, so --maps all would otherwise take one pass per dungeon). Sets each MapFiles' `local`; their
        batches() then come from those files. Returns the temporary folder: the caller removes it (rmtree) when
        the maps are done. The caller makes sure they fit the disk (it asks for no more than one batch's worth)."""
        members = []
        for mf in mfs:
            members += list(mf.tiles.values()) + ([mf.wdt] if mf.wdt else [])
        if not members:
            return None
        size = sum(self.entries[m][0] for m in members)
        log(f"  extracting {len(mfs)} maps in one 7z pass ({', '.join(mf.folder_name for mf in mfs)}; "
            f"{-(-size // MB)} MB) ...")
        tmp, local = self._extract(members, work)
        for mf in mfs:
            mf.local = {m: local[m] for m in list(mf.tiles.values()) + ([mf.wdt] if mf.wdt else [])}
        return tmp

    def batches(self, mf: MapFiles, work: str, budget: int, log=print):
        """Yield ({(tx, ty): local path}, wdt local path or None) batch by batch; each batch's files are deleted
        when the next one is asked for (and at the end, or on an error). The WDT comes with the first batch, so it
        is read before any tile. Each extraction says so first ("<map>: extracting batch i of n (X MB)"): on a big
        solid archive one 7z pass takes minutes. A prefetched map (`local`) comes as one batch, without a pass."""
        if mf.local is not None:
            yield {t: mf.local[p] for t, p in mf.tiles.items()}, (mf.local.get(mf.wdt) if mf.wdt else None)
            return
        items = sorted(mf.tiles.items(), key=lambda kv: (kv[0][1], kv[0][0]))
        free = free_bytes(work)
        room = free - self.min_free
        cap = min(budget, room) if budget > 0 else room
        biggest = max([mf.sizes.get(p, 0) for _t, p in items] + [mf.sizes.get(mf.wdt or "", 0)])
        if cap < biggest or cap <= 0:
            raise SourceError(f"not enough free disk in {work} to extract {mf.folder_name}: {free // MB} MB free, "
                              f"{self.min_free // MB} MB must stay free, and the biggest file is {biggest // MB} MB")
        groups: list[list[tuple[tuple[int, int], str]]] = []
        cur: list = []
        cur_bytes = mf.sizes.get(mf.wdt or "", 0)
        for t, p in items:
            s = mf.sizes.get(p, 0)
            if cur and cur_bytes + s > cap:
                groups.append(cur)
                cur, cur_bytes = [], 0
            cur.append((t, p))
            cur_bytes += s
        if cur or not groups:
            groups.append(cur)
        if len(groups) > 1:
            log(f"  {mf.folder_name}: {mf.total_bytes() // MB} MB of ADTs, extracted in {len(groups)} batches of "
                f"at most {cap // MB} MB")
        for gi, group in enumerate(groups):
            members = [p for _t, p in group]
            if gi == 0 and mf.wdt:
                members.append(mf.wdt)
            if not members:
                yield {}, None
                continue
            size = sum(self.entries[m][0] for m in members)
            log(f"  {mf.folder_name}: extracting batch {gi + 1} of {len(groups)} ({len(group)} tiles, "
                f"{-(-size // MB)} MB) ...")
            tmp, local = self._extract(members, work)
            try:
                yield {t: local[p] for t, p in group}, (local.get(mf.wdt) if gi == 0 and mf.wdt else None)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)

    def has_dbc(self, file_name: str) -> bool:
        return file_name.lower() in self._dbcs

    def dbc(self, file_name: str, work: str) -> TempFile | None:
        member = self._dbcs.get(file_name.lower())
        if member is None:
            return None
        self.log(f"extracting {member} from the archive ...")
        tmp, local = self._extract([member], work)
        return TempFile(local[member], tmp)

    def dbcs(self, file_names: list[str], work: str) -> TempFiles:
        """The DBCs of these names that the archive has, extracted in one 7z pass (one temporary folder)."""
        want = {n.lower(): self._dbcs[n.lower()] for n in file_names if n.lower() in self._dbcs}
        if not want:
            return TempFiles({}, None)
        self.log(f"extracting {', '.join(want.values())} from the archive (one 7z pass) ...")
        tmp, local = self._extract(list(want.values()), work)
        return TempFiles({n: local[m] for n, m in want.items()}, tmp)


def parse_7z_listing(text: str) -> dict[str, tuple[int, bool]]:
    """{path: (size, is folder)} from `7z l -slt` (7-Zip 16.02 to 24: blocks of 'Key = value' lines after the
    '----------' line; a folder has 'Folder = +' or an 'Attributes' value starting with D)."""
    out: dict[str, tuple[int, bool]] = {}
    started = False
    cur: dict[str, str] = {}

    def flush():
        if "Path" in cur:
            is_dir = cur.get("Folder", "") == "+" or cur.get("Attributes", "").startswith("D")
            try:
                size = int(cur.get("Size", "0") or 0)
            except ValueError:
                size = 0
            out[cur["Path"].replace("\\", "/")] = (size, is_dir)

    for line in text.splitlines():
        if not started:
            if line.strip() == "----------":
                started = True
            continue
        if not line.strip():
            flush()
            cur = {}
            continue
        if " = " in line:
            k, v = line.split(" = ", 1)
            if k == "Path" and "Path" in cur:
                flush()
                cur = {}
            cur[k.strip()] = v
        elif line.endswith(" ="):
            cur[line[:-2].strip()] = ""
    flush()
    return out


def open_source(path: str, seven_zip: str | None = None, min_free: int = 0, log=print):
    if os.path.isdir(path):
        return FolderSource(path)
    if path.lower().endswith(".7z") or os.path.isfile(path):
        return SevenZipSource(path, seven_zip, min_free, log)
    raise SourceError(f"{path} is neither a folder nor a .7z archive")
