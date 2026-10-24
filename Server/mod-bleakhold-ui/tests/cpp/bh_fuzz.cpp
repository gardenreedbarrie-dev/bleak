// mod-bleakhold-ui tests: fuzzing of everything a client can reach, under ASan/UBSan.
//
// For every input:
//   * ParseClientMessage() must agree with an independent reading of the document written with
//     std::regex (differential check), and an accepted message must re-encode to a message that parses
//     to the same intent;
//   * the Endpoint (rate limits, handshake, duplicates) gets the input at a time taken from the input
//     and may never accept more than its token bucket allows;
//   * EscapeText/BuildFrames/PayloadWriter keep their invariants for the input used as server text;
//   * the Bleakhold Royale encoders (section 17) keep their field and record counts with the input as every name.
//
// Standalone (mutation driver):  bh_fuzz [iterations] [seed] [corpus files...]
// libFuzzer:                     build with -DBH_LIBFUZZER -fsanitize=fuzzer (see run_tests.sh)
//
// SPDX-License-Identifier: GPL-2.0-or-later

#include "BleakholdCodec.h"
#include "BleakholdEndpoint.h"
#include "BleakholdIntent.h"
#include "BleakholdMessages.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <fstream>
#include <random>
#include <regex>
#include <sstream>
#include <string>
#include <vector>

using namespace Bleakhold;
using namespace Bleakhold::Proto;

namespace
{
    [[noreturn]] void Die(std::string const& what, std::string const& input)
    {
        std::fprintf(stderr, "bh_fuzz: %s\n  input (%zu bytes): ", what.c_str(), input.size());
        for (unsigned char c : input)
        {
            if (c >= 0x20 && c < 0x7F && c != '\\')
                std::fputc(c, stderr);
            else
                std::fprintf(stderr, "\\x%02X", c);
        }
        std::fputc('\n', stderr);
        std::abort();
    }

    // ---------------------------------------------------------------------------------------------
    // Reference reading of section 3 and 6, independent of BleakholdIntent.cpp
    // ---------------------------------------------------------------------------------------------
    std::vector<std::string> Split(std::string const& s, char sep)
    {
        std::vector<std::string> out;
        std::string cur;
        for (char c : s)
        {
            if (c == sep)
            {
                out.push_back(cur);
                cur.clear();
            }
            else
                cur += c;
        }
        out.push_back(cur);
        return out;
    }

    bool RefInt(std::string const& f, long long lo, long long hi)
    {
        static std::regex const re("-?[0-9]{1,15}");
        if (!std::regex_match(f, re))
            return false;
        long long const v = std::stoll(f);
        return v >= lo && v <= hi;
    }

    bool RefToken(std::string const& f, std::size_t max)
    {
        static std::regex const re("[A-Za-z0-9_.-]+");
        return !f.empty() && f.size() <= max && std::regex_match(f, re);
    }

    constexpr long long I32 = 2147483647;

