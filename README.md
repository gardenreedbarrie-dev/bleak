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

## Running

1. Copy the `Data` folder of your 3.3.5a client into `bin/Win/`, so you have `bin/Win/Data/`.
2. Point `Data/<locale>/realmlist.wtf` at the server you want to connect to.
3. Start `bin/Win/WowClient64.exe` (or `Wow64.exe`).

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
| `.adt`, `.wdt`, `.wdl` | Split terrain tiles (`_tex0`, `_obj0`) merged into one 3.3.5a tile, with FileDataID textures and placements; the map's WDT and WDL reshaped to match |
| `.blp` | Uncompressed (BGRA) textures re-encoded to DXT5, retail character component textures converted for the 3.3.5a compositor, world textures and textures of modern assets larger than 2048 reduced to 2048 |

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

### Not supported yet

- Animations stored in the `.anim` files of a `.skel`-based model (`AFSB`/`AFSA` chunks) do not play, and a
  `.skel` that names a parent skeleton is not followed.
- Character models from the Shadowlands customization system need game data the 3.3.5a client does not
  have; the Warlords of Draenor era HD character models are the usual choice.
- Rendering features newer clients add: four-layer WMO materials, height-blended terrain, more than four
  terrain layers (layers 5-8 are dropped), WMO-to-outdoor visibility through open-sided spaces.

### License

The conversion code is GPL-3.0-or-later (`ThirdParty/WarcraftXL`, `Engine/Source/ModernAssets`,
`Engine/Source/Model2/M2Modern.*`). Whoever distributes a client built with it must make the corresponding
source code available under the same license.

## Layout

| Path | Contents |
|---|---|
| `Engine/Source/` | Engine modules: Storm, Gx (Direct3D 9 / OpenGL), Model2, Frame/FrameXML UI, SoundEngine, Lua, ... |
| `WoW/Source/` | Game modules: objects, world rendering, UI, networking, database, glue screens |
| `WoW/Common/` | Code shared by the game modules |
| `ThirdParty/` | Libraries linked from their upstream sources |
| `ThirdParty/WarcraftXL/` | WarcraftXL's modern-asset conversions (GPL-3.0-or-later) |
| `Engine/Source/ModernAssets/` | Runs those conversions on the files the client opens |
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
