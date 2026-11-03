"""cafe.json, the café catalogue: loading, the rules every entry must keep, and the default layout's footprint checks.

validate(doc) returns every problem of a parsed cafe.json (empty when it is valid); load() raises CatalogError with
them. The rules:
- ids are inside their blocks (ids) and unique, and every reference (cafés, staff, personas, recipes, actions,
  stations, spells, icons, items, gameobjects, npc_text, layout links) resolves;
- the recipe rules (19 archetypes per café, steps of known actions ending with Serve, a timed step in each, at most
  MaxSteps) and the design numbers of the tiers and barista levels (TIERS, LEVELS) are kept;
- the default layout of both cafés passes the footprint checks (layout_problems);
- every named persona and staff member has one fixed display (the first listed) and a gender tag that matches the
  display-gender table of the stock "[PH] Gossip NPC" rows (DISPLAY_GENDER) where the display is in it;
- names and lines fit the protocol caps (NAME_BYTES, LINE_BYTES) and their database columns;
- no goblin persona or staff member at café 1 (and its staff are all human); Rush groups carry kind "group".
"""

import json
import math
import os
import re

from . import TOOL

CAFE_JSON = os.path.join(TOOL, "cafe.json")

# Protocol caps (BleakholdMessages.h, section 21): MaxCafeNameBytes and MaxCafeLineBytes.
NAME_BYTES = 48
LINE_BYTES = 160
MAX_STEPS = 12          # MaxCafeSteps
MAX_ACTION_ID = 63      # CSTEP takes 1..63
GOLD_MIN_MS = 375       # every gold zone is at least this wide
GOLD_SHIFT = 50         # each timed step shifts its gold zone by up to +-5% of the duration ...
GOLD_CLAMP = (50, 950)  # ... clamped to [5%, 95%]
SERVE, TAKE, BIN = 25, 24, 26
STEP_SPELL_BASE = 100900
STAND_IN_OFFSET = 30
DISPLAY_OFFSET = 890000  # display id = new-art gameobject entry - 890000
NEVER_VISUAL = 3881      # cooking: with the Chef's Hat aura the core forces a 500 ms cast (Object.cpp)
STATION_ORDER = ("G", "E", "K", "C", "B", "S", "V")
FAMILIES = ("C", "T", "M")
ARCHETYPES = ["C%d" % i for i in range(1, 8)] + ["T%d" % i for i in range(1, 7)] + ["M%d" % i for i in range(1, 7)]

# The design numbers (sections 2.5, 2.8 and 2.9); BleakholdCafeRules.h and its tests build on them.
TIERS = {
    1: {"price80": 4000, "buffMin": 30, "xp": 8, "tip": 400},
    2: {"price80": 6000, "buffMin": 35, "xp": 12, "tip": 600},
    3: {"price80": 9000, "buffMin": 40, "xp": 18, "tip": 900},
    4: {"price80": 12000, "buffMin": 45, "xp": 25, "tip": 1300},
    5: {"price80": 18000, "buffMin": 50, "xp": 35, "tip": 1800},
}
# level: (total XP, tickets, the archetypes it unlocks)
LEVELS = {
    1: (0, 1, ("C1", "C2", "T1", "T2")),
    2: (120, 1, ("C3", "M1", "M2")),
    3: (320, 1, ("C4", "T3")),
    4: (620, 2, ("C5", "M3")),
    5: (1040, 2, ("C6", "T4")),
    6: (1600, 2, ("T5", "M4")),
    7: (2320, 2, ("M5",)),
    8: (3220, 3, ("T6",)),
    9: (4320, 3, ("C7",)),
    10: (5640, 3, ("M6",)),
}
LEVEL_REWARDS = ("tutorial", "apprenticeApron", "memory", "staffDrink", "regulars", "title", "masterApron",
                 "serverFirst")

# The stock "[PH] Gossip NPC" rows of creature_template_model: display -> (race, gender). Other displays' genders
# are unverified (V21); their tags are not checked.
DISPLAY_GENDER = {
    19175: ("gnome", "f"), 19176: ("gnome", "m"), 19177: ("human", "f"), 19178: ("human", "m"),
    19181: ("orc", "f"), 19182: ("orc", "m"), 19183: ("tauren", "f"), 19184: ("tauren", "m"),
    19185: ("troll", "f"), 19186: ("troll", "m"), 19187: ("undead", "f"), 19188: ("undead", "m"),
    19340: ("goblin", "f"), 19343: ("goblin", "m"),
}
# Displays whose race is known from their stock creature although their gender is not in the table above.
DISPLAY_RACE = {29904: "goblin"}
RACES = ("human", "dwarf", "gnome", "night elf", "draenei", "high elf", "orc", "troll", "tauren", "undead",
         "blood elf", "goblin", "eredar")

# UI.CAFE_GLYPHS (Art/CafeGlyphs.tga), in atlas order.
GLYPHS = ("bean", "grinder", "machine", "steam", "kettle", "leaf", "coldbox", "scoop",
          "blender", "bottle", "cream", "bell", "cup", "teacup", "shake", "patience",
          "star", "coin", "ticket", "chair", "sun", "crown", "apron", "bin",
          "memory", "group", "timer", "arrow", "hand", "lock", "check", "dot")

# Emote ids the actions use (SharedDefines.h Emote): loop states and one-shots.
EMOTE_STATES = {69: "EMOTE_STATE_USE_STANDING", 133: "EMOTE_STATE_USE_STANDING_NO_SHEATHE",
                173: "EMOTE_STATE_WORK", 428: "EMOTE_STATE_LOOT"}
EMOTE_ONESHOTS = {274: "EMOTE_ONESHOT_NO", 396: "EMOTE_ONESHOT_TALK_NO_SHEATHE", 432: "EMOTE_ONESHOT_USE_STANDING"}

# Staff line keys and the placeholders each may hold.
STAFF_LINES = {
    "shiftOffered": (), "shiftStart": (), "shiftEnd": (), "rushStart": (), "houseOrder": (), "ambientAnswer": (),
    "takeover": (), "dangerPause": (), "idle": (), "refuse": (), "tutorialShot": (), "tutorialSteam": (),
    "levelUp": ("{n}",), "tableService": ("{drink}",), "rush": (),
}
YELL_LINES = ("rushStart",)
OWNER_LINES = ("shiftOffered", "shiftStart", "shiftEnd", "rushStart", "houseOrder", "ambientAnswer", "takeover",
               "dangerPause", "idle", "refuse")
HEAD_LINES = ("tutorialShot", "tutorialSteam", "levelUp", "houseOrder")
STAFF_ROLES = ("staff_owner", "staff_head", "staff_busser", "staff_extra_1", "staff_extra_2", "staff_extra_3")
PERSONA_KINDS = ("named", "generic", "child", "group")
GROUP_SIZE = 3

# Database columns (data/sql/base/db_world): gameobject_template.name varchar(100), creature_template.name and
# subname char(100), item_template.name varchar(255) and description varchar(255); RaceForge's spell_dbc limits.
GO_NAME_BYTES = 100
CREATURE_NAME_BYTES = 100
ITEM_TEXT_BYTES = 255
SPELL_TEXT_BYTES = {"name": 100, "description": 4000, "aura_description": 550}
# RaceForge parse_spell's keys (Tools/RaceForge/rflib/config.py) and the café wrapper around them (section 6.3).
SPELL_KEYS = ("id", "name", "subtext", "description", "aura_description", "icon", "icon_name", "visual", "fields",
              "comment", "cast_by", "server_row", "text_locales")
WRAPPER_KEYS = ("spell", "castMs", "durationMs", "range")
# The Spell.dbc columns (RaceForge's Spell schema) the café spells set; CafeForge resolves castingTimeIndex,
# durationIndex and rangeIndex from castMs, durationMs and range, so those three never appear here.
SPELL_FIELDS = ("attributes", "attributesEx", "attributesExB", "attributesExC", "attributesExD", "interruptFlags",
                "auraInterruptFlags", "channelInterruptFlags", "effect[0]", "effectDieSides[0]",
                "effectBasePoints[0]", "implicitTargetA[0]", "effectAura[0]", "defenseType", "schoolMask")
A1_CHANNEL = 0x4
A4_BAR = 0x08000000
CAFE_SPELLS = [100900] + list(range(100901, 100927)) + list(range(100930, 100939))

# Layout: roles, and the distances of section 3.12.3.
MARKER_ROLES = ("order_spot", "pickup_spot", "door")
SPOT_GAP = 0.7            # the two work spots of a station, side by side
FIRST_SPOT_MIN = 2.0      # first spots (and spot-pair centres) of two stations
ANY_SPOT_MIN = 1.2        # any two spots of different stations
STAFF_SPOT_MIN = 0.8      # a staff home from any work spot
CLEARANCE = 0.3           # a work spot or a staff home from every footprint (a body fits)
DOOR_MIN = 25.0           # the door from the anchor
EPS = 1e-6

