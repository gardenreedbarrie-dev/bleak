// Tests of WoW/Common/ComponentCore/BleakMarkOwners.h, the game-free part of glowing marks by player GUID
// (BLEAKHOLD(marks)): which GUIDs are players' (Lua numbers and "0x" strings), the path rules of each slot, Set, Clear
// and Get, the entry and name limits, the name pool's stable pointers, and the sync generation.
// run_marks_core.sh builds and runs it with the host compiler.
#include "WoW/Common/ComponentCore/BleakMarkOwners.h"
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

using namespace BleakMarkOwners;

namespace {
    int s_failed = 0;
    int s_checks = 0;

    void Check(bool ok, const std::string& what) {
        s_checks++;

        if (!ok) {
            s_failed++;
            printf("FAIL: %s\n", what.c_str());
        }
    }

    std::string Mark(uint32_t n) {
        return "Character\\BleakholdMarks\\NightElf\\Female\\Design" + std::to_string(n) + "_EluneBlue.blp";
    }

    std::string Eye(uint32_t n) {
        return "Character\\BleakholdEyes\\NightElf\\Female\\Eye_Colour" + std::to_string(n) + ".blp";
    }

    bool Same(const char* a, const char* b) {
        return (!a && !b) || (a && b && !strcmp(a, b));
    }

    void TestGuids() {
        uint64_t guid = 0;
        Check(ParseGuidString("0x0000000000000004", &guid) && guid == 4, "a 16-digit player GUID parses");
        Check(ParseGuidString("0X4b1", &guid) && guid == 0x4B1, "0X and mixed-case hex parse");
        Check(ParseGuidString("0xF130000000001234", &guid) && guid == 0xF130000000001234ull && !IsPlayerGuid(guid), "a creature GUID parses but is no player's");
        Check(ParseGuidString("0xFFFFFFFFFFFFFFFF", &guid) && guid == 0xFFFFFFFFFFFFFFFFull, "16 F digits parse");
        Check(!ParseGuidString("0x00000000000000001", &guid), "17 digits are refused");
        Check(!ParseGuidString("0x", &guid), "no digits are refused");
        Check(!ParseGuidString("1201", &guid), "a decimal string is refused");
        Check(!ParseGuidString("x1201", &guid) && !ParseGuidString("00x1", &guid), "no 0x prefix is refused");
        Check(!ParseGuidString("0x12g4", &guid) && !ParseGuidString("0x12 ", &guid) && !ParseGuidString(" 0x12", &guid), "other characters are refused");
        Check(!ParseGuidString("", &guid) && !ParseGuidString(nullptr, &guid), "empty and null are refused");

        Check(IsPlayerGuid(1) && IsPlayerGuid(0xFFFFFFFFull), "counters 1 and 2^32-1 are players");
        Check(!IsPlayerGuid(0), "GUID 0 is no player");
        Check(!IsPlayerGuid(0x100000000ull) && !IsPlayerGuid(0x0000000100000001ull), "a high half is no player");

        Check(GuidFromNumber(1.0, &guid) && guid == 1, "the number 1 is a GUID");
        Check(GuidFromNumber(4294967295.0, &guid) && guid == 0xFFFFFFFFull, "the number 2^32-1 is a GUID");
        Check(GuidFromNumber(1201.0, &guid) && guid == 1201, "the number 1201 is a GUID");
        Check(!GuidFromNumber(0.0, &guid) && !GuidFromNumber(-1.0, &guid), "0 and negatives are refused");
        Check(!GuidFromNumber(4294967296.0, &guid), "2^32 is refused");
        Check(!GuidFromNumber(1.5, &guid), "fractions are refused");
        double nan = 0.0;
        nan = nan / nan;
        Check(!GuidFromNumber(nan, &guid), "NaN is refused");
        Check(!GuidFromNumber(1e300, &guid), "huge numbers are refused");
    }

