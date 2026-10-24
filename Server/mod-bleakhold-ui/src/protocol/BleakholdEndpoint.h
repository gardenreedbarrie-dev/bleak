/*
 * mod-bleakhold-ui: server side of the Bleakhold UI protocol (docs/BleakholdProtocol.md).
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Per-player protocol state, without AzerothCore: the handshake, the rate limits of section 8, the
 * duplicate guard, the outgoing SEQ and the revision counter of every topic. The module keeps one
 * Endpoint per online player; the tests drive it directly with a fake clock.
 */

#ifndef BLEAKHOLD_ENDPOINT_H
#define BLEAKHOLD_ENDPOINT_H

#include "BleakholdIntent.h"

#include <array>
#include <cstdint>
#include <string>
#include <string_view>
#include <unordered_map>
#include <vector>

namespace Bleakhold::Proto
{
    // A token bucket. Time is in milliseconds from any monotonic clock.
    class TokenBucket
    {
    public:
        TokenBucket() = default;
        TokenBucket(double capacity, double perSecond) { Configure(capacity, perSecond); }

        void Configure(double capacity, double perSecond);
        bool Take(uint64_t nowMs);          // true when a token was available
        double Tokens() const { return _tokens; }

    private:
        double _capacity = 1;
        double _perMs = 0.001;
        double _tokens = 1;
        uint64_t _lastMs = 0;
        bool _started = false;
    };

    // Section 8 limits (all of them can be changed in mod_bleakhold_ui.conf).
    struct Limits
    {
        double burst = 10;                   // all BHc messages: bucket size ...
        double perSecond = 5;                // ... refilled at this rate; the rest is dropped silently
        uint32_t floodDrops = 200;           // this many drops ...
        uint32_t floodWindowMs = 60000;      // ... within this window ...
        uint32_t floodMuteMs = 60000;        // ... ignore the player's BHc for this long
        uint32_t helloIntervalMs = 5000;     // HELLO: 1 per 5 s
        uint32_t getTopicIntervalMs = 1000;  // GET: every topic at most once per second
        uint32_t heavyTopicIntervalMs = 5000;// GET DEF, LIDX, BOARD (large answers): at most this often (HELLO resets)
        double leaderboardPerSecond = 2;     // LBQ: 2 per second
        uint32_t queueIntervalMs = 1000;     // QJOIN, QLEAVE, QREPLY: 1 per second each
        uint32_t keyIntervalMs = 2000;       // KSTART, KCANCEL, KMODE: 1 per 2 s each
        double claimPerSecond = 2;           // TCLAIM, TREROLL, BCLAIM, OUTFIT, WEHANDIN: 2 per second together
        uint32_t emojiIntervalMs = 2500;     // EMOJI: 1 per BleakholdUi.Emoji.CooldownMs
        uint32_t danceIntervalMs = 1000;     // DANCE: 1 per BleakholdUi.Dance.CooldownMs
        uint32_t caseIntervalMs = 1000;      // CASEOPEN: 1 per BleakholdUi.Case.CooldownMs
        uint32_t campIntervalMs = 1000;      // CAMP (every act together): 1 per BleakholdUi.RateLimit.CampIntervalMs
        uint32_t glideIntervalMs = 1000;     // GLIDE: 1 per BleakholdUi.RateLimit.GlideIntervalMs
        uint32_t repairIntervalMs = 2000;    // REPAIR: 1 per BleakholdUi.RateLimit.RepairIntervalMs
        uint32_t royaleIntervalMs = 500;     // RDROP, RSPEC: 1 each per BleakholdUi.RateLimit.RoyaleIntervalMs
        uint32_t royaleDeployIntervalMs = 1000; // RDEPLOY: 1 per BleakholdUi.RateLimit.RoyaleDeployIntervalMs
        // the same action intent again within this window is ignored (0 = off); RSPEC is never a duplicate (next,
        // next is two steps)
        uint32_t duplicateWindowMs = 1000;
    };

