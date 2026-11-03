"""The files CafeForge's data step generates from cafe.json (all committed; generate(check=True) finds stale ones):

  Server/mod-bleakhold-ui/src/BleakholdCafeData.h      core-free C++ catalogue (namespace Bleakhold::CafeData)
  Interface/AddOns/Bleakhold/CafeData.lua               the addon's ns.CafeData (fallbacks until DEF arrives)
  Server/mod-bleakhold-ui/data/sql/db-world/04_bleakhold_cafe_templates.sql
                                                        gameobject, creature and item templates, the staff's
                                                        creature_template_addon, spell_custom_attr and npc_text

Every renderer is a pure function of the parsed catalogue: the same cafe.json gives the same bytes on every
machine (LF line endings, UTF-8, fixed number formats).
"""

import math
import os

from . import REPO
from . import catalog as C

HEADER_PATH = "Server/mod-bleakhold-ui/src/BleakholdCafeData.h"
LUA_PATH = "Interface/AddOns/Bleakhold/CafeData.lua"
SQL_PATH = "Server/mod-bleakhold-ui/data/sql/db-world/04_bleakhold_cafe_templates.sql"
SOURCE = "Tools/CafeForge/cafeforge_data.py from Tools/CafeForge/cafe.json"

MAX_DISPLAYS = 12
MAX_FAV = 3
NEVER_SAVED = (100900, 100936, 100937)          # On Shift, the speed helper, Tired
SPELL_ATTR0_CU_AURA_CANNOT_BE_SAVED = 0x01000000  # SpellInfo.h
GO_FLAG_NODESPAWN = 0x20
UNIT_FLAGS = 0x2 | 0x100 | 0x200                 # NON_ATTACKABLE, IMMUNE_TO_PC, IMMUNE_TO_NPC
FLAGS_EXTRA_CIVILIAN = 0x2
CREATURE_TYPE_HUMANOID = 7
CUSTOMER_FACTION = 35


# --------------------------------------------------------------------------------------------- derived data

def drink_cup(cafe, recipe):
    """The stock item a seated customer holds (section 3.7.4): tier 5 drinks a gold tankard, the Starleaf and the
    Sunleaf a wine glass, else the café's cup of the family."""
    cups = cafe["cups"]
    if recipe["tier"] == 5:
        return cups["T5"]
    if recipe["arch"] == "T6":
        return cups["starleaf"]
    return cups[recipe["family"]]


def recipes_of(doc):
    """(café, recipe, id, name, text) for both cafés, in id order."""
    out = []
    for cafe in doc["cafes"]:
        for r in doc["recipes"]:
            name, text = r["names"][str(cafe["id"])]
            out.append((cafe, r, C.recipe_id(cafe["id"], r["n"]), name, text))
    return out


def marker_go(row):
    """The .cafe show marker template of a layout row's role group."""
    role = row["role"]
    if C.station_of(row):
        return 909368
    if role in ("order_spot", "pickup_spot") or role.startswith("queue_"):
        return 909369
    if role == "door" or role.startswith("path_") or role.startswith("chair_"):
        return 909378
    return 909379


def layout_rows(doc):
    """Every café's layout rows (café 1 first), each with its footprint halves resolved."""
    gos = C.by_key(doc["gameobjects"], "entry")
    out = []
    for cafe in (1, 2):
        for r in C.cafe_layout(doc, cafe):
            fp = None if r.get("creature") else C.go_footprint(gos.get(r["entry"]))
            go = gos.get(r["entry"], {}) if not r.get("creature") else {}
            out.append((r, fp, go))
    return out


# ------------------------------------------------------------------------------------------------ formatting

def cpp_str(s):
    """A C++ string literal: ASCII as is, every other byte as a 3-digit octal escape (never ambiguous)."""
    out = []
    for b in s.encode("utf-8"):
        ch = chr(b)
        if ch in "\\\"":
            out.append("\\" + ch)
        elif 32 <= b < 127:
            out.append(ch)
        else:
            out.append("\\%03o" % b)
    return '"%s"' % "".join(out)


def decl(code, comment="", col=60):
    """An "inline constexpr" line with its comment aligned."""
    line = "    inline constexpr " + code
    return (line.ljust(col) + "// " + comment) if comment else line


def cpp_char(c):
    return "'%s'" % c if c else "'\\0'"


def fnum(v):
    """A float with the shortest repr that reads back exactly ("0.8", "-24.0")."""
    v = float(v)
    if v == 0:
        return "0.0"
    r = repr(v)
    return r if ("." in r or "e" in r) else r + ".0"


def cpp_float(v):
    return fnum(v) + "f"


def rad(deg):
    """Degrees to radians, rounded to 7 decimals so the text is short and stable."""
    r = round(math.radians(deg), 7)
    return 0.0 if r == 0 else r


def cpp_bool(b):
    return "true" if b else "false"


def cpp_array(values, size, fmt=str):
    vals = [fmt(v) for v in values] + ["0"] * (size - len(values))
    return "{ { %s } }" % ", ".join(vals)


def lua_str(s):
    return '"%s"' % s.replace("\\", "\\\\").replace('"', '\\"')


def lua_num(v):
    if isinstance(v, int) and not isinstance(v, bool):
        return str(v)
    f = float(v)
    return str(int(f)) if f.is_integer() else repr(f)


def sql_str(s):
    if s is None:
        return "NULL"
    return "'%s'" % s.replace("\\", "\\\\").replace("'", "''")


def sql_val(v):
    if v is None:
        return "NULL"
    if isinstance(v, str):
        return sql_str(v)
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, float):
        return lua_num(v)
    return str(v)


def split_long(line, width=120, more=4):
    """A generated line longer than width, broken after ", " outside string literals (continuations indented by
    more); a single piece that is still too long stays as it is."""
    if len(line) <= width or line.lstrip().startswith(("//", "--")):
        return [line]
    cuts, quote, i = [], None, 0
    while i < len(line):
        ch = line[i]
        if quote:
            if ch == "\\":
                i += 1
            elif ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif line.startswith(", ", i):
            cuts.append(i + 1)
        i += 1
    indent = " " * (len(line) - len(line.lstrip()) + more)
    out, start, prefix = [], 0, ""
    while len(prefix) + len(line) - start > width:
        fits = [c for c in cuts if c > start and len(prefix) + c - start <= width]
        later = [c for c in cuts if c > start]
        cut = fits[-1] if fits else (later[0] if later else None)
        if cut is None:
            break
        out.append(prefix + line[start:cut])
        start, prefix = cut + 1, indent
    out.append(prefix + line[start:])
    return out


def wrap_all(lines, width=120):
    out = []
    for line in lines:
        out.extend(split_long(line, width))
    return out


def wrap(prefix, items, sep=", ", width=116, indent="    "):
    """prefix + items joined with sep, wrapped at width (continuation lines indented)."""
    lines, cur = [], prefix
    for i, it in enumerate(items):
        tok = it + (sep if i < len(items) - 1 else "")
        if len(cur) + len(tok.rstrip()) > width and cur.strip():
            lines.append(cur.rstrip())
            cur = indent
        cur += tok
    lines.append(cur.rstrip())
    return lines


