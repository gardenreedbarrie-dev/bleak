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
        CafeShift,        // CSHIFT   cafeId, on (section 21)
        CafeTake,         // CTAKE    orderId
        CafeStep,         // CSTEP    ticketId, stepIndex, actionId
        CafeRelease,      // CREL     ticketId, stepIndex, clientMs
        CafeOrder,        // CORDER   cafeId, recipeId, tipPct
        CafeCancel,       // CCANCEL  orderId
        CafeStaff,        // CSTAFF   recipeId
        Count
    };

    // GET topics (section 6). The first nine are revisioned (section 5).
    enum class Topic : uint8_t
    {
        Week, Era, Tasks, Key, Board, Queue, Coll, Lidx, Season,   // revisioned
        Firsts, Mplus, Rift, Set, Def, Cases, Case, CampState,
        RoyaleState, RoyaleMap,                                    // ROYS, ROYM (section 17)
        WarModeState, WarZone, WarMap, Wanted,                     // WMST, WPZ, WPMAP, WANTED (section 19)
        Arena,                                                     // ARENA (section 20)
        CafeList, CafeState, CafeQueue, CafeTickets, CafeMenu,     // CAFE, CAFST, CAFQ, CAFT, CAFM (section 21)
        CafeOrderState, CafeProfile, CafeBuffs,                    // CAFO, CAFP, CAFBF
        Count
    };
    inline constexpr uint8_t RevisionedTopicCount = 9;

    // QJOIN kind: the dungeon board, the Eclipse Rift, Bleakhold Royale (section 17: activityId is the mode id,
    // tier 0, size 1), the 1v1 arena queue (section 20: activityId 1, tier 0 skirmish or 1 rated, size 1).
    enum class QueueKind : char { Dungeon = 'D', Rift = 'R', Royale = 'B', Arena = 'A' };
    // LBQ board. A (section 20): seasonId is an arena season id (0 = the current one), dungeonId the bracket.
    // C (section 21): seasonId is a week id (0 = this week), dungeonId the cafe.
    enum class Board : char { Keys = 'K', Rift = 'R', RaidEchoes = 'E', Firsts = 'F', Arena = 'A', Cafe = 'C' };
    // QJOIN A: the one activity (the 1v1 queue); LBQ A: the brackets (1v1, 2v2, 3v3, 5v5).
    inline constexpr uint32_t ArenaActivityId = 1;
    inline constexpr bool IsArenaBracket(uint32_t bracket)
    {
        return bracket == 1 || bracket == 2 || bracket == 3 || bracket == 5;
    }
    // The cafes (section 21): 1 The Lion's Roast (Stormwind), 2 The Grinding Tusk (Orgrimmar). CSHIFT, CORDER and GET
    // CAFM take any id 1..255 (the server checks it); LBQ C only these two.
    inline constexpr bool IsCafeId(uint32_t cafeId) { return cafeId == 1 || cafeId == 2; }
    // CSTEP and CREL: steps 1..MaxCafeStepIndex of a ticket, action ids 1..MaxCafeActionId (the server checks its
    // catalogue); CREL's clientMs is at most MaxCafeReleaseMs. CORDER's tip is one of four percentages.
    inline constexpr uint32_t MaxCafeStepIndex = 12;
    inline constexpr uint32_t MaxCafeActionId = 63;
    inline constexpr uint32_t MaxCafeReleaseMs = 60000;
    inline constexpr bool IsCafeTipPct(uint32_t pct) { return pct == 0 || pct == 10 || pct == 25 || pct == 50; }
    // HELLO caps: the optional parts of the client that are loaded. Bit 1 the cafe's UI (section 21: the staff's
    // gossip opens its windows with CAFUI only for it). A client without optional parts sends no caps field.
    enum ClientCap : uint32_t { ClientCapCafeUi = 1 };
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
        uint32_t arg1 = 0;  // SET: legacy tier; DEF: 0; CASE: the case item id; CAFM: the cafe id
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
        uint32_t caps = 0;             // ClientCap bits; the optional fifth field (0 when left off)

        // GET
        std::vector<TopicRequest> topics;

        // TCLAIM, TREROLL
        uint32_t taskUid = 0;

        // QJOIN
        QueueKind queueKind = QueueKind::Dungeon;
        uint32_t activityId = 0;       // dungeon (map) id, 0 for the Rift, the mode id (> 0) for Royale, 1 for Arena
        uint8_t tier = 0;              // 0 Normal, 1 Veteran, 2 Elite, 3 Nightmare (always 0 for Royale; Arena: 0
                                       // skirmish, 1 rated)
        uint8_t roles = 0;             // RoleMask bits, 1..7 (ignored for Royale and Arena)
        uint8_t groupSize = 0;         // 1..5, 1 = enter alone (always 1 for Royale and Arena)

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
        uint32_t seasonId = 0;         // A: an arena season id; 0 = the current season; C: a week id, 0 = this week
        uint32_t dungeonId = 0;        // 0 = all; A: the bracket, 1, 2, 3 or 5 (never 0); C: the cafe, 1 or 2
        uint32_t classId = 0;          // 0 = all; A: teams with a member of this class
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

        // The cafe (section 21). CSHIFT: cafeId, cafeOn; CTAKE: orderId (0 = the best order I can make); CSTEP:
        // ticketId, stepIndex (the ticket's next step, from 1), actionId; CREL: ticketId, stepIndex, clientMs (what the
        // client measured from CAFEV S to the press; the server clamps it); CORDER: cafeId, recipeId, tipPct (0, 10, 25
        // or 50); CCANCEL: orderId; CSTAFF: recipeId
        uint8_t cafeId = 0;            // 1..255 (the server checks it is a cafe)
        bool cafeOn = false;           // CSHIFT: 1 start a shift, 0 end it
        uint32_t orderId = 0;          // CTAKE 0..2147483647, CCANCEL 1..2147483647
        uint32_t ticketId = 0;         // 1..2147483647
        uint8_t stepIndex = 0;         // 1..MaxCafeStepIndex
        uint8_t actionId = 0;          // 1..MaxCafeActionId
        uint16_t recipeId = 0;         // 1..65535
        uint8_t tipPct = 0;            // IsCafeTipPct
        uint16_t clientMs = 0;         // 0..MaxCafeReleaseMs
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
    // Whether the Endpoint's duplicate guard holds for an action intent: false for RSPEC (next, next is two steps) and
    // the cafe's CTAKE, CSTEP and CREL ("next" twice is two takes; a re-press after an ERR is the same payload and
    // must arrive). Their rate limits still hold.
    bool IsDuplicateGuarded(IntentType type);

    // Parses a whole client chat text ("BHc\t" + body). On success fills `out` and returns
    // DropReason::None. Never keeps references into `chatText`.
    DropReason ParseClientMessage(std::string_view chatText, Intent& out);

    // Canonical payload of an intent, exactly as the reference client encodes it (no frame header).
    std::string EncodeIntentPayload(Intent const& intent);

    // Canonical client frame body "1 OP SEQ 1/1[ PAYLOAD]" (tests and the dedupe key use it).
    std::string EncodeIntentBody(Intent const& intent);
}

#endif