    enum class Verdict : uint8_t
    {
        Accepted,     // dispatch the intent
        Dropped,      // ignore silently (malformed, flood, before HELLO, throttled GET/HELLO, duplicate)
        Refused,      // a well-formed action intent over its own limit: answer ERR "busy"
        NotOurs,      // not a Bleakhold message: let the core deliver it
    };

    struct ReceiveResult
    {
        Verdict verdict = Verdict::Dropped;
        DropReason reason = DropReason::None;
        bool muteStarted = false;     // this message started a flood mute (log it)
    };

    struct EndpointStats
    {
        uint64_t received = 0;
        uint64_t accepted = 0;
        uint64_t refused = 0;
        std::array<uint64_t, static_cast<std::size_t>(DropReason::Count)> dropped{};
        uint64_t framesOut = 0;
        uint64_t messagesOut = 0;
        uint64_t mutes = 0;
    };

    class Endpoint
    {
    public:
        explicit Endpoint(Limits const& limits = Limits());

        void SetLimits(Limits const& limits);

        // Feed one chat text the player whispered to themselves with LANG_ADDON. On Accepted, `out`
        // holds the intent (for GET only the records that passed the per-topic limit).
        ReceiveResult Receive(std::string_view chatText, uint64_t nowMs, Intent& out);

        // True once the client sent a valid HELLO (in this session). Push nothing before.
        bool Ready() const { return _ready; }
        Intent const& Hello() const { return _hello; }

        // Outgoing: builds the chat texts ("BHs\t" + frame) of one server message and advances SEQ.
        // A message that needs more than 99 parts of maxBody is framed with 1000-byte bodies instead.
        // Returns an empty vector (and does not advance SEQ) if the payload cannot be framed at all
        // (over 64 KiB).
        std::vector<std::string> Frame(std::string_view op, std::string_view payload, std::size_t maxBody);

        // Next revision of a revisioned topic (+1 per snapshot or delta; starts at 1).
        uint32_t NextRev(Topic topic);
        uint32_t Rev(Topic topic) const;

        // Whether a snapshot of the topic was sent since the last HELLO (a delta needs one first).
        bool HasSnapshot(Topic topic) const;
        void MarkSnapshot(Topic topic);

        uint32_t Seq() const { return _seq; }
        EndpointStats const& Stats() const { return _stats; }
        bool Muted(uint64_t nowMs) const { return nowMs < _mutedUntil; }

    private:
        void CountDrop(uint64_t nowMs, ReceiveResult& r);
        bool CheckActionLimit(IntentType type, uint64_t nowMs);
        bool FilterGet(Intent& intent, uint64_t nowMs);

        Limits _limits;
        TokenBucket _all;
        TokenBucket _helloBucket;
        TokenBucket _leaderboard;
        TokenBucket _claims;
        std::array<TokenBucket, 3> _queue;   // QJOIN, QLEAVE, QREPLY
        std::array<TokenBucket, 3> _key;     // KMODE, KSTART, KCANCEL
        TokenBucket _emoji;
        TokenBucket _dance;
        TokenBucket _case;
        TokenBucket _camp;
        TokenBucket _glide;
        TokenBucket _repair;
        TokenBucket _royaleDrop;
        TokenBucket _royaleDeploy;
        TokenBucket _royaleSpectate;
        std::unordered_map<std::string, uint64_t> _lastGet;
        struct LastIntent { std::string key; uint64_t atMs = 0; bool set = false; };
        std::array<LastIntent, static_cast<std::size_t>(IntentType::Count)> _last{};

        uint64_t _windowStart = 0;
        uint32_t _windowDrops = 0;
        uint64_t _mutedUntil = 0;

        bool _ready = false;
        Intent _hello;
        uint32_t _seq = 0;
        std::array<uint32_t, RevisionedTopicCount> _rev{};
        std::array<bool, RevisionedTopicCount> _snapshot{};
        EndpointStats _stats;
    };
}

#endif
