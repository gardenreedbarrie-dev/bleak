// mod-bleakhold-ui tests: unit tests of the core-independent protocol code, and every example frame of
// docs/BleakholdProtocol.md.
//
//   bh_unit <repo root>
//
// SPDX-License-Identifier: GPL-2.0-or-later

#include "bh_check.h"

#include "BleakholdCodec.h"
#include "BleakholdEndpoint.h"
#include "BleakholdIntent.h"
#include "BleakholdMessages.h"
#include "../../src/BleakholdCampRules.h"
#include "../../src/BleakholdCases.h"
#include "../../src/BleakholdDance.h"
#include "../../src/BleakholdEmoji.h"

#include <cmath>
#include <map>
#include <set>

using namespace Bleakhold;
using namespace Bleakhold::Proto;

static std::string g_repo;

// ---------------------------------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------------------------------
static std::vector<std::string> SplitStr(std::string const& s, char sep)
{
    std::vector<std::string> out;
    std::size_t start = 0;
    while (true)
    {
        std::size_t p = s.find(sep, start);
        if (p == std::string::npos)
        {
            out.push_back(s.substr(start));
            return out;
        }
        out.push_back(s.substr(start, p - start));
        start = p + 1;
    }
}

// Payload compared the way the client reads it: a missing trailing field is the same as an empty one.
static std::string Norm(std::string const& payload)
{
    std::string out;
    std::vector<std::string> recs = SplitStr(payload, ';');
    for (std::size_t r = 0; r < recs.size(); ++r)
    {
        std::vector<std::string> f = SplitStr(recs[r], ',');
        while (f.size() > 1 && f.back().empty())
            f.pop_back();
        if (r)
            out += ';';
        for (std::size_t i = 0; i < f.size(); ++i)
        {
            if (i)
                out += ',';
            out += f[i];
        }
    }
    return out;
}

static std::string Chat(std::string const& body) { return "BHc\t" + body; }

static DropReason Parse(std::string const& body, Intent* out = nullptr)
{
    Intent tmp;
    DropReason r = ParseClientMessage(Chat(body), tmp);
    if (out)
        *out = tmp;
    return r;
}

static std::vector<std::string> DocLines(char const* prefix)
{
    std::string const doc = bhtest::ReadFile(g_repo + "/docs/BleakholdProtocol.md");
    std::vector<std::string> out;
    std::string const p = std::string(prefix) + " ";
    for (std::string const& line : SplitStr(doc, '\n'))
        if (line.compare(0, p.size(), p) == 0)
            out.push_back(line.substr(p.size()));
    return out;
}

// ---------------------------------------------------------------------------------------------------
// Codec
// ---------------------------------------------------------------------------------------------------
TEST("base36 round trip and limits")
{
    CHECK_EQ(Base36(0), "0");
    CHECK_EQ(Base36(35), "z");
    CHECK_EQ(Base36(36), "10");
    CHECK_EQ(Base36(SeqModulo - 1), "zzzzzz");
    CHECK_EQ(Base36(SeqModulo), "0");
    for (uint32_t v : { 1u, 7u, 1295u, 46655u, 1000000u, SeqModulo - 1 })
        CHECK_EQN(*ParseBase36(Base36(v)), v);
    CHECK(!ParseBase36(""));
    CHECK(!ParseBase36("1234567"));
    CHECK(!ParseBase36("A"));
    CHECK(!ParseBase36("-1"));
    CHECK_EQN(NextSeq(0), 1u);
    CHECK_EQN(NextSeq(41), 42u);
    CHECK_EQN(NextSeq(SeqModulo - 1), 1u);
}

TEST("escaping covers separators, percent, pipe and control bytes")
{
    CHECK_EQ(EscapeText("a;b,c:d~e|f%g"), "a%3Bb%2Cc%3Ad%7Ee%7Cf%25g");
    CHECK_EQ(EscapeText("tab\there\nnew\x7F"), "tab%09here%0Anew%7F");
    CHECK_EQ(EscapeText(std::string("nul\0byte", 8)), "nulbyte");
    CHECK_EQ(EscapeText("caf\xC3\xA9"), "caf\xC3\xA9");
    CHECK_EQ(EscapeText("bad\xFF\xFEx"), "bad??x");
    CHECK_EQ(EscapeText("\xE2\x82"), "??");
    CHECK_EQ(EscapeText("\xC0\x80"), "??");           // overlong NUL
    CHECK_EQ(EscapeText("\xED\xA0\x80"), "???");      // UTF-16 surrogate
    CHECK_EQ(EscapeText(std::string(30, 'x') + "\xC3\xA9", 31), std::string(30, 'x'));   // never half a sequence
    CHECK_EQ(EscapeText("\xC3\xA9\xC3\xA9\xC3\xA9", 5), "\xC3\xA9\xC3\xA9");
    std::string ascii;
    for (int b = 1; b < 128; ++b)
        ascii += static_cast<char>(b);
    std::string const e = EscapeText(ascii);
    CHECK(e.find_first_of(";,:~|") == std::string::npos);
    for (char c : e)
        CHECK(static_cast<unsigned char>(c) >= 0x20 && static_cast<unsigned char>(c) != 0x7F);
    CHECK_EQ(*Unescape(e), ascii);
    CHECK(!Unescape("%4"));
    CHECK(!Unescape("abc%"));
    CHECK(!Unescape("%G1"));
    CHECK(!Unescape("%00"));
    CHECK_EQ(*Unescape("%41%42"), "AB");
}

TEST("payload writer: records, lists, tuples, trailing empty fields")
{
    PayloadWriter w;
    w.Int(1).Empty().Text("x,y").Empty().Empty();
    w.Record().Ints(std::vector<uint32_t>{ 1, 3, 4 }).Texts({ "a:b", "c" }).Empty();
    w.Record().Empty().Empty();
    w.Record().Tuples({ { PayloadWriter::TuplePart("Na~me"), PayloadWriter::TuplePart(int64_t(3)) }, { "B", "2" } });
    CHECK_EQ(w.Take(), "1,,x%2Cy;1:3:4,a%3Ab:c;,;Na%7Eme~3:B~2");
    PayloadWriter v;
    v.Empty();
    CHECK_EQ(v.Take(), "");
    PayloadWriter o;
    o.Opt(Opt<uint32_t>()).Opt(Opt<uint32_t>(5)).Opt(Opt<bool>(true)).Opt(Opt<bool>()).Opt(Opt<int32_t>(-3));
    CHECK_EQ(o.Take(), ",5,1,,-3");
    PayloadWriter c;
    c.Char('K').Char('k').Char(';');
    CHECK_EQ(c.Take(), "K");
}

static void CheckFrames(std::string const& op, uint32_t seq, std::string const& payload, std::size_t maxBody)
{
    std::vector<std::string> frames = BuildFrames(op, seq, payload, maxBody);
    CHECK_MSG(!frames.empty(), "frames for maxBody " + std::to_string(maxBody));
    std::string joined;
    for (std::size_t i = 0; i < frames.size(); ++i)
    {
        std::string const& f = frames[i];
        CHECK_MSG(f.size() <= maxBody, "frame within maxBody");
        std::string const head = "1 " + op + " " + Base36(seq) + " " + std::to_string(i + 1) + "/" + std::to_string(frames.size());
        CHECK_MSG(f.compare(0, head.size(), head) == 0, "header " + head);
        std::string part = f.size() > head.size() ? f.substr(head.size() + 1) : std::string();
        CHECK(f.size() == head.size() || f[head.size()] == ' ');
        if (!part.empty())
        {
            CHECK_MSG(part.back() != '%', "no cut right after %");
            CHECK_MSG(part.size() < 2 || part[part.size() - 2] != '%', "no cut inside %XX");
            unsigned char const first = static_cast<unsigned char>(part[0]);
            CHECK_MSG(i == 0 || !(first >= 0x80 && first < 0xC0), "no part starts inside a UTF-8 sequence");
        }
        joined += part;
    }
    CHECK_MSG(joined == payload, "reassembles");
}

TEST("frames: chunking at records, never inside an escape or UTF-8")
{
    PayloadWriter w;
    for (int i = 0; i < 80; ++i)
        w.Record().Int(i).Text("Na%me;" + std::to_string(i)).Text("\xC3\xA9\xE2\x82\xAC caf\xC3\xA9 \xF0\x9F\x98\x80");
    std::string const payload = w.Take();
    for (std::size_t maxBody : { 64u, 100u, 233u, 251u, 255u, 1000u })
        CheckFrames("LB", 77, payload, maxBody);
    // dense escapes and multibyte text without any record separator
    std::string dense;
    for (int i = 0; i < 900; ++i)
        dense += (i % 3 == 0) ? std::string("%2C") : (i % 3 == 1 ? std::string("\xE2\x82\xAC") : std::string("\xF0\x9F\x98\x80"));
    for (std::size_t maxBody : { 64u, 65u, 66u, 67u, 99u, 1000u })
        CheckFrames("BOARD", 1295, dense, maxBody);
    CHECK_EQ(BuildFrames("QLEAVE", 9, "", 1000).at(0), "1 QLEAVE 9 1/1");
    CHECK(BuildFrames("week", 1, "x").empty());
    CHECK(BuildFrames("TOOLONGOP", 1, "x").empty());
    CHECK(BuildFrames("WEEK", 1, std::string(MaxAssembled + 1, 'x')).empty());
    CHECK(BuildFrames("WEEK", 1, std::string(99 * 60, 'x'), 64).empty());   // more than 99 parts
    CHECK(BuildFrames("WEEK", 1, "x", 10).empty());
    std::size_t const capped = BuildFrames("WEEK", 1, std::string(5000, 'x'), 5000).at(0).size();   // capped at 1000
    CHECK(capped <= 1000 && capped >= 990);
}

TEST("definition hash is stable, content based and never zero")
{
    Definitions a;
    a.affixes.push_back({ 1, "Fortified", "x" });
    Definitions b = a;
    CHECK_EQN(DefinitionsHash(a), DefinitionsHash(b));
    b.affixes[0].text = "y";
    CHECK(DefinitionsHash(a) != DefinitionsHash(b));
    CHECK(DefinitionsHash(Definitions()) != 0);
    CHECK(DefinitionsHash(a) <= 0x7FFFFFFFu);
}

// ---------------------------------------------------------------------------------------------------
// Client messages
// ---------------------------------------------------------------------------------------------------
TEST("every C> example of the document is accepted and re-encodes byte for byte")
{
    std::vector<std::string> lines = DocLines("C>");
    CHECK(lines.size() >= 17);
    bool seen[static_cast<std::size_t>(IntentType::Count)] = {};
    for (std::string const& body : lines)
    {
        Intent in;
        DropReason r = Parse(body, &in);
        CHECK_MSG(r == DropReason::None, body + " -> " + DropReasonName(r));
        if (r != DropReason::None)
            continue;
        CHECK_EQ(EncodeIntentBody(in), body);
        seen[static_cast<std::size_t>(in.type)] = true;
    }
    for (std::size_t i = 0; i < static_cast<std::size_t>(IntentType::Count); ++i)
        CHECK_MSG(seen[i], std::string("example for ") + IntentOpName(static_cast<IntentType>(i)));
    // a few decoded values
    Intent in;
    CHECK(Parse("1 QJOIN 6 1/1 D,389,2,4,3", &in) == DropReason::None);
    CHECK(in.type == IntentType::QueueJoin && in.queueKind == QueueKind::Dungeon && in.activityId == 389 && in.tier == 2 &&
        in.roles == RoleDamage && in.groupSize == 3 && in.seq == 6);
    CHECK(Parse("1 GET 3 1/1 SET,1,2", &in) == DropReason::None);
    CHECK(in.topics.size() == 1 && in.topics[0].topic == Topic::Set && in.topics[0].arg1 == 1 && in.topics[0].arg2 == 2);
    CHECK(Parse("1 HELLO 1 1/1 1,1.0.0,0,enUS", &in) == DropReason::None);
    CHECK(in.proto == 1 && in.addonVersion == "1.0.0" && in.dataVersion == 0 && in.locale == "enUS");
    CHECK(Parse("1 LBQ g 1/1 K,1,0,0,2", &in) == DropReason::None);
    CHECK(in.board == Board::Keys && in.seasonId == 1 && in.page == 2 && in.seq == 16);
    CHECK(Parse("1 EMOJI i 1/1 7", &in) == DropReason::None);
    CHECK(in.type == IntentType::Emoji && in.emojiId == 7 && in.seq == 18);
    CHECK(Parse("1 EMOJI i 1/1 255", &in) == DropReason::None && in.emojiId == 255);
    CHECK(Parse("1 DANCE j 1/1 5", &in) == DropReason::None);
    CHECK(in.type == IntentType::Dance && in.danceId == 5 && in.seq == 19);
    CHECK(Parse("1 DANCE j 1/1 1023", &in) == DropReason::None && in.danceId == 1023);
    CHECK(Parse("1 CASEOPEN l 1/1 990001,7", &in) == DropReason::None);
    CHECK(in.type == IntentType::CaseOpen && in.caseItemId == 990001 && in.caseNonce == 7 && in.seq == 21);
    CHECK(Parse("1 GET k 1/1 CASES;CASE,990001", &in) == DropReason::None);
    CHECK(in.topics.size() == 2 && in.topics[0].topic == Topic::Cases && in.topics[1].topic == Topic::Case &&
        in.topics[1].arg1 == 990001);
    CHECK(Parse("1 GET m 1/1 CAMPST", &in) == DropReason::None);
    CHECK(in.topics.size() == 1 && in.topics[0].topic == Topic::CampState && in.seq == 22);
    CHECK(Parse("1 CAMP n 1/1 M", &in) == DropReason::None);
    CHECK(in.type == IntentType::Camp && in.campAct == CampAct::Make && in.campSkill == 0 && in.seq == 23);
    CHECK(Parse("1 CAMP o 1/1 O,164", &in) == DropReason::None);
    CHECK(in.type == IntentType::Camp && in.campAct == CampAct::Object && in.campSkill == 164 && in.seq == 24);
    CHECK(Parse("1 CAMP p 1/1 P", &in) == DropReason::None);
    CHECK(in.type == IntentType::Camp && in.campAct == CampAct::Pack && in.campSkill == 0);
    CHECK(Parse("1 CAMP p 1/1 O,2147483647", &in) == DropReason::None && in.campSkill == 2147483647u);
    CHECK(Parse("1 GLIDE q 1/1", &in) == DropReason::None && in.type == IntentType::Glide && in.seq == 26);
    CHECK(Parse("1 REPAIR r 1/1", &in) == DropReason::None && in.type == IntentType::Repair && in.seq == 27);
    // Bleakhold Royale (section 17)
    CHECK(Parse("1 GET s 1/1 ROYS;ROYM", &in) == DropReason::None);
    CHECK(in.topics.size() == 2 && in.topics[0].topic == Topic::RoyaleState && in.topics[1].topic == Topic::RoyaleMap);
    CHECK(Parse("1 QJOIN t 1/1 B,901,0,4,1", &in) == DropReason::None);
    CHECK(in.type == IntentType::QueueJoin && in.queueKind == QueueKind::Royale && in.activityId == 901 &&
        in.tier == 0 && in.roles == RoleDamage && in.groupSize == 1 && in.seq == 29);
    CHECK(Parse("1 RDROP u 1/1 -412,96", &in) == DropReason::None);
    CHECK(in.type == IntentType::RoyaleDrop && in.dropX == -412 && in.dropY == 96 && in.seq == 30);
    CHECK(Parse("1 RDROP u 1/1 -17067,17067", &in) == DropReason::None && in.dropX == -17067 && in.dropY == 17067);
    CHECK(Parse("1 RDROP u 1/1 0,-0", &in) == DropReason::None && in.dropX == 0 && in.dropY == 0);
    CHECK_EQ(EncodeIntentBody(in), "1 RDROP u 1/1 0,0");
    CHECK(Parse("1 RDEPLOY v 1/1", &in) == DropReason::None && in.type == IntentType::RoyaleDeploy && in.seq == 31);
    CHECK(Parse("1 RSPEC w 1/1 2", &in) == DropReason::None);
    CHECK(in.type == IntentType::RoyaleSpectate && in.spectateDir == SpectateDir::Previous && in.seq == 32);
    CHECK(Parse("1 RSPEC w 1/1 0", &in) == DropReason::None && in.spectateDir == SpectateDir::Killer);
    CHECK(Parse("1 RSPEC w 1/1 1", &in) == DropReason::None && in.spectateDir == SpectateDir::Next);
    CHECK_EQ(IntentOpName(IntentType::RoyaleDeploy), "RDEPLOY");
    CHECK_EQ(TopicName(Topic::RoyaleMap), "ROYM");
    CHECK(!IsRevisioned(Topic::RoyaleState) && !IsRevisioned(Topic::RoyaleMap));
    CHECK(IsActionIntent(IntentType::RoyaleDrop) && IsActionIntent(IntentType::RoyaleDeploy) &&
        IsActionIntent(IntentType::RoyaleSpectate));
}

