/*
 * mod-bleakhold-ui: server side of the Bleakhold UI protocol (docs/BleakholdProtocol.md).
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Camping (section 16): campfires (CAMP M), camp objects of the professions (CAMP O), packing up (CAMP P), rest at a
 * fire, settling (camp object buffs and Campfire Warmth), the XP bonus of warmth and Well Fed food, field repair
 * (REPAIR), the High Elf glide Walk on Air (GLIDE) and the CAMPST state.
 *
 * Threads: everything runs on the world thread (the chat hook, the world tick, login and logout) except four hooks
 * that come from map threads: XpBonusPct (OnPlayerGiveXP), OnEnterCombat, OnGameObjectAdded and OnPlayerMove (the
 * glide). Those touch only the player they are given, the timers and the glides (under their own locks) and a queue of
 * new fires. Game objects and players are kept as guids and found again on every use, so a fire that despawns, a grid
 * that unloads or a player who logs out leaves nothing dangling.
 *
 * Glide (Walk on Air): GLIDE puts the feather fall aura (BleakholdUi.Glide.Spell) on the player. A fall at least
 * CampRules::GlideMinHeight above the ground becomes a glide: the server pushes the player forward along their facing
 * (Unit::KnockbackFrom from a point behind them, BleakholdUi.Glide.ForwardSpeed, no vertical speed: never up), and
 * again whenever they turn (OnPlayerMove: the client reports its facing while falling, and keeps the direction a fall
 * started with otherwise), never close to the ground. Landing or water ends the glide and takes the aura away (a
 * landing with a push still on its way waits for its ack: the push throws the player off again); a GLIDE on the
 * ground waits for a ledge until the aura runs out, and a map without the glide ends it (a battleground or an arena;
 * a dungeon or a raid unless BleakholdUi.Glide.Instances: CampRules::NoGlideMap). CampRules.h holds the rules, and
 * docs/BleakholdProtocol.md section 16 why mod-anticheat accepts it.
 *
 * Rest: a player at a fire gets the core's REST_FLAG_IN_FACTION_AREA bit (the core has no camp bit); outside an area that
 * has the faction rest flag that bit can only be the camp's. The core's rest mask keeps inn and city rest when the bit
 * goes, and the bit is still set when the core saves a player who logs out at the fire, so that logout counts as an inn
 * logout. The RESTING player flag such a logout leaves in the characters table is cleared at the next login. A player
 * who already rests without any rest bit (Player::SetRestState: mod-guildhouse) gets no camp bit at all
 * (CampRules::MaySetCampRestBit): taking it off later would end that rest too.
 */

#ifndef BLEAKHOLD_CAMP_H
#define BLEAKHOLD_CAMP_H

#include "BleakholdCampRules.h"
#include "BleakholdMessages.h"

#include <array>
#include <atomic>
#include <cstdint>
#include <mutex>
#include <string>
#include <unordered_map>
#include <vector>

class GameObject;
class Map;
class Player;
struct MovementInfo;

namespace Bleakhold
{
    struct CampConfig
    {
        bool campOn = true;                  // BleakholdUi.Camp.Enable (feature bit 512)
        bool glideOn = true;                 // BleakholdUi.Glide.Enable (1024)
        bool repairOn = true;                // BleakholdUi.Repair.Enable (2048)
        uint32_t minLevel = 5;
        uint32_t cooldownSec = 900;
        uint32_t fireSec = 900;
        uint32_t fireEntry = 194300;         // the camp fire's gameobject_template entry
        std::vector<uint32_t> extraFireEntries;
        std::vector<uint32_t> allowedFocusIds{ 1, 3, 4 };   // spell foci camp objects and fires may carry
        float radius = 10.0f;
        uint32_t settleSec = 60;
        uint32_t buffSec = 3600;
        uint32_t warmthSec = 1800;
        uint32_t warmthXpPct = 10;
        uint32_t warmthSpell = 0;            // an aura shown for the warmth (0: none); cosmetic, the bonus is the module's
        uint32_t foodXpPct = 5;
        uint32_t maxXpPct = 25;
        CampRules::Tiers tierSkill = CampRules::DefaultTierSkill;
        std::vector<CampRules::Profession> professions;
        uint32_t repairMinSkill = 75;
        uint32_t repairDiscountPct = 10;
        std::vector<uint32_t> glideRaces{ 15 };
        uint32_t glideCooldownSec = 90;
        uint32_t glideSec = 10;
        uint32_t glideSpell = CampRules::WalkOnAirSpell;   // falls back to CampRules::SlowFallSpell when missing
        float glideForwardSpeed = 12.0f;     // yd/s (0: no push, a plain slow fall)
        bool glideSteer = true;              // push again when the player turns
        bool glideRequireFalling = false;    // GLIDE only in the air
        bool glideInstances = false;         // GLIDE in dungeons and raids
        uint32_t glideStartKit = 13709;      // SpellVisualKit played when a glide starts (0: none)
    };