    bool RefFields(std::string const& op, std::string const& payload)
    {
        if (op == "GET")
        {
            if (payload.empty())
                return false;
            std::vector<std::string> recs = Split(payload, ';');
            if (recs.size() > 8)
                return false;
            static std::regex const plain(
                "WEEK|ERA|TASKS|KEY|BOARD|QUEUE|COLL|LIDX|SEASON|FIRSTS|MPLUS|RIFT|CASES|CAMPST|ROYS|ROYM");
            for (std::string const& r : recs)
            {
                std::vector<std::string> f = Split(r, ',');
                if (f.size() == 1 && std::regex_match(f[0], plain))
                    continue;
                if (f.size() == 3 && f[0] == "SET" && RefInt(f[1], 0, I32) && RefInt(f[2], 0, I32))
                    continue;
                if (f.size() == 2 && f[0] == "DEF" && RefInt(f[1], 0, 0))
                    continue;
                if (f.size() == 2 && f[0] == "CASE" && RefInt(f[1], 1, I32))
                    continue;
                return false;
            }
            return true;
        }
        if (payload.find(';') != std::string::npos)
            return false;
        std::vector<std::string> f;
        if (!payload.empty())
            f = Split(payload, ',');
        auto n = [&](std::size_t k) { return f.size() == k; };
        if (op == "HELLO")
            return n(4) && RefInt(f[0], 1, 999) && RefToken(f[1], 16) && RefInt(f[2], 0, I32) && RefToken(f[3], 8);
        if (op == "TCLAIM" || op == "TREROLL" || op == "BCLAIM" || op == "OUTFIT")
            return n(1) && RefInt(f[0], 1, I32);
        if (op == "QJOIN")
        {
            if (!n(5) || (f[0] != "D" && f[0] != "R" && f[0] != "B") || !RefInt(f[1], 0, I32) || !RefInt(f[2], 0, 3) ||
                !RefInt(f[3], 1, 7) || !RefInt(f[4], 1, 5))
                return false;
            long long const activity = std::stoll(f[1]);
            if (f[0] == "B")   // Bleakhold Royale: a mode id, no tier, solo (section 17)
                return activity != 0 && std::stoll(f[2]) == 0 && std::stoll(f[4]) == 1;
            return f[0] == "R" ? activity == 0 : activity != 0;
        }
        if (op == "QLEAVE" || op == "KSTART" || op == "KCANCEL" || op == "WEHANDIN" || op == "GLIDE" ||
            op == "REPAIR" || op == "RDEPLOY")
            return n(0);
        if (op == "RDROP")   // integer world yards, may be negative
            return n(2) && RefInt(f[0], -17067, 17067) && RefInt(f[1], -17067, 17067);
        if (op == "RSPEC")
            return n(1) && RefInt(f[0], 0, 2);
        if (op == "QREPLY")
            return n(2) && RefInt(f[0], 1, I32) && RefInt(f[1], 0, 1);
        if (op == "KMODE")
            return n(1) && RefInt(f[0], 0, 2);
        if (op == "LBQ")
            return n(5) && (f[0] == "K" || f[0] == "R" || f[0] == "E" || f[0] == "F") && RefInt(f[1], 0, I32) && RefInt(f[2], 0, I32) &&
                RefInt(f[3], 0, I32) && RefInt(f[4], 1, 999);
        if (op == "PING")
            return n(1) && RefInt(f[0], 0, I32);
        if (op == "EMOJI")
            return n(1) && RefInt(f[0], 0, 255);
        if (op == "DANCE")
            return n(1) && RefInt(f[0], 0, 1023);
        if (op == "CASEOPEN")
            return n(2) && RefInt(f[0], 1, I32) && RefInt(f[1], 0, I32);
        if (op == "CAMP")   // M, P; or O with a skill line id
            return (n(1) && (f[0] == "M" || f[0] == "P")) || (n(2) && f[0] == "O" && RefInt(f[1], 1, I32));
        return false;
    }

    bool RefAccepts(std::string const& t)
    {
        if (t.size() > 255 || t.find('\0') != std::string::npos)
            return false;
        static std::regex const head("BHc\t([0-9]{1,3}) ([A-Z]{2,8}) ([0-9a-z]{1,6}) ([0-9]{1,2})/([0-9]{1,2})(?: ([\\s\\S]*))?");
        std::smatch m;
        if (!std::regex_match(t, m, head))
            return false;
        int const ver = std::stoi(m[1].str());
        std::string const op = m[2].str();
        int const part = std::stoi(m[4].str());
        int const total = std::stoi(m[5].str());
        if (part < 1 || total < 1 || part > total || total != 1)
            return false;
        if (ver != 1 && op != "HELLO")
            return false;
        return RefFields(op, m[6].matched ? m[6].str() : std::string());
    }

    bool SameIntent(Intent const& a, Intent const& b)
    {
        return EncodeIntentPayload(a) == EncodeIntentPayload(b) && a.type == b.type && a.seq == b.seq;
    }

