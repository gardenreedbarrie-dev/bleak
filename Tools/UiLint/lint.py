#!/usr/bin/env python3
# UiLint: static checks for a 3.3.5a addon folder (default: Interface/AddOns/Bleakhold).
#
#   python3 -I Tools/UiLint/lint.py [--wowlua PATH] [--root REPO] [addon dir...]
#
# Checks:
#   lua      every .lua parses with the client's own Lua 5.1 parser (wowlua -p)
#   xml      every .xml is well-formed (xmllint --noout); <Script file>/<Include file> resolve
#   toc      "## Interface: 30300"; every listed file exists (case-insensitive, like the client);
#            no file under tests/ is listed; every .lua of the addon is listed
#   globals  global writes are Bleakhold* (or the few names FrameXML requires); global reads exist
#            in 3.3.5a: client C functions (extracted from the source), the Lua base set the game
#            opens, the client's compat aliases, framexml_globals.txt, or the addon's own globals
#   events   RegisterEvent("X") names exist in the client's event table (WoW/Source/Ui/Types.h)
#   api      no API of later clients (C_Timer, SetColorTexture, BackdropTemplate, SetAtlas, ...)
#   art      texture paths into the addon resolve to a .tga/.blp; every .tga is 32/24-bit,
#            power-of-two and at least 8x8
#   content  no Pandaren or Monk anywhere (10 stock classes only)
import argparse
import importlib.util
import os
import re
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))

ALLOWED_SET = re.compile(r"^(Bleakhold\w*|SLASH_BLEAKHOLD(?:TELL|TRANSMOG)?\d+|BINDING_HEADER_BLEAKHOLD|BINDING_NAME_BLEAKHOLD_\w+|ToggleCollectionsJournal|ChatEdit_ExtractTellTarget)$")
FORBIDDEN = [
    (re.compile(r"\bC_[A-Z]\w*\s*\."), "C_* namespaces do not exist in 3.3.5a"),
    (re.compile(r"\bC_Timer\b"), "C_Timer does not exist in 3.3.5a"),
    (re.compile(r"SetColorTexture"), "SetColorTexture does not exist in 3.3.5a (use SetTexture(r,g,b,a))"),
    (re.compile(r"BackdropTemplate"), "BackdropTemplate does not exist in 3.3.5a"),
    (re.compile(r"SetAtlas|GetAtlasInfo"), "atlases do not exist in 3.3.5a"),
    (re.compile(r"\bUnitPopup\w*"), "UnitPopup menus must not be modified (taint)"),
    (re.compile(r"RegisterAddonMessagePrefix|C_ChatInfo"), "no addon prefix registration in 3.3.5a"),
    (re.compile(r"\bIsInGroup\b|\bIsInRaid\b|UnitIsGroupLeader|GetNumGroupMembers"), "post-3.3.5a group API"),
]
CONTENT = re.compile(r"pandaren|\bmonk\b|\bMONK\b", re.I)
EVENT_RE = re.compile(r"RegisterEvent\(\s*[\"']([A-Za-z0-9_]+)[\"']")
TEX_RE = re.compile(r"[\"'](Interface\\\\AddOns\\\\Bleakhold\\\\[^\"']+)[\"']")
ART_RE = re.compile(r"(?:UI\.)?ART\s*\.\.\s*[\"']([A-Za-z0-9_]+)[\"']")


# Lua functions Bleakhold.exe adds to the 3.3.5a API, read from the client's own registration table so the lint
# and the client cannot drift apart (the addon checks that each exists before calling it).
CLIENT_API_SOURCES = (("WoW/Source/Ui/BleakholdDance.cpp", re.compile(r'\{\s*"(BleakholdDance_\w+)",\s*&Script_')),)


def client_api(root):
    names = set()
    for rel_path, pattern in CLIENT_API_SOURCES:
        path = os.path.join(root, rel_path)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as fh:
                names |= set(pattern.findall(fh.read()))
    return names


class Report:
    def __init__(self):
        self.errors = []
        self.counts = {}

    def err(self, check, msg):
        self.errors.append("%-8s %s" % (check, msg))

    def count(self, check, n=1):
        self.counts[check] = self.counts.get(check, 0) + n


