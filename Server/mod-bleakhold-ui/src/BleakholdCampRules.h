/*
 * mod-bleakhold-ui: server side of the Bleakhold UI protocol (docs/BleakholdProtocol.md).
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Camping (section 16): the rules that need no AzerothCore, so the tests can check them. The game side is
 * BleakholdCamp.cpp.
 */

#ifndef BLEAKHOLD_CAMP_RULES_H
#define BLEAKHOLD_CAMP_RULES_H

#include "BleakholdMessages.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <optional>
#include <string_view>
#include <vector>

namespace Bleakhold::CampRules
{
    inline constexpr uint32_t MaxObjectsPerFire = 3;
    inline constexpr uint8_t TierCount = 3;
    using Tiers = std::array<uint32_t, TierCount>;
    inline constexpr Tiers DefaultTierSkill = { 75, 225, 375 };

    // The tier a profession skill reaches: 1..3, or 0 below the first threshold.
    inline uint8_t TierFor(uint32_t skill, Tiers const& thresholds)
    {
        uint8_t tier = 0;
        for (uint8_t i = 0; i < TierCount; ++i)
            if (thresholds[i] && skill >= thresholds[i])
                tier = static_cast<uint8_t>(i + 1);
        return tier;
    }

    // Decimal ids from a configuration list ("22, 23", "75,225,375"): anything but a digit separates; a number over
    // 2^32 - 1 is dropped.
    inline std::vector<uint32_t> ParseIds(std::string_view s)
    {
        std::vector<uint32_t> out;
        uint64_t v = 0;
        bool in = false;
        bool tooBig = false;
        auto flush = [&]() {
            if (in && !tooBig)
                out.push_back(static_cast<uint32_t>(v));
            v = 0;
            in = false;
            tooBig = false;
        };
        for (char c : s)
        {
            if (c >= '0' && c <= '9')
            {
                v = v * 10 + static_cast<uint64_t>(c - '0');
                if (v > 0xFFFFFFFFull)
                {
                    tooBig = true;
                    v = 0xFFFFFFFFull;
                }
                in = true;
            }
            else
                flush();
        }
        flush();
        return out;
    }

    // Camp.TierSkill: exactly three thresholds, each above the one before (and above 0).
    inline std::optional<Tiers> ParseTiers(std::string_view s)
    {
        std::vector<uint32_t> const v = ParseIds(s);
        if (v.size() != TierCount || v[0] == 0 || v[1] <= v[0] || v[2] <= v[1])
            return std::nullopt;
        return Tiers{ v[0], v[1], v[2] };
    }

    // The XP bonus in percent: Campfire Warmth plus Well Fed, at most maxPct.
    inline uint32_t BonusPct(bool warm, bool fed, uint32_t warmthPct, uint32_t foodPct, uint32_t maxPct)
    {
        uint64_t const sum = (warm ? uint64_t(warmthPct) : 0) + (fed ? uint64_t(foodPct) : 0);
        return static_cast<uint32_t>(std::min<uint64_t>(sum, maxPct));
    }

    // amount + amount * pct / 100 (rounded down), saturating at 2^32 - 1.
    inline uint32_t AddPct(uint32_t amount, uint32_t pct)
    {
        uint64_t const v = uint64_t(amount) + uint64_t(amount) * pct / 100;
        return static_cast<uint32_t>(std::min<uint64_t>(v, 0xFFFFFFFFull));
    }

    // The repair cost multiplier: blacksmiths pay (100 - pct) %.
    inline float RepairCostMod(bool blacksmith, uint32_t discountPct)
    {
        if (!blacksmith)
            return 1.0f;
        return static_cast<float>(100 - std::min<uint32_t>(discountPct, 100)) / 100.0f;
    }

    // REPAIR: a blacksmith with enough skill anywhere (feature 2048), or anyone at a fire with an anvil (feature 512).
    inline bool RepairAllowed(bool fieldRepairOn, uint32_t blacksmithSkill, uint32_t minSkill, bool campOn, bool anvilAtFire)
    {
        return (fieldRepairOn && blacksmithSkill > 0 && blacksmithSkill >= minSkill) || (campOn && anvilAtFire);
    }

    // Where camp object slot 0..2 stands around a fire: on a circle of `distance` yards, 120 degrees apart, slot 0
    // beyond the fire as seen by the one who made it (they stand in front of it, on the other side), facing the fire.
    struct Offset { float x = 0, y = 0, angle = 0; };
    inline Offset SlotOffset(uint32_t slot, float fireOrientation, float distance)
    {
        float const tau = 6.28318530718f;
        float const a = fireOrientation + static_cast<float>(slot % MaxObjectsPerFire) * (tau / 3.0f);
        Offset o;
        o.x = std::cos(a) * distance;
        o.y = std::sin(a) * distance;
        o.angle = std::fmod(a + tau / 2.0f, tau);   // facing the fire
        return o;
    }

