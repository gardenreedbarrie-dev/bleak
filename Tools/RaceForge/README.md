# RaceForge

Adds the Bleakhold races to your own 3.3.5a game data:

| Race | Id | Faction | Template race (models, sounds, racials, classes) | Faction race (language, reputation, start zone) |
|---|---|---|---|---|
| High Elf | 22 | Alliance | Blood Elf (10), helmet prefix `Be` | Human (1), starts in Northshire |
| Eredar | 23 | Horde | Draenei (11), helmet prefix `Dr` | Orc (2), starts in the Valley of Trials |

RaceForge reads the DBC files of your client and writes:

- patched copies of every table it changes, once for the client and once (identical) for the server;
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
| SkillRaceClassInfo, SkillLineAbility, TalentTab, DanceMoves | Race bit `1 << (race - 1)` added by the mask rule below |
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
- `creature_model_info`: only for display ids the template race does not use.

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
| `template_race` | The race cloned for looks, sounds, racials and classes |
| `faction`, `faction_race` | `alliance` or `horde`, and a playable race of that faction for the faction template, reputations and content masks |
| `faction_template` | A FactionTemplate id instead of the faction race's |
| `classes` | `null` for the template's classes, or a subset of them. Class 10 (Monk) is refused |
| `male_display_id`, `female_display_id` | `null` for the template's displays |
| `required_expansion` | `null` for the template's (at most 2) |
| `cinematic_sequence_id` | Intro cinematic, 0 for none |
| `start`, `death_knight_start` | Start positions (`map`, `zone`, `x`, `y`, `z`, `o`) for `playercreateinfo` |
| `stats` | `null` to copy the template's `player_race_stats`, or `strength` ... `spirit` |
| `policy.faction_wide_masks` | The mask rule above (`true`) or plain template copies (`false`) |
| `policy.reputation_from`, `policy.content_masks_from` | `faction_race` (default) or `template_race` |

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
- with `--mpq`, the archive against the client reader's rules and its files against the written DBCs.

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
`--force-letters`.

After a change to the Rec classes, regenerate the layouts with `py -3 -I Tools\RaceForge\raceforge.py schemas --write`.
