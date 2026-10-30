#!/usr/bin/env python3
# Self-test for lint.py: builds a deliberately broken addon in a temporary folder and checks that every
# lint rule reports it. Run with python3 -I (check.sh does).
import os
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

BAD = {
    "BadAddon.toc": "## Interface: 30200\nCore.lua\nmissing.lua\ntests\\test_x.lua\n",
    "Core.lua": "\n".join([
        "local ADDON, ns = ...",
        "leaked = 1",                                   # global write
        "C_Timer.After(1, function() end)",             # later API
        "local t = UIParent:CreateTexture() t:SetColorTexture(1, 0, 0)",
        "if IsInGroup() then end",                      # later group API
        "local f = CreateFrame('Frame', nil, UIParent, 'BackdropTemplate')",
        "f:RegisterEvent(\"NOT_AN_EVENT\")",
        "local x = NoSuchGlobalFunction()",             # unknown global read
        "local cls = 'MONK'",                           # content
        "local tex = 'Interface\\\\AddOns\\\\Bleakhold\\\\Art\\\\Nope'",
        "local j = 'Interface\\\\AddOns\\\\Bleakhold\\\\Art\\\\Journal\\\\Oops'",  # not bg_/btn_<KEY>
    ]) + "\n",
    "Unlisted.lua": "local a = 1\n",
    "Broken.lua": "local x = = 1\n",
    "Bad.xml": "<Ui><Script file=\"gone.lua\"/></Ui>\n",
    "Malformed.xml": "<Ui><Frame></Ui>\n",
    "tests/test_x.lua": "local ok = true\n",
}

EXPECT = [
    ("toc", "Interface: 30300"),
    ("toc", "missing.lua"),
    ("toc", "test file must not be loaded"),
    ("toc", "Unlisted.lua is not listed"),
    ("lua", "unexpected symbol"),
    ("xml", "gone.lua"),
    ("xml", "Malformed.xml"),
    ("globals", "writes global 'leaked'"),
    ("globals", "reads global 'NoSuchGlobalFunction'"),
    ("api", "C_Timer"),
    ("api", "SetColorTexture"),
    ("api", "BackdropTemplate"),
    ("api", "post-3.3.5a group API"),
    ("events", "NOT_AN_EVENT"),
    ("content", "Pandaren/Monk"),
    ("art", "texture not found"),
    ("art", "a Journal picture is bg_<KEY> or btn_<KEY>"),
    ("art", "not power-of-two"),
]


def tga(path, w, h):
    head = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, w, h, 32, 8)
    with open(path, "wb") as f:
        f.write(head + b"\xff" * (w * h * 4))


def main():
    wowlua = os.path.join(HERE, "build", "wowlua")
    build = os.path.join(HERE, "build")
    with tempfile.TemporaryDirectory(dir=build if os.path.isdir(build) else None) as tmp:
        addon = os.path.join(tmp, "BadAddon")
        for rel, text in BAD.items():
            p = os.path.join(addon, *rel.split("/"))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w") as f:
                f.write(text)
        os.makedirs(os.path.join(addon, "Art"), exist_ok=True)
        tga(os.path.join(addon, "Art", "Odd.tga"), 48, 32)
        r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "lint.py"), "--wowlua", wowlua, addon],
                           capture_output=True, text=True)
        out = r.stdout + r.stderr
        missing = [(c, s) for c, s in EXPECT if not any(l.startswith(c) and s in l for l in out.splitlines())]
        if r.returncode == 0:
            print("lint self-test: lint accepted a broken addon")
            print(out)
            return 1
        if missing:
            print("lint self-test: rules that did not fire:")
            for c, s in missing:
                print("  %s: %s" % (c, s))
            print(out)
            return 1
    print("lint self-test: all %d rules fire" % len(EXPECT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
