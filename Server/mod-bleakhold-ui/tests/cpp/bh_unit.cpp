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
#include "../../src/BleakholdEmoji.h"

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
