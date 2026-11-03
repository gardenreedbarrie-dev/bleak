#ifndef WOW_COMMON_COMPONENTCORE_BLEAKMARKOWNERS_H
#define WOW_COMMON_COMPONENTCORE_BLEAKMARKOWNERS_H

#include <cstddef>
#include <cstdint>
#include <cstring>
#include <deque>
#include <string>
#include <unordered_map>
#include <vector>

// BLEAKHOLD(marks): glowing marks by player GUID, the parts that need no game code, so that
// Tools/MarkForge/tests/test_mark_owners.cpp can test them with the host compiler.
//
// On a realm whose CharSections cannot carry the marks (an HD pack), a mark and an eye colour are a cosmetic of their
// own (mod-bleakhold-ui protocol section 22): the addon hands Bleakhold.exe, by player GUID, the mark texture and the
// eye sprite to use (WoW/Source/Ui/BleakholdMarks.cpp, the Lua natives). CCharacterComponent::LoadMarkLayer and
// GeosRenderPrep take them from here in place of the features row's and the face row's third texture; everything
// after the name (the `_Glow` layer, atlas paste, glow bake and draw, size guards) is the CharSections path's.
//
// The names are interned in a pool that is never freed nor shrunk, so a `const char*` from it stays valid for the
// life of the process: CCharacterComponent::m_eyeSprite keeps the pointer it was given and compares it later.
namespace BleakMarkOwners {

static const uint32_t kMaxEntries = 4096; // the server lists at most 2000, plus previews and margin
static const uint32_t kMaxNames = 1024;   // 24 race-sexes x 17 names = 408 real ones
static const uint32_t kPathMax = 120;     // + `_Glow` (5) stays under the texture cache's 127
static const uint32_t kNone = 0xFFFFFFFF; // no name in that slot

static const char kMarkPrefix[] = "Character\\BleakholdMarks\\";
static const char kEyePrefix[] = "Character\\BleakholdEyes\\";

enum Slot {
    SLOT_MARK,
    SLOT_EYE,
};

// ---- GUIDs ----

// 3.3.5a player GUIDs are 0x00000000xxxxxxxx: the high half 0, the counter not 0.
inline bool IsPlayerGuid(uint64_t guid) {
    return (guid >> 32) == 0 && (guid & 0xFFFFFFFFull) != 0;
}

// "0x" or "0X" and 1-16 hex digits, nothing else (as UnitGUID returns it). Any GUID; IsPlayerGuid says whose.
inline bool ParseGuidString(const char* text, uint64_t* out) {
    if (!text || text[0] != '0' || (text[1] != 'x' && text[1] != 'X')) {
        return false;
    }

    uint64_t value = 0;
    size_t digits = 0;

    for (const char* p = text + 2; *p; p++, digits++) {
        uint32_t digit;

        if (*p >= '0' && *p <= '9') {
            digit = static_cast<uint32_t>(*p - '0');
        } else if (*p >= 'a' && *p <= 'f') {
            digit = static_cast<uint32_t>(*p - 'a' + 10);
        } else if (*p >= 'A' && *p <= 'F') {
            digit = static_cast<uint32_t>(*p - 'A' + 10);
        } else {
            return false;
        }

        if (digits >= 16) {
            return false;
        }

        value = (value << 4) | digit;
    }

    if (digits == 0) {
        return false;
    }

    *out = value;
    return true;
}

// A Lua number: the player's GUID counter, a whole number 1..4294967295 (as the protocol sends it).
inline bool GuidFromNumber(double number, uint64_t* out) {
    if (!(number >= 1.0 && number <= 4294967295.0)) {
        return false;
    }

    uint64_t value = static_cast<uint64_t>(number);

    if (static_cast<double>(value) != number) {
        return false;
    }

    *out = value;
    return true;
}

// ---- Paths ----

inline char LowerAscii(char c) {
    return c >= 'A' && c <= 'Z' ? static_cast<char>(c - 'A' + 'a') : c;
}

inline bool StartsWithNoCase(const char* text, size_t length, const char* prefix) {
    size_t prefixLength = strlen(prefix);

    if (length < prefixLength) {
        return false;
    }

    for (size_t i = 0; i < prefixLength; i++) {
        if (LowerAscii(text[i]) != LowerAscii(prefix[i])) {
            return false;
        }
    }

    return true;
}

inline bool EndsWithNoCase(const char* text, size_t length, const char* suffix) {
    size_t suffixLength = strlen(suffix);
    return length >= suffixLength && StartsWithNoCase(text + length - suffixLength, suffixLength, suffix);
}

// A mark or eye sprite path the exe takes: 1..120 bytes of `A-Z a-z 0-9 _ . \`, no `\\`, no `..`, no leading `\`,
// ending in `.blp` but not `_Glow.blp` (any case), under the slot's folder (case-insensitive).
inline bool PathOk(const char* path, Slot slot) {
    if (!path) {
        return false;
    }

    size_t length = strlen(path);

    if (length < 1 || length > kPathMax || path[0] == '\\') {
        return false;
    }

    for (size_t i = 0; i < length; i++) {
        char c = path[i];
        bool allowed = (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '_' || c == '.' || c == '\\';

        if (!allowed) {
            return false;
        }

        if (i > 0 && ((c == '\\' && path[i - 1] == '\\') || (c == '.' && path[i - 1] == '.'))) {
            return false;
        }
    }

    if (!EndsWithNoCase(path, length, ".blp") || EndsWithNoCase(path, length, "_glow.blp")) {
        return false;
    }

    return StartsWithNoCase(path, length, slot == SLOT_MARK ? kMarkPrefix : kEyePrefix);
}

// ---- The map ----

enum SetResult {
    SET_CHANGED,    // the entry was made, changed or removed: the GUID's components are rebuilt
    SET_UNCHANGED,  // the entry already held these values (or there was none to clear): nothing to rebuild
    SET_BAD_PATH,   // a path broke PathOk: nothing changed
    SET_FULL,       // a new entry would pass kMaxEntries: nothing changed
    SET_FULL_NAMES, // the new names would pass kMaxNames: nothing changed
};

inline bool SetOk(SetResult result) {
    return result == SET_CHANGED || result == SET_UNCHANGED;
}

class Owners {
    public:
    // Stores guid's mark and eye (null or "" for none; both none clears the entry). The caller checks the GUID.
    SetResult Set(uint64_t guid, const char* mark, const char* eye) {
        bool hasMark = mark && *mark;
        bool hasEye = eye && *eye;

        if ((hasMark && !PathOk(mark, SLOT_MARK)) || (hasEye && !PathOk(eye, SLOT_EYE))) {
            return SET_BAD_PATH;
        }

        if (!hasMark && !hasEye) {
            return this->Clear(guid) ? SET_CHANGED : SET_UNCHANGED;
        }

        auto found = this->m_entries.find(guid);

        if (found == this->m_entries.end() && this->m_entries.size() >= kMaxEntries) {
            return SET_FULL;
        }

        uint32_t markIndex = hasMark ? this->Find(mark) : kNone;
        uint32_t eyeIndex = hasEye ? this->Find(eye) : kNone;
        size_t newNames = (hasMark && markIndex == kNone) + (hasEye && eyeIndex == kNone);

        if (newNames == 2 && !strcmp(mark, eye)) {
            newNames = 1;
        }

        if (this->m_names.size() + newNames > kMaxNames) {
            return SET_FULL_NAMES;
        }

        if (hasMark && markIndex == kNone) {
            markIndex = this->Intern(mark);
        }

        if (hasEye && eyeIndex == kNone) {
            eyeIndex = this->Intern(eye);
        }

        if (found != this->m_entries.end()) {
            Entry& entry = found->second;
            entry.stale = false;

            if (entry.mark == markIndex && entry.eye == eyeIndex) {
                return SET_UNCHANGED;
            }

            entry.mark = markIndex;
            entry.eye = eyeIndex;
            return SET_CHANGED;
        }

        Entry entry;
        entry.mark = markIndex;
        entry.eye = eyeIndex;
        entry.stale = false;
        this->m_entries.emplace(guid, entry);
        return SET_CHANGED;
    }

    // Removes guid's entry; whether there was one.
    bool Clear(uint64_t guid) {
        return this->m_entries.erase(guid) != 0;
    }

    // Removes every entry; their GUIDs go to `removed` (when given) for the rebuild.
    uint32_t ClearAll(std::vector<uint64_t>* removed) {
        uint32_t count = static_cast<uint32_t>(this->m_entries.size());

        if (removed) {
            for (const auto& item : this->m_entries) {
                removed->push_back(item.first);
            }
        }

        this->m_entries.clear();
        return count;
    }

    // The entry's names, or null. False when guid has no entry.
    bool Get(uint64_t guid, const char** mark, const char** eye) const {
        auto found = this->m_entries.find(guid);

        if (found == this->m_entries.end()) {
            *mark = nullptr;
            *eye = nullptr;
            return false;
        }

        *mark = this->Name(found->second.mark);
        *eye = this->Name(found->second.eye);
        return true;
    }

    // What CCharacterComponent reads; an empty map costs no lookup.
    const char* Mark(uint64_t guid) const {
        const char* mark = nullptr;
        const char* eye = nullptr;

        if (guid && !this->m_entries.empty()) {
            this->Get(guid, &mark, &eye);
        }

        return mark;
    }

    const char* Eye(uint64_t guid) const {
        const char* mark = nullptr;
        const char* eye = nullptr;

        if (guid && !this->m_entries.empty()) {
            this->Get(guid, &mark, &eye);
        }

        return eye;
    }

    uint32_t Count() const {
        return static_cast<uint32_t>(this->m_entries.size());
    }

    bool Empty() const {
        return this->m_entries.empty();
    }

    uint32_t NameCount() const {
        return static_cast<uint32_t>(this->m_names.size());
    }

    // A full list is coming: every entry is stale until a Set or Clear of its GUID.
    uint32_t BeginSync() {
        for (auto& item : this->m_entries) {
            item.second.stale = true;
        }

        return this->Count();
    }

    // The list is done: the entries still stale go, and their GUIDs go to `removed` (when given) for the rebuild.
    uint32_t EndSync(std::vector<uint64_t>* removed) {
        uint32_t count = 0;

        for (auto it = this->m_entries.begin(); it != this->m_entries.end();) {
            if (it->second.stale) {
                if (removed) {
                    removed->push_back(it->first);
                }

                it = this->m_entries.erase(it);
                count++;
            } else {
                ++it;
            }
        }

        return count;
    }

    // Logout: no entries, no rebuild; the names stay (pointers to them may still be held).
    void Reset() {
        this->m_entries.clear();
    }

    private:
    struct Entry {
        uint32_t mark;
        uint32_t eye;
        bool stale;
    };

    const char* Name(uint32_t index) const {
        return index < this->m_names.size() ? this->m_names[index].c_str() : nullptr;
    }

    uint32_t Find(const char* name) const {
        for (size_t i = 0; i < this->m_names.size(); i++) {
            if (this->m_names[i] == name) {
                return static_cast<uint32_t>(i);
            }
        }

        return kNone;
    }

    uint32_t Intern(const char* name) {
        uint32_t index = this->Find(name);

        if (index != kNone) {
            return index;
        }

        // A deque never moves its elements as it grows, and a string is never changed once in: c_str() stays put.
        this->m_names.emplace_back(name);
        return static_cast<uint32_t>(this->m_names.size() - 1);
    }

    std::unordered_map<uint64_t, Entry> m_entries;
    std::deque<std::string> m_names;
};

} // namespace BleakMarkOwners

#endif