    void TestPaths() {
        Check(PathOk(Mark(1).c_str(), SLOT_MARK), "a mark path is a mark");
        Check(PathOk(Eye(1).c_str(), SLOT_EYE), "an eye path is an eye");
        Check(!PathOk(Mark(1).c_str(), SLOT_EYE), "a mark path is no eye");
        Check(!PathOk(Eye(1).c_str(), SLOT_MARK), "an eye path is no mark");
        Check(PathOk("character\\bleakholdmarks\\Orc\\Male\\A_B.BLP", SLOT_MARK), "prefix and .blp in any case");
        Check(PathOk("CHARACTER\\BLEAKHOLDEYES\\Orc\\Male\\Eye_BloodRed.Blp", SLOT_EYE), "the eye prefix in any case");
        Check(!PathOk("Character\\BleakholdMarks\\Orc\\Male\\A_B_Glow.blp", SLOT_MARK), "a _Glow file is refused");
        Check(!PathOk("Character\\BleakholdMarks\\Orc\\Male\\A_B_GLOW.BLP", SLOT_MARK), "a _GLOW file is refused");
        Check(PathOk("Character\\BleakholdMarks\\Orc\\Male\\A_BGlow.blp", SLOT_MARK), "Glow without the underscore is a name");
        Check(!PathOk("\\Character\\BleakholdMarks\\Orc\\Male\\A_B.blp", SLOT_MARK), "a leading backslash is refused");
        Check(!PathOk("Character\\BleakholdMarks\\\\Orc\\Male\\A_B.blp", SLOT_MARK), "a double backslash is refused");
        Check(!PathOk("Character\\BleakholdMarks\\..\\Male\\A_B.blp", SLOT_MARK), "a .. is refused");
        Check(!PathOk("Character\\BleakholdMarks\\Orc\\Male\\A..blp", SLOT_MARK), "a .. before blp is refused");
        Check(!PathOk("Character/BleakholdMarks/Orc/Male/A_B.blp", SLOT_MARK), "forward slashes are refused");
        Check(!PathOk("Character\\BleakholdMarks\\Orc\\Male\\A B.blp", SLOT_MARK), "a space is refused");
        Check(!PathOk("Character\\BleakholdMarks\\Orc\\Male\\A-B.blp", SLOT_MARK), "a dash is refused");
        Check(!PathOk("Character\\BleakholdMarks\\Orc\\Male\\A_B.tga", SLOT_MARK), "another extension is refused");
        Check(!PathOk("Character\\BleakholdMarks\\Orc\\Male\\A_B.blp.", SLOT_MARK), "a trailing dot is refused");
        Check(!PathOk("Character\\BleakholdMarks\\Orc\\Male\\A_B", SLOT_MARK), "no extension is refused");
        Check(!PathOk("Character\\Bleakhold\\Orc\\Male\\A_B.blp", SLOT_MARK), "another folder is refused");
        Check(!PathOk("Character\\BleakholdMarksX\\A.blp", SLOT_MARK), "a longer folder name is refused");
        Check(!PathOk("", SLOT_MARK) && !PathOk(nullptr, SLOT_EYE), "empty and null are refused");
        Check(!PathOk("Character\\BleakholdMarks\\Orc\\Male\\A\xC3\xA9.blp", SLOT_MARK), "non-ASCII bytes are refused");

        // The 120-byte edge.
        std::string prefix = "Character\\BleakholdMarks\\";
        std::string at120 = prefix + std::string(120 - prefix.size() - 4, 'a') + ".blp";
        std::string at121 = prefix + std::string(121 - prefix.size() - 4, 'a') + ".blp";
        Check(at120.size() == 120 && PathOk(at120.c_str(), SLOT_MARK), "a 120-byte path is taken");
        Check(at121.size() == 121 && !PathOk(at121.c_str(), SLOT_MARK), "a 121-byte path is refused");
        Check(at120.size() + 5 < 127, "120 + _Glow stays under the texture cache's 127");

        // The longest real names of the contract (78 and 83 with _Glow).
        std::string longest = "Character\\BleakholdMarks\\NightElf\\Female\\CenarionVines_MoonwellTeal.blp";
        Check(PathOk(longest.c_str(), SLOT_MARK) && longest.size() <= kPathMax, "a real NightElf female mark is taken");
    }