HEX6 = re.compile(r"^[0-9A-F]{6}$")
ROLE_RE = re.compile(r"^(counter|tipjar|backbar|station_[GEKCBSV]|order_spot|pickup_spot|queue_[1-8]|door|path_\d+|"
                     r"table_\d+|chair_\d+|parasol_\d+|kegtable_\d+|chalkboard|staff_owner|staff_head|staff_busser|"
                     r"staff_extra_[1-3]|decor)$")
BAD_TEXT = re.compile(r"[\x00-\x1f|$\\]")


class CatalogError(Exception):
    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__("\n".join(self.problems))


def load(path=CAFE_JSON, check=True):
    """The parsed cafe.json; raises CatalogError (with every problem) when it is not valid."""
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError) as ex:
        raise CatalogError(["%s: %s" % (path, ex)]) from None
    if check:
        problems = validate(doc)
        if problems:
            raise CatalogError(problems)
    return doc


# ---------------------------------------------------------------------------------------------- small helpers

def is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def is_num(v):
    return (isinstance(v, (int, float))) and not isinstance(v, bool)


def nbytes(s):
    return len(s.encode("utf-8"))


def lines_of(steps):
    """Checklist lines of a recipe: consecutive equal actions merge into one line ("Scoop Ice Cream x2")."""
    return sum(1 for i, a in enumerate(steps) if i == 0 or steps[i - 1] != a)


def recipe_id(cafe_id, n):
    return cafe_id * 100 + n


def by_key(items, key):
    return {i.get(key): i for i in items if isinstance(i, dict)}


def _text(problems, where, s, limit, allow_empty=False, placeholders=()):
    """A text field: a string, within its byte limit, with no control character, '|', '$' or '\\', and with no
    placeholder but the allowed ones."""
    if not isinstance(s, str):
        problems.append("%s: must be a string" % where)
        return
    if not s.strip() and not allow_empty:
        problems.append("%s: is empty" % where)
    if s != s.strip():
        problems.append("%s: has leading or trailing spaces" % where)
    if nbytes(s) > limit:
        problems.append("%s: %d bytes, more than %d" % (where, nbytes(s), limit))
    if BAD_TEXT.search(s):
        problems.append("%s: holds a control character, '|', '$' or '\\'" % where)
    for ph in re.findall(r"\{[^}]*\}", s):
        if ph not in placeholders:
            problems.append("%s: unknown placeholder %s" % (where, ph))


def _fields(problems, where, obj, required, optional=()):
    if not isinstance(obj, dict):
        problems.append("%s: must be an object" % where)
        return False
    for k in obj:
        if k not in required and k not in optional and k != "comment":
            problems.append("%s: unknown field %r" % (where, k))
    for k in required:
        if k not in obj:
            problems.append("%s: missing field %r" % (where, k))
    return True


def _in_block(problems, doc, block, value, where):
    lo, hi = doc.get("ids", {}).get(block, (0, -1))
    if not is_int(value) or not lo <= value <= hi:
        problems.append("%s: %r is outside the %s block %d-%d" % (where, value, block, lo, hi))


# ---------------------------------------------------------------------------------------------------- geometry

def to_anchor(f, l, turn_deg, x, y):
    """A piece-frame offset (x along the piece's front, y to its left) in the anchor frame (F, L)."""
    t = math.radians(turn_deg)
    return (f + x * math.cos(t) - y * math.sin(t), l + x * math.sin(t) + y * math.cos(t))


class Box:
    """A piece's 2D footprint: centre (f, l), half depth hd along the piece's front, half width hw across it."""

    def __init__(self, f, l, hd, hw, turn_deg):
        self.f, self.l, self.hd, self.hw, self.t = f, l, hd, hw, math.radians(turn_deg)

    def local(self, f, l):
        dx, dy = f - self.f, l - self.l
        c, s = math.cos(self.t), math.sin(self.t)
        return dx * c + dy * s, -dx * s + dy * c

    def corners(self):
        c, s = math.cos(self.t), math.sin(self.t)
        return [(self.f + x * c - y * s, self.l + x * s + y * c)
                for x, y in ((self.hd, self.hw), (self.hd, -self.hw), (-self.hd, -self.hw), (-self.hd, self.hw))]

    def contains(self, f, l, eps=EPS):
        x, y = self.local(f, l)
        return abs(x) < self.hd - eps and abs(y) < self.hw - eps

    def holds(self, other, eps=EPS):
        """Every corner of other inside (or on the edge of) this box."""
        for f, l in other.corners():
            x, y = self.local(f, l)
            if abs(x) > self.hd + eps or abs(y) > self.hw + eps:
                return False
        return True

    def distance(self, f, l):
        x, y = self.local(f, l)
        dx, dy = max(abs(x) - self.hd, 0.0), max(abs(y) - self.hw, 0.0)
        return math.hypot(dx, dy)

    def axes(self):
        c, s = math.cos(self.t), math.sin(self.t)
        return [(c, s), (-s, c)]

    def overlaps(self, other, eps=EPS):
        """True when the two boxes share area (separating axis test; touching edges do not count)."""
        for ax, ay in self.axes() + other.axes():
            p1 = [f * ax + l * ay for f, l in self.corners()]
            p2 = [f * ax + l * ay for f, l in other.corners()]
            if max(p1) <= min(p2) + eps or max(p2) <= min(p1) + eps:
                return False
        return True


def go_footprint(go):
    """(W across the piece, D along its front) of a gameobject: its declared footprint, else its model size."""
    if not isinstance(go, dict):
        return None
    fp = go.get("footprint")
    if isinstance(fp, list) and len(fp) == 2 and all(is_num(v) for v in fp):
        return float(fp[0]), float(fp[1])
    size = go.get("size")
    if isinstance(size, list) and len(size) == 3 and all(is_num(v) for v in size):
        return float(size[0]), float(size[1])
    return None


def cafe_layout(doc, cafe_id):
    """The layout rows of one café in slot order, with the entry resolved for that café. Rows without "cafe" are
    shared; their entry is a number or {"1": entry, "2": entry}."""
    out = []
    for row in doc.get("layout", []):
        if not isinstance(row, dict) or row.get("cafe", cafe_id) != cafe_id:
            continue
        r = dict(row)
        e = row.get("entry", 0)
        if isinstance(e, dict):
            e = e.get(str(cafe_id), 0)
        r["entry"] = e
        r["cafe"] = cafe_id
        out.append(r)
    out.sort(key=lambda r: r.get("slot", 0))
    return out


def station_of(row):
    role = row.get("role", "")
    if role == "counter":
        return "V"
    if role.startswith("station_"):
        return role[-1]
    return ""


def work_spots(row):
    """The station's work spots in the anchor frame, in their listed order."""
    return [to_anchor(row["f"], row["l"], row.get("turn", 0), x, y) for x, y in row.get("work", [])]


def stand_spots(row):
    return [to_anchor(row["f"], row["l"], row.get("turn", 0), x, y) for x, y in row.get("stand", [])]


def piece_box(doc, row):
    gos = by_key(doc.get("gameobjects", []), "entry")
    go = gos.get(row.get("entry"))
    fp = go_footprint(go) if not row.get("creature") else None
    if fp is None:
        return None
    return Box(row["f"], row["l"], fp[1] / 2.0, fp[0] / 2.0, row.get("turn", 0))


