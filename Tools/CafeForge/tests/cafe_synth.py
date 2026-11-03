"""Synthetic patch sets for the CafeForge tests, modelled on Tools/RaceForge/tests/synth.py and Tools/MapForge/tests/
synth_dbc.py and synth_mpq.py. No Blizzard data: every id, name and path here is made up, except the café's own ids
and the SpellVisual ids cafe.json names (numbers only).

stock_tables() gives the eight tables the café reads or changes in the client's 3.3.5a layouts (cflib/schemas.py,
RaceForge's for Spell and the spell reference tables); write_stock() puts them in a folder like the server's
data/dbc; write_patch() packs tables (and any other files) into a realm patch with MpqPack; write_art() makes a
ModelForge output folder (manifest.json and files/) for every café display and icon, with made-up file contents.
"""

import hashlib
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.dirname(HERE)
sys.dont_write_bytecode = True
if TOOL not in sys.path:
    sys.path.insert(0, TOOL)

from cflib import archive, config, schemas  # noqa: E402  (config puts RaceForge, MpqPack and MapForge on sys.path)
from cflib import marker as markermod  # noqa: E402

import mpqpack  # noqa: E402
from rflib.dbc import DbcTable  # noqa: E402

LOCALES = 16
PACKS = {"hd": ["Data/patch-[ABCDEGIMNPSU].MPQ", "Data/Patch-Y.MPQ"]}
# Made-up rows: (id, base ms) cast times, (id, ms) durations, the visuals cafe.json names plus one more.
CAST_TIMES = ((1, 0), (2, 500), (3, 800), (4, 1000), (5, 1200), (6, 1500), (7, 2000), (8, 3000))
DURATIONS = ((1, 2000), (2, 2500), (3, 3000), (4, 3500), (5, 3600000), (6, -1), (7, 10000))
VISUALS = (1, 92, 180, 327, 654, 3886, 13785)


def f32(value):
    return struct.unpack("<I", struct.pack("<f", value))[0]


def new_row(table, row_id):
    row = [0] * len(table.schema.columns)
    table.set(row, "id", row_id)
    return row


def loc(table, row, name, text):
    table.set_loc(row, name, [text] + [""] * (LOCALES - 1))
    table.set(row, "%s_flags" % name, 0xFF01FE)


def spell_table(extra=()):
    """Spell.dbc with two made-up spells and extra (id, name) rows."""
    t = DbcTable.empty(schemas.get("Spell"))
    for row_id, name in ((1, "Made Up Bolt"), (90001, "Made Up Ward")) + tuple(extra):
        row = new_row(t, row_id)
        loc(t, row, "name", name)
        t.rows.append(row)
    return t


def stock_tables(cast_times=CAST_TIMES, durations=DURATIONS, visuals=VISUALS, titles=None, spells=()):
    """{table name: DbcTable} of the stock copies."""
    out = {"Spell": spell_table(spells)}
    t = DbcTable.empty(schemas.get("SpellCastTimes"))
    for row_id, ms in cast_times:
        row = new_row(t, row_id)
        t.set(row, "base", ms)
        t.set(row, "minimum", ms)
        t.rows.append(row)
    out["SpellCastTimes"] = t
    t = DbcTable.empty(schemas.get("SpellDuration"))
    for row_id, ms in durations:
        row = new_row(t, row_id)
        t.set(row, "duration", ms)
        t.set(row, "maxDuration", ms)
        t.rows.append(row)
    out["SpellDuration"] = t
    t = DbcTable.empty(schemas.get("SpellRange"))
    for row_id, far, text in ((1, 0.0, "Self Only"), (2, 30.0, "Made Up Range")):
        row = new_row(t, row_id)
        for c in ("rangeMax[0]", "rangeMax[1]"):
            row[t.col(c)] = f32(far)
        loc(t, row, "displayName", text)
        t.rows.append(row)
    out["SpellRange"] = t
    t = DbcTable.empty(schemas.get("SpellVisual"))
    for row_id in visuals:
        t.rows.append(new_row(t, row_id))
    out["SpellVisual"] = t
    t = DbcTable.empty(schemas.get("SpellIcon"))
    row = new_row(t, 1)
    t.set_str(row, "textureFilename", "Interface\\Icons\\Made_Up_Icon")
    t.rows.append(row)
    out["SpellIcon"] = t
    t = DbcTable.empty(schemas.get("CharTitles"))
    for row_id, mask, text in titles or ((1, 1, "Made Up %s"), (2, 2, "%s the Invented")):
        row = new_row(t, row_id)
        loc(t, row, "name", text)
        loc(t, row, "name1", text)
        t.set(row, "maskID", mask)
        t.rows.append(row)
    out["CharTitles"] = t
    t = DbcTable.empty(schemas.get("GameObjectDisplayInfo"))
    row = new_row(t, 1)
    t.set_str(row, "modelName", "World\\Made\\Up\\Crate.m2")
    t.rows.append(row)
    out["GameObjectDisplayInfo"] = t
    return out


