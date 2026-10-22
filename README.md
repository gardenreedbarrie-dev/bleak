# wowdecomp

A C++ decompilation of the World of Warcraft 3.3.5a client (`Wow.exe`, build 12340, June 2010).

Join the discord for other clients and to show off some cool stuff you build.

https://discord.gg/DsZMGUD8aT

Every function is reconstructed from the original binary and keeps the address it came from in an
`// OFFSET:` tag, so each one can be compared against the original. The source tree follows the layout
of the original client (`Engine/Source/<Module>`, `WoW/Source/<Module>`, original file names).

x64 is the main target. Win32 still builds and is used to check struct layouts against the 32-bit
original.

## Progress

The percentages below measure how much of the original binary has a counterpart in this source tree. They do
**not** say how much of the game works, and the missing part is not missing gameplay: the client builds into a
complete executable and the game is 100% playable. Bugs could still be hiding, though; a ported function can behave differently
from the original.

Measured against the 12340 binary on 2026-10-15. A function counts as ported when its address is
tagged in the source.

| | Ported | Total | Share of the original |
|---|---:|---:|---:|
| Functions | 24,515 | 27,157 | 90.3% |
| Code bytes | 5,270,186 | 5,656,573 | 93.2% |

The total leaves out 658 functions that IDA identifies as compiler library code and 132 import thunks.
Most of the untagged remainder is code the build gets elsewhere: compiler-generated code (static
initializers, template instances) that our compiler emits on its own, C runtime helpers, and third-party
libraries that are linked from their upstream sources instead of being decompiled (FreeType, zlib, PCRE,
parts of FMOD Ex).

## Requirements

