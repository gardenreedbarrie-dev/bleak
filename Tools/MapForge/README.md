# MapForge

Builds an original map for the 3.3.5a (12340) client and AzerothCore: the terrain files (`terrain/`), the DBC rows
that make the client and the server know the map, the patch archives players install, and the server SQL. The first
map is **Bleakhold Royale**, a 20-40 player free-for-all battle royale (`bleakhold_royale.json`).

No Blizzard data is in this folder or in the repository. The tools only work on files you give them, and the tests
use made-up tables and archives. Python 3.10 or newer, standard library only; run with `-I`.

## Data and packaging

`package.py` adds the map's rows to **the realm's current DBCs**, decides which archive each modified DBC must go
into, packs the map archive, rebuilds the realm archives that need the rows, and writes the AzerothCore SQL. The
DBC reader and writer is RaceForge's (`Tools/RaceForge/rflib/dbc.py`: every existing row and the string block stay
byte for byte, new strings are appended), archives are MpqPack's, textures BlpConvert's. The layouts come from the
client's own record classes in `WoW/Source/DB/Rec` (`dbc/schemas.py`; the client aborts on a DBC whose column
count or row size differs).

### What the map gets

- **Map.dbc**: id **901**, directory `BleakholdRoyale`, InstanceType **3**, MaxPlayers 40. Values the config
  leaves out are copied from Warsong Gulch (489); the loading screen is Warsong's.
- **AreaTable.dbc**: zone **5100** on map 901 with the flags `ARENA` (0x80, free-for-all PvP for the whole zone)
  and `NO_FLY_ZONE`; sounds and music copied from Warsong Gulch (3277).
- **Light.dbc**: the map's default light (coordinates 0,0,0), next free id. All 8 LightParams slots point at the
  stock LightParams row that shows `Environments\Stars\WintergraspSmokySky.M2`.
- **WorldMapArea.dbc**: next free id, bounds from the terrain's tiles widened to the world map's 1002:668 frame (no
  world map art yet).
- **BattlemasterList.dbc**: id **12** (a free BattlegroundTypeId), map 901, solo queue, levels 80-80. The client
  lists every BattlemasterList row with InstanceType 3 in its battleground UI.
- **PvpDifficulty.dbc**: one bracket, range index 7, levels 80-80, next free id (`GetBattlegroundBracketByLevel`
  needs it).
- **LoadingScreens.dbc**: nothing by default. `loading_screen: {"name", "file", "image", "wide_image"}` adds a row
  and 1024x1024 / 2048x1024 BLPs; the file path may hold only one dot, since the client inserts `Wide` before the
  first one.

**Ids.** Stock 3.3.5a maps end at 724 and AzerothCore's sources and SQL know none above it; the realm's own Emberwing
Hollow is map 740 (`mod-bleakhold`), so 901 keeps clear of both and of anything a pack installer may have added
near 740. The map id stays below 1000: the server names its map files with `%03u` and `mmaps_generator` overflows a
12-byte filter for 4-digit ids. Stock areas end below 5000, so the zone is 5100. Ids the server's own SQL already
uses (`--server-sql`, for example the fork's server-only WorldMapArea rows 1000 and 1001) are refused or skipped,
and every other id is the next free one above the table's own ids, because the client keeps each table in an array
indexed from its lowest to its highest id. The build stops when an id belongs to anything that is not this map.
**The live world database was not available**: run `bleakhold_royale_check.sql` before installing (below).

**InstanceType 3 (battleground).** Every match is its own `BattlegroundMap` instance, keyed by the player's
battleground id (`MapInstanced::CreateInstanceForPlayer`); instances share the terrain, so concurrent matches are
cheap; nobody can walk or teleport in outside a match (`TeleportTo` refuses battleground maps unless
`InBattleground()`); spirit healers, start timers, the score frame and deserter handling come with it. Type 0 would
be one shared world map (one match at a time, players log back into it). Types 1/2 need an `instance_template` row
and pick the instance by group binds, and `InstanceMap::CannotEnter` turns away a player from another group once
anyone is inside, which rules out a 40-player FFA. Type 4 (arena) adds arena-only client rules (no spells with long
cooldowns, arena frames). The server side still needs the Battleground subclass, its `battleground_template` row
and the BattlegroundTypeId 12 registration; `Battleground::AddPlayer` puts players into team raids, which are
friendly to each other, so the subclass has to undo that for a free-for-all.

**Free-for-all.** `Player::UpdateArea` sets `IsInFFAPvPArea` from the area's 0x80 flag and `UpdateFFAPvPState`
then sets `UNIT_BYTE2_FLAG_FFA_PVP`; the client's `GetZonePVPInfo()` reports "arena". The flag is read from the area
the player stands in, so every MCNK of the terrain must carry the zone id (or a subzone that has the flag too);
the build checks the terrain manifest's area ids against the config.

**Sky.** Skyboxes never sit in ADTs: a map's default Light row points at LightParams rows, and those at LightSkybox
rows that name the M2. `light.skybox` finds the stock LightParams row of a given skybox; `params_from_map`,
`params_from_light` or `params` choose exact rows; without a light section the client uses Light 1 (the default
sky). New LightParams rows are not made: each would need 18 LightIntBand and 6 LightFloatBand rows at ids derived
from its own.

No WorldStateUI rows are added. If scoreboard columns are added later, the rows of type 2 for this map and for map
-1 must stay contiguous in the file (`BattlefieldInfo.cpp`), so they cannot simply be appended.

### Which DBCs to give it

The client reads each DBC from the archive with the highest priority that holds it, so the input must be those
copies, not stock ones: the realm's patches (Patch-R, Patch-Y, Patch-Z and others) already ship modified DBCs, some
merged with Reforged's, and a build from stock files would drop all of that (Emberwing Hollow's Map row, for one).

