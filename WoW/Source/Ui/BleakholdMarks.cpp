// BLEAKHOLD(marks): the Lua natives of glowing marks by player GUID (BleakholdMarks.h). GameUI_Scripts.cpp registers
// them with the other FrameXML functions; CGGameUI::Shutdown calls Reset.
#include "WoW/Source/Ui/BleakholdMarks.h"
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <vector>
#include "Engine/Source/FrameScript/FrameScript.h"
#include "Engine/Source/lua-5.1/src/lua.h"
#include "WoW/Common/ComponentCore/BleakMarkOwners.h"
#include "WoW/Common/ComponentCore/CharacterComponent.h"

namespace {
    // Each refusal reason is logged once per session (Logs\BleakholdMarks.log), not once per Set.
    bool s_loggedBadPath;
    bool s_loggedFull;
    bool s_loggedFullNames;

    BleakMarkOwners::Owners& Owners() {
        return CCharacterComponent::BleakMarkOwnerMap();
    }

    void LogRefusal(BleakMarkOwners::SetResult result) {
        bool* logged = nullptr;
        const char* line = nullptr;

        switch (result) {
            case BleakMarkOwners::SET_BAD_PATH:
                logged = &s_loggedBadPath;
                line = "marks: BleakholdMarks_Set refused a path (not a Character\\BleakholdMarks\\ or Character\\BleakholdEyes\\ .blp of at most 120 characters); logged once";
                break;
            case BleakMarkOwners::SET_FULL:
                logged = &s_loggedFull;
                line = "marks: BleakholdMarks_Set refused a new GUID, the map holds 4096 already; logged once";
                break;
            case BleakMarkOwners::SET_FULL_NAMES:
                logged = &s_loggedFullNames;
                line = "marks: BleakholdMarks_Set refused a new name, the pool holds 1024 already; logged once";
                break;
            default:
                return;
        }

        if (!*logged) {
            *logged = true;
            CCharacterComponent::BleakMarksLog(line);
        }
    }

    // A player's GUID: a number 1..4294967295 (the GUID counter, as the protocol sends it) or a "0x..." string (as
    // UnitGUID returns it) whose high half is 0. Anything else is refused.
    bool GuidArg(lua_State* L, int32_t index, uint64_t* guid) {
        uint64_t value = 0;
        bool ok = false;
        int32_t type = lua_type(L, index);

        // lua_isnumber would take "0x..." strings as numbers too, so the type decides.
        if (type == LUA_TNUMBER) {
            ok = BleakMarkOwners::GuidFromNumber(lua_tonumber(L, index), &value);
        } else if (type == LUA_TSTRING) {
            ok = BleakMarkOwners::ParseGuidString(lua_tostring(L, index), &value);
        }

        if (!ok || !BleakMarkOwners::IsPlayerGuid(value)) {
            return false;
        }

        *guid = value;
        return true;
    }

    // A path: a string, or nil / "" for none (null). Any other type, or a string with a zero byte in it, is refused.
    bool PathArg(lua_State* L, int32_t index, const char** path) {
        int32_t type = lua_type(L, index);

        if (type == LUA_TNONE || type == LUA_TNIL) {
            *path = nullptr;
            return true;
        }

        if (type != LUA_TSTRING) {
            return false;
        }

        size_t length = 0;
        const char* text = lua_tolstring(L, index, &length);

        if (!text || strlen(text) != length) {
            return false;
        }

        *path = length ? text : nullptr;
        return true;
    }

    uint32_t Rebuild(const std::vector<uint64_t>& guids) {
        uint32_t rebuilt = 0;

        for (uint64_t guid : guids) {
            rebuilt += CCharacterComponent::BleakMarksChanged(guid);
        }

        return rebuilt;
    }

