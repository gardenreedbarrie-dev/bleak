# MapForge

Builds an original map for the 3.3.5a (12340) client and AzerothCore: the terrain files (`terrain/`), the DBC rows
that make the client and the server know the map, the patch archives players install, and the server SQL. The first
map is **Bleakhold Royale**, a 20-40 player free-for-all battle royale. Its current version, **Bleakhold Royale v2**
"Sunglass Lagoon", is a bright tropical valley (terrain `specs/royale_v2.json`, DBC config
`bleakhold_royale_v2.json`) and is the default in every command below; v1, the dark ruined valley
(`specs/royale_v1.json` with `bleakhold_royale.json`), still builds the same way. v2's terrain features (mountain
ranges, lakes, rivers with waterfalls, beaches, art from later expansions) are also shown on a small test bed,
`specs/royale_v2_demo.json`.

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

- **Map.dbc**: id **901**, directory `BleakholdRoyale`, InstanceType **3**, MaxPlayers 40, `timeOfDayOverride`
  **1050** (17:30 light; the client uses value / 1440). Values the config leaves out are copied from Warsong Gulch
  (489); the loading screen is Warsong's.
- **AreaTable.dbc**: zone **5200** on map 901 with the flags `ARENA` (0x80, free-for-all PvP for the whole zone)
  and `NO_FLY_ZONE`; ambience and music copied from Duskwood (`zone.template` 10). Subzones **5201-5213** (The
  Bleak Hold, Harrow Farm, ... The Overlook) copy the zone row, so they inherit `ARENA` and `NO_FLY_ZONE` and give
  the native zone text; the terrain spec's `areas` put them on the chunks. `clear_flags` drops every template flag
  that changes the rules (duels, rest, sanctuary, cities, ghost revival, indoor-only, outdoor PvP): the build
  **fails** when a zone or subzone row keeps any flag it did not set besides the harmless ones
  (`dbc/config.py` `HARMLESS_TEMPLATE_FLAGS`: unknown/unused bits and `OUTSIDE`), and `report.txt` lists the final
  flags, what the config set and what the template kept.
- **Light.dbc**: the map's default light (coordinates 0,0,0), next free id. All 8 LightParams slots point at the
  stock LightParams row that shows `Environments\Stars\WintergraspSmokySky.M2` (v1, `bleakhold_royale.json`). v2
  (`bleakhold_royale_v2.json`, the default) copies Sholazar Basin's whole light set instead (`params_from_light`
  1690: a bright blue sky, warm sun, clear water), fixes the time at noon (`time_of_day_override` 720), takes
  Un'Goro Crater's zone row as the template (`zone.template` 490, brighter character lighting) with
  Stranglethorn's jungle ambience and music (`ambience_id` 32, `zone_music` 3) and its own subzone names; everything
  else equals v1's config.
- **WorldMapArea.dbc**: next free id, bounds from the terrain's tiles widened to the world map's 1002:668 frame. Its
  name (`world_map_area.name`, `BleakholdRoyale`) is the folder of the world map art, `Interface\WorldMap\<name>\`
  ("Minimap and world map tiles" below).
- **BattlemasterList.dbc**: id **12** (a free BattlegroundTypeId), map 901, solo queue, levels 80-80. The client
  lists every BattlemasterList row with InstanceType 3 in its battleground UI.
- **PvpDifficulty.dbc**: one bracket, range index 7, levels 80-80, next free id (`GetBattlegroundBracketByLevel`
  needs it).
- **The patch marker** `Interface\Bleakhold\Royale\MarkerV2.blp` (`archives.marker_texture`; v1's config has
  `Marker.blp`): a 32 x 32 storm ring MapForge draws itself (`dbc/marker.py`, no game data) and converts with
  BlpConvert (DXT5, every mip). The Bleakhold addon tests it with `Texture:SetTexture` (`Royale.lua` `R.MARKER`):
  only a client with this version's patch-Q opens it. Each version names its own file, so a client still holding
  v1's patch-Q (v1 terrain under the same map id) cannot queue onto v2.
- **LoadingScreens.dbc**: nothing by default. `loading_screen: {"name", "file", "image", "wide_image"}` adds a row
  and 1024x1024 / 2048x1024 BLPs; the file path may hold only one dot, since the client inserts `Wide` before the
  first one.

**Ids.** Stock 3.3.5a maps end at 724 and AzerothCore's sources and SQL know none above it; the realm's own Emberwing
Hollow is map 740 (`mod-bleakhold`), so 901 keeps clear of both and of anything a pack installer may have added
near 740. The map id stays below 1000: the server names its map files with `%03u` and `mmaps_generator` overflows a
12-byte filter for 4-digit ids. Stock areas end below 5000, and the realm's own patches add areas 5006-5018, 5100,
5101 and more from 6001 on (its AreaTable row 5100 stopped the first build on the VPS), so the zone is 5200, its
subzones 5201-5213 and the places that are only POIs 5214-5217. Ids the server's own SQL already uses
(`--server-sql`, for example the fork's server-only WorldMapArea rows 1000 and 1001) are refused or skipped,
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
rows that name the M2. `light.skybox` finds the stock LightParams row of a given skybox (stock LightSkybox.dbc
spells every name `.mdx` while the files are `.M2`, so names match ignoring case and with either extension);
`params_from_map`,
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
DBCs. In use: H L R T V X Y Z (realm), A B C D E G I M N P S U (Reforged), J (WoW Forever's login patch), Q (this map),
4 (Tools/CafeForge's café archive) and 5 (this map's extractor copy); RaceForge writes customization art to
patch-6..9 and refuses taken names (`Tools/RaceForge/taken_patches.json`). Free: F, K, O, W and 6-9.

- **The map archive is `patch-Q.MPQ`**: the highest free letter, outside RaceForge's art letters and outside the
  launcher's HD pack (`Data/patch-[ABCDEGIMNPSU].MPQ` and `Data/Patch-Y.MPQ`), so every player has it. It holds
  `World\Maps\BleakholdRoyale\*.wdt/.wdl/.adt`, the loading screen, the minimap and world map tiles with the merged
  `md5translate.trs`, a marker file, the patch marker texture, and every modified DBC that no realm patch holds.
  Its paths are new, so its letter only has to beat the stock archives; the build fails if any other patch already
  holds one of them.
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
- `md5translate.trs` (minimap) is one global file: with minimap tiles, the build starts from the trs the players load
  today, adds one line per tile with CR LF line ends (the client drops a last line without one), and packs it into
  patch-Q; it fails if a later archive holds a trs. See "Minimap and world map tiles".

`package.py doctor --patches <folder>` lists the archives in load order with their packs and prints where each
DBC would go, without building anything.

### Build on the VPS

The real client and the realm's patches are on the VPS (`/srv/bleakhold-launcher/base` and `patches`):

```sh
cd /root/bleak/Tools/MapForge
python3 -I package.py doctor --patches /srv/bleakhold-launcher/patches --config bleakhold_royale_v2.json
python3 -I package.py pull --patches /srv/bleakhold-launcher/patches --out /root/mapforge/dbc \
    --config bleakhold_royale_v2.json