def load_extract(root):
    spec = importlib.util.spec_from_file_location("uilint_extract_api", os.path.join(HERE, "extract_api.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.extract(root)


def ci_resolve(base, rel):
    """Resolve rel (backslashes or slashes) under base case-insensitively, like the client's loose-file lookup."""
    parts = [p for p in re.split(r"[\\/]+", rel) if p and p != "."]
    cur = base
    for p in parts:
        if p == "..":
            cur = os.path.dirname(cur)
            continue
        try:
            names = os.listdir(cur)
        except OSError:
            return None
        match = [n for n in names if n.lower() == p.lower()]
        if not match:
            return None
        cur = os.path.join(cur, match[0])
    return cur


def is_pow2(n):
    return n >= 8 and (n & (n - 1)) == 0


def check_tga(path, rep):
    with open(path, "rb") as f:
        head = f.read(18)
    if len(head) < 18:
        rep.err("art", "%s: truncated TGA header" % path)
        return
    idlen, cmtype, itype = head[0], head[1], head[2]
    w, h, depth = struct.unpack("<HHB", head[12:17])
    if itype not in (2, 10) or cmtype != 0:
        rep.err("art", "%s: TGA image type %d (want 2 or 10, no colour map)" % (path, itype))
    if depth not in (24, 32):
        rep.err("art", "%s: %d-bit TGA (want 24 or 32)" % (path, depth))
    if not (is_pow2(w) and is_pow2(h)):
        rep.err("art", "%s: %dx%d is not power-of-two and at least 8x8" % (path, w, h))
    rep.count("art")


def lint_addon(addon, api, wowlua, framexml, rep):
    name = os.path.basename(os.path.normpath(addon))
    files = []
    for dp, dn, fn in os.walk(addon):
        for f in fn:
            files.append(os.path.join(dp, f))
    lua_files = sorted(f for f in files if f.lower().endswith(".lua"))
    xml_files = sorted(f for f in files if f.lower().endswith(".xml"))
    tga_files = sorted(f for f in files if f.lower().endswith(".tga"))
    rel = lambda p: os.path.relpath(p, addon).replace(os.sep, "/")
    in_tests = lambda p: rel(p).lower().startswith("tests/")

    # --- lua parse
    for f in lua_files:
        r = subprocess.run([wowlua, "-p", f], capture_output=True, text=True)
        if r.returncode != 0:
            rep.err("lua", r.stderr.strip() or ("%s: parse failed" % f))
        rep.count("lua")

    # --- xml
    for f in xml_files:
        r = subprocess.run(["xmllint", "--noout", f], capture_output=True, text=True)
        if r.returncode != 0:
            rep.err("xml", r.stderr.strip())
            continue
        rep.count("xml")
        try:
            tree = ET.parse(f)
        except ET.ParseError as e:
            rep.err("xml", "%s: %s" % (f, e))
            continue
        for el in tree.iter():
            tag = el.tag.split("}")[-1]
            if tag in ("Script", "Include") and el.get("file"):
                if not ci_resolve(os.path.dirname(f), el.get("file")):
                    rep.err("xml", "%s: <%s file=\"%s\"> not found" % (rel(f), tag, el.get("file")))

    # --- toc
    tocs = [f for f in files if f.lower().endswith(".toc")]
    listed = set()
    main_toc = ci_resolve(addon, name + ".toc")
    if not main_toc:
        rep.err("toc", "%s: missing %s.toc" % (addon, name))
    for toc in tocs:
        with open(toc, "r", encoding="utf-8-sig", errors="replace") as fh:
            lines = fh.read().splitlines()
        if not any(re.match(r"^##\s*Interface:\s*30300\s*$", l) for l in lines):
            rep.err("toc", "%s: needs '## Interface: 30300'" % rel(toc))
        for l in lines:
            l = l.rstrip()
            if not l or l.startswith("#"):
                continue
            target = ci_resolve(os.path.dirname(toc), l)
            if not target:
                rep.err("toc", "%s: listed file not found: %s" % (rel(toc), l))
                continue
            listed.add(os.path.normcase(os.path.abspath(target)))
            if in_tests(target):
                rep.err("toc", "%s: test file must not be loaded: %s" % (rel(toc), l))
            rep.count("toc")
    for f in lua_files:
        if not in_tests(f) and os.path.normcase(os.path.abspath(f)) not in listed:
            rep.err("toc", "%s is not listed in the TOC" % rel(f))

    # --- globals (addon files only, tests excluded)
    addon_lua = [f for f in lua_files if not in_tests(f)]
    known = set(api["globals"]) | set(api["compat"]) | set(api["luabase"]) | framexml
    known |= client_api(os.path.normpath(os.path.join(HERE, "..", "..")))
    sets, gets = {}, []
    if addon_lua:
        r = subprocess.run([wowlua, "-g"] + addon_lua, capture_output=True, text=True)
        for line in r.stdout.splitlines():
            m = re.match(r"^(.*):(\d+):(GET|SET):(.+)$", line)
            if not m:
                continue
            path, ln, kind, gname = m.group(1), int(m.group(2)), m.group(3), m.group(4)
            if kind == "SET":
                sets.setdefault(gname, (path, ln))
            else:
                gets.append((path, ln, gname))
    for gname, (path, ln) in sorted(sets.items()):
        rep.count("globals")
        if not ALLOWED_SET.match(gname):
            rep.err("globals", "%s:%d: writes global '%s' (only Bleakhold* globals)" % (rel(path), ln, gname))
    defined = set(sets)
    for path, ln, gname in gets:
        rep.count("globals")
        if gname not in known and gname not in defined:
            rep.err("globals", "%s:%d: reads global '%s', which 3.3.5a does not have" % (rel(path), ln, gname))

    # --- text checks: events, forbidden API, art paths, content
    art_dir = ci_resolve(addon, "Art")
    for f in [x for x in files if x.lower().endswith((".lua", ".xml", ".toc"))]:
        if in_tests(f):
            continue
        with open(f, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        code = text
        for i, line in enumerate(text.splitlines(), 1):
            stripped = line.split("--", 1)[0] if f.lower().endswith(".lua") else line
            for pat, why in FORBIDDEN:
                if pat.search(stripped):
                    rep.err("api", "%s:%d: %s" % (rel(f), i, why))
            if CONTENT.search(line):
                rep.err("content", "%s:%d: no Pandaren/Monk content" % (rel(f), i))
        for ev in EVENT_RE.findall(code):
            rep.count("events")
            if ev not in api["events"]:
                rep.err("events", "%s: unknown event %s" % (rel(f), ev))
        for path in TEX_RE.findall(code):
            sub = path.replace("\\\\", "\\").split("\\", 3)[3]
            if sub.endswith("\\"):
                continue
            if not (ci_resolve(addon, sub) or ci_resolve(addon, sub + ".tga") or ci_resolve(addon, sub + ".blp")):
                rep.err("art", "%s: texture not found: %s" % (rel(f), path))
            rep.count("art")
        for art in ART_RE.findall(code):
            if not art_dir or not (ci_resolve(art_dir, art + ".tga") or ci_resolve(art_dir, art + ".blp")):
                rep.err("art", "%s: Art\\%s not found" % (rel(f), art))
            rep.count("art")
    for f in tga_files:
        check_tga(f, rep)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.path.normpath(os.path.join(HERE, "..", "..")))
    ap.add_argument("--wowlua", default=os.path.join(HERE, "build", "wowlua"))
    ap.add_argument("addons", nargs="*")
    a = ap.parse_args()
    if not os.path.isfile(a.wowlua):
        print("lint: %s not found; run Tools/UiLint/build_wowlua.sh first" % a.wowlua, file=sys.stderr)
        return 2
    addons = a.addons or [os.path.join(a.root, "Interface", "AddOns", "Bleakhold")]
    api = load_extract(a.root)
    framexml = set()
    with open(os.path.join(HERE, "framexml_globals.txt"), "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#"):
                framexml.add(line)
    rep = Report()
    for addon in addons:
        lint_addon(addon, api, a.wowlua, framexml, rep)
    summary = ", ".join("%s %d" % (k, v) for k, v in sorted(rep.counts.items()))
    if rep.errors:
        for e in rep.errors:
            print(e)
        print("lint: %d problem(s) (%s)" % (len(rep.errors), summary))
        return 1
    print("lint: clean (%s)" % summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