    class Camp
    {
    public:
        static Camp& Instance();

        // BleakholdUi.Camp.*, Glide.*, Repair.* (world thread; from Mgr::LoadConfig). The ids are checked against the
        // world tables once they are loaded (OnStartup) and again on every later load.
        void LoadConfig();
        void OnStartup();

        // ---- intents and the CAMPST topic (world thread) ----
        void HandleCamp(Player* player, Intent const& intent);
        void HandleGlide(Player* player, Intent const& intent);
        void HandleRepair(Player* player, Intent const& intent);
        // CAMPST now, or as soon as a second has passed since the last one (GET CAMPST, after HELLO).
        void RequestState(Player* player);
        CampState StateOf(Player* player);

        // Every world tick: fires, who is at which fire, rest, settling, CAMPST changes.
        void Update(uint64_t nowMs);

        // ---- hooks ----
        void OnLogin(Player* player);                 // world thread: clears a RESTING flag left by a camp logout
        void OnLogout(Player* player);                // world thread: forgets the player's camp state and glide
        // map thread (every movement packet of every player; a single atomic load while nobody glides)
        void OnPlayerMove(Player* player, MovementInfo const& movementInfo, uint32_t opcode);
        static void OnEnterCombat(Player* player);    // map thread: camp rest ends at once (rest allows logout in combat)
        uint32_t XpBonusPct(Player* player);          // map thread: warmth + Well Fed, capped; 0 at the level cap
        void OnGameObjectAdded(GameObject* go);       // map threads: notes Basic Campfires and Camp.ExtraFireEntries

        // ---- GM command (world thread) ----
        std::vector<std::string> Describe(Player* player);
        void ResetCooldowns(Player* player);
        bool SpawnFireFor(Player* player, std::string& error);   // a camp fire for the player, without the rules
        struct Counts { std::size_t fires = 0, objects = 0, atFire = 0; };
        Counts GetCounts();

    private:
        Camp() = default;

        struct CampObject
        {
            uint64_t guid = 0;          // raw game object guid
            uint32_t skill = 0;
            uint8_t tier = 1;
            uint32_t buff = 0;
            uint64_t owner = 0;         // raw player guid
            uint8_t slot = 0;
        };
        struct Fire
        {
            uint64_t guid = 0;
            uint32_t mapId = 0;
            uint32_t entry = 0;
            bool ours = false;          // made with CAMP M (or the GM command)
            bool permanent = false;     // a world spawn: never goes out
            uint64_t owner = 0;         // the maker, or the caster of a Basic Campfire; 0 for a world spawn
            float x = 0, y = 0, z = 0, o = 0;
            std::vector<CampObject> objects;
        };
        struct Camper
        {
            uint64_t fire = 0;          // the fire the player is at (0: none)
            uint64_t arrivedMs = 0;
            bool settled = false;
            CampState sent;             // the last CAMPST
            bool hasSent = false;
            bool want = false;          // a CAMPST is due (an event, or a change within the last second)
            uint64_t sentMs = 0;
        };
        struct Timers { uint64_t campReadyAt = 0, warmthEnd = 0, glideReadyAt = 0; };   // game time, seconds
        struct NewFire { uint64_t guid = 0; uint32_t mapId = 0, entry = 0; bool permanent = false; uint64_t owner = 0; float x = 0, y = 0, z = 0, o = 0; };

