/*
 * mod-bleakhold-ui: server side of the Bleakhold UI protocol (docs/BleakholdProtocol.md).
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Glowing marks (section 22): the rules, without AzerothCore, so tests/cpp/bh_marks.cpp checks them on their own.
 *   - the texture path rule every builder shares (Character\BleakholdMarks\..., Character\BleakholdEyes\...)
 *   - the catalogue (bleakhold_mark_catalogue): which rows are good, which race-sexes are offered, DEF N
 *   - a character's choice: what is offered to their race, sex and class, what the server applies now
 *   - MARKSET: the checks in their order, the price (first change free, nothing at all always free), the cooldown
 *   - the lists: who is listed, how many entries a page holds at a frame size
 *   - the tables' DDL (the module SQL files hold the same text; bh_marks checks it)
 * BleakholdMarks.cpp is the core side: the configuration, the database, the hooks and the messages.
 */

#ifndef BLEAKHOLD_MARKS_RULES_H
#define BLEAKHOLD_MARKS_RULES_H

#include "BleakholdCodec.h"
#include "BleakholdMessages.h"

#include <algorithm>
#include <array>
#include <cstdint>
#include <map>
#include <set>
#include <string>
#include <string_view>
#include <tuple>
#include <vector>

namespace Bleakhold::MarksRules
{
    inline constexpr uint32_t ClassDeathKnight = 6;
    inline constexpr uint32_t FirstDeathKnightEye = 4;   // eyes 4 Blood Red and 5 Unholy Green are Death Knights' only
    inline constexpr std::size_t MaxTextureBytes = 120;  // the texture column; + "_Glow" stays under the client's 127
    inline constexpr uint32_t MaxPriceCopper = 2147483647;
    inline constexpr uint32_t MaxCooldownHours = 720;
    inline constexpr std::string_view MarkFolder = "Character\\BleakholdMarks\\";
    inline constexpr std::string_view EyeFolder = "Character\\BleakholdEyes\\";

    // =============================================================================================================
    // BleakholdUi.Marks.* (section 22), clamped
    // =============================================================================================================
    struct Settings
    {
        bool enable = false;
        bool gmOnly = true;
        uint32_t priceCopper = 100000;
        bool firstFree = true;
        uint32_t cooldownHours = 1;
        uint32_t maxListEntries = static_cast<uint32_t>(MaxMarkListEntries);
    };

    inline Settings Clamped(Settings s)
    {
        s.priceCopper = std::min(s.priceCopper, MaxPriceCopper);
        s.cooldownHours = std::min(s.cooldownHours, MaxCooldownHours);
        s.maxListEntries = std::clamp<uint32_t>(s.maxListEntries, 1, static_cast<uint32_t>(MaxMarkListEntries));
        return s;
    }