# ---------------------------------------------------------------------------------------------- C++ header

def render_header(doc):
    cafes = doc["cafes"]
    o = []
    w = o.append
    w("/*")
    w(" * mod-bleakhold-ui: server side of the Bleakhold UI protocol (docs/BleakholdProtocol.md).")
    w(" * SPDX-License-Identifier: GPL-2.0-or-later")
    w(" *")
    w(" * The cafe catalogue (section 21): the cafes, stations, actions, recipes, barista levels, staff, customer")
    w(" * personas, lines, templates and the default layout. Generated by Tools/CafeForge/cafeforge_data.py from")
    w(" * Tools/CafeForge/cafe.json; do not edit. No AzerothCore dependency.")
    w(" */")
    w("")
    w("#ifndef BLEAKHOLD_CAFE_DATA_H")
    w("#define BLEAKHOLD_CAFE_DATA_H")
    w("")
    w("#include <array>")
    w("#include <cstddef>")
    w("#include <cstdint>")
    w("#include <string_view>")
    w("")
    w("namespace Bleakhold::CafeData")
    w("{")
    ids = doc["ids"]
    w("    // Id blocks (cafe.json ids). Every cafe id lies inside them; the uninstall removes the whole blocks.")
    for name, key in (("Spell", "spells"), ("Display", "displays"), ("Icon", "icons"), ("GameObject", "gameobjects"),
                      ("Creature", "creatures"), ("Item", "items"), ("NpcText", "npcText")):
        w("    inline constexpr uint32_t %sFirst = %d;" % (name, ids[key][0]))
        w("    inline constexpr uint32_t %sLast = %d;" % (name, ids[key][1]))
    sid = doc["spellIds"]
    w("")
    w(decl("uint32_t SpellOnShift = %d;" % sid["shift"], "the shift marker"))
    w(decl("uint32_t SpellStepBase = %d;" % sid["stepBase"], "the step spell of action a is SpellStepBase + a"))
    w(decl("uint32_t SpellSprint = %d;" % sid["sprint"], "the hidden speed helper of the milkshake buff"))
    w(decl("uint32_t SpellTired = %d;" % sid["tired"]))
    w(decl("uint32_t SpellBestBarista = %d;" % sid["crown"]))
    w("    // SPELL_ATTR0_CU_AURA_CANNOT_BE_SAVED rows of 04_bleakhold_cafe_templates.sql (spell_custom_attr).")
    w("    inline constexpr std::array<uint32_t, %d> NeverSavedSpells = %s;"
      % (len(NEVER_SAVED), cpp_array(NEVER_SAVED, len(NEVER_SAVED))))
    titles = doc["dbc"]["titles"]
    w(decl("uint32_t TitleBarista = %d;" % titles[0]["id"], "CharTitles \"%s\", mask bit %d"
           % (titles[0]["name"], titles[0]["mask"])))
    w(decl("uint32_t TitleLegend = %d;" % titles[1]["id"], "\"%s\", mask bit %d"
           % (titles[1]["name"].replace("é", "e"), titles[1]["mask"])))
    w(decl("uint32_t StandInOffset = %d;" % C.STAND_IN_OFFSET, "the stand-in template is the new-art entry + %d"
           % C.STAND_IN_OFFSET))
    w(decl("uint32_t DisplayOffset = %d;" % C.DISPLAY_OFFSET, "a new-art display id is its entry - %d"
           % C.DISPLAY_OFFSET))
    markers = {g["marker"]: g["entry"] for g in doc["gameobjects"] if "marker" in g}
    w("    // .cafe show: one marker template per role group.")
    w(decl("uint32_t MarkerStationSpot = %d;" % markers["station spot"]))
    w(decl("uint32_t MarkerQueue = %d;" % markers["queue, order and pickup"],
           "queue slots, the order and the pickup spot"))
    w(decl("uint32_t MarkerPath = %d;" % markers["path, door and seat"], "aisle nodes, the door and the seats"))
    w(decl("uint32_t MarkerOther = %d;" % markers["other"]))
    w("")
    w(decl("std::size_t MaxSteps = %d;" % C.MAX_STEPS, "MaxCafeSteps"))
    w(decl("std::size_t MaxDisplays = %d;" % MAX_DISPLAYS, "displays of one persona"))
    w(decl("std::size_t MaxFavourites = %d;" % MAX_FAV, "favourites of one persona (one per Rush group member)"))
    w(decl("std::size_t StationCount = %d;" % len(C.STATION_ORDER), "G E K C B S V"))
    w("")

    # cafés
    w("    struct Cafe")
    w("    {")
    w("        uint8_t id;")
    w("        std::string_view name;")
    w("        std::string_view cityKey;              // sw, org (the .cafe <city> argument)")
    w("        std::string_view cityName;")
    w("        char team;                             // A or H")
    w("        uint16_t map;")
    w("        uint16_t zone;")
    w("        uint32_t owner;                        // house worker 1 (creature entry)")
    w("        uint32_t head;                         // house worker 2")
    w("        uint32_t busser;")
    w("        uint32_t staffFaction;")
    w("        std::string_view tagline;")
    w("        std::string_view trim;                 // faction trim colour, hex")
    w("        char linePool;                         // the adult customers' line pool")
    w("        uint32_t buffCoffee, buffTea, buffShake;")
    w("        uint32_t apronApprentice, apronMaster, apronGolden;")
    w("        uint32_t textGreeting, textHelp, textMenu, textBoard, textRefuse;   // npc_text ids")
    w("        std::string_view serverFirstKey;")
    w("        std::string_view serverFirstText;")
    w("    };")
    w("")
    w("    inline constexpr std::array<Cafe, %d> Cafes = { {" % len(cafes))
    for c in cafes:
        nt = c["npcText"]
        w("        { %d, %s, %s, %s, '%s', %d, %d, %d, %d, %d, %d," % (
            c["id"], cpp_str(c["name"]), cpp_str(c["city"]), cpp_str(c["cityName"]), c["team"], c["map"], c["zone"],
            c["owner"], c["head"], c["busser"], c["faction"]))
        w("          %s, %s, '%s'," % (cpp_str(c["tagline"]), cpp_str(c["trim"]), c["linePool"]))
        w("          %d, %d, %d, %d, %d, %d, %d, %d, %d, %d, %d," % (
            c["buffs"]["C"], c["buffs"]["T"], c["buffs"]["M"], c["aprons"]["apprentice"], c["aprons"]["master"],
            c["aprons"]["golden"], nt["greeting"], nt["help"], nt["menu"], nt["board"], nt["refuse"]))
        w("          %s, %s }," % (cpp_str(c["serverFirst"]["key"]), cpp_str(c["serverFirst"]["text"])))
    w("    } };")
    w("")

    # families
    w("    struct Family")
    w("    {")
    w("        char id;                               // C coffee, T tea, M milkshake")
    w("        std::string_view name;")
    w("        std::string_view buff;")
    w("        std::string_view color;")
    w("        std::string_view glyph;")
    w("    };")
    w("")
    w("    inline constexpr std::array<Family, %d> Families = { {" % len(doc["families"]))
    for f in doc["families"]:
        w("        { '%s', %s, %s, %s, %s }," % (f["id"], cpp_str(f["name"]), cpp_str(f["buff"]), cpp_str(f["color"]),
                                                cpp_str(f["glyph"])))
    w("    } };")
    w("")

    # stations
    w("    struct Station")
    w("    {")
    w("        char id;                               // G E K C B S V")
    w("        std::string_view name;                 // \"Walk to the Espresso Machine first.\"")
    w("        std::array<std::string_view, 2> names; // the piece's name at cafe 1 and cafe 2")
    w("        std::string_view glyph;")
    w("        uint32_t icon;                         // SpellIcon of its step spells")
    w("        uint32_t visual;                       // SpellVisual of its step spells")
    w("    };")
    w("")
    w("    // In CafeSite::stations order.")
    w("    inline constexpr std::array<Station, StationCount> Stations = { {")
    for s in doc["stations"]:
        w("        { '%s', %s, { { %s, %s } }, %s, %d, %d }," % (
            s["id"], cpp_str(s["name"]), cpp_str(s["names"]["1"]), cpp_str(s["names"]["2"]), cpp_str(s["glyph"]),
            s["icon"], s["visual"]))
    w("    } };")
    w("")

    # actions
    w("    struct Action")
    w("    {")
    w("        uint8_t id;                            // 1..63; Actions[id - 1]")
    w("        char station;")
    w("        uint8_t key;                           // the bar slot at its station")
    w("        char kind;                             // T tap, H timed (press again to release)")
    w("        uint32_t durMs;")
    w("        uint16_t goldLo, goldHi;               // timed: the gold zone in permille of durMs, before the shift")
    w("        std::string_view name;")
    w("        std::string_view hordeName;            // the name at cafe 2 when it differs, else empty")
    w("        uint16_t emoteState;                   // loop state set while the step runs, or 0")
    w("        uint16_t emoteOneShot;                 // one-shot emote played at the start, or 0")
    w("        uint32_t spell;                        // SpellStepBase + id")
    w("        std::string_view glyph;")
    w("    };")
    w("")
    acts = doc["actions"]
    w("    inline constexpr std::array<Action, %d> Actions = { {" % len(acts))
    for a in acts:
        lo, hi = a.get("gold", (0, 0))
        w("        { %d, '%s', %d, '%s', %d, %d, %d, %s, %s, %d, %d, %d, %s }," % (
            a["id"], a["station"], a["key"], a["kind"], a["durMs"], lo, hi, cpp_str(a["name"]), cpp_str(a["hordeName"]),
            a["emote"].get("state", 0), a["emote"].get("oneshot", 0), a["spell"], cpp_str(a["glyph"])))
    w("    } };")
    w("    inline constexpr uint8_t ActionTakeOrder = %d;" % C.TAKE)
    w("    inline constexpr uint8_t ActionServe = %d;" % C.SERVE)
    w("    inline constexpr uint8_t ActionBin = %d;" % C.BIN)
    w("")

    # tiers
    w("    struct Tier")
    w("    {")
    w("        uint8_t tier;")
    w("        uint32_t price80;                      // copper at character level 80")
    w("        uint8_t buffMin;                       // base buff minutes")
    w("        uint8_t xp;                            // base barista XP")
    w("        uint32_t tip;                          // base NPC tip, copper")
    w("    };")
    w("")
    w("    inline constexpr std::array<Tier, %d> Tiers = { {" % len(doc["tiers"]))
    for t in sorted(doc["tiers"], key=int):
        v = doc["tiers"][t]
        w("        { %s, %d, %d, %d, %d }," % (t, v["price80"], v["buffMin"], v["xp"], v["tip"]))
    w("    } };")
    w("")

    # recipes
    w("    struct Recipe")
    w("    {")
    w("        uint16_t id;                           // cafeId * 100 + n")
    w("        uint8_t cafeId;")
    w("        uint8_t n;                             // the archetype number 1..19, the same in both cafes")
    w("        std::string_view arch;                 // C1..C7, T1..T6, M1..M6")
    w("        char family;")
    w("        uint8_t tier;")
    w("        uint8_t unlock;                        // barista level")
    w("        uint8_t stepCount;")
    w("        std::array<uint8_t, MaxSteps> steps;   // action ids; a repeated id is pressed again")
    w("        uint8_t lines;                         // checklist lines (equal neighbours merge)")
    w("        std::string_view name;")
    w("        std::string_view text;")
    w("        uint32_t cupItem;                      // the stock item a seated customer holds")
    w("        uint32_t tableCup;                     // the new-art cup gameobject (stand-in: + StandInOffset)")
    w("    };")
    w("")
    recs = recipes_of(doc)
    w("    inline constexpr std::array<Recipe, %d> Recipes = { {" % len(recs))
    for cafe, r, rid, name, text in recs:
        w("        { %d, %d, %d, %s, '%s', %d, %d, %d, %s, %d," % (
            rid, cafe["id"], r["n"], cpp_str(r["arch"]), r["family"], r["tier"], r["unlock"], len(r["steps"]),
            cpp_array(r["steps"], C.MAX_STEPS), C.lines_of(r["steps"])))
        w("          %s," % cpp_str(name))
        w("          %s," % cpp_str(text))
        w("          %d, %d }," % (drink_cup(cafe, r), cafe["tableCups"][r["family"]]))
    w("    } };")
    w("")

    # levels
    w("    struct Level")
    w("    {")
    w("        uint8_t level;")
    w("        uint32_t xp;                           // total barista XP to reach it")
    w("        uint8_t tickets;                       // open tickets at once")
    w("        std::string_view text;")
    w("    };")
    w("")
    w("    inline constexpr std::array<Level, %d> Levels = { {" % len(doc["levels"]))
    for lv in doc["levels"]:
        w("        { %d, %d, %d," % (lv["level"], lv["xp"], lv["tickets"]))
        w("          %s }," % cpp_str(lv["text"]))
    w("    } };")
    w("")

    # staff
    w("    struct StaffMember")
    w("    {")
    w("        uint32_t entry;")
    w("        uint8_t cafeId;")
    w("        std::string_view name;")
    w("        std::string_view subname;")
    w("        std::string_view role;                 // the layout role of its home slot")
    w("        uint32_t display;")
    w("        char gender;")
    w("        uint32_t faction;")
    w("        uint32_t npcflag;")
    w("        std::string_view script;")
    w("        uint16_t emote;                        // creature_template_addon loop emote")
    w("        uint8_t house;                         // house worker 1 (owner) or 2 (head barista), else 0")
    w("    };")
    w("")
    staff = doc["staff"]
    w("    inline constexpr std::array<StaffMember, %d> Staff = { {" % len(staff))
    for s in staff:
        w("        { %d, %d, %s, %s, %s, %d," % (
            s["entry"], s["cafe"], cpp_str(s["name"]), cpp_str(s["subname"]), cpp_str(s["role"]), s["displays"][0]))
        w("          '%s', %d, %d, %s, %d, %d }," % (
            s["gender"], s["faction"], s["npcflag"], cpp_str(s["script"]), s["emote"], s.get("house", 0)))
    w("    } };")
    w("")
    w("    struct StaffLine")
    w("    {")
    w("        uint32_t entry;")
    w("        std::string_view key;                  // shiftStart, idle, levelUp ({n}), tableService ({drink}), ...")
    w("        std::string_view text;")
    w("        bool yell;")
    w("    };")
    w("")
    sl = []
    for s in staff:
        for k in sorted(s["lines"]):
            v = s["lines"][k]
            for t in (v if isinstance(v, list) else [v]):
                sl.append((s["entry"], k, t, k in C.YELL_LINES))
    w("    // In staff order; a key with several lines (idle) has one row per line.")
    w("    inline constexpr std::array<StaffLine, %d> StaffLines = { {" % len(sl))
    for e, k, t, y in sl:
        w("        { %d, %s," % (e, cpp_str(k)))
        w("          %s, %s }," % (cpp_str(t), cpp_bool(y)))
    w("    } };")
    w("")

    # personas
    w("    enum class PersonaKind : uint8_t")
    w("    {")
    w("        Named,                                 // one fixed display (the first), its own lines")
    w("        Generic,                               // a random display and recipe, lines from its pool")
    w("        Child,                                 // a generic child: pool K, never during the Rush")
    w("        Group                                  // a Rush group: groupSize members, the first says the order"
      " line")
    w("    };")
    w("")
    w("    struct Persona")
    w("    {")
    w("        uint32_t entry;")
    w("        uint8_t cafeId;")
    w("        std::string_view name;")
    w("        PersonaKind kind;")
    w("        bool child;                            // never during the Rush (also the named children)")
    w("        bool enabled;")
    w("        char gender;                           // m or f for named personas, else '-'")
    w("        uint8_t patiencePct;")
    w("        uint8_t tipPct;")
    w("        uint8_t minLevel, maxLevel;")
    w("        uint8_t displayCount;")
    w("        std::array<uint32_t, MaxDisplays> displays;   // 0 = none yet (the persona stays disabled)")
    w("        uint8_t favCount;")
    w("        std::array<uint8_t, MaxFavourites> fav;        // archetype numbers n; a group's member i orders fav[i]")
    w("        uint8_t groupSize;")
    w("        char pool;                             // A, H or K: generic lines (and a group's other members), else"
      " '-'")
    w("        std::string_view order;                // own lines (named and groups), else empty")
    w("        std::string_view thanks;")
    w("        std::string_view complaint;            // \"emote:...\" is a text emote")
    w("    };")
    w("")
    arch_n = {a: i + 1 for i, a in enumerate(C.ARCHETYPES)}
    kinds = {"named": "Named", "generic": "Generic", "child": "Child", "group": "Group"}
    pers = doc["personas"]
    w("    // Sorted by entry; CrowdSink::NpcArrived's personaIdx is an index into this array.")
    w("    inline constexpr std::array<Persona, %d> Personas = { {" % len(pers))
    for p in sorted(pers, key=lambda x: x["entry"]):
        w("        { %d, %d, %s, PersonaKind::%s, %s, %s, '%s', %d, %d, %d, %d," % (
            p["entry"], p["cafe"], cpp_str(p["name"]), kinds[p["kind"]], cpp_bool(p["child"]), cpp_bool(p["enabled"]),
            p.get("gender", "-"), p["patience"], p["tip"], p["level"][0], p["level"][1]))
        w("          %d, %s," % (len(p["displays"]), cpp_array(p["displays"], MAX_DISPLAYS)))
        w("          %d, %s, %d, '%s'," % (len(p["fav"]), cpp_array([arch_n[f] for f in p["fav"]], MAX_FAV),
                                         p.get("groupSize", 0), p.get("pool", "-")))
        w("          %s," % cpp_str(p.get("order", "")))
        w("          %s," % cpp_str(p.get("thanks", "")))
        w("          %s }," % cpp_str(p.get("complaint", "")))
    w("    } };")
    w("")
    w("    struct PoolLine")
    w("    {")
    w("        char pool;                             // A Alliance adult, H Horde adult, K child")
    w("        char kind;                             // O order ({drink}), T thanks, C complaint")
    w("        std::string_view text;")
    w("    };")
    w("")
    pl = []
    for name in sorted(doc["linePools"]):
        pool = doc["linePools"][name]
        for k, letter in (("order", "O"), ("thanks", "T"), ("complaint", "C")):
            for t in pool[k]:
                pl.append((name, letter, t))
    w("    inline constexpr std::array<PoolLine, %d> PoolLines = { {" % len(pl))
    for name, letter, t in pl:
        w("        { '%s', '%s', %s }," % (name, letter, cpp_str(t)))
    w("    } };")
    w("")

    # gameobjects
    w("    struct GameObject")
    w("    {")
    w("        uint32_t entry;")
    w("        uint8_t type;                          // 5 GENERIC, 7 CHAIR")
    w("        uint32_t display;")
    w("        std::string_view name;")
    w("        float scale;")
    w("        std::string_view model;                // the ModelForge model of a new-art piece, else empty")
    w("        uint32_t standIn;                      // new art: its stand-in template (entry + StandInOffset), else"
      " 0")
    w("        uint32_t standInDisplay;")
    w("        float halfW, halfD;                    // footprint: half width across the piece, half depth along its"
      " front")
    w("        float height;                          // model height (new art), else 0")
    w("        float topHeight;                       // where cups stand (tables, counter, back bar), else 0")
    w("        uint8_t slots, seatHeight;             // chairs (type 7)")
    w("        bool decal;                            // a floor decal: exempt from the footprint checks")
    w("    };")
    w("")
    gos = sorted(doc["gameobjects"], key=lambda g: g["entry"])
    w("    // Sorted by entry. The stand-ins (standIn) are templates of their own, with the same name.")
    w("    inline constexpr std::array<GameObject, %d> GameObjects = { {" % len(gos))
    for g in gos:
        fp = C.go_footprint(g) or (0.0, 0.0)
        si = g.get("standin", {})
        slots, height = (g["data"] if g["type"] == 7 else (0, 0))
        w("        { %d, %d, %d, %s, %s, %s," % (
            g["entry"], g["type"], g["display"], cpp_str(g["name"]), cpp_float(g["scale"]),
            cpp_str(g.get("model", ""))))
        w("          %d, %d, %s, %s, %s, %s, %d, %d, %s }," % (
            si.get("entry", 0), si.get("display", 0), cpp_float(fp[0] / 2), cpp_float(fp[1] / 2),
            cpp_float(g["size"][2] if "size" in g else 0), cpp_float(g.get("topHeight", 0)), slots, height,
            cpp_bool(g.get("decal", False))))
    w("    } };")
    w("")

    # layout
    w("    struct LayoutPiece")
    w("    {")
    w("        uint8_t cafeId;")
    w("        uint16_t slot;")
    w("        std::string_view role;                 // bleakhold_cafe_piece.role")
    w("        char station;                          // the station of a station piece, else '\\0'")
    w("        uint32_t entry;                        // gameobject (new art) or creature entry; 0 for a marker")
    w("        bool creature;")
    w("        uint16_t link;                         // chair or parasol: its table; on-top piece: counter or back"
      " bar")
    w("        float f, l, u;                         // yards: forward along the anchor's facing, to its left, up")
    w("        float turn;                            // radians, relative to the anchor's facing")
    w("        bool snap;                             // ground-snapped at build")
    w("        uint8_t workCount;")
    w("        std::array<std::array<float, 2>, 2> work;   // work spots [fwd, side] in the piece's frame (+X its"
      " front)")
    w("        uint8_t standCount;")
    w("        std::array<float, 2> stand;            // keg table: the standing spot [fwd, side] in the piece's frame")
    w("        std::array<float, 2> side;             // queue slot: its side point, [f, l] from the slot")
    w("        float halfW, halfD;                    // footprint of the piece (0 for markers and creatures)")
    w("        float topHeight;")
    w("        bool decal;")
    w("        uint32_t marker;                       // .cafe show marker template of its role group")
    w("    };")
    w("")
    rows = layout_rows(doc)
    w("    // Cafe 1 then cafe 2, each in slot order.")
    w("    inline constexpr std::array<LayoutPiece, %d> Layout = { {" % len(rows))
    for r, fp, go in rows:
        work = r.get("work", [])
        stand = r.get("stand", [])
        side = r.get("side", [0, 0])
        fp = fp or (0.0, 0.0)
        warr = "{ { %s } }" % ", ".join(
            "{ { %s, %s } }" % (cpp_float(x), cpp_float(y)) for x, y in (work + [[0, 0], [0, 0]])[:2])
        st = C.station_of(r)
        w("        { %d, %d, %s, %s, %d, %s, %d, %s, %s, %s, %s, %s," % (
            r["cafe"], r["slot"], cpp_str(r["role"]), cpp_char(st), r["entry"], cpp_bool(r.get("creature", False)),
            r.get("link", 0), cpp_float(r["f"]), cpp_float(r["l"]), cpp_float(r["u"]), cpp_float(rad(r["turn"])),
            cpp_bool(r["snap"])))
        w("          %d, %s," % (len(work), warr))
        sp = stand[0] if stand else [0, 0]
        w("          %d, { { %s, %s } }, { { %s, %s } }, %s, %s, %s, %s, %d }," % (
            len(stand), cpp_float(sp[0]), cpp_float(sp[1]), cpp_float(side[0]), cpp_float(side[1]),
            cpp_float(fp[0] / 2), cpp_float(fp[1] / 2), cpp_float(go.get("topHeight", 0)),
            cpp_bool(go.get("decal", False)), marker_go(r)))
    w("    } };")
    w("")
    seat, cup = doc["seating"], doc["counterCup"]
    w("    // A chair's approach point is its seat moved ApproachYd away from its table; a table cup stands")
    w("    // TableCupYd from the table centre toward the seat, at the table's topHeight.")
    w("    inline constexpr float ApproachYd = %s;" % cpp_float(seat["approach"]))
    w("    inline constexpr float TableCupYd = %s;" % cpp_float(seat["tableCup"]))
    w("    // The counter cup of an order: on the counter top at (CounterCupF, the pickup spot's l, CounterCupU);")
    w("    // ready player orders sharing the pickup spot step CounterCupStepL along the counter, at most"
      " CounterCupMax.")
    w("    inline constexpr float CounterCupF = %s;" % cpp_float(cup["f"]))
    w("    inline constexpr float CounterCupU = %s;" % cpp_float(cup["u"]))
    w("    inline constexpr float CounterCupStepL = %s;" % cpp_float(cup["stepL"]))
    w("    inline constexpr uint8_t CounterCupMax = %d;" % cup["max"])
    w("")

    # items
    w("    struct Item")
    w("    {")
    w("        uint32_t entry;")
    w("        uint8_t cafeId;                        // 0: both")
    w("        std::string_view name;")
    w("    };")
    w("")
    w("    inline constexpr std::array<Item, %d> Items = { {" % len(doc["items"]))
    for it in doc["items"]:
        w("        { %d, %d, %s }," % (it["entry"], it["cafe"], cpp_str(it["name"])))
    w("    } };")
    w("")

    # lookups
    w("    inline constexpr uint16_t RecipeId(uint8_t cafeId, uint8_t n)")
    w("    {")
    w("        return static_cast<uint16_t>(cafeId * 100 + n);")
    w("    }")
    w("")
    for fn, typ, arr, key, arg in (("FindCafe", "Cafe", "Cafes", "id", "uint8_t id"),
                                   ("FindStation", "Station", "Stations", "id", "char id"),
                                   ("FindAction", "Action", "Actions", "id", "uint8_t id"),
                                   ("FindRecipe", "Recipe", "Recipes", "id", "uint16_t id"),
                                   ("FindLevel", "Level", "Levels", "level", "uint8_t id"),
                                   ("FindStaff", "StaffMember", "Staff", "entry", "uint32_t id"),
                                   ("FindPersona", "Persona", "Personas", "entry", "uint32_t id"),
                                   ("FindGameObject", "GameObject", "GameObjects", "entry", "uint32_t id")):
        w("    inline constexpr %s const* %s(%s)" % (typ, fn, arg))
        w("    {")
        w("        for (%s const& x : %s)" % (typ, arr))
        w("            if (x.%s == id)" % key)
        w("                return &x;")
        w("        return nullptr;")
        w("    }")
        w("")
    w("    // The index of a station in Stations (and CafeSite::stations), or -1.")
    w("    inline constexpr int StationIndex(char id)")
    w("    {")
    w("        for (std::size_t i = 0; i < Stations.size(); ++i)")
    w("            if (Stations[i].id == id)")
    w("                return static_cast<int>(i);")
    w("        return -1;")
    w("    }")
    w("")
    w("    // The index of a persona in Personas (CrowdSink::NpcArrived's personaIdx), or -1.")
    w("    inline constexpr int PersonaIndex(uint32_t entry)")
    w("    {")
    w("        for (std::size_t i = 0; i < Personas.size(); ++i)")
    w("            if (Personas[i].entry == entry)")
    w("                return static_cast<int>(i);")
    w("        return -1;")
    w("    }")
    w("")
    w("    static_assert(Actions.size() <= 63 && Actions[ActionServe - 1].station == 'V', \"cafe.json actions\");")
    w("    static_assert(Recipes.size() == %d && Levels.size() == 10 && Tiers.size() == 5, \"cafe.json recipes\");"
      % len(recs))
    w("}")
    w("")
    w("#endif")
    return "\n".join(wrap_all(o)) + "\n"