    void TestSetClearGet() {
        Owners owners;
        const char* mark = nullptr;
        const char* eye = nullptr;

        Check(owners.Empty() && owners.Count() == 0 && !owners.Mark(5) && !owners.Eye(5), "a new map is empty");
        Check(!owners.Get(5, &mark, &eye) && !mark && !eye, "Get of an unknown GUID has nothing");

        Check(owners.Set(5, Mark(1).c_str(), Eye(1).c_str()) == SET_CHANGED, "Set makes an entry");
        Check(owners.Get(5, &mark, &eye) && Same(mark, Mark(1).c_str()) && Same(eye, Eye(1).c_str()), "Get reads both names");
        Check(Same(owners.Mark(5), Mark(1).c_str()) && Same(owners.Eye(5), Eye(1).c_str()), "Mark and Eye read them");
        Check(!owners.Mark(0) && !owners.Eye(0), "owner 0 reads nothing");
        Check(owners.Count() == 1 && owners.NameCount() == 2, "one entry, two names");

        Check(owners.Set(5, Mark(1).c_str(), Eye(1).c_str()) == SET_UNCHANGED, "the same Set changes nothing");
        Check(owners.Count() == 1 && owners.NameCount() == 2, "and adds nothing");

        Check(owners.Set(5, Mark(2).c_str(), Eye(1).c_str()) == SET_CHANGED, "another mark changes the entry");
        Check(Same(owners.Mark(5), Mark(2).c_str()) && Same(owners.Eye(5), Eye(1).c_str()), "the mark changed, the eye kept");

        Check(owners.Set(5, nullptr, Eye(1).c_str()) == SET_CHANGED, "an eye alone changes the entry");
        Check(!owners.Mark(5) && Same(owners.Eye(5), Eye(1).c_str()), "no mark, the eye");
        Check(owners.Set(5, "", Eye(1).c_str()) == SET_UNCHANGED, "\"\" is none as nil is");

        Check(owners.Set(6, Mark(3).c_str(), "") == SET_CHANGED, "a mark alone makes an entry");
        Check(Same(owners.Mark(6), Mark(3).c_str()) && !owners.Eye(6), "the mark, no eye");

        Check(owners.Set(5, nullptr, nullptr) == SET_CHANGED && !owners.Get(5, &mark, &eye), "both none clears");
        Check(owners.Set(5, "", "") == SET_UNCHANGED, "both none with no entry changes nothing");
        Check(owners.Count() == 1, "one entry left");

        Check(owners.Set(6, "Character\\BleakholdMarks\\A_Glow.blp", nullptr) == SET_BAD_PATH, "a bad mark fails");
        Check(owners.Set(6, Mark(3).c_str(), Mark(3).c_str()) == SET_BAD_PATH, "a mark in the eye slot fails");
        Check(owners.Set(6, nullptr, "nope.blp") == SET_BAD_PATH, "a bad eye fails, even when clearing the mark");
        Check(Same(owners.Mark(6), Mark(3).c_str()) && !owners.Eye(6), "failed Sets leave the entry");
        Check(owners.Set(7, Mark(1).c_str(), "x") == SET_BAD_PATH && !owners.Get(7, &mark, &eye), "a failed Set makes no entry");
        Check(!SetOk(SET_BAD_PATH) && !SetOk(SET_FULL) && !SetOk(SET_FULL_NAMES) && SetOk(SET_CHANGED) && SetOk(SET_UNCHANGED), "SetOk");

        Check(owners.Clear(6) && !owners.Clear(6), "Clear says whether there was an entry");
        Check(owners.Empty(), "empty again");

        owners.Set(1, Mark(1).c_str(), nullptr);
        owners.Set(2, nullptr, Eye(1).c_str());
        owners.Set(3, Mark(2).c_str(), Eye(2).c_str());
        std::vector<uint64_t> removed;
        Check(owners.ClearAll(&removed) == 3 && removed.size() == 3 && owners.Empty(), "ClearAll removes and names every entry");
        Check(owners.ClearAll(nullptr) == 0, "ClearAll of nothing");
    }

    void TestLimits() {
        Owners owners;

        for (uint32_t i = 1; i <= kMaxEntries; i++) {
            owners.Set(i, Mark(1).c_str(), Eye(1).c_str());
        }

        Check(owners.Count() == kMaxEntries && owners.NameCount() == 2, "4096 entries share two names");
        Check(owners.Set(kMaxEntries + 1, Mark(1).c_str(), nullptr) == SET_FULL, "entry 4097 fails");
        Check(owners.Set(kMaxEntries + 1, Mark(9).c_str(), nullptr) == SET_FULL && owners.NameCount() == 2, "and interns no name");
        Check(owners.Count() == kMaxEntries && !owners.Mark(kMaxEntries + 1), "the map is unchanged");
        Check(owners.Set(7, Mark(2).c_str(), nullptr) == SET_CHANGED, "an existing entry still changes when full");
        Check(owners.Set(7, nullptr, nullptr) == SET_CHANGED && owners.Count() == kMaxEntries - 1, "clearing makes room");
        Check(owners.Set(kMaxEntries + 1, Mark(1).c_str(), nullptr) == SET_CHANGED, "then a new one fits");

        Owners names;

        for (uint32_t i = 0; i < kMaxNames / 2; i++) {
            Check(names.Set(i + 1, Mark(i).c_str(), Eye(i).c_str()) == SET_CHANGED, "names " + std::to_string(2 * i) + " and " + std::to_string(2 * i + 1));
        }

        Check(names.NameCount() == kMaxNames, "1024 names");
        const char* first = names.Mark(1);
        Check(names.Set(9000, Mark(5000).c_str(), nullptr) == SET_FULL_NAMES, "name 1025 fails");
        Check(names.Set(1, Mark(5000).c_str(), Eye(0).c_str()) == SET_FULL_NAMES, "also for an existing entry");
        Check(names.NameCount() == kMaxNames && names.Count() == kMaxNames / 2 && !names.Mark(9000), "the map and pool are unchanged");
        Check(names.Mark(1) == first && Same(names.Eye(1), Eye(0).c_str()), "entry 1 is unchanged");
        Check(names.Set(9000, Mark(3).c_str(), Eye(7).c_str()) == SET_CHANGED, "known names still go in when the pool is full");

        Owners half;

        for (uint32_t i = 0; i < kMaxNames - 1; i++) {
            half.Set(i + 1, Mark(i).c_str(), nullptr);
        }

        Check(half.NameCount() == kMaxNames - 1, "1023 names");
        Check(half.Set(9000, Mark(7000).c_str(), Eye(7000).c_str()) == SET_FULL_NAMES && half.NameCount() == kMaxNames - 1, "two new names with room for one: neither goes in");
        Check(half.Set(9000, Mark(0).c_str(), Eye(7000).c_str()) == SET_CHANGED && half.NameCount() == kMaxNames, "one new name with room for one goes in");
    }

