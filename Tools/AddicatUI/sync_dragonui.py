#!/usr/bin/env python3
"""AddicatUI from DragonUI: copy an upstream DragonUI checkout into the AddicatUI addon folders, renamed.

    python3 -I sync_dragonui.py code <dragonui checkout> [<AddOns folder>]   the code (into the repository)
    python3 -I sync_dragonui.py art <dragonui checkout> <AddOns folder>      the art, the font and the game data

AddicatUI is Bleakhold's interface, a fork of DragonUI (https://github.com/NeticSoul/DragonUI, MIT, by NeticSoul and
DragonUI's contributors). "code" copies DragonUI/ and DragonUI_Options/ into AddicatUI/ and AddicatUI_Options/
(default: Interface/AddOns of this repository), renaming DragonUI to AddicatUI in names, paths and text, and /dui
to /aui. It leaves out what may not be published in this repository: the textures (World of Warcraft artwork, see
DragonUI's THIRD_PARTY_NOTICES.md), the Expressway font (its licence asks for payment when it ships with
software) and the tables made from the game's DBC files and AzerothCore's tables. "art" copies exactly those into
an AddOns folder of a client package (the CI package step runs it on the commit named in UPSTREAM): the textures
and the font into their own addon, AddicatUI_Art, which AddicatUI needs (## Dependencies), so the game does not
load AddicatUI at all without its art; the tables into AddicatUI, whose namespace they fill.

Licence texts and notices are copied word for word. "code" writes over the files it copies and deletes nothing:
AddicatUI has its own changes, so take a newer DragonUI by running "code" on a branch that holds only the
previous import and merging that branch. Standard library only.
"""

import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
ADDONS = os.path.join(REPO, "Interface", "AddOns")

FOLDERS = {"DragonUI": "AddicatUI", "DragonUI_Options": "AddicatUI_Options"}
ART_ADDON = "AddicatUI_Art"
# Where "art" puts the upstream art in AddicatUI_Art, and the paths the code then uses.
ART_HOME = [("DragonUI/Textures", "Textures"), ("DragonUI_Options/Textures", "OptionsTextures"),
            ("DragonUI/Fonts/expressway.ttf", "Fonts/expressway.ttf")]
# The art's paths in the code (WoW paths ignore case; Lua strings double the backslash, XML does not).
PATHS = re.compile(r"(addons(?:\\{1,2}))addicatui((?:\\{1,2}))(textures|fonts(?:\\{1,2})expressway\.ttf)", re.IGNORECASE)
ART_TOC = """## Interface: 30300
## Title: AddicatUI Art
## Notes: DragonUI's artwork for AddicatUI. World of Warcraft art is (c) Blizzard Entertainment; see THIRD_PARTY_NOTICES.md.
## Author: DragonUI (NeticSoul and contributors), packaged for Bleakhold
## Version: {commit}
"""

# Never in the repository: copied by "art" into a package only.
ART = [
    "DragonUI/Textures",
    "DragonUI_Options/Textures",
    "DragonUI/Fonts/expressway.ttf",
    # game data (DragonUI's THIRD_PARTY_NOTICES.md, "Blizzard Entertainment artwork and game data")
    "DragonUI/modules/worldmap/fogdata.lua",
    "DragonUI/modules/worldmap/entrancedata.lua",
    "DragonUI/modules/worldmap/flightpointdata.lua",
    "DragonUI/modules/worldmap/graveyarddata.lua",
    "DragonUI/modules/worldmap/inndata.lua",
    "DragonUI/modules/spellbook/trainerdata.lua",
    "DragonUI/data/aura_durations.lua",
    "DragonUI/data/companion_traits.lua",
    "DragonUI/data/mount_speeds.lua",
]

# Copied as they are (licences and notices name DragonUI and the projects it credits).
VERBATIM = re.compile(r"(^|/)(LICENSE[^/]*|LICENSES/.*|THIRD_PARTY_NOTICES\.md)$")
TEXT = (".lua", ".xml", ".toc")