        void MakeCamp(Player* player, Intent const& intent);
        void PlaceObject(Player* player, Intent const& intent);
        void PackUp(Player* player, Intent const& intent);
        GameObject* SummonFire(Player* player, uint32_t lifetimeSec);
        Fire* FireOf(Player* player, GameObject** go = nullptr);     // the fire the player is at now, checked again
        GameObject* Resolve(Fire const& fire, Map** map = nullptr);
        void RemoveFire(uint64_t fireGuid, bool despawnFire);
        void Settle(Player* player, Fire const& fire);
        void ApplyObjectBuff(Player* player, uint32_t skill, uint8_t tier, uint32_t buff);
        void ApplyAura(Player* player, uint32_t spellId, uint32_t seconds);
        CampRules::Profession const* ProfessionOf(uint32_t skill) const;
        uint8_t PlaceableTier(Player* player, CampRules::Profession const& prof) const;
        bool CanGlide(Player* player) const;
        // the glide's push (map thread or world thread, for the player given): along `facing`, `fallSpeed` yd/s down
        static void GlidePush(Player* player, float facing, float forwardSpeed, float fallSpeed);
        static bool CanPush(Player* player);
        static float HeightAboveGround(Player* player, float x, float y, float z);
        // on a map without the glide: a battleground or an arena (Royale's included), a dungeon or a raid unless
        // `instancesOn` (CampRules::NoGlideMap)
        static bool NoGlideHere(Player* player, bool instancesOn);
        void EndGlide(uint64_t rawGuid);              // forget a glide (the aura is the caller's business)
        Opt<uint32_t> GlidingSec(uint64_t rawGuid);   // CAMPST gliding
        static bool AnvilAt(Fire const& fire);
        static bool InFactionRestArea(Player* player);
        static void EndCampRest(Player* player);
        static bool IsWellFed(Player* player);
        static bool InCityOrSanctuary(Player* player);
        void SendState(Player* player, Camper& camper, uint64_t nowMs);
        void Validate();
        void DrainNewFires();
        Timers TimersOf(uint32_t lowGuid);

        std::recursive_mutex _lock;                  // the world-thread state below (defensive: all of it is world thread)
        CampConfig _cfg;
        std::unordered_map<uint64_t, Fire> _fires;
        std::unordered_map<uint64_t, Camper> _campers;
        uint64_t _lastTickMs = 0;
        uint64_t _lastPurgeMs = 0;
        bool _worldLoaded = false;

        std::mutex _timerLock;                       // timers survive a relog (a relog must not reset a cooldown)
        std::unordered_map<uint32_t, Timers> _timers;

        std::mutex _newLock;                         // fires noted by OnGameObjectAdded, taken in by the next tick
        std::vector<NewFire> _newFires;

        // the glides running now, by raw player guid (map threads: OnPlayerMove; world thread: GLIDE, the tick); never
        // held while another of the module's locks is taken
        struct GlideRun
        {
            CampRules::Glide glide;
            uint32_t spell = 0;          // the aura it put on (the config may change mid-glide)
            float forwardSpeed = 0;
            bool steer = true;
            bool instances = false;      // BleakholdUi.Glide.Instances as GLIDE read it
            uint32_t startKit = 0;
            int32_t auraMaxMs = 0;       // the aura's max duration as GLIDE set it (0: it rode on a mage's Slow Fall)
        };
        // the end of a glide takes its aura off (not a mage's own Slow Fall: CampRules::GlideTakesAura)
        static void TakeGlideAura(Player* player, GlideRun const& run, uint64_t nowMs);
        std::mutex _glideLock;
        std::unordered_map<uint64_t, GlideRun> _glides;
        std::atomic<uint32_t> _glideCount{ 0 };       // _glides.size(), read without the lock by OnPlayerMove

        // read by the map-thread hooks without a lock
        static constexpr std::size_t MaxHookEntries = 16;
        std::array<std::atomic<uint32_t>, MaxHookEntries> _hookEntries{};
        std::atomic<uint32_t> _hookCount{ 0 };
        std::atomic<bool> _xpOn{ true };
        std::atomic<uint32_t> _xpWarmth{ 10 }, _xpFood{ 5 }, _xpMax{ 25 };
    };
}

#endif
