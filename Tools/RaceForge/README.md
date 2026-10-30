# RaceForge

Adds the Bleakhold races to your own 3.3.5a game data:

| Race | Id (build) | Id on the Bleakhold realm | Faction | Template race (models, sounds, classes) | Faction race (language, reputation, start zone) | Racials |
|---|---|---|---|---|---|---|
| High Elf | 22 | 15 | Alliance | Blood Elf (10), helmet prefix `Be` | Human (1), starts in Northshire | Wind Blessed (90500); not Blood Elf's |
| Eredar | 23 | 19 | Horde | Draenei (11), helmet prefix `Dr` | Orc (2), starts in the Valley of Trials | Elemental Insight (90501), Read Ley Line (90502); not Draenei's |

`build` adds the races after the stock rows 1-21, as 22 and 23. The Bleakhold realm got them from its own race patch
(`Patch-R.MPQ`), which reuses stock creature display slots: High Elf 15 (stock Skeleton), Eredar 19 (Taunka), and
Pandaren in 20 and 21. `update` works on the races there (`realm_id` in races.json).

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
new races) is already in the decompilation, `BLEAKHOLD(races)`. The client finds High Elf and Eredar by their
`client_file_string` (`HighElf`, `Eredar`, in any case), not by id, so the same client works with the build's 22 and
23 and with the realm's 15 and 19; a race with another file name borrows nothing. The character creation screen
needs Bleakhold glue UI as well: the stock GlueXML has 10 race buttons and stops with "Too many races!" when
ChrRaces holds more playable races. Install the races together with that glue UI. The new races use the template
races' models; HD models are a later step.

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
own `patch-R.MPQ`, Y the HD pack), A B C D E G I M N P S U (Reforged), J (a login screen) and Q (MapForge), and so do
the digits 2 and 3 (stock), 4 (CafeForge's café archive) and 5 (MapForge). Free: F, K, O, W and 6-9. The
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
  stock patches, 4 is CafeForge's café archive and 5 is MapForge's archive for the server's extractors (both are in
  `taken_patches.json`, so 6-9 are the free digits).

`taken_patches.json`, next to `races.json`, lists every name in use with its owner. RaceForge refuses an art name in
it before it does anything else, and with `--patches-dir <folder>` (the realm's patch folder, or a client's `Data`
folder) also every name already in that folder. `--art-letters` picks other names under the same check; the error
lists the free ones. `--force-letters` writes the art under taken names anyway, with a warning on the console and
in the report: never publish such archives next to the realm's patches. When a new patch ships, add its name to
`taken_patches.json`.

Size: MpqPack writes MPQ format 0 (v1), whose offsets are 32 bits, so each archive stays under 4 GiB. The client
reads those offsets unsigned (`InitializeTables` in `Engine/Source/BlizzardCore/Source/Packages/Mopaq`), so
archives between 2 and 4 GiB are fine. 3500 MB of files per archive leaves room for the tables (`--art-max-mb`
takes at most 4000), and the four default names hold 14000 MB; for a larger package, add a free letter
(`--art-letters 6789F`; the refusal lists the free ones, and a letter sorts after the lettered patches before it, as
above). The client also reads format 1 (v2, with 64-bit offsets, for archives over 4 GiB), but
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
| `id` | Race id, 1-31 (the client keeps races in 32-bit masks), the one `build` gives. 24-26 are refused: later clients use them for Pandaren, which Bleakhold does not have |
| `realm_id` | The race's id on the realm `update` works on, when that realm's own race patch put it in another ChrRaces slot (Bleakhold: High Elf 15, Eredar 19); `null` or missing: `id`. `update` refuses to run unless the realm's ChrRaces holds the race there under its `client_file_string`. `build` ignores it |
| `name`, `names` | Name for every locale; `names` overrides single locales (`enUS`, `koKR`, `frFR`, `deDE`, `zhCN`, `zhTW`, `esES`, `esMX`, `ruRU`) |
| `name_female`, `name_male` | Gendered names. `null`: the race's name wherever the template has a gendered name (German, French, ...), empty elsewhere |
| `client_file_string` | 1-13 letters or digits; names portraits, corpse skeletons and Lua race tokens (`UnitRace`). `HighElf` and `Eredar` are how the client knows the Bleakhold races (Blood Elf and Draenei scenes, voices and portraits) |
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
| `cast_by` | `race` (default): a racial, which a race must list. `server`: a spell no race learns, which a server module casts (Walk on Air's aura, 100800); it gets its Spell.dbc row only. `module`: a spell a server module teaches and the player casts from the spellbook (Walk on Air, 100801, which mod-bleakhold-ui teaches to the races of `BleakholdUi.Glide.Races`); like `server`, no race lists it and it gets no `playercreateinfo` row |
| `server_row` | An SQL file of this repository (relative to its root) that holds the spell's `spell_dbc` row: RaceForge then writes none and checks that row against the Spell.dbc row field for field (columns the INSERT leaves out count as the table's defaults) |
| `text_locales` | The locale slots that get the texts: all nine by default (like the race names), `["enUS"]` to match a row that fills only that one |

