#!/usr/bin/env python3
# Extract the in-game Lua API of the 3.3.5a client from its decompiled source, so lint and tests can
# check that the Bleakhold addon only uses functions, widget methods and events that exist in 3.3.5a.
#
#   python3 -I Tools/UiLint/extract_api.py [--root REPO] [--lua OUT.lua] [--summary]
#
# Sources (all under the repo root):
#   global functions: every FrameScript_Method / luaL_Reg table not named *Methods, outside WoW/Source/Glue
#                     (glue-screen functions do not exist in the game UI)
#   widget methods:   s_ScriptMethods tables, mapped to widget types by file (see FILE_TYPES)
#   events:           EVENT(NAME, n) entries of WoW/Source/Ui/Types.h
#   Lua globals:      the compat aliases in FrameScript.cpp (s_compatLua) and the stock library names
import argparse
import os
import re
import sys

FILE_TYPES = {
    "CScriptObject_Scripts.cpp": "ScriptObject",
    "CScriptRegion_Scripts.cpp": "Region",
    "CSimpleFrame_Scripts.cpp": "Frame",
    "CSimpleButton_Scripts.cpp": "Button",
    "CSimpleCheckbox_Scripts.cpp": "CheckButton",
    "CSimpleEditBox_Scripts.cpp": "EditBox",
    "CSimpleFont_Scripts.cpp": "Font",
    "CSimpleFontString_Scripts.cpp": "FontString",
    "CSimpleTexture_Scripts.cpp": "Texture",
    "CSimpleStatusBar_Scripts.cpp": "StatusBar",
    "CSimpleSlider_Scripts.cpp": "Slider",
    "CSimpleScrollFrame_Scripts.cpp": "ScrollFrame",
    "CSimpleModel_Scripts.cpp": "Model",
    "CSimpleMessageFrame_Scripts.cpp": "MessageFrame",
    "CSimpleMessageScrollFrame_Scripts.cpp": "ScrollingMessageFrame",
    "CSimpleHTML_Scripts.cpp": "SimpleHTML",
    "CSimpleColorSelect_Scripts.cpp": "ColorSelect",
    "CSimpleMovieFrame_Scripts.cpp": "MovieFrame",
    "CSimpleAnimGroup_Scripts.cpp": "AnimationGroup",
    "CSimpleAnim_Scripts.cpp": "Animation",
    "CSimpleAlphaAnim_Scripts.cpp": "Alpha",
    "CSimpleScaleAnim_Scripts.cpp": "Scale",
    "CSimpleRotationAnim_Scripts.cpp": "Rotation",
    "CSimpleTranslationAnim_Scripts.cpp": "Translation",
    "CSimplePathAnim_Scripts.cpp": "Path",
    "CSimpleControlPoint_Scripts.cpp": "ControlPoint",
    "CharacterModelBase_Scripts.cpp": "PlayerModel",
    "DressUpModelFrame_Scripts.cpp": "DressUpModel",
    "TabardModelFrame_Scripts.cpp": "TabardModel",
    "CGCooldown_Scripts.cpp": "Cooldown",
    "MinimapFrame_Scripts.cpp": "Minimap",
    "CGQuestPOIFrame_Scripts.cpp": "QuestPOIFrame",
    "Tooltip_Scripts.cpp": "GameTooltip",
}

# Widget inheritance of the 3.3.5a client (CSimple* class hierarchy).
PARENTS = {
    "ScriptObject": None,
    "Region": "ScriptObject",
    "Texture": "Region",
    "FontString": "Region",
    "Frame": "Region",
    "Button": "Frame",
    "CheckButton": "Button",
    "EditBox": "Frame",
    "StatusBar": "Frame",
    "Slider": "Frame",
    "ScrollFrame": "Frame",
    "Model": "Frame",
    "PlayerModel": "Model",
    "DressUpModel": "PlayerModel",
    "TabardModel": "PlayerModel",
    "MessageFrame": "Frame",
    "ScrollingMessageFrame": "Frame",
    "SimpleHTML": "Frame",
    "ColorSelect": "Frame",
    "MovieFrame": "Frame",
    "Cooldown": "Frame",
    "Minimap": "Frame",
    "QuestPOIFrame": "Frame",
    "GameTooltip": "Frame",
    "Font": "ScriptObject",
    "AnimationGroup": "ScriptObject",
    "Animation": "ScriptObject",
    "Alpha": "Animation",
    "Scale": "Animation",
    "Rotation": "Animation",
    "Translation": "Animation",
    "Path": "Animation",
    "ControlPoint": "ScriptObject",
}

# Font-instance methods are shared by these types in the client (CSimpleFontable mix-in): the font
# methods live in CSimpleFont_Scripts.cpp and are also exposed on these widgets.
FONTABLE = ("FontString", "EditBox", "MessageFrame", "ScrollingMessageFrame", "SimpleHTML")

