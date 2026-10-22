// mod-bleakhold-ui tests: every intent captured from the real addon (tests/lua/test_capture_intents.lua)
// through the module's parser and its Endpoint (rate limits) with the timing the client used.
//
//   bh_intents <captured.txt>       lines: "BHC" TAB seconds TAB body
//
// SPDX-License-Identifier: GPL-2.0-or-later

#include "bh_check.h"

#include "BleakholdCodec.h"
#include "BleakholdEndpoint.h"
#include "BleakholdIntent.h"

#include <cmath>
#include <map>

using namespace Bleakhold;
using namespace Bleakhold::Proto;

struct Captured
{
    uint64_t ms;
    std::string body;
};

static std::vector<Captured> g_msgs;

TEST("every captured intent parses and re-encodes byte for byte")
{
    CHECK(g_msgs.size() >= 40);
    bool ops[static_cast<std::size_t>(IntentType::Count)] = {};
    bool topics[static_cast<std::size_t>(Topic::Count)] = {};
    for (Captured const& c : g_msgs)
    {
        CHECK_MSG(c.body.size() <= MaxClientBody, c.body);
        Intent in;
        DropReason r = ParseClientMessage("BHc\t" + c.body, in);
        CHECK_MSG(r == DropReason::None, c.body + " -> " + DropReasonName(r));
        if (r != DropReason::None)
            continue;
        CHECK_EQ(EncodeIntentBody(in), c.body);
        ops[static_cast<std::size_t>(in.type)] = true;
        for (TopicRequest const& t : in.topics)
            topics[static_cast<std::size_t>(t.topic)] = true;
    }
    for (std::size_t i = 0; i < static_cast<std::size_t>(IntentType::Count); ++i)
        CHECK_MSG(ops[i], std::string("captured ") + IntentOpName(static_cast<IntentType>(i)));
    for (std::size_t i = 0; i < static_cast<std::size_t>(Topic::Count); ++i)
        CHECK_MSG(topics[i], std::string("captured GET ") + TopicName(static_cast<Topic>(i)));
}

TEST("replayed with the client's timing, the server's limits never drop legitimate traffic")
{
    Endpoint ep;
    std::map<std::string, int> verdicts;
    bool first = true;
    for (Captured const& c : g_msgs)
    {
        Intent in;
        ReceiveResult r = ep.Receive("BHc\t" + c.body, c.ms, in);
        if (first)
        {
            CHECK_MSG(r.verdict == Verdict::Accepted && in.type == IntentType::Hello, "the client starts with HELLO");
            first = false;
        }
        std::string const key = r.verdict == Verdict::Accepted ? "accepted" : (r.verdict == Verdict::Refused ? "refused/" : "dropped/") +
            std::string(r.verdict == Verdict::Accepted ? "" : DropReasonName(r.reason));
        ++verdicts[key];
        // the client throttles itself below the server's bucket, never sends before HELLO and never
        // repeats a GET topic within 3 s: none of these may happen
        CHECK_MSG(r.reason != DropReason::Flood && r.reason != DropReason::Muted && r.reason != DropReason::NoHello &&
            !r.muteStarted, c.body + " -> " + DropReasonName(r.reason));
        CHECK_MSG(!(in.type == IntentType::Get && r.verdict != Verdict::Accepted), "GET dropped: " + c.body);
    }
    std::printf("  replay of %zu captured intents:", g_msgs.size());
    for (auto const& [k, n] : verdicts)
        std::printf(" %s=%d", k.c_str(), n);
    std::printf("\n");
}

int main(int argc, char** argv)
{
    if (argc < 2)
    {
        std::fprintf(stderr, "usage: bh_intents <captured.txt>\n");
        return 2;
    }
    std::string const text = bhtest::ReadFile(argv[1]);
    std::size_t start = 0;
    while (start < text.size())
    {
        std::size_t end = text.find('\n', start);
        if (end == std::string::npos)
            end = text.size();
        std::string const line = text.substr(start, end - start);
        start = end + 1;
        if (line.compare(0, 4, "BHC\t") != 0)
            continue;
        std::size_t const tab = line.find('\t', 4);
        if (tab == std::string::npos)
            continue;
        double const sec = std::stod(line.substr(4, tab - 4));
        g_msgs.push_back({ static_cast<uint64_t>(std::llround(sec * 1000.0)), line.substr(tab + 1) });
    }
    std::printf("bh_intents: %zu captured intents\n", g_msgs.size());
    return bhtest::RunAll();
}
