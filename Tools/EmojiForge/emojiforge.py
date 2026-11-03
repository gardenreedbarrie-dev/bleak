#!/usr/bin/env python3
"""EmojiForge: the emoji catalogue and art of the Bleakhold emoji bubbles.

    python3 -I emojiforge.py generate [--check]
    python3 -I emojiforge.py art --noto DIR [--only KEY,KEY] [--preview DIR] [--jobs N] [--allow-other-commit]
    python3 -I emojiforge.py check
    python3 -I emojiforge.py patterns

emojis.json is the catalogue: the id, key, name and group of every emoji and where its picture comes from (a Noto
Emoji 3D image or a short text drawn with the Bangers font). generate writes the three files made from it:
Interface/AddOns/Bleakhold/EmojiData.lua (the addon's list), Server/mod-bleakhold-ui/src/BleakholdEmoji.h (the
server module's count and keys) and Interface/Bleakhold/Emoji/NOTICE.md (the attribution); --check only compares.
art draws Interface/Bleakhold/Emoji/EmojiNNN.blp (256x256 BLP2, DXT5 with every mip level, written by
Tools/BlpConvert/blpconvert.py) and needs Pillow; DIR is a checkout of noto-emoji at the commit emojis.json pins
(patterns prints its sparse-checkout patterns; README.md has the commands). check validates the catalogue, the
generated files and the art. generate, check and patterns need only the standard library.

Ids go on the wire (EMOJI <id>, then SMSG_PLAY_SPELL_VISUAL kit 900000 + id) and saved emote wheels hold
emoji:<key>, so the catalogue is append-only: never renumber, rename or remove an emoji.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.dont_write_bytecode = True  # keep the repository free of __pycache__
if os.path.join(REPO, "Tools", "BlpConvert") not in sys.path:
    sys.path.insert(0, os.path.join(REPO, "Tools", "BlpConvert"))

import blpconvert as bc  # noqa: E402

CATALOGUE = os.path.join(HERE, "emojis.json")
EMOJI_DIR = os.path.join(REPO, "Interface", "Bleakhold", "Emoji")
LICENSES = ("LICENSE-OFL-NotoEmoji.txt", "LICENSE-Apache-2.0.txt", "LICENSE-OFL-Bangers.txt")

# Fixed by the client (WoW/Common/BleakholdEmoji.h) and the server module (BleakholdCodec.h): emojis.json must
# hold exactly these values.
KIT_BASE = 900000
MAX_EMOJIS = 256
TEXTURE = "Interface\\Bleakhold\\Emoji\\Emoji%03d"
ART = {"size": 256, "pad": 8, "format": "dxt5"}
ART_LEVELS = 9  # 256x256 down to 1x1
NOTO_REPO = "https://github.com/googlefonts/noto-emoji"
NOTO_PATH = "3D/png/512/emoji_u{codepoints}.png"
NOTO_SIZE = 512
# Text emotes are drawn at twice the art size and must fit in this square (12 px margin at 1x), so that after the
# downscale the opaque letters stay inside [12, 244) and their soft edge inside the Noto art box [8, 248).
TEXT_BOX = 464

FIELDS = {
    "catalogue": ("format", "kitBase", "maxEmojis", "texture", "art", "noto", "font", "groups", "emojis"),
    "noto": ("repo", "commit", "path"),
    "font": ("file", "license", "sha256", "fill", "stroke"),
    "group": ("key", "label"),
}
ENTRY_FIELDS = ("id", "key", "name", "group")
ENTRY_SOURCES = ("noto", "text")

KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,23}$")
NAME_RE = re.compile(r"^[A-Za-z0-9 '!?.-]{1,24}$")
GROUP_RE = re.compile(r"^[a-z]+$")
NOTO_RE = re.compile(r"^[0-9a-f]{4,6}(_[0-9a-f]{4,6})*$")
TEXT_RE = re.compile(r"^[A-Z0-9]{1,5}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COLOUR_RE = re.compile(r"^[0-9A-F]{6}$")


class CatalogueError(Exception):
    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__("\n".join(self.problems))


# ------------------------------------------------------------------------------------------------ catalogue

def norm(s):
    """The name normal form the addon looks names up with: lower case, trimmed, no outer ':', '_' for spaces."""
    return re.sub(r"\s+", "_", s.lower().strip().strip(":"))


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _is_str(v, pattern=None):
    return isinstance(v, str) and (pattern is None or pattern.fullmatch(v) is not None)


def _json(v):
    return json.dumps(v, sort_keys=True)


def _check_fields(problems, where, obj, allowed, required=None):
    for name in obj:
        if name not in allowed:
            problems.append("%s: unknown field %r" % (where, name))
    for name in (allowed if required is None else required):
        if name not in obj:
            problems.append("%s: missing field %r" % (where, name))


def validate_catalogue(data):
    """Every problem of a parsed emojis.json (empty when it is valid)."""
    if not isinstance(data, dict):
        return ["the catalogue must be a JSON object"]
    problems = []
    _check_fields(problems, "catalogue", data, FIELDS["catalogue"])
    for name, want in (("format", 1), ("kitBase", KIT_BASE), ("maxEmojis", MAX_EMOJIS), ("texture", TEXTURE),
                       ("art", ART)):
        if name in data and _json(data[name]) != _json(want):
            problems.append("%s must be %s (the client and the server module depend on it), not %s"
                            % (name, _json(want), _json(data[name])))

    noto = data.get("noto")
    if isinstance(noto, dict):
        _check_fields(problems, "noto", noto, FIELDS["noto"])
        if "repo" in noto and noto["repo"] != NOTO_REPO:
            problems.append("noto.repo must be %s" % NOTO_REPO)
        if "path" in noto and noto["path"] != NOTO_PATH:
            problems.append("noto.path must be %s" % NOTO_PATH)
        if "commit" in noto and not _is_str(noto["commit"], COMMIT_RE):
            problems.append("noto.commit must be a full 40-digit lower-case commit hash")
    elif "noto" in data:
        problems.append("noto must be an object")

    font = data.get("font")
    if isinstance(font, dict):
        _check_fields(problems, "font", font, FIELDS["font"])
        for name in ("file", "license"):
            if name not in font:
                continue
            v = font[name]
            if not _is_str(v) or not v or os.path.isabs(v) or not os.path.isfile(os.path.join(HERE, v)):
                problems.append("font.%s: %r is not a file relative to Tools/EmojiForge" % (name, v))
        if "sha256" in font and not _is_str(font["sha256"], SHA256_RE):
            problems.append("font.sha256 must be 64 lower-case hex digits")
        for name in ("fill", "stroke"):
            if name in font and not _is_str(font[name], COLOUR_RE):
                problems.append("font.%s must be a colour RRGGBB in upper-case hex, not %r" % (name, font[name]))
    elif "font" in data:
        problems.append("font must be an object")

    group_keys = set()
    groups = data.get("groups")
    if isinstance(groups, list) and groups:
        for i, g in enumerate(groups):
            where = "groups[%d]" % i
            if not isinstance(g, dict):
                problems.append("%s must be an object" % where)
                continue
            _check_fields(problems, where, g, FIELDS["group"])
            if "key" in g:
                if not _is_str(g["key"], GROUP_RE):
                    problems.append("%s: group key %r must match %s" % (where, g["key"], GROUP_RE.pattern))
                elif g["key"] in group_keys:
                    problems.append("%s: duplicate group key %r" % (where, g["key"]))
                else:
                    group_keys.add(g["key"])
            if "label" in g and not _is_str(g["label"], NAME_RE):
                problems.append("%s: label %r must be 1-24 characters of [A-Za-z0-9 '!?.-]" % (where, g["label"]))
    elif "groups" in data:
        problems.append("groups must be a non-empty list")

    emojis = data.get("emojis")
    if not isinstance(emojis, list) or not emojis:
        if "emojis" in data:
            problems.append("emojis must be a non-empty list")
        return problems
    if len(emojis) > MAX_EMOJIS:
        problems.append("emojis has %d entries; at most %d fit the protocol (EMOJI 0..%d)"
                        % (len(emojis), MAX_EMOJIS, MAX_EMOJIS - 1))
    keys = {}
    names = {}
    for i, e in enumerate(emojis):
        where = "emojis[%d]" % i
        if not isinstance(e, dict):
            problems.append("%s must be an object" % where)
            continue
        if _is_str(e.get("key")):
            where += " (%s)" % e["key"]
        _check_fields(problems, where, e, ENTRY_FIELDS + ENTRY_SOURCES, ENTRY_FIELDS)
        if "id" in e and not (_is_int(e["id"]) and e["id"] == i):
            problems.append("%s: id %s, but the ids must be 0..n-1 in order (expected %d)" % (where, _json(e["id"]), i))
        if "key" in e:
            k = e["key"]
            if not _is_str(k, KEY_RE):
                problems.append("%s: key %r must match %s" % (where, k, KEY_RE.pattern))
            elif k in keys:
                problems.append("%s: duplicate key %r (also emojis[%d])" % (where, k, keys[k]))
            else:
                keys[k] = i
        if "name" in e:
            n = e["name"]
            if not _is_str(n, NAME_RE):
                problems.append("%s: name %r must be 1-24 characters of [A-Za-z0-9 '!?.-]" % (where, n))
            else:
                names.setdefault(norm(n), []).append(i)
        if "group" in e and (not _is_str(e["group"]) or e["group"] not in group_keys):
            problems.append("%s: group %r is not in groups" % (where, e["group"]))
        sources = [s for s in ENTRY_SOURCES if s in e]
        if len(sources) != 1:
            problems.append("%s: needs exactly one of noto and text (has %s)"
                            % (where, ", ".join(sources) or "neither"))
        if "noto" in e and not _is_str(e["noto"], NOTO_RE):
            problems.append("%s: noto %r must be hex codepoints joined by _ (as in emoji_u1f602.png)"
                            % (where, e["noto"]))
        if "text" in e and not _is_str(e["text"], TEXT_RE):
            problems.append("%s: text %r must be 1-5 characters of [A-Z0-9]" % (where, e["text"]))
    for n, ids in names.items():
        if len(ids) > 1:
            problems.append("emojis %s: names %s are the same name to /bh emoji (%r)"
                            % (", ".join(map(str, ids)), ", ".join(repr(emojis[i]["name"]) for i in ids), n))
        other = keys.get(n)
        for i in ids:
            if other is not None and other != i:
                problems.append("emojis[%d]: name %r is the key of emojis[%d] to /bh emoji"
                                % (i, emojis[i]["name"], other))
    return problems


def load_catalogue(path=CATALOGUE):
    """Reads and validates emojis.json; raises CatalogueError with every problem found."""
    duplicates = []

    def pairs(items):
        obj = {}
        for k, v in items:
            if k in obj:
                duplicates.append("field %r appears twice in one object" % k)
            obj[k] = v
        return obj

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f, object_pairs_hook=pairs)
    except (OSError, ValueError) as ex:
        raise CatalogueError(["%s: %s" % (path, ex)])
    problems = duplicates + validate_catalogue(data)
    if problems:
        raise CatalogueError(problems)
    return data


def font_path(cat):
    return os.path.join(HERE, cat["font"]["file"])


def font_sha256(cat):
    with open(font_path(cat), "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def noto_file(cat, entry):
    return cat["noto"]["path"].format(codepoints=entry["noto"])


def noto_patterns(cat):
    """Sparse-checkout patterns of the noto-emoji files the art and the licences come from."""
    return ["/LICENSE", "/README.md"] + ["/" + noto_file(cat, e) for e in cat["emojis"] if "noto" in e]


# ------------------------------------------------------------------------------------------ generated files

def _lua_str(s):
    return '"%s"' % s.replace("\\", "\\\\").replace('"', '\\"')


def render_lua(cat):
    out = [
        "-- Bleakhold: the emoji catalogue. Generated by Tools/EmojiForge/emojiforge.py from "
        "Tools/EmojiForge/emojis.json;",
        "-- do not edit. EMOJI <id> shows the emoji above the player's head (docs/BleakholdProtocol.md, section 13).",
        "local ADDON, ns = ...",
        "local Data = ns.Data",
        "",
        "Data.emojiGroups = {",
    ]
    for g in cat["groups"]:
        out.append("    { key = %s, label = %s }," % (_lua_str(g["key"]), _lua_str(g["label"])))
    out += ["}", "", "Data.emojis = {"]
    for e in cat["emojis"]:
        out.append("    { id = %d, key = %s, name = %s, group = %s, texture = %s }," % (
            e["id"], _lua_str(e["key"]), _lua_str(e["name"]), _lua_str(e["group"]),
            _lua_str(cat["texture"] % e["id"])))
    out.append("}")
    return "\n".join(out) + "\n"


def render_server_header(cat):
    keys = [e["key"] for e in cat["emojis"]]
    lines, line = [], ""
    for i, k in enumerate(keys):
        token = '"%s"%s' % (k, "," if i < len(keys) - 1 else "")
        if line and len("        " + line + " " + token) > 100:
            lines.append("        " + line)
            line = token
        else:
            line = token if not line else line + " " + token
    lines.append("        " + line)
    out = [
        "/*",
        " * mod-bleakhold-ui: server side of the Bleakhold UI protocol (docs/BleakholdProtocol.md).",
        " * SPDX-License-Identifier: GPL-2.0-or-later",
        " *",
        " * The emoji catalogue (EMOJI, section 13). Generated by Tools/EmojiForge/emojiforge.py from",
        " * Tools/EmojiForge/emojis.json; do not edit. No AzerothCore dependency.",
        " */",
        "",
        "#ifndef BLEAKHOLD_EMOJI_H",
        "#define BLEAKHOLD_EMOJI_H",
        "",
        "#include <cstdint>",
        "",
        "namespace Bleakhold",
        "{",
        "    // EMOJI ids 0 .. EmojiCatalogueCount - 1 exist; the client has art for each of them.",
        "    inline constexpr uint32_t EmojiCatalogueCount = %d;" % len(keys),
        "    static_assert(EmojiCatalogueCount >= 1 && EmojiCatalogueCount <= %d," % MAX_EMOJIS,
        '        "the emoji catalogue (Tools/EmojiForge/emojis.json) must hold 1..%d entries (Proto::MaxEmojis)");'
        % MAX_EMOJIS,
        "",
        "    // Key of each id (for logs), the same as the addon's Data.emojis.",
        "    inline constexpr char const* EmojiCatalogueKeys[EmojiCatalogueCount] = {",
    ] + lines + [
        "    };",
        "}",
        "",
        "#endif",
    ]
    return "\n".join(out) + "\n"


def _id_ranges(ids):
    """Emoji073-Emoji082, Emoji090 for [73, ..., 82, 90]."""
    parts, start = [], None
    for i, n in enumerate(ids):
        if start is None:
            start = n
        if i + 1 == len(ids) or ids[i + 1] != n + 1:
            parts.append("Emoji%03d" % start if start == n else "Emoji%03d-Emoji%03d" % (start, n))
            start = None
    return ", ".join(parts)


def render_notice(cat):
    size, pad = ART["size"], ART["pad"]
    noto = cat["noto"]
    text_ids = [e["id"] for e in cat["emojis"] if "text" in e]
    about = (
        "Emoji images from Noto Emoji 3D (%s, commit %s, folder %s), Copyright 2013 Google LLC. The project's LICENSE "
        "is the SIL Open Font License 1.1 (%s) and its README states that image resources are under the Apache "
        "License 2.0 (%s); both texts are included. Modified: each image was scaled to %dx%d on a %dx%d transparent "
        "canvas and converted to BLP (DXT5 with mipmaps) by Tools/EmojiForge/emojiforge.py."
        % (noto["repo"], noto["commit"], os.path.dirname(noto["path"]), LICENSES[0], LICENSES[1],
           size - 2 * pad, size - 2 * pad, size, size))
    if text_ids:
        about += (
            " Text emotes (%s) drawn by Tools/EmojiForge with the Bangers font, Copyright 2010 The Bangers Project "
            "Authors (https://github.com/googlefonts/bangers), SIL Open Font License 1.1 (%s)."
            % (_id_ranges(text_ids), LICENSES[2]))
    out = textwrap.wrap(about, 116, break_long_words=False, break_on_hyphens=False)
    out += [
        "",
        "Generated by Tools/EmojiForge/emojiforge.py from Tools/EmojiForge/emojis.json; do not edit.",
        "",
        "| File | Key | Name | Source |",
        "|---|---|---|---|",
    ]
    for e in cat["emojis"]:
        source = ("Noto %s" % os.path.basename(noto_file(cat, e))) if "noto" in e else 'text "%s", Bangers' % e["text"]
        out.append("| Emoji%03d.blp | %s | %s | %s |" % (e["id"], e["key"], e["name"], source))
    return "\n".join(out) + "\n"


# Repository path (with /) -> renderer.
GENERATED = {
    "Interface/AddOns/Bleakhold/EmojiData.lua": render_lua,
    "Server/mod-bleakhold-ui/src/BleakholdEmoji.h": render_server_header,
    "Interface/Bleakhold/Emoji/NOTICE.md": render_notice,
}


def repo_path(rel):
    return os.path.join(REPO, *rel.split("/"))


def generate(cat, check=False):
    """Writes the generated files that differ from the catalogue (only compares with check); returns those paths.

    A checkout with CRLF line endings (Windows, * text=auto) is not stale; the files are written with LF."""
    stale = []
    for rel, render in GENERATED.items():
        text = render(cat)
        path = repo_path(rel)
        try:
            with open(path, "r", encoding="utf-8", newline="") as f:
                current = f.read().replace("\r\n", "\n")
        except FileNotFoundError:
            current = None
        if current == text:
            continue
        stale.append(rel)
        if not check:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
    return stale


# ---------------------------------------------------------------------------------------------------- art

def blp_name(emoji_id):
    return "Emoji%03d.blp" % emoji_id


def check_art(cat, directory=EMOJI_DIR):
    """Problems of the shipped art: one BLP per id with the header the client expects, no others, the licences."""
    problems = []
    rel = os.path.relpath(directory, REPO).replace(os.sep, "/")
    count = len(cat["emojis"])
    for e in cat["emojis"]:
        path = os.path.join(directory, blp_name(e["id"]))
        where = "%s/%s (%s)" % (rel, blp_name(e["id"]), e["key"])
        if not os.path.isfile(path):
            problems.append("%s is missing (run emojiforge.py art)" % where)
            continue
        try:
            h, levels, issues = bc.check_blp(path)
        except (OSError, ValueError) as ex:
            problems.append("%s: %s" % (where, ex))
            continue
        problems += ["%s: %s" % (where, s) for s in issues]
        got = (h["encoding"], h["alphaSize"], h["preferredFormat"], h["width"], h["height"], levels)
        want = (2, 8, bc.PIXEL_DXT5, ART["size"], ART["size"], ART_LEVELS)
        if got != want:
            problems.append("%s: encoding %d, alphaSize %d, preferredFormat %d, %dx%d, %d level(s); wants DXT5 "
                            "(2, 8, 7) %dx%d with %d levels" % ((where,) + got + want[3:]))
    for name in sorted(os.listdir(directory)) if os.path.isdir(directory) else []:
        m = re.match(r"^emoji(\d+)\.blp$", name, re.I)
        if m and (int(m.group(1)) >= count or name != blp_name(int(m.group(1)))):
            problems.append("%s/%s is not in the catalogue (%d emojis)" % (rel, name, count))
    for name in LICENSES:
        if not os.path.isfile(os.path.join(directory, name)):
            problems.append("%s/%s is missing" % (rel, name))
    return problems


def _pil():
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        raise ImportError("emojiforge.py art needs Pillow: pip install Pillow")
    return Image, ImageDraw, ImageFont


def _rgba(hexstr):
    return (int(hexstr[0:2], 16), int(hexstr[2:4], 16), int(hexstr[4:6], 16), 255)


def prepare_noto(png_path):
    """A 512x512 Noto image scaled to 240x240 in the middle of a transparent 256x256 canvas (PIL RGBA)."""
    Image = _pil()[0]
    size, pad = ART["size"], ART["pad"]
    with Image.open(png_path) as im:
        img = im.convert("RGBA") if im.mode != "RGBA" else im.copy()
    if img.size != (NOTO_SIZE, NOTO_SIZE):
        raise ValueError("%s is %dx%d; the Noto 3D images are %dx%d"
                         % ((png_path,) + img.size + (NOTO_SIZE, NOTO_SIZE)))
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.alpha_composite(img.resize((size - 2 * pad, size - 2 * pad), Image.LANCZOS), (pad, pad))
    return canvas


def draw_text(text, font_file, fill, stroke):
    """A text emote: the largest size that fits, centred, fill and stroke colours RRGGBB (PIL RGBA 256x256)."""
    Image, ImageDraw, ImageFont = _pil()
    big = 2 * ART["size"]
    measure = ImageDraw.Draw(Image.new("RGBA", (big, big)))
    size = 400
    while True:
        font = ImageFont.truetype(font_file, size)
        width = size // 12
        left, top, right, bottom = measure.textbbox((0, 0), text, font=font, stroke_width=width)
        if right - left <= TEXT_BOX and bottom - top <= TEXT_BOX:
            break
        if size <= 8:
            raise ValueError("%r does not fit in %dx%d" % (text, TEXT_BOX, TEXT_BOX))
        size -= 8
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    ImageDraw.Draw(img).text(((big - (right - left)) / 2 - left, (big - (bottom - top)) / 2 - top), text, font=font,
                             fill=_rgba(fill), stroke_width=width, stroke_fill=_rgba(stroke))
    return img.resize((ART["size"], ART["size"]), Image.LANCZOS)


def render_entry(cat, entry, noto_dir):
    if "noto" in entry:
        return prepare_noto(os.path.join(noto_dir, *noto_file(cat, entry).split("/")))
    return draw_text(entry["text"], font_path(cat), cat["font"]["fill"], cat["font"]["stroke"])


def write_blp(img, path, jobs=None):
    """Encodes a 256x256 RGBA picture as the client's emoji BLP; returns the problems check_blp finds."""
    bc.convert(bc.Image(img.size[0], img.size[1], bytearray(img.tobytes())), path, ART["format"], True, jobs)
    return bc.check_blp(path)[2]


