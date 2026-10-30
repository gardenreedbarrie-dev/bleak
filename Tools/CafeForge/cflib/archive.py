"""The café's art and its archives (sections 5.9, 6.2, 6.4): ModelForge's output folder, read and checked against
cafe.json; `art` (ModelForge's build and icons, then the markers); and writing every archive a build changes.

The art is ModelForge's (Tools/ModelForge, run as its own process and never imported): its manifest.json names each
model's display, its .m2, .skin and textures with their sha256 and its bounds, and its output tree holds the files
(DIR/files/World/Bleakhold/Cafe/..., DIR/files/Interface/Icons/BH_Cafe_*.blp). patch-4.MPQ ships exactly the files
of the café's displays (cafe.json's new-art gameobjects) and the café's icons; ModelForge's test cube and any file
the manifest does not list stay out. Each file must still be the one ModelForge built (its sha256).

patch-4.MPQ is CafeForge's own archive: it holds the art, the two markers (cflib/marker.py) and the stock copy of a
table no patch holds (with the café's rows). A new one is written whole (MpqPack's write_archive_streaming); an
earlier one is rebuilt from the realm's copy with the planned files replaced, and every café path it holds that the
build no longer plans goes (a renamed texture, a model taken out), as RaceForge's skins drops its stale textures; so
does a table whose copy a realm patch now decides (Plan.drops). When nothing of it would change, it is not written
at all ("already up to date"): the launcher then has nothing new to send. Every other archive a build changes is a
realm patch that holds a winning copy of a table: rebuilt with that copy replaced and every other file kept
(Tools/MapForge/dbc/patches.py rebuild, as RaceForge's update does).
"""

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field

from . import config as cfgmod
from . import marker

import mpqpack  # noqa: E402  (Tools/MpqPack, on sys.path through cflib.config)
from rflib import skins, update  # noqa: E402  (Tools/RaceForge)

MODELFORGE = os.path.join(cfgmod.TOOLS_DIR, "ModelForge", "modelforge.py")
MANIFEST = "manifest.json"
MARKERS = "markers"
ICON_ROOT = "Interface\\Icons\\"
# ModelForge's `icons` exits 2 while the icons are not made yet (its milestone M5).
ICONS_NOT_YET = 2


class ArtError(Exception):
    pass


def norm(name):
    """An archive path as the client compares it: backslashes, case folded."""
    return name.replace("/", "\\").lower()


def disk_path(folder, archive_name):
    """Where ModelForge's output tree keeps an archive path."""
    return os.path.join(folder, "files", *archive_name.replace("/", "\\").split("\\"))


def read_value(value):
    """A planned file's bytes: value is the bytes or the file on disk."""
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    with open(value, "rb") as f:
        return f.read()


def icon_path(icon):
    """The icon file of a SpellIcon row: its texture name (no extension, as the stock rows) plus .blp."""
    return icon.texture + ".blp"


@dataclass
class Art:
    """The art a build ships, from one ModelForge output folder."""
    folder: str
    files: dict = field(default_factory=dict)     # archive path -> file on disk: the models' files and the icons
    sha: dict = field(default_factory=dict)       # archive path -> sha256
    bounds: dict = field(default_factory=dict)    # display -> ((min x, y, z), (max x, y, z))
    models: dict = field(default_factory=dict)    # display -> ModelForge's model name
    icons: dict = field(default_factory=dict)     # SpellIcon id -> archive path
    missing_models: list = field(default_factory=list)
    missing_icons: list = field(default_factory=list)
    problems: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    @property
    def complete(self):
        return not self.problems

    def size(self):
        return sum(os.path.getsize(p) for p in self.files.values())

    def summary(self, cfg):
        """'24 of 24 café models, 14 of 14 icons' (with what is missing)."""
        text = "%d of %d café models, %d of %d icons" % (len(cfg.displays) - len(self.missing_models),
                                                         len(cfg.displays), len(cfg.icons) - len(self.missing_icons),
                                                         len(cfg.icons))
        return text