# ------------------------------------------------------------------------------------------------- Lua data

def render_lua(doc):
    o = []
    w = o.append
    w("-- Bleakhold: the café catalogue. Generated by Tools/CafeForge/cafeforge_data.py from"
      " Tools/CafeForge/cafe.json;")
    w("-- do not edit. The fallback names and numbers until the server's DEF H, G, F and U records arrive and override")
    w("-- them (docs/BleakholdProtocol.md, section 21).")
    w("local ADDON, ns = ...")
    w("")
    w("ns.CafeData = {")
    w("    cafes = {")
    staff = C.by_key(doc["staff"], "entry")
    for c in doc["cafes"]:
        w("        [%d] = {" % c["id"])
        w("            id = %d, name = %s, city = %s, cityName = %s, team = %s, map = %d, zone = %d," % (
            c["id"], lua_str(c["name"]), lua_str(c["city"]), lua_str(c["cityName"]), lua_str(c["team"]), c["map"],
            c["zone"]))
        w("            owner = %s, head = %s, trim = %s, trimMetal = %s," % (
            lua_str(staff[c["owner"]]["name"]), lua_str(staff[c["head"]]["name"]), lua_str(c["trim"]),
            lua_str(c["trimMetal"])))
        w("            tagline = %s," % lua_str(c["tagline"]))
        w("        },")
    w("    },")
    w("    families = {")
    for f in doc["families"]:
        w("        %s = { id = %s, name = %s, buff = %s, color = %s, glyph = %s }," % (
            f["id"], lua_str(f["id"]), lua_str(f["name"]), lua_str(f["buff"]), lua_str(f["color"]),
            lua_str(f["glyph"])))
    w("    },")
    w("    stationOrder = { %s }," % ", ".join(lua_str(s) for s in C.STATION_ORDER))
    w("    stations = {")
    for st in doc["stations"]:
        w("        %s = { id = %s, name = %s, glyph = %s, icon = %d," % (
            st["id"], lua_str(st["id"]), lua_str(st["name"]), lua_str(st["glyph"]), st["icon"]))
        w("            names = { %s, %s } }," % (lua_str(st["names"]["1"]), lua_str(st["names"]["2"])))
    w("    },")
    w("    actions = {")
    for a in doc["actions"]:
        extra = ""
        if "gold" in a:
            extra += ", gold = { %d, %d }" % tuple(a["gold"])
        w("        [%d] = { id = %d, station = %s, key = %d, kind = %s, durMs = %d%s, spellId = %d," % (
            a["id"], a["id"], lua_str(a["station"]), a["key"], lua_str(a["kind"]), a["durMs"], extra, a["spell"]))
        names = "name = %s" % lua_str(a["name"])
        if a["hordeName"]:
            names += ", hordeName = %s" % lua_str(a["hordeName"])
        w("            %s, glyph = %s }," % (names, lua_str(a["glyph"])))
    w("    },")
    w("    tiers = {")
    for t in sorted(doc["tiers"], key=int):
        v = doc["tiers"][t]
        w("        [%s] = { price80 = %d, buffMin = %d }," % (t, v["price80"], v["buffMin"]))
    w("    },")
    w("    recipes = {")
    for cafe, r, rid, name, text in recipes_of(doc):
        w("        [%d] = { id = %d, cafeId = %d, n = %d, arch = %s, family = %s, tier = %d, unlock = %d," % (
            rid, rid, cafe["id"], r["n"], lua_str(r["arch"]), lua_str(r["family"]), r["tier"], r["unlock"]))
        w("            steps = { %s }, lines = %d," % (", ".join(str(x) for x in r["steps"]), C.lines_of(r["steps"])))
        w("            name = %s," % lua_str(name))
        w("            text = %s }," % lua_str(text))
    w("    },")
    w("    levels = {")
    for lv in doc["levels"]:
        w("        [%d] = { level = %d, xp = %d, tickets = %d," % (lv["level"], lv["level"], lv["xp"], lv["tickets"]))
        w("            text = %s }," % lua_str(lv["text"]))
    w("    },")
    sid = doc["spellIds"]
    w("    spells = {")
    w("        shift = %d, stepBase = %d, sprint = %d, tired = %d, crown = %d," % (
        sid["shift"], sid["stepBase"], sid["sprint"], sid["tired"], sid["crown"]))
    w("        coffee = { %d, %d }, tea = { %d, %d }, shake = { %d, %d }," % (
        sid["coffee"][0], sid["coffee"][1], sid["tea"][0], sid["tea"][1], sid["shake"][0], sid["shake"][1]))
    w("    },")
    w("    -- The hero machines for the café window's 3D view (shown only when patch-4 is present).")
    w("    models = {")
    gos = C.by_key(doc["gameobjects"], "entry")
    for cafe in (1, 2):
        row = next(r for r in C.cafe_layout(doc, cafe) if r["role"] == "station_E")
        g = gos[row["entry"]]
        mf = g.get("modelFrame", {"position": [0, 0, 0], "scale": 1.0, "facing": 0.0})
        w("        [%d] = { name = %s, position = { %s }, scale = %s, facing = %s," % (
            cafe, lua_str(g["model"]), ", ".join(lua_num(v) for v in mf["position"]), lua_num(mf["scale"]),
            lua_num(mf["facing"])))
        w("            path = %s }," % lua_str("World\\Bleakhold\\Cafe\\%s\\BH_Cafe_%s.m2" % (g["model"], g["model"])))
    w("    },")
    w("}")
    return "\n".join(o) + "\n"