    // ---------------------------------------------------------------------------------------------
    // Checks
    // ---------------------------------------------------------------------------------------------
    Endpoint g_ep;
    uint64_t g_now = 1000;
    std::deque<uint64_t> g_accepted;   // times of accepted messages within the last second

    void CheckParser(std::string const& text)
    {
        Intent in;
        DropReason const r = ParseClientMessage(text, in);
        bool const ok = r == DropReason::None;
        if (ok != RefAccepts(text))
            Die(std::string("parser and reference disagree: parser says ") + DropReasonName(r), text);
        if (ok)
        {
            std::string const again = "BHc\t" + EncodeIntentBody(in);
            Intent in2;
            if (ParseClientMessage(again, in2) != DropReason::None || !SameIntent(in, in2))
                Die("an accepted message does not re-encode to the same intent", text);
            if (again.size() > text.size() && again.size() > MaxClientMessage)
                Die("re-encoding grew past the size limit", text);
        }
    }

    void CheckEndpoint(std::string const& text, unsigned char dt)
    {
        g_now += dt;
        Intent in;
        ReceiveResult r = g_ep.Receive(text, g_now, in);
        if (r.verdict == Verdict::Accepted)
        {
            if (ParseClientMessage(text, in) != DropReason::None)
                Die("the endpoint accepted a message the parser rejects", text);
            g_accepted.push_back(g_now);
            while (!g_accepted.empty() && g_now - g_accepted.front() >= 1000)
                g_accepted.pop_front();
            // bucket of 10, 5 per second: at most 10 + 5 accepted within any second
            if (g_accepted.size() > 15)
                Die("the endpoint accepted more than its token bucket allows", text);
        }
        if (r.verdict == Verdict::Accepted && !g_ep.Ready())
            Die("accepted without a handshake", text);
    }

    void CheckEncoders(std::string const& text, unsigned char k)
    {
        std::string const clean = CleanText(text);
        std::string const esc = EscapeText(text);
        for (char ch : esc)
        {
            unsigned char const c = static_cast<unsigned char>(ch);
            if (c < 0x20 || c == 0x7F || c == ';' || c == ',' || c == ':' || c == '~' || c == '|')
                Die("escaped text contains a separator or control byte", text);
        }
        std::optional<std::string> back = Unescape(esc);
        if (!back || *back != clean)
            Die("escape does not round-trip", text);
        std::size_t const cut = 1 + k % 40;   // 0 would mean "no limit"
        std::string const shortText = CleanText(text, cut);
        if (shortText.size() > cut)
            Die("CleanText exceeded its limit", text);

        // a payload of records built from the input, framed at a size taken from the input
        PayloadWriter w;
        for (int i = 0; i < 1 + k % 30; ++i)
            w.Record().Int(i).Text(text).Empty().Texts({ text, text }).Empty();
        std::string const payload = w.Take();
        std::size_t const records = Split(payload, ';').size();
        if (records != static_cast<std::size_t>(1 + k % 30))
            Die("PayloadWriter lost or added a record", text);
        std::size_t const maxBody = 64 + (static_cast<std::size_t>(k) * 7) % 937;
        std::vector<std::string> frames = BuildFrames("BOARD", k * 1000u + 1u, payload, maxBody);
        if (frames.empty())
        {
            // every part is longer than half the room (a cut after ';' is only taken in the second half)
            if (payload.size() <= 49 * (maxBody - 40) && payload.size() <= MaxAssembled)
                Die("BuildFrames gave up on a payload that fits", text);
            return;
        }
        std::string joined;
        for (std::size_t i = 0; i < frames.size(); ++i)
        {
            std::string const& f = frames[i];
            if (f.size() > maxBody)
                Die("frame over maxBody", text);
            std::size_t const sp = f.find(' ', f.find(' ', f.find(' ', 2) + 1) + 1);
            std::string part = sp == std::string::npos ? std::string() : f.substr(sp + 1);
            if (!part.empty())
            {
                if (part.back() == '%' || (part.size() >= 2 && part[part.size() - 2] == '%'))
                    Die("frame cut inside an escape", text);
                unsigned char const first = static_cast<unsigned char>(part[0]);
                if (i > 0 && first >= 0x80 && first < 0xC0)
                    Die("frame cut inside a UTF-8 sequence", text);
            }
            joined += part;
        }
        if (joined != payload)
            Die("frames do not reassemble to the payload", text);
    }

