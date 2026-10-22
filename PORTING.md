# Bleakhold client — exe patch port map

Source: current patched `Wow.exe` (St0nys-AIO-WoW-EXE-Patcher selection + 2 custom patches), diffed and mapped to wowdecomp source via `// OFFSET:` tags.
Each patch must be re-implemented in C++ (byte patches don't apply to the x64 build).

Status: [ ] todo  [x] done  [-] not needed

## Not needed in x64 build
| Patch | Why |
|---|---|
| [-] laa (4GB) | x64 has no 4GB limit |
| [-] glue (custom GlueXML) | covered by `WOWDECOMP_DISABLE_SIGNATURE_CHECKS` (`FrameXML_CheckSignature`, LoadXML.cpp), which only matters for modified copies of GlueXML.toc; Bleakhold's own glue (CUSTOM loginui) needs neither |
| [-] awesome (AwesomeWotlkLib.dll) | already reverted in current Wow.exe; 32-bit DLL can't load in x64 anyway |

## 1. Graphics / HD look — port first
| Patch | What | Source |
|---|---|---|
| [x] farclip | farclip max 10000 | WorldParam_CVar.cpp — `FarClipCallback` |
| [x] horizon | horizonFarclipScale max 12 | WorldParam_CVar.cpp — `HorizonFarClipScaleCallback` |
| [x] envdetail | environmentDetail no 1.5 cap | WorldParam_CVar.cpp — `EnvironmentDetailCallback` |
| [x] grounddist | groundEffectDist max 3166 | WorldParam_CVar.cpp — `GroundEffectDistCallback` |
| [x] sliders | higher graphics slider max | GlueScriptEvents_Scripts.cpp + GameUI_Scripts.cpp — `Script_GetCVarMax` |
| [x] goscale | GameObject cat 0/4 view dist scales w/ envDetail | WorldScene.cpp — `CWorldScene::ScaleFadeDist` |
| [x] hdportraits | portraits 256px instead of 64 (render-target path; CPU fallback stays 64) | PortraitButton.cpp (`RTAlphaSupported` area) |
| [ ] iconsnap | sharp inline icons | GxuFontUtil.cpp — `ParseEmbeddedTexture` |
| [ ] glyphfix | garbled font glyphs | GxuFontMiscClasses.cpp — `RenderBatch`, `TEXTURECACHEROW::CreateNewDesc` |
| [x] occluder | Stormwind occluder fix | occluder table (World/Map code) |
| [x] bluemoon | blue moon in sky | data table @ 0x9D07C0 |
| [x] notransparency | no char fade on zoom-in | Unit_C.cpp — `CGUnit_C::SetMaxAlpha` |
| [ ] **CUSTOM lght** (side table of 4 extra point lights per M2 + 5 lights for map chunks, uploaded to VS constants c236+; only works with matching custom shaders) | more dynamic lights (new `.lght` section, light arrays enlarged) | CGxDevice.cpp (`InitLights`, `Light`, `LightEnable`, `LightSet`), CGxDeviceD3d/D3d9Ex/OpenGl `IStateSyncLights`, GxuLight.cpp, MapObj.cpp (`SetRenderModeLight`, `SetupLighting`), MapRenderChunk.cpp `SetVertexShader`, M2Scene.cpp `SelectLights`, M2Light.cpp (`AddLight`, `CameraSpace`, `SetupGxLights`), ShaderEffect.cpp `SetLocalLighting` |

## 2. Custom (not from St0ny)
| Patch | What | Source |
|---|---|---|
| [x] **CUSTOM modernassets** | Legion+ models, skins, animations, WMOs, split ADTs and BLPs converted as they are opened (WarcraftXL, GPL-3.0-or-later); bone-budget split, skin material rebuild, index starts past 65535, alpha-key cutoff for converted models, crash on modern shader ids | ThirdParty/WarcraftXL, Engine/Source/ModernAssets, SFile2-Core.cpp `SFile::OpenEx`, M2Modern.cpp, M2Shared.cpp, M2Model.cpp, CM2SceneRender.cpp, M2Scene.cpp |
| [x] **CUSTOM terraintiling** | modern tiles' per-texture tiling (MTXP), read from the tile's own trailing ATSC table and applied per layer (WarcraftXL wxl-modern-adt feature, GPL-3.0-or-later); stock tiles unchanged | ModernAssets.cpp `ModernAssetsForEachTileTiling`, MapTerrainTiling.cpp, MapRenderChunk.cpp (`SetVertexShader`, `RenderMultiPassVertexPixelShader[BigAlpha]`), MapArea.cpp (`Purge`, `~CMapArea`, `LoadTerrainTexture` for FileDataID `_s.blp` names) |
| [x] **CUSTOM procwater** | CVar `proceduralWater`: terrain and map object water and ocean draw with the procedural water material (LiquidType 100) when the game data has it | LiquidMaterialBank.cpp `Liquid::GetRenderLiquidType`, MapChunkLiquid.cpp, World.cpp, WorldParam_CVar.cpp |
| [x] **CUSTOM hdtextures** | textures over 4 MB never loaded (async budget); mip scratch overrun by chains over 1024; 2048 scratch and 32 MB budget on x64 | Texture.cpp — `AsyncTextureHandler`, `CreateBlpAsync`, `TextureInitialize`, `TextureLoadBlpMips` |
| [x] **CUSTOM races** | race ids up to 31 (High Elf 22, Eredar 23): race-indexed arrays sized to 32, unknown races allowed in IsRaceClassRestricted, Lua stack checked before the race and class lists, CharSections and facial hair rows for unknown races skipped, Bleakhold races borrow Blood Elf and Draenei scenes, emote voices, Death Knight filters and portraits when the data has none of their own | WoW/Common/BleakholdRaces.h, CharacterCreation.cpp (`Initialize`, `Shutdown`), CharacterCreation_Scripts.cpp, CharacterSelection_Scripts.cpp, SoundInterface2Emotes.cpp, SoundInterface2.cpp `DK_GetPlayerFilterName`, ComponentUtils.cpp, PortraitButton.cpp `SetPortraitTexture` |
| [x] **CUSTOM fix** | addon chat prefix and message copied with no bound into 3000-byte stack buffers; emote sound lookups kept pointers into an array that could move | ChatFrame.cpp (addon message receive), SoundInterface2Emotes.cpp `InitEmoteSounds` |
| [x] **CUSTOM loginui** | Bleakhold glue TOC loaded after GlueXML.toc (optional; no Blizzard files replaced): Bleakhold login screen, restyled dialog with a connecting progress bar, 12-race character creation | CGlueMgr.cpp — `CGlueMgr::Resume`; Interface/Bleakhold/Glue; Tools/BlpConvert |
| [x] **CUSTOM racedata** | High Elf and Eredar rows for ChrRaces and every table keyed by race, race-mask bits (faction-wide masks follow the race's faction), AzerothCore world SQL; built offline from the user's own DBCs and packed into `Data\patch-R.MPQ` | Tools/RaceForge, Tools/MpqPack |
| [x] **CUSTOM ui** | Bleakhold UI addon (Lua only) and its server protocol; addon messages no longer go into the whisper reply history | Interface/AddOns/Bleakhold, docs/BleakholdProtocol.md, Tools/UiLint (lint + tests), ChatFrame.cpp (whisper source recording) |
| [x] **CUSTOM uiserver** | server side of the Bleakhold UI protocol (AzerothCore module; no core change) | Server/mod-bleakhold |
| [x] **CUSTOM branding** | "Bleakhold" window title, popup captions and error log title; CI builds the player exe as `Bleakhold.exe` | Client.cpp, ConsoleDetect.cpp, ConsoleDevice.cpp, WoW/Source/CMakeLists.txt (`WOW_OUTPUT_OVERRIDE`) |
| [x] **CUSTOM names** | client name check always OK (returns 87) | ClientServices.cpp — `CharacterValidateName` |
| [-] **CUSTOM Lexara.dll loader** (file missing, loader was a no-op) | loads `Lexara.dll` at startup | WinMain.cpp `start`, StormRtl.cpp `StormRtlInitialize` — needs x64 Lexara.dll or port into source |

## 3. Character creation
| Patch | What | Source |
|---|---|---|
| [x] raceclass | >10 classes (random class) | CharacterCreation.cpp — `GetRandomClassID` |
| [x] charrandom | no auto-randomized look | CharacterCreation.cpp — `InitCharacterComponents` |
| [x] level101 | lvl 101+ druid stats, barber for all | tables.cpp — `GetGameTableValue` |

## 4. Gameplay / stability
| Patch | What | Source |
|---|---|---|
| [x] itemcache | refresh item cache immediately | DanceCache.cpp area (0x6695FD) |
| [x] timer | always precise timer | Win64/TimeManager.cpp — `Calibrate` |
| [x] mirrorfix | Mirror Image leak/crash | Unit_C.cpp — `OnReceiveMirrorImageDataFromServer` |
| [x] wmocube | missing WMO → error cube, not #134 | Map.cpp — `CMap::SafeOpen` |
| [x] areatrigger | 50 ms area trigger check | Player_C.cpp — `AreaTriggerCheck` |
| [x] swing (already in decomp) | no swing on right-click | Player_C.cpp — `MeleeModeEnter` |
| [x] npcanim | no NPC attack anim on turn | Unit_C.cpp — `PreAnimate` |
| [x] spellanim (already in decomp) | anim fix after cancelled channel | Unit_C.cpp — `OnChannelSpellChanged` |
| [x] ghostattack | ghost attack on evade | UnitCombat_C.cpp — `ClearAttackRound` |
| [x] naked | naked character bug | Player_C.cpp — `IsXRayVisionActive` area |
| [x] forcereaction | keep force reaction on /reload | GameUI.cpp — `LeaveWorld` |
| [x] mail | no 60s new-mail wait | MailInfo_Scripts.cpp — `Script_CheckInbox` |
| [x] deadchat | chat commands while dead | ChatFrame_Scripts.cpp — `Script_SendChatMessage` |

## 5. UI / window / sound
| Patch | What | Source |
|---|---|---|
| [x] tracker | auto-sort quest tracker | GameUI_CVar.cpp — `RegisterGameCVars` |
| [x] worldmap | advanced world map default | GameUI_CVar.cpp — `RegisterGameCVars` |
| [x] castbars | cast bars on all frames | GameUI.cpp — `ClearTarget` area |
| [x] bubblerange | chat bubble range 50 yd | ChatBubbleFrame.cpp `Update`, Unit_C.cpp `ChatBubbleShow` |
| [x] window / maximize | windowed + maximized default | ConsoleDevice_CVar.cpp — `RegisterGxCVars` |
| [x] windowfix (already in decomp) | no black screen to windowed | Client_CVar.cpp — `DesktopGammaCallback` |
| [ ] mouse | mouse flicker / camera jump | Win64/Input.cpp — `DispatchMouseButtonChanges`, `CenterMouse`, `OsWindowProc` |
| [x] sound | optimized sound settings | SoundInterface2.cpp `Init`, SoundInterface2_CVar.cpp |

## 6. Security / login
| Patch | What | Source |
|---|---|---|
| [x] scandll | disable Scan.dll | ScanDLLGlue.cpp |
| [x] noserverpatch / nosurvey | block server patches / hw survey | CGlueMgr.cpp — `CGlueMgr::Idle` |
| [x] skipbnet | skip Battle.net login | ClientServices.cpp — `Logon` |
| [x] skiprdp | skip RDP check | ConsoleDetect.cpp — `ConsoleDetectDetectHardware` |
| [x] nohttp | no HTTP to Battle.net | Win64/OsURLDownload.cpp — `DownloadString` |

## Still open
- mouse (CenterMouse rewrite + OsWindowProc cursor tracking)
- glyphfix, iconsnap (font cache hooks)
- CUSTOM lght (needs the custom shader MPQ it was built for)
- connect the server's own Mythic+, Dungeon Journey, Eclipse Rift and task systems to Server/mod-bleakhold (src/BleakholdUi.h)
- server code for the new races: taxi nodes, race/faction change, costume auras, racial riding trainers (an AzerothCore module)
- HD High Elf and Eredar models (palettized skins, geoset remap, 512 composite)

All Bleakhold changes are marked `BLEAKHOLD(<patch>)` in the source: `grep -rn BLEAKHOLD` lists them.
