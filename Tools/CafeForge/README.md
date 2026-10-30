# CafeForge

Holds the catalogue of the Bleakhold café (The Lion's Roast in Stormwind, The Grinding Tusk in Orgrimmar: coffee,
tea and milkshakes made by players on a barista shift) and makes everything that comes from it: the files the server
module and the addon read, and, on the realm's server, the café's DBC rows and the client archive `patch-4.MPQ`.

`cafe.json` is the source of truth: the cafés, stations, actions, recipes, levels, staff, customers, the default
layout, the templates, and the café's DBC rows (`dbc`). Its ids are append-only, never reused. No Blizzard data is in
this folder or in the repository: the tools only read the DBCs and archives you give them, and the tests use made-up
tables and archives. Python 3.10 or newer, standard library only; run with `-I`.

## Commands

```sh
python3 -I Tools/CafeForge/cafeforge.py data              # write the generated files (below)
python3 -I Tools/CafeForge/cafeforge.py data --check      # exit 1 and name any stale file (CI)
python3 -I Tools/CafeForge/cafeforge.py art --out DIR     # ModelForge's models and icons, the markers: DIR/art
python3 -I Tools/CafeForge/cafeforge.py doctor --patches /srv/bleakhold-launcher/patches \
    --dbc /var/lib/docker/volumes/azerothcore-wotlk_ac-client-data/_data/dbc \
    --server-sql /root/bleakserv/data/sql --server-sql /root/bleakserv/modules
python3 -I Tools/CafeForge/cafeforge.py build --patches /srv/bleakhold-launcher/patches \
    --dbc /var/lib/docker/volumes/azerothcore-wotlk_ac-client-data/_data/dbc --out /root/cafeforge --force \
    [--preview] [--art DIR] [--server-sql-out /root/bleakhold-generated-sql/pending_db_world] \
    [--earlier-sql /root/azerothcore-wotlk/modules/mod-bleakhold-ui/data/sql --earlier-sql /root/bleakhold-generated-sql]
python3 -I Tools/CafeForge/cafeforge.py validate --out /root/cafeforge   # the build's checks again
python3 -I Tools/CafeForge/cafeforge.py sql --dbc DBC --out FOLDER [--patches P] [--art DIR] [--check-out FILE] \
    [--earlier-sql PATH ...]
python3 -I Tools/CafeForge/cafeforge.py schemas --check   # the DBC layouts against WoW/Source/DB/Rec
python3 -I Tools/CafeForge/tests/run_tests.py             # the tests
```

`doctor`, `build` and `validate` run on the realm's server (they read its patch folder and DBCs); `data`, `art`,
`schemas` and the tests run anywhere. The server runbook is in bleakserv's `deploy/README.md` ("The café"), and
bleakserv's `deploy/cafe/build-cafe.sh` runs the whole of it in one command. The café's server stays off by default
either way, and runs on stand-in art (`BleakholdUi.Cafe.UseNewArt = 0`) until the patch has reached the players.

## Generated files (`data`)

| File | What it is |
|---|---|
| `Server/mod-bleakhold-ui/src/BleakholdCafeData.h` | The server module's core-free C++ catalogue |
| `Interface/AddOns/Bleakhold/CafeData.lua` | The addon's `ns.CafeData` |
| `Server/mod-bleakhold-ui/data/sql/db-world/04_bleakhold_cafe_templates.sql` | The world templates (module SQL) |

The C++ catalogue is `namespace Bleakhold::CafeData`; the SQL holds the gameobject, creature, item and `npc_text`
templates, the staff's `creature_template_addon` and the `spell_custom_attr` rows.

Never edit them by hand; change `cafe.json` and run `data` (`cafeforge_data.py` does the same on its own).
`cflib/catalog.py` checks every rule of the catalogue first (ids, references, recipes, levels, genders, the
protocol's text caps, the layout's footprints) and `cflib/gen.py` writes the files.

## The DBC rows

Four client tables get rows, all in the café's id blocks of `cafe.json` `ids`:

| Table | Rows | Identity (same row: update; anything else at the id: refused) |
|---|---|---|
| Spell.dbc | 100900 On Shift, 100901-100926 the step spells, 100930-100938 the buffs and markers | `name[0]` |
| GameObjectDisplayInfo.dbc | 19300-19323, the new models (display = gameobject entry - 890000) | `modelName` |
| CharTitles.dbc | 190 "%s the Barista" (mask 160), 191 "%s, Café Legend" (mask 161) | `name[0]` |
| SpellIcon.dbc | 19300-19313, `Interface\Icons\BH_Cafe_<Name>` | `textureFilename` |

