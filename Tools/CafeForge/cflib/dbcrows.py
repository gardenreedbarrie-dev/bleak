"""The café's DBC rows (section 6.3): the spell wrapper resolved into RaceForge SpellDefs, the four tables' rows, and
forging them into one copy of a table.

Spell rows are RaceForge's: each wrapper's castMs, durationMs and range become castingTimeIndex, durationIndex and
rangeIndex (resolve_indices(), by value, from the SpellCastTimes, SpellDuration and SpellRange copies the players
read), go into the spell's fields, and rflib/config.py parse_spell and rflib/spells.py build_row do the rest, so a
café spell row is built exactly as Walk on Air's is. CharTitles, SpellIcon and GameObjectDisplayInfo rows are built
here from their schemas (cflib/schemas.py).

forge_rows() puts the rows into one copy of a table, as RaceForge's update does with its racials: a free id gets the
row, an id that already holds the café's row (the same identity: Spell and CharTitles name[0], GameObjectDisplayInfo
modelName, SpellIcon textureFilename) is left as it is or brought up to date, and an id that holds anything else is a
refusal ("taken by ..."). A CharTitles mask that another row uses is refused too: two titles on one mask bit would
share the bit in every character's known-titles mask.
"""

import copy
from dataclasses import dataclass, field

from . import schemas

from rflib import config as rfconfig  # noqa: E402  (Tools/RaceForge)
from rflib import spells as spellmod  # noqa: E402
from rflib.dbc import DbcError, DbcTable, to_signed  # noqa: E402
from rflib.update import row_differences  # noqa: E402

IDENTITY = {"Spell": "name[0]", "CharTitles": "name[0]", "GameObjectDisplayInfo": "modelName",
            "SpellIcon": "textureFilename"}
# Identities that are client paths: compared as the client does, without regard to case or slash direction.
PATH_IDENTITY = ("GameObjectDisplayInfo", "SpellIcon")
SELF_ONLY = "Self Only"
LOCALE_SLOTS = 16


class RowError(Exception):
    pass


# ------------------------------------------------------------------------------------- the wrapper's indices

@dataclass
class Index:
    """What one wrapper value resolved to: the table row (index) and the value that row holds."""
    column: str          # castingTimeIndex, durationIndex or rangeIndex
    wanted: object       # castMs / durationMs (ms) or the range name
    index: int
    value: object
    exact: bool
    table: str = ""

    def text(self):
        if self.column == "rangeIndex":
            got = "%r" % self.value
        else:
            got = "%s ms" % self.value
        if self.index == 0:
            return "%s %s -> 0 (none)" % (self.key_name(), self.wanted)
        return "%s %s -> %s %d (%s%s)" % (self.key_name(), self.wanted, self.table, self.index, got,
                                         "" if self.exact else ", the nearest: no exact row")

    def key_name(self):
        return {"castingTimeIndex": "castMs", "durationIndex": "durationMs", "rangeIndex": "range"}[self.column]


def _cast_index(table, ms):
    rows = [(to_signed(r[0]), table.get_signed(r, "base")) for r in table.rows
            if table.get_signed(r, "perLevel") == 0]
    exact = sorted(i for i, base in rows if base == ms)
    if exact:
        return Index("castingTimeIndex", ms, exact[0], ms, True, "SpellCastTimes")
    if not rows:
        return None
    i, base = min(rows, key=lambda r: (abs(r[1] - ms), r[0]))
    return Index("castingTimeIndex", ms, i, base, False, "SpellCastTimes")


def _duration_index(table, ms):
    if ms == 0:
        # an instant spell without an aura has no duration row, as the stock ones have none
        return Index("durationIndex", 0, 0, 0, True, "SpellDuration")
    rows = [(to_signed(r[0]), table.get_signed(r, "duration")) for r in table.rows
            if table.get_signed(r, "durationPerLevel") == 0 and table.get_signed(r, "maxDuration")
            == table.get_signed(r, "duration")]
    exact = sorted(i for i, d in rows if d == ms)
    if exact:
        return Index("durationIndex", ms, exact[0], ms, True, "SpellDuration")
    rows = [r for r in rows if r[1] > 0]
    if ms < 0 or not rows:
        return None
    i, d = min(rows, key=lambda r: (abs(r[1] - ms), r[0]))
    return Index("durationIndex", ms, i, d, False, "SpellDuration")


def _range_index(table, name):
    zero = []
    for r in table.rows:
        ranges = [table.float_value(r, c) for c in ("rangeMin[0]", "rangeMin[1]", "rangeMax[0]", "rangeMax[1]")]
        if all(v == 0 for v in ranges):
            zero.append((to_signed(r[0]), table.get_str(r, "displayName[0]")))
    named = sorted(i for i, text in zero if text == SELF_ONLY)
    if named:
        return Index("rangeIndex", name, named[0], SELF_ONLY, True, "SpellRange")
    if not zero:
        return None
    i, text = min(zero)
    return Index("rangeIndex", name, i, text, False, "SpellRange")