TEST("cases: chances add up to 10000 and the roll follows the weights")
{
    using namespace Bleakhold::Cases;
    std::vector<uint32_t> c = Chances({ 12, 12, 12, 12, 12, 12, 12, 12, 4 });
    uint32_t sum = 0;
    for (uint32_t v : c)
        sum += v;
    CHECK(sum == 10000u);
    CHECK(c[0] == 1200 || c[0] == 1201);
    CHECK(c[8] == 400u);
    c = Chances({ 1, 1, 1 });
    CHECK(c[0] + c[1] + c[2] == 10000 && c[0] == 3334 && c[1] == 3333 && c[2] == 3333);
    c = Chances({ 5, 0, 5 });
    CHECK(c[0] == 5000 && c[1] == 0 && c[2] == 5000);
    c = Chances({ 0, 0 });
    CHECK(c[0] == 0 && c[1] == 0);
    c = Chances({ 4000000000u, 4000000000u, 1 });   // big weights do not overflow
    CHECK(c[0] + c[1] + c[2] == 10000 && c[0] == 5000 && c[2] == 0);
    std::vector<uint32_t> const w = { 45, 45, 10 };
    CHECK(TotalWeight(w) == 100u);
    CHECK(Pick(w, 0) == 0u);
    CHECK(Pick(w, 44) == 0u);
    CHECK(Pick(w, 45) == 1u);
    CHECK(Pick(w, 89) == 1u);
    CHECK(Pick(w, 90) == 2u);
    CHECK(Pick(w, 99) == 2u);
    CHECK(Pick(w, 100) == 3u);                    // out of range: none
    CHECK(Pick({ 0, 3 }, 0) == 1u);               // a weight of 0 is never picked
    CHECK(Pick({}, 0) == 0u);
}

