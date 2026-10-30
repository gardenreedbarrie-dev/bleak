"""DBC layouts: the café's own tables, generated from the client's record classes (WoW/Source/DB/Rec), and
RaceForge's for the rest.

The client aborts on a DBC whose column count or row size differs from its record class (WowClientDB_Common::Load),
so the Rec classes decide every layout. The block between the GENERATED lines is written by
`python3 -I Tools/CafeForge/cafeforge.py schemas --write` from RaceForge's parser (rflib/recparse.py), the way
MapForge's dbc/schemas.py is; tests/test_dbcrows.py regenerates it whenever the Rec folder is in the checkout and
compares. Spell, SpellCastTimes, SpellDuration, SpellRange and SpellVisual are RaceForge's (rflib/schemas.py), so
RaceForge's spells.build_row and the café rows share one Spell layout.
Each entry: file name, s_numColumns, s_rowSize, s_generatedID, columns as (name, kind, size).
"""

import os

from . import REPO
from . import config  # noqa: F401  (puts Tools/RaceForge on sys.path)

from rflib import recparse, schema_access  # noqa: E402

TABLES = ("CharTitles", "GameObjectDisplayInfo", "SpellIcon")
BEGIN = "# --- GENERATED from WoW/Source/DB/Rec by cafeforge.py schemas --write; do not edit ---"
END = "# --- END GENERATED ---"

# --- GENERATED from WoW/Source/DB/Rec by cafeforge.py schemas --write; do not edit ---
SCHEMAS = {
    'CharTitles': ('DBFilesClient\\CharTitles.dbc', 37, 148, False, (
        ('id', 'int', 4),
        ('conditionID', 'int', 4),
        ('name[0]', 'locstr', 4),
        ('name[1]', 'locstr', 4),
        ('name[2]', 'locstr', 4),
        ('name[3]', 'locstr', 4),
        ('name[4]', 'locstr', 4),
        ('name[5]', 'locstr', 4),
        ('name[6]', 'locstr', 4),
        ('name[7]', 'locstr', 4),
        ('name[8]', 'locstr', 4),
        ('name[9]', 'locstr', 4),
        ('name[10]', 'locstr', 4),
        ('name[11]', 'locstr', 4),
        ('name[12]', 'locstr', 4),
        ('name[13]', 'locstr', 4),
        ('name[14]', 'locstr', 4),
        ('name[15]', 'locstr', 4),
        ('name_flags', 'locflags', 4),
        ('name1[0]', 'locstr', 4),
        ('name1[1]', 'locstr', 4),
        ('name1[2]', 'locstr', 4),
        ('name1[3]', 'locstr', 4),
        ('name1[4]', 'locstr', 4),
        ('name1[5]', 'locstr', 4),
        ('name1[6]', 'locstr', 4),
        ('name1[7]', 'locstr', 4),
        ('name1[8]', 'locstr', 4),
        ('name1[9]', 'locstr', 4),
        ('name1[10]', 'locstr', 4),
        ('name1[11]', 'locstr', 4),
        ('name1[12]', 'locstr', 4),
        ('name1[13]', 'locstr', 4),
        ('name1[14]', 'locstr', 4),
        ('name1[15]', 'locstr', 4),
        ('name1_flags', 'locflags', 4),
        ('maskID', 'int', 4),
    )),
    'GameObjectDisplayInfo': ('DBFilesClient\\GameObjectDisplayInfo.dbc', 19, 76, False, (
        ('id', 'int', 4),
        ('modelName', 'str', 4),
        ('sound[0]', 'int', 4),
        ('sound[1]', 'int', 4),
        ('sound[2]', 'int', 4),
        ('sound[3]', 'int', 4),
        ('sound[4]', 'int', 4),
        ('sound[5]', 'int', 4),
        ('sound[6]', 'int', 4),
        ('sound[7]', 'int', 4),
        ('sound[8]', 'int', 4),
        ('sound[9]', 'int', 4),
        ('geoBoxMin[0]', 'float', 4),
        ('geoBoxMin[1]', 'float', 4),
        ('geoBoxMin[2]', 'float', 4),
        ('geoBoxMax[0]', 'float', 4),
        ('geoBoxMax[1]', 'float', 4),
        ('geoBoxMax[2]', 'float', 4),
        ('objectEffectPackageID', 'int', 4),
    )),
    'SpellIcon': ('DBFilesClient\\SpellIcon.dbc', 2, 8, False, (
        ('id', 'int', 4),
        ('textureFilename', 'str', 4),
    )),
}
# --- END GENERATED ---

_cache = {}


def get(name):
    """The client layout of a table as a RaceForge TableSchema, checked against its column count and row size."""
    if name not in TABLES:
        return schema_access.get(name)
    if name not in _cache:
        filename, num_columns, row_size, generated_id, columns = SCHEMAS[name]
        schema = recparse.TableSchema(name, filename, num_columns, row_size, generated_id,
                                      [recparse.Column(*c) for c in columns])
        recparse.check_schema(schema)
        _cache[name] = schema
    return _cache[name]


def archive_file(name):
    """DBFilesClient\\Spell.dbc for Spell."""
    return get(name).filename


def file_name(name):
    """Spell.dbc for Spell."""
    return archive_file(name).split("\\")[-1]


def default_rec_dir():
    """WoW/Source/DB/Rec of this checkout, if it is there."""
    path = os.path.join(REPO, "WoW", "Source", "DB", "Rec")
    return path if os.path.isdir(path) else None


def generated_block(rec_dir):
    """The text between (and with) the GENERATED lines, for TABLES."""
    lines = [BEGIN, "SCHEMAS = {"]
    for name in TABLES:
        schema = recparse.load_rec(rec_dir, name)
        lines.append("    %r: (%r, %d, %d, %s, (" % (name, schema.filename, schema.num_columns, schema.row_size,
                                                     schema.generated_id))
        for column in schema.columns:
            lines.append("        (%r, %r, %d)," % (column.name, column.kind, column.size))
        lines.append("    )),")
    lines += ["}", END]
    return "\n".join(lines)


def module_text(rec_dir, path=__file__):
    """This file with its GENERATED block made from rec_dir."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    start = text.index("\n%s\n" % BEGIN) + 1
    end = text.index("\n%s\n" % END, start) + 1 + len(END)
    return text[:start] + generated_block(rec_dir) + text[end:]