A CharTitles mask another row uses is refused too: two titles on one bit would share it in every character's
known-titles mask.

**Spells** are RaceForge `SpellDef` objects (`Tools/RaceForge/rflib/config.py` `parse_spell`, the format of
`races.json`'s spells) inside a café-only wrapper:

```json
{ "spell": { "id": 100903, "name": "Pull Shot", "icon": 19301, "visual": 654, "cast_by": "server",
             "text_locales": ["enUS"], "fields": { "attributesEx": 4, "effect[0]": 3, "...": 0 } },
  "castMs": 0, "durationMs": 3000, "range": "self" }
```

`castMs`, `durationMs` and `range` are resolved by value from the SpellCastTimes, SpellDuration and SpellRange copies
the players read (with every pack on; the same rows must mean the same in every other pack combination) into
`castingTimeIndex`, `durationIndex` and `rangeIndex`, which go into `fields`; only then does `parse_spell` see the
spell, and RaceForge's `spells.build_row` makes the row, exactly as for Walk on Air. A cast time or duration with no
exact row takes the nearest one with a warning (the cast bar is cosmetic: the server times every step itself);
`durationMs` 0 is no duration row (`durationIndex` 0), -1 the infinite row; `range` `"self"` is the "Self Only" row
(0 yd). A wrapper key inside `spell`, a resolved column in `fields`, or a `fields` key that is no Spell.dbc column is
refused (`unknown keys`, `set by CafeForge`, `Spell.dbc has no such column`). `doctor` prints every resolved row.

## Where the rows go

The café's archive is **`patch-4.MPQ`** (registered in `Tools/RaceForge/taken_patches.json`). The client sorts
`Data\patch-?.MPQ` by name and the last one wins (`Tools/MapForge/dbc/patches.py`): a digit sorts above the stock
`patch-2/3` and the locale patches and below every lettered patch, so `patch-4.MPQ` can never hide a realm or pack
archive's copy of a table, and it is outside every launcher pack.

A table a realm patch already holds cannot simply go into another archive: the client reads the top copy only. So,
as RaceForge's `update` and MapForge's `"dbc": "auto"` do it, for every café table and every combination of the
launcher's optional packs (read from RaceForge's `races.json`, `archives.optional_packs`; `--packs-from` takes
another file) the archive whose copy the client reads today is found, and the café's rows are forged into **that
copy**; that archive is rebuilt with everything else kept. Players with and without the HD pack each keep the copy
they load today, plus the café's rows. A combination where no patch holds the table gets the stock copy (`--dbc`,
the server's `data/dbc`) with the rows, in `patch-4.MPQ`. When `patch-4.MPQ` holds a table from such an earlier
build and a locale patch below it now holds the table too, the locale patch's copy decides and `patch-4.MPQ`'s goes.