- Windows 10 or 11
- Visual Studio 2022 with the **Desktop development with C++** workload (MSVC v143 and a Windows SDK)
- CMake 3.10 or newer (the one that ships with Visual Studio works)
- For Win32 builds only: [NASM](https://www.nasm.us/), on `PATH` or passed as `-DNASM_EXECUTABLE=<path>`, and
  `DivxDecoder.dll` from your 3.3.5a client copied to `ThirdParty/DivxDecoder/` (the build copies it next to the
  executables; the x64 build uses its own decoder instead)
- A World of Warcraft **3.3.5a (12340)** client. No game data is included in this repository.

## Building

From a Developer PowerShell or any shell with `cmake` on `PATH`:

```powershell
git clone https://github.com/SatyPardus/wowdecomp.git
cd wowdecomp

# x64 (main target)
cmake -S . -B build/x64 -G "Visual Studio 17 2022" -A x64
cmake --build build/x64 --config Release --target WowClient --parallel

# Win32 (optional, needs NASM)
cmake -S . -B build/win32 -G "Visual Studio 17 2022" -A Win32
cmake --build build/win32 --config Release --target WowClient --parallel
```

In-source builds are refused, so keep the build directory separate (`build/` above).

The client is written to `bin/Win/`:

| Target | x64 | Win32 |
|---|---|---|
| `WowClient` | `WowClient64.exe` | `WowClient32.exe` |
| `Wow` | `Wow64.exe` | `Wow32.exe` |

`WowClient` is the client with a crash logger: it opens a console window and writes
`WowClient_crash.log` when the client crashes. `Wow` is the same client without it. You can also turn the
logger off in `WowClient` with `-DWOWCLIENT_CRASH_LOG=OFF`.

### Options

| CMake option | Default | Effect |
|---|---|---|
| `WOWDECOMP_DISABLE_SIGNATURE_CHECKS` | `OFF` | Skip the MPQ file and `.toc.sig` signature checks, so modified game data and interface files load |
| `WOWCLIENT_CRASH_LOG` | `ON` | Build `WowClient` with the crash logger |
| `WOWCLIENT_OUTPUT_OVERRIDE` | empty | Name the `WowClient` executable something other than `WowClient64` / `WowClient32` |
| `WOW_OUTPUT_OVERRIDE` | empty | Name the `Wow` executable something other than `Wow64` / `Wow32` |
| `BLEAKFX_REQUIRE_SHADERS` | `OFF` | Stop the configure when the Windows SDK's `fxc` is missing, instead of building BleakFx without its shaders (CI turns it on) |

## Running

1. Copy the `Data` folder of your 3.3.5a client into `bin/Win/`, so you have `bin/Win/Data/`.
2. Point `Data/<locale>/realmlist.wtf` at the server you want to connect to.
3. Start `bin/Win/WowClient64.exe` (or `Wow64.exe`).

## Download

The CI build (`Build Bleakhold Client`, artifact `bleakhold-client-x64`) is one folder to copy over a 3.3.5a
client: `Bleakhold.exe`, the glue screens in `Data\Interface\Bleakhold\Glue`, the emoji art in
`Data\Interface\Bleakhold\Emoji`, the UI addon in `Interface\AddOns\Bleakhold`, `Tools\BleakholdRaceForge.exe` and
`INSTALL.txt` (from `Tools/Package`), which explains the steps for players and for the server owner. It holds no
game data.

## Modern (HD) assets

The client also loads models, map objects, terrain and textures made for newer clients (Legion and
later), converting each file to the 3.3.5a format as it is opened. Files already in the 3.3.5a format are
loaded exactly as before. The conversions come from [WarcraftXL](https://github.com/WarcraftXL); see
`ThirdParty/WarcraftXL/README.md`.

| Files | What is converted |
|---|---|
| `.m2` | Chunked (`MD21`) and plain models of versions 272-274: textures named by FileDataID, split skeletons (`.skel`), cameras, particles, ribbons, animation ids |
| `.anim` | The `AFM2` wrapper of external animation files |
| `.skin` | The material contract a modern skin leaves out is rebuilt when the model loads, and sections drawing with more bones than the GPU holds per draw are split (this applies to every model) |
| `.wmo` | Root and group files: modern-only chunks, shaders, material ids, FileDataID textures and doodads |
| `.adt`, `.wdt`, `.wdl` | Split terrain tiles (`_tex0`, `_obj0`) merged into one 3.3.5a tile, with FileDataID textures and placements; each texture keeps the tiling the tile gives it (`MTXP`); the map's WDT and WDL reshaped to match |
| `.blp` | Uncompressed (BGRA) textures re-encoded to DXT5, retail character component textures converted for the 3.3.5a compositor, world textures and textures of modern assets larger than 2048 reduced to 2048 (on x64; on Win32 the caps are 1024 for modern assets and 512, or 256 with `environmentDetail` below 0.75, for world textures) |

Skins with more than 65535 indices (retail character models) are drawn correctly, and textures larger than
1024 load: before, a texture file over 4 MB never finished loading and a chain over 1024 overran the mip
scratch buffer.

### Adding modern assets

1. Export the files from a retail installation with their paths, for example with
   [wow.export](https://github.com/Kruithne/wow.export) or CASC Explorer. The client looks up a model's
   skins and animations by name (`<model>00.skin`, `<model><anim>-<variation>.anim`), so keep the names
   the tools give them.
2. Pack them into a patch archive in `Data`, for example `Data/patch-Z.MPQ`, with the paths the client
   asks for (`Creature\...`, `World\...`). The CI build already accepts unsigned archives
   (`WOWDECOMP_DISABLE_SIGNATURE_CHECKS`).
3. Put the community listfile (`listfile.csv`, `id;path` per line) next to the executable, in `Data`, or
   inside an archive. Modern assets name many of their files by FileDataID; without the listfile those
   textures and placements fall back to placeholders. A listfile trimmed to the files you ship loads faster.
4. Point the game data at the new files (`CreatureDisplayInfo.dbc`, `ItemDisplayInfo.dbc`, ...) as usual.

The client writes what it converted, and what it could not, to `Logs/ModernAssets.log`. Set the environment
variable `WXL_VERBOSE_ASSET_LOGS=1` to log every converted file.

### Water

| CVar | Default | What it does |
|---|---|---|
| `proceduralWater` | `0` | Ocean, lake and river water, on terrain and in map objects, draws with the procedural water material (`LiquidType.dbc` row 100, "Basic Procedural Water") instead of the animated texture frames. Stays off when that row or its shaders are missing from the game data. Water already loaded keeps its look until its area loads again. |

### Not supported yet

- Animations stored in the `.anim` files of a `.skel`-based model (`AFSB`/`AFSA` chunks) do not play, and a
  `.skel` that names a parent skeleton is not followed.
- Character models from the Shadowlands customization system need game data the 3.3.5a client does not
  have; the Warlords of Draenor era HD character models are the usual choice.
- Rendering features newer clients add: four-layer WMO materials, height-blended terrain layers, more than
  four terrain layers (layers 5-8 are dropped, as WarcraftXL drops them too), WMO-to-outdoor visibility
  through open-sided spaces. WarcraftXL's height-blend terrain shaders read a different register layout
  from the one its own height-blend code uploads, so they are not used.

### License

The conversion code is GPL-3.0-or-later (`ThirdParty/WarcraftXL`, `Engine/Source/ModernAssets`,
`Engine/Source/Model2/M2Modern.*`, `WoW/Source/WorldClient/MapTerrainTiling.*`). Whoever distributes a client built with it must make the corresponding
source code available under the same license.

## Bleakhold races

The client accepts race ids up to 31 (`WoW/Common/BleakholdRaces.h`). High Elf (22, Alliance, built from Blood
Elf) and Eredar (23, Horde, built from Draenei) need game data that is made from your own 3.3.5a DBCs; no game
data is in this repository:

```powershell
py -3 -I Tools\RaceForge\raceforge.py build --dbc C:\azerothcore\data\dbc --out C:\bleakhold\raceforge-out --mpq
```

Or double-click `Tools\BleakholdRaceForge.exe` from the CI package and drag the dbc folder into it.

- Client: copy `raceforge-out\client\patch-R.MPQ` into the client's `Data` folder. The client reads DBC files
  only from MPQ archives; `Tools/MpqPack` builds them.
- Server: copy the files of `raceforge-out\server\dbc` into the server's `data\dbc`, and run
  `raceforge-out\server\sql\bleakhold_races.sql` on the world database.
- Character creation shows the new races with the Bleakhold glue files installed (see below).
- Until their own art exists, both races use the models, scenes, voices and portraits of their template race.

See `Tools/RaceForge/README.md` for the race settings (`races.json`) and what the server still needs.

## Bleakhold UI

The in-game Bleakhold interface is a built-in addon in `Interface/AddOns/Bleakhold`:
- Activities: daily and weekly tasks, the Dungeon Journey board and queue, keystones, Eclipse Rift.
- Collections, Season and Leaderboards windows.
- Minimap buttons, the Mythic+ tracker and keystone countdown (with a DBM pull bar), task toasts, item tooltip
  lines and coloured server announcements.

Copy the folder to `Interface\AddOns\Bleakhold` next to the executable. `/bh` (or `/bleakhold`) opens it,
`/bh help` lists the commands, and `/bh demo` shows every window with sample data without a server.

It talks to the server only through addon messages and sends intents only; the server decides everything. The
message format for the server module is in `docs/BleakholdProtocol.md`. Until the server answers its `HELLO`,
the addon sends nothing else.

Checks (Linux; needs g++, python3, xmllint): `Tools/UiLint/check.sh` builds a host Lua from the client's own Lua
5.1 source, lints the addon against the 3.3.5a API extracted from this source tree, and runs the unit tests.
The art is generated with `python3 -I Tools/UiLint/make_art.py`.

## Bleakhold server module

`Server/mod-bleakhold-ui/` is the server half of the Bleakhold UI: an AzerothCore module (GPL-2.0-or-later, like
AzerothCore) that implements `docs/BleakholdProtocol.md`. Copy the folder to `azerothcore-wotlk/modules/`,
re-run CMake and build; the worldserver applies its SQL itself and installs `mod_bleakhold_ui.conf.dist` next to your
other module configs. `.bleakhold test all` in game fills every window with sample data.

Out of the box it handles the protocol (strict parsing, rate limits, handshake, revisions, chunking) and the parts
that need no custom system: definitions, week schedule, season and war effort, legacy sets, leaderboards, server
firsts and the chat tags. Keystones, the Dungeon Journey board and queue, the Eclipse Rift and tasks come from your
own systems through `Server/mod-bleakhold-ui/src/BleakholdUi.h` (one function per server message, one handler per
button); `Server/mod-bleakhold-ui/README.md` shows how to connect each one.

Tests (Linux; clang or g++, python3): `Server/mod-bleakhold-ui/tests/run_tests.sh` checks the module against every
example in the protocol document, runs its messages through the addon's own Lua parser and every message the addon
sends through the module, and fuzzes the parser under AddressSanitizer.

## Emoji bubbles

A player picks an emoji in Collections > Animations > Emojis, on page 4 of the emote wheel or with
`/bh emoji <name>` (`/bh emoji list` shows them all), and everyone nearby sees it pop up over that character's head
for 3.25 s. The addon sends `EMOJI <id>` (`docs/BleakholdProtocol.md`, section 13); the server module checks it
(feature on, known id, cooldown, not muted) and calls `player->SendPlaySpellVisual(900000 + id)`, which AzerothCore
sends as `SMSG_PLAY_SPELL_VISUAL` to every player in range. The Bleakhold client (BLEAKHOLD(emoji),
`WoW/Source/Ui/EmojiBubbleFrame.cpp`) catches kits 900000 to 900255 before it looks in SpellVisualKit and draws the
emoji over that unit like a chat bubble, above its name and any chat bubble. Stock clients find no such kit and
ignore the packet.

- Install: copy `Interface/Bleakhold/Emoji` from this repository to `<client>\Data\Interface\Bleakhold\Emoji\`
  (the CI package has it there), or pack it into a `Data\patch-?.MPQ` under the same path. Without it no bubble is
  drawn, and the addon shows a plain icon in place of each picture.
- Client settings: the CVars `emojiBubbles` (default `1`; `/bh emojis on|off` shows or hides every emoji bubble,
  yours too) and `emojiBubbleScale` (`0.5` to `2`, default `1.0`; `/console emojiBubbleScale 1.5`), saved in
  `Config.wtf`.
- Server settings (`mod_bleakhold_ui.conf.dist`): `BleakholdUi.Emoji.Enable` (default `1`; HELLO feature bit 64)
  and `BleakholdUi.Emoji.CooldownMs` (default `2500`; the addon itself waits 3.25 s between two emojis).
- Catalogue: `Tools/EmojiForge/emojis.json` lists the emojis: 73 Noto Emoji 3D images and 10 text emotes (GG, EZ,
  LOL, RIP, OMG, WOW, NICE, BRB, AFK, GLHF). `python3 -I Tools/EmojiForge/emojiforge.py generate` writes the
  addon's `EmojiData.lua`, the module's `src/BleakholdEmoji.h` and the art's `NOTICE.md` from it, `art` draws the
  BLPs (needs Pillow and a noto-emoji checkout) and `check` validates all of it. Ids go on the wire and into saved
  wheels, so the catalogue is append-only; a new emoji needs a rebuilt server module and a new client package
  (`Tools/EmojiForge/README.md`).
- Licences: the emoji images come from Google's Noto Emoji (Copyright 2013 Google LLC; the project's LICENSE is the
  SIL Open Font License 1.1 and its README puts image resources under the Apache License 2.0, so both texts are in
  `Interface/Bleakhold/Emoji`); the text emotes are drawn with the Bangers font (SIL Open Font License 1.1).
  `Interface/Bleakhold/Emoji/NOTICE.md` names the source of every file.

## Graphics (BleakFx)

The Bleakhold client post-processes the 3D world after it is drawn and before the interface
(BLEAKHOLD(bleakfx), `Engine/Source/BleakFx`): ambient occlusion and light shafts from the depth buffer, bloom,
clarity (local contrast), colour grading with a filmic contrast curve, vignette, FXAA and contrast-adaptive
sharpening. The interface, chat and emoji bubbles stay sharp on top. In game, `/bh graphics` (or a key binding
in Key Bindings > Bleakhold) opens the settings window with presets (Off, Classic+, Bleakhold, Cinematic) and a
slider for each effect; they are the `bleakFx*` CVars, saved in `Config.wtf`.

- Needs the Direct3D 9 renderer (the default, `gxApi d3d9` or `d3d9ex`) and shader model 3; with anything else
  the frame is drawn exactly as by the stock client. Ambient occlusion and light shafts also need Multisampling
  1x: an INTZ depth texture stands in for the back buffer's depth buffer (`Engine/Source/Gx/BleakDepth.h`), and
  INTZ cannot be multisampled. FXAA replaces the multisampling.
- The bloom stands in for the stock full screen glow; the underwater and drunk blur stay. Zones whose light
  settings make them glowier get a little more bloom.
- Shaders: `Engine/Source/BleakFx/Shaders/*.hlsl` (ps_3_0 and vs_3_0) are compiled with the Windows SDK's `fxc`
  during the build and embedded in the executable, so they need no game files. Without `fxc` the client builds
  without them and BleakFx stays off.
- CVars: `bleakFx` (on/off), `bleakFxAO`, `bleakFxAORadius`, `bleakFxSunShafts`, `bleakFxBloom`,
  `bleakFxBloomThreshold`, `bleakFxClarity`, `bleakFxContrast`, `bleakFxSaturation`, `bleakFxVibrance`,
  `bleakFxWarmth`, `bleakFxBrightness`, `bleakFxShadows`, `bleakFxVignette`, `bleakFxAA` (0 off, 1 FXAA) and
  `bleakFxSharpen`; each one's description gives its range.
- Methods: ambient occlusion after Scalable Ambient Obscurance (McGuire, Mara and Luebke, 2012), bloom after
  Jimenez's downsample and upsample filters (2014), FXAA after Timothy Lottes' FXAA 3.11, sharpening after AMD
  FidelityFX CAS (MIT). The shaders are written for this client; none is copied from those sources.

## Login screen and character creation

The client loads `Interface\Bleakhold\Glue\BleakholdGlue.toc` right after the stock
`Interface\GlueXML\GlueXML.toc` on every glue load (BLEAKHOLD(loginui), `CGlueMgr::Resume`). Those files
restyle and extend the stock screens from Lua: the Bleakhold login screen, a restyled dialog with a connecting
progress bar, and character creation with the High Elf and Eredar races and a First Name and a Last Name box
(the server's mod-two-names accepts "First Last"; the last name is optional). No Blizzard file is replaced, so
this works with signature checks on or off.

- Install: copy `Interface/Bleakhold/Glue` from this repository to `<client>\Data\Interface\Bleakhold\Glue\`
  (or `<client>\Interface\Bleakhold\Glue\`), or pack it into a `Data\patch-?.MPQ` under the same path, before
  starting the client. Without it the stock screens appear. Do not use `<client>\Interface\GlueXML`: the client
  renames that folder on every glue load.
- Settings (links, skipping the agreement screens, the Login button waiting for both fields, two names on or
  off) are at the top of `BleakholdStrings.lua`.
- Tests: `Tools/UiLint/glue/run.sh` runs the login, race and name scenarios against a mock of the glue API
  (part of `Tools/UiLint/check.sh`).
- Fonts: Marcellus and Marcellus SC, SIL Open Font License 1.1 (`Fonts/OFL.txt`).
- Art: `Tools/BlpConvert/make_login_art.py` draws the login art (needs Pillow);
  `Tools/BlpConvert/blpconvert.py IN OUT.blp [--format dxt1|dxt5|bgra] [--size WxH|--pad]` converts any picture
  to a BLP the client loads. Textures must be powers of two.

## Layout

| Path | Contents |
|---|---|
| `Engine/Source/` | Engine modules: Storm, Gx (Direct3D 9 / OpenGL), Model2, Frame/FrameXML UI, SoundEngine, Lua, ... |
| `WoW/Source/` | Game modules: objects, world rendering, UI, networking, database, glue screens |
| `WoW/Common/` | Code shared by the game modules |
| `ThirdParty/` | Libraries linked from their upstream sources |
| `ThirdParty/WarcraftXL/` | WarcraftXL's modern-asset conversions (GPL-3.0-or-later) |
| `Tools/MpqPack/` | Python tool that packs files into an MPQ patch archive the client loads (`Data\patch-<letter>.MPQ`) |
| `Tools/RaceForge/` | Python tool that adds the Bleakhold races (High Elf, Eredar) to your own DBCs and writes the AzerothCore SQL |
| `Tools/BlpConvert/` | Python tool that converts pictures to BLP textures; draws the login art |
| `Tools/EmojiForge/` | Python tool that holds the emoji catalogue and makes the emoji art, the addon's list and the server module's list |
| `Interface/Bleakhold/Glue/` | Bleakhold login screen and character creation (glue Lua, art, fonts) |
| `Interface/Bleakhold/Emoji/` | Emoji bubble art (BLP, made by `Tools/EmojiForge`) with its licences and `NOTICE.md` |
| `Interface/AddOns/Bleakhold/` | Bleakhold UI addon (Activities, Mythic+, Rift, Collections with Animations, emote wheel, Season, Leaderboards) |
| `Tools/UiLint/` | Lint and unit tests for the Bleakhold Lua (host Lua built from the client's own source) |
| `docs/BleakholdProtocol.md` | Message protocol between the Bleakhold server module and the UI |
| `Server/mod-bleakhold-ui/` | AzerothCore module: server side of the Bleakhold UI protocol |
| `Engine/Source/ModernAssets/` | Runs those conversions on the files the client opens |
| `Engine/Source/BleakFx/` | Post-processing of the 3D world (ambient occlusion, light shafts, bloom, grading, FXAA, sharpening) and its HLSL shaders |
| `Tools/WowClient/` | The `WowClient` executable target |
| `Tools/XvidDecoder/` | x64 movie decoder that replaces the original 32-bit `DivxDecoder.dll` |

## Special thanks

- [WarcraftXL](https://github.com/WarcraftXL), for the modern-asset conversions
- [binana](https://github.com/thunderbrewhq/binana)
- [thunderbrew](https://github.com/thunderbrewhq/thunderbrew)
- [whoa](https://github.com/whoahq/whoa)
- TOMRUS, for the initial IDB
- Everyone who has reported bugs so far
- The WoW modding community
