"""raceforge.py install: put the archives of an output folder of `skins` or `update` into the realm's patch folder.

Each archive under OUT/client goes to the same place in the patch folder (client/enUS/ to enUS/). The file there may be
a link (Patch-R.MPQ links to the download site's copy): the link stays, and the file it points at is replaced. Before
anything changes:

- with OUT/install.json (written by skins and update), each file of the patch folder must still be the one the tool
  read, by size and modification time: otherwise the patches changed since, and the tool must run again. An archive
  that came from the game folder (--client Data) or is new must not be in the patch folder yet;
- the file it replaces is kept in OUT/old-patches/<path>: a hard link where OUT is on the same filesystem (no copy, no
  space), else a copy. A later install from the same OUT keeps that backup while the patch folder still holds what
  the earlier one put there (so it stays the file of before the first install); when another install has replaced
  the file in between, the old backup moves to OUT/old-patches-<n>/<path> and the file replaced now is kept instead,
  so going back never undoes that other install.

Then each archive goes next to its destination as <name>.new (publish.sh only takes files that end in .MPQ) and is
renamed over it in one step, so a player or the publisher never sees half a file. OUT's archive is moved, not copied,
where both are on one filesystem. Each install also writes OUT/old-patches/installed.json (RECORD): per archive, the
backup and the file it put there (size and modification time), written before the archive moves. --force of skins and
update never removes old-patches.

`--restore` goes by that record, not by install.json (a later run of the tool into OUT rewrites install.json): it puts
each backup back the same way (and removes an archive that install added) when the patch folder still holds what
install put there and the backup is still the file it replaced, and refuses, changing nothing, when another install
has replaced it since. An archive already put back is left as it is. A folder without the record (an install by
hand, as the runbooks did before) is restored only where the patch folder's file is byte for byte the one in
OUT/client, which such an install copied; an archive such an install added stays.
"""

from __future__ import annotations

import errno
import json
import os
import shutil
import stat
import time
from dataclasses import dataclass

INSTALL_FILE = "install.json"
OLD_PATCHES = "old-patches"
RECORD = "installed.json"  # in OLD_PATCHES
PUBLISH = "bash /root/bleakserv/deploy/launcher/publish.sh"


class InstallError(Exception):
    pass


def fingerprint(path: str) -> tuple[int, int]:
    st = os.stat(path)
    return st.st_size, st.st_mtime_ns


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def entry(rel: str, client_path: str, origin: str, source: str, size: int | None, mtime_ns: int | None,
          out_path: str) -> dict:
    """One archive of install.json. origin: "patches" (it replaces the patch folder's file, read at size and
    mtime_ns), "client" (an archive of the game folder's Data, which the patch folder will override) or "new"."""
    out_size, out_mtime = fingerprint(out_path)
    return {"rel": rel, "client_path": client_path, "origin": origin,
            "source": os.path.abspath(source) if source else "", "size": size, "mtime_ns": mtime_ns,
            "out_size": out_size, "out_mtime_ns": out_mtime}


