"""dances.json: the dance catalogue, and everything generated from it."""

import importlib
import json
import os
import re
import sys

from . import pack as P

FIELDS = ("format", "kitBase", "maxDances", "fps", "pack", "musicFolder", "categories", "dances")
DANCE_FIELDS = ("id", "key", "name", "command", "category", "source")
KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 '!.\-]{0,23}$")
COMMAND_RE = re.compile(r"^[a-z][a-z0-9]{2,23}$")
SOURCE_RE = re.compile(r"^[a-z_][a-z0-9_]*:[a-z_][a-z0-9_]*$")

# Fixed by the client (WoW/Common/BleakholdDance.h, Engine/Source/Model2/M2Dance.cpp) and the server module.
KIT_BASE = 910000
MAX_DANCES = 1024
PACK_PATH = "Interface\\Bleakhold\\Dances\\Dances.bdc"
MUSIC_FOLDER = "Interface\\Bleakhold\\Dances\\Music\\"

# Slash commands a dance may not take: the stock text emotes and chat commands of 3.3.5a, and Bleakhold's own.
RESERVED_COMMANDS = set("""
agree amaze angry apologize applaud attacktarget bashful beckon beg belch bite bleed blink blow blush boggle bonk
bored bounce bow brb bravo burp bye cackle calm charge cheer chicken chuckle clap cold comfort commend confused
congratulate cough cower crack cringe cry cuddle curious curtsey dance ding disagree doubt drink drool duck eat
embarrass encourage enemy eye facepalm faint fart fidget flee flex flirt flop follow frown gasp gaze giggle glad
glare gloat golfclap goodbye greet grin groan grovel growl guffaw hail happy healme hello helpme hiccup highfive
hiss holdhand hug hungry hurry idea incoming insult introduce jk joke kiss kneel laugh lavish lay lick listen lost
love mad massage moan mock moo moon mourn no nod nosepick oom openfire panic pat peer pest pick pity pizza plead
point poke ponder pounce pray purr puzzle raise rasp ready regret rofl roar rude sad salute scared scratch sexy
shake shimmy shiver shoo shout shrug shy sigh silly slap sleep smell smile smirk snarl snicker sniff snub soothe
sorry spit stare stink surprised surrender suspicious sweat talk tap taunt tease thank think thirsty threaten
tickle tired train truce twiddle veto victory violin volunteer wait wave welcome whine whistle wink work yawn yw
bh bleakhold say yell whisper party raid guild officer emote reply script run reload console logout quit camp
macro help who join leave chat stopattack cast use target focus assist invite kick dnd afk roll random played
""".split())


class CatalogueError(Exception):
    pass


def load(path):
    with open(path, "r", encoding="utf-8") as f:
        cat = json.load(f)
    validate(cat)
    return cat


def validate(cat):
    errors = []
    for k in FIELDS:
        if k not in cat:
            errors.append("missing field %r" % k)
    if errors:
        raise CatalogueError("; ".join(errors))
    if cat["format"] != 1:
        errors.append("format must be 1")
    if cat["kitBase"] != KIT_BASE or cat["maxDances"] != MAX_DANCES:
        errors.append("kitBase and maxDances are fixed by the client (%d, %d)" % (KIT_BASE, MAX_DANCES))
    if cat["pack"] != PACK_PATH or cat["musicFolder"] != MUSIC_FOLDER:
        errors.append("pack and musicFolder are fixed by the client")
    if not isinstance(cat["fps"], int) or not 10 <= cat["fps"] <= 60:
        errors.append("fps must be 10..60")
    cats = set()
    for c in cat["categories"]:
        if not KEY_RE.match(c.get("key", "")) or not c.get("label"):
            errors.append("bad category %r" % c)
        cats.add(c.get("key"))
    keys, names, commands = set(), set(), set()
    if not 1 <= len(cat["dances"]) <= MAX_DANCES:
        errors.append("1..%d dances" % MAX_DANCES)
    for i, d in enumerate(cat["dances"]):
        where = "dance %d" % i
        missing = [k for k in DANCE_FIELDS if k not in d]
        extra = [k for k in d if k not in DANCE_FIELDS]
        if missing or extra:
            errors.append("%s: fields %s" % (where, missing or extra))
            continue
        if d["id"] != i:
            errors.append("%s: ids must be 0, 1, 2, ... in order (append new dances at the end)" % where)
        if not KEY_RE.match(d["key"]) or d["key"] in keys:
            errors.append("%s: bad or repeated key %r" % (where, d["key"]))
        keys.add(d["key"])
        if not NAME_RE.match(d["name"]) or d["name"].lower() in names:
            errors.append("%s: bad or repeated name %r" % (where, d["name"]))
        names.add(d["name"].lower())
        if not COMMAND_RE.match(d["command"]) or d["command"] in commands or d["command"] in RESERVED_COMMANDS:
            errors.append("%s: bad, repeated or reserved command %r" % (where, d["command"]))
        commands.add(d["command"])
        if d["category"] not in cats:
            errors.append("%s: unknown category %r" % (where, d["category"]))
        if not SOURCE_RE.match(d["source"]):
            errors.append("%s: source must be module:function" % where)
    if errors:
        raise CatalogueError("; ".join(errors))