# ------------------------------------------------------------------------------------------------------ SQL

GO_COLUMNS = ("entry", "type", "displayId", "name", "IconName", "castBarCaption", "unk1", "size") + \
    tuple("Data%d" % i for i in range(24)) + ("AIName", "ScriptName", "VerifiedBuild")
GO_ADDON_COLUMNS = ("entry", "faction", "flags", "mingold", "maxgold", "artkit0", "artkit1", "artkit2", "artkit3")
CREATURE_COLUMNS = (
    "entry", "difficulty_entry_1", "difficulty_entry_2", "difficulty_entry_3", "KillCredit1", "KillCredit2", "name",
    "subname", "IconName", "gossip_menu_id", "minlevel", "maxlevel", "exp", "faction", "npcflag", "speed_walk",
    "speed_run", "speed_swim", "speed_flight", "detection_range", "rank", "dmgschool", "DamageModifier",
    "BaseAttackTime", "RangeAttackTime", "BaseVariance", "RangeVariance", "unit_class", "unit_flags", "unit_flags2",
    "dynamicflags", "family", "type", "type_flags", "lootid", "pickpocketloot", "skinloot", "PetSpellDataId",
    "VehicleId", "mingold", "maxgold", "AIName", "MovementType", "HoverHeight", "HealthModifier", "ManaModifier",
    "ArmorModifier", "ExperienceModifier", "RacialLeader", "movementId", "RegenHealth", "CreatureImmunitiesId",
    "flags_extra", "ScriptName", "VerifiedBuild")