def resolve_indices(cfg, tables):
    """{(column, wanted): Index} for every castMs, durationMs and range of the café spells, from tables (the
    SpellCastTimes, SpellDuration and SpellRange copies the players read), and the problems."""
    out, problems = {}, []
    wanted = sorted({("castingTimeIndex", s.cast_ms) for s in cfg.spells}
                    | {("durationIndex", s.duration_ms) for s in cfg.spells}, key=lambda k: (k[0], k[1]))
    wanted += sorted({("rangeIndex", s.range) for s in cfg.spells})
    finders = {"castingTimeIndex": ("SpellCastTimes", _cast_index), "durationIndex": ("SpellDuration", _duration_index),
               "rangeIndex": ("SpellRange", _range_index)}
    for column, value in wanted:
        name, finder = finders[column]
        table = tables.get(name)
        if table is None:
            problems.append("%s.dbc is in no patch and not in --dbc: the café spells' %s cannot be resolved"
                            % (name, column))
            continue
        found = finder(table, value)
        if found is None:
            what = {"castingTimeIndex": "a %s ms cast time" % value, "rangeIndex": "a \"%s\" range (0 yd)" % value,
                    "durationIndex": "an infinite (-1) duration" if value == -1 else "a %s ms duration" % value}
            problems.append("%s.dbc has no row for %s" % (name, what[column]))
            continue
        out[(column, value)] = found
    return out, problems


def index_problems(indices, tables, label):
    """The resolved rows must mean the same in another pack combination's copies: (problems)."""
    problems = []
    for idx in indices.values():
        if idx.index == 0:
            continue
        table = tables.get(idx.table)
        if table is None:
            continue
        row = table.by_id().get(idx.index)
        if row is None:
            problems.append("%s %d (%s %s) is missing in the copy %s read" % (idx.table, idx.index, idx.key_name(),
                                                                              idx.wanted, label))
            continue
        again = {"SpellCastTimes": _cast_index, "SpellDuration": _duration_index,
                 "SpellRange": _range_index}[idx.table](_only(table, row), idx.wanted)
        if again is None or again.index != idx.index or (idx.column != "rangeIndex" and again.value != idx.value):
            problems.append("%s %d holds another value in the copy %s read (%s %s)"
                            % (idx.table, idx.index, label, idx.key_name(), idx.wanted))
    return problems


def _only(table, row):
    """A table holding only row (to ask whether that one row still resolves the same)."""
    return DbcTable(table.schema, [row], bytes(table.strings))


def spell_defs(cfg, indices):
    """{id: RaceForge SpellDef} of the café spells with the resolved indices in their fields."""
    out = {}
    for s in cfg.spells:
        data = copy.deepcopy(s.data)
        fields = dict(data.get("fields") or {})
        for column, value in (("castingTimeIndex", s.cast_ms), ("durationIndex", s.duration_ms),
                              ("rangeIndex", s.range)):
            idx = indices.get((column, value))
            if idx is None:
                raise RowError("spell %d (%s): %s %s is not resolved" % (s.id, s.name, column, value))
            fields[column] = idx.index
        data["fields"] = fields
        try:
            out[s.id] = rfconfig.parse_spell(data, s.index)
        except rfconfig.ConfigError as ex:
            raise RowError("dbc.%s" % ex) from None
    return out


# ------------------------------------------------------------------------------------------------- the rows

class Rows:
    """The café's rows of the four tables. bounds: {display: ((min x, y, z), (max x, y, z))} from ModelForge's
    manifest; without it the GameObjectDisplayInfo rows are known by their identity only (doctor)."""

    def __init__(self, cfg, defs, bounds=None):
        self.cfg = cfg
        self.defs = defs
        self.bounds = bounds
        self.titles = {t.id: t for t in cfg.titles}
        self.icons = {i.id: i for i in cfg.icons}
        self.displays = {d.id: d for d in cfg.displays}

    def ids(self, name):
        return self.cfg.ids_of(name)

    def label(self, name, row_id):
        if name == "Spell":
            return "spell %d %s" % (row_id, self.defs[row_id].name)
        if name == "CharTitles":
            return "title %d %r" % (row_id, self.titles[row_id].name)
        if name == "SpellIcon":
            return "icon %d %s" % (row_id, self.icons[row_id].texture.split("\\")[-1])
        return "display %d %s" % (row_id, self.displays[row_id].name)

    def identity(self, name, row_id):
        if name == "Spell":
            return self.defs[row_id].name
        if name == "CharTitles":
            return self.titles[row_id].name
        if name == "SpellIcon":
            return self.icons[row_id].texture
        return self.displays[row_id].model

    def buildable(self, name):
        return name != "GameObjectDisplayInfo" or self.bounds is not None

    def build(self, name, table, row_id):
        """The café's row of row_id, its strings added to table's string block."""
        if name == "Spell":
            return spellmod.build_row(table, self.defs[row_id])
        row = [0] * len(table.schema.columns)
        table.set(row, "id", row_id)
        if name == "CharTitles":
            title = self.titles[row_id]
            for loc in ("name", "name1"):
                table.set_loc(row, loc, [title.name] + [""] * (LOCALE_SLOTS - 1))
                table.set(row, "%s_flags" % loc, spellmod.LOC_FLAGS_TEXT)
            table.set(row, "maskID", title.mask)
        elif name == "SpellIcon":
            table.set_str(row, "textureFilename", self.icons[row_id].texture)
        else:
            if self.bounds is None or row_id not in self.bounds:
                raise RowError("display %d: no bounds (ModelForge's manifest.json has none for it)" % row_id)
            low, high = self.bounds[row_id]
            table.set_str(row, "modelName", self.displays[row_id].model)
            for i in range(3):
                row[table.col("geoBoxMin[%d]" % i)] = spellmod.float_bits(low[i])
                row[table.col("geoBoxMax[%d]" % i)] = spellmod.float_bits(high[i])
        return row