# copy the tables pull did not find (stock-only) from the server's data/dbc into /root/mapforge/dbc
# only for a spec with extra assets (art from later expansions, below): find the modern files
python3 -I package.py resolve-assets --spec <spec> --out /root/mapforge/assets \
    --sources /srv/bleakhold-launcher/patches [<Reforged MPQs or loose folders> ...] --listfile <3.3.5a listfile>
python3 -I terrain/build.py specs/royale_v2.json /root/mapforge/terrain [--assets <extracted client files>] \
    [--resolution /root/mapforge/assets/asset_resolution.json]
python3 -I package.py build --config bleakhold_royale_v2.json --dbc /root/mapforge/dbc \
    --terrain /root/mapforge/terrain --patches /srv/bleakhold-launcher/patches \
    --server-sql /root/bleakserv/data/sql --server-sql /root/bleakserv/modules --out /root/mapforge/out \
    [--minimap <tiles>/minimap --worldmap <tiles>/worldmap --trs <client Data folder>]
```

The last line ships the island's minimap and world map tiles ("Minimap and world map tiles" below). On the realm,
bleakserv's `deploy/maps/build-royale.sh` runs these commands in one go; its `deploy/maps/README.md` ("The island on
the minimap and the world map") is the owner's runbook for the tiles.

For v1, use `specs/royale_v1.json` and `bleakhold_royale.json` instead; a spec and a config always go together
(the subzone names differ). The exit code is 0 when every check passed; read `out/report.txt`. Then:

1. **Client**: put `out/client/patch-Q.MPQ` and every rebuilt realm archive in `out/client/` into
   `/srv/bleakhold-launcher/patches/` (upload under a new name and `mv` it into place; never overwrite a published
   file). A rebuilt archive replaces the realm's file of the same name. Players need a client restart.
2. **Server rows**: AzerothCore loads map_dbc, areatable_dbc, light_dbc, worldmaparea_dbc, battlemasterlist_dbc and
   pvpdifficulty_dbc over its `data/dbc` files by id (`LoadDBC` -> `DBCDatabaseLoader`; a row the files lack is
   added), so `data/dbc` stays as it is. Run `out/server/sql/bleakhold_royale_check.sql` on `acore_world` first; it
   must list nothing but rows of this map. Then add `out/server/sql/bleakhold_royale.sql` to bleakserv as
   `data/sql/updates/pending_db_world/rev_<timestamp>.sql` (`create_sql.sh` makes the name; `build --pending
   <that folder>` writes it directly). `bleakhold_royale_remove.sql` undoes it. The map points go the same way as
   their own rev file: `out/server/sql/bh_royale_poi.sql` (DELETE of map 901's rows, then the INSERT; the table
   layout is `bh_royale_poi_table.sql`). `package.py poi-sql --pois <terrain output> --out <folder>` writes just
   those two files from a terrain build, without DBCs.
3. **Server terrain**: `bash deploy/maps/install-map.sh --from-json /root/mapforge/out/server/extract/server-map.json`
   in bleakserv (its `deploy/maps/README.md`) makes the server's maps, vmaps and mmaps from
   `out/server/extract/patch-5.MPQ`. When the terrain places extra-asset doodads, that archive holds the terrain
   build's server copy (`server/World/Maps/<Dir>`), the same tiles without them, so vmap4_extractor reads only
   3.3.5 models. The extractors read only numbered patches, never lettered ones, so the
   installer stages that archive in a copy of the client as `Data/patch-5.MPQ` (the last archive map_extractor
   opens) and `Data/enUS/patch-enUS-99.MPQ` (vmap4_extractor opens locale patches -2 to -99 last, so a lower number
   could lose to a realm locale patch holding a Map.dbc).

   The archive is for the server only. Its Map.dbc holds **only this map's row** and it adds an **empty
   GameObjectDisplayInfo.dbc** (both in the client's exact layouts), so map_extractor and vmap4_extractor walk this
   one map and convert no game object models: seconds and a few MB instead of 30-90 minutes and several GB. That
   is safe because nothing else they read changes: map_extractor reads LiquidType.dbc from the stock archives,
   vmap4_extractor reads nothing else, neither reads AreaTable.dbc, and the installer keeps only this map's files
   (never `vmaps/GameObjectModels.dtree`). `build --full-extract-dbc` ships the full Map.dbc and no
   GameObjectDisplayInfo.dbc instead. The players' `patch-Q.MPQ` and the rebuilt realm archives are the same
   either way.

`package.py validate --config bleakhold_royale_v2.json --out <folder>` checks an output folder again, the map art
included: every minimap tile the merged trs lists and all twelve world map tiles must be there as 256 x 256 DXT1
BLPs the client draws; art that is not there at all is a note.

### Minimap and world map tiles

The island on the minimap and on the stock world map (M, Shift-M) is art in patch-Q. It is drawn by
`Tools/BlpConvert/make_royale_art.py --tiles <tiles>` from the terrain spec (Pillow and numpy; about two minutes,
most of it the terrain build), from the same render as the HUD's island map, so all three match:

- `<tiles>/minimap/map<X>_<YY>.png`: 256 x 256 per ADT tile of the WDT (9 for the 3 x 3 map), north up, west left.
- `<tiles>/worldmap/BleakholdRoyale1..12.png`: the 1024 x 768 world map picture in 4 x 3 tiles of 256, row-major,
  the stock world map's layout (`NUM_WORLDMAP_DETAIL_TILES`). Its top-left 1002 x 668 is the map frame, which
  WorldMapArea's bounds stretch over the island's tiles widened to 1002:668: the island fills the height, the sea
  the sides.

Give it `--out <scratch folder>` on the VPS: without it, it also rewrites the HUD art in the checkout, and
build-royale.sh stops on a clone with local changes.

`package.py build` packs them:

- `--minimap <tiles>/minimap`: each tile as `Textures\Minimap\<Directory>\map<X>_<YY>.blp` (DXT1; the build fails
  when the tiles are not exactly the WDT's), plus `Textures\Minimap\md5translate.trs`, the client's one global name
  table (`LoadMD5Names`, `MinimapBuildSource`: a tile it does not list is never drawn). The merged trs starts from the
  one the players load today: `--trs`, a file or a client's Data folder (or build-royale.sh's stage,
  `/root/mapforge/stage`), read like the client (the top patch archive that holds it with every pack on, the map
  archive left out; else the base archives in `OpenArchives`' order: expansion, lichking, common, common-2, the
  locale ones); without `--trs`, the top copy in `--patches` outside patch-Q, else patch-Q's own (an earlier merge,
  whose lines for this map are replaced). Shipping only our lines would break every stock map's minimap, so a build
  with none of these fails.
- `--worldmap <tiles>/worldmap`: `Interface\WorldMap\<name>\<name>1..12.blp`, `<name>` the config's
  `world_map_area.name`: all twelve or the build fails (a tile the client cannot load keeps the picture of the map
  it showed before, Scarlet Monastery's for this map id), each a 256 x 256 PNG (converted to DXT1, one level:
  interface textures are drawn with plain linear filtering and no mips) or a DXT1 BLP of that size, never resampled.
- Every name goes through the same collision check as the terrain: a realm archive that already holds one stops the
  build.
- **A rebuild keeps them.** A build that is not given `--minimap` or `--worldmap` ships those of patch-Q in
  `--patches` again (when MapForge wrote it and it holds them whole), so a new MapForge or a changed realm patch,
  which build-royale.sh rebuilds by itself, never takes the island off the players' minimap and world map.
  `--drop-map-art` leaves them out. `MapForge\mapart.txt` in the archive records what it holds and a fingerprint of
  the terrain they were made for; when the terrain changes, the build keeps them but warns: render them again.
- The patch marker stays `MarkerV2`: the terrain is unchanged, so players with an older patch-Q can still queue;
  they lack only the tiles (the addon covers the stock world map until they have them).
- `package.py doctor --config <config>` also says how many minimap and world map tiles the realm's patch-Q holds.

### Extra assets (art from later expansions)

A terrain spec can name a texture or doodad from a later expansion wherever it names a path:
`{"modern": "<path>", "fallback": "<3.3.5a path>", "kind": "texture" | "doodad"}` (WMOs stay 3.3.5 files, since
vmap4_extractor builds the server's collision from them). One ADT serves every player, so a modern file counts only
when it reaches every player: it must end up in patch-Q.

- `package.py resolve-assets --spec <spec> --out <folder> --sources <folder or MPQ> ... [--listfile <file>]` runs
  where the art is (the VPS). Sources are searched in the order given, the first one holding a file wins: an MPQ,
  or a folder (its `patch-?.MPQ` and locale patches in the client's load order, then its other `*.MPQ`, then its
  loose files). When the winning copy cannot be read (an imploded or LZMA file, which the client reads, or a
  damaged sector) the asset falls back with that reason and a warning; a lower source's copy, perhaps another
  version, is never taken instead. For each modern path it collects what the file needs: a texture's
  `<name>_s.blp` (copied when a source has it; without one the build sets the texture's MTXF flag 1), a model's
  `<name>NN.skin` files (one per skin profile), the textures its texture table names and the `.anim` files of its
  streamed sequences. Files a 3.3.5a listfile holds (`--listfile`: plain or `path<TAB>archives` lines, or an asset
  kit JSON; a retail `listfile.csv` of `id;path` lines is refused, since its paths are not in every client) are in
  every client and are not copied; a modern path found there resolves as `stock` (a stock model stays in the
  server's copy of the tiles). Everything else found is **copied** to `<folder>/files/`, once per file whatever
  the spelling two models use (a file found only in the launcher's optional HD pack is copied too, never just
  referenced), and `<folder>/asset_resolution.json` says, per modern path, `resolved` with its files (size,
  sha256, source) or `fallback` with the reason. A modern path falls back when it or any dependency is missing or
  unreadable, when a name it brings is not a plain relative path (empty, `.` or `..` parts, a drive or a leading
  separator: source archives are third-party files), when a texture is not a BLP, for M2s the client cannot load
  (before version 264, which keep their skins inside, and anything but MD20 264 and 272-274), and for M2s that
  name their files by FileDataID (SFID, TXID, AFID, SKID, BFID chunks: Legion and later retail files): Bleakhold's
  client converts retail M2s (WarcraftXL), but it resolves FileDataIDs through `listfile.csv`
  (`Engine/Source/ModernAssets/ModernAssetsListfile.cpp`), which players without the HD pack do not have, and that
  file is global (a partial copy in patch-Q would hide the HD pack's). The client loads an MD20 at 264 as it is
  and converts 272-274, as MD20 or inside an MD21 chunk (`ModernAssets.cpp` MayTransform, WarcraftXL's
  `Contract.hpp`); `M2Init` refuses every other version, so such a model would be invisible.
- `terrain/build.py ... --resolution <folder>/asset_resolution.json` uses each resolved modern file and the
  fallback for the rest; without `--resolution` every extra asset falls back, so a build works offline. Scatter
  picks, positions and unique ids do not depend on the choice. The build copies the modern files the tiles use to
  `extra_assets/` (listed with their hashes in the manifest's `extra_files`) and, when it places modern doodads,
  writes `server/World/Maps/<Dir>/`: the same WDT, WDL and tiles without them.
- `package.py build --terrain` packs `extra_assets/` into patch-Q (it stops when a file differs from the manifest)
  and notes realm archives that hold the same path: the same bytes are fine; a different copy in an archive that
  loads over patch-Q is what its players see (a warning). `server/extract/patch-5.MPQ` gets the server copy.
- Modern doodads are decoration: the server never sees them, so they have no collision or line of sight there. The
  client may still collide with a model that has collision triangles; the build warns about each one.

### Output

| Path | Contents |
|---|---|
| `client/patch-Q.MPQ` | terrain, textures, extra assets, minimap and world map tiles, DBCs no realm patch holds |
| `client/<realm archive>.MPQ` | each realm archive that wins for a modified DBC, rebuilt with the rows |
| `client/DBFilesClient/*.dbc` | the modified tables, forged on the input copies |
| `server/sql/bleakhold_royale.sql` | the install: DELETE + INSERT per table, passes `codestyle-sql.py` |
| `server/sql/bleakhold_royale_check.sql`, `_remove.sql` | the pre-install check and the removal |
| `server/sql/bh_royale_poi.sql`, `_table.sql` | the server's map points from `pois.json` (with `--terrain`) |
| `server/extract/patch-5.MPQ` | server only: terrain (no modern doodads), 1-map Map.dbc, empty GameObjectDisplayInfo |
| `server/extract/server-map.json` | `{"map_id", "dir", "patch"}` for `install-map.sh --from-json` |
| `report.txt` | every decision and check |

### Config

`bleakhold_royale_v2.json` (v2) and `bleakhold_royale.json` (v1): `map` (id, directory under 64 characters,
template, name and per-locale `names`, instance_type, flags, corpse, `time_of_day_override` (null: the template's;
"off" or -1: the natural day cycle; 0-1440: a fixed time in minutes), expansion, max_players), `zone` (id, template,
name, `set_flags`/`clear_flags` by `AREA_FLAG_*` name, area_bit or automatic, sounds or the template's, `subzones`),
`loading_screen` (null, an existing id, or a new row), `light`, `world_map_area` (bounds `"auto"` from the terrain
or `[left, right, top, bottom]`), `battleground` (BattlemasterList id and template, queue rules, PvpDifficulty
brackets) and `archives` (map archive name, DBC mode, the launcher's optional packs, reserved letters,
`marker_texture`). Null values are copied from the template row.

**The POI SQL.** `bh_royale_poi (map, id, kind, name, x, y, z, o, radius, weight, param, PRIMARY KEY (map, id))`
in the world database, one row per `pois.json` entry: `name` is the POI's `title` (or its name), `o` its facing in
radians, `z` the spawn height (the server snaps it to the floor below z + 2). When the points hold Royale kinds,
the build also checks what the server's startup validation refuses: one lobby, at least 3 landmarks, 2 Shadow
Sight orbs, at least 44 common crate spots, at least 2 supply sites, at least one final site, every final site at
most 490 yd from the map centre, and each kind's params and weights.

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
and the whole build. `tests/test_package_mapart.py` covers the map art: the world map tiles (names, all twelve, 256 x
256 DXT1 with one level, BLPs passed through, collisions, a config without a world map), the minimap tiles and where
the merged trs starts (a realm patch, patch-Q's earlier merge, a trs that loads over patch-Q, a client Data folder
with patch and base archives, an archive that cannot be read), a rebuild that keeps the art byte for byte, new tiles
over kept ones, `--drop-map-art`, art made for other terrain, art there only in part, and validate and doctor.

## Terrain

`terrain/` writes the map's own terrain from a JSON spec: the WDT, the WDL and one ADT per tile, laid out as
`World\Maps\<Dir>\` for the map archive. The spec is ours (heights, textures by rule, placements of stock models by
path); no Blizzard file is copied. The map is `specs/royale_v2.json`, Bleakhold Royale v2 "Sunglass Lagoon"
(royale-spec.md 2, 3.3-3.6, 6.6; its `_comment` describes it): the same 3 x 3-tile frame, ids and storm centre
as v1, a mountain ring around a bright valley with the Sunglass Lagoon and Sunstair Isle at the centre, nine final
sites, four rivers with waterfalls, mountain pools, beaches, the Sunwatch Overlook lobby balcony in the
north-west peaks and 117 Royale POIs (13 landmarks, 3 crossings, an explicit `centre`, 58 common crates and 6
strongboxes, 16 supply sites). `specs/royale_v1.json` is Bleakhold Royale v1 (royale-spec.md 2.1-2.4):
a 3 x 3-tile solo battle royale with the ruined keep plateau in the centre (ring A), four outer landmarks (ring B:
Harrow Farm, Blackvein Pit, Gloomtimber Mill, The Pale Shrine), seven inner sites where the storm ends (ring C),
the Overlook lobby mesa in the north-west corner, a river with three crossings (Old Ford, Covered Bridge, Pit
Bridge), dirt roads between the sites, about 1,000 scattered cover doodads, the Royale POIs (lobby, landmarks,
crossings, 44 common crates and 6 strongboxes, 2 Shadow Sight and 8 buff orbs, 6 supply sites, 8 final sites)
and a cliff ring that closes the edge. `specs/royale_draft.json` is the earlier draft it grew from.

`specs/royale_v2_demo.json` is a 2 x 2-tile test bed for the v2 features, not the v2 map: a mountain range rings a
bright valley, a terrace in the north holds a tarn (Slow Water), a river falls from a gorge onto the terrace and
over its edge into a lagoon with an island (two waterfalls), beaches paint every shore, and five extra assets
(beach sand, the waterfall, two palms, the grass) name modern files from the v2 asset kit with 3.3.5 fallbacks.

```sh
python3 -I Tools/MapForge/terrain/build.py Tools/MapForge/specs/royale_v2.json out/terrain [--force] \
    [--resolution asset_resolution.json]
python3 -I Tools/MapForge/terrain/validate.py out/terrain [--assets <extracted client files>] [--dbc <dbc folder>] \
    [--listfile <3.3.5a listfile or asset kit>] [--resolution asset_resolution.json]
python3 -I Tools/MapForge/terrain/ac_crosscheck.py out/terrain --extractor <build>/src/tools/map_extractor \
    [--vmap4 <build>/src/tools/vmap4_extractor] [--client]
```

`build.py` writes, besides `World/Maps/<Dir>/`:

- `pois.json`: the named points (`pois`) for the server's spawn table (`bh_royale_poi`): id, name, kind, title,
  x, y, `z` (the spawn height), `ground` (the terrain height), `z_source` (`ground`, `explicit` or
  `placement:<label>`), facing, radius, weight, param; plus the map id, the world bounds and the counts per kind.
  It sits next to `World/`, not inside it, so the archive gets only client files.
- `terrain_manifest.json`: map id and directory, tiles, world bounds, the MCNK area ids, every placement with its
  unique id, resolved position and tiles, the border check, the roads, the scatter statistics (candidates, placed,
  rejections per mask), the doodad and POI counts, the chunks that hold more than 4 textures, warnings and file
  hashes. `package.py --terrain` reads it (directory, tiles, area ids) and packs `World/Maps/<Dir>/`.
- `preview.png`, `heightmap.png`: top-down views, north up. Texture colours shaded by the slope, water, WMOs (red),
  doodads (yellow; scattered ones as single darker pixels), POIs by kind (lobby white, landmarks magenta, crossings
  cyan, crates orange and strongboxes red, Shadow Sight purple, buff orbs green, supply sites yellow, final sites
  light blue with a ring at the last circle's 35 yards), waterfalls white, modern doodads cyan; grey levels by
  height.
- With extra assets resolved: `extra_assets/` (the modern files the tiles use, for patch-Q) and, when modern
  doodads are placed, `server/World/Maps/<Dir>/` (the same map without them, for the server's extractors). The
  manifest then lists every use (`extra_assets`: where, modern, fallback, which one is used and why), the files
  (`extra_files`) and the server copy (`server_tiles`, `server_doodads_left_out`); with mountains, lakes, rivers
  or beaches it also gets `mountains`, `lakes`, `rivers` (levels, falls, waterfall doodads), `water_merged_chunks`,
  `water_dropped_cells` and `beaches`. Specs that use none of these get the same files and manifest as before.

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
  `package.py` adds, the zone id in `bleakhold_royale_v2.json`), `uid_base` (first automatic unique id).
- `heightmap`: `base`, `noise` layers (`scale` in yards, `amplitude`, `octaves`, `persistence`, `lacunarity`,
  `seed`) and `features`, applied in order:
  `hill` (`center`, `radius`, `height`, `shape` smooth/cone/dome), `flatten` or `plateau` (`shape`, `height` or
  null for the terrain height at its centre, `offset` added to it, `falloff`, `mode` set/raise/lower; a mesa is
  `height` null, `offset` 25, `mode` raise), `river` (`path`, `width`, `bank`,
  `bed` height), `ramp` (`from`/`to` `[x, y, z or null]`, `width`, `falloff`), `border` (adds `height` within
  `inset` yards of the tile range's edge, fading over `width`, `jitter` for a natural line; stack a wide ridge and
  a steep wall for a cliff), `mountains` (below), `water_bodies` (marks where the lakes and rivers carve; without
  it they carve after every feature, before the POIs flatten their spots), `clamp` (`min`, `max`).
- `mountains`, a range along the whole edge in place of a `border` ring: `width` (its depth from the tile edge
  to the foot, where the valley ends), `height` (`[lowest, highest]` peaks above the foot, varied along the range
  by low-frequency noise), `cliff` (`height`, `width`: the wall at the foot), `layers` (1-5 ridge lines, foothills
  nearest the valley, the back range highest), `peak_scale` (spacing of peaks), `saddles` (0-1, how deep the dips
  between peaks go), `ledges` (`step`, `flat`, `coverage`: terraced shelves at noise-shifted heights where a noise
  mask allows, or null), `jitter`/`jitter_scale` (the foot line wanders), `corner_radius`, `seed`. Each ridge is a
  bump across the band times sharp ridged noise along it; the mass rises behind the cliff so the highest crests
  reach the peak height above the foot. Only exact IEEE operations (and floor), like every other feature.
- `lakes`: `name`, `shape`, `level`, `liquid_type` (default 1), `depth` (basin depth, reached `shelf` yards in
  from the shore), `shore` (yards outside where the land blends to `freeboard` above the water: low ground becomes
  a bank, high ground a beach), `min_depth`, `islands` (`center`, `radius`, `height` above the water).
- `rivers`: `name`, `liquid_type`, `width`, `depth`, `bank`, `freeboard`, `min_depth`, `fall_run`, `reaches`
  (`level`, `path`), `waterfall`. Each reach holds its water at one level, falling downstream; reach k + 1
  continues from the last point of reach k. The channel is carved `depth` below each reach's water (built up into
  an embanked channel where the ground is lower, except inside lakes), the banks stand `freeboard` above the water
  and blend back over `bank` yards, and each step is spread over `fall_run` yards of the bed. Where the level
  drops, `waterfall` places its `model` at the step (scaled to the drop when `height`, the model's own drop, is
  given; `anchor` top or bottom, `facing_offset`, `z_offset`) and its `splash` `splash_offset` yards downstream on
  the lower water (`splash_scale`, `splash_z_offset`). The model paths come from the asset kit; either may be an
  extra asset. Waterfall doodads get ids after the spec's own placements, before the scatter.
- `beaches`: `sand`, `wet_sand`, `riverbed`, `lakebed` (texture names; `lakebed` defaults to the riverbed),
  `width`/`fade` (sand within that many yards of any water edge), `height`/`height_fade` (at most that far above
  the water), `wet_width`, `wet_height`, `wet_depth` (wet sand at the waterline, above and under it), `bed_fade`,
  `slope_max` (no sand on steeper ground), `edge_noise`/`noise_scale`, `strength`, `exclude` (shapes without
  sand) and `fall_clearance` (no sand within that many yards of a waterfall, default 18). The rules paint at a
  `{"beaches": true}` entry in `texture_rules`, or after every rule. They read a water field over the lattice:
  which points are under water (and the level), and for dry points the nearest submerged point (two integer
  sweeps, exact everywhere).
- `textures`: `name`, `path` (`.blp`, or an extra asset), `color` for the preview, `effect_id`
  (GroundEffectTexture for ground clutter), `mtxf_flags` (1 when the texture has no `_s.blp`: with specular terrain
  on, the client loads `<name>_s.blp` unless MTXF flag 1 is set, `CMapArea::LoadTerrainTexture`; for an extra
  asset it applies to the fallback, and a used modern texture gets 0 or 1 by whether its `_s.blp` ships).
- Extra assets: wherever a texture path, a doodad model, a scatter model or a waterfall model goes,
  `{"modern": path, "fallback": 3.3.5a path, "kind": "texture" | "doodad"}` (`kind` may be left out; it must match
  the field). See "Extra assets" above.
- `texture_rules`: the first texture covers everything, then each rule paints its texture over with a coverage
  made of `shape` + `fade`, `slope` (`min`/`max` degrees), `height` (`min`/`max`/`fade`), `noise` (`scale`,
  `threshold`, `fade`) and `strength`. An entry `{"roads": true}` marks where the roads paint (without it they
  paint before every rule). A chunk holds at most 4 textures: the build warns about every chunk where a fifth one
  had weight (`texture_overflow_chunks` in the manifest), so keep regional textures a chunk apart.
- `roads`: `name`, `points` (a polyline), `width` (default 7), `fade` (default 4), `texture`, `strength`: a texture
  painted along the line, and a mask the scatter groups keep clear of.
- `doodads` (`.m2`) and `wmos` (root `.wmo`): `model`, `position` `[x, y]` (on the ground) or `[x, y, z]`,
  `z_offset`, `facing` (the server's orientation in degrees) or raw `rotation` `[x, y, z]` in file order, `scale`
  (doodads only), `uid`, `bounds` (model box, used when `--assets` does not have the model), `radius` (fallback footprint), and for WMOs `doodad_set`,
  `name_set`. Chests, orbs and other interactive things are server GameObjects, not terrain doodads.
- `water`: `liquid_type` (stock LiquidType id, 1 = water), `height`, `shape`, `min_depth`: flat water in a shape,
  without carving (v1's river and pond).
- `holes`: shapes cut out of the terrain (none in the royale map: players drop in anywhere).
- `scatter`: deterministic cover. Each group has `name`, `seed`, `models` (`model`, `weight`, `radius` for the
  footprint, `body` for spacing (default radius / 2), `scale` `[min, max]`, `z_offset`), `density` (candidates per
  10,000 square yards) or also a `count` cap, `min_spacing` within the group, an optional `shape` and `exclude`
  shapes, `slope` `{max}`, `height` `{min, max}`, `noise` (`scale`, `threshold`, `fade`: clusters and lanes),
  `clearance` in yards from `roads`, the `river` (river features), `pois` (beyond each POI's radius; `poi_kinds`
  limits it to some kinds) and the spec's own `placements` (always on, 1 by default), `dry` (default true: never in
  water), `facing` (fixed; random otherwise). One candidate per cell of a jittered grid (`count` groups take the
  cells in a hashed order); a candidate stays when it passes every mask and its body clears every doodad scattered
  before it. Integer hashing only, so the same spec gives the same doodads everywhere; they get ids after the spec's
  own placements and labels `<group> #<n>`.
- `pois`: `name`, `kind`, `position`, `radius`, `flatten` (true or `{falloff}`: the whole radius becomes flat
  ground at the terrain height of its centre), `id` (the server key; the rest get the next free ids from 1),
  `title` (the name players see), `facing`, `weight`, `param`, `z_offset`, and `z_from` (the label of a WMO or
  doodad: the point takes that placement's z, plus `z_offset`, for crates inside buildings). The Royale kinds have
  fixed rules: `lobby`, `landmark`, `crossing`, `orb_shadow`, `supply_site` (param 0), `crate` (param 1 common, 2
  strongbox), `orb_buff` (param 1 speed, 2 restoration, 3 berserk) and `final_site` (an integer weight above 0;
  only final sites carry a weight). Other kinds are free-form. A `landmark` is also a landing point: the server
  drops a player with no pin (or no valid ground near it) there, and the boundary rule may send players back to
  one, both at the highest surface, so it stands on open, flat, dry ground outside every WMO box, not on a roof.
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
  it). MODF extents are the placed model box: from the real model with `--assets` (MOHD of a WMO, the header box
  of an M2; it wins over `bounds`, because a realm patch such as an HD pack can replace a model with a bigger
  one), else from `bounds`, else a cube of `radius` as a fallback.
- **Water**: MH2O, one liquid instance per chunk, vertex format 0 (heights + depth), fishable bits for the wet
  cells, deep 0, an 8-byte exists bitmap (AzerothCore reads a whole u64), the rectangle of the wet cells (a river
  bank that crosses a chunk gives a partial rectangle and bitmap). A cell is wet where a body's shape holds its
  centre (a river's also where it holds one of the cell's corners: its rounded bed stays under the water out to
  about 0.9 of the half width) and the terrain dips below that body's level there; where several bodies hold a wet
  cell the lowest water wins. Levels are per cell: every vertex takes the level of the cell it is the top-left
  corner of (else of a wet cell to its left or above), min/max are the vertex range. Both readers agree on that
  layout: the client reads `(width + 1) * (height + 1)` heights row by row and the exists bit `col + width * row`
  (`CChunkLiquid::CreateVertXY`, `TileExists`), map_extractor the same (`System.cpp`, MH2O pass), and the server
  keeps one level per cell at its top-left vertex (`GridTerrainData::GetLiquidData`), a vertex only that chunk or
  an earlier one in the extractor's loop writes, so per-chunk and per-reach levels survive cell by cell. The
  client interpolates a cell's four corners, so every wet cell has all four at its own level: a cell next to
  higher water inside a chunk (any of its 8 neighbours) stays dry, or the client would draw it sloping below the
  ground at the lip while the server held the upper level over the whole cell (a player there would be under
  water on dry ground). A step inside a chunk leaves a one-cell gap at the foot of the fall, a step on a chunk edge
  a step; the waterfall model covers both.
- **Several water bodies**: in different chunks they simply coexist (any number, any liquid types). Where two meet
  in one chunk, cells of the chunk's first-listed liquid type are merged into its one instance, each keeping its
  own level (`water_merged_chunks`); cells of another liquid type are dropped with a warning
  (`water_dropped_cells`), because the client would draw a second instance (`CMapChunk::CreateLiquids` loops over
  them) but AzerothCore's map_extractor reads only the first instance and keeps one liquid type per chunk, so the
  server would not know that water. Keep bodies of different liquid types a chunk apart.
- **WDL**: MVER, empty MWMO/MWID/MODF, MAOF, then MARE (17 x 17 + 16 x 16 heights) and MAHO per tile
  (`CMapLowDetail::Load` reads them by position).

The build also checks that the map is closed: a flood fill over walkable steps (50 degrees) from the centre must
not reach the edge of the tiles (`border` in the manifest, a warning otherwise). The fill swims: a point under
water counts at the water surface, so a carved river bed (steeper than walking allows, but under water up to its
lip) does not cut the fill off from the far bank. With mountains the fill starts from every point of the valley
(players can be dropped anywhere in it, so a mesa or a river at the centre cannot hide a way out), and it also
needs walkable ground under every dry point (its normal within 50 degrees): the client stops a character on a
steeper surface in any direction, and a wandering foot line would otherwise let a rise-per-step fill zigzag up the
cliff. It then reports how far into the range the walkable ground reaches (`border.mountains.deepest_yards`) and
warns when that passes the cliff at the foot (players could leave the valley there). Specs without mountains keep
the rise-per-step check from the centre.

### Validator

`validate.py` parses the files itself; it shares no code with the writer. It checks every chunk position, size,
offset and count above, the MCNK sub-chunk walk exactly as the client does it, name tables (MMID/MWID must list the
strings in order for `vmap4_extractor`), index ranges, unique ids across tiles, that an object reaching into a
tile is listed there, height and normal seams across chunks and tiles, WDL against the ADT corners, and that the
shipped ADTs match MAIN exactly (a flagged tile without an ADT makes the client load `ErrorCube.mdx` as terrain).
It also checks `Textures\Minimap\md5translate.trs` when the output has one: CR LF line ends, and that it is not our
lines alone (it is one global file; merge it with the stock one on the VPS). And `pois.json` next to `World/`: the
map directory, unique names and ids, kinds with fixed params and weights, every point on the tiles, final sites at
most 490 yd from the centre, and no point below the terrain it stands on. MH2O: liquid types, vertex formats,
rectangles, every offset in range, vertex heights finite and inside `[minHeight, maxHeight]` (the client culls
the water by that box), an exists bitmap with at least one cell (map_extractor reports "Wrong liquid detect"
otherwise), every wet cell's four corners at one height (the client interpolates them, the server keeps the
top-left one for the whole cell), a warning for a second instance (the server ignores it). The server's extract copy
(`server/World/Maps/<NAME>`, when present): its own full check, the same tiles, heights, holes, areas, water and
WMOs as the client tiles, and doodads that are the client's minus extra assets only; client tiles that place
extra-asset doodads without a server copy are an error.

The tools are data-free; on the VPS, give them the real data:

- `--assets <folder of extracted client files>` (validate and build): every texture, `_s.blp` companion and model
  exists, and MODF extents equal the real placed WMO box. `build.py --assets` takes the model boxes from there too.
- `--dbc <folder>` (validate): liquid types, area ids and ground effects exist in LiquidType, AreaTable and
  GroundEffectTexture.
- `--listfile <3.3.5a listfile or asset kit>` (validate, repeatable): every texture, `_s.blp` the client will load
  (MTXF flag 1 off) and model the tiles name is a 3.3.5 listfile path or an extra asset the output ships
  (`extra_assets/`); WMOs must be 3.3.5 paths. `--resolution <asset_resolution.json>`: the shipped files match the
  resolution's hashes, and no modern path that fell back is named.

### AzerothCore cross-check

`ac_crosscheck.py` packs the map with a one-row Map.dbc and a stand-in LiquidType.dbc into a fake
`Data/enUS/locale-enUS.MPQ` (MpqPack), runs AzerothCore's `map_extractor -e 1 -f 0` on it, reads the `.map` files
it writes and compares every height, area id, hole and liquid cell with the ADTs, including each wet cell's level
(per chunk and per reach) and that dry cells read -500; with `--vmap4` it also runs `vmap4_extractor`, which walks
every ADT chunk by size. When the output has the server's extract copy it checks that copy (what the server
extracts); `--client` checks the client tiles. Build the tools in a separate folder:
`cmake -S bleakserv -B build-tools -G Ninja -DAPPS_BUILD=none -DTOOLS_BUILD=maps-only -DSCRIPTS=none
-DMODULES=none`, then `ninja -C build-tools map_extractor vmap4_extractor`.

### Terrain tests

```sh
python3 -I -m unittest discover -s Tools/MapForge/tests -p "test_terrain*.py"
```

They build small made-up maps and check the round trip through the validator, the header offsets, the MCNK layout,
height and normal continuity across chunks and tiles, normal direction, alpha sizes and layer limits, texture,
doodad and WMO index ranges, unique ids and tile spanning, the POI file and flat spots, the POI kinds, ids, `z_from`
and the `pois.json` checks, roads, the flatten offset, the 4-layer warning, scatter (determinism, weights, spacing,
every mask, counts, ids), the v1 map's content (POI counts, final-site reach and cover, the mesa, the look brief's
models, roads, subzones and atmosphere), the border check (swimming across a river, a fill from the whole valley),
mountain ranges (peak heights, saddles, ledges, the cliff, closure for several seeds, rounded corners, determinism,
limits), lakes and rivers (per-cell levels through an emulation of map_extractor's MH2O pass, two levels in one
chunk at a fall with no wet cell sloping between them, wet bank cells over the rounded bed, partial chunks, liquid
types, merging and dropping where bodies meet, the carved bed, banks and lake basin, waterfall placements), beaches
(sand, wet sand and beds by distance, height, depth and slope, exclusions, the water field), extra assets
(fallbacks, a resolution's choices, MTXF flags, the server copy, the validator's path rules), the v2 config and the
v2 demo (built once and checked end to end), the corruptions the validator must catch (one per client or extractor
rule), the real-data checks with made-up DBCs and model files, the PNG, the CLI, golden bytes for a one-tile map and
determinism. With `MAPFORGE_AC_EXTRACTOR` (and optionally `MAPFORGE_AC_VMAP4`) set to built AzerothCore tools they
also run the cross-check on the golden map, the river-and-lake map and a map with a server copy.
`tests/test_package_assets.py` covers resolve-assets (source order, an unreadable top copy, a model's skins, textures
and anims, one copy per spelling, unsafe names, retail listfiles, the M2 versions the client loads, stock models,
fallbacks) and how `package.py build` ships extra assets.

### Not done yet

- Model boxes need game data: without `bounds` or `--assets`, WMO extents and footprints come from `radius`
  (the sample uses the asset kit's estimates). Rebuild on the VPS with `--assets`, and check there what only the
  real models show: the Pit Bridge's deck height and length (`ArathiStoneBridge01.wmo` at z 3.6, facing 103), the
  covered bridge, the Overlook's collision ring (`CollisionWallPvP01.m2` segments), floor heights for the crates
  inside buildings (`z_from` + 0.3), and the frame rate with about 1,300 doodads (the scatter densities are the
  knob).
- One liquid instance per chunk (bodies of another liquid type are dropped where they share a chunk) and one
  liquid type per river (no fast-water rapids below a fall); water surfaces are flat per reach (a step at each
  fall, no sloped water); no MCLQ, no MCSH shadows, no MCCV vertex colours, no MFBO flight bounds.
- The minimap has tiles only inside the WDT: near the map's edge (the lobby balcony in a corner) the rest of the
  round minimap stays black.
- Waterfall models are placed at the step with the spec's `height` as their own drop; the real models' heights
  and origins need checking on the VPS (`--assets` gives their boxes) or in a client.
- Mountain ledges are flat shelves above the cliff: unreachable on foot, but a player who parachutes onto one
  stands there until the storm takes them.
- Extra assets: models that name files by FileDataID always fall back (the client's `listfile.csv` is global and
  only the HD pack has it); modern doodads have no server collision or line of sight; modern terrain textures were
  made for retail terrain scaling and may tile differently.
- Texture weights beyond a chunk's 4 layers are dropped for that chunk, which can show a seam where a fifth
  texture meets.
- The water depth byte uses 8 steps per yard; the client's depth table units are not confirmed.
- Nothing here was loaded in a real client: the format follows the decompiled readers and passes AzerothCore's
  extractors.
