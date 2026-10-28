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
#include <string>
#include <string_view>
#include <utility>
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

    // What a repair cost: the money that went (Player::DurabilityRepairAll returns the cost only when a guild bank
    // pays, and 0 when the player pays).
    inline uint32_t MoneySpent(uint32_t before, uint32_t after)
    {
        return before > after ? before - after : 0;
    }

    // Copper as the toasts write it: "1g 2s 3c", "2s 0c", "0c".
    inline std::string MoneyText(uint32_t copper)
    {
        std::string out;
        if (copper >= 10000)
            out += std::to_string(copper / 10000) + "g ";
        if (copper >= 100)
            out += std::to_string(copper / 100 % 100) + "s ";
        out += std::to_string(copper % 100) + "c";
        return out;
    }

    // Camp rest uses the core's REST_FLAG_IN_FACTION_AREA bit (BleakholdCamp.h). The camp sets it only when taking it
    // off again cannot end anyone else's rest: the core clears PLAYER_FLAGS_RESTING when the last rest bit goes, and a
    // player who rests with no rest bit at all got that rest from Player::SetRestState (mod-guildhouse in a guild
    // house). Such a player already rests, so the camp leaves the rest alone; leaving the fire, combat and logout then
    // have no camp bit to take off. With an inn or city bit set, the camp's bit is safe: that bit keeps the rest.
    inline bool MaySetCampRestBit(bool resting, bool anyRestBit)
    {
        return !resting || anyRestBit;
    }

    // The spell foci a camp object or camp fire may carry (BleakholdUi.Camp.AllowedFocusIds): the common stations
    // found in every town or lit by anyone, anvil (1), forge (3) and cooking fire (4). Every other focus belongs to a
    // station tied to a place (Alchemy Lab 663, Mana Loom 1426, a moonwell, the Death Knight runeforge, ...), which a
    // camp object would carry into the field; such a template is refused. A focus of 0 is no station at all.
    inline constexpr std::string_view DefaultAllowedFocusIds = "1,3,4";
    inline bool FocusAllowed(uint32_t focusId, std::vector<uint32_t> const& allowed)
    {
        return focusId == 0 || std::find(allowed.begin(), allowed.end(), focusId) != allowed.end();
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

    // One effect of a spell the camp would cast on a player (BleakholdCamp.cpp reads it from SpellInfo).
    struct BuffEffect
    {
        bool present = false;         // the effect slot is used
        bool changesXp = false;       // an XP aura (MOD_XP_PCT, MOD_XP_QUEST_PCT)
        bool areaAura = false;        // APPLY_AREA_AURA_*
        bool reachesOthers = false;   // an area or cone target, or more than one chain target
        bool positive = false;        // SpellInfo::IsPositiveEffect
        bool inertTrigger = false;    // TRIGGER_SPELL of an inert marker (unscripted, unlinked, dummy auras only)
    };
    using BuffEffects = std::array<BuffEffect, 3>;

    enum class BuffProblem : uint8_t { None, ChangesXp, AreaAura, ReachesOthers, NotBuff };

    // Whether the camp may cast a spell on a player: it raises no XP itself (the module's bonus would come on top of
    // the core's), reaches nobody else (players who never settled) and every effect is positive. SpellInfo::IsPositive
    // is not the test: the core marks an effect negative when it triggers a negative spell, even one it never casts,
    // and every Sayge's Dark Fortune (23735-23738, 23766-23769) triggers the server-only marker 23770 "Sayge's Carnie
    // Buff" (a dummy aura with SPELL_ATTR0_AURA_IS_DEBUFF, skipped by Spell::EffectTriggerSpell). A trigger of such
    // an inert marker cannot harm the player, so it does not make the spell a debuff.
    inline BuffProblem CheckBuff(BuffEffects const& effects)
    {
        for (BuffEffect const& e : effects)
            if (e.present && e.changesXp)
                return BuffProblem::ChangesXp;
        for (BuffEffect const& e : effects)
            if (e.present && e.areaAura)
                return BuffProblem::AreaAura;
        for (BuffEffect const& e : effects)
            if (e.present && e.reachesOthers)
                return BuffProblem::ReachesOthers;
        bool any = false;   // at least one effect that does the player good
        for (BuffEffect const& e : effects)
        {
            if (!e.present)
                continue;
            if (!e.positive && !e.inertTrigger)
                return BuffProblem::NotBuff;
            any = any || e.positive;
        }
        return any ? BuffProblem::None : BuffProblem::NotBuff;
    }

    inline char const* BuffProblemText(BuffProblem p)
    {
        switch (p)
        {
            case BuffProblem::None: return "";
            case BuffProblem::ChangesXp: return "changes XP (the camping bonus would be added twice)";
            case BuffProblem::AreaAura: return "is an area aura (it would reach players who never settled)";
            case BuffProblem::ReachesOthers:
                return "has an area or chain target (it would reach players who never settled)";
            case BuffProblem::NotBuff: return "is not a buff";
        }
        return "is not a buff";
    }

    // A profession with camp objects: the game object of each tier and the buff it gives (tier 1..3).
    struct Profession
    {
        uint32_t skill = 0;          // SkillLine id
        char const* key = "";        // BleakholdUi.Camp.Profession.<key>
        Tiers objects{};             // gameobject_template entries
        Tiers buffs{};               // spell ids
    };

    // The defaults (camping-assets.md): every object is an existing script-free, trap-free game object, and no
    // crafting station tied to a place (FocusAllowed: the tier 3 Alchemy object is the Apothecary Table 190689, the
    // Alchemy Lab's look without its focus, and the Tailoring one the Armor Stand 188216 instead of the Mana Loom);
    // the buffs are scrolls (tiers 1 and 2; one scroll at a time, as in the core's spell groups), Sayge's fortunes and
    // other buffs that belong to no stacking group (tier 3), and Well Fed for cooks (which also counts as Well Fed for
    // the food XP bonus, and replaces other food). Only self buffs: a party aura would reach players who never
    // settled. Every buff passes CheckBuff (checked against Spell.dbc 3.3.5a: single-target auras, no area target, no
    // chain; the fortunes' only non-positive effect is the inert trigger of 23770). Spell values: change them in
    // mod_bleakhold_ui.conf after a look in game.
    inline constexpr std::array<Profession, 14> DefaultProfessions = { {
        { 171, "Alchemy",        { 190678, 190444, 190689 }, { 8113, 12177, 23738 } },
        { 164, "Blacksmithing",  { 201893, 189626, 171715 }, { 8094, 12175, 23767 } },
        { 333, "Enchanting",     { 186746, 181361, 184723 }, { 8097, 12176, 23766 } },
        { 202, "Engineering",    { 193585, 193668, 184624 }, { 8116, 12174, 23736 } },
        { 182, "Herbalism",      { 195194, 180801, 180805 }, { 8113, 12177, 15366 } },
        { 773, "Inscription",    { 187254, 191140, 190693 }, { 8097, 12176, 23768 } },
        { 755, "Jewelcrafting",  { 188190, 184909, 188048 }, { 8119, 12179, 23735 } },
        { 165, "Leatherworking", { 188221, 176461, 188223 }, { 8100, 12178, 23737 } },
        { 186, "Mining",         { 190386, 180780, 123207 }, { 8100, 12178, 23737 } },
        { 393, "Skinning",       { 19875, 180692, 187983 },  { 8116, 12174, 22817 } },
        { 197, "Tailoring",      { 181077, 200297, 188216 }, { 8100, 12178, 22818 } },
        { 185, "Cooking",        { 181790, 3769, 186143 },   { 24870, 57288, 57399 } },
        { 129, "FirstAid",       { 181129, 180676, 178226 }, { 8094, 12175, 23769 } },
        { 356, "Fishing",        { 186614, 181143, 190226 }, { 7840, 12177, 22820 } },
    } };

    inline constexpr uint32_t SkillBlacksmithing = 164;
    inline constexpr uint8_t AnvilTier = 2;   // a blacksmithing object of this tier or higher is an anvil (REPAIR)

    // ---- the High Elf glide, Walk on Air (GLIDE) ----
    //
    // The 3.3.5a client gives a falling player no air control: CMovementShared::StartMove, CalcDirection and
    // SetFacing keep the direction and speed a fall started with (WoW/Source/Object/MovementShared.cpp), and a feather
    // fall aura (MOVEMENTFLAG_SAFE_FALL) only caps the descent at s_safeFallTerminalVelocity. So the glide is the
    // feather fall aura plus a server push: SMSG_MOVE_KNOCK_BACK (Unit::KnockbackFrom), which the client turns into a
    // new fall (CMovement_C::Launch -> StartFalling(verticalSpeed)) with the given horizontal direction and speed, even
    // when it arrives after a landing. The push is sent again when the player turns (the client reports its facing
    // while falling), which is the steering.
    inline constexpr uint32_t WalkOnAirSpell = 100800;   // the Bleakhold spell (spell_dbc row, client Spell.dbc row)
    inline constexpr uint32_t SlowFallSpell = 130;       // the fallback when the realm lacks Walk on Air
    inline constexpr float SafeFallTerminal = 7.0f;      // yd/s, CMovementShared::s_safeFallTerminalVelocity
    inline constexpr float FallGravity = 19.291105f;     // yd/s^2, the client's fall acceleration
    inline constexpr float GlideMinHeight = 2.5f;        // yd above the ground: a fall that becomes a glide
    inline constexpr float GlideSteerAngle = 0.0873f;    // rad (5 degrees): a turn that re-aims the glide
    inline constexpr uint64_t GlideSteerGapMs = 200;     // at most five steering pushes a second
    inline constexpr uint32_t GlideMaxPushes = 64;       // pushes per glide (a hard cap; 10 s of steering needs ~50)
    inline constexpr float GlideMaxForwardSpeed = 30.0f; // BleakholdUi.Glide.ForwardSpeed is clamped to 0..this
    inline constexpr uint64_t GlideAckWaitMs = 1500;     // a landing waits this long for the ack of a push on its way

    // The descent speed of a feather-falling client (CMovementShared::GetFeatherFallVelocity): the fall's start
    // velocity (positive = down) plus gravity over the fall time, capped at the safe-fall terminal velocity, and never
    // upward (a jump's rising part counts as 0).
    inline float FeatherFallSpeed(float zspeed, uint32_t fallTimeMs)
    {
        if (!std::isfinite(zspeed))
            return SafeFallTerminal;
        float v = std::min(zspeed, SafeFallTerminal) + FallGravity * static_cast<float>(fallTimeMs) / 1000.0f;
        return std::clamp(v, 0.0f, SafeFallTerminal);
    }

    // The smallest angle between two facings, 0..pi.
    inline float AngleBetween(float a, float b)
    {
        float const tau = 6.28318530718f;
        if (!std::isfinite(a) || !std::isfinite(b))
            return 0.0f;
        float d = std::fmod(std::fabs(a - b), tau);
        return d > tau / 2.0f ? tau - d : d;
    }

    // Unit::KnockbackFrom pushes away from a point: the point one yard behind the player pushes them along `facing`.
    struct Point2 { float x = 0, y = 0; };
    inline Point2 PushOrigin(float x, float y, float facing)
    {
        return { x - std::cos(facing), y - std::sin(facing) };
    }

    // The maps without the glide: a battleground or an arena (the Royale map included) always; a dungeon or a raid
    // (Map::IsDungeon) unless BleakholdUi.Glide.Instances, since the steerable push skips jump shortcuts (Mythic+
    // routes and timers) and undoes drop-off mechanics (knockbacks off a platform, the Lich King's edge), which Slow
    // Fall, with no forward control, never could. GLIDE there is refused (glide_here), and a glide carried in (a
    // teleport, a summon, an instance portal) ends on arrival with its aura.
    inline bool NoGlideMap(bool pvpMap, bool instanceMap, bool instancesOn)
    {
        return pvpMap || (instanceMap && !instancesOn);
    }

    // GLIDE refusals, checked in this order (BleakholdCamp.cpp fills the facts; section 16 lists the codes).
    struct GlideFacts
    {
        bool raceOk = false;       // the real race is in BleakholdUi.Glide.Races
        bool noGlideMap = false;   // NoGlideMap: a battleground or an arena, or a dungeon or a raid (Instances off)
        bool alive = false;
        bool mounted = false;      // mounted, on a vehicle or on a flight path
        bool flying = false;       // flying, or able to fly (a flight form or a flying mount's aura)
        bool inWater = false;      // swimming or standing in water
        bool held = false;         // rooted, stunned, feared, confused, charmed or controlling another unit
        bool inAir = false;        // falling or jumping
        bool requireFalling = false;
        uint32_t cooldownLeft = 0; // seconds
    };
    enum class GlideRefusal : uint8_t { None, Race, Here, Dead, Mounted, Flying, Water, Held, Ground, Cooldown };
    inline GlideRefusal CheckGlide(GlideFacts const& f)
    {
        if (!f.raceOk)
            return GlideRefusal::Race;
        if (f.noGlideMap)
            return GlideRefusal::Here;
        if (!f.alive)
            return GlideRefusal::Dead;
        if (f.mounted)
            return GlideRefusal::Mounted;
        if (f.flying)
            return GlideRefusal::Flying;
        if (f.inWater)
            return GlideRefusal::Water;
        if (f.held)
            return GlideRefusal::Held;
        if (f.requireFalling && !f.inAir)
            return GlideRefusal::Ground;
        if (f.cooldownLeft > 0)
            return GlideRefusal::Cooldown;
        return GlideRefusal::None;
    }

    // ---- Walk on Air in the spellbook (BleakholdUi.Glide.CastSpell) ----
    //
    // The racial a High Elf casts from the spellbook or an action bar: the module teaches it to the races that can
    // glide (at login), and its spell script runs GLIDE's checks on the cast, in the air only, and starts the same
    // glide on the hit. A refused cast fails with one of the client's own cast results (it words them itself and
    // starts no cooldown); the glide's cooldown is the module's either way, shared with GLIDE, and shown on the
    // spell.
    inline constexpr uint32_t WalkOnAirCastSpell = 100801;

    // SpellCastResult values of 3.3.5a (AzerothCore's SharedDefines.h, the client's Magic/Types.h): the ones a refused
    // glide cast shows.
    namespace CastResult
    {
        inline constexpr uint32_t CasterDead = 23;          // "You are dead"
        inline constexpr uint32_t NotFlying = 59;           // "You are flying"
        inline constexpr uint32_t NotHere = 60;             // "You can't use that here"
        inline constexpr uint32_t NotMounted = 64;          // "You are mounted"
        inline constexpr uint32_t NotReady = 67;            // "Not yet recovered"
        inline constexpr uint32_t OnlyAboveWater = 88;      // "Cannot use while swimming"
        inline constexpr uint32_t Rooted = 103;             // "You are unable to move"
        inline constexpr uint32_t SpellUnavailable = 107;   // "The spell is not available to you"
        inline constexpr uint32_t NotOnGround = 171;        // "Cannot be used on the ground" (the addon: glide text)
        inline constexpr uint32_t Ok = 255;                 // SPELL_CAST_OK
    }

    // The cast result of a GLIDE refusal (GlideFacts filled with requireFalling: the spell needs the air).
    inline uint32_t GlideCastResult(GlideRefusal refusal)
    {
        switch (refusal)
        {
            case GlideRefusal::None: return CastResult::Ok;
            case GlideRefusal::Race: return CastResult::SpellUnavailable;
            case GlideRefusal::Here: return CastResult::NotHere;
            case GlideRefusal::Dead: return CastResult::CasterDead;
            case GlideRefusal::Mounted: return CastResult::NotMounted;
            case GlideRefusal::Flying: return CastResult::NotFlying;
            case GlideRefusal::Water: return CastResult::OnlyAboveWater;
            case GlideRefusal::Held: return CastResult::Rooted;
            case GlideRefusal::Ground: return CastResult::NotOnGround;
            case GlideRefusal::Cooldown: return CastResult::NotReady;
        }
        return CastResult::SpellUnavailable;
    }

    // At login: who can glide knows the spell, who cannot (another race, the glide or the spell off) does not.
    enum class SpellbookChange : uint8_t { None, Learn, Unlearn };
    inline SpellbookChange GlideSpellbookChange(bool canGlide, bool knowsSpell)
    {
        if (canGlide && !knowsSpell)
            return SpellbookChange::Learn;
        if (!canGlide && knowsSpell)
            return SpellbookChange::Unlearn;
        return SpellbookChange::None;
    }

    // Where a newly learned spell goes on the action bars (once, when it is learned): the first empty slot of the
    // main bar (0-11), then of the bottom left (60-71), bottom right (48-59), right (24-35) and second right (36-47)
    // bars; -1 when all of them are full. Page 2 of the main bar (12-23) shows only when paged to, and 72 and up are
    // the stance and form bars.
    inline int FirstFreeBarSlot(std::vector<uint8_t> const& occupied)
    {
        constexpr std::array<std::pair<uint8_t, uint8_t>, 5> Bars{ { { 0, 12 }, { 60, 72 }, { 48, 60 }, { 24, 36 },
            { 36, 48 } } };
        for (auto const& [first, end] : Bars)
            for (uint8_t slot = first; slot < end; ++slot)
                if (std::find(occupied.begin(), occupied.end(), slot) == occupied.end())
                    return slot;
        return -1;
    }

    // One glide, from GLIDE until it ends. `airborne`: the fall has become a glide (falling at least GlideMinHeight
    // above the ground); before that the aura only waits for a ledge (GLIDE while standing) and a small hop does not
    // use it up.
    struct Glide
    {
        uint64_t endMs = 0;         // the aura's end
        bool airborne = false;
        uint32_t pushes = 0;
        uint32_t acked = 0;         // pushes the client acked (CMSG_MOVE_KNOCK_BACK_ACK)
        uint64_t lastPushMs = 0;
        float pushFacing = 0;       // the facing of the last push
        float pushDown = 0;         // the descent the last push sent, yd/s (0: the start's)
        bool closing = false;       // landed with a push on its way (GlideStep::Hold): no more pushes
        float lastX = 0, lastY = 0, lastZ = 0;   // the last movement packet's position
        bool hasLast = false;
    };

    // What a movement packet of a gliding player tells.
    struct GlideMove
    {
        uint64_t nowMs = 0;
        bool landed = false;        // MSG_MOVE_FALL_LAND
        bool water = false;         // MSG_MOVE_START_SWIM or swimming
        bool falling = false;       // MOVEMENTFLAG_FALLING or MOVEMENTFLAG_FALLING_FAR
        bool auraOn = true;         // the glide's aura is still on (not cancelled, not dispelled, not dead)
        bool noGlideMap = false;    // on a map without the glide (NoGlideMap; a GLIDE just before the port): it ends
        float height = 1e9f;        // yd above the ground or the water (filled only while falling)
        bool canPush = false;       // client-controlled, not rooted or stunned, not on a transport
        bool moved = false;         // this packet's position is not the last one's (never push a player stuck in place)
        float facing = 0;
    };

    enum class GlideStep : uint8_t
    {
        None,
        Start,     // the fall becomes a glide: mark it airborne, play the start, push (no fall speed) if allowed
        Push,      // push forward along the new facing, keeping the descent speed (a turn, or the first push)
        Hold,      // landed with a push the client has not acked: it throws them off again, so the glide (and its
                   // feather fall) stays without more pushes, and the landing after the ack ends it
        End,       // landed, in water or over: the glide and its aura end
    };

    inline GlideStep NextGlideStep(Glide const& g, GlideMove const& m, bool pushOn, bool steerOn)
    {
        if (m.nowMs >= g.endMs || !m.auraOn || m.noGlideMap)
            return GlideStep::End;
        if (m.water)
            return GlideStep::End;
        if (m.landed || !m.falling)
        {
            if (!g.airborne)
                return GlideStep::None;   // a hop on the ground keeps a waiting glide
            if (g.acked < g.pushes && m.nowMs < g.lastPushMs + GlideAckWaitMs)
                return GlideStep::Hold;   // (a push that is never acked holds it GlideAckWaitMs at most)
            return GlideStep::End;
        }
        if (!g.airborne)
            return m.height >= GlideMinHeight ? GlideStep::Start : GlideStep::None;
        // no push after a landing, nor close to the ground (it could reach the client after it lands)
        if (g.closing || !pushOn || !m.canPush || !m.moved || g.pushes >= GlideMaxPushes || m.height < GlideMinHeight)
            return GlideStep::None;
        if (g.pushes == 0)
            return GlideStep::Push;   // the start could not push (held, on a transport): push once it can
        if (!steerOn || m.nowMs < g.lastPushMs + GlideSteerGapMs)
            return GlideStep::None;
        if (AngleBetween(m.facing, g.pushFacing) < GlideSteerAngle)
            return GlideStep::None;
        return GlideStep::Push;
    }

    // The client acks every push (CMSG_MOVE_KNOCK_BACK_ACK); an ack that is not the glide's (a spell's knockback)
    // counts no further than the pushes sent.
    inline void CountAck(Glide& g)
    {
        g.acked = std::min(g.acked + 1, g.pushes);
    }

    // The descent a steering push keeps: the fall the last push started (at its own descent), over the time since it.
    // Both pushes reach the client with the same delay, so latency drops out; the triggering packet's zspeed and fall
    // time are a round trip old (and the client's to write), and would flatten the glide. A first push that comes late
    // (the start could not push) takes the terminal speed. Turning never slows the descent.
    inline float PushFallSpeed(Glide const& g, uint64_t nowMs)
    {
        if (g.pushes == 0)
            return SafeFallTerminal;
        uint64_t const since = nowMs > g.lastPushMs ? nowMs - g.lastPushMs : 0;
        return FeatherFallSpeed(g.pushDown, static_cast<uint32_t>(std::min<uint64_t>(since, 60000)));
    }

    // Slow Fall, the fallback spell, may be a mage's own. GLIDE does not shorten one with more time left than a glide
    // (the glide rides on it), and the glide's end takes it off only while it is still the one GLIDE put on: the max
    // duration GLIDE gave it (`setMaxMs`; 0: GLIDE rode on the mage's) and no more time left than the glide plus a
    // second (a recast gives it its full 30 s again). Walk on Air is the glide's alone.
    inline bool GlideRidesAura(uint32_t spell, int32_t leftMs, int32_t glideMs)
    {
        return spell == SlowFallSpell && leftMs > glideMs;
    }
    inline bool GlideTakesAura(uint32_t spell, int32_t setMaxMs, int32_t maxMs, int32_t leftMs, uint64_t glideLeftMs)
    {
        if (spell != SlowFallSpell)
            return true;
        return setMaxMs > 0 && maxMs == setMaxMs && leftMs >= 0 && static_cast<uint64_t>(leftMs) <= glideLeftMs + 1000;
    }

    // Whether a new CAMPST must go out: anything but the counting-down timers changed (a timer that starts or
    // ends counts: cooldown started, warmth started or ended, the fire went out, glide used, a glide began or ended).
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
        auto gliding = [](Opt<uint32_t> const& g) { return g && *g > 0; };
        return a.state != b.state || a.mine != b.mine || a.xpPct != b.xpPct || a.repair != b.repair || a.fed != b.fed ||
            on(a.fireSec) != on(b.fireSec) || on(a.cooldownSec) != on(b.cooldownSec) || on(a.warmthSec) != on(b.warmthSec) ||
            glide(a.glideSec) != glide(b.glideSec) || gliding(a.glidingSec) != gliding(b.glidingSec) ||
            !sameObjects(a.objects, b.objects) || !samePlaces(a.place, b.place);
    }
}

#endif