    // The input as every name of the Royale messages: it may never add or remove a field or a record, and each name
    // decodes to the input cleaned and cut to the encoder's limit.
    void CheckRoyaleEncoders(std::string const& text, unsigned char k)
    {
        auto name = [&](std::string const& field, std::size_t maxBytes, char const* what) {
            std::optional<std::string> back = Unescape(field);
            if (!back || *back != CleanText(text, maxBytes))
                Die(std::string(what) + ": the name does not decode to the cleaned input", text);
        };
        auto fields = [&](std::string const& record, std::size_t want, char const* what) {
            std::vector<std::string> f = Split(record, ',');
            if (f.size() != want)
                Die(std::string(what) + ": " + std::to_string(f.size()) + " fields instead of " + std::to_string(want),
                    text);
            return f;
        };
        auto records = [&](std::string const& payload, std::size_t want, char const* what) {
            std::vector<std::string> r = Split(payload, ';');
            if (r.size() != want)
                Die(std::string(what) + ": " + std::to_string(r.size()) + " records instead of " + std::to_string(want),
                    text);
            return r;
        };

        RoyaleKill kill;
        kill.killerName = text; kill.killerClassId = 1u; kill.victimName = text; kill.victimClassId = 8;
        kill.cause = RoyaleCause::Storm; kill.aliveAfter = k; kill.killerKills = 2u;
        // announce from the input's first byte: written only for the six codes with a credited killer (the name
        // cleans to something)
        kill.announce = static_cast<RoyaleAnnounce>(static_cast<char>(k));
        bool const announced = k != 0 && std::strchr("FDTMRG", k) && !CleanText(text, RoyaleNameBytes).empty();
        std::vector<std::string> f = fields(records(EncodeRoyaleKill(kill), 1, "ROYK")[0], announced ? 8 : 7, "ROYK");
        name(f[0], RoyaleNameBytes, "ROYK killer");
        name(f[2], RoyaleNameBytes, "ROYK victim");
        if (announced && f[7] != std::string(1, static_cast<char>(k)))
            Die("ROYK: the announce field is not the code given", text);

        RoyaleState st;
        st.watchName = text; st.pinX = -17067; st.myX = -1; st.myY = static_cast<int32_t>(k);
        f = fields(records(EncodeRoyaleState(st), 1, "ROYS")[0], 23, "ROYS");
        name(f[20], RoyaleNameBytes, "ROYS watchName");

        RoyaleMap mp;
        mp.pois = { { 1, RoyalePoiKind::Landmark, -1, 1, 2, text }, { 2, RoyalePoiKind::Lobby, 0, 0, k, text } };
        std::vector<std::string> r = records(EncodeRoyaleMap(mp), 3, "ROYM");
        fields(r[0], 11, "ROYM header");
        for (std::size_t i = 1; i < r.size(); ++i)
        {
            // the name is the last field: an empty one is left out
            bool const empty = CleanText(text, 40).empty();
            f = fields(r[i], empty ? 5 : 6, "ROYM place");
            if (!empty)
                name(f[5], 40, "ROYM place");
        }

        RoyaleEvent ev;
        ev.kind = RoyaleEventKind::Winner; ev.value = k; ev.x = 1; ev.y = -1; ev.msLeft = 5u; ev.name = text;
        f = Split(records(EncodeRoyaleEvent(ev), 1, "ROYV")[0], ',');
        if (f.size() != 6 && !(f.size() == 5 && CleanText(text, RoyaleNameBytes).empty()))
            Die("ROYV: wrong field count", text);
        if (f.size() == 6)
            name(f[5], RoyaleNameBytes, "ROYV name");

        RoyaleResult res;
        res.matchId = 1; res.placement = 1; res.total = 2; res.winnerName = text; res.rewarded = true;
        Reward rw; rw.kind = RewardKind::Honor; rw.amount = 25u; rw.itemId = 0u; rw.text = text;
        res.rewards = { rw, rw };
        r = records(EncodeRoyaleResult(res), 3, "ROYE");
        f = fields(r[0], 11, "ROYE");
        name(f[7], RoyaleNameBytes, "ROYE winnerName");
        if (Split(r[1], ',').size() > 4 || Split(r[1], ',')[0] != "H")
            Die("ROYE: wrong reward record", text);
    }

