"""CafeForge library: the Bleakhold café's content, generated files, DBC rows and packaging.

Modules:
  catalog    cafe.json: loading and every rule of the catalogue (ids, references, recipes, levels, personas,
             genders, protocol caps) and the default layout's footprint checks
  gen        the generated files: Server/mod-bleakhold-ui/src/BleakholdCafeData.h, Interface/AddOns/Bleakhold/
             CafeData.lua and Server/mod-bleakhold-ui/data/sql/db-world/04_bleakhold_cafe_templates.sql
The packaging, from cafe.json and ModelForge's manifest:
  config     the café's DBC rows (the spell wrapper), patch-4.MPQ, the markers' paths, the launcher's packs
  schemas    the CharTitles, GameObjectDisplayInfo and SpellIcon layouts (generated from WoW/Source/DB/Rec)
  dbcrows    the rows of the four tables and forging them into one copy of a table
  plan       where each table goes, for every combination of the launcher's packs
  doctor     `doctor`: what a build would do, read-only
  archive    the art (ModelForge's output, `art`), patch-4.MPQ's contents, writing the archives
  marker     the addon's marker texture and CafeForge's marker file
  forge      `build`
  sqlout     the server's DBC rev, the check of the world database, `sql`
  validate   the checks every build ends with, `validate`
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.dirname(HERE)
REPO = os.path.normpath(os.path.join(TOOL, "..", ".."))
sys.dont_write_bytecode = True  # keep the repository free of __pycache__