NAME = re.compile(r"(dragon)(ui)", re.IGNORECASE)
SLASH = re.compile(r'(?<=[/"])du(icomp|keybind|kb|i)\b')


def rename(text):
    """DragonUI -> AddicatUI in every spelling (DRAGONUI, dragonui, dragonUI...), /dui -> /aui."""
    def name(m):
        d, u = m.group(1), m.group(2)
        a = "addicat" if d.islower() else ("ADDICAT" if d.isupper() else "Addicat")
        return a + u
    text = NAME.sub(name, text)
    text = SLASH.sub(lambda m: "au" + m.group(1), text)
    return PATHS.sub(lambda m: m.group(1) + ART_ADDON + m.group(2) + m.group(3), text)


def is_art(rel):
    return any(rel == a or rel.startswith(a + "/") for a in ART)


def files(src):
    for folder in FOLDERS:
        base = os.path.join(src, folder)
        if not os.path.isdir(base):
            raise SystemExit("not a DragonUI checkout (no %s/): %s" % (folder, src))
        for root, dirs, names in os.walk(base):
            dirs.sort()
            for n in sorted(names):
                full = os.path.join(root, n)
                yield full, os.path.relpath(full, src).replace(os.sep, "/")


def target(rel, out):
    for upstream, home in ART_HOME:
        if rel == upstream or rel.startswith(upstream + "/"):
            return os.path.join(out, ART_ADDON, *(home + rel[len(upstream):]).split("/"))
    parts = rel.split("/")
    parts[0] = FOLDERS[parts[0]]
    parts[-1] = rename(parts[-1])
    return os.path.join(out, *parts)


def toc_dependency(out):
    """AddicatUI needs AddicatUI_Art: without the art the game leaves it off."""
    path = os.path.join(out, "AddicatUI", "AddicatUI.toc")
    with open(path, "r", encoding="utf-8", newline="") as f:
        text = f.read()
    if "## Dependencies:" not in text:
        nl = "\r\n" if "\r\n" in text else "\n"
        text = text.replace("## SavedVariables:", "## Dependencies: " + ART_ADDON + nl + "## SavedVariables:", 1)
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text)


def copy(full, rel, dest):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if rel.endswith(TEXT) and not VERBATIM.search(rel):
        with open(full, "rb") as f:
            data = f.read()
        text = data.decode("utf-8")
        with open(dest, "wb") as f:
            f.write(rename(text).encode("utf-8"))
    else:
        shutil.copyfile(full, dest)


def main(argv):
    if len(argv) < 2 or argv[0] not in ("code", "art"):
        print(__doc__)
        return 2
    mode, src = argv[0], argv[1]
    out = argv[2] if len(argv) > 2 else (ADDONS if mode == "code" else None)
    if not out:
        print("art needs the AddOns folder of a package")
        return 2
    count = 0
    for full, rel in files(src):
        if rel.split("/")[-1] in (".gitignore", ".gitattributes"):
            continue
        if is_art(rel) != (mode == "art"):
            continue
        copy(full, rel, target(rel, out))
        count += 1
    if mode == "code":
        toc_dependency(out)
    else:
        art = os.path.join(out, ART_ADDON)
        commit = upstream_commit(src)
        with open(os.path.join(art, ART_ADDON + ".toc"), "w", encoding="utf-8", newline="\n") as f:
            f.write(ART_TOC.format(commit=commit[:12]))
        shutil.copyfile(os.path.join(src, "DragonUI", "THIRD_PARTY_NOTICES.md"), os.path.join(art, "THIRD_PARTY_NOTICES.md"))
        shutil.copyfile(os.path.join(src, "DragonUI", "LICENSE.txt"), os.path.join(art, "LICENSE.txt"))
    print("%s: %d files from %s into %s" % (mode, count, src, out))
    return 0


def upstream_commit(src):
    head = os.path.join(src, ".git", "HEAD")
    try:
        with open(head) as f:
            ref = f.read().strip()
        if ref.startswith("ref: "):
            with open(os.path.join(src, ".git", ref[5:])) as f:
                return f.read().strip()
        return ref
    except OSError:
        return "unknown"


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