    // =============================================================================================================
    // The texture path rule (section 1 of the contract all builders share): backslashes, no leading backslash, ".blp"
    // in lower case.
    //   Character\BleakholdMarks\<RaceFile>\<Male|Female>\<DesignKey>_<ColourKey>.blp   (+ _Glow.blp beside it)
    //   Character\BleakholdEyes\<RaceFile>\<Male|Female>\Eye_<EyeKey>.blp
    // =============================================================================================================
    inline bool IsAlpha(char c) { return (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z'); }
    inline bool IsAlnum(char c) { return IsAlpha(c) || (c >= '0' && c <= '9'); }
    inline bool IsHexDigit(char c) { return (c >= '0' && c <= '9') || (c >= 'A' && c <= 'F') || (c >= 'a' && c <= 'f'); }

    // a design, colour or eye key: [A-Za-z0-9]{1,32}
    inline bool IsKey(std::string_view s)
    {
        return !s.empty() && s.size() <= MaxMarkKeyBytes && std::all_of(s.begin(), s.end(), IsAlnum);
    }

    // ChrRaces clientFileString: [A-Za-z]{1,16}
    inline bool IsRaceFile(std::string_view s)
    {
        return !s.empty() && s.size() <= MaxMarkRaceFileBytes && std::all_of(s.begin(), s.end(), IsAlpha);
    }

    inline bool IsHex6(std::string_view s) { return s.size() == 6 && std::all_of(s.begin(), s.end(), IsHexDigit); }

    // a name: 1..48 bytes of valid UTF-8 without NUL (the client shows it as it is)
    inline bool IsName(std::string_view s)
    {
        return !s.empty() && s.size() <= MaxMarkNameBytes && Proto::CleanText(s) == s;
    }

    inline std::string_view SexFolder(uint32_t sex) { return sex == 0 ? "Male" : "Female"; }

    inline std::string MarkTexture(std::string_view raceFile, uint32_t sex, std::string_view designKey,
        std::string_view colourKey)
    {
        std::string out(MarkFolder);
        out.append(raceFile).append("\\").append(SexFolder(sex)).append("\\").append(designKey).append("_")
            .append(colourKey).append(".blp");
        return out;
    }

    inline std::string EyeTexture(std::string_view raceFile, uint32_t sex, std::string_view eyeKey)
    {
        std::string out(EyeFolder);
        out.append(raceFile).append("\\").append(SexFolder(sex)).append("\\Eye_").append(eyeKey).append(".blp");
        return out;
    }

    // =============================================================================================================
    // The catalogue: the rows of bleakhold_mark_catalogue (deploy/marks/build-marks.sh writes them from MarkForge's
    // manifest). A row that breaks a rule is dropped (and logged). A race-sex is offered only with all 12 looks
    // (4 designs x 3 colours) good, one key and name per design and per colour across its rows; its eye sprites are
    // offered one by one.
    // =============================================================================================================
    struct CatalogueRow
    {
        uint32_t race = 0, sex = 0;
        char kind = 'M';                     // M a mark look, E an eye sprite
        uint32_t design = 0;                 // M: 1-4; E: 0
        uint32_t colour = 0;                 // M: 1-3; E: the eye, 1-5
        std::string raceFile;
        std::string designKey, designName;   // M only
        std::string colourKey, colourName;   // M: the colour; E: the eye
        std::string hex;                     // RRGGBB
        uint32_t glow = 0;                   // M: 1 when the colour has _Glow files
        uint32_t dkOnly = 0;                 // E: 1 for eyes 4 and 5
        std::string texture;
    };

    // Why a row is not good on its own (empty when it is).
    inline std::string RowProblem(CatalogueRow const& r)
    {
        if (r.race < 1 || r.race > 255)
            return "race outside 1-255";
        if (r.sex > 1)
            return "sex is not 0 or 1";
        if (!IsRaceFile(r.raceFile))
            return "race_file is not [A-Za-z]{1,16}";
        if (!IsKey(r.colourKey))
            return "colour_key is not [A-Za-z0-9]{1,32}";
        if (!IsName(r.colourName))
            return "colour_name is empty, longer than 48 bytes or not UTF-8";
        if (!IsHex6(r.hex))
            return "hex is not 6 hex digits";
        if (r.texture.size() > MaxTextureBytes)
            return "texture longer than 120 bytes";
        if (r.kind == 'M')
        {
            if (r.design < 1 || r.design > MaxMarkDesign)
                return "a mark's design outside 1-4";
            if (r.colour < 1 || r.colour > MaxMarkColour)
                return "a mark's colour outside 1-3";
            if (!IsKey(r.designKey))
                return "design_key is not [A-Za-z0-9]{1,32}";
            if (!IsName(r.designName))
                return "design_name is empty, longer than 48 bytes or not UTF-8";
            if (r.glow > 1)
                return "glow is not 0 or 1";
            if (r.dkOnly != 0)
                return "a mark with dk_only";
            if (r.texture != MarkTexture(r.raceFile, r.sex, r.designKey, r.colourKey))
                return "texture is not " + MarkTexture(r.raceFile, r.sex, r.designKey, r.colourKey);
            return std::string();
        }
        if (r.kind == 'E')
        {
            if (r.design != 0)
                return "an eye's design is not 0";
            if (r.colour < 1 || r.colour > MaxMarkEye)
                return "an eye outside 1-5";
            if (r.dkOnly != (r.colour >= FirstDeathKnightEye ? 1u : 0u))
                return "dk_only is not 1 exactly for eyes 4 and 5";
            if (r.texture != EyeTexture(r.raceFile, r.sex, r.colourKey))
                return "texture is not " + EyeTexture(r.raceFile, r.sex, r.colourKey);
            return std::string();
        }
        return "kind is not M or E";
    }

    inline uint32_t RaceSexId(uint32_t race, uint32_t sex) { return race * 2 + sex; }

    struct RaceSex
    {
        uint32_t race = 0, sex = 0;
        std::string raceFile;
        bool offered = false;
        std::array<MarkDesignDef, MaxMarkDesign> designs{};
        std::array<MarkColourDef, MaxMarkColour> colours{};
        std::array<bool, MaxMarkEye> eyeOffered{};
        std::array<MarkEyeDef, MaxMarkEye> eyes{};
    };

    struct Catalogue
    {
        std::map<uint32_t, RaceSex> races;   // by RaceSexId; only offered ones
        std::vector<std::string> problems;   // one line per dropped row or race-sex, for the log
        std::size_t rows = 0;                // rows read
        std::size_t goodRows = 0;            // rows used

        RaceSex const* Find(uint32_t race, uint32_t sex) const
        {
            auto it = races.find(RaceSexId(race, sex));
            return it == races.end() ? nullptr : &it->second;
        }
        std::size_t Offered() const { return races.size(); }
        bool operator==(Catalogue const& o) const;
    };

    inline std::string RowName(CatalogueRow const& r)
    {
        return "race " + std::to_string(r.race) + " sex " + std::to_string(r.sex) + " " + std::string(1, r.kind) + " " +
            std::to_string(r.design) + "/" + std::to_string(r.colour);
    }

    inline Catalogue BuildCatalogue(std::vector<CatalogueRow> const& rows)
    {
        Catalogue cat;
        cat.rows = rows.size();
        // the good rows by race-sex, one per (kind, design, colour)
        std::map<uint32_t, std::map<std::tuple<char, uint32_t, uint32_t>, CatalogueRow const*>> byRace;
        for (CatalogueRow const& r : rows)
        {
            std::string const why = RowProblem(r);
            if (!why.empty())
            {
                cat.problems.push_back(RowName(r) + ": " + why);
                continue;
            }
            auto& slot = byRace[RaceSexId(r.race, r.sex)][{ r.kind, r.design, r.colour }];
            if (slot)
            {
                cat.problems.push_back(RowName(r) + ": a second row of the same look");
                continue;
            }
            slot = &r;
        }
        for (auto const& [id, looks] : byRace)
        {
            CatalogueRow const& any = *looks.begin()->second;
            RaceSex rs;
            rs.race = any.race;
            rs.sex = any.sex;
            std::string why;
            // every look, the designs' and colours' keys and names alike across their rows, one race_file
            CatalogueRow const* first = nullptr;
            for (uint32_t d = 1; d <= MaxMarkDesign && why.empty(); ++d)
                for (uint32_t c = 1; c <= MaxMarkColour && why.empty(); ++c)
                {
                    auto it = looks.find({ 'M', d, c });
                    if (it == looks.end())
                    {
                        why = "no look for design " + std::to_string(d) + " colour " + std::to_string(c);
                        break;
                    }
                    CatalogueRow const& r = *it->second;
                    if (!first)
                        first = &r;
                    MarkDesignDef& dd = rs.designs[d - 1];
                    MarkColourDef& cd = rs.colours[c - 1];
                    if (c == 1)
                        dd = MarkDesignDef{ d, r.designKey, r.designName };
                    else if (dd.key != r.designKey || dd.name != r.designName)
                        why = "design " + std::to_string(d) + " has two keys or names";
                    if (d == 1)
                        cd = MarkColourDef{ c, r.colourKey, r.colourName, r.hex, r.glow == 1 };
                    else if (cd.key != r.colourKey || cd.name != r.colourName || cd.hex != r.hex || cd.glow != (r.glow == 1))
                        why = "colour " + std::to_string(c) + " has two keys, names, hex or glow";
                    if (r.raceFile != first->raceFile)
                        why = "two race_file values";
                }
            if (why.empty())
            {
                std::set<std::string> keys;
                for (MarkDesignDef const& dd : rs.designs)
                    keys.insert(dd.key);
                if (keys.size() != MaxMarkDesign)
                    why = "two designs share a key";
                keys.clear();
                for (MarkColourDef const& cd : rs.colours)
                    keys.insert(cd.key);
                if (why.empty() && keys.size() != MaxMarkColour)
                    why = "two colours share a key";
            }
            if (!why.empty())
            {
                cat.problems.push_back("race " + std::to_string(rs.race) + " sex " + std::to_string(rs.sex) +
                    " is not offered: " + why);
                continue;
            }
            rs.raceFile = first->raceFile;
            rs.offered = true;
            cat.goodRows += MaxMarkDesign * MaxMarkColour;
            std::set<std::string> eyeKeys;
            for (uint32_t e = 1; e <= MaxMarkEye; ++e)
            {
                auto it = looks.find({ 'E', 0, e });
                if (it == looks.end())
                    continue;
                CatalogueRow const& r = *it->second;
                if (r.raceFile != rs.raceFile || !eyeKeys.insert(r.colourKey).second)
                {
                    cat.problems.push_back(RowName(r) + ": " +
                        (r.raceFile != rs.raceFile ? "another race_file than the marks'" : "a key another eye has"));
                    continue;
                }
                rs.eyeOffered[e - 1] = true;
                rs.eyes[e - 1] = MarkEyeDef{ e, r.colourKey, r.colourName, r.hex, r.dkOnly == 1 };
                ++cat.goodRows;
            }
            cat.races[id] = rs;
        }
        return cat;
    }

    inline bool Catalogue::operator==(Catalogue const& o) const
    {
        if (races.size() != o.races.size())
            return false;
        for (auto const& [id, a] : races)
        {
            auto it = o.races.find(id);
            if (it == o.races.end())
                return false;
            RaceSex const& b = it->second;
            if (a.raceFile != b.raceFile || a.eyeOffered != b.eyeOffered)
                return false;
            for (std::size_t i = 0; i < MaxMarkDesign; ++i)
                if (a.designs[i].key != b.designs[i].key || a.designs[i].name != b.designs[i].name)
                    return false;
            for (std::size_t i = 0; i < MaxMarkColour; ++i)
                if (a.colours[i].key != b.colours[i].key || a.colours[i].name != b.colours[i].name ||
                    a.colours[i].hex != b.colours[i].hex || a.colours[i].glow != b.colours[i].glow)
                    return false;
            for (std::size_t i = 0; i < MaxMarkEye; ++i)
                if (a.eyeOffered[i] && (a.eyes[i].key != b.eyes[i].key || a.eyes[i].name != b.eyes[i].name ||
                    a.eyes[i].hex != b.eyes[i].hex))
                    return false;
        }
        return true;
    }

    // DEF N: one record per offered race-sex, in id order.
    inline void FillDefinitions(Catalogue const& cat, Definitions& defs)
    {
        for (auto const& [id, rs] : cat.races)
        {
            MarkRaceDef d;
            d.raceId = rs.race;
            d.sex = rs.sex;
            d.raceFile = rs.raceFile;
            d.designs.assign(rs.designs.begin(), rs.designs.end());
            d.colours.assign(rs.colours.begin(), rs.colours.end());
            for (std::size_t i = 0; i < MaxMarkEye; ++i)
                if (rs.eyeOffered[i])
                    d.eyes.push_back(rs.eyes[i]);
            defs.markRaces.push_back(std::move(d));
        }
    }

    // =============================================================================================================
    // A character's choice
    // =============================================================================================================
    struct Choice
    {
        uint8_t design = 0, colour = 0, eye = 0;
        bool None() const { return design == 0 && colour == 0 && eye == 0; }
        bool operator==(Choice const& o) const { return design == o.design && colour == o.colour && eye == o.eye; }
        bool operator!=(Choice const& o) const { return !(*this == o); }
    };

    // A full look (design and colour) of an offered race-sex; design 0 colour 0 (no mark) is always offered.
    inline bool LookOffered(Catalogue const& cat, uint32_t race, uint32_t sex, uint32_t design, uint32_t colour)
    {
        if (design == 0 && colour == 0)
            return true;
        if (design < 1 || design > MaxMarkDesign || colour < 1 || colour > MaxMarkColour)
            return false;
        return cat.Find(race, sex) != nullptr;
    }

    // An eye sprite that exists for the race-sex, 4 and 5 for Death Knights only; eye 0 (the race's own) always.
    inline bool EyeOffered(Catalogue const& cat, uint32_t race, uint32_t sex, uint32_t classId, uint32_t eye)
    {
        if (eye == 0)
            return true;
        if (eye > MaxMarkEye || (eye >= FirstDeathKnightEye && classId != ClassDeathKnight))
            return false;
        RaceSex const* rs = cat.Find(race, sex);
        return rs && rs->eyeOffered[eye - 1];
    }

    inline bool Offered(Catalogue const& cat, uint32_t race, uint32_t sex, uint32_t classId, Choice const& c)
    {
        return LookOffered(cat, race, sex, c.design, c.colour) && EyeOffered(cat, race, sex, classId, c.eye);
    }

    // The stored choice as the server applies it now: a layer the catalogue no longer offers for the character's race,
    // sex and class reads as 0 (the row keeps it).
    inline Choice Applied(Catalogue const& cat, uint32_t race, uint32_t sex, uint32_t classId, Choice const& stored)
    {
        Choice out;
        if (stored.design != 0 && LookOffered(cat, race, sex, stored.design, stored.colour))
        {
            out.design = stored.design;
            out.colour = stored.colour;
        }
        if (EyeOffered(cat, race, sex, classId, stored.eye))
            out.eye = stored.eye;
        return out;
    }

    // =============================================================================================================
    // Price and cooldown
    // =============================================================================================================
    // What a change to a mark or eye costs now (MARKME): 0 while the next change is free (FirstFree and no change yet,
    // or Price 0).
    inline uint32_t PriceNow(Settings const& s, uint32_t changes)
    {
        return s.firstFree && changes == 0 ? 0 : s.priceCopper;
    }

    // What this change costs: a change to nothing at all (0,0,0) is always free.
    inline uint32_t PriceFor(Settings const& s, uint32_t changes, Choice const& wanted)
    {
        return wanted.None() ? 0 : PriceNow(s, changes);
    }

    // Seconds until the next change is allowed (0 = now). changedAt 0: never changed.
    inline uint32_t CooldownLeft(Settings const& s, uint32_t changedAt, uint32_t now)
    {
        if (!s.cooldownHours || !changedAt)
            return 0;
        uint64_t const length = uint64_t(s.cooldownHours) * 3600;
        uint64_t const end = uint64_t(changedAt) + length;
        if (now >= end)
            return 0;
        // a clock that went back never makes the wait longer than one cooldown
        return static_cast<uint32_t>(std::min<uint64_t>(end - now, length));
    }

    // The sentence of marks_cooldown: the minutes left (rounded up), or the hours from two hours on.
    inline std::string CooldownText(uint32_t seconds)
    {
        uint32_t const minutes = std::max<uint32_t>(1, (seconds + 59) / 60);
        if (minutes > 120)
            return "You can change your markings again in " + std::to_string((minutes + 59) / 60) + " hours.";
        return "You can change your markings again in " + std::to_string(minutes) + (minutes == 1 ? " minute." : " minutes.");
    }

    // =============================================================================================================
    // MARKSET: the checks after the parser, the rate and the duplicate guard, in this order (section 22)
    // =============================================================================================================
    enum class Verdict : uint8_t { Ok, Off, Dead, Combat, Unknown, Same, Cooldown, Price, Gold };

    struct SetInput
    {
        bool feature = false;                // feature bit 262144 for the player
        bool alive = true;
        bool inCombat = false;
        uint32_t race = 0, sex = 0, classId = 0;
        Choice stored;                       // the row (applied with the catalogue here)
        Choice wanted;
        uint32_t changes = 0, changedAt = 0;
        uint32_t maxCopper = 0;
        uint64_t money = 0;
        uint32_t now = 0;
    };

    struct SetResult
    {
        Verdict verdict = Verdict::Ok;
        uint32_t price = 0;                  // what the change costs (Ok, Price, Gold)
        uint32_t cooldownSec = 0;            // Cooldown: the seconds left
    };

    inline SetResult CheckSet(Catalogue const& cat, Settings const& s, SetInput const& in)
    {
        SetResult r;
        auto verdict = [&](Verdict v) { r.verdict = v; return r; };
        if (!in.feature)
            return verdict(Verdict::Off);
        if (!in.alive)
            return verdict(Verdict::Dead);
        if (in.inCombat)
            return verdict(Verdict::Combat);
        if (!Offered(cat, in.race, in.sex, in.classId, in.wanted))
            return verdict(Verdict::Unknown);
        if (in.wanted == Applied(cat, in.race, in.sex, in.classId, in.stored))
            return verdict(Verdict::Same);
        r.cooldownSec = CooldownLeft(s, in.changedAt, in.now);
        if (r.cooldownSec)
            return verdict(Verdict::Cooldown);
        r.price = PriceFor(s, in.changes, in.wanted);
        if (r.price > in.maxCopper)
            return verdict(Verdict::Price);
        if (in.money < r.price)
            return verdict(Verdict::Gold);
        return r;
    }

    // The ERR of a refusal (Ok has none: an empty code).
    inline Refusal RefusalOf(Verdict v)
    {
        switch (v)
        {
            case Verdict::Off: return MarksErr::Off;
            case Verdict::Dead: return MarksErr::Dead;
            case Verdict::Combat: return MarksErr::Combat;
            case Verdict::Unknown: return MarksErr::Unknown;
            case Verdict::Same: return MarksErr::Same;
            case Verdict::Cooldown: return MarksErr::Cooldown;
            case Verdict::Price: return MarksErr::Price;
            case Verdict::Gold: return MarksErr::Gold;
            default: return Refusal{ "", "" };
        }
    }

    // MARKME follows these refusals, so the window shows the current price and cooldown.
    inline bool MarkMeFollows(Verdict v) { return v == Verdict::Cooldown || v == Verdict::Price; }

    // An accepted change: the row's counters (paid_total saturates).
    struct Stored
    {
        Choice choice;
        uint32_t changes = 0, changedAt = 0, paidTotal = 0;
    };

    inline Stored Accept(Stored s, Choice const& wanted, uint32_t price, uint32_t now)
    {
        s.choice = wanted;
        s.changes = s.changes == UINT32_MAX ? s.changes : s.changes + 1;
        s.changedAt = now ? now : 1;
        s.paidTotal = static_cast<uint32_t>(std::min<uint64_t>(uint64_t(s.paidTotal) + price, UINT32_MAX));
        return s;
    }

    // =============================================================================================================
    // Lists
    // =============================================================================================================
    // A player's list entry (race, sex and the applied choice); listed only while the owner has the feature bit (under
    // GmOnly only game masters) and has a mark or an eye.
    inline MarkEntry EntryOf(uint32_t guid, uint32_t race, uint32_t sex, Choice const& applied)
    {
        MarkEntry e;
        e.guid = guid;
        e.race = static_cast<uint8_t>(std::min<uint32_t>(race, 255));
        e.sex = static_cast<uint8_t>(sex ? 1 : 0);
        e.design = applied.design;
        e.colour = applied.colour;
        e.eye = applied.eye;
        return e;
    }

    inline bool Listed(bool ownerFeature, MarkEntry const& e)
    {
        return ownerFeature && MarkEntryValid(e) && !MarkEntryNone(e);
    }

    // MARKS entries per page at a frame size (BleakholdUi.Frame.MaxBody): a page is one message, at most 99 frames,
    // and BuildFrames fills every frame at least half (it cuts after a ';' in the second half of the room).
    inline std::size_t PageRecordsFor(std::size_t maxBody)
    {
        constexpr std::size_t Header = 2 + 5 + 1 + 6 + 1 + 5 + 1;   // "1 MARKS zzzzzz 99/99 "
        constexpr std::size_t HeaderRecord = 20;                     // "2147483647,5,5,2000;"
        constexpr std::size_t Record = 23;                           // "4294967295,255,1,4,3,5;"
        maxBody = std::min(maxBody, Proto::MaxServerBody);
        if (maxBody <= Header + 8)
            return 1;
        std::size_t const fits = (Proto::MaxParts * ((maxBody - Header) / 2) - HeaderRecord) / Record;
        return std::clamp<std::size_t>(fits, 1, MaxMarkPageRecords);
    }

    // =============================================================================================================
    // The tables: the text of data/sql/db-characters/02_bleakhold_marks_characters.sql and
    // data/sql/db-world/05_bleakhold_marks_catalogue.sql (deploy/marks/marks_catalogue.py writes the world one too),
    // run again at startup (CREATE TABLE IF NOT EXISTS); bh_marks checks the files hold these statements.
    // =============================================================================================================
    inline constexpr std::array<std::string_view, 1> CharacterTablesSql = { {
        "CREATE TABLE IF NOT EXISTS `bleakhold_marks` (\n"
        "  `guid` INT UNSIGNED NOT NULL,\n"
        "  `design` TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '0 none, 1-4',\n"
        "  `colour` TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '0 none, 1-3',\n"
        "  `eye` TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '0 the race''s own, 1-5',\n"
        "  `changes` INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'accepted MARKSET changes (FirstFree: the first is free)',\n"
        "  `changed_at` INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'unix time of the last change (CooldownHours)',\n"
        "  `paid_total` INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'copper paid for changes, all told',\n"
        "  PRIMARY KEY (`guid`)\n"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci",
    } };

    inline constexpr std::array<std::string_view, 1> WorldTablesSql = { {
        "CREATE TABLE IF NOT EXISTS `bleakhold_mark_catalogue` (\n"
        "  `race` TINYINT UNSIGNED NOT NULL, `sex` TINYINT UNSIGNED NOT NULL,\n"
        "  `kind` CHAR(1) NOT NULL COMMENT 'M a mark look, E an eye sprite',\n"
        "  `design` TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'M: 1-4; E: 0',\n"
        "  `colour` TINYINT UNSIGNED NOT NULL COMMENT 'M: 1-3; E: the eye, 1-5',\n"
        "  `race_file` VARCHAR(16) NOT NULL,\n"
        "  `design_key` VARCHAR(32) NOT NULL DEFAULT '', `design_name` VARCHAR(48) NOT NULL DEFAULT '',\n"
        "  `colour_key` VARCHAR(32) NOT NULL, `colour_name` VARCHAR(48) NOT NULL,\n"
        "  `hex` CHAR(6) NOT NULL, `glow` TINYINT UNSIGNED NOT NULL DEFAULT 0, `dk_only` TINYINT UNSIGNED NOT NULL DEFAULT 0,\n"
        "  `texture` VARCHAR(120) NOT NULL, `sha1` CHAR(40) NOT NULL DEFAULT '',\n"
        "  `build` VARCHAR(40) NOT NULL DEFAULT '' COMMENT 'the build-marks.sh build id (the manifest sha1)',\n"
        "  PRIMARY KEY (`race`, `sex`, `kind`, `design`, `colour`)\n"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci",
    } };
}

#endif