MODEL_COLUMNS = ("CreatureID", "Idx", "CreatureDisplayID", "DisplayScale", "Probability", "VerifiedBuild")
CREATURE_ADDON_COLUMNS = ("entry", "path_id", "mount", "bytes1", "bytes2", "emote", "visibilityDistanceType", "auras")
CUSTOM_ATTR_COLUMNS = ("spell_id", "attributes")
NPC_TEXT_COLUMNS = ("ID", "text0_0", "text0_1", "BroadcastTextID0", "lang0", "Probability0", "em0_0", "em0_1", "em0_2",
                    "em0_3", "em0_4", "em0_5", "VerifiedBuild")
# item_template (data/sql/base/db_world/item_template.sql) in column order, with the values the aprons do not set.
ITEM_COLUMNS = (
    ("entry", 0), ("class", 0), ("subclass", 0), ("SoundOverrideSubclass", -1), ("name", ""), ("displayid", 0),
    ("Quality", 0), ("Flags", 0), ("FlagsExtra", 0), ("BuyCount", 1), ("BuyPrice", 0), ("SellPrice", 0),
    ("InventoryType", 0), ("AllowableClass", -1), ("AllowableRace", -1), ("ItemLevel", 0), ("RequiredLevel", 0),
    ("RequiredSkill", 0), ("RequiredSkillRank", 0), ("requiredspell", 0), ("requiredhonorrank", 0),
    ("RequiredCityRank", 0), ("RequiredReputationFaction", 0), ("RequiredReputationRank", 0), ("maxcount", 0),
    ("stackable", 1), ("ContainerSlots", 0), ("stat_type1", 0), ("stat_value1", 0), ("stat_type2", 0),
    ("stat_value2", 0), ("stat_type3", 0), ("stat_value3", 0), ("stat_type4", 0), ("stat_value4", 0),
    ("stat_type5", 0), ("stat_value5", 0), ("stat_type6", 0), ("stat_value6", 0), ("stat_type7", 0),
    ("stat_value7", 0), ("stat_type8", 0), ("stat_value8", 0), ("stat_type9", 0), ("stat_value9", 0),
    ("stat_type10", 0), ("stat_value10", 0), ("ScalingStatDistribution", 0), ("ScalingStatValue", 0),
    ("dmg_min1", 0), ("dmg_max1", 0), ("dmg_type1", 0), ("dmg_min2", 0), ("dmg_max2", 0), ("dmg_type2", 0),
    ("armor", 0), ("holy_res", 0), ("fire_res", 0), ("nature_res", 0), ("frost_res", 0), ("shadow_res", 0),
    ("arcane_res", 0), ("delay", 0), ("ammo_type", 0), ("RangedModRange", 0), ("spellid_1", 0),
    ("spelltrigger_1", 0), ("spellcharges_1", 0), ("spellppmRate_1", 0), ("spellcooldown_1", -1),
    ("spellcategory_1", 0), ("spellcategorycooldown_1", -1), ("spellid_2", 0), ("spelltrigger_2", 0),
    ("spellcharges_2", 0), ("spellppmRate_2", 0), ("spellcooldown_2", -1), ("spellcategory_2", 0),
    ("spellcategorycooldown_2", -1), ("spellid_3", 0), ("spelltrigger_3", 0), ("spellcharges_3", 0),
    ("spellppmRate_3", 0), ("spellcooldown_3", -1), ("spellcategory_3", 0), ("spellcategorycooldown_3", -1),
    ("spellid_4", 0), ("spelltrigger_4", 0), ("spellcharges_4", 0), ("spellppmRate_4", 0), ("spellcooldown_4", -1),
    ("spellcategory_4", 0), ("spellcategorycooldown_4", -1), ("spellid_5", 0), ("spelltrigger_5", 0),
    ("spellcharges_5", 0), ("spellppmRate_5", 0), ("spellcooldown_5", -1), ("spellcategory_5", 0),
    ("spellcategorycooldown_5", -1), ("bonding", 0), ("description", ""), ("PageText", 0), ("LanguageID", 0),
    ("PageMaterial", 0), ("startquest", 0), ("lockid", 0), ("Material", 0), ("sheath", 0), ("RandomProperty", 0),
    ("RandomSuffix", 0), ("block", 0), ("itemset", 0), ("MaxDurability", 0), ("area", 0), ("Map", 0),
    ("BagFamily", 0), ("TotemCategory", 0), ("socketColor_1", 0), ("socketContent_1", 0), ("socketColor_2", 0),
    ("socketContent_2", 0), ("socketColor_3", 0), ("socketContent_3", 0), ("socketBonus", 0), ("GemProperties", 0),
    ("RequiredDisenchantSkill", -1), ("ArmorDamageModifier", 0), ("duration", 0), ("ItemLimitCategory", 0),
    ("HolidayId", 0), ("ScriptName", ""), ("DisenchantID", 0), ("FoodType", 0), ("minMoneyLoot", 0),
    ("maxMoneyLoot", 0), ("flagsCustom", 0), ("VerifiedBuild", 0),
)