def build(cat, dances_dir, only=None):
    """{key: Dance} for the catalogue's dances (only: a set of keys)."""
    if dances_dir not in sys.path:
        sys.path.insert(0, dances_dir)
    out = {}
    for d in cat["dances"]:
        if only and d["key"] not in only:
            continue
        module, func = d["source"].split(":")
        mod = importlib.import_module(module)
        fn = getattr(mod, "DANCES", {}).get(func)
        if fn is None:
            raise CatalogueError("dance %s: %s has no dance %r in DANCES" % (d["key"], module, func))
        out[d["key"]] = fn()
    return out


def clip_frames(dance, fps):
    return max(2, int(round(dance.seconds * fps)))


def loop_ms(dance, fps):
    """The loop length as the client computes it (BleakDance::ClipLengthMs: frames * 1000 / fps, integer)."""
    return clip_frames(dance, fps) * 1000 // fps


def write_pack(cat, built):
    clips = []
    for d in cat["dances"]:
        dance = built[d["key"]]
        frames = dance.sample(cat["fps"])
        clips.append((d["id"], d["key"], cat["fps"], dance.bpm, frames, True))
    return P.write(clips)


def _lua_string(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render_lua(cat, built):
    fps = cat["fps"]
    lines = [
        "-- Bleakhold: the dance catalogue. Generated by Tools/DanceForge/danceforge.py from Tools/DanceForge/dances.json;",
        "-- do not edit. DANCE <id> starts the dance (docs/BleakholdProtocol.md, section 14); the Bleakhold client plays",
        "-- it from Interface\\Bleakhold\\Dances\\Dances.bdc, with the music Interface\\Bleakhold\\Dances\\Music\\<key>.mp3 if",
        "-- there is one.",
        "local ADDON, ns = ...",
        "local Data = ns.Data",
        "",
        "Data.danceCategories = {",
    ]
    for c in cat["categories"]:
        lines.append("    { key = %s, label = %s }," % (_lua_string(c["key"]), _lua_string(c["label"])))
    lines += ["}", "", "Data.dances = {"]
    for d in cat["dances"]:
        dance = built[d["key"]]
        lines.append("    { id = %d, key = %s, name = %s, cmd = %s, cat = %s, bpm = %s, seconds = %.2f }," % (
            d["id"], _lua_string(d["key"]), _lua_string(d["name"]), _lua_string("/" + d["command"]),
            _lua_string(d["category"]), ("%g" % dance.bpm), loop_ms(dance, fps) / 1000.0))
    lines += ["}", ""]
    return "\n".join(lines)


def render_header(cat, built):
    fps = cat["fps"]
    n = len(cat["dances"])
    keys = ", ".join('"%s"' % d["key"] for d in cat["dances"])
    loops = ", ".join(str(loop_ms(built[d["key"]], fps)) for d in cat["dances"])
    wrapped_keys = _wrap(keys, 8)
    wrapped_loops = _wrap(loops, 8)
    return "\n".join([
        "/*",
        " * mod-bleakhold-ui: server side of the Bleakhold UI protocol (docs/BleakholdProtocol.md).",
        " * SPDX-License-Identifier: GPL-2.0-or-later",
        " *",
        " * The dance catalogue (DANCE, section 14). Generated by Tools/DanceForge/danceforge.py from",
        " * Tools/DanceForge/dances.json; do not edit. No AzerothCore dependency.",
        " */",
        "",
        "#ifndef BLEAKHOLD_DANCE_H",
        "#define BLEAKHOLD_DANCE_H",
        "",
        "#include <cstdint>",
        "",
        "namespace Bleakhold",
        "{",
        "    // DANCE ids 0 .. DanceCatalogueCount - 1 exist; the client has a clip for each of them.",
        "    inline constexpr uint32_t DanceCatalogueCount = %d;" % n,
        "    static_assert(DanceCatalogueCount >= 1 && DanceCatalogueCount <= 1024,",
        "        \"the dance catalogue (Tools/DanceForge/dances.json) must hold 1..1024 entries (Proto::MaxDances)\");",
        "",
        "    // Length of one loop of each dance in ms (the kit is sent again at the start of every loop).",
        "    inline constexpr uint32_t DanceLoopMs[DanceCatalogueCount] = {",
    ] + wrapped_loops + [
        "    };",
        "",
        "    // Key of each id (for logs), the same as the addon's Data.dances.",
        "    inline constexpr char const* DanceCatalogueKeys[DanceCatalogueCount] = {",
    ] + wrapped_keys + [
        "    };",
        "}",
        "",
        "#endif",
        "",
    ])


def _wrap(items, per_line):
    parts = [p.strip() for p in items.split(",")]
    out = []
    for i in range(0, len(parts), per_line):
        out.append("        " + ", ".join(parts[i:i + per_line]) + ",")
    if out:
        out[-1] = out[-1].rstrip(",")
    return out


def render_music_readme(cat, built):
    fps = cat["fps"]
    lines = [
        "Bleakhold dances: music",
        "=======================",
        "",
        "Every dance can have its own music. Put a file named after the dance's key in this folder:",
        "",
        "    Data\\Interface\\Bleakhold\\Dances\\Music\\<key>.mp3      (or <key>.ogg, or <key>.wav)",
        "",
        "or pack it into an MPQ under the same path and give that MPQ to your players. The music starts with",
        "the dance, loops while the character dances and stops when they stop; everybody nearby who has the",
        "same file hears it from the dancer (Sound Effects volume; /console bleakDanceMusic 0 turns it off,",
        "bleakDanceMusicVolume 0..1 sets its volume). A dance without a file dances in silence.",
        "",
        "Pick music at the dance's tempo so the moves land on the beat; trim the file to a whole number of",
        "dance loops (or any length: it simply repeats). Only use music you have the rights to.",
        "",
        "Generated by Tools/DanceForge/danceforge.py from Tools/DanceForge/dances.json.",
        "",
        "%-4s %-22s %-24s %6s %8s" % ("id", "key (file name)", "dance", "BPM", "loop (s)"),
    ]
    for d in cat["dances"]:
        dance = built[d["key"]]
        lines.append("%-4d %-22s %-24s %6g %8.2f" % (d["id"], d["key"], d["name"], dance.bpm,
                                                    loop_ms(dance, fps) / 1000.0))
    lines.append("")
    return "\r\n".join(lines)


def outputs(repo, cat, built):
    """{path: text} of every generated file."""
    return {
        os.path.join(repo, "Interface", "AddOns", "Bleakhold", "DanceData.lua"): render_lua(cat, built),
        os.path.join(repo, "Server", "mod-bleakhold-ui", "src", "BleakholdDance.h"): render_header(cat, built),
        os.path.join(repo, "Interface", "Bleakhold", "Dances", "Music", "README.txt"): render_music_readme(cat, built),
    }
