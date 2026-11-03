/*
 * mod-bleakhold-ui: server side of the Bleakhold UI protocol (docs/BleakholdProtocol.md).
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Cases (section 15): the weighted roll and the chances shown in CASE. No AzerothCore dependency.
 */
#ifndef BLEAKHOLD_CASES_H
#define BLEAKHOLD_CASES_H

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <vector>

namespace Bleakhold::Cases
{
    // The chance of every reward in 1/10000, from the weights: the largest remainders get the rounding, so the
    // chances add up to exactly 10000 (0 for a weight of 0; all 0 when every weight is 0).
    inline std::vector<uint32_t> Chances(std::vector<uint32_t> const& weights)
    {
        std::vector<uint32_t> out(weights.size(), 0);
        uint64_t total = 0;
        for (uint32_t w : weights)
            total += w;
        if (total == 0)
            return out;
        uint64_t given = 0;
        std::vector<std::pair<uint64_t, std::size_t>> rest;   // remainder, index
        for (std::size_t i = 0; i < weights.size(); ++i)
        {
            uint64_t const scaled = uint64_t(weights[i]) * 10000;
            out[i] = uint32_t(scaled / total);
            given += out[i];
            if (weights[i])
                rest.emplace_back(scaled % total, i);
        }
        std::stable_sort(rest.begin(), rest.end(), [](auto const& a, auto const& b) { return a.first > b.first; });
        for (std::size_t k = 0; given < 10000 && k < rest.size(); ++k, ++given)
            ++out[rest[k].second];
        return out;
    }

    // The reward `roll` (0 <= roll < the sum of the weights) lands on; weights.size() when there is none.
    inline std::size_t Pick(std::vector<uint32_t> const& weights, uint64_t roll)
    {
        for (std::size_t i = 0; i < weights.size(); ++i)
        {
            if (roll < weights[i])
                return i;
            roll -= weights[i];
        }
        return weights.size();
    }

    inline uint64_t TotalWeight(std::vector<uint32_t> const& weights)
    {
        uint64_t total = 0;
        for (uint32_t w : weights)
            total += w;
        return total;
    }
}

#endif