# The tables the file owns and the id ranges it deletes first (section 3.10.3).
OWNED = (
    ("gameobject_template", "entry", 909300, 909379),
    ("gameobject_template_addon", "entry", 909300, 909379),
    ("creature_template", "entry", 909300, 909379),
    ("creature_template_model", "CreatureID", 909300, 909379),
    ("creature_template_addon", "entry", 909300, 909379),
    ("spell_custom_attr", "spell_id", 100900, 100959),
    ("item_template", "entry", 909380, 909389),
    ("npc_text", "ID", 909300, 909319),
)


def go_rows(doc):
    """Every gameobject_template row: the new-art pieces, their stand-ins and the furniture and markers."""
    rows = []
    for g in doc["gameobjects"]:
        data = list(g["data"]) + [0] * (24 - len(g["data"]))
        rows.append([g["entry"], g["type"], g["display"], g["name"], "", "", "", float(g["scale"])] + data +
                    ["", "", 0])
        si = g.get("standin")
        if si:
            rows.append([si["entry"], g["type"], si["display"], g["name"], "", "", "", float(si["scale"])] + data +
                        ["", "", 0])
    rows.sort(key=lambda r: r[0])
    return rows


def creature_rows(doc):
    rows, models, addons = [], [], []

    def exp(level):
        return 2 if level > 70 else 1 if level > 60 else 0

    def row(entry, name, subname, lv, faction, npcflag, script):
        return [entry, 0, 0, 0, 0, 0, name, subname, None, 0, lv[0], lv[1], exp(lv[1]), faction, npcflag, 1.0,
                1.14286, 1.0, 1.0, 20.0, 0, 0, 1.0, 2000, 2000, 1.0, 1.0, 1, UNIT_FLAGS, 0, 0, 0,
                CREATURE_TYPE_HUMANOID, 0, 0, 0, 0, 0, 0, 0, 0, "NullCreatureAI", 0, 1.0, 1.0, 1.0, 1.0, 1.0, 0, 0, 1,
                0, FLAGS_EXTRA_CIVILIAN, script, 0]

    for s in doc["staff"]:
        rows.append(row(s["entry"], s["name"], s["subname"], (s["level"], s["level"]), s["faction"], s["npcflag"],
                        s["script"]))
        models.append([s["entry"], 0, s["displays"][0], 1.0, 1.0, 0])
        addons.append([s["entry"], 0, 0, 0, 0, s["emote"], 0, ""])
    for p in doc["personas"]:
        rows.append(row(p["entry"], p["name"], None, p["level"], CUSTOMER_FACTION, 0, ""))
        disp = p["displays"]
        if disp == [0]:
            disp = [p["templateDisplay"]]
        elif p["kind"] == "named":
            disp = disp[:1]
        # creature_template_model holds at most 4 models (CHECK Idx <= 3); the module picks from the whole list.
        for i, d in enumerate(disp[:4]):
            models.append([p["entry"], i, d, 1.0, 1.0, 0])
    rows.sort(key=lambda r: r[0])
    models.sort(key=lambda r: (r[0], r[1]))
    addons.sort(key=lambda r: r[0])
    return rows, models, addons