    void FuzzOne(uint8_t const* data, std::size_t size)
    {
        std::string const raw(reinterpret_cast<char const*>(data), size);
        unsigned char const k = size ? data[0] : 0;
        CheckParser(raw);
        CheckParser("BHc\t" + raw);
        CheckEndpoint("BHc\t" + raw, k);
        CheckEndpoint(raw, static_cast<unsigned char>(k >> 3));
        CheckEncoders(raw, k);
        CheckRoyaleEncoders(raw, k);
    }

#ifndef BH_LIBFUZZER
    // ---------------------------------------------------------------------------------------------
    // Standalone mutation driver
    // ---------------------------------------------------------------------------------------------
    std::vector<std::string> Seeds()
    {
        return {
            "1 HELLO 1 1/1 1,1.0.0,0,enUS", "1 GET 2 1/1 WEEK;ERA;TASKS;KEY;QUEUE;MPLUS;LIDX", "1 GET 3 1/1 SET,1,2", "1 GET 4 1/1 DEF,0",
            "1 TCLAIM 4 1/1 103", "1 TREROLL 5 1/1 101", "1 QJOIN 6 1/1 D,389,2,4,3", "1 QJOIN 7 1/1 R,0,0,4,1", "1 QREPLY 8 1/1 77,1",
            "1 QLEAVE 9 1/1", "1 KMODE a 1/1 2", "1 KSTART b 1/1", "1 KCANCEL c 1/1", "1 BCLAIM d 1/1 55", "1 WEHANDIN e 1/1",
            "1 OUTFIT f 1/1 201", "1 LBQ g 1/1 K,1,0,0,2", "1 PING h 1/1 12345", "1 EMOJI i 1/1 7", "1 DANCE j 1/1 5",
            "1 GET k 1/1 CASES;CASE,990001", "1 CASEOPEN l 1/1 990001,7", "1 WEEK 2s 1/1 3,4",
            "1 GET m 1/1 CAMPST", "1 CAMP n 1/1 M", "1 CAMP o 1/1 O,164", "1 CAMP p 1/1 P", "1 GLIDE q 1/1", "1 REPAIR r 1/1",
            "1 GET s 1/1 ROYS;ROYM", "1 QJOIN t 1/1 B,901,0,4,1", "1 RDROP u 1/1 -412,96", "1 RDEPLOY v 1/1",
            "1 RSPEC w 1/1 2", "1 RDROP x 1/1 -17067,17067", "2 HELLO 1 1/1 2,2.0,7,deDE",
        };
    }