Refused (doctor lists every one; a build stops): a café id taken by another row, a CharTitles mask clash, a
`patch-4.MPQ` in the patch folder that CafeForge did not write (no `Bleakhold\Cafe\cafeforge.txt`) or that is
ModelForge's test patch (its marker says `test`), `patch-4.MPQ` inside a pack, any other archive holding a café path
(`World\Bleakhold\Cafe\`, `Interface\Icons\BH_Cafe_`, `Interface\Bleakhold\Cafe\`), a SpellVisual a café spell names
that the players' copy lacks, an unreadable archive, and rows of the server's SQL in the café's id blocks
(`--server-sql`: `spell_dbc`, `spell_custom_attr`, `gameobjectdisplayinfo_dbc`, `chartitles_dbc`, the gameobject,
creature and item templates with their addon and model tables, `npc_text`; files whose head names CafeForge are the
café's own and are skipped).

## doctor

Read-only. It prints, for every café table and pack combination, one line in the form the build will print:

```
  Spell.dbc from patch-R.MPQ -> patch-R.MPQ (36 to add)
      max id 90170; café ids 100900-100938
  GameObjectDisplayInfo.dbc: no patch (stock) -> patch-4.MPQ (24 to add)
  all packs: Spell.dbc from Patch-Y.MPQ -> Patch-Y.MPQ (36 to add)
  no packs: Spell.dbc from patch-R.MPQ -> patch-R.MPQ (36 to add)
```

(a label only when the combinations read different copies), with the rows that would change, then the CharTitles
masks in use, the resolved cast-time, duration and range rows, the SpellVisual rows, the archives a build writes with
their sizes against the free space (`--out`, default the current folder; an earlier build's output there counts as
free, since `build --force` removes it first, but its `art/` does not), the server SQL's rows in the café's ids,
the warnings, and every problem. Exit code 0 means a build can run; 1 lists what stops it. Without `--manifest`
(ModelForge's `manifest.json`) the display rows are recognised by their model path only ("the café's (bounds at
build)"); with it their bounds are compared too. Run it again after another tool (RaceForge, MapForge) installed its
archives: each tool forges from the installed winner, so the café's rows normally survive, and doctor shows where
they are missing.

## build

```sh
python3 -I Tools/CafeForge/cafeforge.py build --patches P --dbc D --out O --force --preview --server-sql-out G
```

Everything a client and the server need, into one output folder:

| Path | What it is |
|---|---|
| `O/art/` | ModelForge's output (`art`), kept between builds with its cache; `--art DIR` uses one made before |
| `O/client/<archive>` | every archive that changes, at its place in the patch folder (`client/enUS/...` for a locale patch) |
| `O/server/sql/bleakhold_cafe_dbc.sql` | the server's `spell_dbc`, `gameobjectdisplayinfo_dbc` and `chartitles_dbc` rows |
| `O/server/cafe_check.sql` | the read-only check of the world database (bleakserv's `deploy/cafe/check-cafe-db.sh`) |
| `O/install.json` | for `raceforge.py install`: each archive with the file it replaces as the build read it |
| `O/plan.json`, `O/report.txt` | where the build read from (for `validate`), and everything it did with every check |

Nothing is written before every refusal has been looked for, in this order: the plan without the art (all of
doctor's refusals), an earlier output without `--force`, the art (below), the plan again with the art's bounds, and
the free space (each archive written whole, the largest rebuilt one's files unpacked meanwhile, the new files, a
margin; refused with what it needs and has). Then `--force` clears the earlier output, but never `O/art` and never
`O/old-patches` (the backups of an install), install.json is written as unfinished, and:

- **The archives.** Each realm archive that holds a winning copy is rebuilt with that copy replaced and every other
  file kept (MapForge's `rebuild`). `patch-4.MPQ` holds the art, the two markers and the stock copies with the café's
  rows: a new one is written whole (MpqPack's streaming writer); an earlier one is rebuilt, and every café path it
  holds that the build no longer plans goes (a renamed texture, a model taken out), and so does a table whose copy a
  realm patch now decides. When nothing of `patch-4.MPQ` would change it is not written at all, so the launcher has
  nothing to send: `patch-4.MPQ: already up to date (nothing written)`.
- **The SQL.** The rev holds the café's server rows, built from the same rows as the client copies; each id block is
  deleted before its rows go in (the file can be applied again), and the text names no time, so a build that changes
  nothing writes the same SQL. The check SQL only reads: every row it prints is in one of the café's id blocks and not
  the café's own (another spell, display, template, item, text or title, or another use of the titles). The café's
  own rows are this version's and those of the café's SQL under each `--earlier-sql` (a file whose head names
  CafeForge: the module SQL as the server has it, every earlier rev), so a new version that renames a spell, a piece,
  an NPC or an item, edits a text or moves a model finds its old rows in the database and passes.
- **The checks**, on the archives as the players will read them once installed (the patch folder with `O/client`'s
  archives in their place), for every pack combination: every written archive passes the client reader's checks,
  reads back what was put in and keeps every other file of the archive it replaces; the plan made again on that view
  has nothing left to do (every copy of every café table holds every café row field for field, no id is taken,
  nothing must move, `patch-4.MPQ` carries CafeForge's marker); `patch-4.MPQ` holds every model, skin, texture and
  icon with ModelForge's sha256, a marker texture the client loads and a marker file whose sha256 list is the
  archive's contents; what every café spell points at is there (icon, visual, cast time, duration, range); and the SQL
  reads back as the client rows, field for field.

Only when every check passed is install.json marked as passed and, with `--server-sql-out`, the rev written into that
folder (a new `rev_<nanoseconds>.sql`, whole or not at all, through RaceForge's `write_rev`; nothing when the folder's
newest café rev holds the same rows). The same rows as an older café rev only (an A, B, A history: ac-db-import never
applies that older file again, and the server holds B's rows) are written as a new rev with a note line
`-- Written again by cafeforge.py: the same rows as ..., after ...`, as `build-cafe.sh` does. The build prints:

```
Spell.dbc from patch-R.MPQ -> patch-R.MPQ (36 added)
GameObjectDisplayInfo.dbc: no patch (stock) -> patch-4.MPQ (24 added)
CharTitles.dbc: no patch (stock) -> patch-4.MPQ (2 added)
SpellIcon.dbc: no patch (stock) -> patch-4.MPQ (14 added)
written: /root/cafeforge/client/patch-R.MPQ (1 replaced, 0 added)
written: /root/cafeforge/client/patch-4.MPQ (new; 92 files)
22 checks, 0 failed (report: /root/cafeforge/report.txt)
Server SQL rev: /root/bleakhold-generated-sql/pending_db_world/rev_<numbers>.sql (written)
```

and then the next steps. A second build after the install prints `(already up to date)` for every table, `no archive
changes`, and `(already there with the same SQL: nothing written)`. `validate --out O` runs the same checks again; an
archive that `raceforge.py install` already moved into the patch folder is checked there, and any other change of the
patch folder since the build fails ("build again") and marks install.json as not passed, so install refuses it.

## art

`art --out DIR` runs ModelForge (`Tools/ModelForge/modelforge.py build --all`, then `icons`) into `DIR/art` as its own
process, and draws the markers into `DIR/art/markers`. The contract is ModelForge's `manifest.json`: for each model
its `display`, its `.m2`, `.skin` and textures, the sha256 of every file (`files`) and its `bounds`; the icons are
`DIR/art/files/Interface/Icons/BH_Cafe_<Name>.blp` (and `icons` in the manifest when ModelForge lists them). CafeForge
ships exactly the files of cafe.json's 24 displays and its 14 icons: ModelForge's test cube and any file the manifest
does not list stay out, every file must still have the sha256 ModelForge built it with, every path must be under the
café's folders, and each display's `.m2` must be the model path its row names. A build needs every model and every
icon; until ModelForge has them all (its milestone M5) `art` and `build` say what is missing
(`ModelForge built 1 of the 24 café models; missing: ...`) and a build stops there.

The markers: `Interface\Bleakhold\Cafe\Marker.blp`, an 8 x 8 DXT5 texture CafeForge draws itself (the same bytes on
every run), which the addon probes to know the player has the patch; and `Bleakhold\Cafe\cafeforge.txt`, which says
CafeForge wrote the archive (tool, version, build time, host) and lists the sha256 of every other file in it. A
`patch-4.MPQ` without it is another patch's name and is never replaced; ModelForge's test patch has one that says only
`test` and is refused too.

## sql

`sql --dbc D --out FOLDER` writes the server rows alone, for a dev realm before a client patch exists (milestone M4):
the spells' cast-time, duration and range rows come from `--dbc` (and `--patches` when given), the displays' boxes
from the art (`--art`) or else from cafe.json's sizes. `--out` is a folder (a new `rev_<nanoseconds>.sql`, or nothing
when the newest café rev there holds the same rows; the same rows as an older one only: a new rev with the note line,
as `build` writes it) or a `.sql` path; `--check-out FILE` writes the check SQL too (with `--earlier-sql`, as `build`).

## On the realm's server

Run as root in tmux, one line at a time; each line says what it must print. The long version, with what to do when a
line prints something else, is bleakserv's `deploy/README.md` ("The café"); `bash deploy/cafe/build-cafe.sh` there
runs steps 2 to 6 in one go (with `--dry-run` first).

```sh
cd /root/bleak && git pull && cd /root/bleakserv && git pull   # no "error" or "fatal"
cd /root/bleak/Tools/CafeForge && python3 -I cafeforge.py doctor --patches /srv/bleakhold-launcher/patches --dbc /var/lib/docker/volumes/azerothcore-wotlk_ac-client-data/_data/dbc --server-sql /root/bleakserv/data/sql --server-sql /root/bleakserv/modules   # No problems: cafeforge.py build can run.
python3 -I cafeforge.py build --patches /srv/bleakhold-launcher/patches --dbc /var/lib/docker/volumes/azerothcore-wotlk_ac-client-data/_data/dbc --out /root/cafeforge --force --preview --server-sql-out /root/bleakhold-generated-sql/pending_db_world --earlier-sql /root/azerothcore-wotlk/modules/mod-bleakhold-ui/data/sql --earlier-sql /root/azerothcore-wotlk/data/sql/updates --earlier-sql /root/bleakhold-generated-sql --earlier-sql /root/bleakserv/data/sql/updates; echo "exit code: $?"   # N checks, 0 failed ... exit code: 0
bash /root/bleakserv/deploy/cafe/check-cafe-db.sh /root/cafeforge/server/cafe_check.sql; echo "exit code: $?"   # check passed: no rows / exit code: 0
python3 -I /root/bleak/Tools/RaceForge/raceforge.py install --from /root/cafeforge --patches /srv/bleakhold-launcher/patches   # Now publish it: ...
bash /root/bleakserv/deploy/launcher/publish.sh   # Published build ...
```

**One tool at a time**: RaceForge (`update`, `skins`), MapForge and CafeForge can all rebuild the same realm archives;
install one tool's output before running the next, and run `doctor` again after another tool's install (each tool
forges from the installed copy, so the café's rows normally survive; when doctor shows rows to add, build and install
again). Going back: `raceforge.py install --restore --from /root/cafeforge --patches /srv/bleakhold-launcher/patches`,
then `publish.sh`.

## Layout of the folder

| Path | What it is |
|---|---|
| `cafe.json` | the catalogue |
| `cafeforge.py` | the command line |
| `cafeforge_data.py` | `data` on its own |
| `cflib/catalog.py`, `cflib/gen.py` | the catalogue's rules and the generated files |
| `cflib/config.py` | the packaging config: the `dbc` rows, the spell wrapper, `patch-4.MPQ`, the markers, the packs |
| `cflib/schemas.py` | the CharTitles, GameObjectDisplayInfo and SpellIcon layouts (`schemas --write`) |
| `cflib/dbcrows.py` | the resolved spell rows, the other tables' rows, forging them into one copy |
| `cflib/plan.py` | where each table goes per pack combination |
| `cflib/doctor.py` | `doctor`, with the server SQL scan |
| `cflib/archive.py` | the art (ModelForge's output read and checked; `art`), patch-4.MPQ's contents, writing the archives |
| `cflib/marker.py` | the marker texture and the marker file |
| `cflib/forge.py` | `build` |
| `cflib/sqlout.py` | the server rev, the check SQL, `sql` |
| `cflib/validate.py` | the checks of a build; `validate` |
| `tests/` | `run_tests.py` runs every `test_*.py`; `cafe_synth.py` makes the made-up tables, patch sets and art |

`cflib/schemas.py` is generated from the client's record classes (`WoW/Source/DB/Rec`); the other layouts are
RaceForge's. The DBC reader and writer, the spell rows and their SQL, the archive order and rebuild and the MPQ reader
are RaceForge's (`rflib`), MapForge's (`dbc/patches.py`, `dbc/sqlgen.py`) and MpqPack's, imported and never copied;
the install and its `--restore` are RaceForge's (`rflib/install.py`), the marker texture is BlpConvert's.

## Tests

```sh
python3 -I Tools/CafeForge/tests/run_tests.py
```

The catalogue and the generated files (the C++ header compiled core-free, the Lua run by the client's Lua 5.1 when
`Tools/UiLint` built it, the SQL applied twice to SQLite), the spell wrapper (resolution, the nearest cast time, the
refusals, the rows and their `spell_dbc` SQL read back field for field), doctor on synthetic patch sets (Spell.dbc in
patch-R only and in patch-R and the HD pack, a table only the pack holds, GameObjectDisplayInfo in no patch, a taken
spell, title, icon and display id, a CharTitles mask clash, `patch-4.MPQ` without a marker and as ModelForge's test
patch, café paths in another archive, a missing visual, reference rows that differ between pack combinations, an
unreadable archive, a re-run that is already up to date, a changed row, the manifest bounds in the display rows, the
server SQL scan), the build on synthetic patch sets and art (a new `patch-4.MPQ` and the winning realm copy rebuilt,
the HD pack, a locale patch's copy placed under `client/enUS/`, a re-run after the install that changes nothing, a
renamed texture dropped from `patch-4.MPQ`, a realm copy below `patch-4.MPQ` taking over, changed bounds, every
refusal before anything is written, too little space, a failed check that writes no rev and blocks the install,
install.json's fingerprints against a changed patch folder, `validate` before and after the install, `--restore`),
ModelForge's real output for the models it builds today (EspressoSW: read, checked against its manifest, refused
alone, shipped with made-up art for the rest and its bounds in the display row), the markers, the rev (read back field
for field, applied twice to SQLite, the same text every time), the check SQL on SQLite (it finds the rows that are not
the café's and only those), the `sql` command, `data --check`, and the layouts against the Rec classes. With a
bleakserv checkout next to this repository (or `CAFEFORGE_SERVER_SRC`), the SQL's columns, the check SQL's and the
rev's, are also held to bleakserv's base schema, the rev to bleakserv's SQL codestyle, and its updates are scanned for
rows in the café's ids. CI runs them and `data --check` on every push.