def write_json(path: str, data: dict) -> str:
    """path, whole or not at all."""
    with open(path + ".part", "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())

    os.replace(path + ".part", path)
    return path


def write_manifest(out_dir: str, tool: str, patches_dir: str, client_dir: str | None, entries: list[dict],
                   checks_passed: bool) -> str:
    return write_json(os.path.join(out_dir, INSTALL_FILE), {
        "_readme": "For raceforge.py install: each archive of client/ with the file of the patch folder it replaces, "
                   "as the tool read it (size, mtime_ns). install refuses a file that changed since.",
        "tool": tool,
        "written": now(),
        "patches": os.path.realpath(patches_dir),
        "client": os.path.realpath(client_dir) if client_dir else "",
        "checks_passed": bool(checks_passed),
        "archives": entries,
    })


def load_manifest(out_dir: str) -> dict | None:
    path = os.path.join(out_dir, INSTALL_FILE)

    if not os.path.exists(path):
        return None

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise InstallError(f"{path}: cannot be read ({e})") from None

    if not isinstance(data, dict) or not isinstance(data.get("archives"), list):
        raise InstallError(f"{path}: not an install.json of RaceForge")

    for item in data["archives"]:
        if (not isinstance(item, dict) or not isinstance(item.get("rel"), str)
                or item.get("origin") not in ("patches", "client", "new")):
            raise InstallError(f"{path}: an archive entry is damaged ({item!r})")

    return data


# --- the record of what install did (OUT/old-patches/installed.json) ---------------------------------------------


def record_path(out_dir: str) -> str:
    return os.path.join(out_dir, OLD_PATCHES, RECORD)


def load_record(out_dir: str) -> dict | None:
    path = record_path(out_dir)

    if not os.path.exists(path):
        return None

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise InstallError(f"{path}: cannot be read ({e})") from None

    keys = ("installed_size", "installed_mtime_ns")

    if not isinstance(data, dict) or not isinstance(data.get("archives"), dict) or not all(
            isinstance(v, dict) and isinstance(v.get("backup"), bool) and all(isinstance(v.get(k), int) for k in keys)
            and (not v["backup"] or all(isinstance(v.get(k), int) for k in ("backup_size", "backup_mtime_ns")))
            for v in data["archives"].values()):
        raise InstallError(f"{path}: not a record of RaceForge's install, or damaged")

    return data


def save_record(out_dir: str, record: dict):
    os.makedirs(os.path.join(out_dir, OLD_PATCHES), exist_ok=True)
    write_json(record_path(out_dir), record)


def installed_of(item: dict) -> tuple[int, int]:
    return item["installed_size"], item["installed_mtime_ns"]


def backup_of(item: dict) -> tuple[int, int]:
    return item["backup_size"], item["backup_mtime_ns"]


def same_file(a: str, b: str) -> bool:
    """Whether a and b are one file (a hard link) or a copy that kept size and modification time (copy_synced)."""
    try:
        return os.path.samefile(a, b) or fingerprint(a) == fingerprint(b)
    except OSError:
        return False


def same_bytes(a: str, b: str) -> bool:
    if os.path.getsize(a) != os.path.getsize(b):
        return False

    with open(a, "rb") as fa, open(b, "rb") as fb:
        while True:
            chunk = fa.read(16 * 1024 * 1024)

            if chunk != fb.read(16 * 1024 * 1024):
                return False

            if not chunk:
                return True


# --- planning ----------------------------------------------------------------------------------------------------


def safe_rel(rel: str) -> list[str]:
    parts = rel.replace("\\", "/").split("/")

    if not rel or os.path.isabs(rel) or any(p in ("", ".", "..") for p in parts):
        raise InstallError(f"{rel!r} is not a path inside the patch folder")

    return parts


def discover(folder: str) -> list[dict]:
    """The archives of an output folder without install.json: every .MPQ under it."""
    out = []

    for root, dirs, files in os.walk(folder):
        dirs.sort()

        for name in sorted(files):
            if name.lower().endswith(".mpq"):
                rel = os.path.relpath(os.path.join(root, name), folder).replace(os.sep, "/")
                out.append({"rel": rel})

    return out


@dataclass
class Action:
    kind: str  # replace, add, installed (nothing to do), restore, remove, absent, restored (nothing to do)
    rel: str
    src: str
    link: str
    dest: str
    backup: str
    backup_plan: str = ""  # replace and add: "take", "keep", "aside" or "added" (backup_plan()); "" when nothing is there

    def text(self) -> str:
        return {
            "replace": f"replace {self.dest} with {self.src}"
                       + (f" (link {self.link} stays)" if self.link != self.dest else ""),
            "add": f"add {self.dest} ({self.src})",
            "installed": f"already installed: {self.dest}",
            "restore": f"put back {self.dest} from {self.backup}",
            "remove": f"remove {self.dest} (install added it)",
            "absent": f"already gone: {self.dest}",
            "restored": f"already put back: {self.dest}",
        }[self.kind]


def backup_plan(dest: str, backup: str, item: dict | None) -> str:
    """What happens to OUT/old-patches/<path> before dest is replaced: "take" a backup of dest (there is none yet),
    "keep" the one there (it is dest, or the file of before an earlier install from OUT whose archive dest still is),
    put it "aside" first (another install replaced the archive since: going back to that backup would undo it), or
    none at all, "added": dest is the archive an earlier install from OUT added (a new archive, its record says no
    backup) and still is, so going back removes it as before; a backup of it would put that earlier copy back."""
    if not os.path.lexists(backup):
        if (item is not None and not item["backup"] and os.path.isfile(dest)
                and fingerprint(dest) == installed_of(item)):
            return "added"

        return "take" if os.path.isfile(dest) else ""

    if os.path.isfile(dest) and same_file(dest, backup):
        return "keep"

    if (item is not None and item["backup"] and os.path.isfile(dest) and fingerprint(dest) == installed_of(item)
            and os.path.isfile(backup) and fingerprint(backup) == backup_of(item)):
        return "keep"

    return "aside"


def plan_install(out_dir: str, patches_dir: str, manifest: dict | None, entries: list[dict],
                 record: dict | None = None) -> list[Action]:
    actions = []
    done = (record or {}).get("archives", {})

    for item in entries:
        parts = safe_rel(item["rel"])
        rel = "/".join(parts)
        src = os.path.join(out_dir, "client", *parts)
        link = os.path.join(patches_dir, *parts)
        dest = os.path.realpath(link)
        backup = os.path.join(out_dir, OLD_PATCHES, *parts)
        made = (item.get("out_size"), item.get("out_mtime_ns"))
        where = (rel, src, link, dest, backup)

        if not os.path.isfile(src):
            if manifest is not None and os.path.isfile(dest) and fingerprint(dest) == made:
                actions.append(Action("installed", *where))
                continue

            raise InstallError(f"{src} is missing"
                               + (" and the patch folder's file is not the archive the tool wrote" if manifest else ""))

        plan = backup_plan(dest, backup, done.get(rel))

        if manifest is None:
            actions.append(Action("replace" if os.path.isfile(dest) else "add", *where, plan))
            continue

        if os.path.getsize(src) != item.get("out_size"):
            raise InstallError(f"{src} is not the archive the tool wrote ({os.path.getsize(src)} bytes, it wrote "
                               f"{item.get('out_size')})")

        if item["origin"] == "patches":
            if not os.path.isfile(dest):
                raise InstallError(f"{link}: the patch folder no longer has this archive; run the tool again")

            if fingerprint(dest) != (item.get("size"), item.get("mtime_ns")):
                raise InstallError(f"{dest} changed since the tool read it (size or modification time): the "
                                   "patches changed, so this output may no longer fit them. Run the tool again, then "
                                   "install its new output")

            actions.append(Action("replace", *where, plan))
        else:
            if os.path.lexists(link):
                origin = "the game folder" if item["origin"] == "client" else "nowhere (a new archive)"
                raise InstallError(f"{link} exists now, but the tool read {item['rel']} from {origin}: run the tool "
                                   "again")

            source = item.get("source")
            read = (item.get("size"), item.get("mtime_ns"))

            if item["origin"] == "client" and source and (not os.path.isfile(source) or fingerprint(source) != read):
                raise InstallError(f"{source} changed since the tool read it: run the tool again")

            actions.append(Action("add", *where, plan))

    return actions


def plan_restore(out_dir: str, patches_dir: str, record: dict | None) -> list[Action]:
    """What --restore does: by the record of each install from OUT, or, without one, by the bytes of OUT/client."""
    actions = []
    other = ("another install has replaced it since, and putting the old copy back would undo that one too. Nothing "
             "was changed")

    if record is not None:
        for rel, item in sorted(record["archives"].items()):
            parts = safe_rel(rel)
            link = os.path.join(patches_dir, *parts)
            dest = os.path.realpath(link)
            backup = os.path.join(out_dir, OLD_PATCHES, *parts)
            current = fingerprint(dest) if os.path.isfile(dest) else None

            if item["backup"]:
                if not os.path.isfile(backup):
                    raise InstallError(f"{backup} is missing: the archive install replaced cannot be put back")

                if fingerprint(backup) != backup_of(item):
                    raise InstallError(f"{backup} is not the file install replaced (it changed since): it cannot be "
                                       "put back")

                if current is not None and same_file(dest, backup):
                    actions.append(Action("restored", rel, backup, link, dest, backup))
                elif current == installed_of(item):
                    actions.append(Action("restore", rel, backup, link, dest, backup))
                else:
                    raise InstallError(f"{dest} is not the archive install put there: {other}")
            elif not os.path.lexists(link):
                actions.append(Action("absent", rel, "", link, dest, backup))
            elif current == installed_of(item):
                actions.append(Action("remove", rel, "", link, dest, backup))
            else:
                raise InstallError(f"{dest} is not the archive install added: {other} (remove it by hand if you mean "
                                   "to)")

        return actions

    for item in discover(os.path.join(out_dir, OLD_PATCHES)):
        parts = safe_rel(item["rel"])
        link = os.path.join(patches_dir, *parts)
        dest = os.path.realpath(link)
        backup = os.path.join(out_dir, OLD_PATCHES, *parts)
        copied = os.path.join(out_dir, "client", *parts)

        if os.path.isfile(dest) and same_file(dest, backup):
            actions.append(Action("restored", item["rel"], backup, link, dest, backup))
        elif os.path.isfile(dest) and os.path.isfile(copied) and same_bytes(dest, copied):
            actions.append(Action("restore", item["rel"], backup, link, dest, backup))
        else:
            raise InstallError(f"{out_dir} has no record of what was installed from it ({OLD_PATCHES}/{RECORD}: an "
                               f"install by hand, as the runbooks did before), and {dest} is not byte for byte "
                               f"{copied}, the archive such an install copied there: another install may have "
                               "replaced it since, and putting the old copy back would undo that one too. Nothing was "
                               "changed")

    if not actions:
        raise InstallError(f"{os.path.join(out_dir, OLD_PATCHES)} holds nothing to put back: nothing was installed "
                           f"from {out_dir}")

    return actions


# --- doing it ----------------------------------------------------------------------------------------------------


# os.link's errors on a filesystem without hard links, or across filesystems
NO_LINK = {getattr(errno, name) for name in ("EXDEV", "EPERM", "EOPNOTSUPP", "ENOTSUP", "EMLINK", "ENOSYS")
           if hasattr(errno, name)}


def copy_synced(src: str, dst: str):
    """dst as a complete copy of src (data, mode and times), on disk before it returns."""
    with open(src, "rb") as fin, open(dst, "wb") as fout:
        shutil.copyfileobj(fin, fout, 16 * 1024 * 1024)
        fout.flush()
        os.fsync(fout.fileno())

    shutil.copystat(src, dst)


def sync_folder(folder: str):
    try:
        fd = os.open(folder, os.O_RDONLY)
    except OSError:
        return

    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def aside_path(out_dir: str, rel: str) -> str:
    """OUT/old-patches-<n>/<path> for the lowest n not taken."""
    n = 1

    while os.path.lexists(os.path.join(out_dir, f"{OLD_PATCHES}-{n}", *rel.split("/"))):
        n += 1

    return os.path.join(out_dir, f"{OLD_PATCHES}-{n}", *rel.split("/"))


def keep_backup(action: Action, out_dir: str, say) -> None:
    """OUT/old-patches/<path> before dest is replaced, as action.backup_plan says: a new backup is a hard link when it
    can be, else a copy."""
    if action.backup_plan == "aside":
        aside = aside_path(out_dir, action.rel)
        os.makedirs(os.path.dirname(aside), exist_ok=True)
        os.rename(action.backup, aside)
        say(f"older backup moved to {aside}: another install replaced {action.dest} since the one from this folder")

    if action.kind != "replace":
        return

    if action.backup_plan == "keep":
        say(f"backup already there: {action.backup}")
        return

    if action.backup_plan == "added":
        say(f"no backup: an earlier install from this folder added {action.dest} (--restore removes it)")
        return

    os.makedirs(os.path.dirname(action.backup), exist_ok=True)

    try:
        os.link(action.dest, action.backup)
        say(f"backup: {action.backup} (hard link)")
    except OSError as e:
        if e.errno not in NO_LINK:
            raise

        copy_synced(action.dest, action.backup + ".part")
        os.replace(action.backup + ".part", action.backup)
        say(f"backup: {action.backup} (copy)")


def put_in_place(src: str, dest: str, move: bool) -> None:
    """src at dest in one step: first dest + ".new" next to it (renamed when move and on the same filesystem, else
    copied), then renamed over dest. The new file keeps the mode of the one it replaces."""
    tmp = dest + ".new"
    mode = stat.S_IMODE(os.stat(dest).st_mode) if os.path.exists(dest) else 0o644
    os.makedirs(os.path.dirname(dest), exist_ok=True)

    if os.path.lexists(tmp):
        os.remove(tmp)

    moved = False

    if move:
        try:
            os.rename(src, tmp)
            moved = True
        except OSError as e:
            if e.errno != errno.EXDEV:
                raise
    else:
        try:
            os.link(src, tmp)
        except OSError as e:
            if e.errno not in NO_LINK:
                raise
        else:
            moved = True

    if not moved:
        copy_synced(src, tmp)

    os.chmod(tmp, mode)
    os.replace(tmp, dest)
    sync_folder(os.path.dirname(dest))

    if move and os.path.exists(src):
        os.remove(src)  # copied across filesystems: the move is complete only now


def dry_backup_text(action: Action, out_dir: str) -> str:
    if action.backup_plan == "aside":
        text = f"would move the older backup {action.backup} to {aside_path(out_dir, action.rel)}"
        return text + (f" and back up {action.dest} there anew" if action.kind == "replace" else "")

    return {"take": f"would back up {action.dest} to {action.backup}",
            "keep": f"would keep the backup {action.backup}",
            "added": f"would keep no backup: an earlier install from this folder added {action.dest}"}.get(
                action.backup_plan, "")


def run(out_dir: str, patches_dir: str, dry_run: bool = False, restore: bool = False, say=print) -> int:
    out_dir = os.path.abspath(out_dir)
    patches_dir = os.path.abspath(patches_dir)

    if not os.path.isdir(patches_dir):
        raise InstallError(f"--patches {patches_dir} is not a folder")

    if not os.path.isdir(out_dir):
        raise InstallError(f"--from {out_dir} is not a folder")

    manifest = load_manifest(out_dir)
    record = load_record(out_dir)

    if restore:
        # the record, not install.json: a later run of the tool into OUT rewrites install.json, and may have failed
        recorded = (record or {}).get("patches") or (manifest or {}).get("patches")

        if recorded and os.path.realpath(recorded) != os.path.realpath(patches_dir):
            raise InstallError(f"{out_dir} was installed into the patch folder {recorded}, not {patches_dir}")

        if record is None:
            say(f"No {OLD_PATCHES}/{RECORD} in {out_dir} (an install by hand, or an older RaceForge): each archive is "
                "put back only where the patch folder still holds the one of client/, byte for byte.")

        actions = plan_restore(out_dir, patches_dir, record)
    else:
        if manifest is None:
            entries = discover(os.path.join(out_dir, "client"))
            say(f"No {INSTALL_FILE} in {out_dir} (an output folder of an older RaceForge): the check that the patch "
                "folder did not change since the tool read it is skipped.")
        else:
            entries = manifest["archives"]

            if manifest.get("checks_passed") is False:
                raise InstallError(f"the run that wrote {out_dir} did not finish or failed some checks (see its "
                                   "report.txt): nothing is installed")

            recorded = manifest.get("patches")

            if recorded and os.path.realpath(recorded) != os.path.realpath(patches_dir):
                raise InstallError(f"{out_dir} was made from the patch folder {recorded}, not {patches_dir}")

        if record is not None and record.get("patches") and (
                os.path.realpath(record["patches"]) != os.path.realpath(patches_dir)):
            raise InstallError(f"{out_dir} was installed into the patch folder {record['patches']}, not {patches_dir}")

        actions = plan_install(out_dir, patches_dir, manifest, entries, record)

    work = [a for a in actions if a.kind not in ("installed", "absent", "restored")]

    for action in actions:
        say(("would " if dry_run and action in work else "") + action.text())

        if dry_run and action in work and dry_backup_text(action, out_dir):
            say(dry_backup_text(action, out_dir))

    if not work:
        what = "every archive is already put back." if restore else "every archive is already in place."
        say("Nothing to do: " + (what if actions else f"{out_dir} has no archives."))
        return 0

    if dry_run:
        say("Dry run: nothing was changed.")
        return 0

    if restore:
        for action in work:
            if action.kind == "remove":
                os.remove(action.dest)
                sync_folder(os.path.dirname(action.dest))
                say(f"removed: {action.dest}")
            else:
                put_in_place(action.src, action.dest, move=False)
                say(f"restored: {action.dest}")
    else:
        record = record or {"_readme": "For raceforge.py install --restore: per archive of the patch folder, the "
                                       f"backup in {OLD_PATCHES}/ (false: install added the archive) and the file "
                                       "install put there, by size and mtime_ns.",
                            "patches": os.path.realpath(patches_dir), "archives": {}}

        for action in work:
            keep_backup(action, out_dir, say)

        for action in work:
            # an archive an earlier install from OUT added stays one install added: --restore removes it
            item = {"backup": action.kind == "replace" and action.backup_plan != "added",
                    "tool": (manifest or {}).get("tool", ""), "at": now()}

            if item["backup"]:
                item["backup_size"], item["backup_mtime_ns"] = fingerprint(action.backup)

            # recorded before the archive moves (the move keeps its size and time), so a stop in between leaves a
            # record that --restore can go by
            item["installed_size"], item["installed_mtime_ns"] = fingerprint(action.src)
            record["archives"][action.rel] = item
            save_record(out_dir, record)
            put_in_place(action.src, action.dest, move=True)

            if fingerprint(action.dest) != installed_of(item):
                item["installed_size"], item["installed_mtime_ns"] = fingerprint(action.dest)
                save_record(out_dir, record)

            say({"replace": "replaced", "add": "added"}[action.kind] + f": {action.dest}")

    say(f"Now publish it: {PUBLISH}")
    return 0