The build checks that the icon, the visual, the duration, the range and the cast time exist (when those DBCs are in
the input folder) and that no SkillLineAbility row teaches a spell of `spells`: racial spells show in the spellbook's
General tab, and the server teaches them (mod-bleakhold in bleakserv; Walk on Air in the spellbook mod-bleakhold-ui). The
Bleakhold racials:

| Spell | Race | Effect (Spell.dbc) | Icon, visual |
|---|---|---|---|
| 90500 Wind Blessed, passive | High Elf | aura 193 (SPELL_AURA_MELEE_SLOW, Berserking's) +3: melee, ranged and cast speed 3% faster | 2837 Ability_Druid_GaleWinds |
| 90501 Elemental Insight, passive | Eredar | aura 168 (SPELL_AURA_MOD_DAMAGE_DONE_VERSUS, Beast Slaying's) +5%, creature type mask 8 (Elemental) | 2016 Spell_Nature_ElementalAbsorption |
| 90502 Read Ley Line | Eredar | instant, 2 min cooldown, off the global cooldown, castable while sitting; auras 88 and 110 (mana) +100% for 30 s; mod-bleakhold makes it 2 min when cast while resting | 2158 Spell_Arcane_StudentOfMagic; visual 4279 (Mana Tide's: a blue splash and glowing hands, then a mana swirl at the feet) |
| 100800 Walk on Air (server-cast) | the High Elf glide's aura (mod-bleakhold-ui casts it when a glide starts) | aura 105 feather fall, 10 s; its `spell_dbc` row is `Server/mod-bleakhold-ui/data/sql/db-world/02_bleakhold_walk_on_air.sql` | 1931 Spell_Nature_EyeOfTheStorm; visual 63 (Slow Fall's: a light at the hands and a soft flash at the head as the glide starts; was 7370, Magic Wings' wings). Others that fit: 0 none, 12114 Guardian Spirit's golden wings, 12724 Cyclone Fall's whirl and floating pose, 6768 Levitate's swirl at the feet |
| 100801 Walk on Air (module-taught) | High Elf, in the spellbook: mod-bleakhold-ui teaches it at login (`BleakholdUi.Glide.CastSpell`) and puts it on a free action bar slot once | instant, 90 s cooldown (`recoveryTime`; the module sends `BleakholdUi.Glide.Cooldown` when it differs, and shares it with `/glide`), off the global cooldown, self; a dummy effect its script (`spell_bleakhold_walk_on_air`) turns into the glide, in the air only (on the ground the cast fails with "Cannot be used on the ground", free); its `spell_dbc` row is the same SQL file's | 505 Spell_Magic_FeatherFall; no visual of its own (the aura's is the glide's look) |

## Updating a live realm (`raceforge.py update`)

`build` starts from stock DBCs and refuses tables that already hold the new races. A realm that already runs them
takes the racials (and any later change to `spells` or `racials`) with `update`, which works like Tools/MapForge's DBC
placement and reuses its archive code (`Tools/MapForge/dbc/patches.py`):

- the races are the realm's: each race at its `realm_id` (15 and 19 on the Bleakhold realm; its `id` without one). For
  every combination of the launcher's optional packs, the ChrRaces.dbc the client reads must hold the race there
  under its `client_file_string` (`HighElf`, `Eredar`); otherwise it stops before it writes anything and says where
  the race is instead (`HighElf is race 22 there: set realm_id 22 ...`) or that the realm has no such race;
- for SkillRaceClassInfo, SkillLineAbility and Spell, and for every combination of the optional packs
  (`archives.optional_packs`: with and without the HD pack), it finds the copy the client reads today: the archive that
  sorts last among those holding the file;
- it forges the change into that copy (clears the races' bits on the dropped skill lines, adds the spells, or
  replaces an earlier version of the same spell; an id that holds any other spell stops it) and rebuilds that archive
  with every other file kept. Players with and without a pack each keep the copy they load today, plus the change.
  Every other bit stays as the realm has it (the template race's, the languages, the Pandaren). A row that only a
  dropping race had gets the mask `0x80000000`, the bit of race 32, which no race has: a mask of 0 would mean every
  race;
- where no patch holds a table, the stock copy from `--dbc` gets the change and goes into `archives.own` (patch-R, or
  the realm's file of that name in another case, such as `Patch-R.MPQ`). Every player loads that archive, so when only
  a pack archive holds the table and `archives.own` sorts after it (the HD pack's patch-A to patch-P sort before
  patch-R), the update stops instead of hiding the pack's copy: add the table to a patch every player loads, or set
  `archives.own` to a patch outside every pack that sorts below the pack archive. It also stops when `archives.own`
  is itself in a pack, which the players without it would not load;
- it never writes into the patch folder: the rebuilt archives go to `--out/client`, each at its place in the patch
  folder (`client/enUS/` for a locale patch), with `install.json` (the archives it read, for `raceforge.py install`,
  see "Installing an output folder"). Running it again on the updated patches changes nothing ("already up to
  date").

The server SQL (`server/sql/bleakhold_racials.sql`) is written from the realm's own rows, never stock ones:

- the `spell_dbc` rows of the racials, the same rows as the client's Spell.dbc (on the Bleakhold realm the same as
  those bleakserv's pending_db_world already applied);
- every `skillraceclassinfo_dbc` and `skilllineability_dbc` row of the dropped skill lines (756, 760) as the client
  reads it, without the races' bits; they override the server's data/dbc by id. `--dbc` is the server's data/dbc:
  its rows of those lines that the client's copy lacks and that give a race a dropped line are written too. Any other
  override row of those lines in the world database (earlier work) loses the races' bits by an `UPDATE`;
- `playercreateinfo_skills`, `_spell_custom` and `_cast_spell`: a row of the race alone for a dropped skill line or
  spell goes; a row of more races (a mask the realm shares with the template race) keeps the others;
  `playercreateinfo_action`: the race's own template racial buttons take Read Ley Line (the Eredar) or go; the
  races' own racials in `playercreateinfo_spell_custom`;
- where `realm_id` differs from `id`: the rows an earlier update wrote for `id` (racemask `1 << (id - 1)` racials,
  Read Ley Line's `playercreateinfo_action` rows of race `id`) go, so nothing points at a race the realm does not
  have.

Every statement can run again (it deletes what it adds first, or finds nothing left to change), and it passes
bleakserv's SQL linter. `--server-sql-out <folder>` also writes it, when every check passed, as a new
`rev_<nanoseconds>.sql` in that folder (the name `create_sql.sh` gives): `/root/bleakhold-generated-sql/pending_db_world`
is the server's folder of SQL made on the VPS, which bleakserv's `deploy/update-bleakhold-ui.sh` deploys like the
repository's pending SQL and `ac-db-import` applies once. A file of that folder that already holds the same SQL is
kept and nothing is written (running `update` again makes no second file); a `.sql` path in place of the folder is
never overwritten when it holds other SQL. The file is there whole or not at all: it is written as a hidden
`.rev_<nanoseconds>.sql.part` (no `.sql` file, so the deploy does not take it) and gets its name only once it is
complete, so a full disk or Ctrl-C leaves no cut-off `.sql` file for `ac-db-import` to run. `--server-sql <file>`
compares the DBC rows with another file field for field.

### The Bleakhold realm, step by step

On the VPS, as root: the realm's patches in `/srv/bleakhold-launcher/patches`, the server's data/dbc in the Docker
volume, bleak in `/root/bleak`, bleakserv in `/root/bleakserv`. bleakserv's `deploy/README.md` ("High Elf and Eredar
racials") has the same steps with what each check prints.

1. The new code:
   ```sh
   cd /root/bleak && git pull
   cd /root/bleakserv && git pull
   ```
2. The racials from the realm's own files (nothing on the server changes yet):
   ```sh
   cd /root/bleak/Tools/RaceForge
   python3 -I raceforge.py update --patches /srv/bleakhold-launcher/patches \
     --dbc /var/lib/docker/volumes/azerothcore-wotlk_ac-client-data/_data/dbc \
     --out /root/raceforge-racials --force \
     --server-sql-out /root/bleakhold-generated-sql/pending_db_world
   echo "exit code: $?"
   ```
   It must print `exit code: 0`, the line `ChrRaces.dbc (Patch-R.MPQ, for ...): race 15 is HighElf, race 19 is Eredar`,
   `... checks, 0 failed` and `Server SQL rev: /root/bleakhold-generated-sql/pending_db_world/rev_....sql (written)`.
3. The client archives into the patch folder, then publish. `client/` holds each rebuilt archive at its place in the
   patch folder (`enUS/` for a locale patch). `Patch-R.MPQ` there is a link to the download site's
   `/root/wow-site/site/public/downloads/Patch-R.MPQ`: install replaces the file the link points at, so the link stays
   and the site gets the new archive too, and keeps the archives as they were in `old-patches` (see "Installing an
   output folder"):
   ```sh
   cd /root/bleak/Tools/RaceForge
   python3 -I raceforge.py install --from /root/raceforge-racials --patches /srv/bleakhold-launcher/patches
   bash /root/bleakserv/deploy/launcher/publish.sh
   ```
   It prints `replaced: <file>` for every archive (or stops, changing nothing, when a patch changed since step 2: run
   step 2 again).
   Wait for `Published build ...`. Players get the archives when their launcher has updated the game and they
   restart it: give them time before step 5.
4. The glide settings (the update script keeps a value the server already has, so these are set by hand):
   ```sh
   C=/root/azerothcore-wotlk/env/dist/etc/modules/mod_bleakhold_ui.conf
   cp -p "$C" /root/raceforge-racials/mod_bleakhold_ui.conf.before
   sed -i -E \
     -e 's/^([[:space:]]*BleakholdUi\.Glide\.Races[[:space:]]*=).*/\1 "15"/' \
     -e 's/^([[:space:]]*BleakholdUi\.Glide\.Spell[[:space:]]*=).*/\1 100800/' \
     -e 's/^([[:space:]]*BleakholdUi\.Glide\.Cooldown[[:space:]]*=).*/\1 90/' "$C"
   grep -nE '^[[:space:]]*BleakholdUi\.Glide\.(Races|Spell|Cooldown)[[:space:]]*=' "$C"
   ```
   The grep must show `BleakholdUi.Glide.Races = "15"`, `BleakholdUi.Glide.Spell = 100800` and
   `BleakholdUi.Glide.Cooldown = 90`.
5. The server: check, then update:
   ```sh
   cd /root/bleakserv && bash deploy/update-bleakhold-ui.sh --check
   tmux new -s update
   cd /root/bleakserv && bash deploy/update-bleakhold-ui.sh
   ```
   The check lists the rev file of step 2 as `new ... (made on this server: /root/bleakhold-generated-sql)`,
   mod-bleakhold's `bh_racials.cpp` and `bh_racials_rules.h`, and `config: mod_bleakhold.conf: ... new setting(s)
   added with their defaults: ... Bleakhold.Racials.HighElfRace Bleakhold.Racials.EredarRace` (15 and 19). The update
   rebuilds the world server and `ac-db-import`, which applies the rev file before the world server starts.
6. The log:
   ```sh
   docker logs --tail 5000 ac-worldserver 2>&1 | grep -E 'mod-bleakhold: racials|BleakholdUi\.Glide'
   ```
   It must show this line, and no `BleakholdUi.Glide.Spell` error:
   ```text
   mod-bleakhold: racials on (High Elf race 15: 90500; Eredar race 19: 90501, 90502; Read Ley Line 120 s while resting)
   ```
   Each High Elf and Eredar logs `mod-bleakhold: racials of <name> (race 15)` (or `race 19`) at its first login
   after the update. Lines `mod-bleakhold: racials: ...` and `racials stay off ...` say what is still wrong: fix it at
   once. Once `ac-db-import` has applied the rev file of step 2, the core takes the Blood Elf and Draenei racials from
   every High Elf and Eredar at login (`Player::_LoadSkills`), whether or not mod-bleakhold runs, so with the racials
   off they log in with no racials at all. Nothing was taken from any character only when that file was not applied.

The realm's world rows have no plain way back. bleakserv's `rollback.sh` leaves the database as it is, and the old
mod-bleakhold it puts back knows races 22 and 23 only, so races 15 and 19 then have no racials;
`Bleakhold.Racials.Enable = 0` leaves them without racials too (unless `PlayerStart.CustomSpells = 1`). The template
racials come back only with a new rev that gives races 15 and 19 the skill lines 756 and 760 again: fixing what the
log names and updating again is the way out.

## Skins (`raceforge.py skins`)

`skins` gives a race of races.json new skin colours on the realm that already has it. On the Bleakhold realm the High
Elf becomes night-elf-like purple, from pale lavender to deep violet, in place of the fair Blood Elf skin; Blood Elves
stay exactly as they are.

### What changes

- The High Elf's CharSections rows (race 15, from the realm's race patch) name the Blood Elf's textures: the same files
  as the Blood Elf's rows. Those files are never changed. For every High Elf row of the sections in `skins.json` (0
  skin and 1 face), each texture is recoloured into a new file

  ```text
  Character\BleakholdSkins\HighElf\<hash>\<the original path>
  ```

  and only that row's texture name changes to it. The rows and their order stay, every other field of every row stays,
  and the new names are appended to the string block. Hair and facial hair rows are not changed (they have colours of
  their own), nor underwear rows: section 4 can be listed, but its cloth colours sit near skin hues and would turn
  purple too.
- Each new texture keeps the original's format, size, header and alpha: a palette texture gets a new palette; a DXT1,
  DXT3 or DXT5 texture (the type the client takes from preferredFormat) new endpoint colours in every block of every
  level, each block in the mode it had (endpoints whose order flips swap places and the indices follow; a four-colour
  block whose endpoints become equal gets one moved by one step of blue, so no texel turns transparent); a BGRA texture
  new pixels in every level. The levels are walked as the client walks them (CalcLevelCount, the header's offsets and
  sizes). A JPEG or BLP1 texture, or any other format, stops the run with the texture's name and format.
- The colours, in OKLab (a perceptual colour space): the skin colour of a sex and skin colour index is the median of
  the opaque pixels of mid lightness of its skin texture (section 0, variation 0, texture 0). A sex's skin colours are
  ranked by lightness and spread over `palette`, lightest first, so the palest Blood Elf skin gets the palest lavender
  and the darkest the deepest violet (the Death Knight rows, flag 0x4, over `dk_palette`). Every pixel of a texture then
  moves with its skin colour: the skin's lightness becomes the target's through a curve on lightness, so the shading
  stays; its chroma and hue become the target's, and colours near the skin's keep part of their difference from it.
  Colours far from the skin's hue (green eyes) or far more colourful barely move or not at all. A nearly grey skin (a
  Death Knight's) has hardly a hue of its own, so a colour on it is weighed against the nearer of that hue and the hue
  of the sex's other skins: its lips move with it, its green eyes still do not. The faces of a skin colour use the
  same numbers as its body texture, so the seams match.
- The hash is 10 hex digits of a SHA-1 over the original's bytes, the colour numbers and an algorithm version: the same
  input always gives the same file. Every new name is checked to stay under 260 characters, the client's limit.

The server needs nothing: AzerothCore reads CharSections.dbc without its texture names (`CharSectionsEntryfmt` is
`diiixxxiii`, bleakserv's `src/server/shared/DataStores/DBCfmt.h`), and the ids, races, sections, flags, variations
and colours stay as they are.

### Where the files go

The game's files are the launcher's: `--client` (the game folder it ships, `/srv/bleakhold-launcher/base`) with
`--patches` over it, a file of `--patches` replacing the one of the same path. The client loads the base archives of
`s_archives` (`WoW/Source/Client.cpp`: an earlier one wins, `<locale>\locale-<locale>.MPQ` and the like under the
locale's folder), then `patch.MPQ` and `patch-<locale>.MPQ`, then every `patch-?.MPQ` and
`<locale>\patch-<locale>-?.MPQ` above all of them (see "Art archive names and sizes"). An `alternate.MPQ` loads above
every patch: skins warns about it. For every combination of the launcher's optional packs (`archives.optional_packs`),
the CharSections.dbc the client reads is forged, and:

- the archive that holds it gets the forged copy and the new textures, when every combination that reads it gets the
  same result. On the Bleakhold realm that is `Patch-R.MPQ`, for every player;
- when a pack replaces a source texture under the same name (an HD pack's own Blood Elf skin), its players get other
  skin colours from the same CharSections.dbc. The combination with the fewest packs keeps that archive; each other
  one needs an archive of a pack the first one lacks, which its players load above that archive (`Patch-Y.MPQ` above
  `Patch-R.MPQ` for the HD pack) and which no players with other skins load: every combination that loads it and
  takes CharSections.dbc from below it would read the copy there. The highest such archive gets their own
  CharSections.dbc and textures, and `Character\BleakholdSkins\CharSections-copy.json`, which names that copy (by its
  SHA-1) and the archive it was made from. When there is none, nothing is written, and the error names the pack and
  the archive it would need to load after, or the players in the way;
- such a copy hides the CharSections.dbc below it from its players, so it never stays as it was: every run passes over
  it (the report says so) and makes it again from the archive below, so a later change there, such as a new row of the
  race patch, reaches those players too, and it removes the copy, its textures and its `CharSections-copy.json` once
  no combination needs them. A copy that changed since (its SHA-1 is not the one named) is the realm's own again
  (a warning says so);
- a CharSections.dbc that comes from a base archive stops it (the realm's race patch must hold the race's rows), and so
  does a ChrRaces.dbc without the race at its `realm_id` (`HighElf` at 15), for any combination.

Before anything is written, the client's view of every combination is worked out from the planned archives: it must
read its own forged CharSections.dbc, and every new texture name must resolve to exactly the recoloured file. After
writing, the same check runs on the written archives, read back from disk, with every other row (every other race,
and the race's rows of other sections) compared with the realm's field for field, and every new texture parsed and
decoded as the client reads it, at its original's size. Each rebuilt archive keeps every other file, and drops the
files under `Character\BleakholdSkins\HighElf\` that the new plan does not use (and skins' own copy of
CharSections.dbc, above). `--out` must have room for the rebuilt
archives first ("needs X GB free ..., has Y GB"). A rebuilt archive is downloaded again by every player who has it:
a rebuilt HD pack archive is large.

### Running it again

A row that already names one of these files is read through it: its source is the original path after the hash
folder. So on the updated realm `skins` finds the same files, prints `already up to date` and writes no archive. A
pack's own copy of CharSections.dbc is made again from the one below it, from the same string block plus its own
names, so it comes out the same too. A change of `skins.json` gives new names: the rows move to them, and the old
files leave every archive that is rebuilt (an archive the new plan does not write keeps its old files, unused; the
report lists them).

### The way back

`raceforge.py install --restore --from <the skins output> --patches <the patch folder>` puts the archives install
replaced back (see "Installing an output folder"), then publish. Or set `"sections": []` for the race in `skins.json`
and run `skins` and `install` again: every row goes back to its original textures, the new files leave the archive,
and a pack archive's own copy of CharSections.dbc goes too.

### Output

| Path | Contents |
|---|---|
| `client\<archive>` | Each rebuilt archive at its place in the patch folder (`client\enUS\` for a locale patch) |
| `report.txt` | The archives in the client's order, every skin colour with its target, where each file goes, warnings and checks |
| `install.json` | For `install`: each archive with the file it replaces as skins read it (size, modification time) |
| `preview\<race>-<sex>.png` | With `--preview`: a row per skin colour (lightest first, Death Knights last), its body texture and its first face's lower and upper textures, each before and after |

The exit code is 0 only when every check passed. It prints, for every combination, the archive the client reads
CharSections.dbc from, how many rows and textures changed and where they go, and the archives written.

### skins.json

| Key | Meaning |
|---|---|
| `races` | One entry per race to recolour, found in races.json by its `client_file_string` (at its `realm_id`). Only `HighElf` is there; an Eredar entry would take its own palette |
| `sections` | CharSections sections to recolour: 0 skin, 1 face, 4 underwear (default `[0, 1]`). Hair (3) and facial hair (2) are refused. `[]` puts every row back on its original textures |
| `palette` | Target colours `#RRGGBB`, lightest first; any number of entries (linear in OKLab between them) |
| `dk_palette` | The same for the Death Knight rows (flag 0x4) |
| `transform` | How far each colour moves (for every race; a race's own `transform` overrides single keys) |

`transform` (the defaults were tuned on previews of made-up elf textures):

| Key | Default | Meaning |
|---|---|---|
| `hue_full_within`, `hue_none_beyond` | 35, 65 | Degrees of hue from the skin's: a colour within the first moves fully, beyond the second not at all (green eyes) |
| `hue_unreliable_below` | 0.35 | A colour of less chroma than this share of the skin's (or than `chroma_floor`) has no reliable hue: it moves fully and takes the target hue |
| `chroma_full_within`, `chroma_none_beyond` | 0.07, 0.13 | OKLab chroma above the skin's: up to the first a colour moves fully, from the second not at all |
| `gamma_min`, `gamma_max` | 0.5, 2.5 | Limits of the lightness curve that takes the skin's lightness to the target's |
| `chroma_exponent`, `chroma_max` | 0.7, 0.16 | New chroma = target chroma x (chroma / skin chroma) ^ exponent, at most chroma_max |
| `chroma_floor` | 0.02 | A colour of less chroma is nearly grey: it has no reliable hue. A skin of less chroma (a Death Knight's) takes a gentler chroma ratio, and a colourful colour on it is weighed against the nearer of its hue and the hue of the sex's other skins: lips move, an eye keeps its colour |
| `hue_spread` | 0.3 | Share of a colour's hue difference from the skin that it keeps |
| `stats_alpha_min`, `stats_lightness_min`, `stats_lightness_max` | 128, 0.2, 0.97 | Which pixels count for the skin colour: alpha at least (when the texture has alpha), OKLab lightness between |

To tune it, run `skins` with `--preview` into a scratch folder (it writes nothing into the patch folder), look at the
PNGs, change `palette` (lighter or darker, more or less colourful) and run again. Lips or shadows that turn too blue:
lower `hue_spread`; too colourful: lower `chroma_max`. Any change gives new file names, which is fine: the old ones
leave the archive.

### The Bleakhold realm, step by step (skins)

On the VPS, as root, with the patches in `/srv/bleakhold-launcher/patches` and the game folder in
`/srv/bleakhold-launcher/base`:

1. The new code: `cd /root/bleak && git pull`.
2. The new skins, from the realm's own files (nothing on the realm changes yet):
   ```sh
   cd /root/bleak/Tools/RaceForge
   python3 -I raceforge.py skins --patches /srv/bleakhold-launcher/patches --client /srv/bleakhold-launcher/base \
     --out /root/raceforge-skins --force --preview
   echo "exit code: $?"
   ```
   It must print `exit code: 0`, for every pack combination a line like
   `all packs: CharSections.dbc from Patch-R.MPQ; <n> rows on <m> recoloured textures (<n> rows changed) -> Patch-R.MPQ`
   (the numbers are the realm's), `written: /root/raceforge-skins/client/Patch-R.MPQ (...)`, `... checks, 0 failed` and
   a `Next:` line with the install command. Look at `/root/raceforge-skins/preview/*.png` (copy them to your PC, for
   example with `scp root@<server>:/root/raceforge-skins/preview/*.png .`).
3. Into the patch folder, then publish:
   ```sh
   python3 -I raceforge.py install --from /root/raceforge-skins --patches /srv/bleakhold-launcher/patches
   bash /root/bleakserv/deploy/launcher/publish.sh
   ```
   Wait for `Published build ...`. Players see the new skins once their launcher has the new archive and they restart
   the game. The server needs nothing.
4. Optionally check: the same command as step 2 with `--out /root/raceforge-skins-check` prints `already up to date`.

## Installing an output folder (`raceforge.py install`)

`install` puts the archives of an output folder of `skins` or `update` into the realm's patch folder:

```sh
python3 -I raceforge.py install --from /root/raceforge-skins --patches /srv/bleakhold-launcher/patches [--dry-run]
```

- Each archive under `client/` goes to the same place in the patch folder (`client/enUS/` to `enUS/`). When the patch
  folder holds a link there (`Patch-R.MPQ` links to the download site's copy), the link stays and the file it points at
  is replaced.
- With `install.json` (which `skins` and `update` write), every file it replaces must still be the one the tool read,
  by size and modification time; otherwise the patches changed since, nothing is changed, and the tool must run again.
  An archive that came from the game folder (a patch of `base/Data`) or that is new must not be in the patch folder
  yet. A run whose checks failed is not installed. An output folder of an older RaceForge, without `install.json`, is
  installed anyway, and install says that this check was skipped.
- The file it replaces is kept in `<output folder>/old-patches/<path>`: a hard link when both are on one filesystem
  (no copy, no space), else a copy. A later install from the same folder keeps that backup while the patch folder
  still holds what the earlier one put there (`backup already there`), so it stays the file of before the first
  install. When another install (another tool's, from its own folder) has replaced the archive in between, the old
  backup moves to `old-patches-<n>/<path>` and the file replaced now is kept in its place (`older backup moved to
  ...`): going back from this folder then never undoes that other install.
- The new archive goes next to its destination as `<name>.new` (publish.sh only takes files that end in `.MPQ`) and is
  renamed over it in one step, so neither a player nor the publisher sees half a file. Where both are on one
  filesystem, the output's archive is moved, not copied. It prints `replaced: <file>` (or `added: <file>`) for each, and
  the publish command at the end. Running it again prints `already installed: <file>`.
- Each install writes `old-patches/installed.json`: per archive, the backup (or that install added the archive) and the
  file it put there, by size and modification time, written before the archive moves. `--force` of `skins` and
  `update` never removes `old-patches` or `old-patches-<n>`.
- `--dry-run` only lists what it would do, backups included. `--restore` goes by `installed.json`, not by
  `install.json`, so a later run of the tool into the same folder (`already up to date`, a new output not installed,
  or a run that failed) does not change what it undoes. It puts each backup back the same way (and removes an archive
  install added) when the patch folder still holds what install put there and the backup is still the file it
  replaced; when another install has replaced that archive since, it refuses and changes nothing (putting the old
  copy back would undo that one too). An archive already put back prints `already put back: <file>`. A folder without
  `installed.json` (an install by hand with the runbooks' earlier shell loop) is restored only where the patch
  folder's file is byte for byte the one in its `client/`, which that loop copied there; an archive such an install
  added stays.

## Finding a file in the realm's archives (`raceforge.py find`)

`find` tells which archive the client reads a file from, so a screen that looks different from the stock one (a
realm patch's own character creation screen, say) can be traced to the patch that brings it. It reads the game the
way `skins` does: `--client` (the game folder the launcher ships) with `--patches` over it, in the client's order
(see "Where the files go"), `alternate.MPQ` included, for every combination of the launcher's optional packs
(`archives.optional_packs` of races.json: `hd`, the Reforged HD pack). It changes nothing.

```sh
cd /root/bleak/Tools/RaceForge
python3 -I raceforge.py find --patches /srv/bleakhold-launcher/patches --client /srv/bleakhold-launcher/base \
  Interface/GlueXML/CharacterCreate.xml
```

prints, for a realm whose HD pack brings its own screen (the archive names are the realm's):

```text
Interface\GlueXML\CharacterCreate.xml
  all packs (hd): from Patch-Y.MPQ (patches, hd pack)
    in, lowest first: enUS/locale-enUS.MPQ (game), Patch-Y.MPQ (patches, hd pack)
  no packs: from enUS/locale-enUS.MPQ (game)
```

Each line is one kind of player: with every pack, without some, without any. `from` names the archive whose copy
that player's client reads (the highest that holds the file); `in, lowest first` every archive that holds it. Write
the path with `/` (or in single quotes): a shell drops the backslashes of `Interface\GlueXML\...` when it is not in
quotes, and `find` says so when a path (or a `--list` folder) has no folder left in it. Case does not matter.

| Option | What it does |
|---|---|
| `--grep TEXT` | Prints the lines of the copy the client reads that contain TEXT, in any case, with their line numbers (`35:`, as an editor counts them); once for each different copy, naming the players who read it. Repeat it for more texts. At most 200 lines (the `--` lines of `--after` count too), then how many matching lines were left out; text files only (an image says `not a text file`) |
| `--after N` | With `--grep`: also the N lines after each one (up to 50), so an XML button's `<Anchors>` show under its name; `--` separates the blocks (without `--after` there is none) |
| `--out FILE` | Writes the copy the client reads to FILE (or, for a folder, to the file's own name in it); a copy that other players read goes next to it as `<name>-2<ext>` |
| `--list FOLDER` | Lists every file under FOLDER that the archives' listfiles name, with the archive the client reads it from (with every pack); `*` marks a file from the patches folder, and `(no packs: ...)` a file other players read from another archive. An archive without a listfile is named in a note (find its files by name) |
| `--locale`, `--config` | As for `skins` |

The exit code is 0 when the file (or a file of the folder) was found.

### The Bleakhold realm: which patch draws the character creation screen

On the VPS, as root (each command prints a few lines to screenshot):

1. The glue files the realm's patches replace (`*`):
   ```sh
   cd /root/bleak/Tools/RaceForge
   python3 -I raceforge.py find --patches /srv/bleakhold-launcher/patches --client /srv/bleakhold-launcher/base \
     --list Interface/GlueXML
   ```
   When `GlueXML.toc` has a `*`, the files that patch's screens load:
   `... find ... Interface/GlueXML/GlueXML.toc --grep .` (every line with a dot: the file names).
2. The race buttons of the screen the players get, with their anchors:
   ```sh
   python3 -I raceforge.py find --patches /srv/bleakhold-launcher/patches --client /srv/bleakhold-launcher/base \
     Interface/GlueXML/CharacterCreate.xml --grep RaceButton --after 8
   ```
3. Its Lua: the race count, the button names, and how it shows racials:
   ```sh
   python3 -I raceforge.py find --patches /srv/bleakhold-launcher/patches --client /srv/bleakhold-launcher/base \
     Interface/GlueXML/CharacterCreate.lua --grep MAX_RACES --grep RaceButton --grep ABILITY --grep RACIAL --after 2
   ```
4. Both files whole, to send on:
   ```sh
   python3 -I raceforge.py find --patches /srv/bleakhold-launcher/patches --client /srv/bleakhold-launcher/base \
     Interface/GlueXML/CharacterCreate.xml --out /root/glue/
   python3 -I raceforge.py find --patches /srv/bleakhold-launcher/patches --client /srv/bleakhold-launcher/base \
     Interface/GlueXML/CharacterCreate.lua --out /root/glue/
   ```

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
the SQL on a model of the world database (run twice) and against bleakserv's linter. The Bleakhold realm's layout has
tests of its own: High Elf and Eredar in the slots 15 and 19 of `Patch-R.MPQ` with masks of the realm's own (rows of
a race alone, a Pandaren bit, the languages) and a server data/dbc with rows the client lacks; ChrRaces without the
races there, in an HD pack's copy, and a wrong `realm_id`; the SQL on a model of that realm's world database after the
earlier update for races 22 and 23 (run twice); `--server-sql-out` (one rev file, never a changed one, none when a
check fails, and none at all when the disk fills up or Ctrl-C comes while it is written). With a bleakserv checkout
next to this repository it also compares the server's `spell_dbc` columns, the pending world-database file and
mod-bleakhold's racial table with races.json.

`test_skins.py` covers `skins` and `install` with made-up textures and archives (`tests/synth_skins.py`, with a texture
painted like a fair elf skin: shading, pink lips, a green iris, an eye white, a dark-red cloth patch): the recolouring
of every format (palette with every alpha size; DXT1 four- and three-colour blocks with transparent texels, an order
flip, endpoints that become equal; DXT3; DXT5; BGRA; the levels as the client walks them; the refused formats), the
skin colours, their ranking and the palette, the eyes and lips on a Death Knight's nearly grey skin and a very pale
one, the client's archive order (base archives, patches over the game folder, locale archives), and the placement on
made-up realms: everything in `Patch-R.MPQ`; an HD pack archive below it that replaces a texture, with a pack archive
above it (its copy made again after a new row in `Patch-R.MPQ`, and removed by `"sections": []`) and without one
(refused); a second pack whose higher archive other players load; CharSections.dbc in two archives; running again, a
palette change and `"sections": []`; the refusals. `install`: a dry run, a linked destination (the link stays, the file behind
it is replaced and backed up), a patch that changed since, `--restore` (twice; after the tool ran again into the same
folder; after another tool's install in between, from either folder; a folder installed by hand), a folder without
`install.json`, and `update`'s output with its install line.

`test_find.py` covers `find` on a made-up game folder and patch folder: the archive each pack combination reads a
file from and every holder, `--grep` (several texts, `--after`, no `--` without it, the 200-line limit with the `--`
lines in it, a binary file, line numbers past a form feed, a Windows-1252 ellipsis or U+2028, none of which ends a
line), `--out` (a folder, one file per different copy), `--list` (the `*` marks, another combination's archive, a file
only one pack has), a file in no archive, a path and a `--list` folder a shell has stripped of their backslashes,
`alternate.MPQ` above every patch, and an archive without a listfile.

After a change to the Rec classes, regenerate the layouts with `py -3 -I Tools\RaceForge\raceforge.py schemas --write`.
