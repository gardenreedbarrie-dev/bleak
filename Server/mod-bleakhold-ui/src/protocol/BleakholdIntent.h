/*
 * mod-bleakhold-ui: server side of the Bleakhold UI protocol (docs/BleakholdProtocol.md).
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Client intents (section 6) and their strict parser. No AzerothCore dependency.
 *
 * Everything a client sends is an untrusted request. ParseClientMessage() accepts a message only when
 * it matches the document exactly; anything else is dropped (the caller never echoes client text).
 */

#ifndef BLEAKHOLD_INTENT_H
#define BLEAKHOLD_INTENT_H

#include <cstdint>
#include <string>
#include <string_view>
#include <vector>

namespace Bleakhold
{
    // One value per client op of section 6.
    enum class IntentType : uint8_t
    {
        Hello,            // HELLO    proto, addonVer, dataVer, locale
        Get,              // GET      topic[,arg...] records
        TaskClaim,        // TCLAIM   uid
        TaskReroll,       // TREROLL  uid
        QueueJoin,        // QJOIN    kind, activityId, tier, roles, size
        QueueLeave,       // QLEAVE
        QueueReply,       // QREPLY   proposalId, accept
        KeyMode,          // KMODE    mode
        KeyStart,         // KSTART
        KeyCancel,        // KCANCEL
        BountyClaim,      // BCLAIM   bountyId
        WarEffortHandIn,  // WEHANDIN
        Outfit,           // OUTFIT   setId
        LeaderboardQuery, // LBQ      board, seasonId, dungeonId, classId, page
        Ping,             // PING     nonce
        Emoji,            // EMOJI    emojiId
        Dance,            // DANCE    danceId
        CaseOpen,         // CASEOPEN caseItemId, nonce
        Camp,             // CAMP     act[,skill]
        Glide,            // GLIDE
        Repair,           // REPAIR
        RoyaleDrop,       // RDROP    x, y (section 17)
        RoyaleDeploy,     // RDEPLOY
        RoyaleSpectate,   // RSPEC    dir
        WarMode,          // WARMODE  on (section 19)
        Count
    };

    // GET topics (section 6). The first nine are revisioned (section 5).
    enum class Topic : uint8_t
    {
        Week, Era, Tasks, Key, Board, Queue, Coll, Lidx, Season,   // revisioned
        Firsts, Mplus, Rift, Set, Def, Cases, Case, CampState,
        RoyaleState, RoyaleMap,                                    // ROYS, ROYM (section 17)
        WarModeState, WarZone, WarMap, Wanted,                     // WMST, WPZ, WPMAP, WANTED (section 19)
        Count
    };
    inline constexpr uint8_t RevisionedTopicCount = 9;

    // QJOIN kind: the dungeon board, the Eclipse Rift, Bleakhold Royale (section 17: activityId is the mode id,
    // tier 0, size 1).
    enum class QueueKind : char { Dungeon = 'D', Rift = 'R', Royale = 'B' };
    enum class Board : char { Keys = 'K', Rift = 'R', RaidEchoes = 'E', Firsts = 'F' };
    // CAMP act (section 16): make camp, place a camp object, pack up my camp.
    enum class CampAct : char { Make = 'M', Object = 'O', Pack = 'P' };
    // RSPEC dir (section 17): watch the killer (or the first player alive), the next one, the previous one.
    enum class SpectateDir : uint8_t { Killer = 0, Next = 1, Previous = 2 };

    // RDROP x and y are integer world yards within the limits of a WoW map (+-32 tiles of 533.33 yards).
    inline constexpr int32_t MaxWorldCoord = 17067;

    // Role bits of QJOIN and QUEUE members.
    enum RoleMask : uint8_t { RoleTank = 1, RoleHealer = 2, RoleDamage = 4 };

    struct TopicRequest
    {
        Topic topic = Topic::Week;
        uint32_t arg1 = 0;  // SET: legacy tier; DEF: 0; CASE: the case item id
        uint32_t arg2 = 0;  // SET: class id
    };

    // A parsed client intent. Only the fields of `type` are meaningful.
    struct Intent
    {
        IntentType type = IntentType::Count;
        uint32_t seq = 0;              // the client's SEQ (echoed in ERR)

        // HELLO (hints only: never base a permission or reward on them)
        uint32_t proto = 0;
        std::string addonVersion;      // [A-Za-z0-9_.-]{1,16}
        uint32_t dataVersion = 0;
        std::string locale;            // [A-Za-z0-9_.-]{1,8}

