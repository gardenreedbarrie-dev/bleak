r"""Names of the customization art archives, and the guard that keeps them off names other patches use.

How the client finds patch archives (WoW/Source/WowServices/PatchFiles.cpp, OpenArchives in WoW/Source/Client.cpp):
it lists Data\patch-?.MPQ and Data\<locale>\patch-<locale>-?.MPQ, where '?' is exactly one character of any kind
(Blizzard::File::SimpleGlob, matched without regard to case), sorts them by full path with SStrCmpI (MSVC _strnicmp:
letters folded to lower case, then byte order) and gives the path that sorts last the highest priority. The stock
Data\patch-2.MPQ and patch-3.MPQ are in that same list; Data\patch.MPQ and Data\<locale>\patch-<locale>.MPQ come below
it, the base archives (common.MPQ, expansion.MPQ, lichking.MPQ, locale-<locale>.MPQ, ...) below everything. So:

- digits sort before letters: patch-3 < patch-6 < patch-A < patch-Z;
- case never matters: patch-s.MPQ and patch-S.MPQ are one file to Windows, to the client and to the launcher;
- patch-0 and patch-1 sort before the stock patch-2 and patch-3, which would then outrank them.

The art archives therefore use letters, the digits 4-9 or "~" (which sorts after every letter) only, and never a name
in taken_patches.json (or one already in the realm's patch folder, --patches-dir).
"""

from __future__ import annotations

import json
import os

TAKEN_FILE = "taken_patches.json"

# One character each: patch-<c>.MPQ. Digits below 4 are the stock patches or sort below them; "~" sorts after every
# letter (customize's model archive patch-~.MPQ).
ART_CHARACTERS = "456789ABCDEFGHIJKLMNOPQRSTUVWXYZ~"


class PatchNameError(Exception):
    pass


def name_key(name: str) -> str:
    """How the client and Windows compare two archive paths: case and slash direction ignored."""
    return name.replace("\\", "/").casefold()


def art_archive_names(letters: str, dbc_mpq: str | None) -> list[str]:
    """patch-<c>.MPQ for every character of letters, without the DBC archive's own name."""
    letters = letters.upper()

    if not letters or any(c not in ART_CHARACTERS for c in letters) or len(set(letters)) != len(letters):
        raise PatchNameError(f"--art-letters {letters!r}: give distinct characters from A-Z, 4-9 and ~ (patch-0 and "
                             "patch-1 sort below the stock patch-2 and patch-3, which are taken)")

    names = [f"patch-{c}.MPQ" for c in letters]

    if dbc_mpq:
        names = [n for n in names if name_key(n) != name_key(dbc_mpq)]

    if not names:
        raise PatchNameError(f"--art-letters {letters!r}: {dbc_mpq} is the DBC archive; give other characters for "
                             "the art")

    return names


def load_taken(path: str) -> dict[str, str]:
    """taken_patches.json as {name key: owner}."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise PatchNameError(f"{path} is missing: RaceForge needs it to keep the art archives off the names other "
                             "patches use") from None
    except (OSError, ValueError) as e:
        raise PatchNameError(f"{path}: {e}") from None

    groups = data.get("taken") if isinstance(data, dict) else None

    if not isinstance(groups, list) or not groups:
        raise PatchNameError(f"{path}: needs a \"taken\" list of {{\"comment\": owner, \"names\": [...]}}")

    taken = {}

    for i, group in enumerate(groups):
        if not isinstance(group, dict) or not isinstance(group.get("comment"), str) or not group["comment"].strip():
            raise PatchNameError(f"{path}: taken[{i}] needs a \"comment\" naming the owner")

        names = group.get("names")

        if not isinstance(names, list) or not names or not all(isinstance(n, str) and n.strip() for n in names):
            raise PatchNameError(f"{path}: taken[{i}] ({group['comment']}) needs a \"names\" list of archive names")

        for name in names:
            key = name_key(name.strip())

            if key in taken:
                raise PatchNameError(f"{path}: {name} is listed twice ({taken[key]}; {group['comment']})")

            taken[key] = group["comment"]

    return taken


REALM_GROUP = "Bleakhold realm"  # the realm's own archives: the tools may rebuild them
STOCK_GROUP = "Blizzard"
CUSTOMIZE_GROUP = "RaceForge customize"


def load_groups(path: str) -> list[tuple[str, set[str]]]:
    """taken_patches.json as [(owner comment, {name key})], checked as load_taken() checks it."""
    load_taken(path)

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    return [(g["comment"], {name_key(n.strip()) for n in g["names"]}) for g in data["taken"]]


def realm_owned(groups: list[tuple[str, set[str]]]) -> set[str]:
    """The names of the Bleakhold realm group (REALM_GROUP): the archives the realm owns and its tools rebuild."""
    found = [names for comment, names in groups if comment.startswith(REALM_GROUP)]

    if not found:
        raise PatchNameError(f"{TAKEN_FILE} has no \"{REALM_GROUP}\" group naming the realm's own archives")

    return set().union(*found)


def foreign(groups: list[tuple[str, set[str]]]) -> dict[str, str]:
    """{name key: owner} of the archives another project owns (Reforged, WoW Forever, MapForge, CafeForge, ...):
    every group but the stock patches, the realm's own and customize's own archives. No tool rebuilds them."""
    keep = (REALM_GROUP, STOCK_GROUP, CUSTOMIZE_GROUP)
    return {n: comment for comment, names in groups if not comment.startswith(keep) for n in names}


def scan_patches_dir(folder: str) -> dict[str, str]:
    """Every name in a patch folder (the realm's patches/, or a client's Data folder; a client folder's Data
    subfolder is read too), as {name key: path}. Folders count as well: the client opens a folder named
    patch-?.MPQ as an archive (SFileOpenArchive, OpenDirectPathAsArchive)."""
    if not os.path.isdir(folder):
        raise PatchNameError(f"--patches-dir {folder} is not a folder")

    folders = [folder]
    folders += [os.path.join(folder, e) for e in os.listdir(folder)
                if e.casefold() == "data" and os.path.isdir(os.path.join(folder, e))]
    present = {}

    for top in folders:
        for entry in os.listdir(top):
            present.setdefault(name_key(entry), os.path.join(top, entry))

    return present


def problems(names: list[str], taken: dict[str, str], present: dict[str, str] | None = None) -> list[str]:
    """Why each of names may not be written: taken by another patch, or already in the patch folder."""
    out = []

    for name in names:
        key = name_key(name)

        if key in taken:
            out.append(f"{name} is taken by {taken[key]}")

        if present and key in present:
            out.append(f"{name} is already in the patch folder: {present[key]}")

    return out


def free_characters(taken: dict[str, str], present: dict[str, str] | None = None, dbc_mpq: str | None = None) -> str:
    """The art characters no patch uses."""
    used = set(taken) | set(present or ()) | ({name_key(dbc_mpq)} if dbc_mpq else set())
    return "".join(c for c in ART_CHARACTERS if name_key(f"patch-{c}.MPQ") not in used)
