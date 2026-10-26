# RaceForge

Adds the Bleakhold races to your own 3.3.5a game data:

| Race | Id | Faction | Template race (models, sounds, classes) | Faction race (language, reputation, start zone) | Racials |
|---|---|---|---|---|---|
| High Elf | 22 | Alliance | Blood Elf (10), helmet prefix `Be` | Human (1), starts in Northshire | Wind Blessed (90500); not Blood Elf's |
| Eredar | 23 | Horde | Draenei (11), helmet prefix `Dr` | Orc (2), starts in the Valley of Trials | Elemental Insight (90501), Read Ley Line (90502); not Draenei's |

RaceForge reads the DBC files of your client and writes:

- patched copies of every table it changes, once for the client and once (identical) for the server, including the
  races' own racial spells and the server-cast spells of races.json as new Spell.dbc rows (see "Racials and spells");
- an MPQ with the client copies (with `--mpq`), built with `Tools/MpqPack`;
- the AzerothCore world-database SQL;
- a report with every change and the result of its checks.

No Blizzard data is in this folder or in the repository: the tool only works on files you give it, and its tests
use made-up tables. The DBC layouts come from the client's own record classes in `WoW/Source/DB/Rec` (the client
aborts when a DBC's column count or row size is different).

It needs Python 3.10 or newer and nothing else. Run it with `-I`.

The client side of the races (ids up to 31, Blood Elf and Draenei scenes, voices and Death Knight filters for the
new races) is already in the decompilation, `BLEAKHOLD(races)`. The character creation screen needs Bleakhold glue
UI as well: the stock GlueXML has 10 race buttons and stops with "Too many races!" when ChrRaces holds more playable
races. Install the races together with that glue UI. The new races use the template races' models; HD models are a
later step.

## The easy way

The CI package (`Tools\BleakholdRaceForge.exe`, no Python needed) and `raceforge.py` without a command both
run the same build: double-click it and drag your DBC folder into the window, or drop the folder onto it. The
output goes to `Bleakhold-RaceForge-Output` next to that folder (running it again replaces it), with the archive
`client\patch-R.MPQ`, the server DBCs and SQL, and `report.txt`.

## Step by step (Windows)

The examples assume the decompilation in `C:\bleakhold\wowdecomp`, the client in `C:\WoW335`, AzerothCore in
`C:\azerothcore`. On Windows the Python launcher is `py -3`; elsewhere use `python3`.

1. **Get your DBCs.** Use the DBCs the client actually reads: the newest copy of each file, from the highest
   patch. The easiest source is the server's `data\dbc` folder, which AzerothCore's extractor made from the same
   client. You can also extract `DBFilesClient\*.dbc` from the client's archives with an MPQ tool, opening the locale
   archives with their patches (`Data\enUS\locale-enUS.MPQ`, `patch-enUS.MPQ`, `patch-enUS-2.MPQ`,
   `patch-enUS-3.MPQ`). If you already ship custom DBCs (custom items, spells), start from those.

2. **Check `Tools\RaceForge\races.json`.** It holds the two races. Change ids, names, start positions or the class
   list there (see below), or copy it and pass `--config`.

3. **Build:**

   ```bat
   cd C:\bleakhold\wowdecomp
   py -3 -I Tools\RaceForge\raceforge.py build --dbc C:\azerothcore\data\dbc --out C:\bleakhold\raceforge-out --mpq
   ```

   The exit code is 0 when every check passed. Read `C:\bleakhold\raceforge-out\report.txt`. To build again into the
   same folder, add `--force`. Run it on stock DBCs: it refuses DBCs that already contain race 22 or 23.

4. **Client:** copy `raceforge-out\client\patch-R.MPQ` to `C:\WoW335\Data\patch-R.MPQ`. The client reads DBCs
   only from archives, and a `Data\patch-<letter>.MPQ` that sorts later wins (see `Tools/MpqPack/README.md`).
   If another patch of yours holds any of the same DBCs, build from that patch's DBCs and use a later letter.
   Use a client built with `WOWDECOMP_DISABLE_SIGNATURE_CHECKS=ON` (the CI build is), which accepts modified game
   data.