def find_art(folder):
    """The folder that holds ModelForge's manifest.json: folder itself, or its art/ (an output folder of `art`)."""
    if os.path.isfile(os.path.join(folder, MANIFEST)) or not os.path.isfile(os.path.join(folder, "art", MANIFEST)):
        return os.path.abspath(folder)
    return os.path.abspath(os.path.join(folder, "art"))


def _bounds(entry, where):
    bounds = entry.get("bounds")
    try:
        low = tuple(float(v) for v in bounds["min"])
        high = tuple(float(v) for v in bounds["max"])
    except (TypeError, KeyError, ValueError):
        raise ArtError("%s: bounds must be {\"min\": [x, y, z], \"max\": [x, y, z]}" % where) from None
    if len(low) != 3 or len(high) != 3 or any(a > b for a, b in zip(low, high)):
        raise ArtError("%s: bounds %s - %s are not a box" % (where, list(low), list(high)))
    return low, high


def load_art(folder, cfg):
    """The art of a ModelForge output folder for cafe.json's displays and icons. Never raises for what it finds: a
    missing model or icon, a file that changed since ModelForge built it, a path outside the café's folders, are
    Art.problems (a build stops on them)."""
    folder = find_art(folder)
    art = Art(folder)
    path = os.path.join(folder, MANIFEST)
    if not os.path.isfile(path):
        art.problems.append("%s has no ModelForge %s: run  python3 -I Tools/CafeForge/cafeforge.py art --out <folder>"
                            "  first (or give the build no --art: it makes the art itself)" % (folder, MANIFEST))
        art.missing_models = [d.name for d in cfg.displays]
        art.missing_icons = [i.texture.split("\\")[-1] for i in cfg.icons]
        return art
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as ex:
        art.problems.append("%s: cannot be read (%s)" % (path, ex))
        return art
    if not isinstance(data, dict) or data.get("tool") != "ModelForge" or data.get("version") != 1:
        art.problems.append("%s is not a manifest of ModelForge version 1" % path)
        return art
    listed = data.get("files") if isinstance(data.get("files"), dict) else {}
    listed = {norm(k): (k, v) for k, v in listed.items() if isinstance(k, str) and isinstance(v, str)}
    models = [m for m in data.get("models") or [] if isinstance(m, dict)]
    by_display = {m.get("display"): m for m in models}
    wanted = {d.id for d in cfg.displays}
    for m in models:
        if m.get("display") not in wanted:
            art.notes.append("not shipped: %s (display %s is not a café piece)" % (m.get("name"), m.get("display")))

    def take(name, where):
        """A file of the manifest into art.files, checked against its sha256."""
        if not cfgmod.is_cafe_path(name):
            art.problems.append("%s: %s is outside the café's folders (%s)" % (where, name, ", ".join(
                cfgmod.CAFE_PREFIXES)))
            return
        entry = listed.get(norm(name))
        disk = disk_path(folder, name)
        if not os.path.isfile(disk):
            art.problems.append("%s: %s is not in %s" % (where, name, os.path.join(folder, "files")))
            return
        sha = marker.sha256_file(disk)
        if entry is not None and entry[1].lower() != sha:
            art.problems.append("%s: %s changed since ModelForge built it (its sha256 is not the manifest's): build "
                                "the art again" % (where, name))
            return
        if entry is None and where.startswith("display"):
            art.problems.append("%s: %s is not in the manifest's files" % (where, name))
            return
        art.files[name] = disk
        art.sha[name] = sha

    for d in cfg.displays:
        m = by_display.get(d.id)
        where = "display %d (%s)" % (d.id, d.name)
        if m is None:
            art.missing_models.append(d.name)
            continue
        if norm(str(m.get("m2", ""))) != norm(d.model):
            art.problems.append("%s: ModelForge's model is %s; the display row names %s" % (where, m.get("m2"),
                                                                                           d.model))
            continue
        try:
            art.bounds[d.id] = _bounds(m, where)
        except ArtError as ex:
            art.problems.append(str(ex))
            continue
        textures = m.get("textures") if isinstance(m.get("textures"), list) else []
        for name in [m["m2"], m.get("skin") or ""] + textures:
            if not isinstance(name, str) or not name:
                art.problems.append("%s: the manifest names no .skin or an empty texture" % where)
                continue
            take(name, where)
        art.models[d.id] = d.name
    icon_entries = {i.get("id"): i for i in data.get("icons") or [] if isinstance(i, dict)}
    for icon in cfg.icons:
        name = icon_path(icon)
        where = "icon %d" % icon.id
        listed_icon = icon_entries.get(icon.id)
        if listed_icon is not None and norm(str(listed_icon.get("path", ""))) != norm(name):
            art.problems.append("%s: ModelForge's icon is %s; the SpellIcon row names %s" % (
                where, listed_icon.get("path"), icon.texture))
            continue
        if not os.path.isfile(disk_path(folder, name)):
            art.missing_icons.append(icon.texture.split("\\")[-1])
            continue
        before = len(art.problems)
        take(name, where)
        if len(art.problems) == before:
            problems = marker.blp_problems(art.files[name])
            if problems:
                art.problems.append("%s: %s: %s" % (where, name, "; ".join(problems)))
            else:
                art.icons[icon.id] = name
    if art.missing_models:
        art.problems.insert(0, "ModelForge built %d of the %d café models; missing: %s. The café's patch needs every "
                               "one (ModelForge's milestone M5)" % (len(cfg.displays) - len(art.missing_models),
                                                                    len(cfg.displays), ", ".join(art.missing_models)))
    if art.missing_icons:
        art.problems.insert(1 if art.missing_models else 0,
                            "%d of the %d café icons are in %s; missing: %s (ModelForge's icons, milestone M5)" % (
                                len(cfg.icons) - len(art.missing_icons), len(cfg.icons),
                                os.path.join(folder, "files", "Interface", "Icons"), ", ".join(art.missing_icons)))
    return art