    void TestPool() {
        Owners owners;
        owners.Set(1, Mark(1).c_str(), Eye(1).c_str());
        const char* mark = owners.Mark(1);
        const char* eye = owners.Eye(1);
        std::string markCopy = mark;

        for (uint32_t i = 2; i < 600; i++) {
            owners.Set(i, Mark(i % 400).c_str(), Eye(i % 100).c_str());
        }

        Check(owners.Mark(1) == mark && owners.Eye(1) == eye, "the names keep their pointers as the pool grows");
        owners.Clear(1);
        Check(markCopy == mark, "a cleared entry's name stays readable");
        owners.Set(1, Mark(1).c_str(), Eye(1).c_str());
        Check(owners.Mark(1) == mark && owners.Eye(1) == eye, "the same name comes back as the same pointer");
        std::vector<uint64_t> removed;
        owners.ClearAll(&removed);
        Check(markCopy == mark, "ClearAll keeps the names");
        uint32_t names = owners.NameCount();
        owners.Reset();
        Check(owners.Empty() && owners.NameCount() == names && markCopy == mark, "Reset empties the map and keeps the pool");
        owners.Set(42, Mark(1).c_str(), nullptr);
        Check(owners.Mark(42) == mark && owners.NameCount() == names, "after Reset a known name is the same pointer");

        Owners reset;
        reset.Set(1, Mark(1).c_str(), Eye(1).c_str());
        reset.BeginSync();
        reset.Reset();
        reset.Set(2, Mark(1).c_str(), nullptr);
        Check(reset.EndSync(nullptr) == 0 && reset.Count() == 1, "an entry made after Reset is not stale");
    }

    void TestSync() {
        Owners owners;
        owners.Set(1, Mark(1).c_str(), nullptr);
        owners.Set(2, Mark(2).c_str(), nullptr);
        owners.Set(3, Mark(3).c_str(), nullptr);
        owners.Set(4, Mark(4).c_str(), nullptr);
        owners.Set(5, Mark(5).c_str(), nullptr);

        std::vector<uint64_t> removed;
        Check(owners.EndSync(&removed) == 0 && removed.empty(), "EndSync without BeginSync removes nothing");

        Check(owners.BeginSync() == 5, "BeginSync counts the entries");
        Check(owners.Set(1, Mark(1).c_str(), nullptr) == SET_UNCHANGED, "an equal Set in a sync changes nothing");
        Check(owners.Set(2, Mark(9).c_str(), nullptr) == SET_CHANGED, "a different Set in a sync changes");
        Check(owners.Clear(3), "a Clear in a sync");
        Check(owners.Set(6, Mark(6).c_str(), nullptr) == SET_CHANGED, "a new entry in a sync");
        Check(owners.Set(4, "bad", nullptr) == SET_BAD_PATH, "a failed Set in a sync");
        Check(owners.EndSync(&removed) == 2, "EndSync removes the two untouched entries");
        Check(removed.size() == 2 && ((removed[0] == 4 && removed[1] == 5) || (removed[0] == 5 && removed[1] == 4)), "4 (its Set failed) and 5");
        Check(owners.Count() == 3 && owners.Mark(1) && owners.Mark(2) && owners.Mark(6) && !owners.Mark(3), "1, 2 and 6 stay");
        removed.clear();
        Check(owners.EndSync(&removed) == 0 && removed.empty(), "a second EndSync removes nothing");

        Check(owners.BeginSync() == 3 && owners.EndSync(&removed) == 3 && owners.Empty(), "an empty list removes everything");
        Check(owners.BeginSync() == 0 && owners.EndSync(nullptr) == 0, "a sync of an empty map");
    }
}

int main() {
    TestGuids();
    TestPaths();
    TestSetClearGet();
    TestLimits();
    TestPool();
    TestSync();

    printf("test_mark_owners: %d checks, %d failed\n", s_checks, s_failed);
    return s_failed ? 1 : 0;
}