def layout_problems(doc, cafe_id):
    """The footprint checks of the default layout (section 3.12.3) for one café."""
    problems = []
    where = "layout (café %d)" % cafe_id
    rows = cafe_layout(doc, cafe_id)
    gos = by_key(doc.get("gameobjects", []), "entry")
    slots = {r["slot"]: r for r in rows if is_int(r.get("slot"))}
    boxes = {}
    for r in rows:
        if r.get("creature") or not r.get("entry"):
            continue
        go = gos.get(r["entry"])
        if go is None:
            continue
        b = piece_box(doc, r)
        if b is None:
            problems.append("%s slot %s: gameobject %s has no footprint (size or footprint)" % (where, r["slot"],
                                                                                              r["entry"]))
            continue
        boxes[r["slot"]] = (b, bool(go.get("decal")))

    def linked(a, b):
        return slots[a].get("link") == b or slots[b].get("link") == a

    solid = sorted(s for s, (b, decal) in boxes.items() if not decal)
    for i, a in enumerate(solid):
        for b in solid[i + 1:]:
            if not linked(a, b) and boxes[a][0].overlaps(boxes[b][0]):
                problems.append("%s: the footprints of slot %d (%s) and slot %d (%s) overlap"
                                % (where, a, slots[a]["role"], b, slots[b]["role"]))
    for s in solid:
        r = slots[s]
        parent = r.get("link")
        if not parent or r["role"].startswith("chair_"):
            continue
        if parent not in boxes:
            problems.append("%s slot %d: linked to slot %s, which has no footprint" % (where, s, parent))
        elif not boxes[parent][0].holds(boxes[s][0]):
            problems.append("%s slot %d (%s): its footprint is not inside its parent's top (slot %d)"
                            % (where, s, r["role"], parent))

    # points: (what, f, l, needs clearance)
    points = []
    spots = {}
    for r in rows:
        st = station_of(r)
        if st:
            spots[st] = work_spots(r)
            for i, (f, l) in enumerate(spots[st]):
                points.append(("station %s work spot %d" % (st, i + 1), f, l, True))
        role = r.get("role", "")
        if r.get("creature"):
            points.append(("%s home" % role, r["f"], r["l"], True))
        elif role in MARKER_ROLES or role.startswith("queue_") or role.startswith("path_"):
            points.append((role, r["f"], r["l"], False))
        if role.startswith("queue_") and r.get("side"):
            points.append(("%s side point" % role, r["f"] + r["side"][0], r["l"] + r["side"][1], False))
        for i, (f, l) in enumerate(stand_spots(r)):
            points.append(("%s stand spot %d" % (role, i + 1), f, l, False))
    for what, f, l, clear in points:
        for s in solid:
            b = boxes[s][0]
            if b.contains(f, l):
                problems.append("%s: the %s (%.2f, %.2f) stands inside the footprint of slot %d (%s)"
                                % (where, what, f, l, s, slots[s]["role"]))
            elif clear and b.distance(f, l) < CLEARANCE - EPS:
                problems.append("%s: the %s (%.2f, %.2f) is %.2f yd from slot %d (%s), less than %.1f"
                                % (where, what, f, l, b.distance(f, l), s, slots[s]["role"], CLEARANCE))

    for st in STATION_ORDER:
        if st not in spots:
            problems.append("%s: no station %s" % (where, st))
        elif len(spots[st]) != 2:
            problems.append("%s: station %s needs exactly two work spots" % (where, st))
        elif abs(math.dist(*spots[st]) - SPOT_GAP) > 0.01:
            problems.append("%s: the work spots of station %s are %.2f yd apart, not %.1f"
                            % (where, st, math.dist(*spots[st]), SPOT_GAP))
    names = [s for s in STATION_ORDER if len(spots.get(s, ())) == 2]
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            first = math.dist(spots[a][0], spots[b][0])
            ca = ((spots[a][0][0] + spots[a][1][0]) / 2, (spots[a][0][1] + spots[a][1][1]) / 2)
            cb = ((spots[b][0][0] + spots[b][1][0]) / 2, (spots[b][0][1] + spots[b][1][1]) / 2)
            if first < FIRST_SPOT_MIN - EPS:
                problems.append("%s: the first work spots of stations %s and %s are %.2f yd apart, less than %.1f"
                                % (where, a, b, first, FIRST_SPOT_MIN))
            if math.dist(ca, cb) < FIRST_SPOT_MIN - EPS:
                problems.append("%s: the work spots of stations %s and %s are centred %.2f yd apart, less than %.1f"
                                % (where, a, b, math.dist(ca, cb), FIRST_SPOT_MIN))
            near = min(math.dist(p, q) for p in spots[a] for q in spots[b])
            if near < ANY_SPOT_MIN - EPS:
                problems.append("%s: work spots of stations %s and %s are %.2f yd apart, less than %.1f"
                                % (where, a, b, near, ANY_SPOT_MIN))
    for r in rows:
        if not r.get("creature"):
            continue
        for st, sp in spots.items():
            for f, l in sp:
                d = math.dist((r["f"], r["l"]), (f, l))
                if d < STAFF_SPOT_MIN - EPS:
                    problems.append("%s: the %s home is %.2f yd from a work spot of station %s, less than %.1f"
                                    % (where, r["role"], d, st, STAFF_SPOT_MIN))
    for r in rows:
        if r.get("role") == "door" and math.hypot(r["f"], r["l"]) < DOOR_MIN - EPS:
            problems.append("%s: the door is %.1f yd from the anchor, less than %.0f"
                            % (where, math.hypot(r["f"], r["l"]), DOOR_MIN))
    return problems


# ---------------------------------------------------------------------------------------------- validation

def validate(doc):
    """Every problem of a parsed cafe.json (empty when it is valid)."""
    if not isinstance(doc, dict):
        return ["cafe.json must be a JSON object"]
    problems = []
    top = ("version", "ids", "cafes", "families", "stations", "actions", "recipes", "tiers", "levels", "staff",
           "personas", "linePools", "layout", "seating", "counterCup", "gameobjects", "items", "npcText", "spellIds",
           "dbc")
    _fields(problems, "cafe.json", doc, top)
    if problems:
        return problems
    if doc["version"] != 1:
        problems.append("version must be 1")
    _check_ids(problems, doc)
    for check in (_check_cafes, _check_stations, _check_actions, _check_recipes, _check_levels, _check_staff,
                  _check_personas, _check_pools, _check_gameobjects, _check_layout, _check_items, _check_npc_text,
                  _check_dbc):
        try:
            check(problems, doc)
        except (KeyError, TypeError, ValueError, AttributeError, IndexError) as ex:
            problems.append("%s: malformed entry (%s: %s)" % (check.__name__[7:], type(ex).__name__, ex))
    return problems


def _check_ids(problems, doc):
    ids = doc["ids"]
    want = ("spells", "displays", "icons", "titles", "titleMasks", "gameobjects", "creatures", "items", "npcText")
    _fields(problems, "ids", ids, want)
    for k in want:
        v = ids.get(k)
        if not (isinstance(v, list) and len(v) == 2 and all(is_int(x) for x in v) and v[0] <= v[1]):
            problems.append("ids.%s: must be [first, last]" % k)
    fixed = {"spells": [100900, 100959], "displays": [19300, 19339], "icons": [19300, 19319], "titles": [190, 191],
             "titleMasks": [160, 161], "gameobjects": [909300, 909379], "creatures": [909300, 909379],
             "items": [909380, 909389], "npcText": [909300, 909319]}
    for k, v in fixed.items():
        if ids.get(k) != v:
            problems.append("ids.%s must be %s (the id registry; the server's startup checks and the uninstall "
                            "use these blocks)" % (k, v))