# ------------------------------------------------------------------------------------------- the art command

def _run(cmd, quiet):
    sys.stdout.flush()  # our lines before ModelForge's
    if not quiet:
        return subprocess.run(cmd).returncode, ""
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return r.returncode, r.stdout


def make_art(out_dir, cfg, preview=False, only=None, tex_scale=None, jobs=None, quiet=False, say=print):
    """`art`: ModelForge's build (every model it can build) and icons into OUT/art, then the markers into
    OUT/art/markers. Returns the Art (Art.problems: what a build would refuse). Raises ArtError when ModelForge
    fails."""
    if not os.path.isfile(MODELFORGE):
        raise ArtError("%s is missing: CafeForge needs Tools/ModelForge of the same checkout" % MODELFORGE)
    art_dir = os.path.join(os.path.abspath(out_dir), "art")
    os.makedirs(art_dir, exist_ok=True)
    # a manifest of an earlier run would pass for this one if ModelForge stopped half-way
    for stale in (os.path.join(art_dir, MANIFEST), os.path.join(art_dir, MARKERS)):
        if os.path.isdir(stale):
            shutil.rmtree(stale)
        elif os.path.exists(stale):
            os.remove(stale)
    cmd = [sys.executable, "-I", MODELFORGE, "build", "--out", art_dir]
    cmd += ["--only", only] if only else ["--all"]
    if preview:
        cmd.append("--preview")
    if tex_scale:
        cmd += ["--tex-scale", str(tex_scale)]
    if jobs:
        cmd += ["--jobs", str(jobs)]
    say("ModelForge build: %s" % art_dir)
    rc, text = _run(cmd, quiet)
    if rc != 0 or not os.path.isfile(os.path.join(art_dir, MANIFEST)):
        raise ArtError("ModelForge's build failed (exit code %d)%s" % (rc, (": " + text.strip().splitlines()[-1])
                                                                       if text.strip() else ""))
    rc, text = _run([sys.executable, "-I", MODELFORGE, "icons", "--out", art_dir], True)
    if rc == ICONS_NOT_YET:
        say("ModelForge icons: not made yet (%s)" % (text.strip().splitlines() or ["exit code 2"])[-1])
    elif rc != 0:
        raise ArtError("ModelForge's icons failed (exit code %d): %s" % (rc, text.strip()[-400:]))
    art = load_art(art_dir, cfg)
    blp = marker.write_marker_blp(os.path.join(art_dir, MARKERS, "Marker.blp"))
    files = dict(art.sha)
    files[cfgmod.MARKER_TEXTURE] = marker.sha256_file(blp)
    with open(os.path.join(art_dir, MARKERS, "cafeforge.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write(marker.marker_text(files, what="cafeforge.py art"))
    return art


# ------------------------------------------------------------------------------------------ the archives

@dataclass
class Written:
    """One archive a build wrote into OUT/client."""
    name: str            # as the patch folder spells it
    client_path: str     # Data\patch-4.MPQ, Data\enUS\patch-enUS-8.MPQ
    path: str            # the file in OUT/client
    new: bool
    files: dict          # archive path -> bytes or file on disk: what the build put in
    replaced: int = 0    # of them, names the archive had
    dropped: list = field(default_factory=list)
    changed: int = -1    # of the replaced ones, those with other bytes (-1: not counted)

    @property
    def rel(self):
        return "/".join(self.client_path.split("\\")[1:])

    def text(self):
        if self.new:
            return "written: %s (new; %d files)" % (self.path, len(self.files))
        if self.changed >= 0:
            parts = ["%d added" % (len(self.files) - self.replaced), "%d changed" % self.changed,
                     "%d the same" % (self.replaced - self.changed)]
        else:
            parts = ["%d replaced" % self.replaced, "%d added" % (len(self.files) - self.replaced)]
        if self.dropped:
            parts.append("%d dropped" % len(self.dropped))
        return "written: %s (%s)" % (self.path, ", ".join(parts))

    def planned_bytes(self, name):
        return read_value(self.files[name])


@dataclass
class OwnPlan:
    """What happens to patch-4.MPQ: its planned files, what it drops, and whether it changes at all."""
    files: dict                  # archive path -> bytes or file: art, the marker texture, its table copies
    drop: list                   # names of the existing archive that go
    up_to_date: bool
    existing: object = None      # the patch folder's patch-4.MPQ (MapForge Archive) or None


def plan_own(plan, patchset, art, work_dir):
    """OwnPlan of the café's archive. work_dir: where the marker texture is drawn."""
    files = dict(art.files)
    files[cfgmod.MARKER_TEXTURE] = marker.write_marker_blp(os.path.join(work_dir, "Marker.blp"))
    files.update(plan.targets.get(plan.own, {}))
    existing = patchset.find(plan.own)
    if existing is None:
        return OwnPlan(files, [], False, None)
    patches = update.patch_tools()
    try:
        names = patches.archive_contents(existing.reader, existing.name)
    except patches.PatchError as ex:
        raise ArtError(str(ex)) from None
    planned = {mpqpack.name_key(n) for n in files}
    drops = {mpqpack.name_key(n) for n in plan.drops}
    marker_key = mpqpack.name_key(cfgmod.MARKER_FILE)
    special = {mpqpack.name_key(n) for n in mpqpack.SPECIAL_FILES}
    drop = [n for n in names if mpqpack.name_key(n) not in special | {marker_key} | planned
            and (cfgmod.is_cafe_path(n) or mpqpack.name_key(n) in drops)]
    same = not drop and not plan.targets.get(plan.own)
    if same:
        for name, value in files.items():
            if not existing.has(name):
                same = False
                break
            if existing.read(name) != read_value(value):
                same = False
                break
    return OwnPlan(files, drop, same, existing)


def rebuild_problems(plan, patchset):
    """Archives the plan rebuilds that MapForge's rebuild could not copy whole (files their (listfile) does not name,
    locale-specific copies): found before anything is written."""
    patches = update.patch_tools()
    problems = []
    for target in sorted(plan.targets, key=str.lower):
        archive = patchset.find(target)
        if archive is None or archive.reader is None:
            continue
        try:
            patches.archive_contents(archive.reader, archive.name)
        except patches.PatchError as ex:
            problems.append(str(ex))
    return problems


def _stage(files, folder):
    """{archive path: file on disk}: bytes are written into folder first."""
    out = {}
    for i, (name, value) in enumerate(sorted(files.items(), key=lambda kv: kv[0].lower())):
        if isinstance(value, (bytes, bytearray)):
            path = os.path.join(folder, "%06d" % i)
            os.makedirs(folder, exist_ok=True)
            with open(path, "wb") as f:
                f.write(value)
            value = path
        out[name] = value
    return out


def _place(out_dir, archive, name):
    """OUT/client/<its place in the patch folder>: a locale patch goes to client/enUS/."""
    place = archive.client_path.split("\\")[1:] if archive is not None else [name]
    return os.path.join(out_dir, "client", *place)


def write_archives(plan, patchset, own, out_dir, say=print):
    """Every archive the plan changes into OUT/client. Returns [Written]."""
    patches = update.patch_tools()
    written = []
    merged = os.path.join(out_dir, "merged")
    staging = os.path.join(out_dir, "staging")
    try:
        for target, files in sorted(plan.targets.items(), key=lambda kv: kv[0].lower()):
            if target.lower() == plan.own.lower():
                continue
            source = patchset.find(target)
            out_path = _place(out_dir, source, target)
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            replacements = _stage(files, os.path.join(merged, target))
            say("rebuilding %s ..." % target)
            replaced = patches.rebuild(source, replacements, out_path, staging)
            written.append(Written(source.name, source.client_path, out_path, False, dict(files), len(replaced)))
        if not own.up_to_date:
            names = {mpqpack.name_key(n) for n in own.files}
            kept = {}
            if own.existing is not None:
                dropped = {mpqpack.name_key(n) for n in own.drop}
                special = {mpqpack.name_key(n) for n in mpqpack.SPECIAL_FILES + (cfgmod.MARKER_FILE,)}
                for name in patches.archive_contents(own.existing.reader, own.existing.name):
                    key = mpqpack.name_key(name)
                    if key not in names | dropped | special:
                        kept[name] = marker.sha256_of(own.existing.read(name))
            shas = dict(kept)
            for name, value in own.files.items():
                shas[name] = marker.sha256_of(value) if isinstance(value, (bytes, bytearray)) else \
                    marker.sha256_file(value)
            files = dict(own.files)
            files[cfgmod.MARKER_FILE] = marker.marker_text(shas).encode("utf-8")
            out_path = _place(out_dir, own.existing, plan.own)
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            items = _stage(files, os.path.join(merged, plan.own))
            if own.existing is None:
                say("writing %s ..." % plan.own)
                mpqpack.write_archive_streaming(out_path, sorted(items.items(), key=lambda kv: kv[0].lower()))
                written.append(Written(plan.own, "Data\\" + plan.own, out_path, True, files))
            else:
                say("rebuilding %s ..." % plan.own)
                drop_keys = {mpqpack.name_key(n) for n in own.drop}
                changed = sum(1 for n, v in files.items() if own.existing.has(n)
                              and own.existing.read(n) != read_value(v))
                replaced = patches.rebuild(own.existing, items, out_path, staging,
                                           drop=lambda n: mpqpack.name_key(n) in drop_keys)
                written.append(Written(own.existing.name, own.existing.client_path, out_path, False, files,
                                       len(replaced), list(own.drop), changed))
    except (patches.PatchError, mpqpack.MpqError) as ex:
        raise ArtError(str(ex)) from None
    finally:
        shutil.rmtree(merged, ignore_errors=True)
        shutil.rmtree(staging, ignore_errors=True)
    return written


def space_needed(plan, patchset, own):
    """Bytes OUT needs for the archives (skins.space_needed's rule): each written whole, the largest rebuilt one's
    files unpacked meanwhile (patches.rebuild stages them), the staged copies of the new files, and a margin."""
    total, staging = skins.SPACE_MARGIN, 0
    jobs = [(t, files) for t, files in plan.targets.items() if t.lower() != plan.own.lower()]
    if not own.up_to_date:
        jobs.append((plan.own, own.files))
    for target, files in jobs:
        new = sum(len(v) if isinstance(v, (bytes, bytearray)) else os.path.getsize(v) for v in files.values())
        total += 2 * new
        archive = patchset.find(target)
        if archive is not None:
            reader = archive.reader
            total += os.path.getsize(archive.path)
            staging = max(staging, sum(b.file_size for b in reader.blocks if b.flags & mpqpack.FILE_EXISTS))
    return total + staging
