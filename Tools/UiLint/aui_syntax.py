#!/usr/bin/env python3
"""Compile every Lua file of AddicatUI and AddicatUI_Options with the client's own Lua 5.1 (wowlua -p).

    python3 -I aui_syntax.py <wowlua> <AddOns folder> <scratch folder>

The client's luaL_loadbuffer skips a UTF-8 byte order mark, luaL_loadfile (wowlua -p) does not, so the files are
compiled from copies without it. Exit code 0 when every file compiles. Standard library only.
"""

import os
import shutil
import subprocess
import sys

ADDONS = ("AddicatUI", "AddicatUI_Options")
BOM = b"\xef\xbb\xbf"


def main(argv):
    if len(argv) != 3:
        print(__doc__)
        return 2
    wowlua, src, out = (os.path.abspath(a) for a in argv)
    shutil.rmtree(out, ignore_errors=True)
    files = []
    for addon in ADDONS:
        for top, dirs, names in os.walk(os.path.join(src, addon)):
            dirs.sort()
            for name in sorted(names):
                if not name.endswith(".lua"):
                    continue
                rel = os.path.relpath(os.path.join(top, name), src)
                with open(os.path.join(src, rel), "rb") as f:
                    data = f.read()
                dest = os.path.join(out, rel)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with open(dest, "wb") as f:
                    f.write(data[len(BOM):] if data.startswith(BOM) else data)
                files.append(rel)
    if not files:
        print("no AddicatUI files under %s" % src)
        return 1
    failed = 0
    for i in range(0, len(files), 200):
        r = subprocess.run([wowlua, "-p"] + files[i:i + 200], cwd=out, capture_output=True, text=True)
        if r.returncode:
            failed += 1
            sys.stdout.write(r.stdout + r.stderr)
    if failed:
        return 1
    print("AddicatUI: %d Lua files compile" % len(files))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