    // Seconds from `now` until `end` (both seconds), 0 once it is past.
    inline uint32_t SecondsLeft(uint64_t end, uint64_t now)
    {
        return end > now ? static_cast<uint32_t>(std::min<uint64_t>(end - now, 0xFFFFFFFFull)) : 0;
    }

    // A profession with camp objects: the game object of each tier and the buff it gives (tier 1..3).
    struct Profession
    {
        uint32_t skill = 0;          // SkillLine id
        char const* key = "";        // BleakholdUi.Camp.Profession.<key>
        Tiers objects{};             // gameobject_template entries
        Tiers buffs{};               // spell ids
    };

    // The defaults (camping-assets.md): every object is an existing script-free, trap-free game object; the buffs
    // are scrolls (tiers 1 and 2; one scroll at a time, as in the core's spell groups), Sayge's fortunes and other
    // buffs that belong to no stacking group (tier 3), and Well Fed for cooks (which also counts as Well Fed for the
    // food XP bonus, and replaces other food). Only self buffs: a party aura would reach players who never settled.
    // Spell values were not checked against Spell.dbc: change them in mod_bleakhold_ui.conf after a look in game.
    inline constexpr std::array<Profession, 14> DefaultProfessions = { {
        { 171, "Alchemy",        { 190678, 190444, 187115 }, { 8113, 12177, 23738 } },
        { 164, "Blacksmithing",  { 201893, 189626, 171715 }, { 8094, 12175, 23767 } },
        { 333, "Enchanting",     { 186746, 181361, 184723 }, { 8097, 12176, 23766 } },
        { 202, "Engineering",    { 193585, 193668, 184624 }, { 8116, 12174, 23736 } },
        { 182, "Herbalism",      { 195194, 180801, 180805 }, { 8113, 12177, 15366 } },
        { 773, "Inscription",    { 187254, 191140, 190693 }, { 8097, 12176, 23768 } },
        { 755, "Jewelcrafting",  { 188190, 184909, 188048 }, { 8119, 12179, 23735 } },
        { 165, "Leatherworking", { 188221, 176461, 188223 }, { 8100, 12178, 23737 } },
        { 186, "Mining",         { 190386, 180780, 123207 }, { 8100, 12178, 23737 } },
        { 393, "Skinning",       { 19875, 180692, 187983 },  { 8116, 12174, 22817 } },
        { 197, "Tailoring",      { 181077, 200297, 184803 }, { 8100, 12178, 22818 } },
        { 185, "Cooking",        { 181790, 3769, 186143 },   { 24870, 57288, 57399 } },
        { 129, "FirstAid",       { 181129, 180676, 178226 }, { 8094, 12175, 23769 } },
        { 356, "Fishing",        { 186614, 181143, 190226 }, { 7840, 12177, 22820 } },
    } };

    inline constexpr uint32_t SkillBlacksmithing = 164;
    inline constexpr uint8_t AnvilTier = 2;   // a blacksmithing object of this tier or higher is an anvil (REPAIR)

    // Whether a new CAMPST must go out: anything but the counting-down timers changed (a timer that starts or
    // ends counts: cooldown started, warmth started or ended, the fire went out, glide used).
    inline bool Changed(CampState const& a, CampState const& b)
    {
        auto sameObjects = [](std::vector<CampObjectInfo> const& x, std::vector<CampObjectInfo> const& y) {
            if (x.size() != y.size())
                return false;
            for (std::size_t i = 0; i < x.size(); ++i)
                if (x[i].skill != y[i].skill || x[i].tier != y[i].tier || x[i].mine != y[i].mine)
                    return false;
            return true;
        };
        auto samePlaces = [](std::vector<CampPlace> const& x, std::vector<CampPlace> const& y) {
            if (x.size() != y.size())
                return false;
            for (std::size_t i = 0; i < x.size(); ++i)
                if (x[i].skill != y[i].skill || x[i].tier != y[i].tier)
                    return false;
            return true;
        };
        auto on = [](uint32_t t) { return t > 0; };
        auto glide = [](Opt<uint32_t> const& g) { return g ? (*g > 0 ? 2 : 1) : 0; };
        return a.state != b.state || a.mine != b.mine || a.xpPct != b.xpPct || a.repair != b.repair || a.fed != b.fed ||
            on(a.fireSec) != on(b.fireSec) || on(a.cooldownSec) != on(b.cooldownSec) || on(a.warmthSec) != on(b.warmthSec) ||
            glide(a.glideSec) != glide(b.glideSec) || !sameObjects(a.objects, b.objects) || !samePlaces(a.place, b.place);
    }
}

#endif