def same_identity(name, a, b):
    if name in PATH_IDENTITY:
        return a.replace("/", "\\").casefold() == b.replace("/", "\\").casefold()
    return a == b


# ----------------------------------------------------------------------------------------------- forging

@dataclass
class Forged:
    """What forge_rows did to one copy: notes per row, the ids it added or changed, and refusals."""
    notes: list = field(default_factory=list)
    added: list = field(default_factory=list)
    updated: list = field(default_factory=list)
    same: list = field(default_factory=list)
    ours: list = field(default_factory=list)     # identity only: the café's row, not compared (no manifest)
    problems: list = field(default_factory=list)

    @property
    def changed(self):
        return sorted(self.added + self.updated)

    def summary(self, done=False):
        """'(36 added)', '(already up to date)', ... ; done False: what a build would do ('36 to add')."""
        parts = []
        for count, past, future in ((self.added, "added", "to add"), (self.updated, "updated", "to update"),
                                    (self.ours, "the café's (bounds at build)", "the café's (bounds at build)")):
            if count:
                parts.append("%d %s" % (len(count), past if done else future))
        if not parts and not self.problems:
            return "already up to date"
        if self.same and parts:
            parts.append("%d up to date" % len(self.same))
        return ", ".join(parts) if parts else "refused"


def mask_problems(table, rows):
    """CharTitles masks the café titles use that another row holds."""
    ours = {t.mask: t for t in rows.cfg.titles}
    problems = []
    for row in table.rows:
        mask = table.get_signed(row, "maskID")
        title = ours.get(mask)
        if title is None:
            continue
        row_id = to_signed(row[0])
        if row_id == title.id and table.get_str(row, "name[0]") == title.name:
            continue
        problems.append("CharTitles mask %d (title %d %r) is taken by title %d %r" % (
            mask, title.id, title.name, row_id, table.get_str(row, "name[0]")))
    return problems


def forge_rows(name, table, rows):
    """Put the café's rows of table name into one copy of it (in place). Returns Forged."""
    out = Forged()
    by_id = table.by_id()
    column = IDENTITY[name]
    if name == "CharTitles":
        out.problems += mask_problems(table, rows)
    for row_id in rows.ids(name):
        label = rows.label(name, row_id)
        existing = by_id.get(row_id)
        if existing is None:
            if rows.buildable(name):
                table.rows.append(rows.build(name, table, row_id))
                out.notes.append("%s: added" % label)
            else:
                out.notes.append("%s: free" % label)
            out.added.append(row_id)
            continue
        current = table.get_str(existing, column)
        if not same_identity(name, current, rows.identity(name, row_id)):
            out.problems.append("%s: id %d is taken by %r (%s) in this copy of %s" % (
                label, row_id, current, column, schemas.file_name(name)))
            continue
        if not rows.buildable(name):
            out.notes.append("%s: the café's" % label)
            out.ours.append(row_id)
            continue
        scratch = DbcTable.empty(table.schema)
        expected = rows.build(name, scratch, row_id)
        differences = row_differences(table, existing, scratch, expected)
        if not differences:
            out.notes.append("%s: already there" % label)
            out.same.append(row_id)
            continue
        existing[:] = rows.build(name, table, row_id)
        out.notes.append("%s: updated (%s%s)" % (label, ", ".join(differences[:6]), ", ..." if len(differences) > 6
                                                  else ""))
        out.updated.append(row_id)
    return out


def table_from(data, name, where):
    """A copy of a table from its file bytes; RowError when it is not that table's 3.3.5a layout."""
    try:
        return DbcTable.from_bytes(data, schemas.get(name), where)
    except DbcError as ex:
        raise RowError(str(ex)) from None