def _check_cafes(problems, doc):
    cafes = doc["cafes"]
    if [c.get("id") for c in cafes] != [1, 2]:
        problems.append("cafes: must be café 1 (Stormwind) and café 2 (Orgrimmar), in that order")
        return
    staff = by_key(doc["staff"], "entry")
    gos = by_key(doc["gameobjects"], "entry")
    items = by_key(doc["items"], "entry")
    texts = by_key(doc["npcText"], "id")
    spells = {w["spell"]["id"] for w in doc["dbc"]["spells"]
              if isinstance(w, dict) and isinstance(w.get("spell"), dict)}
    want = {1: ("sw", "A", 0, 1519, 12, "A"), 2: ("org", "H", 1, 1637, 29, "H")}
    for c in cafes:
        where = "café %d" % c["id"]
        _fields(problems, where, c, ("id", "name", "city", "cityName", "team", "map", "zone", "owner", "head",
                                     "busser", "faction", "tagline", "trim", "trimMetal", "linePool", "childPool",
                                     "cups", "tableCups", "buffs", "aprons", "npcText", "serverFirst"))
        city, team, mapid, zone, faction, pool = want[c["id"]]
        if (c.get("city"), c.get("team"), c.get("map"), c.get("zone"), c.get("faction"), c.get("linePool")) != \
                (city, team, mapid, zone, faction, pool):
            problems.append("%s: city, team, map, zone, faction and linePool must be %s"
                            % (where, (city, team, mapid, zone, faction, pool)))
        _text(problems, where + ".name", c.get("name"), NAME_BYTES)
        _text(problems, where + ".cityName", c.get("cityName"), NAME_BYTES)
        _text(problems, where + ".tagline", c.get("tagline"), LINE_BYTES)
        if not HEX6.match(str(c.get("trim"))):
            problems.append("%s.trim: must be six upper-case hex digits" % where)
        for role, key in (("staff_owner", "owner"), ("staff_head", "head"), ("staff_busser", "busser")):
            s = staff.get(c.get(key))
            if not s or s.get("cafe") != c["id"] or s.get("role") != role:
                problems.append("%s.%s: %r is not this café's %s" % (where, key, c.get(key), role))
        if c.get("childPool") != "K":
            problems.append("%s.childPool: must be K" % where)
        cups = c.get("cups", {})
        if set(cups) != {"C", "T", "M", "T5", "starleaf"} or not all(is_int(v) and v > 0 for v in cups.values()):
            problems.append("%s.cups: needs item ids for C, T, M, T5 and starleaf" % where)
        tc = c.get("tableCups", {})
        if set(tc) != set(FAMILIES) or not all(v in gos for v in tc.values()):
            problems.append("%s.tableCups: needs a café gameobject for C, T and M" % where)
        b = c.get("buffs", {})
        if set(b) != set(FAMILIES) or not all(v in spells for v in b.values()):
            problems.append("%s.buffs: needs a café spell for C, T and M" % where)
        ap = c.get("aprons", {})
        if set(ap) != {"apprentice", "master", "golden"} or not all(v in items for v in ap.values()):
            problems.append("%s.aprons: needs items for apprentice, master and golden" % where)
        nt = c.get("npcText", {})
        if set(nt) != {"greeting", "help", "menu", "board", "refuse"} or not all(v in texts for v in nt.values()):
            problems.append("%s.npcText: needs npc_text ids for greeting, help, menu, board and refuse" % where)
        sf = c.get("serverFirst", {})
        if not isinstance(sf, dict) or sf.get("key") != "cafe_master_%d" % c["id"]:
            problems.append("%s.serverFirst.key: must be cafe_master_%d" % (where, c["id"]))
        else:
            _text(problems, where + ".serverFirst.text", sf.get("text"), LINE_BYTES)
    fams = doc["families"]
    if [f.get("id") for f in fams] != list(FAMILIES):
        problems.append("families: must be C, T and M, in that order")
    for f in fams:
        _fields(problems, "family %s" % f.get("id"), f, ("id", "name", "buff", "color", "glyph"))
        if f.get("glyph") not in GLYPHS:
            problems.append("family %s: unknown glyph %r" % (f.get("id"), f.get("glyph")))
        if not HEX6.match(str(f.get("color"))):
            problems.append("family %s: color must be six upper-case hex digits" % f.get("id"))
    sid = doc["spellIds"]
    want_ids = {"shift": 100900, "stepBase": 100900, "coffee": [c["buffs"]["C"] for c in cafes],
                "tea": [c["buffs"]["T"] for c in cafes], "shake": [c["buffs"]["M"] for c in cafes],
                "sprint": 100936, "tired": 100937, "crown": 100938}
    if sid != want_ids:
        problems.append("spellIds: must be %s (the cafés' buffs and the fixed spell ids)" % json.dumps(want_ids))


def _check_stations(problems, doc):
    st = doc["stations"]
    if [s.get("id") for s in st] != list(STATION_ORDER):
        problems.append("stations: must be %s, in that order" % " ".join(STATION_ORDER))
    icons = {i.get("id") for i in doc["dbc"]["icons"]}
    for s in st:
        where = "station %s" % s.get("id")
        _fields(problems, where, s, ("id", "name", "names", "glyph", "icon", "visual"))
        _text(problems, where + ".name", s.get("name"), NAME_BYTES)
        names = s.get("names", {})
        if set(names) != {"1", "2"}:
            problems.append("%s.names: needs the names of café 1 and café 2" % where)
        for k, v in names.items():
            _text(problems, "%s.names.%s" % (where, k), v, min(NAME_BYTES, GO_NAME_BYTES))
        if s.get("glyph") not in GLYPHS:
            problems.append("%s: unknown glyph %r" % (where, s.get("glyph")))
        if s.get("icon") not in icons:
            problems.append("%s: icon %r is not a café SpellIcon (dbc.icons)" % (where, s.get("icon")))
        if not is_int(s.get("visual")) or s["visual"] <= 0 or s["visual"] == NEVER_VISUAL:
            problems.append("%s: visual must be a SpellVisual id, never 0 or %d" % (where, NEVER_VISUAL))


