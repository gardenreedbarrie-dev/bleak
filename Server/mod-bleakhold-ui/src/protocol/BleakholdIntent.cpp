/*
 * mod-bleakhold-ui: server side of the Bleakhold UI protocol (docs/BleakholdProtocol.md).
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "BleakholdIntent.h"
#include "BleakholdCodec.h"

#include <array>

namespace Bleakhold
{
    namespace
    {
        using Proto::Int32Max;
        constexpr std::size_t MaxClientOpLength = 8;   // WEHANDIN

        struct OpInfo
        {
            char const* name;
            IntentType type;
        };

        constexpr std::array<OpInfo, static_cast<std::size_t>(IntentType::Count)> Ops = {{
            { "HELLO", IntentType::Hello },
            { "GET", IntentType::Get },
            { "TCLAIM", IntentType::TaskClaim },
            { "TREROLL", IntentType::TaskReroll },
            { "QJOIN", IntentType::QueueJoin },
            { "QLEAVE", IntentType::QueueLeave },
            { "QREPLY", IntentType::QueueReply },
            { "KMODE", IntentType::KeyMode },
            { "KSTART", IntentType::KeyStart },
            { "KCANCEL", IntentType::KeyCancel },
            { "BCLAIM", IntentType::BountyClaim },
            { "WEHANDIN", IntentType::WarEffortHandIn },
            { "OUTFIT", IntentType::Outfit },
            { "LBQ", IntentType::LeaderboardQuery },
            { "PING", IntentType::Ping },
            { "EMOJI", IntentType::Emoji },
            { "DANCE", IntentType::Dance },
            { "CASEOPEN", IntentType::CaseOpen },
            { "CAMP", IntentType::Camp },
            { "GLIDE", IntentType::Glide },
            { "REPAIR", IntentType::Repair },
            { "RDROP", IntentType::RoyaleDrop },
            { "RDEPLOY", IntentType::RoyaleDeploy },
            { "RSPEC", IntentType::RoyaleSpectate },
            { "WARMODE", IntentType::WarMode },
        }};

        struct TopicInfo
        {
            char const* name;
            Topic topic;
            uint8_t args;
        };

        constexpr std::array<TopicInfo, static_cast<std::size_t>(Topic::Count)> Topics = {{
            { "WEEK", Topic::Week, 0 },
            { "ERA", Topic::Era, 0 },
            { "TASKS", Topic::Tasks, 0 },
            { "KEY", Topic::Key, 0 },
            { "BOARD", Topic::Board, 0 },
            { "QUEUE", Topic::Queue, 0 },
            { "COLL", Topic::Coll, 0 },
            { "LIDX", Topic::Lidx, 0 },
            { "SEASON", Topic::Season, 0 },
            { "FIRSTS", Topic::Firsts, 0 },
            { "MPLUS", Topic::Mplus, 0 },
            { "RIFT", Topic::Rift, 0 },
            { "SET", Topic::Set, 2 },
            { "DEF", Topic::Def, 1 },
            { "CASES", Topic::Cases, 0 },
            { "CASE", Topic::Case, 1 },
            { "CAMPST", Topic::CampState, 0 },
            { "ROYS", Topic::RoyaleState, 0 },
            { "ROYM", Topic::RoyaleMap, 0 },
            { "WMST", Topic::WarModeState, 0 },
            { "WPZ", Topic::WarZone, 0 },
            { "WPMAP", Topic::WarMap, 0 },
            { "WANTED", Topic::Wanted, 0 },
        }};

        constexpr char const* DropNames[] = {
            "none", "not_bleakhold", "server_prefix", "too_long", "nul", "bad_header", "version", "chunked",
            "unknown_op", "field_count", "bad_field", "out_of_range", "bad_topic", "flood", "muted", "no_hello",
            "throttled", "duplicate",
        };
        static_assert(sizeof(DropNames) / sizeof(DropNames[0]) == static_cast<std::size_t>(DropReason::Count));

        bool IsDigit(char c) { return c >= '0' && c <= '9'; }

        bool IsTokenChar(char c)
        {
            return (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || IsDigit(c) || c == '_' || c == '.' || c == '-';
        }

        // Splits s at every `sep`, keeping empty pieces.
        std::vector<std::string_view> Split(std::string_view s, char sep)
        {
            std::vector<std::string_view> out;
            std::size_t start = 0;
            while (true)
            {
                std::size_t const p = s.find(sep, start);
                if (p == std::string_view::npos)
                {
                    out.push_back(s.substr(start));
                    break;
                }
                out.push_back(s.substr(start, p - start));
                start = p + 1;
            }
            return out;
        }

        // Integer field in [lo, hi].
        DropReason Int(std::string_view f, int64_t lo, int64_t hi, uint32_t& out)
        {
            std::optional<int64_t> v = Proto::ParseDecimal(f);
            if (!v)
                return DropReason::BadField;
            if (*v < lo || *v > hi)
                return DropReason::OutOfRange;
            out = static_cast<uint32_t>(*v);
            return DropReason::None;
        }

        // Integer field in [lo, hi] that may be negative.
        DropReason Signed(std::string_view f, int64_t lo, int64_t hi, int32_t& out)
        {
            std::optional<int64_t> v = Proto::ParseDecimal(f);
            if (!v)
                return DropReason::BadField;
            if (*v < lo || *v > hi)
                return DropReason::OutOfRange;
            out = static_cast<int32_t>(*v);
            return DropReason::None;
        }

        DropReason Small(std::string_view f, int64_t lo, int64_t hi, uint8_t& out)
        {
            uint32_t v = 0;
            DropReason r = Int(f, lo, hi, v);
            if (r == DropReason::None)
                out = static_cast<uint8_t>(v);
            return r;
        }

        DropReason Token(std::string_view f, std::size_t maxLen, std::string& out)
        {
            if (f.empty() || f.size() > maxLen)
                return DropReason::BadField;
            for (char c : f)
                if (!IsTokenChar(c))
                    return DropReason::BadField;
            out.assign(f.data(), f.size());
            return DropReason::None;
        }

#define BH_TRY(expr) do { DropReason _r = (expr); if (_r != DropReason::None) return _r; } while (0)

        // Number of fields of every op except GET (CAMP: one, or two when the first is O; see ParseFields).
        int FieldCountOf(IntentType t)
        {
            switch (t)
            {
                case IntentType::Hello: return 4;
                case IntentType::TaskClaim: return 1;
                case IntentType::TaskReroll: return 1;
                case IntentType::QueueJoin: return 5;
                case IntentType::QueueLeave: return 0;
                case IntentType::QueueReply: return 2;
                case IntentType::KeyMode: return 1;
                case IntentType::KeyStart: return 0;
                case IntentType::KeyCancel: return 0;
                case IntentType::BountyClaim: return 1;
                case IntentType::WarEffortHandIn: return 0;
                case IntentType::Outfit: return 1;
                case IntentType::LeaderboardQuery: return 5;
                case IntentType::Ping: return 1;
                case IntentType::Emoji: return 1;
                case IntentType::Dance: return 1;
                case IntentType::CaseOpen: return 2;
                case IntentType::Camp: return 1;
                case IntentType::Glide: return 0;
                case IntentType::Repair: return 0;
                case IntentType::RoyaleDrop: return 2;
                case IntentType::RoyaleDeploy: return 0;
                case IntentType::RoyaleSpectate: return 1;
                case IntentType::WarMode: return 1;
                default: return -1;
            }
        }

        DropReason ParseGet(std::string_view payload, Intent& out)
        {
            if (payload.empty())
                return DropReason::FieldCount;
            std::vector<std::string_view> records = Split(payload, ';');
            if (records.size() > 8)
                return DropReason::FieldCount;
            out.topics.clear();
            for (std::string_view rec : records)
            {
                if (rec.empty())
                    return DropReason::FieldCount;
                std::vector<std::string_view> f = Split(rec, ',');
                TopicInfo const* info = nullptr;
                for (TopicInfo const& t : Topics)
                    if (f[0] == t.name)
                        info = &t;
                if (!info)
                    return DropReason::BadTopic;
                if (f.size() - 1 != info->args)
                    return DropReason::BadTopic;
                TopicRequest req;
                req.topic = info->topic;
                if (info->topic == Topic::Set)
                {
                    BH_TRY(Int(f[1], 0, Int32Max, req.arg1));
                    BH_TRY(Int(f[2], 0, Int32Max, req.arg2));
                }
                else if (info->topic == Topic::Def)
                    BH_TRY(Int(f[1], 0, 0, req.arg1));   // "DEF,0": all kinds
                else if (info->topic == Topic::Case)
                    BH_TRY(Int(f[1], 1, Int32Max, req.arg1));
                out.topics.push_back(req);
            }
            return DropReason::None;
        }

        DropReason ParseFields(IntentType type, std::string_view payload, Intent& out)
        {
            if (type == IntentType::Get)
                return ParseGet(payload, out);
            if (payload.find(';') != std::string_view::npos)
                return DropReason::FieldCount;
            std::vector<std::string_view> f;
            if (!payload.empty())
                f = Split(payload, ',');
            // CAMP O carries the skill line id; CAMP M and CAMP P carry nothing more
            int const want = type == IntentType::Camp && !f.empty() && f[0] == "O" ? 2 : FieldCountOf(type);
            if (static_cast<int>(f.size()) != want)
                return DropReason::FieldCount;
            switch (type)
            {
                case IntentType::Hello:
                    BH_TRY(Int(f[0], 1, 999, out.proto));
                    BH_TRY(Token(f[1], 16, out.addonVersion));
                    BH_TRY(Int(f[2], 0, Int32Max, out.dataVersion));
                    BH_TRY(Token(f[3], 8, out.locale));
                    break;
                case IntentType::TaskClaim:
                case IntentType::TaskReroll:
                    BH_TRY(Int(f[0], 1, Int32Max, out.taskUid));
                    break;
                case IntentType::QueueJoin:
                {
                    if (f[0] == "D")
                        out.queueKind = QueueKind::Dungeon;
                    else if (f[0] == "R")
                        out.queueKind = QueueKind::Rift;
                    else if (f[0] == "B")
                        out.queueKind = QueueKind::Royale;
                    else
                        return DropReason::BadField;
                    BH_TRY(Int(f[1], 0, Int32Max, out.activityId));
                    BH_TRY(Small(f[2], 0, 3, out.tier));
                    BH_TRY(Small(f[3], 1, 7, out.roles));
                    BH_TRY(Small(f[4], 1, 5, out.groupSize));
                    // activityId is a dungeon id for D, 0 for the Rift and the mode id for Royale
                    if (out.queueKind == QueueKind::Rift ? out.activityId != 0 : out.activityId == 0)
                        return DropReason::OutOfRange;
                    // Royale is solo and has no tiers (section 17)
                    if (out.queueKind == QueueKind::Royale && (out.tier != 0 || out.groupSize != 1))
                        return DropReason::OutOfRange;
                    break;
                }
                case IntentType::QueueReply:
                {
                    BH_TRY(Int(f[0], 1, Int32Max, out.proposalId));
                    uint32_t a = 0;
                    BH_TRY(Int(f[1], 0, 1, a));
                    out.accept = a == 1;
                    break;
                }
                case IntentType::KeyMode:
                    BH_TRY(Small(f[0], 0, 2, out.mode));
                    break;
                case IntentType::BountyClaim:
                    BH_TRY(Int(f[0], 1, Int32Max, out.bountyId));
                    break;
                case IntentType::Outfit:
                    BH_TRY(Int(f[0], 1, Int32Max, out.setId));
                    break;
                case IntentType::LeaderboardQuery:
                {
                    if (f[0].size() != 1)
                        return DropReason::BadField;
                    switch (f[0][0])
                    {
                        case 'K': out.board = Board::Keys; break;
                        case 'R': out.board = Board::Rift; break;
                        case 'E': out.board = Board::RaidEchoes; break;
                        case 'F': out.board = Board::Firsts; break;
                        default: return DropReason::BadField;
                    }
                    BH_TRY(Int(f[1], 0, Int32Max, out.seasonId));
                    BH_TRY(Int(f[2], 0, Int32Max, out.dungeonId));
                    BH_TRY(Int(f[3], 0, Int32Max, out.classId));
                    BH_TRY(Int(f[4], 1, 999, out.page));
                    break;
                }
                case IntentType::Ping:
                    BH_TRY(Int(f[0], 0, Int32Max, out.nonce));
                    break;
                case IntentType::Emoji:
                    BH_TRY(Small(f[0], 0, Proto::MaxEmojis - 1, out.emojiId));
                    break;
                case IntentType::Dance:
                    BH_TRY(Int(f[0], 0, Proto::MaxDances - 1, out.danceId));
                    break;
                case IntentType::CaseOpen:
                    BH_TRY(Int(f[0], 1, Int32Max, out.caseItemId));
                    BH_TRY(Int(f[1], 0, Int32Max, out.caseNonce));
                    break;
                case IntentType::Camp:
                    if (f[0] == "M")
                        out.campAct = CampAct::Make;
                    else if (f[0] == "P")
                        out.campAct = CampAct::Pack;
                    else if (f[0] == "O")
                    {
                        out.campAct = CampAct::Object;
                        BH_TRY(Int(f[1], 1, Int32Max, out.campSkill));
                    }
                    else
                        return DropReason::BadField;
                    break;
                case IntentType::RoyaleDrop:
                    BH_TRY(Signed(f[0], -MaxWorldCoord, MaxWorldCoord, out.dropX));
                    BH_TRY(Signed(f[1], -MaxWorldCoord, MaxWorldCoord, out.dropY));
                    break;
                case IntentType::RoyaleSpectate:
                {
                    uint8_t dir = 0;
                    BH_TRY(Small(f[0], 0, 2, dir));
                    out.spectateDir = static_cast<SpectateDir>(dir);
                    break;
                }
                case IntentType::WarMode:
                {
                    uint32_t on = 0;
                    BH_TRY(Int(f[0], 0, 1, on));
                    out.warModeOn = on == 1;
                    break;
                }
                default:
                    break;
            }
            return DropReason::None;
        }

#undef BH_TRY
    }

    char const* IntentOpName(IntentType type)
    {
        std::size_t const i = static_cast<std::size_t>(type);
        return i < Ops.size() ? Ops[i].name : "";
    }

    char const* TopicName(Topic topic)
    {
        std::size_t const i = static_cast<std::size_t>(topic);
        return i < Topics.size() ? Topics[i].name : "";
    }

    char const* DropReasonName(DropReason reason)
    {
        std::size_t const i = static_cast<std::size_t>(reason);
        return i < static_cast<std::size_t>(DropReason::Count) ? DropNames[i] : "?";
    }

    bool IsRevisioned(Topic topic)
    {
        return static_cast<uint8_t>(topic) < RevisionedTopicCount;
    }

    bool IsActionIntent(IntentType type)
    {
        switch (type)
        {
            case IntentType::Hello:
            case IntentType::Get:
            case IntentType::LeaderboardQuery:
            case IntentType::Ping:
            case IntentType::Count:
                return false;
            default:
                return true;
        }
    }

    DropReason ParseClientMessage(std::string_view text, Intent& out)
    {
        // The prefix is everything before the first tab (the client splits there too).
        std::size_t const tab = text.find('\t');
        std::string_view const prefix = text.substr(0, tab);
        if (prefix == Proto::ServerPrefix)
            return DropReason::ServerPrefix;
        if (prefix != Proto::ClientPrefix)
            return DropReason::NotBleakhold;
        if (text.size() > Proto::MaxClientMessage)
            return DropReason::TooLong;
        if (text.find('\0') != std::string_view::npos)
            return DropReason::Nul;
        if (tab == std::string_view::npos)
            return DropReason::BadHeader;
        std::string_view body = text.substr(tab + 1);
        if (body.size() > Proto::MaxClientBody)
            return DropReason::TooLong;

        std::size_t i = 0;
        auto takeWhile = [&](auto pred, std::size_t maxLen) -> std::string_view {
            std::size_t const start = i;
            while (i < body.size() && i - start < maxLen + 1 && pred(body[i]))
                ++i;
            return body.substr(start, i - start);
        };
        auto expect = [&](char c) -> bool {
            if (i < body.size() && body[i] == c)
            {
                ++i;
                return true;
            }
            return false;
        };

        std::string_view const ver = takeWhile(IsDigit, 3);
        if (ver.empty() || ver.size() > 3 || !expect(' '))
            return DropReason::BadHeader;
        // The document says 2 to 6 letters, but three of its own intents are longer (TREROLL, KCANCEL,
        // WEHANDIN), so client ops may have up to 8; the op must be a known intent anyway.
        std::string_view const op = takeWhile([](char c) { return c >= 'A' && c <= 'Z'; }, MaxClientOpLength);
        if (op.size() < 2 || op.size() > MaxClientOpLength || !expect(' '))
            return DropReason::BadHeader;
        std::string_view const seq = takeWhile([](char c) { return IsDigit(c) || (c >= 'a' && c <= 'z'); }, 6);
        if (seq.empty() || seq.size() > 6 || !expect(' '))
            return DropReason::BadHeader;
        std::string_view const part = takeWhile(IsDigit, 2);
        if (part.empty() || part.size() > 2 || !expect('/'))
            return DropReason::BadHeader;
        std::string_view const total = takeWhile(IsDigit, 2);
        if (total.empty() || total.size() > 2)
            return DropReason::BadHeader;
        std::string_view payload;
        if (i < body.size())
        {
            if (!expect(' '))
                return DropReason::BadHeader;
            payload = body.substr(i);
        }

        int64_t const partV = *Proto::ParseDecimal(part);
        int64_t const totalV = *Proto::ParseDecimal(total);
        if (partV < 1 || totalV < 1 || partV > totalV)
            return DropReason::BadHeader;
        if (totalV != 1)
            return DropReason::Chunked;

        IntentType type = IntentType::Count;
        for (OpInfo const& o : Ops)
            if (op == o.name)
                type = o.type;
        if (type == IntentType::Count)
            return DropReason::UnknownOp;
        // VER must be 1; only HELLO is read whatever its version, so an old or new client can learn
        // what this server speaks.
        if (*Proto::ParseDecimal(ver) != Proto::ProtocolVersion && type != IntentType::Hello)
            return DropReason::Version;

        Intent parsed;
        parsed.type = type;
        parsed.seq = *Proto::ParseBase36(seq);
        DropReason const r = ParseFields(type, payload, parsed);
        if (r != DropReason::None)
            return r;
        out = std::move(parsed);
        return DropReason::None;
    }

    std::string EncodeIntentPayload(Intent const& in)
    {
        auto n = [](uint32_t v) { return std::to_string(v); };
        switch (in.type)
        {
            case IntentType::Hello:
                return n(in.proto) + "," + in.addonVersion + "," + n(in.dataVersion) + "," + in.locale;
            case IntentType::Get:
            {
                std::string out;
                for (TopicRequest const& t : in.topics)
                {
                    if (!out.empty())
                        out += ';';
                    out += TopicName(t.topic);
                    if (t.topic == Topic::Set)
                        out += "," + n(t.arg1) + "," + n(t.arg2);
                    else if (t.topic == Topic::Def || t.topic == Topic::Case)
                        out += "," + n(t.arg1);
                }
                return out;
            }
            case IntentType::TaskClaim:
            case IntentType::TaskReroll:
                return n(in.taskUid);
            case IntentType::QueueJoin:
                return std::string(1, static_cast<char>(in.queueKind)) + "," + n(in.activityId) + "," + n(in.tier) + "," +
                    n(in.roles) + "," + n(in.groupSize);
            case IntentType::QueueReply:
                return n(in.proposalId) + "," + (in.accept ? "1" : "0");
            case IntentType::KeyMode:
                return n(in.mode);
            case IntentType::BountyClaim:
                return n(in.bountyId);
            case IntentType::Outfit:
                return n(in.setId);
            case IntentType::LeaderboardQuery:
                return std::string(1, static_cast<char>(in.board)) + "," + n(in.seasonId) + "," + n(in.dungeonId) + "," +
                    n(in.classId) + "," + n(in.page);
            case IntentType::Ping:
                return n(in.nonce);
            case IntentType::Emoji:
                return n(in.emojiId);
            case IntentType::Dance:
                return n(in.danceId);
            case IntentType::CaseOpen:
                return n(in.caseItemId) + "," + n(in.caseNonce);
            case IntentType::Camp:
                return in.campAct == CampAct::Object ? "O," + n(in.campSkill) : std::string(1, static_cast<char>(in.campAct));
            case IntentType::RoyaleDrop:
                return std::to_string(in.dropX) + "," + std::to_string(in.dropY);
            case IntentType::RoyaleSpectate:
                return n(static_cast<uint32_t>(in.spectateDir));
            case IntentType::WarMode:
                return in.warModeOn ? "1" : "0";
            default:
                return std::string();
        }
    }

    std::string EncodeIntentBody(Intent const& in)
    {
        std::string body = "1 ";
        body += IntentOpName(in.type);
        body += ' ';
        body += Proto::Base36(in.seq);
        body += " 1/1";
        std::string const payload = EncodeIntentPayload(in);
        if (!payload.empty())
        {
            body += ' ';
            body += payload;
        }
        return body;
    }
}