5. **Server (AzerothCore):**
   1. Stop worldserver and back up `C:\azerothcore\data\dbc`.
   2. Copy every file of `raceforge-out\server\dbc` into `C:\azerothcore\data\dbc` (they replace the stock files).
   3. Run `raceforge-out\server\sql\bleakhold_races.sql` on the world database (`acore_world`), for example
      `mysql -u acore -p acore_world < C:\bleakhold\raceforge-out\server\sql\bleakhold_races.sql`.
   4. Optionally run `bleakhold_races_content_masks.sql` too (see below).
   5. Start worldserver. AzerothCore builds its race list and race masks from ChrRaces at start-up (`RaceMgr`), so
      it needs no race limit change.

   `bleakhold_races_remove.sql` undoes the SQL; put the backed-up DBCs back as well. If the world database has rows
   in `chrraces_dbc`, `charsections_dbc`, `skillraceclassinfo_dbc` or similar tables, those rows override the DBC
   files by id; RaceForge does not write them.

To check an output folder again: `py -3 -I Tools\RaceForge\raceforge.py validate --dbc C:\azerothcore\data\dbc --out C:\bleakhold\raceforge-out --mpq C:\bleakhold\raceforge-out\client\patch-R.MPQ`.

To pack extra client files into the same archive (for example corpse skeletons under the new names,
`World\Generic\PassiveDoodads\DeathSkeletons\HighElfMaleDeathSkeleton.m2`, copied from your client), put them in a
folder with their archive paths as subfolders and add `--mpq-extra <folder>`.

## Character customization packages (more faces, hair, skins, tattoos, HD models)

