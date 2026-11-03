"""CafeForge's packaging config: the café's DBC rows (cafe.json `dbc`, section 6.3), their archive and the
launcher's optional packs.

cafe.json holds the rows; cflib/catalog.py validates them with the rest of the catalogue:
- `dbc.spells`: RaceForge SpellDef objects (Tools/RaceForge/rflib/config.py parse_spell) inside a café-only wrapper,
  {"spell": {...}, "castMs": n, "durationMs": n, "range": "self"}. cflib/dbcrows.py resolves the three wrapper keys
  to castingTimeIndex, durationIndex and rangeIndex from the winning SpellCastTimes, SpellDuration and SpellRange
  copies, writes them into the spell's fields and only then calls parse_spell, so the SpellDef is RaceForge's own and
  RaceForge's spells.build_row builds the row. parse_wrapper() checks a wrapper as far as it can without those
  copies: its own keys, then parse_spell and the Spell.dbc columns of its fields;
- `dbc.titles`: CharTitles {id, name, mask};
- `dbc.icons`: SpellIcon {id, texture}.
The GameObjectDisplayInfo rows belong to the new-art gameobjects (display = entry - 890000). Their model paths follow
ModelForge's output tree (Tools/ModelForge/mflib/props CATALOGUE names the model of each display); their bounds come
from ModelForge's manifest.json at build time.

The café's archive is patch-4.MPQ: a digit sorts below every lettered patch, so it never hides a realm or pack
archive's copy of a table (Tools/RaceForge/taken_patches.json registers it). The optional packs are the launcher's,
read from RaceForge's races.json (`archives.optional_packs`), so every tool works out the winners for the same packs.

Importing this module puts Tools/RaceForge, Tools/MpqPack and Tools/MapForge at the end of sys.path, as MapForge's
dbc package does for its siblings: CafeForge's own modules always win over one of the same name there.
"""

import copy
import json
import os
import sys
from dataclasses import dataclass, field

from . import REPO, TOOL
from . import catalog

TOOLS_DIR = os.path.dirname(TOOL)
SIBLINGS = tuple(os.path.join(TOOLS_DIR, name) for name in ("RaceForge", "MpqPack", "MapForge"))

for _path in SIBLINGS:
    if os.path.isdir(_path) and _path not in sys.path:
        sys.path.append(_path)

from rflib import config as rfconfig  # noqa: E402  (Tools/RaceForge)
from rflib import schema_access, spells as spellmod  # noqa: E402
from rflib.dbc import DbcTable  # noqa: E402

RACES_JSON = os.path.join(TOOLS_DIR, "RaceForge", "races.json")
OWN_ARCHIVE = "patch-4.MPQ"
# A build's own output in --out: what `build --force` removes before it writes (so its space counts as free, for the
# build and for doctor alike), and the plan file validate reads back. The art (OUT/art) stays.
PLAN_FILE = "plan.json"
OUT_ENTRIES = ("client", "server", "merged", "staging", "report.txt", "install.json", PLAN_FILE)
# The file in patch-4.MPQ that says CafeForge wrote it; ModelForge's testpatch writes one that says "test".
MARKER_FILE = "Bleakhold\\Cafe\\cafeforge.txt"
# The texture the addon probes for the patch (CAFE.SPEC.md 4.8: SetTexture("Interface\\Bleakhold\\Cafe\\Marker")).
MARKER_TEXTURE = "Interface\\Bleakhold\\Cafe\\Marker.blp"
# Paths only the café's archive may hold (compared in lower case, backslashes).
CAFE_PREFIXES = ("world\\bleakhold\\cafe\\", "interface\\icons\\bh_cafe_", "interface\\bleakhold\\cafe\\",
                 "bleakhold\\cafe\\")
MODEL_ROOT = "World\\Bleakhold\\Cafe"
# The tables the café adds rows to, and the ones its spells point at.
TABLES = ("Spell", "GameObjectDisplayInfo", "CharTitles", "SpellIcon")
REFERENCE_TABLES = ("SpellCastTimes", "SpellDuration", "SpellRange", "SpellVisual")
WRAPPER_KEYS = ("spell", "castMs", "durationMs", "range", "comment")
# The Spell.dbc columns CafeForge sets from the wrapper; a spell's own fields never hold them.
RESOLVED = {"castMs": "castingTimeIndex", "durationMs": "durationIndex", "range": "rangeIndex"}
RANGES = ("self",)


class ConfigError(Exception):
    pass


@dataclass
class CafeSpell:
    """One wrapper of dbc.spells: the SpellDef object without the resolved columns, and what resolves them."""
    data: dict
    cast_ms: int
    duration_ms: int
    range: str
    index: int = 0

    @property
    def id(self):
        return self.data["id"]

    @property
    def name(self):
        return self.data["name"]


@dataclass
class Title:
    id: int
    name: str
    mask: int


@dataclass
class Icon:
    id: int
    texture: str


@dataclass
class Display:
    """A new-art GameObjectDisplayInfo row: the display, ModelForge's model name and the client path of its .m2."""
    id: int
    name: str
    model: str
    entry: int


@dataclass
class Config:
    spells: list
    titles: list
    icons: list
    displays: list
    ids: dict
    optional_packs: dict = field(default_factory=dict)
    own: str = OWN_ARCHIVE
    path: str = ""

    def block(self, name):
        """(first, last) of an id block of cafe.json `ids` (spells, displays, icons, titles, titleMasks, ...)."""
        lo, hi = self.ids[name]
        return lo, hi

    def ids_of(self, table):
        """The café's row ids of a table, in order."""
        rows = {"Spell": self.spells, "GameObjectDisplayInfo": self.displays, "CharTitles": self.titles,
                "SpellIcon": self.icons}[table]
        return sorted(r.id for r in rows)