        // GET
        std::vector<TopicRequest> topics;

        // TCLAIM, TREROLL
        uint32_t taskUid = 0;

        // QJOIN
        QueueKind queueKind = QueueKind::Dungeon;
        uint32_t activityId = 0;       // dungeon (map) id, 0 for the Rift, the mode id (> 0) for Royale
        uint8_t tier = 0;              // 0 Normal, 1 Veteran, 2 Elite, 3 Nightmare (always 0 for Royale)
        uint8_t roles = 0;             // RoleMask bits, 1..7 (ignored for Royale)
        uint8_t groupSize = 0;         // 1..5, 1 = enter alone (always 1 for Royale)

        // QREPLY
        uint32_t proposalId = 0;
        bool accept = false;

        // KMODE: 0 Normal, 1 Heroic, 2 Mythic
        uint8_t mode = 0;

        // BCLAIM
        uint32_t bountyId = 0;

        // OUTFIT
        uint32_t setId = 0;

        // LBQ
        Board board = Board::Keys;
        uint32_t seasonId = 0;
        uint32_t dungeonId = 0;        // 0 = all
        uint32_t classId = 0;          // 0 = all
        uint32_t page = 1;             // from 1

        // PING
        uint32_t nonce = 0;

        // EMOJI: 0..255 (the server checks it against its catalogue)
        uint8_t emojiId = 0;

        // DANCE: 0..1023 (the server checks it against its catalogue)
        uint32_t danceId = 0;

        // CASEOPEN: an item id (the server checks it is a case) and the client's number, echoed in UNBOX
        uint32_t caseItemId = 0;
        uint32_t caseNonce = 0;

        // CAMP: the action, and with CampAct::Object the skill line id of the profession (0 otherwise; the server
        // checks it against its camp objects)
        CampAct campAct = CampAct::Make;
        uint32_t campSkill = 0;

        // RDROP: the landing pin the player asks for, integer world yards (may be negative), each within
        // -MaxWorldCoord..MaxWorldCoord; the server snaps it to a valid point
        int32_t dropX = 0;
        int32_t dropY = 0;

        // RSPEC
        SpectateDir spectateDir = SpectateDir::Killer;

        // WARMODE: the state the player asks for (1 on, 0 off; section 19)
        bool warModeOn = false;
    };

    // Why a message was not accepted.
    enum class DropReason : uint8_t
    {
        None,
        NotBleakhold,    // not a Bleakhold message at all: let the core handle it
        ServerPrefix,    // a client used the BHs prefix
        TooLong,         // over 255 bytes in all, or a body over 251
        Nul,             // contains a NUL byte
        BadHeader,       // does not match VER SP OP SP SEQ SP PART/TOTAL[ SP PAYLOAD]
        Version,         // VER is not 1 (only HELLO may carry another version)
        Chunked,         // TOTAL > 1: client messages are always 1/1
        UnknownOp,       // not an intent op
        FieldCount,      // wrong number of fields or records
        BadField,        // a field is not a decimal integer / enum / token where one is required
        OutOfRange,      // a value outside the documented range
        BadTopic,        // GET of an unknown topic or with the wrong arguments
        // reasons produced by the Endpoint (rate limits and handshake)
        Flood,           // over the per-player token bucket
        Muted,           // player ignored for a while after a flood
        NoHello,         // anything but HELLO before the handshake
        Throttled,       // over the limit of this op (HELLO, GET topic, ...)
        Duplicate,       // the same intent again within the duplicate window
        Count
    };

    char const* IntentOpName(IntentType type);          // "TCLAIM", ...; "" for Count
    char const* TopicName(Topic topic);                 // "WEEK", ...
    char const* DropReasonName(DropReason reason);      // short name for logs and stats
    bool IsRevisioned(Topic topic);
    bool IsActionIntent(IntentType type);                // everything but HELLO, GET, LBQ and PING

    // Parses a whole client chat text ("BHc\t" + body). On success fills `out` and returns
    // DropReason::None. Never keeps references into `chatText`.
    DropReason ParseClientMessage(std::string_view chatText, Intent& out);

    // Canonical payload of an intent, exactly as the reference client encodes it (no frame header).
    std::string EncodeIntentPayload(Intent const& intent);

    // Canonical client frame body "1 OP SEQ 1/1[ PAYLOAD]" (tests and the dedupe key use it).
    std::string EncodeIntentBody(Intent const& intent);
}

#endif