def contact_sheet(images, cell=128, gap=8, columns=10):
    """PIL RGB sheet of the pictures on #303030, `columns` per row."""
    Image = _pil()[0]
    rows = (len(images) + columns - 1) // columns
    sheet = Image.new("RGBA", (gap + columns * (cell + gap), gap + rows * (cell + gap)), (0x30, 0x30, 0x30, 255))
    for i, img in enumerate(images):
        sheet.alpha_composite(img.resize((cell, cell), Image.LANCZOS),
                              (gap + (i % columns) * (cell + gap), gap + (i // columns) * (cell + gap)))
    return sheet.convert("RGB")


def build_art(cat, noto_dir=None, only=None, preview=None, jobs=None, allow_other_commit=False, out_dir=EMOJI_DIR):
    entries = cat["emojis"]
    if only:
        by_key = {e["key"]: e for e in entries}
        unknown = [k for k in only if k not in by_key]
        if unknown:
            raise SystemExit("--only: not in emojis.json: %s" % ", ".join(unknown))
        entries = [by_key[k] for k in only]
    if any("noto" in e for e in entries):
        if not noto_dir:
            raise SystemExit("--noto DIR is needed: a checkout of %s (see README.md)" % NOTO_REPO)
        if not allow_other_commit:
            try:
                head = subprocess.run(["git", "-C", noto_dir, "rev-parse", "HEAD"], capture_output=True, text=True,
                                      check=True).stdout.strip()
            except (OSError, subprocess.CalledProcessError):
                head = None
            if head != cat["noto"]["commit"]:
                raise SystemExit("%s is at %s, not at the pinned commit %s (emojis.json noto.commit); check it out, "
                                 "or pass --allow-other-commit"
                                 % (noto_dir, head or "no git commit", cat["noto"]["commit"]))
    if any("text" in e for e in entries) and font_sha256(cat) != cat["font"]["sha256"]:
        raise SystemExit("%s does not match font.sha256 in emojis.json" % cat["font"]["file"])
    os.makedirs(out_dir, exist_ok=True)
    if preview:
        os.makedirs(preview, exist_ok=True)
    pictures, failed = [], False
    for e in entries:
        img = render_entry(cat, e, noto_dir)
        path = os.path.join(out_dir, blp_name(e["id"]))
        problems = write_blp(img, path, jobs)
        for p in problems:
            print("%s: %s" % (blp_name(e["id"]), p))
        failed = failed or bool(problems)
        print("wrote %s (%s)" % (os.path.relpath(path, REPO).replace(os.sep, "/"), e["key"]))
        if preview:
            img.save(os.path.join(preview, "%03d_%s.png" % (e["id"], e["key"])))
            pictures.append(img)
    if preview and pictures:
        contact_sheet(pictures).save(os.path.join(preview, "sheet.png"))
        print("previews in %s" % preview)
    return 1 if failed else 0


# --------------------------------------------------------------------------------------------------- main

def _load_or_exit():
    try:
        return load_catalogue(CATALOGUE)
    except CatalogueError as ex:
        for p in ex.problems:
            print("emojis.json: %s" % p)
        raise SystemExit(1)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="emojiforge.py", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="command", required=True)
    g = sub.add_parser("generate", help="write EmojiData.lua, BleakholdEmoji.h and NOTICE.md from emojis.json")
    g.add_argument("--check", action="store_true", help="only compare; exit 1 when a file is stale")
    a = sub.add_parser("art", help="draw Interface/Bleakhold/Emoji/EmojiNNN.blp (needs Pillow)")
    a.add_argument("--noto", metavar="DIR", help="noto-emoji checkout at the pinned commit")
    a.add_argument("--only", metavar="KEY,KEY", help="only these emojis")
    a.add_argument("--preview", metavar="DIR", help="also write NNN_key.png and sheet.png here")
    a.add_argument("--jobs", type=int, help="encoder processes (default: all cores)")
    a.add_argument("--allow-other-commit", action="store_true", help="accept a noto-emoji checkout at another commit")
    sub.add_parser("check", help="validate the catalogue, the generated files and the art")
    sub.add_parser("patterns", help="print the noto-emoji sparse-checkout patterns")
    args = ap.parse_args(argv)
    cat = _load_or_exit()

    if args.command == "generate":
        stale = generate(cat, check=args.check)
        for rel in stale:
            if args.check:
                print("stale: %s (run python3 -I Tools/EmojiForge/emojiforge.py generate)" % rel)
            else:
                print("wrote %s" % rel)
        if not stale:
            print("generated files are up to date (%d emojis)" % len(cat["emojis"]))
        return 1 if args.check and stale else 0
    if args.command == "art":
        only = [k.strip() for k in args.only.split(",") if k.strip()] if args.only else None
        try:
            return build_art(cat, args.noto, only, args.preview, args.jobs, args.allow_other_commit)
        except ImportError as ex:
            raise SystemExit(str(ex))
    if args.command == "check":
        problems = ["stale: %s (run emojiforge.py generate)" % rel for rel in generate(cat, check=True)]
        if font_sha256(cat) != cat["font"]["sha256"]:
            problems.append("%s does not match font.sha256" % cat["font"]["file"])
        problems += check_art(cat)
        for p in problems:
            print(p)
        if not problems:
            print("catalogue, generated files and art are clean (%d emojis)" % len(cat["emojis"]))
        return 1 if problems else 0
    if args.command == "patterns":
        print("\n".join(noto_patterns(cat)))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
