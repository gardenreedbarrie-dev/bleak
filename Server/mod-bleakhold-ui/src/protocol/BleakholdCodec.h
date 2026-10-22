/*
 * mod-bleakhold-ui: server side of the Bleakhold UI protocol (docs/BleakholdProtocol.md).
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Wire-level helpers: escaping, payload writing, base-36 sequence numbers and server frame
 * chunking. This file has no AzerothCore dependency so it can be unit-tested on its own
 * (Server/mod-bleakhold-ui/tests).
 */

#ifndef BLEAKHOLD_CODEC_H
#define BLEAKHOLD_CODEC_H

#include <cstddef>
#include <cstdint>
#include <optional>
#include <string>
#include <string_view>
#include <type_traits>
#include <vector>

namespace Bleakhold::Proto
{
    inline constexpr std::string_view ClientPrefix = "BHc";
    inline constexpr std::string_view ServerPrefix = "BHs";
    inline constexpr uint32_t ProtocolVersion = 1;

    // Client to server: the whole chat text "BHc\t" + body is at most 255 bytes (the core drops longer).
    inline constexpr std::size_t MaxClientMessage = 255;
    inline constexpr std::size_t MaxClientBody = 251;
    // Server to client: body per frame at most 1000 bytes; the client drops longer frames.
    inline constexpr std::size_t MaxServerBody = 1000;
    inline constexpr std::size_t MinServerBody = 64;
    inline constexpr uint32_t MaxParts = 99;
    // Reassembled payload limit of the client.
    inline constexpr std::size_t MaxAssembled = 64 * 1024;
    // SEQ is 1 to 6 base-36 digits and wraps at 36^6.
    inline constexpr uint32_t SeqModulo = 2176782336u;
    inline constexpr int64_t Int32Max = 2147483647;

    // Lower-case base 36, no leading zeros ("0" for 0). n is taken modulo 36^6.
    std::string Base36(uint32_t n);

    // 1 to 6 characters of [0-9a-z]. Returns nothing for anything else.
    std::optional<uint32_t> ParseBase36(std::string_view s);

    // Next outgoing SEQ: 1 .. 36^6-1, then back to 1 (the same scheme as the client).
    uint32_t NextSeq(uint32_t current);

    // Text cleaned for the client: invalid UTF-8 bytes become '?', NUL bytes are removed, and the
    // result is cut to at most maxBytes (0 = no limit) without splitting a UTF-8 sequence.
    std::string CleanText(std::string_view text, std::size_t maxBytes = 0);

    // Escape a value for a payload field: % ; , : ~ | and every byte below 0x20 plus 0x7F become
    // %XX (upper-case hex). The text is cleaned first (see CleanText).
    std::string EscapeText(std::string_view text, std::size_t maxBytes = 0);

    // Inverse of EscapeText for one field; nothing for a malformed escape or an escaped NUL.
    // (The server never needs it for client data, which may not contain escapes; tests use it.)
    std::optional<std::string> Unescape(std::string_view field);

    // Builds a payload: records separated by ';', fields by ',', list items by ':', tuple parts by '~'.
    // Every Text() value is escaped; numbers are plain decimal. An unset optional is an empty field.
    // Empty fields at the end of a record are left out (a missing field is the same as an empty one);
    // a record is never left out, so record positions never shift.
    class PayloadWriter
    {
    public:
        // Start a new record. The first field call starts the first record by itself.
        PayloadWriter& Record();

        PayloadWriter& Int(int64_t value);
        PayloadWriter& Bool(bool value) { return Int(value ? 1 : 0); }
        PayloadWriter& Empty();
        PayloadWriter& Char(char letter);
        PayloadWriter& Text(std::string_view text, std::size_t maxBytes = 0);

        template <typename T>
        PayloadWriter& Opt(std::optional<T> const& value)
        {
            if (!value)
                return Empty();
            if constexpr (std::is_same_v<T, bool>)
                return Bool(*value);
            else
                return Int(static_cast<int64_t>(*value));
        }

        // A ':' list of integers (at most maxItems items, 0 = no limit).
        template <typename T>
        PayloadWriter& Ints(std::vector<T> const& values, std::size_t maxItems = 0)
        {
            BeginField();
            std::size_t n = 0;
            for (T const& v : values)
            {
                if (maxItems && n >= maxItems)
                    break;
                if (n++)
                    _out += ':';
                _out += std::to_string(static_cast<int64_t>(v));
            }
            EndField();
            return *this;
        }

        // A ':' list of escaped texts.
        PayloadWriter& Texts(std::vector<std::string> const& values, std::size_t maxItems = 0, std::size_t maxBytes = 0);

        // A ':' list of tuples; every tuple is a list of already escaped parts joined with '~'.
        // Use TuplePart() to escape the parts.
        PayloadWriter& Tuples(std::vector<std::vector<std::string>> const& tuples, std::size_t maxItems = 0);
        static std::string TuplePart(std::string_view text, std::size_t maxBytes = 0) { return EscapeText(text, maxBytes); }
        static std::string TuplePart(int64_t value) { return std::to_string(value); }

        std::string const& Str() { Trim(); return _out; }
        std::string Take() { Trim(); return std::move(_out); }

    private:
        void BeginField();
        void EndField();
        void Trim();

        std::string _out;
        bool _inRecord = false;
        uint32_t _fields = 0;
        std::size_t _recordStart = 0;   // where the current record's first field starts
        std::size_t _fieldStart = 0;    // where the current field's value starts
        std::size_t _keep = 0;          // end of the last non-empty field of the current record
        bool _anyValue = false;         // the current record has a non-empty field
    };

    // Splits a payload into server frame bodies of at most maxBody bytes:
    //   "1 OP SEQ PART/TOTAL[ PAYLOAD]"
    // Cuts right after a ';' when one is in the second half of the room, and never inside a %XX
    // escape or a UTF-8 sequence. Returns an empty vector when the payload needs more than 99 parts,
    // is larger than 64 KiB, or the op is not 2 to 6 upper-case letters.
    std::vector<std::string> BuildFrames(std::string_view op, uint32_t seq, std::string_view payload,
        std::size_t maxBody = MaxServerBody);

    // Decimal integer as the protocol writes it: optional '-', then 1 to 15 digits. Leading zeros are
    // accepted (the document only asks for a decimal integer); the range is checked by the caller.
    std::optional<int64_t> ParseDecimal(std::string_view s);

    // True when every byte is 'A'-'Z' and the length is 2 to 6.
    bool IsOpName(std::string_view s);
}

#endif