A customization package such as Ascension Character Customization (HD models of the stock races and 500+ extra
faces, hair styles, skins and markings) is a folder with `DBFilesClient\*.dbc` next to art folders
(`Character\`, `Textures\`). Give it to RaceForge and it is merged into your DBCs first, so High Elf and Eredar,
cloned from the merged Blood Elf and Draenei, get every option and the HD models too:

```bat
py -3 -I Tools\RaceForge\raceforge.py build --dbc C:\azerothcore\data\dbc --out C:\bleakhold\raceforge-out --mpq --customization C:\Downloads\Ascension_Character_Customization
```

In the easy mode, drop the DBC folder and then the package folder onto the program (or answer its second
question). The package is your own download; nothing of it is in this repository.

- Tables keyed by race (CharSections, CharHairGeosets, CharacterFacialHairStyles, BarberShopStyle,
  EmotesTextSound): for every race the package has rows for, its rows replace yours; your other races keep theirs.
  Rows for races your ChrRaces lacks, or for the races RaceForge adds, are left out.
- Tables keyed by id (HelmetGeosetVisData, CreatureDisplayInfoExtra): the package's row replaces yours with the same
  id; your other rows are kept.
- CharSections is sorted again (the client groups consecutive rows). Ids that clash with a row you keep get new ones.
- Helmet masks: the new races copy the template race's bit exactly, so a package mask like "every race but a few"
  cannot hide geosets the template race shows.
- The art (every file under the package's folders except `DBFilesClient`) is packed into `client\patch-6.MPQ`,
  then `patch-7.MPQ`, `patch-8.MPQ` and `patch-9.MPQ` as needed, with at most 3500 MB of files each
  (`--art-max-mb`), streamed one file at a time. `--no-art` merges the tables only. See the names and sizes below.
- `customization\base-dbc` in the output holds your DBCs with the package merged in: the starting point the checks
  compare against (`raceforge.py validate` finds it by itself). The report lists every merge step, and checks that
  the package's rows arrived exactly and your other rows did not change.

The server gets the merged tables in `server\dbc` as usual; players need `patch-R.MPQ` and the art archives in
their `Data` folder.

### Art archive names and sizes

Every letter but F, K, O and W already names a patch the realm ships: H L R T V X Y Z (the realm; R is RaceForge's
own `patch-R.MPQ`, Y the HD pack), A B C D E G I M N P S U (Reforged), J (a login screen) and Q (MapForge). The
launcher installs files by name, so an art archive under one of those names would replace that patch on every
player's PC. The art therefore takes digits:

- The client opens every `Data\patch-?.MPQ` with exactly one character, of any kind, in place of `?`, and every
  `Data\<locale>\patch-<locale>-?.MPQ`. It sorts them by path without regard to case, and when two hold the same
  file, the one that sorts last wins (`WoW/Source/WowServices/PatchFiles.cpp`, `OpenArchives` in
  `WoW/Source/Client.cpp`, and `Tools/MpqPack/README.md`). Case never matters: `patch-s.MPQ` is `patch-S.MPQ`.
- Digits sort before letters. `patch-6.MPQ` to `patch-9.MPQ` load after every base archive and the stock
  `patch-2.MPQ` and `patch-3.MPQ`, and below every lettered patch. So the art adds files and replaces stock ones,
  but where a realm or Reforged patch holds the same file (an HD model in Reforged's patches or in `Patch-Y.MPQ`),
  that patch wins and the package's file is not used. For the package's files to win over Reforged's patches, give
  the free letter after them: `--art-letters W`. It still loses to X, Y and Z.
- `--art-letters` takes A-Z and 4-9: `patch-0` and `patch-1` would sort below the stock patches, 2 and 3 are the
  stock patches, and 5 is MapForge's archive for the server's extractors.

`taken_patches.json`, next to `races.json`, lists every name in use with its owner. RaceForge refuses an art name in
it before it does anything else, and with `--patches-dir <folder>` (the realm's patch folder, or a client's `Data`
folder) also every name already in that folder. `--art-letters` picks other names under the same check; the error
lists the free ones. `--force-letters` writes the art under taken names anyway, with a warning on the console and
in the report: never publish such archives next to the realm's patches. When a new patch ships, add its name to
`taken_patches.json`.

Size: MpqPack writes MPQ format 0 (v1), whose offsets are 32 bits, so each archive stays under 4 GiB. The client
reads those offsets unsigned (`InitializeTables` in `Engine/Source/BlizzardCore/Source/Packages/Mopaq`), so
archives between 2 and 4 GiB are fine. 3500 MB of files per archive leaves room for the tables (`--art-max-mb`
takes at most 4000), and the four default names hold 14000 MB; for a larger package, add free characters
(`--art-letters 46789`). The client also reads format 1 (v2, with 64-bit offsets, for archives over 4 GiB), but
MpqPack does not write it.

## Output

| Path | Contents |
|---|---|
| `client\DBFilesClient\*.dbc` | The changed tables, for the client |
| `client\patch-R.MPQ` | The same files in an archive (`--mpq`; `--mpq NAME` for another name) |
| `server\dbc\*.dbc` | Identical copies for AzerothCore's `data\dbc` |
| `server\sql\bleakhold_races.sql` | Required world-database rows |
| `server\sql\bleakhold_races_content_masks.sql` | Optional quest, item, area spell, condition and mail race masks |
| `server\sql\bleakhold_races_remove.sql` | Undoes both SQL files |
| `client\patch-6.MPQ` ... `patch-9.MPQ` | The customization package's art (`--customization`), as many as it needs |
| `customization\base-dbc\*.dbc` | Your DBCs with the package merged in, before the races were added |
| `report.txt` | Every change, warning and check |

## What changes

Rows keyed by race are cloned from the template race, with fresh ids after the highest existing one. Stock rows are
left as they were apart from the race bits below; the string block of each file is kept and new strings are appended
to it. Tables RaceForge does not change are not written.

| Table | Change |
|---|---|
| ChrRaces | A new row from the template: flag 0x1 (not playable) cleared; FactionID = the faction race's faction template; BaseLanguage 7 (Alliance) or 1 (Horde); Alliance column 0 or 1; Name in every locale; ClientFileString `HighElf` / `Eredar`; the template's ClientPrefix, display ids and sounds; CinematicSequenceID 0; RequiredExpansion at most 2 |
| CharBaseInfo | The template's race/class pairs (or the subset in `classes`) |
| CharStartOutfit, CharSections, CharHairGeosets, CharacterFacialHairStyles, NameGen, BarberShopStyle, EmotesTextSound, VocalUISounds | The template race's rows. CharSections is kept sorted by race, sex, section, variation and color, because `BuildComponentArray` groups consecutive rows; NameGen rows stay one run per race and sex (`CNameGen::LoadNames`) |
| SkillRaceClassInfo, SkillLineAbility, TalentTab, DanceMoves | Race bit `1 << (race - 1)` added by the mask rule below, except on the rows of the template's racial skill lines the race drops (`racials.drop_template_skill_lines`) |
| Spell | The rows of races.json's `spells` appended (the stock rows and the string block stay byte for byte) |
| Faction | Reputation race masks: the bit is added wherever the faction race has one, so the race starts with that race's reputations |
| HelmetGeosetVisData | Bit `1 << race` (this table, unlike the others, uses `1 << race`; `CCharacterComponent::AddHelm`) where the template's bit is set |

SoundFilter gets no rows: for High Elf and Eredar Death Knights the client always uses the Blood Elf and Draenei
filters (`SI2::DK_GetPlayerFilterName`).

### The mask rule

A mask of 0 means every race and stays 0. Otherwise the new race gets its bit when the template race has one. The
exception is a mask that holds exactly the playable races of one faction, such as Language: Common (Alliance) or
Language: Orcish (Horde), or a faction-wide spell or mount. That mask follows the new race's
faction, so the High Elf speaks Common, not Orcish. A mask that holds every playable race gets the bit in any case.
`SkillLineAbility.excludeRace` inverts its mask in the client (`SpellTableMatchRaceClass`); the same rule then
decides who is excluded. The faction masks are read from your ChrRaces, FactionTemplate and FactionGroup, the way
the character creation screen splits races into Alliance and Horde. Set `policy.faction_wide_masks` to `false` to
copy the template race's bits everywhere.

The server SQL applies the same rule to `playercreateinfo_skills`, `playercreateinfo_spell_custom` and
`playercreateinfo_cast_spell`. AzerothCore also checks each create skill against SkillRaceClassInfo.dbc, so the two
must agree.

## Server SQL

`bleakhold_races.sql` copies the template race's rows from your own world database and adds:

- `player_race_stats`: the template's stat modifiers (or `stats` from the config);
- `playercreateinfo`: one row per class, at `start` (Death Knights at `death_knight_start`);
- `playercreateinfo_action`, `playercreateinfo_item`: the template's action bars and extra items;
- `playercreateinfo_skills`, `_spell_custom`, `_cast_spell`: rows for the race's bit, chosen by the mask rule;
- `player_totem_model`, `player_shapeshift_model`: the template's totem and form models;
- `creature_model_info`: only for display ids the template race does not use;
- `spell_dbc`: the rows of the racial spells, built from the same rows as the Spell.dbc copies (a spell whose
  `server_row` names another SQL file gets none here), and `playercreateinfo_spell_custom` rows that give each race its
  racials (AzerothCore teaches those at creation only with `PlayerStart.CustomSpells = 1`; the realm's mod-bleakhold
  teaches them at login whatever that option says).

A dropped template racial skill line is left out of `playercreateinfo_skills`, its spells out of `_spell_custom` and
`_cast_spell`, and the template's start action bar buttons of those spells take the race's first active racial (Read
Ley Line for the Eredar) or go.

`bleakhold_races_content_masks.sql` is optional. It lets the new races take the quests and use the items of their
faction race, whose start zone they share: `quest_template.AllowableRaces`, `item_template.AllowableRace`
(including the template's start outfit items, which the race now wears), `spell_area.racemask`,
`mail_level_reward.raceMask` and race conditions (`conditions` type 16). Masks of 0 and -1 are left alone. Review
it before you run it.

Some race handling is in AzerothCore's code, not its data, and needs a module or core change:

- starting taxi nodes (`PlayerTaxi::InitTaxiNodesForLevel`) and the starter gift voucher (`Player.cpp`);
- race and faction change (`CharacterHandler.cpp`): its language switch has no case for other races. Block race
  change to and from the new races until it does;
- race-specific shapeshift and costume auras (`SpellAuraEffects.cpp`);
- racial riding trainers (`trainer.Requirement` is a single race id).

## races.json

| Field | Meaning |
|---|---|
| `id` | Race id, 1-31 (the client keeps races in 32-bit masks). 24-26 are refused: later clients use them for Pandaren, which Bleakhold does not have |
| `name`, `names` | Name for every locale; `names` overrides single locales (`enUS`, `koKR`, `frFR`, `deDE`, `zhCN`, `zhTW`, `esES`, `esMX`, `ruRU`) |
| `name_female`, `name_male` | Gendered names. `null`: the race's name wherever the template has a gendered name (German, French, ...), empty elsewhere |
| `client_file_string` | 1-13 letters or digits; names portraits, corpse skeletons and Lua race tokens (`UnitRace`) |
| `template_race` | The race cloned for looks, sounds and classes, and its racials unless `racials` drops them |
| `faction`, `faction_race` | `alliance` or `horde`, and a playable race of that faction for the faction template, reputations and content masks |
| `faction_template` | A FactionTemplate id instead of the faction race's |
| `classes` | `null` for the template's classes, or a subset of them. Class 10 (Monk) is refused |
| `male_display_id`, `female_display_id` | `null` for the template's displays |
| `required_expansion` | `null` for the template's (at most 2) |
| `cinematic_sequence_id` | Intro cinematic, 0 for none |
| `start`, `death_knight_start` | Start positions (`map`, `zone`, `x`, `y`, `z`, `o`) for `playercreateinfo` |
| `stats` | `null` to copy the template's `player_race_stats`, or `strength` ... `spirit` |
| `racials.drop_template_skill_lines` | SkillLine ids of the template's racial skill lines the race does not get (756 Racial - Blood Elf, 760 Racial - Draenei); each must give the template race a SkillRaceClassInfo row. Empty or missing: the template's racials |
| `racials.spells` | Ids of the race's own racial spells, defined in `spells` |
| `spells` | New Spell.dbc rows, see "Racials and spells" |
| `archives.own`, `archives.optional_packs` | RaceForge's archive (`patch-R.MPQ`) and the launcher's optional packs, for `update` |
| `policy.faction_wide_masks` | The mask rule above (`true`) or plain template copies (`false`) |
| `policy.reputation_from`, `policy.content_masks_from` | `faction_race` (default) or `template_race` |

## Racials and spells

Each race can leave out the template race's racial skill lines and name its own racial spells (`racials`); `spells`
defines every new Spell.dbc row. RaceForge builds each row once and writes the Spell.dbc copies and the `spell_dbc`
SQL from that one row, so the client and the server read the same values; the checks read both back and compare
them field for field (234 columns).

| Key | Meaning |
|---|---|
| `id` | A free spell id (the build stops when the input Spell.dbc has it). Bleakhold: 90500-90509 the racials, 100800-100809 the camping spells of mod-bleakhold-ui; AzerothCore's own `spell_dbc` rows use 100001-100102, mod-transmog-plus 90170-90189 |
| `name`, `subtext`, `description`, `aura_description` | The texts: name, rank text ("Racial", "Racial Passive"), tooltip and aura tooltip, with the client's `$s1`, `$d` tokens |
| `icon`, `icon_name` | SpellIcon.dbc id; with `icon_name` the build checks the icon's texture name too |
| `visual` | SpellVisual.dbc id (0 for none) |
| `fields` | Every other column by its client name (`attributes`, `durationIndex`, `effect[0]`, `effectAura[0]`, `effectBasePoints[0]`, ...). Columns not given are 0, except procChance 101, equippedItemClass -1 and effectChainAmplitude 1.0, as in Blizzard's rows |
| `cast_by` | `race` (default): a racial, which a race must list. `server`: a spell no race learns, which a server module casts (Walk on Air, the High Elf glide); it gets its Spell.dbc row only |
| `server_row` | An SQL file of this repository (relative to its root) that holds the spell's `spell_dbc` row: RaceForge then writes none and checks that row against the Spell.dbc row field for field (columns the INSERT leaves out count as the table's defaults) |
| `text_locales` | The locale slots that get the texts: all nine by default (like the race names), `["enUS"]` to match a row that fills only that one |

The build checks that the icon, the visual, the duration, the range and the cast time exist (when those DBCs are in
the input folder) and that no SkillLineAbility row teaches a spell of `spells`: racial spells show in the spellbook's
General tab, and the server teaches them (mod-bleakhold in bleakserv). The Bleakhold racials:

| Spell | Race | Effect (Spell.dbc) | Icon, visual |
|---|---|---|---|
| 90500 Wind Blessed, passive | High Elf | aura 193 (SPELL_AURA_MELEE_SLOW, Berserking's) +3: melee, ranged and cast speed 3% faster | 2837 Ability_Druid_GaleWinds |
| 90501 Elemental Insight, passive | Eredar | aura 168 (SPELL_AURA_MOD_DAMAGE_DONE_VERSUS, Beast Slaying's) +5%, creature type mask 8 (Elemental) | 2016 Spell_Nature_ElementalAbsorption |
| 90502 Read Ley Line | Eredar | instant, 2 min cooldown, off the global cooldown, castable while sitting; auras 88 and 110 (mana) +100% for 30 s; mod-bleakhold makes it 2 min when cast while resting | 2158 Spell_Arcane_StudentOfMagic; visual 4279 (Mana Tide's: a blue splash and glowing hands, then a mana swirl at the feet) |
| 100800 Walk on Air (server-cast) | High Elf glide (mod-bleakhold-ui) | aura 105 feather fall, 10 s; its `spell_dbc` row is `Server/mod-bleakhold-ui/data/sql/db-world/02_bleakhold_walk_on_air.sql` | 1931 Spell_Nature_EyeOfTheStorm; visual 7370 (Magic Wings' wings) |

## Updating a live realm (`raceforge.py update`)

`build` starts from stock DBCs and refuses tables that already hold the new races. A realm that already runs them
takes the racials (and any later change to `spells` or `racials`) with `update`, which works like Tools/MapForge's DBC
placement and reuses its archive code (`Tools/MapForge/dbc/patches.py`):

- for SkillRaceClassInfo, SkillLineAbility and Spell, and for every combination of the launcher's optional packs
  (`archives.optional_packs`: with and without the HD pack), it finds the copy the client reads today: the archive that
  sorts last among those holding the file;
- it forges the change into that copy (clears the new races' bits on the dropped skill lines, adds the spells, or
  replaces an earlier version of the same spell; an id that holds any other spell stops it) and rebuilds that archive
  with every other file kept. Players with and without a pack each keep the copy they load today, plus the change;
- where no patch holds a table, the stock copy from `--dbc` gets the change and goes into `archives.own` (patch-R, or
  the realm's file of that name in another case, such as `Patch-R.MPQ`). Every player loads that archive, so when only
  a pack archive holds the table and `archives.own` sorts after it (the HD pack's patch-A to patch-P sort before
  patch-R), the update stops instead of hiding the pack's copy: add the table to a patch every player loads, or set
  `archives.own` to a patch outside every pack that sorts below the pack archive. It also stops when `archives.own`
  is itself in a pack, which the players without it would not load;
- it never writes into the patch folder: the rebuilt archives go to `--out/client`. Running it again on the updated
  patches changes nothing ("already up to date").

On the VPS (the realm's patches in `/srv/bleakhold-launcher/patches`, bleak in `/root/bleak`, bleakserv in
`/root/bleakserv`):

```sh
cd /root/bleak/Tools/RaceForge
python3 -I raceforge.py update --patches /srv/bleakhold-launcher/patches --dbc <the server's data/dbc> \
    --out /root/raceforge-racials \
    --server-sql /root/bleakserv/data/sql/updates/pending_db_world/<the racials rev file>.sql
```

The exit code is 0 when every check passed; `report.txt` says, per table and pack combination, which archive was
merged (that is the patch letter it goes in). Then:

1. Client first: put every archive of `/root/raceforge-racials/client/` into the patch folder, replacing the file of
   the same name (upload under another name, then `mv` it into place). Then publish at once (the hourly run at :17
   can come after the server update) and wait for `Published build ...`:
   ```sh
   bash /root/bleakserv/deploy/launcher/publish.sh
   ```
   Players get the archives once their launcher has updated the game and they restart it: give them time before
   step 2, as bleakserv's `deploy/README.md` release steps do.
2. Server: the world rows are bleakserv's pending_db_world file (`server/sql/bleakhold_racials.sql` is the same SQL;
   `--server-sql` compares them field for field) and the code is mod-bleakhold's `bh_racials.cpp`, committed and
   pushed in bleakserv (its deploy script deploys the last commit). Check, then update:
   ```sh
   cd /root/bleakserv && git pull && bash deploy/update-bleakhold-ui.sh --check
   bash deploy/update-bleakhold-ui.sh
   ```
   The check must list the racials `rev_*.sql` as `new`, mod-bleakhold's `bh_racials.cpp`, `bh_racials_rules.h` and
   `mod_bleakhold_loader.cpp`, and the new settings `Bleakhold.Racials.Enable` and
   `Bleakhold.Racials.ReadLeyLine.RestedSec` (`config: mod_bleakhold.conf: ... new setting(s)`). The update copies
   them to the server, rebuilds the world server and `ac-db-import` images and restarts the world server, after
   `ac-db-import` has applied the SQL. A plain `docker compose restart ac-worldserver` applies and builds none of it
   (bleakserv's `deploy/README.md`). `data/dbc` can stay as it is (the rows override it by id); `server/dbc` holds
   the merged copies if you want it in sync anyway.

## Checks

`build` re-reads what it wrote and checks:

- every file against the client's column count and row size, with an identical server copy, unique ids and
  string offsets inside the string block;
- stock rows unchanged apart from the new races' mask bits;
- for each race: playable, FactionID / BaseLanguage / Alliance agreeing, a name in every locale, the
  ClientFileString, the template's ClientPrefix, RequiredExpansion at most 2;
- display ids present in CreatureDisplayInfo with their models in CreatureModelData, start outfit display ids in
  ItemDisplayInfo (skipped when those files are not given);
- the template's class list, a start outfit per class and sex, the template's row count in every cloned table, skins
  for both sexes;
- the faction language, the mask rule in every mask, helmets and reputations;
- CharSections sorted, NameGen contiguous, no Pandaren race and no Monk class anywhere;
- with `--mpq`, the archive against the client reader's rules and its files against the written DBCs;
- no new race bit on a dropped template racial skill line; every spell row exactly as races.json describes it, what it
  points at present, its `spell_dbc` row (RaceForge's SQL or its `server_row` file) equal field for field.

## Tests

```bat
py -3 -I Tools\RaceForge\tests\run_tests.py
```

or `python3 -I -m unittest discover -s Tools/RaceForge/tests -t Tools/RaceForge`. The tests build made-up DBCs in
the client's layouts (`tests/synth.py`, races 1-21 with the stock faction split) and run the whole tool on them.
They also re-derive `rflib/schemas.py` from `WoW/Source/DB/Rec` and parse every Rec class there against its
`s_numColumns`/`s_rowSize`. They check that the mask rule gives the same answer in Python and in the generated SQL,
and run the SQL against a model of the world database in SQLite. `test_art_names.py` checks the art archive names:
the default against `taken_patches.json` and the client's order, the refusal, `--patches-dir`, `--art-letters` and
`--force-letters`. `test_racials.py` covers `racials` and `spells` (the config, the rows and their SQL, the refusals,
a tampered SQL row) and `update` on made-up realms: RaceForge's earlier patch-R only, Spell.dbc in a later realm patch
with a custom row, an optional pack with its own copy, a pack archive below patch-R as the only holder (refused) and
one above it, the realm's archive spelled `Patch-R.MPQ`, a bad spell field, a taken id, a realm without the races,
the SQL on a model of the world database (run twice) and against bleakserv's linter. With a bleakserv checkout next
to this repository it
also compares the server's `spell_dbc` columns, the pending world-database file and mod-bleakhold's racial table with
races.json.

After a change to the Rec classes, regenerate the layouts with `py -3 -I Tools\RaceForge\raceforge.py schemas --write`.