def item_rows(doc):
    names = [c for c, _ in ITEM_COLUMNS]
    rows = []
    for it in doc["items"]:
        v = dict(ITEM_COLUMNS)
        v.update({"entry": it["entry"], "class": 4, "subclass": 1, "name": it["name"], "displayid": it["display"],
                  "Quality": it["quality"], "InventoryType": it["inventoryType"], "ItemLevel": it["itemLevel"],
                  "maxcount": 1, "bonding": 1, "description": it["description"], "Material": 7})
        rows.append([v[c] for c in names])
    return names, rows


def _insert(table, columns, rows):
    head = wrap("INSERT INTO `%s` (" % table, ["`%s`" % c for c in columns])
    head[-1] += ") VALUES"
    body = ["(%s)%s" % (", ".join(sql_val(v) for v in r), "," if i < len(rows) - 1 else ";")
            for i, r in enumerate(rows)]
    return head + body


def render_sql(doc):
    o = []
    w = o.append
    w("-- mod-bleakhold-ui: the café's world templates (protocol section 21): The Lion's Roast (Stormwind) and The")
    w("-- Grinding Tusk (Orgrimmar). Generated by Tools/CafeForge/cafeforge_data.py from Tools/CafeForge/cafe.json; do")
    w("-- not edit. The file owns whole id ranges (gameobject and creature templates 909300-909379, items")
    w("-- 909380-909389, npc_text 909300-909319, spell_custom_attr 100900-100959): each is deleted before its rows are")
    w("-- inserted, so the file can be applied again (ac-db-import re-runs it when it changes).")
    w("-- The pieces are placed in game with .cafe build; nothing here spawns anything. The café spells (spell_dbc")
    w("-- 100900-100959) and the new art's GameObjectDisplayInfo rows come from CafeForge on the server; until they"
      " are")
    w("-- there the module keeps the café off (spells) or uses the stand-ins (art).")
    w("")
    w("-- gameobject_template: 909300-909323 the new-art pieces (display = entry - 890000, patch-4.MPQ), 909330-909353")
    w("-- their stand-ins on stock displays (entry + 30, the same name), 909360-909379 furniture and the .cafe show")
    w("-- markers. GENERIC (5) pieces show their name on hover (Data0 floating tooltip, Data1 highlight); chairs (7)")
    w("-- have Data0 slots and Data1 height.")
    lo, hi = OWNED[0][2], OWNED[0][3]
    w("DELETE FROM `gameobject_template` WHERE `entry` BETWEEN %d AND %d;" % (lo, hi))
    gos = go_rows(doc)
    o.extend(_insert("gameobject_template", GO_COLUMNS, gos))
    w("")
    w("-- gameobject_template_addon: GO_FLAG_NODESPAWN (32) on every piece.")
    w("DELETE FROM `gameobject_template_addon` WHERE `entry` BETWEEN %d AND %d;" % (lo, hi))
    o.extend(_insert("gameobject_template_addon", GO_ADDON_COLUMNS,
                     [[r[0], 0, GO_FLAG_NODESPAWN, 0, 0, 0, 0, 0, 0] for r in gos]))
    w("")
    rows, models, addons = creature_rows(doc)
    w("-- creature_template: 909300-909310 the staff (faction 12 Stormwind / 29 Orgrimmar; the owners and head")
    w("-- baristas have the gossip flag, their scripts and faction 35, so the other team can talk to them and hear the")
    w("-- refusal), 909320-909344 and 909350-909374 the customers (faction 35).")
    w("-- All of them: humanoid, not attackable and immune to players and creatures (unit_flags 0x302), civilian")
    w("-- (flags_extra 2), NullCreatureAI (the module moves them).")
    w("DELETE FROM `creature_template` WHERE `entry` BETWEEN 909300 AND 909379;")
    o.extend(_insert("creature_template", CREATURE_COLUMNS, rows))
    w("")
    w("-- creature_template_model: the fixed display of the staff and the named customers, and up to four displays of")
    w("-- the others (Idx 0..3 is all the table holds; the module picks from the whole list of BleakholdCafeData.h).")
    w("DELETE FROM `creature_template_model` WHERE `CreatureID` BETWEEN 909300 AND 909379;")
    o.extend(_insert("creature_template_model", MODEL_COLUMNS, models))
    w("")
    w("-- creature_template_addon: the staff's loop emotes (Nixxi 173 EMOTE_STATE_WORK at the machine, Zan'jabi 69")
    w("-- EMOTE_STATE_USE_STANDING by the kettle), so a grid reload keeps them.")
    w("DELETE FROM `creature_template_addon` WHERE `entry` BETWEEN 909300 AND 909379;")
    o.extend(_insert("creature_template_addon", CREATURE_ADDON_COLUMNS, addons))
    w("")
    w("-- spell_custom_attr: On Shift (100900), the speed helper (100936) and Tired (100937) are never saved")
    w("-- (SPELL_ATTR0_CU_AURA_CANNOT_BE_SAVED). Rows of spells not yet in spell_dbc are logged and ignored by the"
      " core.")
    w("DELETE FROM `spell_custom_attr` WHERE `spell_id` BETWEEN 100900 AND 100959;")
    o.extend(_insert("spell_custom_attr", CUSTOM_ATTR_COLUMNS,
                     [[s, SPELL_ATTR0_CU_AURA_CANNOT_BE_SAVED] for s in NEVER_SAVED]))
    w("")
    names, irows = item_rows(doc)
    w("-- item_template: the aprons. Cloth robes (InventoryType 20) with no stats and no armor, bind on pickup,"
      " unique,")
    w("-- no sell price.")
    w("DELETE FROM `item_template` WHERE `entry` BETWEEN 909380 AND 909389;")
    o.extend(_insert("item_template", names, irows))
    w("")
    w("-- npc_text: the owners' gossip texts.")
    w("DELETE FROM `npc_text` WHERE `ID` BETWEEN 909300 AND 909319;")
    o.extend(_insert("npc_text", NPC_TEXT_COLUMNS,
                     [[t["id"], t["text"], t["text"], 0, 0, 1.0, 0, 0, 0, 0, 0, 0, 0] for t in doc["npcText"]]))
    return "\n".join(o) + "\n"


# ----------------------------------------------------------------------------------------------- generation

# Repository path (with /) -> renderer.
GENERATED = {
    HEADER_PATH: render_header,
    LUA_PATH: render_lua,
    SQL_PATH: render_sql,
}


def repo_path(rel, repo=REPO):
    return os.path.join(repo, *rel.split("/"))


def generate(doc, check=False, repo=REPO):
    """Writes the generated files that differ from the catalogue (only compares with check); returns their paths.

    A checkout with CRLF line endings (Windows, * text=auto) is not stale; the files are written with LF."""
    stale = []
    for rel, render in GENERATED.items():
        text = render(doc)
        path = repo_path(rel, repo)
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