def model_path(name):
    """The client path of a ModelForge model (its section 5.9 output tree)."""
    return "%s\\%s\\BH_Cafe_%s.m2" % (MODEL_ROOT, name, name)


def is_cafe_path(name):
    """Whether an archive path is one only the café's archive may hold."""
    return name.replace("/", "\\").lower().startswith(CAFE_PREFIXES)


def parse_wrapper(data, index):
    """A dbc.spells wrapper as a CafeSpell, refused (ConfigError) when RaceForge's parse_spell would refuse the spell
    or its fields name no Spell.dbc column."""
    where = "dbc.spells[%d]" % index
    if not isinstance(data, dict):
        raise ConfigError("%s: must be an object {\"spell\": {...}, \"castMs\", \"durationMs\", \"range\"}" % where)
    unknown = sorted(set(data) - set(WRAPPER_KEYS))
    if unknown:
        raise ConfigError("%s: unknown keys %s (a wrapper has spell, castMs, durationMs and range)" % (where, unknown))
    spell = data.get("spell")
    if not isinstance(spell, dict):
        raise ConfigError("%s: needs \"spell\", a RaceForge SpellDef object" % where)
    where = "%s (%s)" % (where, spell.get("name") or spell.get("id"))
    for key in ("castMs", "durationMs"):
        value = data.get(key)
        if not catalog.is_int(value) or value < (-1 if key == "durationMs" else 0):
            raise ConfigError("%s: %s must be a whole number of milliseconds (%s)"
                              % (where, key, "-1 for infinite" if key == "durationMs" else "0 for instant"))
    if data.get("range") not in RANGES:
        raise ConfigError("%s: range must be one of %s" % (where, ", ".join(RANGES)))
    fields = spell.get("fields") or {}
    for key, column in RESOLVED.items():
        if isinstance(fields, dict) and column in fields:
            raise ConfigError("%s: fields.%s is set by CafeForge from the wrapper's %s" % (where, column, key))
    try:
        spelldef = rfconfig.parse_spell(copy.deepcopy(spell), index)
    except rfconfig.ConfigError as ex:
        raise ConfigError("dbc.%s" % ex) from None
    if spelldef.cast_by != "server":
        raise ConfigError("%s: cast_by must be \"server\" (no race learns a café spell)" % where)
    problems = spellmod.field_problems(DbcTable.empty(schema_access.get("Spell")), spelldef)
    if problems:
        raise ConfigError("%s: %s" % (where, "; ".join(problems)))
    return CafeSpell(copy.deepcopy(spell), data["castMs"], data["durationMs"], data["range"], index)


def read_packs(path):
    """archives.optional_packs of a RaceForge races.json or a MapForge config: {pack: [Data/... patterns]}."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as ex:
        raise ConfigError("%s: %s" % (path, ex)) from None
    packs = (data.get("archives") or {}).get("optional_packs") if isinstance(data, dict) else None
    packs = packs or {}
    if not isinstance(packs, dict) or not all(isinstance(k, str) and isinstance(v, list)
                                              and all(isinstance(p, str) for p in v) for k, v in packs.items()):
        raise ConfigError("%s: archives.optional_packs must be {pack: [file patterns]}" % path)
    return {k: list(v) for k, v in packs.items()}


def from_doc(doc, packs=None, path="", catalogue=None):
    """The packaging config of a parsed (and validated) cafe.json. catalogue: ModelForge's {display: (name, size)}
    (catalog.modelforge_catalogue), read from this checkout when None."""
    spells = [parse_wrapper(w, i) for i, w in enumerate(doc["dbc"]["spells"])]
    titles = [Title(t["id"], t["name"], t["mask"]) for t in doc["dbc"]["titles"]]
    icons = [Icon(i["id"], i["texture"]) for i in doc["dbc"]["icons"]]
    if catalogue is None:
        catalogue = catalog.modelforge_catalogue(REPO)
    if catalogue is None:
        raise ConfigError("Tools/ModelForge/mflib/props/__init__.py (CATALOGUE) is missing: it names the café's "
                          "models")
    lo, hi = doc["ids"]["displays"]
    displays = []
    for go in doc["gameobjects"]:
        display = go.get("display")
        if not catalog.is_int(display) or not lo <= display <= hi:
            continue
        if display not in catalogue:
            raise ConfigError("gameobject %s: display %d is not in ModelForge's CATALOGUE" % (go["entry"], display))
        name = catalogue[display][0]
        displays.append(Display(display, name, model_path(name), go["entry"]))
    displays.sort(key=lambda d: d.id)
    for kind, rows in (("spells", spells), ("titles", titles), ("icons", icons), ("displays", displays)):
        ids = [r.id for r in rows]
        if len(set(ids)) != len(ids):
            raise ConfigError("dbc %s: an id is listed twice" % kind)
    return Config(spells, titles, icons, displays, dict(doc["ids"]), dict(packs or {}), OWN_ARCHIVE, path)


def load(path=catalog.CAFE_JSON, packs_from=RACES_JSON):
    """cafe.json (validated by cflib/catalog.py) as a Config, with the optional packs of packs_from."""
    try:
        doc = catalog.load(path)
    except catalog.CatalogError as ex:
        raise ConfigError("%s is not valid (python3 -I Tools/CafeForge/cafeforge.py data lists why): %s"
                          % (path, "; ".join(ex.problems[:5]))) from None
    return from_doc(doc, read_packs(packs_from) if packs_from else {}, path)