- `package.py pull --patches <patch folder> --out <folder>` writes, for each table, the winning copy with every pack
  on. It reads MpqPack archives and third-party ones with zlib or bzip2 files, encrypted files and sector
  checksums. It refuses imploded (PKWARE) and LZMA files with a message; extract those with an MPQ editor.
- A table no realm patch holds comes from the client's base archives: take it from the server's `data/dbc` (the
  extractor made those from the same client; in Docker the `ac-client-data` volume), or extract it.
- `build --patches` compares every input file with the winning copy and fails on a difference.

### Patch letters and where the DBCs go

The client opens every `Data\patch-?.MPQ` (one character) and sorts them by path with `_strnicmp` (letters folded
to lower case); the path sorting last wins. Every lettered patch outranks the locale archives that hold the stock
DBCs. In use: H L R T V X Y Z (realm), A B C D E G I M N P S U (Reforged), J (WoW Forever's login patch); RaceForge
writes customization art as S T U V W X Y Z by default. Free: F K O Q.

- **The map archive is `patch-Q.MPQ`**: the highest free letter, outside RaceForge's art letters and outside the
  launcher's HD pack (`Data/patch-[ABCDEGIMNPSU].MPQ` and `Data/Patch-Y.MPQ`), so every player has it. It holds
  `World\Maps\BleakholdRoyale\*.wdt/.wdl/.adt`, the loading screen and minimap textures, a marker file, and every
  modified DBC that no realm patch holds. Its paths are new, so its letter only has to beat the stock archives; the
  build fails if any other patch already holds one of them.
- **A DBC that a realm patch holds cannot simply go into a later letter**: after Z only `{ } ~` sort, and a
  separate copy above Z would silently hide every later change the realm makes to that table. So `"dbc": "auto"`
  works out, for each table and each pack combination (with and without the HD pack), which archive wins today, and
  **rebuilds each winning archive with the map's rows forged into that archive's own copy**. Players with the pack
  keep Patch-Y's copy plus our rows, players without it keep theirs plus our rows, and the realm's own archive stays
  the baseline for its next DBC edit. A combination where no patch holds the table gets the copy in patch-Q.
- `"dbc": "map"` puts every DBC into the map archive and refuses when a later archive holds one; `"dbc": "merge"`
  with `merge_into` forces one archive and refuses when a later one holds the file.
- Rebuilt archives keep every other file of the original (read and repacked with MpqPack: zlib, a listfile, no
  locale variants). The build refuses an archive whose listfile misses files, or with locale-specific copies.
- `md5translate.trs` (minimap) is one global file: with `--minimap`, the build starts from the realm's current trs
  (from `--patches` or `--trs`), adds one line per tile with CR LF line ends (the client drops a last line without
  one), and packs it into patch-Q; it fails if a later archive holds a trs.

`package.py doctor --patches <folder>` lists the archives in load order with their packs and prints where each
DBC would go, without building anything.

### Build on the VPS

The real client and the realm's patches are on the VPS (`/srv/bleakhold-launcher/base` and `patches`):

```sh
cd /root/bleak/Tools/MapForge
python3 -I package.py doctor --patches /srv/bleakhold-launcher/patches --config bleakhold_royale.json
python3 -I package.py pull --patches /srv/bleakhold-launcher/patches --out /root/mapforge/dbc \
    --config bleakhold_royale.json
# copy the tables pull did not find (stock-only) from the server's data/dbc into /root/mapforge/dbc
python3 -I terrain/build.py <terrain spec> /root/mapforge/terrain
python3 -I package.py build --config bleakhold_royale.json --dbc /root/mapforge/dbc \
    --terrain /root/mapforge/terrain --patches /srv/bleakhold-launcher/patches \
    --server-sql /root/bleakserv/data/sql --server-sql /root/bleakserv/modules --out /root/mapforge/out
```

The exit code is 0 when every check passed; read `out/report.txt`. Then:

1. **Client**: put `out/client/patch-Q.MPQ` and every rebuilt realm archive in `out/client/` into
   `/srv/bleakhold-launcher/patches/` (upload under a new name and `mv` it into place; never overwrite a published
   file). A rebuilt archive replaces the realm's file of the same name. Players need a client restart.
2. **Server rows**: AzerothCore loads map_dbc, areatable_dbc, light_dbc, worldmaparea_dbc, battlemasterlist_dbc and
   pvpdifficulty_dbc over its `data/dbc` files by id (`LoadDBC` -> `DBCDatabaseLoader`; a row the files lack is
   added), so `data/dbc` stays as it is. Run `out/server/sql/bleakhold_royale_check.sql` on `acore_world` first; it
   must list nothing but rows of this map. Then add `out/server/sql/bleakhold_royale.sql` to bleakserv as
   `data/sql/updates/pending_db_world/rev_<timestamp>.sql` (`create_sql.sh` makes the name; `build --pending
   <that folder>` writes it directly). `bleakhold_royale_remove.sql` undoes it.
3. **Server terrain**: the extractors read only numbered patches, never lettered ones. Stage
   `out/server/extract/patch-5.MPQ` (the terrain and the new Map.dbc) in a copy of the client as both
   `Data/patch-5.MPQ` and `Data/enUS/patch-enUS-9.MPQ` (map_extractor lets the common patches win, vmap4_extractor
   the locale patches), run `map_extractor -e 1`, `vmap4_extractor` and `vmap4_assembler`, then
   `mmaps_generator 901`, and copy the `901*` files into the server's maps, vmaps and mmaps.

`package.py validate --config bleakhold_royale.json --out <folder>` checks an output folder again.

### Output

| Path | Contents |
|---|---|
| `client/patch-Q.MPQ` | terrain, textures, and the DBCs no realm patch holds |
| `client/<realm archive>.MPQ` | each realm archive that wins for a modified DBC, rebuilt with the rows |
| `client/DBFilesClient/*.dbc` | the modified tables, forged on the input copies |
| `server/sql/bleakhold_royale.sql` | the install: DELETE + INSERT per table, passes `codestyle-sql.py` |
| `server/sql/bleakhold_royale_check.sql`, `_remove.sql` | the pre-install check and the removal |
| `server/extract/patch-5.MPQ` | terrain + Map.dbc for the server's extractors |
| `report.txt` | every decision and check |

### Config

`bleakhold_royale.json`: `map` (id, directory under 64 characters, template, name and per-locale `names`,
instance_type, flags, corpse, expansion, max_players), `zone` (id, template, name, `set_flags`/`clear_flags` by
`AREA_FLAG_*` name, area_bit or automatic, sounds or the template's, `subzones`), `loading_screen` (null, an
existing id, or a new row), `light`, `world_map_area` (bounds `"auto"` from the terrain or `[left, right, top,
bottom]`), `battleground` (BattlemasterList id and template, queue rules, PvpDifficulty brackets) and `archives`
(map archive name, DBC mode, the launcher's optional packs, reserved letters). Null values are copied from the
template row.

### Tests

```sh
python3 -I Tools/MapForge/tests/run_tests.py
```

`tests/test_dbc*.py` and `tests/test_package.py` build made-up DBCs (`tests/synth_dbc.py`, packed with struct
independently of the reader) and archives (`tests/synth_mpq.py`, including bzip2, encrypted and sector-checksum
files), and check: the layouts against the Rec classes and against AzerothCore's `DBCfmt.h` and `*_dbc` table
columns (when a bleakserv checkout is next to this repository), round trips, that every input row stays byte for
byte, localized strings and their flags column, ids, area bits, the light and battleground rows, the client's
archive order and packs, the placement plan, archive rebuilds, the SQL (run against SQLite, twice, then removed)
and the whole build.

## Terrain

`terrain/` writes the map's own terrain from a JSON spec: the WDT, the WDL and one ADT per tile, laid out as
`World\Maps\<Dir>\` for the map archive. The spec is ours (heights, textures by rule, placements of stock models by
path); no Blizzard file is copied. The sample is `specs/royale_draft.json`: a 3 x 3-tile battle royale arena with
a ruined keep plateau in the centre, a ruined village, a watchtower hill, a crypt hollow and a river ford camp,
cover in between, a river with a ford and a bridge, and a cliff ring that closes the edge.

```sh
python3 -I Tools/MapForge/terrain/build.py Tools/MapForge/specs/royale_draft.json out/terrain [--force]
python3 -I Tools/MapForge/terrain/validate.py out/terrain [--assets <extracted client files>] [--dbc <dbc folder>]
python3 -I Tools/MapForge/terrain/ac_crosscheck.py out/terrain --extractor <build>/src/tools/map_extractor \
    [--vmap4 <build>/src/tools/vmap4_extractor]
```

`build.py` writes, besides `World/Maps/<Dir>/`:

- `pois.json`: the named points (`pois`) with their ground height (orb shrines, crate drops, storm centres,
  landmarks) and the map id, for the server's spawn tables. It sits next to `World/`, not inside it, so the
  archive gets only client files.
- `terrain_manifest.json`: map id and directory, tiles, world bounds, the MCNK area ids, every placement with its
  unique id, resolved position and tiles, the border check, warnings and file hashes. `package.py --terrain`
  reads it (directory, tiles, area ids) and packs `World/Maps/<Dir>/`.
- `preview.png`, `heightmap.png`: top-down views, north up. Texture colours shaded by the slope, water, WMOs (red),
  doodads (yellow), POIs (magenta); grey levels by height.

The same spec and seed give the same bytes: heights use only exact IEEE arithmetic (integer-hash gradient noise,
polynomial falloffs, our own sine/cosine), never the platform's `libm`.

### Coordinates

World X points north, Y west, Z up, in yards, the numbers `.gps` shows. Tiles are 1600/3 = 533.333 yards; tile
(32, 32) has its north-west corner at world (0, 0), and tile (tx, ty) is `<Dir>_<tx>_<ty>.adt` with tx counting
west to east and ty north to south (`CMap::PrepareArea`). A 3 x 3 block on tiles 31-33 covers X and Y from
-1066.67 to 533.33. Model placements are stored as (17066.667 - Y, Z, 17066.667 - X) (`CMap::CreateDoodadDef`).
Heights are evaluated on one lattice every 2.083 yards that every chunk and tile shares, and rounded to 1/64 yard,
which float32 holds exactly, so every edge vertex is bit-identical on both sides.

### Spec

Keys starting with `_` are comments. Every other unknown key is an error.

- `map`: `directory` (Map.dbc Directory, letters/digits/`_`, under 64 characters), `tiles` `{x: [first, last],
  y: [first, last]}` and optionally `id` (the Map.dbc id, copied into the manifest and `pois.json`).
- `seed`, `area_id` (the AreaTable row for every chunk; `areas` lists shapes with other ids; it must be a row
  `package.py` adds, the zone id in `bleakhold_royale.json`), `uid_base` (first automatic unique id).
- `heightmap`: `base`, `noise` layers (`scale` in yards, `amplitude`, `octaves`, `persistence`, `lacunarity`,
  `seed`) and `features`, applied in order:
  `hill` (`center`, `radius`, `height`, `shape` smooth/cone/dome), `flatten` or `plateau` (`shape`, `height` or
  null for the terrain height at its centre, `falloff`, `mode` set/raise/lower), `river` (`path`, `width`, `bank`,
  `bed` height), `ramp` (`from`/`to` `[x, y, z or null]`, `width`, `falloff`), `border` (adds `height` within
  `inset` yards of the tile range's edge, fading over `width`, `jitter` for a natural line; stack a wide ridge and
  a steep wall for a cliff), `clamp` (`min`, `max`).
- `textures`: `name`, `path` (`.blp`), `color` for the preview, `effect_id` (GroundEffectTexture for ground
  clutter), `mtxf_flags` (1 when the texture has no `_s.blp`: with specular terrain on, the client loads
  `<name>_s.blp` unless MTXF flag 1 is set, `CMapArea::LoadTerrainTexture`).
- `texture_rules`: the first texture covers everything, then each rule paints its texture over with a coverage
  made of `shape` + `fade`, `slope` (`min`/`max` degrees), `height` (`min`/`max`/`fade`), `noise` (`scale`,
  `threshold`, `fade`) and `strength`.
- `doodads` (`.m2`) and `wmos` (root `.wmo`): `model`, `position` `[x, y]` (on the ground) or `[x, y, z]`,
  `z_offset`, `facing` (the server's orientation in degrees) or raw `rotation` `[x, y, z]` in file order, `scale`
  (doodads only), `uid`, `bounds` (model box), `radius` (fallback footprint), and for WMOs `doodad_set`,
  `name_set`. Chests, orbs and other interactive things are server GameObjects, not terrain doodads.
- `water`: `liquid_type` (stock LiquidType id, 1 = water), `height`, `shape`, `min_depth`.
- `holes`: shapes cut out of the terrain (none in the royale map: players drop in anywhere).
- `pois`: `name`, `kind`, `position`, `radius`, `flatten` (true or `{falloff}`: the whole radius becomes flat
  ground at the terrain height of its centre).
- Shapes are `{"circle": {center, radius}}`, `{"rect": {min, max}}`, `{"polygon": {points}}` or
  `{"polyline": {points, width}}`, in world coordinates.

### What the files look like, and why

From the client's own readers (`WoW/Source/WorldClient`) and AzerothCore's `map_extractor` / `vmap4_extractor`:

- **WDT**: MVER 18, MPHD (32 bytes), MAIN (4096 x 8 bytes, flag 1 on exactly the shipped tiles), an empty MWMO.
  `CMap::LoadWdt` reads them by position; a missing WDT is a fatal error in the client. MPHD flags 0: no global
  WMO, no MCCV (flag 2 would make the client read MCCV in every chunk), 4-bit alpha (flag 4 would ask for 8-bit
  maps), unsorted doodad refs (flag 8 changes the cull loop).
- **ADT**: MVER, MHDR (64 bytes, offsets relative to its payload, `mamp_value` 0), MCIN at file offset 84
  (AzerothCore subtracts 84), MTEX, MMDX, MMID, MWMO, MWID, MDDF, MODF, MH2O when there is water, 256 MCNK, MTXF.
  The eight required MHDR offsets always point at a chunk, empty or not (`CMapArea::ProcessIffChunks` follows
  them without checks). MCIN flags stay 0: the client keeps its first-use flag there.
- **MCNK**: the 128-byte header, then MCVT (145 heights), MCNR (declared 435 + 13 padding bytes; the client resets
  the size to 448), MCLY, MCRF, MCAL, an empty MCLQ (`sizeLiquid` 8) and an empty MCSE. The client walks them by
  size and resets MCAL's size to `sizeAlpha - 8`, so `sizeAlpha` is the MCAL payload + 8; AzerothCore reads the
  header offsets (from the MCNK start, header included) and wants MCVT at 580 bytes. Flags 0x8000: the client
  reads the full 64 x 64 alpha. Up to 4 layers (the client fills a 4-slot array without a check); layers 1-3 have
  a 2048-byte 4-bit alpha map, first texel in the low nibble, blended in order. `areaid`, the 16-bit `holes`, and
  the low-quality texture map (dominant layer per cell) are filled; normals are signed bytes, 127 = 1.0, in world
  X, Y, Z order.
- **Placements**: doodad scale 1024 = 1.0; WMOs never get flag 0x1 (destructible, skipped by the client); MODF
  scale 1024. A placement is listed in every tile and referenced from every chunk its footprint touches, with the
  same unique id; ids are unique across doodads and WMOs (the client dedups by id, `vmap4_extractor` spawns by
  it). MODF extents are the placed model box: from `bounds`, from the real model with `--assets` (MOHD of a WMO,
  the header box of an M2), or a cube of `radius` as a fallback.
- **Water**: MH2O, one liquid layer per chunk, vertex format 0 (heights + depth), fishable bits for the wet cells,
  deep 0, an 8-byte exists bitmap (AzerothCore reads a whole u64). A cell is wet where the shape holds it and the
  terrain dips below the water level.
- **WDL**: MVER, empty MWMO/MWID/MODF, MAOF, then MARE (17 x 17 + 16 x 16 heights) and MAHO per tile
  (`CMapLowDetail::Load` reads them by position).

The build also checks that the map is closed: a flood fill over walkable steps (50 degrees) from the centre must
not reach the edge of the tiles (`border` in the manifest, a warning otherwise).

### Validator

`validate.py` parses the files itself; it shares no code with the writer. It checks every chunk position, size,
offset and count above, the MCNK sub-chunk walk exactly as the client does it, name tables (MMID/MWID must list the
strings in order for `vmap4_extractor`), index ranges, unique ids across tiles, that an object reaching into a
tile is listed there, height and normal seams across chunks and tiles, WDL against the ADT corners, and that the
shipped ADTs match MAIN exactly (a flagged tile without an ADT makes the client load `ErrorCube.mdx` as terrain).
It also checks `Textures\Minimap\md5translate.trs` when the output has one: CR LF line ends, and that it is not our
lines alone (it is one global file; merge it with the stock one on the VPS).

The tools are data-free; on the VPS, give them the real data:

- `--assets <folder of extracted client files>` (validate and build): every texture, `_s.blp` companion and model
  exists, and MODF extents equal the real placed WMO box. `build.py --assets` takes the model boxes from there too.
- `--dbc <folder>` (validate): liquid types, area ids and ground effects exist in LiquidType, AreaTable and
  GroundEffectTexture.

### AzerothCore cross-check

`ac_crosscheck.py` packs the map with a one-row Map.dbc and a stand-in LiquidType.dbc into a fake
`Data/enUS/locale-enUS.MPQ` (MpqPack), runs AzerothCore's `map_extractor -e 1 -f 0` on it, reads the `.map` files
it writes and compares every height, area id, hole and liquid cell with the ADTs; with `--vmap4` it also runs
`vmap4_extractor`, which walks every ADT chunk by size. Build the tools in a separate folder:
`cmake -S bleakserv -B build-tools -G Ninja -DAPPS_BUILD=none -DTOOLS_BUILD=maps-only -DSCRIPTS=none
-DMODULES=none`, then `ninja -C build-tools map_extractor vmap4_extractor`.

### Terrain tests

```sh
python3 -I -m unittest discover -s Tools/MapForge/tests -p "test_terrain*.py"
```

They build small made-up maps and check the round trip through the validator, the header offsets, the MCNK
layout, height and normal continuity across chunks and tiles, normal direction, alpha sizes and layer limits,
texture, doodad and WMO index ranges, unique ids and tile spanning, the POI file and flat spots, the border check,
the corruptions the validator must catch (one per client or extractor rule), the real-data checks with made-up
DBCs and model files, the PNG, the CLI, golden bytes for a one-tile map and determinism. With
`MAPFORGE_AC_EXTRACTOR` (and optionally `MAPFORGE_AC_VMAP4`) set to built AzerothCore tools they also run the
cross-check.

### Not done yet

- Model boxes need game data: without `bounds` or `--assets`, WMO extents and footprints come from `radius`
  (the sample uses the asset kit's estimates). Rebuild on the VPS with `--assets`.
- One liquid layer per chunk; no MCLQ, no MCSH shadows, no MCCV vertex colours, no MFBO flight bounds, no minimap
  tiles (the trs merge must happen on the VPS from the stock file).
- Texture weights beyond a chunk's 4 layers are dropped for that chunk, which can show a seam where a fifth
  texture meets.
- The water depth byte uses 8 steps per yard; the client's depth table units are not confirmed.
- Nothing here was loaded in a real client: the format follows the decompiled readers and passes AzerothCore's
  extractors.