TEST("dance catalogue fits the protocol")
{
    // src/BleakholdDance.h is generated from Tools/DanceForge/dances.json (its tests compare the rest)
    CHECK(DanceCatalogueCount >= 1 && DanceCatalogueCount <= MaxDances);
    std::set<std::string> keys;
    for (uint32_t i = 0; i < DanceCatalogueCount; ++i)
    {
        std::string const k = DanceCatalogueKeys[i];
        bool ok = !k.empty() && k[0] >= 'a' && k[0] <= 'z' && k.size() <= 32;
        for (char c : k)
            ok = ok && ((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '_');
        CHECK_MSG(ok, "dance key [" + k + "]");
        CHECK_MSG(keys.insert(k).second, "dance key " + k + " is unique");
        CHECK_MSG(DanceLoopMs[i] >= 1000 && DanceLoopMs[i] <= 60000, "dance loop of " + k);
    }
    CHECK_EQ(DanceCatalogueKeys[0], "string_swing");
    Intent in;
    CHECK(Parse("1 DANCE i 1/1 " + std::to_string(DanceCatalogueCount - 1), &in) == DropReason::None &&
        in.danceId == DanceCatalogueCount - 1);
}

TEST("emoji catalogue fits the protocol")
{
    // src/BleakholdEmoji.h is generated from Tools/EmojiForge/emojis.json (its tests compare the rest)
    CHECK(EmojiCatalogueCount >= 1 && EmojiCatalogueCount <= MaxEmojis);
    std::set<std::string> keys;
    for (uint32_t i = 0; i < EmojiCatalogueCount; ++i)
    {
        std::string const k = EmojiCatalogueKeys[i];
        bool ok = !k.empty() && k[0] >= 'a' && k[0] <= 'z';
        for (char c : k)
            ok = ok && ((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '_');
        CHECK_MSG(ok, "emoji key [" + k + "]");
        CHECK_MSG(keys.insert(k).second, "emoji key " + k + " is unique");
    }
    CHECK_EQ(EmojiCatalogueKeys[0], "joy");
    // the last id fits the wire field
    Intent in;
    CHECK(Parse("1 EMOJI i 1/1 " + std::to_string(EmojiCatalogueCount - 1), &in) == DropReason::None &&
        uint32_t(in.emojiId) == EmojiCatalogueCount - 1);
}

TEST("malformed client messages are dropped with the right reason")
{
    struct Bad { std::string text; DropReason why; };
    std::vector<Bad> const bad = {
        { "BHs\t1 WEEK 1 1/1 1", DropReason::ServerPrefix },
        { "BHs", DropReason::ServerPrefix },
        { "AzerothCore\t1 X", DropReason::NotBleakhold },
        { "BHcx\t1 PING 1 1/1 1", DropReason::NotBleakhold },
        { "BHc", DropReason::BadHeader },
        { "BHc\t", DropReason::BadHeader },
        { "BHc\t1 PING 1 1/1 " + std::string(240, '1'), DropReason::TooLong },
        { std::string("BHc\t1 PING 1 1/1 1\0", 19), DropReason::Nul },
        { "BHc\t1 PING 1 1/1 1\t2", DropReason::BadField },
        { "BHc\t1 ping 1 1/1 1", DropReason::BadHeader },
        { "BHc\t1 P 1 1/1 1", DropReason::BadHeader },
        { "BHc\t1 PINGPONG 1 1/1 1", DropReason::UnknownOp },
        { "BHc\t1 PINGPONGS 1 1/1 1", DropReason::BadHeader },
        { "BHc\t1  PING 1 1/1 1", DropReason::BadHeader },
        { "BHc\t1 PING 1 1/1,1", DropReason::BadHeader },
        { "BHc\t1 PING A 1/1 1", DropReason::BadHeader },
        { "BHc\t1 PING 1234567 1/1 1", DropReason::BadHeader },
        { "BHc\t1 PING 1 0/1 1", DropReason::BadHeader },
        { "BHc\t1 PING 1 2/1 1", DropReason::BadHeader },
        { "BHc\t1 PING 1 1/100 1", DropReason::BadHeader },
        { "BHc\t1 PING 1 1/2 1", DropReason::Chunked },
        { "BHc\t1234 PING 1 1/1 1", DropReason::BadHeader },
        { "BHc\t2 PING 1 1/1 1", DropReason::Version },
        { "BHc\t0 PING 1 1/1 1", DropReason::Version },
        { "BHc\t1 SCORE 1 1/1 999", DropReason::UnknownOp },
        { "BHc\t1 MPE 1 1/1 1,1", DropReason::UnknownOp },
        { "BHc\t1 TCLAIM 1 1/1", DropReason::FieldCount },
        { "BHc\t1 TCLAIM 1 1/1 1,2", DropReason::FieldCount },
        { "BHc\t1 TCLAIM 1 1/1 1;2", DropReason::FieldCount },
        { "BHc\t1 TCLAIM 1 1/1 x", DropReason::BadField },
        { "BHc\t1 TCLAIM 1 1/1 1.5", DropReason::BadField },
        { "BHc\t1 TCLAIM 1 1/1 1e5", DropReason::BadField },
        { "BHc\t1 TCLAIM 1 1/1 0x10", DropReason::BadField },
        { "BHc\t1 TCLAIM 1 1/1 +5", DropReason::BadField },
        { "BHc\t1 TCLAIM 1 1/1  5", DropReason::BadField },
        { "BHc\t1 TCLAIM 1 1/1 5 ", DropReason::BadField },
        { "BHc\t1 TCLAIM 1 1/1 nan", DropReason::BadField },
        { "BHc\t1 TCLAIM 1 1/1 %31", DropReason::BadField },
        { "BHc\t1 TCLAIM 1 1/1 0", DropReason::OutOfRange },
        { "BHc\t1 TCLAIM 1 1/1 -1", DropReason::OutOfRange },
        { "BHc\t1 TCLAIM 1 1/1 2147483648", DropReason::OutOfRange },
        { "BHc\t1 TCLAIM 1 1/1 9999999999999999", DropReason::BadField },
        { "BHc\t1 QJOIN 1 1/1 X,1,0,4,5", DropReason::BadField },
        { "BHc\t1 QJOIN 1 1/1 DD,1,0,4,5", DropReason::BadField },
        { "BHc\t1 QJOIN 1 1/1 D,1,4,4,5", DropReason::OutOfRange },
        { "BHc\t1 QJOIN 1 1/1 D,1,0,0,5", DropReason::OutOfRange },
        { "BHc\t1 QJOIN 1 1/1 D,1,0,8,5", DropReason::OutOfRange },
        { "BHc\t1 QJOIN 1 1/1 D,1,0,4,6", DropReason::OutOfRange },
        { "BHc\t1 QJOIN 1 1/1 D,1,0,4,0", DropReason::OutOfRange },
        { "BHc\t1 QJOIN 1 1/1 D,0,0,4,5", DropReason::OutOfRange },
        { "BHc\t1 QJOIN 1 1/1 R,5,0,4,1", DropReason::OutOfRange },
        { "BHc\t1 QJOIN 1 1/1 D,1,0,4", DropReason::FieldCount },
        { "BHc\t1 QREPLY 1 1/1 77,2", DropReason::OutOfRange },
        { "BHc\t1 QREPLY 1 1/1 0,1", DropReason::OutOfRange },
        { "BHc\t1 QLEAVE 1 1/1 1", DropReason::FieldCount },
        { "BHc\t1 QLEAVE 1 1/1  ", DropReason::FieldCount },
        { "BHc\t1 KMODE 1 1/1 3", DropReason::OutOfRange },
        { "BHc\t1 KSTART 1 1/1 1", DropReason::FieldCount },
        { "BHc\t1 LBQ 1 1/1 X,1,0,0,1", DropReason::BadField },
        { "BHc\t1 LBQ 1 1/1 K,1,0,0,0", DropReason::OutOfRange },
        { "BHc\t1 LBQ 1 1/1 K,1,0,0,1000", DropReason::OutOfRange },
        { "BHc\t1 EMOJI 1 1/1 256", DropReason::OutOfRange },
        { "BHc\t1 EMOJI 1 1/1 -1", DropReason::OutOfRange },
        { "BHc\t1 EMOJI 1 1/1", DropReason::FieldCount },
        { "BHc\t1 EMOJI 1 1/1 1,2", DropReason::FieldCount },
        { "BHc\t1 EMOJI 1 1/1 x", DropReason::BadField },
        { "BHc\t1 DANCE 1 1/1 1024", DropReason::OutOfRange },
        { "BHc\t1 DANCE 1 1/1 -1", DropReason::OutOfRange },
        { "BHc\t1 DANCE 1 1/1", DropReason::FieldCount },
        { "BHc\t1 DANCE 1 1/1 1,2", DropReason::FieldCount },
        { "BHc\t1 DANCE 1 1/1 a", DropReason::BadField },
        { "BHc\t1 CASEOPEN 1 1/1 0,1", DropReason::OutOfRange },
        { "BHc\t1 CASEOPEN 1 1/1 2147483648,1", DropReason::OutOfRange },
        { "BHc\t1 CASEOPEN 1 1/1 1,2147483648", DropReason::OutOfRange },
        { "BHc\t1 CASEOPEN 1 1/1 1,-1", DropReason::OutOfRange },
        { "BHc\t1 CASEOPEN 1 1/1", DropReason::FieldCount },
        { "BHc\t1 CASEOPEN 1 1/1 1", DropReason::FieldCount },
        { "BHc\t1 CASEOPEN 1 1/1 1,2,3", DropReason::FieldCount },
        { "BHc\t1 CASEOPEN 1 1/1 x,1", DropReason::BadField },
        { "BHc\t1 GET 1 1/1 CASE", DropReason::BadTopic },
        { "BHc\t1 GET 1 1/1 CASE,0", DropReason::OutOfRange },
        { "BHc\t1 GET 1 1/1 CASES,1", DropReason::BadTopic },
        { "BHc\t1 GET 1 1/1 CAMPST,1", DropReason::BadTopic },
        { "BHc\t1 GET 1 1/1 CAMPSTATE", DropReason::BadTopic },
        { "BHc\t1 CAMP 1 1/1", DropReason::FieldCount },
        { "BHc\t1 CAMP 1 1/1 O", DropReason::FieldCount },
        { "BHc\t1 CAMP 1 1/1 M,0", DropReason::FieldCount },
        { "BHc\t1 CAMP 1 1/1 P,164", DropReason::FieldCount },
        { "BHc\t1 CAMP 1 1/1 O,164,1", DropReason::FieldCount },
        { "BHc\t1 CAMP 1 1/1 M;P", DropReason::FieldCount },
        { "BHc\t1 CAMP 1 1/1 X", DropReason::BadField },
        { "BHc\t1 CAMP 1 1/1 m", DropReason::BadField },
        { "BHc\t1 CAMP 1 1/1 MP", DropReason::BadField },
        { "BHc\t1 CAMP 1 1/1 1", DropReason::BadField },
        { "BHc\t1 CAMP 1 1/1 X,1", DropReason::FieldCount },
        { "BHc\t1 CAMP 1 1/1 O,0", DropReason::OutOfRange },
        { "BHc\t1 CAMP 1 1/1 O,-1", DropReason::OutOfRange },
        { "BHc\t1 CAMP 1 1/1 O,2147483648", DropReason::OutOfRange },
        { "BHc\t1 CAMP 1 1/1 O,x", DropReason::BadField },
        { "BHc\t1 CAMP 1 1/1 O,", DropReason::BadField },
        { "BHc\t1 GLIDE 1 1/1 1", DropReason::FieldCount },
        { "BHc\t1 REPAIR 1 1/1 0", DropReason::FieldCount },
        { "BHc\t1 REPAIRS 1 1/1", DropReason::UnknownOp },
        { "BHc\t1 HELLO 1 1/1 1,1.0 beta,0,enUS", DropReason::BadField },
        { "BHc\t1 HELLO 1 1/1 1,,0,enUS", DropReason::BadField },
        { "BHc\t1 HELLO 1 1/1 1,1.0.0,0,enUSenUSx", DropReason::BadField },
        { "BHc\t1 HELLO 1 1/1 1,12345678901234567,0,enUS", DropReason::BadField },
        { "BHc\t1 HELLO 1 1/1 0,1.0.0,0,enUS", DropReason::OutOfRange },
        { "BHc\t1 HELLO 1 1/1 1,1.0.0,0", DropReason::FieldCount },
        { "BHc\t1 GET 1 1/1", DropReason::FieldCount },
        { "BHc\t1 GET 1 1/1 WEEK;", DropReason::FieldCount },
        { "BHc\t1 GET 1 1/1 WEEK;;ERA", DropReason::FieldCount },
        { "BHc\t1 GET 1 1/1 WEEK;ERA;TASKS;KEY;BOARD;QUEUE;COLL;LIDX;SEASON", DropReason::FieldCount },
        { "BHc\t1 GET 1 1/1 SECRETS", DropReason::BadTopic },
        { "BHc\t1 GET 1 1/1 week", DropReason::BadTopic },
        { "BHc\t1 GET 1 1/1 WEEK,1", DropReason::BadTopic },
        { "BHc\t1 GET 1 1/1 SET,1", DropReason::BadTopic },
        { "BHc\t1 GET 1 1/1 SET,1,2,3", DropReason::BadTopic },
        { "BHc\t1 GET 1 1/1 SET,1,x", DropReason::BadField },
        { "BHc\t1 GET 1 1/1 DEF", DropReason::BadTopic },
        { "BHc\t1 GET 1 1/1 DEF,1", DropReason::OutOfRange },
        // Bleakhold Royale (section 17)
        { "BHc\t1 QJOIN 1 1/1 B,0,0,4,1", DropReason::OutOfRange },        // the mode id is never 0
        { "BHc\t1 QJOIN 1 1/1 B,901,1,4,1", DropReason::OutOfRange },      // no tiers
        { "BHc\t1 QJOIN 1 1/1 B,901,0,4,2", DropReason::OutOfRange },      // solo
        { "BHc\t1 QJOIN 1 1/1 B,901,0,0,1", DropReason::OutOfRange },
        { "BHc\t1 QJOIN 1 1/1 B,901,0,4", DropReason::FieldCount },
        { "BHc\t1 QJOIN 1 1/1 b,901,0,4,1", DropReason::BadField },
        { "BHc\t1 QJOIN 1 1/1 BR,901,0,4,1", DropReason::BadField },
        { "BHc\t1 RDROP 1 1/1", DropReason::FieldCount },
        { "BHc\t1 RDROP 1 1/1 104", DropReason::FieldCount },
        { "BHc\t1 RDROP 1 1/1 104,96,1", DropReason::FieldCount },
        { "BHc\t1 RDROP 1 1/1 104;96", DropReason::FieldCount },
        { "BHc\t1 RDROP 1 1/1 104,", DropReason::BadField },
        { "BHc\t1 RDROP 1 1/1 ,96", DropReason::BadField },
        { "BHc\t1 RDROP 1 1/1 104.5,96", DropReason::BadField },
        { "BHc\t1 RDROP 1 1/1 +104,96", DropReason::BadField },
        { "BHc\t1 RDROP 1 1/1 --104,96", DropReason::BadField },
        { "BHc\t1 RDROP 1 1/1 -,96", DropReason::BadField },
        { "BHc\t1 RDROP 1 1/1 17068,96", DropReason::OutOfRange },
        { "BHc\t1 RDROP 1 1/1 104,-17068", DropReason::OutOfRange },
        { "BHc\t1 RDROP 1 1/1 -2147483649,0", DropReason::OutOfRange },
        { "BHc\t1 RDROP 1 1/1 -9999999999999999,0", DropReason::BadField },
        { "BHc\t1 RDEPLOY 1 1/1 1", DropReason::FieldCount },
        { "BHc\t1 RDEPLOY 1 1/1 ,", DropReason::FieldCount },
        { "BHc\t1 RDEPLOYS 1 1/1", DropReason::UnknownOp },
        { "BHc\t1 RSPEC 1 1/1", DropReason::FieldCount },
        { "BHc\t1 RSPEC 1 1/1 1,2", DropReason::FieldCount },
        { "BHc\t1 RSPEC 1 1/1 3", DropReason::OutOfRange },
        { "BHc\t1 RSPEC 1 1/1 -1", DropReason::OutOfRange },
        { "BHc\t1 RSPEC 1 1/1 N", DropReason::BadField },
        { "BHc\t1 GET 1 1/1 ROYS,1", DropReason::BadTopic },
        { "BHc\t1 GET 1 1/1 ROYM,0", DropReason::BadTopic },
        { "BHc\t1 GET 1 1/1 ROYO", DropReason::BadTopic },
        { "BHc\t1 GET 1 1/1 ROYE", DropReason::BadTopic },
    };
    for (Bad const& b : bad)
    {
        Intent in;
        DropReason r = ParseClientMessage(b.text, in);
        CHECK_MSG(r == b.why, bhtest::Show(b.text) + ": got " + DropReasonName(r) + ", expected " + DropReasonName(b.why));
    }
    // accepted edge cases (the document allows them)
    CHECK(Parse("1 QLEAVE 9 1/1 ") == DropReason::None);           // trailing space with an empty payload
    CHECK(Parse("2 HELLO 1 1/1 2,2.0.0,0,enUS") == DropReason::None); // HELLO of another version is read
    Intent in;
    CHECK(Parse("1 PING 1 1/1 007", &in) == DropReason::None && in.nonce == 7);
    CHECK(Parse("1 PING 01 01/01 5", &in) == DropReason::None && in.seq == 1);
    CHECK(Parse("1 GET zzzzzz 1/1 WEEK;WEEK", &in) == DropReason::None && in.seq == SeqModulo - 1 && in.topics.size() == 2);
    CHECK(Parse("1 GET 8 1/1 WEEK;ERA;TASKS;KEY;BOARD;QUEUE;COLL;DEF,0") == DropReason::None);
    CHECK(Parse("1 TCLAIM 1 1/1 2147483647", &in) == DropReason::None && in.taskUid == 2147483647u);
    std::string const max = "1 PING zzzzzz 1/1 " + std::string(MaxClientBody - 18, '0');
    CHECK_EQN(max.size(), MaxClientBody);
    CHECK(Parse(max) == DropReason::BadField);   // 233 digits: not a number, but not too long either
}

// ---------------------------------------------------------------------------------------------------
// Endpoint: handshake, rate limits, duplicates, SEQ and revisions
// ---------------------------------------------------------------------------------------------------
static ReceiveResult Feed(Endpoint& ep, std::string const& body, uint64_t t, Intent* out = nullptr)
{
    Intent tmp;
    ReceiveResult r = ep.Receive(Chat(body), t, tmp);
    if (out)
        *out = tmp;
    return r;
}

TEST("endpoint: nothing but HELLO before the handshake")
{
    Endpoint ep;
    CHECK(!ep.Ready());
    CHECK(Feed(ep, "1 GET 1 1/1 WEEK", 1000).reason == DropReason::NoHello);
    CHECK(Feed(ep, "1 TCLAIM 2 1/1 5", 1100).reason == DropReason::NoHello);
    Intent scratch;
    CHECK(ep.Receive("hello there", 1200, scratch).verdict == Verdict::NotOurs);
    ReceiveResult h = Feed(ep, "1 HELLO 3 1/1 1,1.0.0,0,enUS", 1300);
    CHECK(h.verdict == Verdict::Accepted && ep.Ready());
    CHECK(Feed(ep, "1 GET 4 1/1 WEEK", 1400).verdict == Verdict::Accepted);
    CHECK_EQ(ep.Hello().locale, "enUS");
}

TEST("endpoint: token bucket of 10 refilled at 5 per second")
{
    Limits l;
    l.duplicateWindowMs = 0;
    Endpoint ep(l);
    Feed(ep, "1 HELLO 1 1/1 1,1.0.0,0,enUS", 0);
    int ok = 0;
    for (int i = 0; i < 20; ++i)
        if (Feed(ep, "1 PING " + Base36(uint32_t(i + 2)) + " 1/1 1", 0).verdict == Verdict::Accepted)
            ++ok;
    CHECK_EQN(ok, 9);   // 10 tokens, HELLO took one
    CHECK_EQN(ep.Stats().dropped[static_cast<std::size_t>(DropReason::Flood)], 11u);
    ok = 0;
    for (int i = 0; i < 20; ++i)
        if (Feed(ep, "1 PING 1 1/1 1", 1000).verdict == Verdict::Accepted)
            ++ok;
    CHECK_EQN(ok, 5);   // one second refills five
    ok = 0;
    for (int t = 2000; t < 12000; t += 100)   // 10 per second offered for 10 s
        if (Feed(ep, "1 PING 1 1/1 1", uint64_t(t)).verdict == Verdict::Accepted)
            ++ok;
    CHECK(ok >= 54 && ok <= 56);   // 5 left from the last second + 5 per second for 10 s
}

TEST("endpoint: 200 drops within a minute mute the player for 60 s")
{
    Endpoint ep;
    Feed(ep, "1 HELLO 1 1/1 1,1.0.0,0,enUS", 0);
    bool muted = false;
    int sent = 0;
    for (uint64_t t = 0; t < 30000 && !muted; t += 10, ++sent)
        muted = Feed(ep, "1 PING 1 1/1 x", t).muteStarted;   // malformed: every one is a drop
    CHECK(muted);
    CHECK(sent >= 200 && sent < 260);
    CHECK(Feed(ep, "1 PING 1 1/1 1", 40000).reason == DropReason::Muted);
    CHECK(Feed(ep, "1 PING 1 1/1 1", 95000).verdict == Verdict::Accepted);
    CHECK_EQN(ep.Stats().mutes, 1u);
}

TEST("endpoint: per-op limits of section 8")
{
    Limits l;
    l.duplicateWindowMs = 0;
    Endpoint ep(l);
    Feed(ep, "1 HELLO 1 1/1 1,1.0.0,0,enUS", 0);
    // HELLO 1 per 5 s
    CHECK(Feed(ep, "1 HELLO 2 1/1 1,1.0.0,0,enUS", 1000).reason == DropReason::Throttled);
    CHECK(Feed(ep, "1 HELLO 3 1/1 1,1.0.0,0,enUS", 5000).verdict == Verdict::Accepted);
    // GET: each topic once per second, SET per (tier, class)
    Intent in;
    CHECK(Feed(ep, "1 GET 4 1/1 WEEK;ERA", 6000, &in).verdict == Verdict::Accepted && in.topics.size() == 2);
    CHECK(Feed(ep, "1 GET 5 1/1 WEEK;KEY", 6100, &in).verdict == Verdict::Accepted && in.topics.size() == 1 && in.topics[0].topic == Topic::Key);
    CHECK(Feed(ep, "1 GET 6 1/1 WEEK;ERA", 6200).reason == DropReason::Throttled);
    CHECK(Feed(ep, "1 GET 7 1/1 WEEK", 7000).verdict == Verdict::Accepted);
    CHECK(Feed(ep, "1 GET 8 1/1 SET,1,1;SET,1,2", 7100, &in).verdict == Verdict::Accepted && in.topics.size() == 2);
    CHECK(Feed(ep, "1 GET 9 1/1 SET,1,1", 7200).reason == DropReason::Throttled);
    // large answers: DEF, LIDX, BOARD at most every 5 s (a new HELLO resets it)
    CHECK(Feed(ep, "1 GET 9 1/1 DEF,0;LIDX;BOARD", 7300, &in).verdict == Verdict::Accepted && in.topics.size() == 3);
    CHECK(Feed(ep, "1 GET 9 1/1 DEF,0;LIDX;BOARD", 8400).reason == DropReason::Throttled);
    CHECK(Feed(ep, "1 GET 9 1/1 DEF,0;LIDX;BOARD", 12300, &in).verdict == Verdict::Accepted && in.topics.size() == 3);
    // LBQ 2 per second
    CHECK(Feed(ep, "1 LBQ a 1/1 K,1,0,0,1", 9000).verdict == Verdict::Accepted);
    CHECK(Feed(ep, "1 LBQ b 1/1 K,1,0,0,2", 9100).verdict == Verdict::Accepted);
    ReceiveResult r = Feed(ep, "1 LBQ c 1/1 K,1,0,0,3", 9200, &in);
    CHECK(r.verdict == Verdict::Refused && in.type == IntentType::LeaderboardQuery && in.seq == 12);
    // QJOIN / QLEAVE / QREPLY: 1 per second each
    CHECK(Feed(ep, "1 QJOIN d 1/1 D,389,2,4,3", 11000).verdict == Verdict::Accepted);
    CHECK(Feed(ep, "1 QLEAVE e 1/1", 11100).verdict == Verdict::Accepted);
    CHECK(Feed(ep, "1 QJOIN f 1/1 D,389,1,4,3", 11200).verdict == Verdict::Refused);
    CHECK(Feed(ep, "1 QJOIN g 1/1 D,389,1,4,3", 12100).verdict == Verdict::Accepted);
    // KMODE / KSTART / KCANCEL: 1 per 2 s each
    CHECK(Feed(ep, "1 KMODE h 1/1 2", 14000).verdict == Verdict::Accepted);
    CHECK(Feed(ep, "1 KMODE i 1/1 1", 15000).verdict == Verdict::Refused);
    CHECK(Feed(ep, "1 KSTART j 1/1", 15100).verdict == Verdict::Accepted);
    CHECK(Feed(ep, "1 KMODE k 1/1 1", 16100).verdict == Verdict::Accepted);
    // claims: 2 per second together
    CHECK(Feed(ep, "1 TCLAIM l 1/1 1", 20000).verdict == Verdict::Accepted);
    CHECK(Feed(ep, "1 BCLAIM m 1/1 2", 20100).verdict == Verdict::Accepted);
    CHECK(Feed(ep, "1 OUTFIT n 1/1 3", 20200).verdict == Verdict::Refused);
    CHECK(Feed(ep, "1 WEHANDIN o 1/1", 20700).verdict == Verdict::Accepted);
    // EMOJI: 1 per 2.5 s (at 24500 the bucket holds exactly one token again)
    CHECK(Feed(ep, "1 EMOJI p 1/1 1", 22000).verdict == Verdict::Accepted);
    ReceiveResult e = Feed(ep, "1 EMOJI q 1/1 2", 23000, &in);
    CHECK(e.verdict == Verdict::Refused && in.type == IntentType::Emoji && in.emojiId == 2);
    CHECK(Feed(ep, "1 EMOJI r 1/1 2", 24600).verdict == Verdict::Accepted);
    // DANCE: 1 per second
    CHECK(Feed(ep, "1 DANCE s 1/1 1", 30000).verdict == Verdict::Accepted);
    ReceiveResult dn = Feed(ep, "1 DANCE t 1/1 2", 30500, &in);
    CHECK(dn.verdict == Verdict::Refused && in.type == IntentType::Dance && in.danceId == 2);
    CHECK(Feed(ep, "1 DANCE u 1/1 2", 31100).verdict == Verdict::Accepted);
    // CASEOPEN: 1 per second
    CHECK(Feed(ep, "1 CASEOPEN v 1/1 990001,1", 40000).verdict == Verdict::Accepted);
    ReceiveResult cs = Feed(ep, "1 CASEOPEN w 1/1 990002,2", 40500, &in);
    CHECK(cs.verdict == Verdict::Refused && in.type == IntentType::CaseOpen && in.caseItemId == 990002);
    CHECK(Feed(ep, "1 CASEOPEN x 1/1 990002,3", 41100).verdict == Verdict::Accepted);
    // CAMP: 1 per second, every act together
    CHECK(Feed(ep, "1 CAMP y 1/1 M", 50000).verdict == Verdict::Accepted);
    ReceiveResult cp = Feed(ep, "1 CAMP z 1/1 O,164", 50500, &in);
    CHECK(cp.verdict == Verdict::Refused && in.type == IntentType::Camp && in.campAct == CampAct::Object && in.campSkill == 164);
    CHECK(Feed(ep, "1 CAMP 10 1/1 O,164", 51100).verdict == Verdict::Accepted);
    CHECK(Feed(ep, "1 CAMP 11 1/1 P", 51600).verdict == Verdict::Refused);
    // GLIDE: 1 per second (another op's bucket is not touched)
    CHECK(Feed(ep, "1 GLIDE 12 1/1", 51700).verdict == Verdict::Accepted);
    CHECK(Feed(ep, "1 GLIDE 13 1/1", 53000).verdict == Verdict::Accepted);
    // REPAIR: 1 per 2 s (the duplicate guard drops a repeat within 1 s; after it the bucket answers busy)
    CHECK(Feed(ep, "1 REPAIR 14 1/1", 60000).verdict == Verdict::Accepted);
    ReceiveResult rp = Feed(ep, "1 REPAIR 15 1/1", 61500, &in);
    CHECK(rp.verdict == Verdict::Refused && in.type == IntentType::Repair);
    CHECK(Feed(ep, "1 REPAIR 16 1/1", 62100).verdict == Verdict::Accepted);
    // RDROP and RSPEC: 1 per 0.5 s each (2 per second); RDEPLOY: 1 per second (section 17)
    CHECK(Feed(ep, "1 RDROP 17 1/1 104,96", 70000).verdict == Verdict::Accepted);
    ReceiveResult rd = Feed(ep, "1 RDROP 18 1/1 -50,-60", 70300, &in);
    CHECK(rd.verdict == Verdict::Refused && in.type == IntentType::RoyaleDrop && in.dropX == -50 && in.dropY == -60);
    CHECK(Feed(ep, "1 RDROP 19 1/1 -50,-60", 70550).verdict == Verdict::Accepted);
    CHECK(Feed(ep, "1 RSPEC 1a 1/1 1", 70560).verdict == Verdict::Accepted);   // its own bucket
    CHECK(Feed(ep, "1 RSPEC 1b 1/1 2", 70900).verdict == Verdict::Refused);
    CHECK(Feed(ep, "1 RSPEC 1c 1/1 2", 71100).verdict == Verdict::Accepted);
    CHECK(Feed(ep, "1 RDEPLOY 1d 1/1", 71110).verdict == Verdict::Accepted);
    ReceiveResult dp = Feed(ep, "1 RDEPLOY 1e 1/1", 71800, &in);
    CHECK(dp.verdict == Verdict::Refused && in.type == IntentType::RoyaleDeploy);
    CHECK(Feed(ep, "1 RDEPLOY 1f 1/1", 72200).verdict == Verdict::Accepted);
    // QJOIN B shares the QJOIN bucket
    CHECK(Feed(ep, "1 QJOIN 1g 1/1 B,901,0,4,1", 80000).verdict == Verdict::Accepted);
    CHECK(Feed(ep, "1 QJOIN 1h 1/1 D,389,1,4,3", 80500).verdict == Verdict::Refused);
    // GET ROYS and ROYM: each topic once per second
    CHECK(Feed(ep, "1 GET 1i 1/1 ROYS;ROYM", 81000, &in).verdict == Verdict::Accepted && in.topics.size() == 2);
    CHECK(Feed(ep, "1 GET 1j 1/1 ROYS", 81500).reason == DropReason::Throttled);
    CHECK(Feed(ep, "1 GET 1k 1/1 ROYS", 82000).verdict == Verdict::Accepted);
}

TEST("endpoint: the Bleakhold Royale limits come from Limits")
{
    Limits l;
    l.duplicateWindowMs = 0;
    l.royaleIntervalMs = 2000;
    l.royaleDeployIntervalMs = 0;   // 0: no limit of its own
    Endpoint ep(l);
    Feed(ep, "1 HELLO 1 1/1 1,1.0.0,0,enUS", 0);
    CHECK(Feed(ep, "1 RDROP 2 1/1 1,1", 1000).verdict == Verdict::Accepted);
    CHECK(Feed(ep, "1 RDROP 3 1/1 2,2", 2500).verdict == Verdict::Refused);
    CHECK(Feed(ep, "1 RDROP 4 1/1 2,2", 3100).verdict == Verdict::Accepted);
    CHECK(Feed(ep, "1 RSPEC 5 1/1 1", 3200).verdict == Verdict::Accepted);
    CHECK(Feed(ep, "1 RSPEC 6 1/1 1", 4000).verdict == Verdict::Refused);
    CHECK(Feed(ep, "1 RDEPLOY 7 1/1", 5000).verdict == Verdict::Accepted);
    CHECK(Feed(ep, "1 RDEPLOY 8 1/1", 5001).verdict == Verdict::Accepted);
}

TEST("endpoint: the camping limits come from Limits")
{
    Limits l;
    l.duplicateWindowMs = 0;
    l.campIntervalMs = 5000;
    l.glideIntervalMs = 3000;
    l.repairIntervalMs = 0;   // 0: no limit of its own
    Endpoint ep(l);
    Feed(ep, "1 HELLO 1 1/1 1,1.0.0,0,enUS", 0);
    CHECK(Feed(ep, "1 CAMP 2 1/1 M", 1000).verdict == Verdict::Accepted);
    CHECK(Feed(ep, "1 CAMP 3 1/1 P", 4000).verdict == Verdict::Refused);
    CHECK(Feed(ep, "1 CAMP 4 1/1 P", 6100).verdict == Verdict::Accepted);
    CHECK(Feed(ep, "1 GLIDE 5 1/1", 7000).verdict == Verdict::Accepted);
    CHECK(Feed(ep, "1 GLIDE 6 1/1", 9000).verdict == Verdict::Refused);
    CHECK(Feed(ep, "1 GLIDE 7 1/1", 10100).verdict == Verdict::Accepted);
    CHECK(Feed(ep, "1 REPAIR 8 1/1", 11000).verdict == Verdict::Accepted);
    CHECK(Feed(ep, "1 REPAIR 9 1/1", 11001).verdict == Verdict::Accepted);
}

TEST("endpoint: the same action twice within the window is ignored")
{
    Endpoint ep;
    Feed(ep, "1 HELLO 1 1/1 1,1.0.0,0,enUS", 0);
    CHECK(Feed(ep, "1 TCLAIM 2 1/1 103", 1000).verdict == Verdict::Accepted);
    CHECK(Feed(ep, "1 TCLAIM 3 1/1 103", 1600).reason == DropReason::Duplicate);
    CHECK(Feed(ep, "1 TCLAIM 4 1/1 104", 1700).verdict == Verdict::Accepted);
    CHECK(Feed(ep, "1 TCLAIM 5 1/1 103", 3000).verdict == Verdict::Accepted);   // window over: the handler decides
    CHECK(Feed(ep, "1 KMODE 6 1/1 2", 4000).verdict == Verdict::Accepted);
    CHECK(Feed(ep, "1 KMODE 7 1/1 0", 6500).verdict == Verdict::Accepted);
    CHECK(Feed(ep, "1 KMODE 8 1/1 2", 9000).verdict == Verdict::Accepted);      // not the same as the last one
    // EMOJI: the same id is dropped before the cooldown answers "busy" (section 13)
    CHECK(Feed(ep, "1 EMOJI 9 1/1 7", 10000).verdict == Verdict::Accepted);
    CHECK(Feed(ep, "1 EMOJI a 1/1 7", 10500).reason == DropReason::Duplicate);
    CHECK(Feed(ep, "1 EMOJI b 1/1 8", 10600).verdict == Verdict::Refused);
    // DANCE: the same dance again at once is dropped too
    CHECK(Feed(ep, "1 DANCE c 1/1 3", 20000).verdict == Verdict::Accepted);
    CHECK(Feed(ep, "1 DANCE d 1/1 3", 20400).reason == DropReason::Duplicate);
    // CASEOPEN: the same request again at once is dropped too; a new one (another nonce) is not (section 15)
    CHECK(Feed(ep, "1 CASEOPEN e 1/1 990001,5", 30000).verdict == Verdict::Accepted);
    CHECK(Feed(ep, "1 CASEOPEN f 1/1 990001,5", 30400).reason == DropReason::Duplicate);
    CHECK(Feed(ep, "1 CASEOPEN g 1/1 990001,6", 31500).verdict == Verdict::Accepted);
    // CAMP: the same act again at once is dropped; another act is a new request (and meets the rate limit)
    CHECK(Feed(ep, "1 CAMP h 1/1 M", 40000).verdict == Verdict::Accepted);
    CHECK(Feed(ep, "1 CAMP i 1/1 M", 40300).reason == DropReason::Duplicate);
    CHECK(Feed(ep, "1 CAMP j 1/1 O,164", 40400).verdict == Verdict::Refused);
    CHECK(Feed(ep, "1 CAMP k 1/1 O,164", 41500).verdict == Verdict::Accepted);
    CHECK(Feed(ep, "1 CAMP l 1/1 O,164", 41900).reason == DropReason::Duplicate);
    CHECK(Feed(ep, "1 CAMP m 1/1 O,171", 42600).verdict == Verdict::Accepted);
    // GLIDE and REPAIR have no fields: any repeat within the window is a duplicate
    CHECK(Feed(ep, "1 GLIDE n 1/1", 50000).verdict == Verdict::Accepted);
    CHECK(Feed(ep, "1 GLIDE o 1/1", 50900).reason == DropReason::Duplicate);
    CHECK(Feed(ep, "1 REPAIR p 1/1", 50950).verdict == Verdict::Accepted);
    CHECK(Feed(ep, "1 REPAIR q 1/1", 51000).reason == DropReason::Duplicate);
    // RDROP: the same pin again at once is dropped, another pin meets the rate limit (section 17)
    CHECK(Feed(ep, "1 RDROP r 1/1 104,96", 60000).verdict == Verdict::Accepted);
    CHECK(Feed(ep, "1 RDROP s 1/1 104,96", 60800).reason == DropReason::Duplicate);
    CHECK(Feed(ep, "1 RDROP t 1/1 104,97", 61300).verdict == Verdict::Accepted);
    // RDEPLOY has no fields: a repeat within the window is a duplicate
    CHECK(Feed(ep, "1 RDEPLOY u 1/1", 62000).verdict == Verdict::Accepted);
    CHECK(Feed(ep, "1 RDEPLOY v 1/1", 62900).reason == DropReason::Duplicate);
    // RSPEC "next" twice is two steps: never a duplicate, only its rate limit holds
    CHECK(Feed(ep, "1 RSPEC w 1/1 1", 70000).verdict == Verdict::Accepted);
    CHECK(Feed(ep, "1 RSPEC x 1/1 1", 70600).verdict == Verdict::Accepted);
    CHECK(Feed(ep, "1 RSPEC y 1/1 1", 70700).verdict == Verdict::Refused);
}

// ---------------------------------------------------------------------------------------------------
// Camping (section 16): the core-independent rules of src/BleakholdCampRules.h and the CAMPST encoder
// ---------------------------------------------------------------------------------------------------
TEST("camping: tiers, id lists, XP bonus, repair rules")
{
    using namespace Bleakhold::CampRules;
    Tiers const t = DefaultTierSkill;
    CHECK(TierFor(0, t) == 0 && TierFor(74, t) == 0 && TierFor(75, t) == 1 && TierFor(224, t) == 1 && TierFor(225, t) == 2 &&
        TierFor(374, t) == 2 && TierFor(375, t) == 3 && TierFor(450, t) == 3 && TierFor(0xFFFFFFFFu, t) == 3);
    CHECK(ParseIds("22") == std::vector<uint32_t>({ 22 }));
    CHECK(ParseIds(" 75, 225 ;375 ") == std::vector<uint32_t>({ 75, 225, 375 }));
    CHECK(ParseIds("").empty() && ParseIds("x, ,").empty());
    CHECK(ParseIds("4294967295,4294967296,7") == std::vector<uint32_t>({ 4294967295u, 7 }));   // too big: dropped
    CHECK(ParseIds("-5") == std::vector<uint32_t>({ 5 }));
    CHECK(ParseTiers("75,225,375") && *ParseTiers("75,225,375") == t);
    CHECK(ParseTiers("1 2 3") && (*ParseTiers("1 2 3"))[2] == 3u);
    CHECK(!ParseTiers("75,225") && !ParseTiers("75,225,375,450") && !ParseTiers("0,225,375") && !ParseTiers("75,75,375") &&
        !ParseTiers("375,225,75") && !ParseTiers(""));
    CHECK(BonusPct(false, false, 10, 5, 25) == 0);
    CHECK(BonusPct(true, false, 10, 5, 25) == 10);
    CHECK(BonusPct(false, true, 10, 5, 25) == 5);
    CHECK(BonusPct(true, true, 10, 5, 25) == 15);
    CHECK(BonusPct(true, true, 20, 15, 25) == 25);   // capped
    CHECK(BonusPct(true, true, 0xFFFFFFFFu, 0xFFFFFFFFu, 100) == 100);
    CHECK(AddPct(100, 15) == 115 && AddPct(5, 15) == 5 && AddPct(7, 15) == 8 && AddPct(0, 25) == 0 && AddPct(1000, 0) == 1000);
    CHECK(AddPct(0xFFFFFFFFu, 25) == 0xFFFFFFFFu);   // saturates
    CHECK(RepairCostMod(false, 10) == 1.0f && RepairCostMod(true, 10) == 0.9f && RepairCostMod(true, 0) == 1.0f &&
        RepairCostMod(true, 250) == 0.0f);
    CHECK(RepairAllowed(true, 75, 75, false, false) && !RepairAllowed(true, 74, 75, false, false));
    CHECK(!RepairAllowed(false, 450, 75, false, false));            // feature 2048 off
    CHECK(RepairAllowed(false, 0, 75, true, true));                 // a camp anvil, no blacksmithing
    CHECK(RepairAllowed(true, 450, 75, false, true));               // either way
    CHECK(!RepairAllowed(false, 0, 75, false, true));               // camping off: an anvil is just a decoration
    CHECK(!RepairAllowed(true, 0, 0, false, false));                // MinSkill 0 still needs the profession
    CHECK(SecondsLeft(100, 40) == 60 && SecondsLeft(40, 40) == 0 && SecondsLeft(0, 40) == 0);
}

TEST("camping: the repair toast shows the money that went")
{
    using namespace Bleakhold::CampRules;
    // Player::DurabilityRepairAll returns 0 when the player pays: the toast uses the money before and after
    CHECK(MoneySpent(50000, 39797) == 10203 && MoneySpent(10, 10) == 0 && MoneySpent(5, 9) == 0);
    CHECK(MoneySpent(0xFFFFFFFFu, 0) == 0xFFFFFFFFu);
    CHECK_EQ(MoneyText(MoneySpent(50000, 39797)), "1g 2s 3c");
    CHECK_EQ(MoneyText(0), "0c");
    CHECK_EQ(MoneyText(99), "99c");
    CHECK_EQ(MoneyText(200), "2s 0c");
    CHECK_EQ(MoneyText(10000), "1g 0s 0c");
    CHECK_EQ(MoneyText(0xFFFFFFFFu), "429496g 72s 95c");
}

TEST("camping: camp rest never takes over rest without a rest bit")
{
    using namespace Bleakhold::CampRules;
    CHECK(MaySetCampRestBit(false, false));    // not resting: the camp's bit makes the rest
    CHECK(MaySetCampRestBit(true, true));      // an inn or city bit: it keeps the rest when the camp's bit goes
    CHECK(!MaySetCampRestBit(true, false));    // mod-guildhouse's SetRestState: removing the bit later would end it
}

TEST("camping: camp objects carry no crafting station tied to a place")
{
    using namespace Bleakhold::CampRules;
    std::vector<uint32_t> const def = ParseIds(DefaultAllowedFocusIds);
    CHECK(def == std::vector<uint32_t>({ 1, 3, 4 }));   // anvil, forge, cooking fire
    CHECK(FocusAllowed(0, def) && FocusAllowed(1, def) && FocusAllowed(3, def) && FocusAllowed(4, def));
    CHECK(!FocusAllowed(2, def));                       // a loom
    CHECK(!FocusAllowed(663, def));                     // Alchemy Lab
    CHECK(!FocusAllowed(1426, def));                    // Mana Loom
    CHECK(FocusAllowed(0, {}) && !FocusAllowed(4, {}));
    CHECK(FocusAllowed(663, ParseIds("1, 663")));
    // the defaults: no location-tied station (gameobject_template: focus 663 Alchemy Labs, focus 1426 Mana Looms);
    // the tier 3 Alchemy and Tailoring objects are inert generic objects with the look of the trade
    for (Profession const& p : DefaultProfessions)
        for (uint32_t o : p.objects)
            for (uint32_t station : { 187115u, 177387u, 180631u, 183848u, 184803u, 185000u })
                CHECK_MSG(o != station, std::string(p.key) + " has no location-tied crafting station");
    CHECK(DefaultProfessions[0].skill == 171 && DefaultProfessions[0].objects[2] == 190689);    // Apothecary Table
    CHECK(DefaultProfessions[10].skill == 197 && DefaultProfessions[10].objects[2] == 188216);  // Armor Stand
}

TEST("camping: the buff check takes Sayge's fortunes and refuses XP, area and harmful spells")
{
    using namespace Bleakhold::CampRules;
    auto aura = [] { BuffEffect e; e.present = true; e.positive = true; return e; };
    // Spell.dbc 3.3.5a, Sayge's Dark Fortune of Spirit 23738: effect 0 a positive MOD_PERCENT_STAT aura on
    // TARGET_UNIT_TARGET_ANY, effect 1 TRIGGER_SPELL 23770 (a dummy aura flagged AURA_IS_DEBUFF), which the core marks
    // negative: SpellInfo::IsPositive() is false, yet the fortune is a buff
    BuffEffect markerTrigger;
    markerTrigger.present = true;
    markerTrigger.inertTrigger = true;
    BuffEffects const sayge = { aura(), markerTrigger, BuffEffect{} };
    CHECK(CheckBuff(sayge) == BuffProblem::None);
    // a scroll (one positive aura), Well Fed 57399 (three)
    CHECK(CheckBuff({ aura(), BuffEffect{}, BuffEffect{} }) == BuffProblem::None);
    CHECK(CheckBuff({ aura(), aura(), aura() }) == BuffProblem::None);
    // the same trigger of a spell that is not an inert marker (a scripted, linked or real debuff): refused
    BuffEffect harmfulTrigger;
    harmfulTrigger.present = true;
    CHECK(CheckBuff({ aura(), harmfulTrigger, BuffEffect{} }) == BuffProblem::NotBuff);
    // a debuff, and a spell whose only effect is the inert trigger (it does the player no good)
    BuffEffect debuff;
    debuff.present = true;
    CHECK(CheckBuff({ debuff, BuffEffect{}, BuffEffect{} }) == BuffProblem::NotBuff);
    CHECK(CheckBuff({ markerTrigger, BuffEffect{}, BuffEffect{} }) == BuffProblem::NotBuff);
    CHECK(CheckBuff({ BuffEffect{}, BuffEffect{}, BuffEffect{} }) == BuffProblem::NotBuff);
    // XP auras (Ribbon Dance 29175), area auras and area or chain targets stay refused, positive or not
    BuffEffect xp = aura();
    xp.changesXp = true;
    CHECK(CheckBuff({ aura(), xp, BuffEffect{} }) == BuffProblem::ChangesXp);
    BuffEffect area = aura();
    area.areaAura = true;
    CHECK(CheckBuff({ area, BuffEffect{}, BuffEffect{} }) == BuffProblem::AreaAura);
    BuffEffect raid = aura();
    raid.reachesOthers = true;   // Prayer of Fortitude: APPLY_AURA on TARGET_UNIT_CASTER_AREA_RAID
    CHECK(CheckBuff({ raid, BuffEffect{}, BuffEffect{} }) == BuffProblem::ReachesOthers);
    BuffEffect xpTrigger = markerTrigger;
    xpTrigger.changesXp = true;
    CHECK(CheckBuff({ aura(), xpTrigger, BuffEffect{} }) == BuffProblem::ChangesXp);
    // facts in an unused slot count for nothing
    BuffEffect ghost = xp;
    ghost.present = false;
    CHECK(CheckBuff({ aura(), BuffEffect{}, ghost }) == BuffProblem::None);
    CHECK_EQ(std::string(BuffProblemText(BuffProblem::NotBuff)), "is not a buff");
    CHECK(std::string(BuffProblemText(BuffProblem::None)).empty());
    for (BuffProblem p : { BuffProblem::ChangesXp, BuffProblem::AreaAura, BuffProblem::ReachesOthers })
        CHECK(!std::string(BuffProblemText(p)).empty());
}

TEST("camping: object slots stand apart around the fire")
{
    using namespace Bleakhold::CampRules;
    for (float o : { 0.0f, 1.0f, 3.14159f, 6.0f })
    {
        Offset a = SlotOffset(0, o, 2.6f), b = SlotOffset(1, o, 2.6f), c = SlotOffset(2, o, 2.6f);
        auto dist = [](Offset const& x, Offset const& y) { return std::sqrt((x.x - y.x) * (x.x - y.x) + (x.y - y.y) * (x.y - y.y)); };
        auto radius = [](Offset const& x) { return std::sqrt(x.x * x.x + x.y * x.y); };
        CHECK(std::fabs(radius(a) - 2.6f) < 0.01f && std::fabs(radius(b) - 2.6f) < 0.01f && std::fabs(radius(c) - 2.6f) < 0.01f);
        CHECK(dist(a, b) > 4.4f && dist(b, c) > 4.4f && dist(a, c) > 4.4f);   // 2.6 * sqrt(3) = 4.5
        CHECK(a.angle >= 0.0f && a.angle < 6.2832f);
        // slot 0 stands beyond the fire as its maker sees it (the fire faces the way its maker looked, 1.5 yd ahead of
        // them), never on the maker's side; the others stand at least 1 yd beside the maker's spot
        CHECK(a.x * std::cos(o) + a.y * std::sin(o) > 2.5f);
        float const mx = -1.5f * std::cos(o), my = -1.5f * std::sin(o);
        for (Offset const& q : { b, c })
            CHECK(std::sqrt((q.x - mx) * (q.x - mx) + (q.y - my) * (q.y - my)) > 1.0f);
        // every object faces the fire
        CHECK(std::fabs(std::cos(b.angle) * b.x + std::sin(b.angle) * b.y + 2.6f) < 0.01f);
    }
    CHECK(SlotOffset(3, 0.0f, 2.0f).x == SlotOffset(0, 0.0f, 2.0f).x);
}

TEST("camping: the default professions are complete and distinct")
{
    using namespace Bleakhold::CampRules;
    std::set<uint32_t> skills;
    std::set<std::string> keys;
    std::set<uint32_t> objects;
    for (Profession const& p : DefaultProfessions)
    {
        CHECK_MSG(skills.insert(p.skill).second, std::string("skill of ") + p.key + " is unique");
        CHECK_MSG(keys.insert(p.key).second, std::string("key ") + p.key + " is unique");
        std::string const k = p.key;
        bool ok = !k.empty();
        for (char ch : k)
            ok = ok && ((ch >= 'A' && ch <= 'Z') || (ch >= 'a' && ch <= 'z'));
        CHECK_MSG(ok, "profession key [" + k + "] is a config key part");
        for (uint8_t i = 0; i < TierCount; ++i)
        {
            CHECK_MSG(p.objects[i] != 0 && p.buffs[i] != 0, k + " tier " + std::to_string(i + 1));
            CHECK_MSG(objects.insert(p.objects[i]).second, k + " objects are not shared with another tier or profession");
        }
        CHECK_MSG(p.buffs[0] != p.buffs[1] && p.buffs[1] != p.buffs[2] && p.buffs[0] != p.buffs[2], k + " buffs differ per tier");
        // never an aura that raises XP itself (the module's bonus would come on top): Ribbon Dance
        for (uint32_t b : p.buffs)
            CHECK_MSG(b != 29175, k + " gives no XP aura");
    }
    CHECK(DefaultProfessions.size() == 14);
    for (uint32_t s : { 129u, 164u, 165u, 171u, 182u, 185u, 186u, 197u, 202u, 333u, 356u, 393u, 755u, 773u })
        CHECK_MSG(skills.count(s), "profession " + std::to_string(s));
    CHECK(SkillBlacksmithing == 164 && AnvilTier == 2);
    CHECK(DefaultProfessions[1].skill == 164 && DefaultProfessions[1].objects[2] == 171715);   // The Great Anvil
}

TEST("camping: CAMPST is sent again only when more than a timer changed")
{
    using namespace Bleakhold::CampRules;
    CampState a;
    a.state = CampStateId::Resting; a.settleSec = 40; a.fireSec = 800; a.mine = true; a.cooldownSec = 700; a.warmthSec = 0;
    a.xpPct = 5; a.objects = { { 171, 1, false } }; a.place = { { 164, 2 } }; a.glideSec = 0u; a.repair = false; a.fed = true;
    CampState b = a;
    CHECK(!Changed(a, b));
    b.settleSec = 10; b.fireSec = 300; b.cooldownSec = 1;   // counting down
    CHECK(!Changed(a, b));
    auto changedBy = [&](auto edit) { CampState c = a; edit(c); return Changed(a, c); };
    CHECK(changedBy([](CampState& c) { c.state = CampStateId::Camping; }));
    CHECK(changedBy([](CampState& c) { c.fireSec = 0; }));            // the fire went out
    CHECK(changedBy([](CampState& c) { c.cooldownSec = 0; }));        // the cooldown is over
    CHECK(changedBy([](CampState& c) { c.warmthSec = 1800; }));       // the warmth started
    CHECK(changedBy([](CampState& c) { c.xpPct = 15; }));
    CHECK(changedBy([](CampState& c) { c.mine = false; }));
    CHECK(changedBy([](CampState& c) { c.objects.push_back({ 164, 2, true }); }));
    CHECK(changedBy([](CampState& c) { c.objects[0].tier = 2; }));
    CHECK(changedBy([](CampState& c) { c.place.clear(); }));
    CHECK(changedBy([](CampState& c) { c.place[0].tier = 3; }));
    CHECK(changedBy([](CampState& c) { c.glideSec = 120u; }));        // glide used
    CHECK(changedBy([](CampState& c) { c.glideSec.reset(); }));       // cannot glide any more
    CHECK(changedBy([](CampState& c) { c.repair = true; }));
    CHECK(changedBy([](CampState& c) { c.fed = false; }));
}

TEST("camping: the CAMPST encoder keeps to the document")
{
    CampState s;
    CHECK_EQ(EncodeCampState(s), "N,0,0,0,0,0,0,,,,0,0");                // nothing: glide empty in the middle
    s.settleSec = 30;                                                     // settle only with R
    CHECK_EQ(EncodeCampState(s), "N,0,0,0,0,0,0,,,,0,0");
    s.state = CampStateId::Resting;
    CHECK_EQ(EncodeCampState(s), "R,30,0,0,0,0,0,,,,0,0");
    s.state = CampStateId::Camping;
    s.objects = { { 164, 0, true }, { 171, 9, false } };                 // tiers clamped to 1..3
    s.glideSec = 0u;
    CHECK_EQ(EncodeCampState(s), "C,0,0,0,0,0,0,164~1~1:171~3~0,,0,0,0");
    for (uint32_t i = 0; i < 20; ++i)
    {
        s.objects.push_back({ 100 + i, 1, false });
        s.place.push_back({ 200 + i, 2 });
    }
    std::string const big = EncodeCampState(s);
    std::vector<std::string> f = SplitStr(big, ',');
    CHECK(f.size() == 12);
    CHECK(SplitStr(f[7], ':').size() == MaxCampObjects && SplitStr(f[8], ':').size() == MaxCampPlaces);
}

// ---------------------------------------------------------------------------------------------------
// Bleakhold Royale (section 17): QUEUE kind B and the ROYS ROYM ROYO ROYK ROYV ROYE encoders
// ---------------------------------------------------------------------------------------------------
TEST("royale: QUEUE kind B appends its counts and never sends members; D and R never send the counts")
{
    QueueState q;
    q.state = QueueStateId::Queued; q.kind = QueueKind::Royale; q.activityId = 901; q.tier = 0; q.size = 1;
    q.queuedSec = 12; q.bandMin = 80; q.bandMax = 80; q.queued = 13; q.minPlayers = 20; q.maxPlayers = 40;
    q.matchesRunning = 0;
    QueueMember m; m.name = "Tester"; m.classId = 1;
    q.members = { m };   // ignored for Royale
    CHECK_EQ(EncodeQueue(4, q), "4,1,B,901,0,1,12,,,,80,80,13,20,40,,,0");
    q.matchesRunning.reset();
    q.queued.reset();
    CHECK_EQ(EncodeQueue(4, q), "4,1,B,901,0,1,12,,,,80,80,,20,40");
    q.state = QueueStateId::NotQueued;
    q.activityId.reset(); q.tier.reset(); q.size.reset(); q.queuedSec.reset(); q.bandMin.reset(); q.bandMax.reset();
    q.minPlayers.reset(); q.maxPlayers.reset();
    CHECK_EQ(EncodeQueue(9, q), "9,0,B");
    QueueState d;
    d.state = QueueStateId::Proposal; d.kind = QueueKind::Dungeon; d.activityId = 389; d.bandMax = 18;
    d.queued = 13; d.minPlayers = 20; d.accepted = 3;   // not part of kind D
    d.members = { m };
    CHECK_EQ(EncodeQueue(2, d), "2,2,D,389,,,,,,,,18;Tester,1,,0");
}

TEST("royale: the encoders keep to the document")
{
    RoyaleState st;
    CHECK_EQ(EncodeRoyaleState(st), "0,0,0,0,0,0,0,,,,0,0,0,0,,,,,,0");   // empty fields in the middle stay
    st.matchId = 7001; st.phase = RoyalePhase::Overtime; st.phaseMsLeft = 4294967295u; st.alive = 2; st.total = 40;
    st.me = RoyaleMe::Spectating; st.kills = 3; st.placement = 7; st.pinX = -17067; st.pinY = 17067; st.stage = 6;
    st.curX = -300; st.curY = -1; st.curR = 0; st.nextX = -301; st.nextY = 0; st.nextR = 0; st.shrinkStartMs = 0u;
    st.shrinkEndMs = 45000u; st.dmgPermille = 160; st.watchName = "Br\xC3\xA9nna, the; long|name";
    st.myX = 455; st.myY = -455;
    CHECK_EQ(EncodeRoyaleState(st), "7001,4,4294967295,2,40,3,3,7,-17067,17067,6,-300,-1,0,-301,0,0,0,45000,160,"
        "Br\xC3\xA9nna%2C the%3B long%7Cname,455,-455");
    st.stages = 6;   // field 24: the stage count (stage 7 = overtime here)
    CHECK_EQ(EncodeRoyaleState(st), "7001,4,4294967295,2,40,3,3,7,-17067,17067,6,-300,-1,0,-301,0,0,0,45000,160,"
        "Br\xC3\xA9nna%2C the%3B long%7Cname,455,-455,6");
    st.watchName = std::string(60, 'x');
    CHECK(SplitStr(EncodeRoyaleState(st), ',')[20].size() == RoyaleNameBytes);   // names cut at 48 bytes
    RoyaleState few;
    few.stages = 16;   // the empty watchName, myX and myY before it stay
    CHECK_EQ(EncodeRoyaleState(few), "0,0,0,0,0,0,0,,,,0,0,0,0,,,,,,0,,,,16");

    RoyaleMap mp;
    mp.mapId = 566; mp.minX = 1500; mp.maxX = 2800; mp.minY = 900; mp.maxY = 2200; mp.lobbyX = 2166; mp.lobbyY = 1564;
    mp.lobbyR = 20; mp.boundHalf = 400; mp.centerX = 2166; mp.centerY = 1564;
    mp.pois = { { 1, RoyalePoiKind::Lobby, 2166, 1564, 20, "The Overlook" },
        { 2, RoyalePoiKind::Crossing, -5, -6, 0, "Ford: east, west" } };
    CHECK_EQ(EncodeRoyaleMap(mp), "566,1500,2800,900,2200,2166,1564,20,400,2166,1564;1,Y,2166,1564,20,The Overlook;"
        "2,C,-5,-6,0,Ford%3A east%2C west");
    mp.pois.clear();
    for (uint32_t i = 0; i < 100; ++i)
        mp.pois.push_back({ i + 1, RoyalePoiKind::Landmark, int32_t(i), -int32_t(i), 10, std::string(70, 'n') });
    std::vector<std::string> recs = SplitStr(EncodeRoyaleMap(mp), ';');
    CHECK_EQN(recs.size(), MaxRoyalePois + 1);
    CHECK(SplitStr(recs[1], ',')[5].size() == 40);

    RoyaleObjects ob;
    ob.matchId = 7001; ob.full = false;
    CHECK_EQ(EncodeRoyaleObjects(ob), "7001,0");
    RoyaleObject supply; supply.objId = 9; supply.kind = RoyaleObjectKind::Supply; supply.x = -950; supply.y = -250;
    supply.state = RoyaleObjectState::Incoming; supply.msLeft = 20000u;
    RoyaleObject buff;
    buff.objId = 4; buff.kind = RoyaleObjectKind::Buff; buff.subtype = static_cast<uint32_t>(RoyaleBuff::Berserk);
    buff.x = 220; buff.y = -250; buff.state = RoyaleObjectState::Opened;
    ob.objects = { supply, buff };
    CHECK_EQ(EncodeRoyaleObjects(ob), "7001,0;9,D,0,-950,-250,3,20000;4,B,3,220,-250,4");
    ob.objects.assign(80, buff);
    CHECK_EQN(SplitStr(EncodeRoyaleObjects(ob), ';').size(), MaxRoyaleObjects + 1);

    RoyaleKill k;
    k.victimName = "Brenna"; k.victimClassId = 8; k.cause = RoyaleCause::Storm; k.aliveAfter = 22;
    CHECK_EQ(EncodeRoyaleKill(k), ",,Brenna,8,S,22");   // nobody got the credit
    k.killerName = "Aldric"; k.killerClassId = 1; k.killerKills = 5; k.cause = RoyaleCause::Afk;
    CHECK_EQ(EncodeRoyaleKill(k), "Aldric,1,Brenna,8,A,22,5");

    RoyaleEvent ev;
    ev.kind = RoyaleEventKind::PlayersLeft; ev.value = 5;
    CHECK_EQ(EncodeRoyaleEvent(ev), "N,5");
    ev.kind = RoyaleEventKind::SupplyOpened; ev.value = 0; ev.x = -850; ev.y = -820; ev.name = "Aldric";
    CHECK_EQ(EncodeRoyaleEvent(ev), "O,0,-850,-820,,Aldric");

    RoyaleResult r;
    r.matchId = 7001; r.placement = 1; r.total = 32; r.kills = 12; r.damage = 4000000000u; r.healing = 5;
    r.survivedSec = 715; r.winnerName = "Dalia"; r.winnerClassId = 11; r.winnerKills = 12; r.rewarded = true;
    Reward h; h.kind = RewardKind::Honor; h.amount = 400; h.text = "Victory";
    Reward sh; sh.kind = RewardKind::Shards; sh.amount = 50;
    r.rewards = { h, sh };
    CHECK_EQ(EncodeRoyaleResult(r), "7001,1,32,12,4000000000,5,715,Dalia,11,12,1;H,400,,Victory;S,50");
    r.rewarded = false; r.rewards.clear(); r.winnerName.clear(); r.winnerClassId.reset(); r.winnerKills.reset();
    CHECK_EQ(EncodeRoyaleResult(r), "7001,1,32,12,4000000000,5,715,,,,0");
    CHECK(static_cast<char>(RewardKind::Honor) == 'H');
    CHECK(FeatureRoyale == 4096u && (FeatureRoyale & (FeatureFieldRepair * 2 - 1)) == 0);
}

TEST("royale: ROYK announce is superseded by BGANN: the field is never written, whatever the caller sets")
{
    RoyaleKill k;
    k.killerName = "Aldric"; k.killerClassId = 1; k.victimName = "Brenna"; k.victimClassId = 8;
    k.cause = RoyaleCause::Player; k.aliveAfter = 23; k.killerKills = 1; k.announce = RoyaleAnnounce::FirstBlood;
    CHECK_EQ(EncodeRoyaleKill(k), "Aldric,1,Brenna,8,P,23,1");
    for (int v = 0; v < 256; ++v)
    {
        k.announce = static_cast<RoyaleAnnounce>(static_cast<char>(v));
        CHECK_EQ(EncodeRoyaleKill(k), std::string("Aldric,1,Brenna,8,P,23,1"));
    }
    k.killerKills.reset();
    k.announce = RoyaleAnnounce::Godlike;
    CHECK_EQ(EncodeRoyaleKill(k), "Aldric,1,Brenna,8,P,23");   // the empty fields at the end go
}

// ---------------------------------------------------------------------------------------------------
// The battleground kill announcer (section 18): BGANN
// ---------------------------------------------------------------------------------------------------
TEST("bgann: the encoder keeps to the document; multi first, then streak")
{
    BgAnnounce a;
    a.killerName = "Aldric"; a.killerClassId = 1; a.victimName = "Brenna"; a.victimClassId = 8;
    a.streak = BgStreak::FirstBlood;
    CHECK_EQ(EncodeBgAnnounce(a), "Aldric,1,Brenna,8,,F");
    a.multi = BgMultiKill::Double; a.streak = BgStreak::None;
    CHECK_EQ(EncodeBgAnnounce(a), "Aldric,1,Brenna,8,D");   // an empty last field is left out
    a.multi = BgMultiKill::Rampage; a.streak = BgStreak::HolyShit;
    CHECK_EQ(EncodeBgAnnounce(a), "Aldric,1,Brenna,8,R,H");
    a.killerName = "Br\xC3\xA9nna, the; long|name";
    CHECK_EQ(EncodeBgAnnounce(a), "Br\xC3\xA9nna%2C the%3B long%7Cname,1,Brenna,8,R,H");
    a.killerName = std::string(60, 'x');
    CHECK(SplitStr(EncodeBgAnnounce(a), ',')[0].size() == BgNameBytes);   // names cut at 48 bytes
    CHECK(FeatureBgAnnouncer == 8192u && FeatureBgAnnouncer == FeatureRoyale * 2);
    CHECK(BgNameBytes == RoyaleNameBytes);
}

TEST("bgann: only the documented letters are written; nothing is sendable without a code and both names")
{
    std::string const multi = "DTUR";
    std::string const streak = "FSOKNWMGH";
    int multis = 0;
    int streaks = 0;
    for (int v = 0; v < 256; ++v)
    {
        char const c = static_cast<char>(v);
        bool const m = v != 0 && multi.find(c) != std::string::npos;
        bool const s = v != 0 && streak.find(c) != std::string::npos;
        multis += m;
        streaks += s;
        CHECK_EQN(BgMultiLetter(static_cast<BgMultiKill>(c)), m ? c : '\0');
        CHECK_EQN(BgStreakLetter(static_cast<BgStreak>(c)), s ? c : '\0');
        BgAnnounce a;
        a.killerName = "Aldric"; a.killerClassId = 1; a.victimName = "Brenna"; a.victimClassId = 8;
        a.multi = static_cast<BgMultiKill>(c);
        CHECK_EQ(EncodeBgAnnounce(a), m ? "Aldric,1,Brenna,8," + std::string(1, c) : std::string("Aldric,1,Brenna,8"));
        CHECK(BgAnnounceSendable(a) == m);
        a.multi = BgMultiKill::None;
        a.streak = static_cast<BgStreak>(c);
        CHECK_EQ(EncodeBgAnnounce(a), s ? "Aldric,1,Brenna,8,," + std::string(1, c) : std::string("Aldric,1,Brenna,8"));
        CHECK(BgAnnounceSendable(a) == s);
    }
    CHECK_EQN(multis, 4);
    CHECK_EQN(streaks, 9);
    BgAnnounce a;
    a.killerName = "Aldric"; a.victimName = "Brenna"; a.multi = BgMultiKill::Triple;
    CHECK(BgAnnounceSendable(a));
    a.killerName = std::string(3, '\0');   // cleans to nothing
    CHECK(!BgAnnounceSendable(a));
    a.killerName = "Aldric"; a.victimName.clear();
    CHECK(!BgAnnounceSendable(a));
    a.victimName = "Brenna"; a.multi = BgMultiKill::None; a.streak = BgStreak::None;
    CHECK(!BgAnnounceSendable(a));
}

TEST("royale: the ERR codes of section 17 are short machine codes and documented")
{
    std::string const doc = bhtest::ReadFile(g_repo + "/docs/BleakholdProtocol.md");
    for (Refusal const& r : { RoyaleErr::Off, RoyaleErr::Level, RoyaleErr::Grouped, RoyaleErr::Busy,
             RoyaleErr::Deserter, RoyaleErr::Bags, RoyaleErr::Ip, RoyaleErr::Lockout, RoyaleErr::NoProposal,
             RoyaleErr::Phase, RoyaleErr::Nobody, RoyaleErr::GlideHere })
    {
        std::string const code = r.code;
        bool ok = !code.empty() && code.size() <= 24;
        for (char c : code)
            ok = ok && ((c >= 'a' && c <= 'z') || c == '_');
        CHECK_MSG(ok, "code [" + code + "]");
        CHECK_MSG(doc.find("| `" + code + "` |") != std::string::npos, code + " is in an error table of the document");
        CHECK_MSG(std::string(r.text).size() <= 160 && !std::string(r.text).empty(), code + " has a sentence");
    }
}

TEST("arena: QJOIN A, LBQ A and GET ARENA parse as section 20 says; everything else is dropped")
{
    Intent in;
    CHECK(Parse("1 QJOIN 1b 1/1 A,1,1,4,1", &in) == DropReason::None);
    CHECK(in.type == IntentType::QueueJoin && in.queueKind == QueueKind::Arena && in.activityId == ArenaActivityId &&
        in.tier == 1 && in.groupSize == 1);
    CHECK(Parse("1 QJOIN 1c 1/1 A,1,0,7,1", &in) == DropReason::None && in.tier == 0 && in.roles == 7);
    CHECK_EQ(EncodeIntentBody(in), "1 QJOIN 1c 1/1 A,1,0,7,1");
    CHECK(Parse("1 QJOIN 1 1/1 A,2,1,4,1") == DropReason::OutOfRange);   // only activity 1
    CHECK(Parse("1 QJOIN 1 1/1 A,0,1,4,1") == DropReason::OutOfRange);
    CHECK(Parse("1 QJOIN 1 1/1 A,1,2,4,1") == DropReason::OutOfRange);   // tier 0 or 1
    CHECK(Parse("1 QJOIN 1 1/1 A,1,3,4,1") == DropReason::OutOfRange);
    CHECK(Parse("1 QJOIN 1 1/1 A,1,1,4,2") == DropReason::OutOfRange);   // solo
    CHECK(Parse("1 QJOIN 1 1/1 A,1,1,0,1") == DropReason::OutOfRange);   // roles 1..7 as for every kind
    CHECK(Parse("1 QJOIN 1 1/1 A,1,1,4") == DropReason::FieldCount);
    CHECK(Parse("1 QJOIN 1 1/1 a,1,1,4,1") == DropReason::BadField);
    CHECK(Parse("1 LBQ 1d 1/1 A,0,3,0,1", &in) == DropReason::None);
    CHECK(in.board == Board::Arena && in.seasonId == 0 && in.dungeonId == 3 && in.classId == 0 && in.page == 1);
    for (char const* ok : { "1 LBQ 1 1/1 A,2,1,8,2", "1 LBQ 1 1/1 A,0,2,0,1", "1 LBQ 1 1/1 A,0,5,11,999" })
        CHECK_MSG(Parse(ok) == DropReason::None, ok);
    for (char const* bad : { "1 LBQ 1 1/1 A,0,0,0,1", "1 LBQ 1 1/1 A,0,4,0,1", "1 LBQ 1 1/1 A,0,6,0,1",
             "1 LBQ 1 1/1 A,0,11,0,1" })
        CHECK_MSG(Parse(bad) == DropReason::OutOfRange, bad);   // one bracket at a time, never "all"
    CHECK(Parse("1 LBQ 1 1/1 A,0,3,0,0") == DropReason::OutOfRange);
    CHECK(Parse("1 LBQ 1 1/1 K,0,0,0,1") == DropReason::None);     // the other boards keep 0 = all
    CHECK(Parse("1 GET 1a 1/1 ARENA", &in) == DropReason::None);
    CHECK(in.topics.size() == 1 && in.topics[0].topic == Topic::Arena);
    CHECK(Parse("1 GET 1 1/1 ARENA,1") == DropReason::BadTopic);
    CHECK(Parse("1 GET 1 1/1 ARENA;QUEUE;ROYS", &in) == DropReason::None && in.topics.size() == 3);
    CHECK_EQ(TopicName(Topic::Arena), "ARENA");
    CHECK(!IsRevisioned(Topic::Arena));
    CHECK(static_cast<uint8_t>(Topic::Arena) == static_cast<uint8_t>(Topic::RoyaleMap) + 1);   // appended
    CHECK_EQN(RevisionedTopicCount, 9u);
    CHECK(IsArenaBracket(1) && IsArenaBracket(2) && IsArenaBracket(3) && IsArenaBracket(5));
    CHECK(!IsArenaBracket(0) && !IsArenaBracket(4) && !IsArenaBracket(6));
}

TEST("arena: the feature bit and the ERR codes of section 20")
{
    CHECK_EQN(static_cast<uint32_t>(FeatureArena), 65536u);
    // 16384 and 32768 belong to World PvP (section 19): FeatureArena never overlaps a lower bit
    CHECK_EQN(static_cast<uint32_t>(FeatureArena) & 0xFFFFu, 0u);
    std::string const doc = bhtest::ReadFile(g_repo + "/docs/BleakholdProtocol.md");
    CHECK(doc.find("65536 arena seasons") != std::string::npos);
    for (Refusal const& r : { ArenaErr::Off, ArenaErr::Level, ArenaErr::Closed, ArenaErr::Busy, ArenaErr::Deserter,
             ArenaErr::Talents, ArenaErr::Team, ArenaErr::Gold })
    {
        std::string const code = r.code;
        bool ok = !code.empty() && code.size() <= 24 && code.compare(0, 6, "arena_") == 0;
        for (char c : code)
            ok = ok && ((c >= 'a' && c <= 'z') || c == '_');
        CHECK_MSG(ok, "code [" + code + "]");
        CHECK_MSG(doc.find("| `" + code + "` |") != std::string::npos, code + " is in an error table of the document");
        CHECK_MSG(std::string(r.text).size() <= 160 && !std::string(r.text).empty(), code + " has a sentence");
    }
}

TEST("arena: ARENA keeps every record's field order and caps")
{
    ArenaState a;
    CHECK_EQ(EncodeArena(a), "0,0,,,,0");   // no arena season: an empty header
    a.seasonId = 3; a.state = ArenaStateId::Upcoming; a.nextStartEpoch = 1800748800u; a.oneTeamCostCopper = 400000u;
    a.seasonName = "Arena Season 3; the, long|one";
    CHECK_EQ(EncodeArena(a), "3,6,,,1800748800,0,400000,Arena Season 3%3B the%2C long%7Cone");
    ArenaBracketState b;
    b.bracket = 2; b.hasTeam = false; b.missingMask = 0x1FF;   // bit 256 is not a protocol bit: cut to 8 bits
    a.brackets = { b };
    ArenaBracketState bad;
    bad.bracket = 4;   // not a bracket: never written
    a.brackets.push_back(bad);
    ArenaCutoff c;
    c.bracket = 5; c.tierId = 1; c.slots = 10; c.floor = 1300;   // nobody inside it yet: cutRank and cutRating empty
    a.cutoffs = { c };
    ArenaLadderInfo l;
    l.bracket = 5; l.eligibleTeams = 7; l.rewardsOpen = false; l.titlesOpen = false;
    a.ladders = { l };
    ArenaFinal f;
    f.bracket = 1; f.finalRank = 3; f.finalRating = 1990; f.grant = ArenaGrant::Delivered;   // no tier
    a.finals = { f };
    CHECK_EQ(EncodeArena(a), "3,6,,,1800748800,0,400000,Arena Season 3%3B the%2C long%7Cone;B,2,0,,,,,,,,,,,,,255;"
        "T,5,1,10,,,1300;N,5,7,0,0;F,1,3,1990,,1");
    ArenaState many;
    for (uint32_t i = 0; i < 40; ++i)
    {
        many.seasons.push_back({ i + 1, "S", SeasonStateId::Past, 1u, 2u });
        ArenaMatch m;
        m.bracket = 1; m.opponent = "X"; m.endEpoch = i; m.reason = ArenaReason::Repeat; m.verdict = ArenaVerdict::Reduced;
        many.matches.push_back(m);
        many.cutoffs.push_back(c);
    }
    std::vector<std::string> recs = SplitStr(EncodeArena(many), ';');
    std::size_t s = 0, m = 0, t = 0;
    for (std::string const& r : recs)
    {
        s += r.compare(0, 2, "S,") == 0;
        m += r.compare(0, 2, "M,") == 0;
        t += r.compare(0, 2, "T,") == 0;
    }
    CHECK_EQN(s, MaxArenaSeasons);
    CHECK_EQN(m, MaxArenaMatches);
    CHECK_EQN(t, MaxArenaCutoffs);
    CHECK(recs.back() == "M,1,0,0,X,4,1,R");
}

TEST("arena: LB and LBME carry the four and the two arena fields on board A only")
{
    Leaderboard lb;
    lb.board = Board::Keys; lb.page = 1; lb.pages = 1;
    LeaderboardRow r;
    r.rank = 1; r.dungeonId = 602u; r.value = 15; r.label = "x";
    r.seasonWins = 1u; r.seasonGames = 2u; r.tierId = 3u; r.flags = 4u;   // ignored on K
    lb.rows = { r };
    CHECK_EQ(EncodeLeaderboard(lb), "K,,,,1,1;1,602,15,,,,x");
    lb.board = Board::Arena; lb.seasonId = 1u; lb.dungeonId = 3u; lb.classId = 0u;
    r.dungeonId = 3u; r.value = 1912; r.dateEpoch = 1793896400u; r.members = { { "Ironvow", 1u }, { "Hale", 7u } };
    r.label = "Ironvow Wardens";
    lb.rows = { r };
    CHECK_EQ(EncodeLeaderboard(lb), "A,1,3,0,1,1;1,3,1912,,1793896400,Ironvow~1:Hale~7,Ironvow Wardens,1,2,3,4");
    r.flags.reset();
    r.tierId.reset();
    lb.rows = { r };
    CHECK_EQ(EncodeLeaderboard(lb), "A,1,3,0,1,1;1,3,1912,,1793896400,Ironvow~1:Hale~7,Ironvow Wardens,1,2");
    LeaderboardMe me;
    me.board = Board::Rift; me.rank = 4u; me.topPermille = 182u; me.tierId = 4u;   // ignored on R
    CHECK_EQ(EncodeLeaderboardMe(me), "R,4");
    me.board = Board::Arena; me.topPercent = 19u; me.value = 1912; me.dungeonId = 3u; me.barPermille = 407u;
    me.label = "Duelist";
    CHECK_EQ(EncodeLeaderboardMe(me), "A,4,19,1912,3,,407,Duelist,182,4");
    LeaderboardMe none;
    none.board = Board::Arena;
    CHECK_EQ(EncodeLeaderboardMe(none), "A");
}

TEST("arena: DEF V and Q follow the other kinds; QUEUE kind A has no member records")
{
    Definitions d;
    d.riftBosses = { { 1, "Echo" } };
    d.arenaTiers = { { 6, "Rank One", "E6CC80", "The best team of the bracket." } };
    ArenaRewardDef q;
    q.id = 105; q.seasonId = 1; q.bracket = 3; q.tierId = 5; q.kind = 'M'; q.entry = 30609; q.count = 1;
    q.text = "Swift Nether Drake";
    ArenaRewardDef bad = q;
    bad.id = 1; bad.kind = 'm';   // only upper-case letters are kinds: written empty
    d.arenaRewards = { q, bad };
    std::vector<std::string> p = EncodeDefinitions(d, 9);
    CHECK_EQN(p.size(), 4u);
    CHECK_EQ(p[0], "R,9;1,Echo");
    CHECK_EQ(p[1], "V,9;6,Rank One,E6CC80,The best team of the bracket.");
    CHECK_EQ(p[2], "Q,9;105,1,3,5,M,30609,1,Swift Nether Drake;1,1,3,5,,30609,1,Swift Nether Drake");
    CHECK_EQ(p[3], "Z,9");
    Definitions e;
    CHECK(DefinitionsHash(d) != DefinitionsHash(e));
    QueueState qa;
    qa.state = QueueStateId::Queued; qa.kind = QueueKind::Arena; qa.activityId = 1u; qa.tier = 1u; qa.size = 1u;
    qa.queuedSec = 8u; qa.estWaitSec = 95u;
    qa.queued = 3u;   // a Royale field: not part of kind A
    QueueMember m; m.name = "Tester";
    qa.members = { m };
    CHECK_EQ(EncodeQueue(7, qa), "7,1,A,1,1,1,8,95");
}

TEST("endpoint: SEQ per message, revisions per topic, snapshots reset by HELLO")
{
    Endpoint ep;
    CHECK(ep.Frame("WEEK", "1", 1000).size() == 1);   // framing itself does not need the handshake
    std::string big;
    for (int i = 0; i < 300; ++i)
        big += "1234567890";
    std::vector<std::string> frames = ep.Frame("BOARD", big, 251);
    CHECK(frames.size() > 10);
    for (std::string const& f : frames)
    {
        CHECK(f.compare(0, 4, "BHs\t") == 0);
        CHECK(f.size() <= 255);
        CHECK(f.compare(4, 9, "1 BOARD 2") == 0);   // all parts share SEQ 2
    }
    CHECK(ep.Frame("WEEK", "1", 1000)[0].compare(0, 13, "BHs\t1 WEEK 3 ") == 0);
    CHECK(ep.Frame("WEEK", std::string(MaxAssembled + 1, 'x'), 1000).empty());
    CHECK_EQN(ep.Seq(), 3u);   // a failed frame does not use a SEQ
    std::vector<std::string> fallback = ep.Frame("LIDX", std::string(20000, '1'), 64);   // 99 parts of 64 are too few
    CHECK(!fallback.empty() && fallback.size() <= 99);
    for (std::string const& f : fallback)
        CHECK(f.size() <= 4 + MaxServerBody && f.size() > 4 + 64);
    CHECK_EQN(ep.Seq(), 4u);
    CHECK_EQN(ep.NextRev(Topic::Tasks), 1u);
    CHECK_EQN(ep.NextRev(Topic::Tasks), 2u);
    CHECK_EQN(ep.NextRev(Topic::Week), 1u);
    CHECK_EQN(ep.NextRev(Topic::Firsts), 0u);   // not revisioned
    Feed(ep, "1 HELLO 1 1/1 1,1.0.0,0,enUS", 0);
    ep.MarkSnapshot(Topic::Tasks);
    CHECK(ep.HasSnapshot(Topic::Tasks));
    Feed(ep, "1 HELLO 2 1/1 1,1.0.0,0,enUS", 6000);   // /reload
    CHECK(!ep.HasSnapshot(Topic::Tasks));
    CHECK_EQN(ep.NextRev(Topic::Tasks), 3u);   // revisions keep counting; a snapshot resets the client anyway
}

// ---------------------------------------------------------------------------------------------------
// Every S> example of the document, rebuilt from the C++ structs
// ---------------------------------------------------------------------------------------------------
static std::map<std::string, std::string> BuiltExamples()
{
    std::map<std::string, std::string> m;
    {
        HelloReply h;
        h.proto = 1; h.minProto = 1; h.serverEpoch = 1792648725; h.utcOffsetMin = 60; h.dataVer = 7; h.featureBits = 58; h.seasonId = 1;
        h.dailyResetEpoch = 1792674645; h.weeklyResetEpoch = 1792907925; h.realmName = "Bleakhold"; h.siteUrl = "bleakhold.com";
        m["HELLO 1"] = EncodeHello(h);
    }
    m["PONG 2"] = EncodePong({ 12345, 1792648730 });
    {
        ErrorReply e;
        e.op = IntentType::TaskClaim; e.seq = 4; e.code = "not_claimable"; e.text = "That task cannot be claimed yet.";
        m["ERR 3"] = EncodeError(e);
    }
    {
        Definitions a;
        a.affixes = { { 1, "Fortified", "Non-boss enemies have more health and hit harder." },
            { 3, "Bolstering", "When a non-boss enemy dies, its allies nearby grow stronger." } };
        std::vector<std::string> p = EncodeDefinitions(a, 7);
        m["DEF 4"] = p.at(0);
        m["DEF 6"] = p.at(1);
        Definitions d;
        DungeonDef hol;
        hol.id = 602; hol.name = "Halls of Lightning"; hol.chapter = 5; hol.lvlMin = 77; hol.lvlMax = 80;
        hol.bosses = { "General Bjarngrim", "Volkhan", "Ionar", "Loken" }; hol.timeLimitSec = 1800;
        d.dungeons = { hol };
        m["DEF 5"] = EncodeDefinitions(d, 7).at(0);
    }
    {
        WeekState w;
        w.keysTimed = 4; w.raidEchoes = 1; w.riftBestFloor = 18; w.mythicCoins = 2140; w.mythicCoinsCap = 5500; w.shards = 1260;
        m["WEEK 7"] = EncodeWeek(1, w);
    }
    {
        EraState e;
        e.eraId = 7; e.nextEraId = 3; e.affixIds = { 1, 3, 4 }; e.weeklyBonusId = 1; e.weeklyBonusDone = false;
        m["ERA 8"] = EncodeEra(1, e);
    }
    {
        TaskList t;
        t.freeRerolls = 1; t.rerollCost = 500000; t.rerollCurrency = Currency::Copper;
        auto task = [](uint32_t uid, TaskKind k, uint32_t tpl, uint32_t have, uint32_t need, RewardKind rk, uint32_t amount, Opt<uint32_t> item,
                        TaskState st, std::string rt = {}) {
            Task x;
            x.uid = uid; x.kind = k; x.templateId = tpl; x.have = have; x.need = need; x.rewardKind = rk; x.rewardAmount = amount;
            x.rewardItemId = item; x.state = st; x.rewardText = std::move(rt);
            return x;
        };
        t.tasks = { task(101, TaskKind::Daily, 1, 0, 1, RewardKind::MythicCoins, 20, std::nullopt, TaskState::Open),
            task(102, TaskKind::Daily, 2, 14, 20, RewardKind::Item, 1, 40752u, TaskState::Open, "1 Emblem of Heroism"),
            task(103, TaskKind::Daily, 3, 5, 5, RewardKind::MythicCoins, 20, std::nullopt, TaskState::Claimable),
            task(201, TaskKind::Weekly, 4, 1, 3, RewardKind::MythicCoins, 150, std::nullopt, TaskState::Open) };
        m["TASKS 9"] = EncodeTasks(1, t);
        m["TASK a"] = EncodeTaskDelta(2, 102, 20, TaskState::Claimable);
    }
    m["TOAST b"] = EncodeToast({ ToastKind::Record, "New record", "Halls of Lightning +8 in 24:13", "leaderboards" });
    {
        KeyState k;
        k.dungeonId = 602; k.level = 8; k.affixIds = { 1, 3, 4 }; k.mode = 2; k.weeklyBestLevel = 9; k.weeklyBestDungeonId = 599;
        k.cachesReady = 1; k.cachesBanked = 2; k.keystoneItemId = 900001; k.maxLevel = 15; k.eraId = 7; k.depleted = false;
        m["KEY c"] = EncodeKey(1, k);
    }
    {
        QueueState q;
        q.state = QueueStateId::Queued; q.kind = QueueKind::Dungeon; q.activityId = 389; q.tier = 2; q.size = 3; q.queuedSec = 30;
        q.estWaitSec = 300; q.bandMin = 13; q.bandMax = 18;
        m["QUEUE d"] = EncodeQueue(2, q);
        QueueState p;
        p.state = QueueStateId::Proposal; p.kind = QueueKind::Dungeon; p.activityId = 389; p.tier = 2; p.size = 3; p.queuedSec = 40;
        p.proposalId = 77; p.timeoutSec = 40; p.bandMin = 13; p.bandMax = 18;
        QueueMember a; a.name = "Tester"; a.classId = 1; a.role = 4; a.accepted = ProposalAnswer::Accepted; a.level = 15;
        QueueMember b; b.name = "Brenna"; b.classId = 2; b.role = 2; b.accepted = ProposalAnswer::Pending; b.level = 16;
        p.members = { a, b };
        m["QUEUE e"] = EncodeQueue(3, p);
    }
    {
        KeyRunStart s;
        s.runId = 7001; s.dungeonId = 602; s.level = 8; s.affixIds = { 1, 3, 4 }; s.eraId = 7; s.countdownMs = 10000; s.timeLimitSec = 1800;
        m["MPS f"] = EncodeKeyRunStart(s);
        KeyRunState r;
        r.runId = 7001; r.elapsedMs = 1122000; r.timeLimitSec = 1800; r.deaths = 2; r.deathPenaltySec = 10; r.forcesCur = 64; r.forcesMax = 100;
        r.bossBits = 1; r.bossKillSec = { 300 }; r.chestSec = { 1260, 1440 }; r.state = KeyRunStateId::Running;
        m["MP g"] = EncodeKeyRunState(r);
        KeyRunEnd e;
        e.runId = 7001; e.result = KeyRunResultId::InTime; e.timeMs = 1453000; e.keyDelta = 1; e.newDungeonId = 599; e.newLevel = 9; e.score = 1840;
        Reward chest; chest.kind = RewardKind::Text; chest.amount = 1; chest.text = "Spoils chest";
        Reward coins; coins.kind = RewardKind::MythicCoins; coins.amount = 150;
        e.rewards = { chest, coins };
        m["MPE h"] = EncodeKeyRunEnd(e);
    }
    {
        RiftState r;
        r.runId = 8001; r.state = RiftStateId::Running; r.floor = 7; r.bossId = 3; r.bossName = "Echo of Nefarian"; r.elapsedMs = 120000;
        r.bestFloor = 18; r.rank = 42; r.deaths = 1; r.groupSize = 1;
        m["RIFT i"] = EncodeRift(r);
        RiftEnd e;
        e.runId = 8001; e.floorReached = 9; e.timeMs = 180000; e.newBest = false;
        Reward coins; coins.kind = RewardKind::MythicCoins; coins.amount = 20;
        e.rewards = { coins };
        m["RIFTE j"] = EncodeRiftEnd(e);
    }
    {
        CollectionState c;
        c.transmogOwned = 412; c.laterAgesOwned = 0; c.laterAgesTotal = 3771; c.legacySetsOwned = 3; c.legacySetsTotal = 48;
        c.tierHave = { 3, 0, 0, 0, 0, 0, 0 }; c.tierTotal = { 8, 8, 5, 9, 5, 5, 8 };
        m["COLL k"] = EncodeCollections(1, c);
    }
    {
        LegacySet s;
        s.tier = 1; s.setId = 201; s.classId = 1; s.name = "Battlegear of Might"; s.collectedBits = 56; s.outfitUnlocked = false;
        s.itemIds = { 16866, 16868, 16865, 16861, 16863, 16864, 16867, 16862 }; s.sourceDungeonIds = { 229, 329, 289, 429, 543 };
        s.lvlMin = 58; s.lvlMax = 61; s.echoBoss = "Ragnaros";
        m["SET l"] = EncodeLegacySet(s);
    }
    {
        LegacyIndex idx;
        LegacyIndexEntry a; a.itemId = 16864; a.tier = 1; a.setId = 201; a.collected = true;
        LegacyIndexEntry b; b.itemId = 16866; b.tier = 1; b.setId = 201; b.collected = false;
        idx.items = { a, b };
        m["LIDX m"] = EncodeLegacyIndex(1, idx);
        m["LCOL n"] = EncodeLegacyCollected(2, 16866, true);
    }
    {
        SeasonState s;
        s.seasonId = 1; s.warEffortPermille = 620; s.contributors = 1284; s.points = 1240; s.rankId = 2; s.nextRankId = 3; s.pointsToNextRank = 260;
        s.warEffortTitle = "Breach the Greymane Wall"; s.warEffortText = "Fill the bar together."; s.spareTokens = 3;
        s.parts = { { "Materials", 800u }, { "Bosses and Echoes", 550u } };
        SeasonRewardState a; a.rewardId = 1; a.earned = true; a.stateText = "Earned";
        SeasonRewardState b; b.rewardId = 2; b.earned = false; b.stateText = "7 / 20";
        s.rewards = { a, b };
        m["SEASON o"] = EncodeSeason(1, s);
    }
    {
        Leaderboard lb;
        lb.board = Board::Keys; lb.seasonId = 1; lb.dungeonId = 0; lb.classId = 0; lb.page = 1; lb.pages = 3;
        LeaderboardRow r1;
        r1.rank = 1; r1.dungeonId = 602; r1.value = 15; r1.timeSec = 300; r1.dateEpoch = 1792645125;
        r1.members = { { "Aldric", 1u }, { "Brenna", 2u }, { "Corwin", 5u }, { "Dalia", 8u }, { "Eamon", 11u } };
        LeaderboardRow r2;
        r2.rank = 2; r2.dungeonId = 599; r2.value = 14; r2.timeSec = 200; r2.dateEpoch = 1792641525; r2.members = { { "Fenna", 3u } };
        lb.rows = { r1, r2 };
        m["LB p"] = EncodeLeaderboard(lb);
        LeaderboardMe me;
        me.board = Board::Keys; me.rank = 42; me.topPercent = 12; me.value = 9; me.dungeonId = 602; me.timeSec = 154; me.barPermille = 580;
        m["LBME q"] = EncodeLeaderboardMe(me);
        FirstsList f;
        f.entries = { { "echo", "Echo of Ragnaros defeated", "Ironvow", 1792562325u }, { "key", "First timed +15", "Dalia's group", 1792216725u } };
        m["FIRSTS r"] = EncodeFirsts(f);
    }
    {
        BoardState b;
        b.shards = 1260; b.bountyId = 55; b.bountyDungeonId = 189; b.bountyState = BountyState::Open; b.bountyRewardText = "50 Shards";
        b.firstRunBonus = true;
        BoardDungeon d1; d1.dungeonId = 389; d1.chapter = 1; d1.lvlMin = 13; d1.lvlMax = 18; d1.tierBits = 15; d1.bestScore = 900; d1.bestTier = 1;
        d1.recordScore = 2400; d1.recordName = "Aldric"; d1.locked = false;
        BoardDungeon d2; d2.dungeonId = 36; d2.chapter = 1; d2.lvlMin = 15; d2.lvlMax = 21; d2.tierBits = 3; d2.locked = false;
        BoardDungeon d3; d3.dungeonId = 189; d3.chapter = 2; d3.lvlMin = 30; d3.lvlMax = 40; d3.tierBits = 1; d3.bestScore = 1500; d3.bestTier = 0;
        d3.recordScore = 3100; d3.recordName = "Brenna"; d3.locked = false;
        b.dungeons = { d1, d2, d3 };
        m["BOARD 3k"] = EncodeBoard(4, b);
    }
    {
        CaseList list;
        list.caseItemIds = { 990001, 990002 };
        m["CASES 4"] = EncodeCases(list);
        CaseInfo c;
        c.caseItemId = 990001; c.title = "Glaive Case"; c.text = "Unlock it to receive one of the items below.";
        c.rewards = { { 32837, 1, 1200, 4 }, { 32838, 1, 400, 5 } };
        m["CASE 5"] = EncodeCase(c);
        Unbox u;
        u.caseItemId = 990001; u.rewardIndex = 2; u.itemId = 32838; u.count = 1; u.nonce = 7;
        m["UNBOX 6"] = EncodeUnbox(u);
    }
    {
        CampState n;   // not at a fire: warmth and food on, the glide on cooldown
        n.state = CampStateId::None; n.cooldownSec = 640; n.warmthSec = 1500; n.xpPct = 15; n.glideSec = 95u; n.repair = false; n.fed = true;
        m["CAMPST 7"] = EncodeCampState(n);
        CampState r;   // just made camp: resting at the own fire, may place two objects, a blacksmith
        r.state = CampStateId::Resting; r.settleSec = 60; r.fireSec = 900; r.mine = true; r.cooldownSec = 900; r.xpPct = 5;
        r.place = { { 164, 2 }, { 197, 3 } }; r.glideSec = 0u; r.repair = true; r.fed = true;
        m["CAMPST 8"] = EncodeCampState(r);
        CampState c;   // settled, after placing the anvil next to someone's alchemy object
        c.state = CampStateId::Camping; c.fireSec = 700; c.mine = true; c.cooldownSec = 880; c.warmthSec = 1800; c.xpPct = 15;
        c.objects = { { 164, 2, true }, { 171, 1, false } }; c.glideSec = 0u; c.repair = true; c.fed = true;
        m["CAMPST 9"] = EncodeCampState(c);
        ErrorReply g;
        g.op = IntentType::Glide; g.seq = 26; g.code = "glide_cooldown"; g.text = "You can glide again in 95 s.";
        m["ERR s"] = EncodeError(g);
        ErrorReply rp;
        rp.op = IntentType::Repair; rp.seq = 27; rp.code = "repair_gold"; rp.text = "You cannot pay for the repair (2g 10s 0c).";
        m["ERR t"] = EncodeError(rp);
    }
    {
        // Bleakhold Royale (section 17)
        QueueState q;
        q.state = QueueStateId::Queued; q.kind = QueueKind::Royale; q.activityId = 901; q.tier = 0; q.size = 1;
        q.queuedSec = 12; q.bandMin = 80; q.bandMax = 80; q.queued = 13; q.minPlayers = 20; q.maxPlayers = 40;
        q.matchesRunning = 1;
        m["QUEUE f"] = EncodeQueue(4, q);
        q.state = QueueStateId::Proposal; q.queuedSec = 95; q.proposalId = 412; q.timeoutSec = 15; q.queued = 24;
        q.accepted = 0; q.proposalSize = 24;
        m["QUEUE g"] = EncodeQueue(5, q);
        QueueState in;
        in.state = QueueStateId::InRun; in.kind = QueueKind::Royale; in.activityId = 901; in.tier = 0; in.size = 1;
        in.bandMin = 80; in.bandMax = 80; in.minPlayers = 20; in.maxPlayers = 40; in.matchesRunning = 2;
        m["QUEUE h"] = EncodeQueue(6, in);
        RoyaleMap mp;
        mp.mapId = 901; mp.minX = -1066; mp.maxX = 533; mp.minY = -1066; mp.maxY = 533;
        mp.lobbyX = 455; mp.lobbyY = 455; mp.lobbyR = 32; mp.boundHalf = 750; mp.centerX = -267; mp.centerY = -267;
        mp.pois = { { 1, RoyalePoiKind::Landmark, -266, -266, 88, "The Bleak Hold" },
            { 2, RoyalePoiKind::Landmark, 120, 80, 62, "Harrow Farm" } };
        m["ROYM i"] = EncodeRoyaleMap(mp);
        RoyaleState st;
        st.matchId = 7001; st.phase = RoyalePhase::Countdown; st.phaseMsLeft = 45000; st.alive = 24; st.total = 24;
        st.me = RoyaleMe::Lobby; st.kills = 0; st.stage = 0; st.curX = -267; st.curY = -267; st.curR = 1080;
        st.dmgPermille = 0; st.myX = 450; st.myY = 452; st.stages = 6;
        m["ROYS j"] = EncodeRoyaleState(st);
        st.phaseMsLeft = 41000; st.pinX = 104; st.pinY = 96;
        m["ROYS k"] = EncodeRoyaleState(st);
        RoyaleObjects ob;
        ob.matchId = 7001; ob.full = true;
        RoyaleObject s1;
        s1.objId = 1; s1.kind = RoyaleObjectKind::ShadowSight; s1.x = -266; s1.y = -266; s1.msLeft = 90000u;
        RoyaleObject s2;
        s2.objId = 2; s2.kind = RoyaleObjectKind::ShadowSight; s2.x = -712; s2.y = 48; s2.msLeft = 90000u;
        RoyaleObject b3;
        b3.objId = 3; b3.kind = RoyaleObjectKind::Buff; b3.subtype = static_cast<uint32_t>(RoyaleBuff::Speed);
        b3.x = 120; b3.y = 80; b3.state = RoyaleObjectState::Ready;
        ob.objects = { s1, s2, b3 };
        m["ROYO l"] = EncodeRoyaleObjects(ob);
        RoyaleEvent d;
        d.kind = RoyaleEventKind::SupplyIncoming; d.value = 0; d.x = -80; d.y = -180; d.msLeft = 20000u;
        m["ROYV m"] = EncodeRoyaleEvent(d);
        RoyaleKill k;
        k.killerName = "Aldric"; k.killerClassId = 1; k.victimName = "Brenna"; k.victimClassId = 8;
        k.cause = RoyaleCause::Player; k.aliveAfter = 23; k.killerKills = 1;
        m["ROYK n"] = EncodeRoyaleKill(k);
        RoyaleResult r;
        r.matchId = 7001; r.placement = 12; r.total = 24; r.kills = 1; r.damage = 18400; r.healing = 0;
        r.survivedSec = 214; r.rewarded = true;
        Reward place; place.kind = RewardKind::Honor; place.amount = 70; place.text = "Placement";
        Reward kill; kill.kind = RewardKind::Honor; kill.amount = 25; kill.text = "1 elimination";
        Reward shards; shards.kind = RewardKind::Shards; shards.amount = 5; shards.text = "Placement";
        r.rewards = { place, kill, shards };
        m["ROYE o"] = EncodeRoyaleResult(r);
        RoyaleEvent w;
        w.kind = RoyaleEventKind::Winner; w.value = 7; w.name = "Dalia";
        m["ROYV p"] = EncodeRoyaleEvent(w);
        ErrorReply g;
        g.op = IntentType::Glide; g.seq = 12; g.code = RoyaleErr::GlideHere.code; g.text = RoyaleErr::GlideHere.text;
        m["ERR q"] = EncodeError(g);
    }
    {
        // the battleground kill announcer (sections 17 and 18)
        auto ann = [](char const* killer, uint32_t kc, char const* victim, uint32_t vc, BgMultiKill mk, BgStreak st) {
            BgAnnounce a;
            a.killerName = killer; a.killerClassId = kc; a.victimName = victim; a.victimClassId = vc;
            a.multi = mk; a.streak = st;
            return EncodeBgAnnounce(a);
        };
        m["BGANN u"] = ann("Aldric", 1, "Brenna", 8, BgMultiKill::None, BgStreak::FirstBlood);
        m["BGANN v"] = ann("Aldric", 1, "Brenna", 8, BgMultiKill::None, BgStreak::FirstBlood);
        m["BGANN w"] = ann("Aldric", 1, "Corwin", 5, BgMultiKill::Double, BgStreak::None);
        m["BGANN x"] = ann("Aldric", 1, "Dalia", 11, BgMultiKill::Triple, BgStreak::KillingSpree);
        m["BGANN y"] = ann("Garrick Stormwind", 4, "Aldric", 1, BgMultiKill::None, BgStreak::Dominating);
        m["BGANN z"] = ann("Eamon", 9, "Fenna", 3, BgMultiKill::Rampage, BgStreak::HolyShit);
    }
    {
        // arena seasons and the 1v1 ladder (section 20)
        ArenaState a;
        a.seasonId = 1; a.state = ArenaStateId::Live; a.startEpoch = 1793318400u; a.endEpoch = 1800576000u;
        a.nextStartEpoch = 1800748800u; a.ratedOpen = true; a.oneTeamCostCopper = 0u; a.seasonName = "Arena Season 1";
        a.seasons = { { 1, "Arena Season 1", SeasonStateId::Current, 1793318400u, 1800576000u },
            { 2, "Arena Season 2", SeasonStateId::Upcoming, 1800748800u, 1808006400u } };
        auto bracket = [](uint32_t br, uint32_t rating, uint32_t rank, uint32_t size, uint32_t games, uint32_t wins,
                           uint32_t wg, uint32_t ww, uint32_t personal, uint32_t recent, uint32_t tier, uint32_t next,
                           uint32_t toNext, uint32_t missing, char const* team) {
            ArenaBracketState b;
            b.bracket = br; b.hasTeam = true; b.rating = rating; b.ladderRank = rank; b.ladderSize = size;
            b.seasonGames = games; b.seasonWins = wins; b.weekGames = wg; b.weekWins = ww; b.personalRating = personal;
            b.recentGames = recent; b.tierId = tier; b.nextTierId = next; b.ratingToNext = toNext;
            b.missingMask = missing; b.teamName = team;
            return b;
        };
        a.brackets = { bracket(1, 1734, 12, 48, 61, 38, 9, 6, 1734, 14, 3, 4, 66, 0, "Aldric"),
            bracket(3, 1912, 4, 22, 44, 30, 12, 8, 1890, 12, 4, 5, 163, ArenaMissWins, "Ironvow Wardens") };
        auto cut = [](uint32_t tier, uint32_t slots, uint32_t rank, uint32_t rating, uint32_t floor) {
            ArenaCutoff c;
            c.bracket = 3; c.tierId = tier; c.slots = slots; c.cutRank = rank; c.cutRating = rating; c.floor = floor;
            return c;
        };
        a.cutoffs = { cut(6, 1, 1, 2140, 2000), cut(5, 2, 2, 2075, 2000), cut(4, 4, 4, 1912, 1800),
            cut(3, 4, 4, 1912, 1650), cut(2, 8, 8, 1702, 1500), cut(1, 22, 22, 1310, 1300) };
        a.ladders = { { 1, 48, true, true }, { 3, 22, true, true } };
        auto match = [](bool won, int32_t change, char const* who, uint32_t at, ArenaVerdict v, ArenaReason why) {
            ArenaMatch x;
            x.bracket = 1; x.won = won; x.ratingChange = change; x.opponent = who; x.endEpoch = at; x.verdict = v;
            x.reason = why;
            return x;
        };
        a.matches = { match(true, 14, "Brenna", 1793900000u, ArenaVerdict::Normal, ArenaReason::None),
            match(false, -11, "Corwin", 1793899000u, ArenaVerdict::Normal, ArenaReason::None),
            match(true, 0, "Dalia", 1793898000u, ArenaVerdict::NotCounted, ArenaReason::Network),
            match(true, 7, "Eamon", 1793897000u, ArenaVerdict::Reduced, ArenaReason::Repeat) };
        m["ARENA 2a"] = EncodeArena(a);
        ArenaState fin;
        fin.seasonId = 1; fin.state = ArenaStateId::FinalStandings; fin.startEpoch = 1793318400u;
        fin.endEpoch = 1800576000u; fin.nextStartEpoch = 1800748800u; fin.ratedOpen = false; fin.oneTeamCostCopper = 0u;
        fin.seasonName = "Arena Season 1";
        fin.brackets = { bracket(1, 1734, 12, 48, 61, 38, 0, 0, 1734, 14, 3, 4, 66, ArenaMissReview, "Aldric") };
        ArenaFinal f;
        f.bracket = 1; f.finalRank = 12; f.finalRating = 1734; f.finalTierId = 3u; f.grant = ArenaGrant::Held;
        fin.finals = { f };
        m["ARENA 2b"] = EncodeArena(fin);

        Leaderboard lb;
        lb.board = Board::Arena; lb.seasonId = 1u; lb.dungeonId = 3u; lb.classId = 0u; lb.page = 1; lb.pages = 3;
        auto row = [](uint32_t rank, int64_t rating, uint32_t last, std::vector<LeaderboardMember> members,
                       char const* team, uint32_t wins, uint32_t games, uint32_t tier, Opt<uint32_t> flags) {
            LeaderboardRow r;
            r.rank = rank; r.dungeonId = 3u; r.value = rating; r.dateEpoch = last; r.members = std::move(members);
            r.label = team; r.seasonWins = wins; r.seasonGames = games; r.tierId = tier; r.flags = flags;
            return r;
        };
        lb.rows = { row(1, 2140, 1793896400u, { { "Brenna", 2u }, { "Corwin", 5u }, { "Dalia", 8u } }, "Dawnbreakers", 61, 70,
                        6, std::nullopt),
            row(2, 2075, 1793890000u, { { "Eamon", 11u }, { "Fenna", 3u }, { "Garrick Stormwind", 4u } }, "The Unbowed", 55,
                68, 5, std::nullopt),
            row(3, 1990, 1793200000u, { { "Hale", 7u }, { "Isolde", 9u }, { "Jorund", 6u } }, "Ashen Pact", 40, 52, 4,
                ArenaInactive) };
        m["LB 2d"] = EncodeLeaderboard(lb);
        LeaderboardMe me;
        me.board = Board::Arena; me.rank = 4u; me.topPercent = 19u; me.value = 1912; me.dungeonId = 3u;
        me.barPermille = 407u; me.label = "Duelist"; me.topPermille = 182u; me.tierId = 4u;
        m["LBME 2e"] = EncodeLeaderboardMe(me);

        Definitions v;
        v.arenaTiers = { { 1, "Combatant", "9D9D9D", "Enough season games and 1300 rating." },
            { 5, "Gladiator", "FF8000", "The top 0.5% of the ladder with 50 wins." } };
        m["DEF 2f"] = EncodeDefinitions(v, 7).at(0);
        Definitions q;
        auto reward = [](uint32_t id, uint32_t season, uint32_t tier, char kind, uint32_t entry, uint32_t count,
                          char const* text) {
            ArenaRewardDef r;
            r.id = id; r.seasonId = season; r.bracket = 3; r.tierId = tier; r.kind = kind; r.entry = entry; r.count = count;
            r.text = text;
            return r;
        };
        q.arenaRewards = { reward(101, 0, 2, 'T', 2090, 1, "Challenger"), reward(105, 1, 5, 'M', 30609, 1, "Swift Nether Drake"),
            reward(110, 0, 1, 'C', 0, 150, "150 Dungeon Shards") };
        m["DEF 2g"] = EncodeDefinitions(q, 7).at(0);

        QueueState qa;
        qa.state = QueueStateId::Queued; qa.kind = QueueKind::Arena; qa.activityId = 1u; qa.tier = 1u; qa.size = 1u;
        qa.queuedSec = 8u; qa.estWaitSec = 95u;
        m["QUEUE 2i"] = EncodeQueue(7, qa);
        ErrorReply e;
        e.op = IntentType::QueueJoin; e.seq = 91; e.code = ArenaErr::Closed.code;
        e.text = "Rated arena opens again when Arena Season 2 starts.";
        m["ERR 2k"] = EncodeError(e);
    }
    return m;
}

TEST("every S> example of the document is what the C++ encoders produce")
{
    std::vector<std::string> lines = DocLines("S>");
    CHECK(lines.size() >= 25);
    std::map<std::string, std::string> const built = BuiltExamples();
    std::map<std::string, std::vector<std::string>> parts;   // "OP SEQ" -> payload parts in order
    std::map<std::string, std::size_t> totals;
    for (std::string const& body : lines)
    {
        CHECK_MSG(body.size() <= MaxServerBody, body);
        CHECK_MSG(body.find('\0') == std::string::npos, body);
        // header check, written independently of the client and server parsers
        std::vector<std::string> sp = SplitStr(body, ' ');
        CHECK_MSG(sp.size() >= 4 && sp[0] == "1" && IsOpName(sp[1]) && ParseBase36(sp[2]), body);
        if (sp.size() < 4)
            continue;
        std::vector<std::string> pt = SplitStr(sp[3], '/');
        CHECK_MSG(pt.size() == 2, body);
        std::size_t const part = std::stoul(pt[0]);
        std::size_t const total = std::stoul(pt[1]);
        CHECK_MSG(part >= 1 && part <= total && total <= 99, body);
        std::string const key = sp[1] + " " + sp[2];
        std::size_t const head = sp[0].size() + sp[1].size() + sp[2].size() + sp[3].size() + 3;
        std::string const payload = body.size() > head ? body.substr(head + 1) : std::string();
        parts[key].resize(total);
        parts[key][part - 1] = payload;
        totals[key] = total;
    }
    for (auto const& [key, list] : parts)
    {
        std::string payload;
        for (std::string const& p : list)
            payload += p;
        auto it = built.find(key);
        CHECK_MSG(it != built.end(), "the test builds the example " + key);
        if (it == built.end())
            continue;
        CHECK_MSG(Norm(it->second) == Norm(payload), key + "\n      doc:   " + payload + "\n      built: " + it->second);
    }
    for (auto const& [key, payload] : built)
        CHECK_MSG(parts.count(key), "built example " + key + " is in the document");
}

int main(int argc, char** argv)
{
    if (argc < 2)
    {
        std::fprintf(stderr, "usage: bh_unit <repo root>\n");
        return 2;
    }
    g_repo = argv[1];
    return bhtest::RunAll();
}