    // BleakholdMarks_Set(guid, markPath, eyePath) -> ok, rebuilt. Both none clears. Nothing changes when ok is false
    // (a bad guid or path, or a full map or name pool); nothing is rebuilt when the entry already held these paths.
    int32_t Script_Set(lua_State* L) {
        uint64_t guid = 0;
        const char* mark = nullptr;
        const char* eye = nullptr;

        if (!GuidArg(L, 1, &guid) || !PathArg(L, 2, &mark) || !PathArg(L, 3, &eye)) {
            lua_pushboolean(L, 0);
            lua_pushnumber(L, 0);
            return 2;
        }

        BleakMarkOwners::SetResult result = Owners().Set(guid, mark, eye);

        if (!BleakMarkOwners::SetOk(result)) {
            LogRefusal(result);
            lua_pushboolean(L, 0);
            lua_pushnumber(L, 0);
            return 2;
        }

        uint32_t rebuilt = result == BleakMarkOwners::SET_CHANGED ? CCharacterComponent::BleakMarksChanged(guid) : 0;
        lua_pushboolean(L, 1);
        lua_pushnumber(L, static_cast<lua_Number>(rebuilt));
        return 2;
    }

    // BleakholdMarks_Clear(guid) -> existed, rebuilt.
    int32_t Script_Clear(lua_State* L) {
        uint64_t guid = 0;
        bool existed = GuidArg(L, 1, &guid) && Owners().Clear(guid);
        uint32_t rebuilt = existed ? CCharacterComponent::BleakMarksChanged(guid) : 0;
        lua_pushboolean(L, existed ? 1 : 0);
        lua_pushnumber(L, static_cast<lua_Number>(rebuilt));
        return 2;
    }

    // BleakholdMarks_ClearAll() -> removed. Each removed GUID is rebuilt.
    int32_t Script_ClearAll(lua_State* L) {
        std::vector<uint64_t> removed;
        uint32_t count = Owners().ClearAll(&removed);
        Rebuild(removed);
        lua_pushnumber(L, static_cast<lua_Number>(count));
        return 1;
    }

    // BleakholdMarks_Get(guid) -> markPath or nil, eyePath or nil.
    int32_t Script_Get(lua_State* L) {
        uint64_t guid = 0;
        const char* mark = nullptr;
        const char* eye = nullptr;

        if (GuidArg(L, 1, &guid)) {
            Owners().Get(guid, &mark, &eye);
        }

        if (mark) {
            lua_pushstring(L, mark);
        } else {
            lua_pushnil(L);
        }

        if (eye) {
            lua_pushstring(L, eye);
        } else {
            lua_pushnil(L);
        }

        return 2;
    }

    // BleakholdMarks_Count() -> entries, maxEntries.
    int32_t Script_Count(lua_State* L) {
        lua_pushnumber(L, static_cast<lua_Number>(Owners().Count()));
        lua_pushnumber(L, static_cast<lua_Number>(BleakMarkOwners::kMaxEntries));
        return 2;
    }

    // BleakholdMarks_BeginSync() -> entries. A full list follows: every entry is stale until it is Set or Cleared.
    int32_t Script_BeginSync(lua_State* L) {
        lua_pushnumber(L, static_cast<lua_Number>(Owners().BeginSync()));
        return 1;
    }

    // BleakholdMarks_EndSync() -> removed. The entries still stale go, and their GUIDs are rebuilt.
    int32_t Script_EndSync(lua_State* L) {
        std::vector<uint64_t> removed;
        uint32_t count = Owners().EndSync(&removed);
        Rebuild(removed);
        lua_pushnumber(L, static_cast<lua_Number>(count));
        return 1;
    }

    struct ScriptFunction {
        const char* name;
        int32_t (*function)(lua_State*);
    };

    const ScriptFunction kScriptFunctions[] = {
        { "BleakholdMarks_Set", &Script_Set },
        { "BleakholdMarks_Clear", &Script_Clear },
        { "BleakholdMarks_ClearAll", &Script_ClearAll },
        { "BleakholdMarks_Get", &Script_Get },
        { "BleakholdMarks_Count", &Script_Count },
        { "BleakholdMarks_BeginSync", &Script_BeginSync },
        { "BleakholdMarks_EndSync", &Script_EndSync },
    };
}

void CGBleakholdMarks::RegisterScriptFunctions() {
    for (const ScriptFunction& f : kScriptFunctions) {
        FrameScript_RegisterFunction(f.name, f.function);
    }
}

void CGBleakholdMarks::UnregisterScriptFunctions() {
    for (const ScriptFunction& f : kScriptFunctions) {
        FrameScript_UnregisterFunction(f.name);
    }
}

void CGBleakholdMarks::Reset() {
    Owners().Reset();
}