def _check_actions(problems, doc):
    acts = doc["actions"]
    stations = by_key(doc["stations"], "id")
    ids = [a.get("id") for a in acts]
    if ids != list(range(1, len(acts) + 1)) or len(acts) > MAX_ACTION_ID:
        problems.append("actions: ids must run 1..n without gaps (n <= %d)" % MAX_ACTION_ID)
    keys = set()
    for a in acts:
        where = "action %s" % a.get("id")
        _fields(problems, where, a, ("id", "station", "key", "kind", "durMs", "name", "hordeName", "emote", "spell",
                                     "visual", "icon", "glyph"), ("gold",))
        s = stations.get(a.get("station"))
        if s is None:
            problems.append("%s: unknown station %r" % (where, a.get("station")))
            continue
        if not is_int(a.get("key")) or not 1 <= a["key"] <= 8 or (a["station"], a["key"]) in keys:
            problems.append("%s: key must be 1..8 and unique at station %s" % (where, a["station"]))
        keys.add((a["station"], a.get("key")))
        if a.get("kind") not in ("T", "H"):
            problems.append("%s: kind must be T (tap) or H (timed)" % where)
        dur = a.get("durMs")
        if not is_int(dur) or not 100 <= dur <= 60000:
            problems.append("%s: durMs must be 100..60000" % where)
            continue
        gold = a.get("gold")
        if a.get("kind") == "H":
            if not (isinstance(gold, list) and len(gold) == 2 and all(is_int(g) for g in gold)):
                problems.append("%s: a timed action needs gold [lo, hi] in permille" % where)
            else:
                lo, hi = gold
                if not GOLD_CLAMP[0] + GOLD_SHIFT <= lo < hi <= GOLD_CLAMP[1] - GOLD_SHIFT:
                    problems.append("%s: gold %s must lie inside [%d, %d] permille so the +-5%% shift never "
                                    "clamps it" % (where, gold, GOLD_CLAMP[0] + GOLD_SHIFT,
                                                   GOLD_CLAMP[1] - GOLD_SHIFT))
                if (hi - lo) * dur < GOLD_MIN_MS * 1000:
                    problems.append("%s: the gold zone is %d ms wide, less than %d"
                                    % (where, (hi - lo) * dur // 1000, GOLD_MIN_MS))
        elif gold is not None:
            problems.append("%s: only a timed action has a gold zone" % where)
        _text(problems, where + ".name", a.get("name"), NAME_BYTES)
        _text(problems, where + ".hordeName", a.get("hordeName"), NAME_BYTES, allow_empty=True)
        em = a.get("emote")
        if not (isinstance(em, dict) and len(em) == 1 and (em.get("state") in EMOTE_STATES
                                                            or em.get("oneshot") in EMOTE_ONESHOTS)):
            problems.append("%s: emote must be {\"state\": loop} or {\"oneshot\": emote} of a known emote" % where)
        if a.get("spell") != STEP_SPELL_BASE + a.get("id", 0):
            problems.append("%s: spell must be %d + the action id" % (where, STEP_SPELL_BASE))
        if a.get("visual") != s.get("visual") or a.get("icon") != s.get("icon"):
            problems.append("%s: visual and icon must be its station's" % where)
        if a.get("glyph") not in GLYPHS:
            problems.append("%s: unknown glyph %r" % (where, a.get("glyph")))
    for want in (TAKE, SERVE, BIN):
        a = next((x for x in acts if x.get("id") == want), None)
        if not a or a.get("station") != "V":
            problems.append("actions: %d (Take Order, Serve, Bin) must be counter actions" % want)


def _check_recipes(problems, doc):
    recs = doc["recipes"]
    acts = by_key(doc["actions"], "id")
    if [r.get("n") for r in recs] != list(range(1, len(ARCHETYPES) + 1)):
        problems.append("recipes: n must run 1..%d" % len(ARCHETYPES))
    names = {"1": set(), "2": set()}
    for r in recs:
        where = "recipe %s" % r.get("arch")
        _fields(problems, where, r, ("n", "arch", "family", "tier", "unlock", "steps", "names"))
        n = r.get("n")
        if not is_int(n) or not 1 <= n <= len(ARCHETYPES) or r.get("arch") != ARCHETYPES[n - 1]:
            problems.append("%s: arch must be %s for n %s (C1-C7 = 1-7, T1-T6 = 8-13, M1-M6 = 14-19)"
                            % (where, ARCHETYPES[n - 1] if is_int(n) and 1 <= n <= 19 else "?", n))
        if r.get("family") != str(r.get("arch"))[:1]:
            problems.append("%s: family must be the archetype's letter" % where)
        if r.get("tier") not in TIERS:
            problems.append("%s: tier must be 1..5" % where)
        if r.get("unlock") not in LEVELS or r.get("arch") not in LEVELS[r.get("unlock")][2]:
            problems.append("%s: unlock %r is not the barista level that unlocks it" % (where, r.get("unlock")))
        steps = r.get("steps")
        if not (isinstance(steps, list) and steps and all(is_int(s) for s in steps)):
            problems.append("%s: steps must be a list of action ids" % where)
            continue
        if len(steps) > MAX_STEPS:
            problems.append("%s: %d steps, more than %d" % (where, len(steps), MAX_STEPS))
        if any(s not in acts for s in steps):
            problems.append("%s: unknown action in steps %s" % (where, steps))
            continue
        if steps[-1] != SERVE or SERVE in steps[:-1] or TAKE in steps or BIN in steps:
            problems.append("%s: steps must end with Serve (%d) and hold no other counter action" % (where, SERVE))
        if not any(acts[s].get("kind") == "H" for s in steps):
            problems.append("%s: needs at least one timed step" % where)
        nm = r.get("names", {})
        if set(nm) != {"1", "2"}:
            problems.append("%s.names: needs the [name, text] of café 1 and café 2" % where)
            continue
        for k, v in nm.items():
            if not (isinstance(v, list) and len(v) == 2):
                problems.append("%s.names.%s: must be [name, text]" % (where, k))
                continue
            _text(problems, "%s.names.%s name" % (where, k), v[0], NAME_BYTES)
            _text(problems, "%s.names.%s text" % (where, k), v[1], LINE_BYTES)
            if v[0] in names[k]:
                problems.append("%s.names.%s: the name %r is used twice in café %s" % (where, k, v[0], k))
            names[k].add(v[0])
    tiers = doc["tiers"]
    if set(tiers) != {str(t) for t in TIERS}:
        problems.append("tiers: must be 1..5")
    for t, want in TIERS.items():
        if tiers.get(str(t)) != want:
            problems.append("tiers.%d: must be %s (sections 2.5 and 2.9)" % (t, json.dumps(want)))


def _check_levels(problems, doc):
    levels = doc["levels"]
    if [lv.get("level") for lv in levels] != list(LEVELS):
        problems.append("levels: must be 1..10")
        return
    for lv in levels:
        where = "level %d" % lv["level"]
        _fields(problems, where, lv, ("level", "xp", "tickets", "rewards", "text"))
        xp, tickets, _ = LEVELS[lv["level"]]
        if lv.get("xp") != xp or lv.get("tickets") != tickets:
            problems.append("%s: total XP %d and %d tickets (section 2.8)" % (where, xp, tickets))
        _text(problems, where + ".text", lv.get("text"), LINE_BYTES)
        rw = lv.get("rewards", [])
        if not isinstance(rw, list) or any(x not in LEVEL_REWARDS for x in rw):
            problems.append("%s.rewards: unknown reward in %s" % (where, rw))
    want = {"tutorial": 1, "apprenticeApron": 5, "memory": 6, "staffDrink": 7, "regulars": 9, "title": 10,
            "masterApron": 10, "serverFirst": 10}
    got = {x: lv["level"] for lv in levels for x in lv.get("rewards", [])}
    if got != want:
        problems.append("levels: rewards must be %s (section 2.8)" % json.dumps(want))


def _gender_problems(problems, where, display, gender):
    if gender not in ("m", "f"):
        problems.append("%s: gender must be \"m\" or \"f\"" % where)
    elif display in DISPLAY_GENDER and DISPLAY_GENDER[display][1] != gender:
        problems.append("%s: gender %r does not match display %d (%s %s)"
                        % (where, gender, display, DISPLAY_GENDER[display][0], DISPLAY_GENDER[display][1]))


def _race_of(display):
    if display in DISPLAY_GENDER:
        return DISPLAY_GENDER[display][0]
    return DISPLAY_RACE.get(display)


def _check_staff(problems, doc):
    staff = doc["staff"]
    seen = set()
    for s in staff:
        where = "staff %s (%s)" % (s.get("entry"), s.get("name"))
        _fields(problems, where, s, ("entry", "cafe", "name", "subname", "role", "displays", "gender", "race",
                                     "faction", "npcflag", "script", "emote", "level", "lines"), ("house",))
        _in_block(problems, doc, "creatures", s.get("entry"), where)
        if s.get("entry") in seen:
            problems.append("%s: entry used twice" % where)
        seen.add(s.get("entry"))
        cafe = s.get("cafe")
        if cafe not in (1, 2):
            problems.append("%s: cafe must be 1 or 2" % where)
            continue
        _text(problems, where + ".name", s.get("name"), min(NAME_BYTES, CREATURE_NAME_BYTES))
        _text(problems, where + ".subname", s.get("subname"), CREATURE_NAME_BYTES)
        if s.get("role") not in STAFF_ROLES:
            problems.append("%s: role must be one of %s" % (where, ", ".join(STAFF_ROLES)))
        d = s.get("displays")
        if not (isinstance(d, list) and len(d) == 1 and is_int(d[0]) and d[0] > 0):
            problems.append("%s: staff have exactly one fixed display" % where)
            continue
        _gender_problems(problems, where, d[0], s.get("gender"))
        race = s.get("race")
        if race not in RACES:
            problems.append("%s: unknown race %r" % (where, race))
        if _race_of(d[0]) and _race_of(d[0]) != race:
            problems.append("%s: race %r does not match display %d (%s)" % (where, race, d[0], _race_of(d[0])))
        if cafe == 1 and (race != "human" or _race_of(d[0]) not in (None, "human")):
            problems.append("%s: The Lion's Roast's staff are all human" % where)
        owner = s.get("role") == "staff_owner"
        head = s.get("role") == "staff_head"
        # the gossip staff talk to both teams (the other one hears the refusal: the core never lets a player talk to
        # a creature that is unfriendly to it); the others wear their city's faction
        want_faction = 35 if owner or head else {1: 12, 2: 29}[cafe]
        if s.get("faction") != want_faction:
            problems.append("%s: faction must be %d" % (where, want_faction))
        want_script = "npc_bh_cafe_owner" if owner else "npc_bh_cafe_staff" if head else ""
        if s.get("script") != want_script or s.get("npcflag") != (1 if owner or head else 0):
            problems.append("%s: script %r and npcflag %d" % (where, want_script, 1 if owner or head else 0))
        if (owner or head) != ("house" in s) or (owner and s.get("house") != 1) or (head and s.get("house") != 2):
            problems.append("%s: house worker 1 is the owner, 2 the head barista; nobody else" % where)
        if s.get("emote") not in (0, 69, 173):
            problems.append("%s: emote must be 0, 69 or 173" % where)
        if not is_int(s.get("level")) or not 1 <= s["level"] <= 80:
            problems.append("%s: level must be 1..80" % where)
        lines = s.get("lines", {})
        if not isinstance(lines, dict):
            problems.append("%s.lines: must be an object" % where)
            continue
        for k, v in lines.items():
            if k not in STAFF_LINES:
                problems.append("%s.lines: unknown line %r" % (where, k))
                continue
            for i, t in enumerate(v if isinstance(v, list) else [v]):
                _text(problems, "%s.lines.%s[%d]" % (where, k, i), t, LINE_BYTES, placeholders=STAFF_LINES[k])
        need = OWNER_LINES if owner else HEAD_LINES if head else ()
        for k in need:
            if k not in lines:
                problems.append("%s.lines: missing %r" % (where, k))
        if s.get("role") == "staff_busser" and "tableService" not in lines:
            problems.append("%s.lines: the busser needs tableService" % where)
    for cafe in (1, 2):
        roles = [s.get("role") for s in staff if s.get("cafe") == cafe]
        for r in ("staff_owner", "staff_head", "staff_busser"):
            if roles.count(r) != 1:
                problems.append("staff: café %d needs exactly one %s" % (cafe, r))
        if len(roles) != len(set(roles)):
            problems.append("staff: café %d has two staff members with the same role" % cafe)


def _check_personas(problems, doc):
    personas = doc["personas"]
    staff = {s.get("entry") for s in doc["staff"]}
    pools = doc["linePools"]
    seen = set()
    for p in personas:
        where = "persona %s (%s)" % (p.get("entry"), p.get("name"))
        _fields(problems, where, p, ("entry", "cafe", "name", "kind", "child", "displays", "fav", "patience", "tip",
                                     "level", "enabled"),
                ("gender", "race", "pool", "order", "thanks", "complaint", "groupSize", "templateDisplay"))
        _in_block(problems, doc, "creatures", p.get("entry"), where)
        if p.get("entry") in seen or p.get("entry") in staff:
            problems.append("%s: entry used twice" % where)
        seen.add(p.get("entry"))
        cafe, kind = p.get("cafe"), p.get("kind")
        if cafe not in (1, 2) or kind not in PERSONA_KINDS:
            problems.append("%s: cafe must be 1 or 2 and kind one of %s" % (where, ", ".join(PERSONA_KINDS)))
            continue
        _text(problems, where + ".name", p.get("name"), min(NAME_BYTES, CREATURE_NAME_BYTES))
        child = p.get("child")
        if not isinstance(child, bool) or (kind == "child" and not child) or (kind in ("generic", "group") and child):
            problems.append("%s: child must be true for kind child (and may be for a named child), false otherwise"
                            % where)
        if not isinstance(p.get("enabled"), bool):
            problems.append("%s: enabled must be true or false" % where)
        d = p.get("displays")
        if not (isinstance(d, list) and d and all(is_int(x) and x >= 0 for x in d)):
            problems.append("%s: displays must be a non-empty list of display ids" % where)
            continue
        if len(set(d)) != len(d):
            problems.append("%s: a display is listed twice" % where)
        if 0 in d:
            if d != [0] or p.get("enabled") or kind != "named" or not is_int(p.get("templateDisplay")):
                problems.append("%s: display 0 (none yet) only as the single display of a disabled named persona "
                                "with a templateDisplay" % where)
        elif "templateDisplay" in p:
            problems.append("%s: templateDisplay is only for a persona with display 0" % where)
        race = p.get("race")
        if race is not None and race not in RACES:
            problems.append("%s: unknown race %r" % (where, race))
        if kind == "named":
            _gender_problems(problems, where, d[0], p.get("gender"))
            if race is None:
                problems.append("%s: a named persona needs a race" % where)
            if _race_of(d[0]) and race and _race_of(d[0]) != race:
                problems.append("%s: race %r does not match display %d (%s)" % (where, race, d[0], _race_of(d[0])))
        elif "gender" in p:
            problems.append("%s: only named personas carry a gender (the others pick a random display)" % where)
        if cafe == 1 and (race == "goblin" or any(_race_of(x) == "goblin" for x in d)):
            problems.append("%s: no goblins at The Lion's Roast" % where)
        fav = p.get("fav")
        if not isinstance(fav, list) or any(f not in ARCHETYPES for f in fav):
            problems.append("%s: fav must be a list of archetype codes" % where)
        elif kind == "group":
            if p.get("groupSize") != GROUP_SIZE or len(fav) != GROUP_SIZE:
                problems.append("%s: a Rush group has groupSize %d and one favourite per member" % (where, GROUP_SIZE))
        else:
            if "groupSize" in p:
                problems.append("%s: only a Rush group (kind group) has a groupSize" % where)
            if kind == "named" and not fav:
                problems.append("%s: a named persona needs at least one favourite" % where)
            if len(fav) != len(set(fav)) or len(fav) > 3:
                problems.append("%s: at most 3 different favourites" % where)
        if child and fav and any(not f.startswith("M") for f in fav):
            problems.append("%s: children only order milkshakes" % where)
        if not is_int(p.get("patience")) or not 50 <= p["patience"] <= 200:
            problems.append("%s: patience must be 50..200 (percent)" % where)
        if not is_int(p.get("tip")) or not 0 <= p["tip"] <= 200:
            problems.append("%s: tip must be 0..200 (percent)" % where)
        lv = p.get("level")
        if not (isinstance(lv, list) and len(lv) == 2 and all(is_int(x) for x in lv) and 1 <= lv[0] <= lv[1] <= 80):
            problems.append("%s: level must be [min, max] in 1..80" % where)
        own = [k for k in ("order", "thanks", "complaint") if k in p]
        if kind in ("named", "group"):
            if len(own) != 3:
                problems.append("%s: a %s persona has its own order, thanks and complaint lines" % (where, kind))
            for k in own:
                _text(problems, "%s.%s" % (where, k), p[k], LINE_BYTES)
        elif own:
            problems.append("%s: a %s persona takes its lines from its pool" % (where, kind))
        pool = p.get("pool")
        want_pool = {"named": None, "group": {1: "A", 2: "H"}[cafe], "generic": {1: "A", 2: "H"}[cafe], "child": "K"}
        if pool != want_pool[kind] or (pool is not None and pool not in pools):
            problems.append("%s: pool must be %r" % (where, want_pool[kind]))
    for cafe in (1, 2):
        kinds = [p.get("kind") for p in personas if p.get("cafe") == cafe]
        for k, n in (("generic", 1), ("child", 1)):
            if kinds.count(k) != n:
                problems.append("personas: café %d needs exactly %d %s persona" % (cafe, n, k))
        if kinds.count("group") < 1:
            problems.append("personas: café %d needs a Rush group" % cafe)
        if kinds.count("named") < 10:
            problems.append("personas: café %d needs at least 10 named personas" % cafe)


def _longest_drink(doc, cafe):
    return max((r["names"][str(cafe)][0] for r in doc["recipes"]), key=nbytes)


def _check_pools(problems, doc):
    pools = doc["linePools"]
    if set(pools) != {"A", "H", "K"}:
        problems.append("linePools: must be A (Alliance adult), H (Horde adult) and K (child)")
    longest = max((_longest_drink(doc, c) for c in (1, 2)), key=nbytes)
    for name, pool in pools.items():
        where = "linePools.%s" % name
        if not _fields(problems, where, pool, ("order", "thanks", "complaint")):
            continue
        for k in ("order", "thanks", "complaint"):
            lines = pool.get(k)
            if not (isinstance(lines, list) and lines):
                problems.append("%s.%s: must be a non-empty list" % (where, k))
                continue
            for i, t in enumerate(lines):
                ph = ("{drink}",) if k == "order" else ()
                _text(problems, "%s.%s[%d]" % (where, k, i), t, LINE_BYTES, placeholders=ph)
                if k == "order" and isinstance(t, str):
                    if t.count("{drink}") != 1:
                        problems.append("%s.order[%d]: must name {drink} once" % (where, i))
                    elif nbytes(t.replace("{drink}", longest)) > LINE_BYTES:
                        problems.append("%s.order[%d]: too long with the longest drink name" % (where, i))
    for s in doc["staff"]:
        for k, ph, value in (("tableService", "{drink}", None), ("levelUp", "{n}", "10")):
            t = s.get("lines", {}).get(k)
            if isinstance(t, str):
                v = value or _longest_drink(doc, s.get("cafe", 1))
                if t.count(ph) != 1:
                    problems.append("staff %s.lines.%s: must hold %s once" % (s.get("entry"), k, ph))
                elif nbytes(t.replace(ph, v)) > LINE_BYTES:
                    problems.append("staff %s.lines.%s: too long once %s is filled in" % (s.get("entry"), k, ph))


def _check_gameobjects(problems, doc):
    gos = doc["gameobjects"]
    seen = set()
    stand_ins = set()
    for g in gos:
        where = "gameobject %s (%s)" % (g.get("entry"), g.get("name"))
        new_art = "model" in g
        if new_art:
            _fields(problems, where, g, ("entry", "type", "display", "model", "name", "scale", "size", "data", "flags",
                                         "customAnims", "standin"), ("footprint", "topHeight", "modelFrame"))
        else:
            _fields(problems, where, g, ("entry", "type", "display", "name", "scale", "data", "flags"),
                    ("footprint", "topHeight", "decal", "marker"))
        e = g.get("entry")
        _in_block(problems, doc, "gameobjects", e, where)
        if e in seen:
            problems.append("%s: entry used twice" % where)
        seen.add(e)
        _text(problems, where + ".name", g.get("name"), GO_NAME_BYTES)
        if not is_int(g.get("display")) or g["display"] <= 0:
            problems.append("%s: display must be a display id" % where)
        if not is_num(g.get("scale")) or g["scale"] <= 0:
            problems.append("%s: scale must be positive" % where)
        if g.get("type") == 5:
            if g.get("data") != [1, 1]:
                problems.append("%s: a GENERIC gameobject has data [1, 1] (floating tooltip, highlight)" % where)
        elif g.get("type") == 7:
            dt = g.get("data")
            if not (isinstance(dt, list) and len(dt) == 2 and is_int(dt[0]) and is_int(dt[1]) and 1 <= dt[0] <= 5
                    and 0 <= dt[1] <= 6):
                problems.append("%s: a CHAIR has data [slots 1..5, height 0..6]" % where)
        else:
            problems.append("%s: type must be 5 (GENERIC) or 7 (CHAIR)" % where)
        if g.get("flags") != 32:
            problems.append("%s: flags must be 32 (GO_FLAG_NODESPAWN)" % where)
        if "topHeight" in g and (not is_num(g["topHeight"]) or g["topHeight"] <= 0):
            problems.append("%s: topHeight must be positive" % where)
        fp = g.get("footprint")
        if fp is not None and not (isinstance(fp, list) and len(fp) == 2 and all(is_num(v) and v > 0 for v in fp)):
            problems.append("%s: footprint must be [W, D] in yards" % where)
        if new_art:
            if g.get("display") != e - DISPLAY_OFFSET:
                problems.append("%s: a new-art display is its entry - %d" % (where, DISPLAY_OFFSET))
            _in_block(problems, doc, "displays", g.get("display"), where + ".display")
            size = g.get("size")
            if not (isinstance(size, list) and len(size) == 3 and all(is_num(v) and v > 0 for v in size)):
                problems.append("%s: size must be [W, D, H] in yards" % where)
            if not isinstance(g.get("model"), str) or not re.match(r"^[A-Z][A-Za-z]+$", g["model"]):
                problems.append("%s: model must be the ModelForge model name" % where)
            si = g.get("standin")
            if not _fields(problems, where + ".standin", si, ("entry", "display", "scale")):
                continue
            if si.get("entry") != e + STAND_IN_OFFSET:
                problems.append("%s: the stand-in entry is the entry + %d" % (where, STAND_IN_OFFSET))
            if not is_int(si.get("display")) or si["display"] <= 0 or not is_num(si.get("scale")) or si["scale"] <= 0:
                problems.append("%s.standin: needs a stock display and a positive scale" % where)
            stand_ins.add(si.get("entry"))
            mf = g.get("modelFrame")
            if mf is not None and not (isinstance(mf, dict) and set(mf) == {"position", "scale", "facing"}
                                       and isinstance(mf["position"], list) and len(mf["position"]) == 3):
                problems.append("%s.modelFrame: must be {position [x, y, z], scale, facing}" % where)
        else:
            if "marker" in g and not g.get("name", "").startswith("Café marker: " + str(g["marker"])):
                problems.append("%s: a marker's name is \"Café marker: <its role group>\"" % where)
            if "marker" not in g and fp is None:
                problems.append("%s: a stock-display piece needs a declared footprint" % where)
    clash = stand_ins & seen
    if clash:
        problems.append("gameobjects: stand-in entries %s are also listed as gameobjects" % sorted(clash))
    markers = sorted(g["entry"] for g in gos if "marker" in g)
    if markers != [909368, 909369, 909378, 909379]:
        problems.append("gameobjects: the markers are 909368, 909369, 909378 and 909379")
    models = [g.get("model") for g in gos if "model" in g]
    if len(models) != len(set(models)):
        problems.append("gameobjects: a model name is used twice")


def _check_layout(problems, doc):
    gos = by_key(doc["gameobjects"], "entry")
    staff = by_key(doc["staff"], "entry")
    known = ("slot", "cafe", "role", "entry", "f", "l", "u", "turn", "snap", "link", "station", "work", "stand", "side",
             "creature")
    for row in doc["layout"]:
        where = "layout slot %s (%s)" % (row.get("slot"), row.get("role"))
        _fields(problems, where, row, ("slot", "role", "entry", "f", "l", "u", "turn", "snap"),
                [k for k in known if k not in ("slot", "role", "entry", "f", "l", "u", "turn", "snap")])
        if not ROLE_RE.match(str(row.get("role"))):
            problems.append("%s: unknown role" % where)
        if not is_int(row.get("slot")) or not 1 <= row["slot"] < 200:
            problems.append("%s: slot must be 1..199 (200 and up are for .cafe add)" % where)
        if row.get("cafe") not in (None, 1, 2):
            problems.append("%s: cafe must be 1 or 2 (or left out for both)" % where)
        if not all(is_num(row.get(k)) for k in ("f", "l", "u", "turn")) or not isinstance(row.get("snap"), bool):
            problems.append("%s: f, l, u and turn are numbers and snap is true or false" % where)
        st = row.get("station")
        if st is not None and st != station_of(row):
            problems.append("%s: station must be %r" % (where, station_of(row)))
        if station_of(row) and st is None:
            problems.append("%s: a station piece names its station" % where)
        if "work" in row and not (station_of(row) and isinstance(row["work"], list) and len(row["work"]) == 2
                                  and all(isinstance(w, list) and len(w) == 2 and all(is_num(v) for v in w)
                                          for w in row["work"])):
            problems.append("%s: work is two [fwd, side] spots, on a station piece only" % where)
        if "stand" in row and not row["role"].startswith("kegtable_"):
            problems.append("%s: stand spots are for keg tables" % where)
        if "side" in row and not row["role"].startswith("queue_"):
            problems.append("%s: side points are for queue slots" % where)
    for cafe in (1, 2):
        rows = cafe_layout(doc, cafe)
        slots = {}
        for r in rows:
            where = "layout (café %d) slot %s (%s)" % (cafe, r.get("slot"), r.get("role"))
            if r.get("slot") in slots:
                problems.append("%s: slot used twice" % where)
            slots[r.get("slot")] = r
            role, e = r.get("role", ""), r.get("entry")
            if role.startswith("staff_"):
                s = staff.get(e)
                if not r.get("creature") or not s or s.get("cafe") != cafe or s.get("role") != role:
                    problems.append("%s: must be this café's %s creature" % (where, role))
            elif role in MARKER_ROLES or role.startswith("queue_") or role.startswith("path_"):
                if e != 0 or r.get("creature"):
                    problems.append("%s: a marker has entry 0" % where)
            else:
                g = gos.get(e)
                if g is None or "marker" in g or r.get("creature"):
                    problems.append("%s: entry %r is not a café piece" % (where, e))
                elif role.startswith("chair_") and (g.get("type") != 7 or g.get("data", [0])[0] != 1):
                    problems.append("%s: NPCs sit only on 1-slot chairs" % where)
                elif g.get("decal") and role != "decor":
                    problems.append("%s: only decor may be a floor decal" % where)
        roles = {r.get("role") for r in rows}
        need = {"counter", "backbar", "order_spot", "pickup_spot", "door", "staff_owner", "staff_head",
                "staff_busser"} | {"station_" + s for s in STATION_ORDER if s != "V"} | \
               {"queue_%d" % i for i in range(1, 9)} | {"table_%d" % i for i in range(1, 5)} | \
               {"chair_%d" % i for i in range(1, 13)} | {"path_1"}
        for role in sorted(need - roles):
            problems.append("layout (café %d): missing %s" % (cafe, role))
        for r in rows:
            link = r.get("link")
            if link is None:
                continue
            p = slots.get(link)
            role = r.get("role", "")
            if p is None:
                problems.append("layout (café %d) slot %s: link %s is not a slot" % (cafe, r.get("slot"), link))
            elif (role.startswith("chair_") or role.startswith("parasol_")) != p.get("role", "").startswith("table_"):
                problems.append("layout (café %d) slot %s: chairs and parasols link to a table, on-top pieces to the "
                                "counter or the back bar" % (cafe, r.get("slot")))
            elif not role.startswith(("chair_", "parasol_")) and p.get("role") not in ("counter", "backbar"):
                problems.append("layout (café %d) slot %s: on-top pieces link to the counter or the back bar"
                                % (cafe, r.get("slot")))
            if role.startswith("chair_") and p is not None:
                want = math.degrees(math.atan2(p["l"] - r["l"], p["f"] - r["f"]))
                if abs((r["turn"] - want + 180) % 360 - 180) > 0.5:
                    problems.append("layout (café %d) slot %s: a chair faces its table (turn %.0f)"
                                    % (cafe, r.get("slot"), want))
            if link and not role.startswith(("chair_", "parasol_")) and r.get("snap"):
                problems.append("layout (café %d) slot %s: an on-top piece is not ground-snapped" % (cafe, r["slot"]))
        problems.extend(layout_problems(doc, cafe))
    seat = doc["seating"]
    _fields(problems, "seating", seat, ("approach", "tableCup"))
    cup = doc["counterCup"]
    _fields(problems, "counterCup", cup, ("f", "u", "stepL", "max"))
    if not all(is_num(seat.get(k)) and seat[k] > 0 for k in ("approach", "tableCup")):
        problems.append("seating: approach and tableCup are positive distances")
    if not (all(is_num(cup.get(k)) for k in ("f", "u", "stepL")) and is_int(cup.get("max")) and 1 <= cup["max"] <= 6):
        problems.append("counterCup: f, u and stepL are numbers and max is 1..6")
    else:
        for cafe in (1, 2):
            rows = cafe_layout(doc, cafe)
            counter = next((r for r in rows if r.get("role") == "counter"), None)
            pickup = next((r for r in rows if r.get("role") == "pickup_spot"), None)
            if counter and pickup:
                box = piece_box(doc, counter)
                for k in range(cup["max"]):
                    if box and not box.contains(cup["f"], pickup["l"] + k * cup["stepL"]):
                        problems.append("counterCup (café %d): cup %d is not on the counter top" % (cafe, k + 1))


def _check_items(problems, doc):
    seen = set()
    for it in doc["items"]:
        where = "item %s (%s)" % (it.get("entry"), it.get("name"))
        _fields(problems, where, it, ("entry", "cafe", "name", "display", "inventoryType", "quality", "itemLevel",
                                      "description"))
        _in_block(problems, doc, "items", it.get("entry"), where)
        if it.get("entry") in seen:
            problems.append("%s: entry used twice" % where)
        seen.add(it.get("entry"))
        _text(problems, where + ".name", it.get("name"), NAME_BYTES)
        _text(problems, where + ".description", it.get("description"), ITEM_TEXT_BYTES)
        if it.get("inventoryType") != 20:
            problems.append("%s: an apron is a robe (InventoryType 20)" % where)
        if it.get("quality") not in range(0, 6) or not is_int(it.get("itemLevel")) or it["itemLevel"] < 1:
            problems.append("%s: quality 0..5 and itemLevel 1 or more" % where)
        if it.get("cafe") not in (0, 1, 2) or not is_int(it.get("display")) or it["display"] <= 0:
            problems.append("%s: cafe 0..2 and a display id" % where)


def _check_npc_text(problems, doc):
    seen = set()
    for t in doc["npcText"]:
        where = "npcText %s" % t.get("id")
        _fields(problems, where, t, ("id", "cafe", "key", "text"))
        _in_block(problems, doc, "npcText", t.get("id"), where)
        if t.get("id") in seen:
            problems.append("%s: id used twice" % where)
        seen.add(t.get("id"))
        _text(problems, where + ".text", t.get("text"), 1000)


def _check_dbc(problems, doc):
    dbc = doc["dbc"]
    _fields(problems, "dbc", dbc, ("spells", "titles", "icons"))
    icons = by_key(dbc["icons"], "id")
    for i in dbc["icons"]:
        where = "dbc.icons %s" % i.get("id")
        _fields(problems, where, i, ("id", "name", "texture"))
        _in_block(problems, doc, "icons", i.get("id"), where)
        if i.get("texture") != "Interface\\Icons\\BH_Cafe_%s" % i.get("name"):
            problems.append("%s: texture must be Interface\\Icons\\BH_Cafe_<name> (no extension)" % where)
    if len(icons) != len(dbc["icons"]):
        problems.append("dbc.icons: an id is used twice")
    titles = dbc["titles"]
    if [(t.get("id"), t.get("mask")) for t in titles] != [(190, 160), (191, 161)]:
        problems.append("dbc.titles: must be 190 (mask 160) and 191 (mask 161)")
    for t in titles:
        _fields(problems, "dbc.titles %s" % t.get("id"), t, ("id", "name", "mask"))
        _text(problems, "dbc.titles %s.name" % t.get("id"), t.get("name"), 100)
        if isinstance(t.get("name"), str) and t["name"].count("%s") != 1:
            problems.append("dbc.titles %s: the name holds %%s once" % t.get("id"))
    acts = by_key(doc["actions"], "id")
    seen = []
    for w in dbc["spells"]:
        if not _fields(problems, "dbc.spells", w, WRAPPER_KEYS):
            continue
        s = w.get("spell", {})
        where = "dbc spell %s (%s)" % (s.get("id"), s.get("name"))
        _fields(problems, where, s, ("id", "name", "description", "icon", "visual", "cast_by", "text_locales",
                                     "fields"), [k for k in SPELL_KEYS])
        sid = s.get("id")
        _in_block(problems, doc, "spells", sid, where)
        seen.append(sid)
        for k, lim in SPELL_TEXT_BYTES.items():
            if k in s:
                _text(problems, "%s.%s" % (where, k), s[k], lim)
        if s.get("cast_by") != "server" or s.get("text_locales") != ["enUS"]:
            problems.append("%s: cast_by \"server\" and text_locales [\"enUS\"]" % where)
        if s.get("icon") not in icons:
            problems.append("%s: icon %r is not a café SpellIcon" % (where, s.get("icon")))
        if not is_int(s.get("visual")) or s["visual"] < 0 or s["visual"] == NEVER_VISUAL:
            problems.append("%s: visual must be a SpellVisual id or 0, never %d" % (where, NEVER_VISUAL))
        fields = s.get("fields", {})
        if not isinstance(fields, dict):
            problems.append("%s.fields: must be an object" % where)
            fields = {}
        for k, v in fields.items():
            if k not in SPELL_FIELDS:
                problems.append("%s.fields: %r is not a column the café spells set" % (where, k))
            if not is_int(v) or not 0 <= v <= 0xFFFFFFFF:
                problems.append("%s.fields.%s: must be a 32-bit whole number" % (where, k))
        if w.get("range") != "self":
            problems.append("%s: range must be \"self\"" % where)
        cast, dur = w.get("castMs"), w.get("durationMs")
        if not is_int(cast) or cast < 0 or not is_int(dur) or dur < -1:
            problems.append("%s: castMs >= 0 and durationMs >= -1 (-1 is infinite)" % where)
            continue
        a = acts.get(sid - STEP_SPELL_BASE) if is_int(sid) else None
        if a is not None and sid != STEP_SPELL_BASE:
            timed = a.get("kind") == "H"
            if s.get("name") is None or s.get("visual") != a.get("visual") or s.get("icon") != a.get("icon"):
                problems.append("%s: a step spell carries its action's visual and icon" % where)
            if s.get("visual") == 0:
                problems.append("%s: a step spell needs a visual (a triggered cast without one is never sent)" % where)
            if timed and (cast != 0 or dur != a.get("durMs") or not fields.get("attributesEx", 0) & A1_CHANNEL):
                problems.append("%s: a timed step is a channel: castMs 0, durationMs = durMs, attributesEx 0x4" % where)
            if not timed and (cast != a.get("durMs") or dur != 0 or fields.get("attributesEx", 0) & A1_CHANNEL):
                problems.append("%s: a tap step is a cast: castMs = durMs, durationMs 0" % where)
            if not fields.get("attributesExD", 0) & A4_BAR or fields.get("effect[0]") != 3:
                problems.append("%s: a step spell is a DUMMY (effect 3) with the forced cast bar (attributesExD "
                                "0x08000000)" % where)
        elif fields.get("effect[0]") != 6 or cast != 0:
            problems.append("%s: an aura spell applies an aura (effect 6) instantly" % where)
    if sorted(x for x in seen if is_int(x)) != CAFE_SPELLS or len(seen) != len(set(seen)):
        problems.append("dbc.spells: must be 100900, the step spells 100901-100926 and 100930-100938, once each")
    want_icons = {s.get("icon") for s in doc["stations"]} | {w["spell"].get("icon") for w in dbc["spells"]
                                                            if isinstance(w, dict) and "spell" in w}
    missing = sorted(i for i in want_icons if i not in icons)
    if missing:
        problems.append("dbc.icons: missing %s" % missing)


# --------------------------------------------------------------------------------------- ModelForge cross-check

def modelforge_catalogue(repo):
    """ModelForge's section 5.8 table (Tools/ModelForge/mflib/props/__init__.py CATALOGUE) as {display: (name,
    size)}, read without importing ModelForge; None when it is not there."""
    import ast
    path = os.path.join(repo, "Tools", "ModelForge", "mflib", "props", "__init__.py")
    try:
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read(), path)
    except (OSError, SyntaxError):
        return None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "CATALOGUE" for t in node.targets):
            rows = ast.literal_eval(node.value)
            return {disp: (name, tuple(float(v) for v in size)) for name, disp, size, _budget in rows}
    return None


def modelforge_problems(doc, catalogue):
    """Every new-art gameobject's model and size against ModelForge's table: ModelForge's tests hold every built
    model to cafe.json's size, so the two must agree."""
    problems = []
    seen = set()
    for g in doc.get("gameobjects", []):
        if "model" not in g:
            continue
        seen.add(g.get("display"))
        want = catalogue.get(g.get("display"))
        if want is None:
            problems.append("gameobject %s: display %s is not in ModelForge's table"
                            % (g.get("entry"), g.get("display")))
            continue
        name, size = want
        if g.get("model") != name:
            problems.append("gameobject %s: model %r, ModelForge calls display %d %r"
                            % (g.get("entry"), g.get("model"), g["display"], name))
        if tuple(float(v) for v in g.get("size", ())) != size:
            problems.append("gameobject %s (%s): size %s, ModelForge's table says %s"
                            % (g.get("entry"), name, g.get("size"), list(size)))
    for disp in sorted(set(catalogue) - seen):
        problems.append("ModelForge model %s (display %d) has no gameobject" % (catalogue[disp][0], disp))
    return problems