    std::string Mutate(std::string s, std::vector<std::string> const& pool, std::mt19937& rng)
    {
        static char const dict[] = { ',', ';', ':', '~', '%', ' ', '/', '\t', '\0', '-', '+', '0', '1', '9', 'A', 'Z', 'a', 'z', '.', '_',
            static_cast<char>(0x80), static_cast<char>(0xC3), static_cast<char>(0xFF), '\n', 'E', 'x' };
        static char const* const words[] = { "2147483647", "2147483648", "-1", "0", "00000000000000000001", "999", "1000", "SET", "DEF", "WEEK", "CASE", "CASES", "CAMPST", "CAMP", "GLIDE", "REPAIR", "O,", "M", "P", "O",
            "HELLO", "GET", "BHc\t", "BHs\t", "1/1", "1/2", "99/99", "zzzzzz", "%00", "%2C", "\xC3\xA9", ";;", ",,",
            "R,0", "D,0", "B,", "B,901", "RDROP", "RDEPLOY", "RSPEC", "ROYS", "ROYM", "-17067", "17068", "-0", "--1" };
        int const steps = 1 + static_cast<int>(rng() % 4);
        for (int i = 0; i < steps; ++i)
        {
            std::size_t const pos = s.empty() ? 0 : rng() % (s.size() + 1);
            switch (rng() % 9)
            {
                case 0: if (!s.empty()) s[rng() % s.size()] ^= static_cast<char>(1u << (rng() % 8)); break;
                case 1: s.insert(pos, 1, dict[rng() % sizeof(dict)]); break;
                case 2: if (!s.empty()) s.erase(rng() % s.size(), 1 + rng() % 4); break;
                case 3: s.insert(pos, words[rng() % (sizeof(words) / sizeof(words[0]))]); break;
                case 4: if (!s.empty()) { std::size_t a = rng() % s.size(); s.insert(pos, s.substr(a, 1 + rng() % 16)); } break;
                case 5: { std::string const& o = pool[rng() % pool.size()]; s = s.substr(0, pos) + o.substr(rng() % (o.size() + 1)); break; }
                case 6: s.resize(s.empty() ? 0 : rng() % (s.size() + 1)); break;
                case 7: s.insert(pos, std::to_string(static_cast<int64_t>(rng()) * ((rng() & 1) ? -1 : 1) * static_cast<int64_t>(rng() % 100000))); break;
                default: if (!s.empty()) s[rng() % s.size()] = static_cast<char>(rng() % 256); break;
            }
            if (s.size() > 400)
                s.resize(400);
        }
        return s;
    }
#endif
}

#ifdef BH_LIBFUZZER
extern "C" int LLVMFuzzerTestOneInput(uint8_t const* data, std::size_t size)
{
    FuzzOne(data, size);
    return 0;
}
#else
int main(int argc, char** argv)
{
    long const iterations = argc > 1 ? std::atol(argv[1]) : 200000;
    unsigned const seed = argc > 2 ? static_cast<unsigned>(std::atol(argv[2])) : 1u;
    std::vector<std::string> pool = Seeds();
    for (int i = 3; i < argc; ++i)
    {
        std::ifstream f(argv[i], std::ios::binary);
        std::string line;
        while (std::getline(f, line))
        {
            if (line.compare(0, 4, "BHC\t") == 0)
                line = line.substr(line.find('\t', 4) + 1);
            if (!line.empty())
                pool.push_back(line);
        }
    }
    std::mt19937 rng(seed);
    long accepted = 0;
    for (std::string const& s : pool)
        FuzzOne(reinterpret_cast<uint8_t const*>(s.data()), s.size());
    std::vector<std::string> corpus = pool;
    for (long i = 0; i < iterations; ++i)
    {
        std::string const in = Mutate(corpus[rng() % corpus.size()], pool, rng);
        FuzzOne(reinterpret_cast<uint8_t const*>(in.data()), in.size());
        Intent tmp;
        if (ParseClientMessage("BHc\t" + in, tmp) == DropReason::None)
        {
            ++accepted;
            if (corpus.size() < 5000)
                corpus.push_back(in);   // keep valid variants: they reach deeper
        }
        // pure random bytes too
        if (i % 16 == 0)
        {
            std::string r(rng() % 300, '\0');
            for (char& c : r)
                c = static_cast<char>(rng() % 256);
            FuzzOne(reinterpret_cast<uint8_t const*>(r.data()), r.size());
        }
    }
    Proto::EndpointStats const& st = g_ep.Stats();
    std::printf("bh_fuzz: %ld mutated inputs (seed %u), %ld parsed as valid intents (all re-encode and match the reference); "
        "endpoint: %llu received, %llu accepted, %llu refused, %llu mutes\n", iterations, seed, accepted,
        static_cast<unsigned long long>(st.received), static_cast<unsigned long long>(st.accepted),
        static_cast<unsigned long long>(st.refused), static_cast<unsigned long long>(st.mutes));
    return 0;
}
#endif