def write_stock(folder, tables=None):
    """The stock tables as <Name>.dbc files in folder (the server's data/dbc)."""
    os.makedirs(folder, exist_ok=True)
    for name, table in (tables or stock_tables()).items():
        table.write(os.path.join(folder, schemas.file_name(name)))
    return folder


def write_patch(folder, archive, tables=None, files=None):
    """A realm patch: tables ({name: DbcTable or bytes}) under DBFilesClient, plus files ({archive path: bytes})."""
    items = []
    for name, table in (tables or {}).items():
        items.append((schemas.archive_file(name), table if isinstance(table, bytes) else table.to_bytes()))
    items += list((files or {}).items())
    path = os.path.join(folder, archive)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    mpqpack.write_archive(path, items)
    return path


def marker(text="CafeForge 1\n"):
    """The café archive's marker file."""
    return {config.MARKER_FILE: text.encode("utf-8")}


SHARED_TEXTURE = "World\\Bleakhold\\Cafe\\Shared\\BH_Cafe_Steam.blp"
_ICON = []


def icon_bytes():
    """A small BLP the client loads (the café's marker picture), standing in for ModelForge's 64 x 64 icons."""
    if not _ICON:
        import tempfile  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmp:
            with open(markermod.write_marker_blp(os.path.join(tmp, "icon.blp")), "rb") as f:
                _ICON.append(f.read())
    return _ICON[0]


def model_bounds(display):
    """Made-up bounds of a display: a box that grows with the id, so every row is different."""
    return [-0.5, -0.5, 0.0], [0.5, 0.5, round(1.0 + (display - 19300) / 100, 4)]


def write_art(folder, cfg, skip_models=(), skip_icons=(), texture_suffix=None, version=1):
    """A ModelForge output folder for cafe.json's displays and icons (and ModelForge's test cube, which a build never
    ships): files/<path> with made-up contents and manifest.json with their sha256. texture_suffix: {model name:
    suffix} renames that model's atlas (BH_Cafe_<Name>_<suffix>.blp). Returns folder."""
    files, models = {}, []

    def put(name, data):
        path = archive.disk_path(folder, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        files[name] = hashlib.sha256(data).hexdigest()

    put(SHARED_TEXTURE, b"made up shared texture")
    for name, display in [("Cube", None)] + [(d.name, d.id) for d in cfg.displays]:
        if name in skip_models:
            continue
        root = "World\\Bleakhold\\Cafe\\%s\\BH_Cafe_%s" % (name, name)
        atlas = "%s_%s.blp" % (root, (texture_suffix or {}).get(name, "Atlas"))
        put(root + ".m2", ("made up model %s" % name).encode())
        put(root + "00.skin", ("made up skin %s" % name).encode())
        put(atlas, ("made up atlas %s" % name).encode())
        low, high = model_bounds(display or 19300)
        models.append({"name": name, "display": display, "m2": root + ".m2", "skin": root + "00.skin",
                       "textures": [atlas, SHARED_TEXTURE], "bounds": {"min": low, "max": high, "radius": 1.0},
                       "size": [1.0, 1.0, 1.0], "parts": {}, "triangles": 12, "collisionTriangles": 12,
                       "particles": 0, "customAnims": False,
                       "modelFrame": {"position": [0, 0, -0.5], "scale": 1.0, "facing": 0.4}})
    icons = []
    for icon in cfg.icons:
        if icon.texture.split("\\")[-1] in skip_icons:
            continue
        put(archive.icon_path(icon), icon_bytes())
        icons.append({"id": icon.id, "path": archive.icon_path(icon)})
    with open(os.path.join(folder, archive.MANIFEST), "w", encoding="utf-8") as f:
        json.dump({"tool": "ModelForge", "version": version, "models": models, "icons": icons, "files": files}, f,
                  indent=2, sort_keys=True)
    return folder
