/*
 * mod-bleakhold-ui: server side of the Bleakhold UI protocol (docs/BleakholdProtocol.md).
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "BleakholdEndpoint.h"
#include "BleakholdCodec.h"

#include <algorithm>

namespace Bleakhold::Proto
{
    void TokenBucket::Configure(double capacity, double perSecond)
    {
        _capacity = capacity < 1 ? 1 : capacity;
        _perMs = (perSecond <= 0 ? 0.001 : perSecond) / 1000.0;
        _tokens = _capacity;
        _started = false;
    }

    bool TokenBucket::Take(uint64_t nowMs)
    {
        if (!_started)
        {
            _started = true;
            _lastMs = nowMs;
        }
        else if (nowMs > _lastMs)
        {
            _tokens = std::min(_capacity, _tokens + static_cast<double>(nowMs - _lastMs) * _perMs);
            _lastMs = nowMs;
        }
        if (_tokens >= 1.0)
        {
            _tokens -= 1.0;
            return true;
        }
        return false;
    }

    Endpoint::Endpoint(Limits const& limits)
    {
        SetLimits(limits);
    }

    void Endpoint::SetLimits(Limits const& l)
    {
        _limits = l;
        auto perInterval = [](uint32_t ms) { return ms ? 1000.0 / ms : 1000.0; };
        _all.Configure(l.burst, l.perSecond);
        _helloBucket.Configure(1, perInterval(l.helloIntervalMs));
        _leaderboard.Configure(l.leaderboardPerSecond, l.leaderboardPerSecond);
        _claims.Configure(l.claimPerSecond, l.claimPerSecond);
        for (TokenBucket& b : _queue)
            b.Configure(1, perInterval(l.queueIntervalMs));
        for (TokenBucket& b : _key)
            b.Configure(1, perInterval(l.keyIntervalMs));
        _emoji.Configure(1, perInterval(l.emojiIntervalMs));
    }

    void Endpoint::CountDrop(uint64_t nowMs, ReceiveResult& r)
    {
        ++_stats.dropped[static_cast<std::size_t>(r.reason)];
        if (nowMs - _windowStart >= _limits.floodWindowMs || nowMs < _windowStart)
        {
            _windowStart = nowMs;
            _windowDrops = 0;
        }
        if (++_windowDrops >= _limits.floodDrops && _limits.floodDrops > 0)
        {
            _mutedUntil = nowMs + _limits.floodMuteMs;
            _windowDrops = 0;
            _windowStart = nowMs;
            r.muteStarted = true;
            ++_stats.mutes;
        }
    }

    bool Endpoint::CheckActionLimit(IntentType type, uint64_t nowMs)
    {
        switch (type)
        {
            case IntentType::QueueJoin: return _queue[0].Take(nowMs);
            case IntentType::QueueLeave: return _queue[1].Take(nowMs);
            case IntentType::QueueReply: return _queue[2].Take(nowMs);
            case IntentType::KeyMode: return _key[0].Take(nowMs);
            case IntentType::KeyStart: return _key[1].Take(nowMs);
            case IntentType::KeyCancel: return _key[2].Take(nowMs);
            case IntentType::Emoji: return _emoji.Take(nowMs);
            case IntentType::TaskClaim:
            case IntentType::TaskReroll:
            case IntentType::BountyClaim:
            case IntentType::Outfit:
            case IntentType::WarEffortHandIn:
                return _claims.Take(nowMs);
            default:
                return true;
        }
    }

    bool Endpoint::FilterGet(Intent& intent, uint64_t nowMs)
    {
        // forget old entries so the map stays small
        if (_lastGet.size() > 64)
        {
            for (auto it = _lastGet.begin(); it != _lastGet.end();)
            {
                if (nowMs - it->second >= std::max(_limits.getTopicIntervalMs, _limits.heavyTopicIntervalMs))
                    it = _lastGet.erase(it);
                else
                    ++it;
            }
        }
        std::vector<TopicRequest> kept;
        for (TopicRequest const& t : intent.topics)
        {
            std::string key = TopicName(t.topic);
            if (t.topic == Topic::Set)
                key += "," + std::to_string(t.arg1) + "," + std::to_string(t.arg2);
            // a small request with a large answer: the client asks for these once per login or window
            bool const heavy = t.topic == Topic::Def || t.topic == Topic::Lidx || t.topic == Topic::Board;
            uint64_t const interval = heavy ? std::max(_limits.getTopicIntervalMs, _limits.heavyTopicIntervalMs) : _limits.getTopicIntervalMs;
            auto it = _lastGet.find(key);
            if (it != _lastGet.end() && nowMs - it->second < interval)
                continue;
            if (_lastGet.size() >= 256)
                continue;   // a flood of distinct SET keys; the next window clears them
            _lastGet[key] = nowMs;
            kept.push_back(t);
        }
        intent.topics = std::move(kept);
        return !intent.topics.empty();
    }

    ReceiveResult Endpoint::Receive(std::string_view chatText, uint64_t nowMs, Intent& out)
    {
        ReceiveResult r;
        Intent parsed;
        DropReason const why = ParseClientMessage(chatText, parsed);
        if (why == DropReason::NotBleakhold)
        {
            r.verdict = Verdict::NotOurs;
            r.reason = why;
            return r;
        }
        ++_stats.received;

        if (Muted(nowMs))
        {
            r.reason = DropReason::Muted;
            ++_stats.dropped[static_cast<std::size_t>(r.reason)];
            return r;
        }
        // every BHc message (and every BHs from a client) costs a token, well-formed or not
        if (!_all.Take(nowMs))
        {
            r.reason = DropReason::Flood;
            CountDrop(nowMs, r);
            return r;
        }
        if (why != DropReason::None)
        {
            r.reason = why;
            CountDrop(nowMs, r);
            return r;
        }

        if (parsed.type == IntentType::Hello)
        {
            if (!_helloBucket.Take(nowMs))
            {
                r.reason = DropReason::Throttled;
                CountDrop(nowMs, r);
                return r;
            }
            // A new HELLO means a fresh client state (login or /reload): it holds no snapshot.
            _ready = true;
            _hello = parsed;
            _snapshot.fill(false);
            _lastGet.clear();
        }
        else if (!_ready)
        {
            r.reason = DropReason::NoHello;
            CountDrop(nowMs, r);
            return r;
        }
        else if (parsed.type == IntentType::Get)
        {
            if (!FilterGet(parsed, nowMs))
            {
                r.reason = DropReason::Throttled;
                CountDrop(nowMs, r);
                return r;
            }
        }
        else if (parsed.type == IntentType::LeaderboardQuery)
        {
            if (!_leaderboard.Take(nowMs))
            {
                r.verdict = Verdict::Refused;
                r.reason = DropReason::Throttled;
                ++_stats.refused;
                CountDrop(nowMs, r);
                out = std::move(parsed);
                return r;
            }
        }
        else if (IsActionIntent(parsed.type))
        {
            // duplicate guard: the same intent as the last accepted one of its op, within the window
            LastIntent& last = _last[static_cast<std::size_t>(parsed.type)];
            std::string key = EncodeIntentPayload(parsed);
            if (_limits.duplicateWindowMs && last.set && last.key == key && nowMs - last.atMs < _limits.duplicateWindowMs)
            {
                r.reason = DropReason::Duplicate;
                CountDrop(nowMs, r);
                return r;
            }
            if (!CheckActionLimit(parsed.type, nowMs))
            {
                r.verdict = Verdict::Refused;
                r.reason = DropReason::Throttled;
                ++_stats.refused;
                CountDrop(nowMs, r);
                out = std::move(parsed);
                return r;
            }
            last.key = std::move(key);
            last.atMs = nowMs;
            last.set = true;
        }

        ++_stats.accepted;
        r.verdict = Verdict::Accepted;
        out = std::move(parsed);
        return r;
    }

    std::vector<std::string> Endpoint::Frame(std::string_view op, std::string_view payload, std::size_t maxBody)
    {
        uint32_t const seq = NextSeq(_seq);
        std::vector<std::string> frames = BuildFrames(op, seq, payload, maxBody);
        // Too many parts for the configured frame size: use the protocol's own limit for this message.
        if (frames.empty() && maxBody < MaxServerBody)
            frames = BuildFrames(op, seq, payload, MaxServerBody);
        if (frames.empty())
            return frames;
        _seq = seq;
        ++_stats.messagesOut;
        _stats.framesOut += frames.size();
        std::string prefix(ServerPrefix);
        prefix += '\t';
        for (std::string& f : frames)
            f.insert(0, prefix);
        return frames;
    }

    uint32_t Endpoint::NextRev(Topic topic)
    {
        std::size_t const i = static_cast<std::size_t>(topic);
        if (i >= _rev.size())
            return 0;
        // wraps to 1 well inside the client's INT32 range
        _rev[i] = _rev[i] >= static_cast<uint32_t>(Int32Max) ? 1 : _rev[i] + 1;
        return _rev[i];
    }

    uint32_t Endpoint::Rev(Topic topic) const
    {
        std::size_t const i = static_cast<std::size_t>(topic);
        return i < _rev.size() ? _rev[i] : 0;
    }

    bool Endpoint::HasSnapshot(Topic topic) const
    {
        std::size_t const i = static_cast<std::size_t>(topic);
        return i < _snapshot.size() && _snapshot[i];
    }

    void Endpoint::MarkSnapshot(Topic topic)
    {
        std::size_t const i = static_cast<std::size_t>(topic);
        if (i < _snapshot.size())
            _snapshot[i] = true;
    }
}