TABLE_RE = re.compile(r"(?:FrameScript_Method|luaL_Reg)\s+([A-Za-z_][A-Za-z0-9_:]*)\s*\[\s*\]\s*=\s*\{(.*?)\n\s*\};", re.S)
ENTRY_RE = re.compile(r"\{\s*\"([A-Za-z_][A-Za-z0-9_]*)\"\s*,")
EVENT_RE = re.compile(r"EVENT\(\s*([A-Z0-9_]+)\s*,\s*\d+\s*\)")
COMPAT_RE = re.compile(r"\"([A-Za-z_][A-Za-z0-9_]*)\s*=")

LUA_BASE = [
    "assert", "collectgarbage", "error", "gcinfo", "getfenv", "getmetatable", "loadstring", "next", "pcall",
    "rawequal", "rawget", "rawset", "select", "setfenv", "setmetatable", "tonumber", "tostring", "type",
    "unpack", "xpcall", "ipairs", "pairs", "newproxy", "_G", "_VERSION", "coroutine", "string", "table",
    "math", "bit",
]


def scan_tables(root):
    globals_, methods = {}, {}
    for top in ("Engine/Source", "WoW/Source"):
        for dirpath, dirnames, filenames in os.walk(os.path.join(root, top)):
            rel = os.path.relpath(dirpath, root).replace(os.sep, "/")
            if rel.startswith("WoW/Source/Glue"):
                continue
            for fn in filenames:
                if not fn.endswith(".cpp"):
                    continue
                path = os.path.join(dirpath, fn)
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    text = f.read()
                for m in TABLE_RE.finditer(text):
                    name, body = m.group(1), m.group(2)
                    entries = ENTRY_RE.findall(body)
                    if "Methods" in name:
                        wtype = FILE_TYPES.get(fn)
                        if wtype:
                            methods.setdefault(wtype, set()).update(entries)
                    else:
                        for e in entries:
                            globals_.setdefault(e, rel + "/" + fn)
    return globals_, methods


def scan_events(root):
    with open(os.path.join(root, "WoW/Source/Ui/Types.h"), "r", encoding="utf-8", errors="replace") as f:
        return sorted(set(EVENT_RE.findall(f.read())))


def c_unescape(s):
    out, i = [], 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            n = s[i + 1]
            out.append({"n": "\n", "t": "\t", "\\": "\\", '"': '"', "'": "'"}.get(n, n))
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def scan_compat(root):
    """Names defined by the client's compat Lua (s_compatLua) and its source text."""
    with open(os.path.join(root, "Engine/Source/FrameScript/FrameScript.cpp"), "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    m = re.search(r"s_compatLua\s*=(.*?);\n", text, re.S)
    names, src = set(), []
    if m:
        for lit in re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(1)):
            src.append(c_unescape(lit))
        for line in "".join(src).splitlines():
            mm = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
            if mm:
                names.add(mm.group(1))
    return sorted(names), "".join(src)


def resolve_methods(methods):
    out = {}
    for wtype in PARENTS:
        acc, t = set(), wtype
        while t:
            acc |= methods.get(t, set())
            t = PARENTS[t]
        if wtype in FONTABLE:
            acc |= methods.get("Font", set())
        out[wtype] = acc
    return out


def extract(root):
    globals_, methods = scan_tables(root)
    compat_names, compat_src = scan_compat(root)
    return {
        "globals": globals_,
        "methods": resolve_methods(methods),
        "events": scan_events(root),
        "compat": compat_names,
        "compat_lua": compat_src,
        "luabase": LUA_BASE,
        "parents": PARENTS,
    }


def lua_str(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def write_lua(api, path):
    lines = ["-- Generated by Tools/UiLint/extract_api.py from the client source. Do not edit.", "return {"]
    lines.append("  globals = {")
    for name in sorted(api["globals"]):
        lines.append("    [%s] = true," % lua_str(name))
    lines.append("  },")
    lines.append("  methods = {")
    for wtype in sorted(api["methods"]):
        lines.append("    %s = {" % wtype)
        for m in sorted(api["methods"][wtype]):
            lines.append("      [%s] = true," % lua_str(m))
        lines.append("    },")
    lines.append("  },")
    lines.append("  events = {")
    for e in api["events"]:
        lines.append("    [%s] = true," % lua_str(e))
    lines.append("  },")
    lines.append("  compat = {")
    for c in api["compat"]:
        lines.append("    [%s] = true," % lua_str(c))
    lines.append("  },")
    lines.append("  parents = {")
    for t, p in sorted(api["parents"].items()):
        lines.append("    %s = %s," % (t, lua_str(p) if p else "false"))
    lines.append("  },")
    lines.append("  compat_lua = %s," % lua_str(api["compat_lua"]).replace("\n", "\\n"))
    lines.append("}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser()
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--root", default=os.path.normpath(os.path.join(here, "..", "..")))
    ap.add_argument("--lua")
    ap.add_argument("--summary", action="store_true")
    a = ap.parse_args()
    api = extract(a.root)
    if a.lua:
        write_lua(api, a.lua)
    if a.summary or not a.lua:
        print("globals:", len(api["globals"]), "events:", len(api["events"]), "compat:", len(api["compat"]))
        for wtype in sorted(api["methods"]):
            print("  %-22s %d" % (wtype, len(api["methods"][wtype])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
