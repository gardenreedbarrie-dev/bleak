/*
 * mod-bleakhold: server side of the Bleakhold UI protocol (docs/BleakholdProtocol.md).
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "BleakholdCodec.h"

namespace Bleakhold::Proto
{
    namespace
    {
        constexpr char Digits36[] = "0123456789abcdefghijklmnopqrstuvwxyz";
        constexpr char Hex[] = "0123456789ABCDEF";

        bool IsCont(unsigned char b) { return b >= 0x80 && b < 0xC0; }

        // Length of the valid UTF-8 sequence at s[i], or 0 when the byte there does not start one.
        std::size_t Utf8SeqLen(std::string_view s, std::size_t i)
        {
            unsigned char const c = static_cast<unsigned char>(s[i]);
            std::size_t len = 0;
            if (c < 0x80)
                return 1;
            if (c >= 0xC2 && c <= 0xDF)
                len = 2;
            else if (c >= 0xE0 && c <= 0xEF)
                len = 3;
            else if (c >= 0xF0 && c <= 0xF4)
                len = 4;
            else
                return 0;
            if (i + len > s.size())
                return 0;
            for (std::size_t j = 1; j < len; ++j)
                if (!IsCont(static_cast<unsigned char>(s[i + j])))
                    return 0;
            unsigned char const c1 = static_cast<unsigned char>(s[i + 1]);
            // overlong 3/4-byte forms, UTF-16 surrogates and code points above U+10FFFF
            if (c == 0xE0 && c1 < 0xA0)
                return 0;
            if (c == 0xED && c1 >= 0xA0)
                return 0;
            if (c == 0xF0 && c1 < 0x90)
                return 0;
            if (c == 0xF4 && c1 >= 0x90)
                return 0;
            return len;
        }

        bool MustEscape(unsigned char c)
        {
            return c < 0x20 || c == 0x7F || c == '%' || c == ';' || c == ',' || c == ':' || c == '~' || c == '|';
        }

        int HexValue(char c)
        {
            if (c >= '0' && c <= '9')
                return c - '0';
            if (c >= 'A' && c <= 'F')
                return c - 'A' + 10;
            if (c >= 'a' && c <= 'f')
                return c - 'a' + 10;
            return -1;
        }
    }

    std::string Base36(uint32_t n)
    {
        n %= SeqModulo;
        if (n == 0)
            return "0";
        char buf[8];
        int i = 0;
        while (n > 0)
        {
            buf[i++] = Digits36[n % 36];
            n /= 36;
        }
        std::string out;
        out.reserve(static_cast<std::size_t>(i));
        while (i > 0)
            out += buf[--i];
        return out;
    }

    std::optional<uint32_t> ParseBase36(std::string_view s)
    {
        if (s.empty() || s.size() > 6)
            return std::nullopt;
        uint64_t v = 0;
        for (char c : s)
        {
            int d;
            if (c >= '0' && c <= '9')
                d = c - '0';
            else if (c >= 'a' && c <= 'z')
                d = c - 'a' + 10;
            else
                return std::nullopt;
            v = v * 36 + static_cast<uint64_t>(d);
        }
        return static_cast<uint32_t>(v);
    }

    uint32_t NextSeq(uint32_t current)
    {
        return current % (SeqModulo - 1) + 1;
    }

    std::string CleanText(std::string_view text, std::size_t maxBytes)
    {
        std::string out;
        out.reserve(text.size() < 256 ? text.size() : 256);
        std::size_t i = 0;
        while (i < text.size())
        {
            if (text[i] == '\0')
            {
                ++i;
                continue;
            }
            std::size_t len = Utf8SeqLen(text, i);
            if (len == 0)
            {
                if (maxBytes && out.size() + 1 > maxBytes)
                    break;
                out += '?';
                ++i;
                continue;
            }
            if (maxBytes && out.size() + len > maxBytes)
                break;
            out.append(text.data() + i, len);
            i += len;
        }
        return out;
    }

    std::string EscapeText(std::string_view text, std::size_t maxBytes)
    {
        std::string const clean = CleanText(text, maxBytes);
        std::string out;
        out.reserve(clean.size() + 8);
        for (char ch : clean)
        {
            unsigned char const c = static_cast<unsigned char>(ch);
            if (MustEscape(c))
            {
                out += '%';
                out += Hex[c >> 4];
                out += Hex[c & 0x0F];
            }
            else
                out += ch;
        }
        return out;
    }

    std::optional<std::string> Unescape(std::string_view field)
    {
        std::string out;
        out.reserve(field.size());
        for (std::size_t i = 0; i < field.size(); ++i)
        {
            if (field[i] != '%')
            {
                out += field[i];
                continue;
            }
            if (i + 2 >= field.size())
                return std::nullopt;
            int const hi = HexValue(field[i + 1]);
            int const lo = HexValue(field[i + 2]);
            if (hi < 0 || lo < 0)
                return std::nullopt;
            int const b = hi * 16 + lo;
            if (b == 0)
                return std::nullopt;
            out += static_cast<char>(b);
            i += 2;
        }
        return out;
    }

    void PayloadWriter::Trim()
    {
        // drop the empty fields at the end of the current record (keep "," for an all-empty record, so
        // the record is still there: the client skips empty records)
        if (!_inRecord)
            return;
        if (_anyValue)
            _out.resize(_keep);
        else if (_fields > 1)
            _out.resize(_recordStart + 1);
    }

    PayloadWriter& PayloadWriter::Record()
    {
        if (_inRecord)
        {
            Trim();
            _out += ';';
        }
        else if (!_out.empty())
            _out += ';';
        _inRecord = true;
        _fields = 0;
        _recordStart = _out.size();
        _keep = _out.size();
        _anyValue = false;
        return *this;
    }

    void PayloadWriter::BeginField()
    {
        if (!_inRecord)
        {
            _inRecord = true;
            _fields = 0;
            _recordStart = _out.size();
            _keep = _out.size();
            _anyValue = false;
        }
        if (_fields++)
            _out += ',';
        _fieldStart = _out.size();
    }

    void PayloadWriter::EndField()
    {
        if (_out.size() > _fieldStart)
        {
            _keep = _out.size();
            _anyValue = true;
        }
    }

    PayloadWriter& PayloadWriter::Int(int64_t value)
    {
        BeginField();
        _out += std::to_string(value);
        EndField();
        return *this;
    }

    PayloadWriter& PayloadWriter::Empty()
    {
        BeginField();
        return *this;
    }

    PayloadWriter& PayloadWriter::Char(char letter)
    {
        BeginField();
        // Enum letters are always plain upper-case ASCII; anything else is written as an empty field.
        if (letter >= 'A' && letter <= 'Z')
            _out += letter;
        EndField();
        return *this;
    }

    PayloadWriter& PayloadWriter::Text(std::string_view text, std::size_t maxBytes)
    {
        BeginField();
        _out += EscapeText(text, maxBytes);
        EndField();
        return *this;
    }

    PayloadWriter& PayloadWriter::Texts(std::vector<std::string> const& values, std::size_t maxItems, std::size_t maxBytes)
    {
        BeginField();
        std::size_t n = 0;
        for (std::string const& v : values)
        {
            if (maxItems && n >= maxItems)
                break;
            if (n++)
                _out += ':';
            _out += EscapeText(v, maxBytes);
        }
        EndField();
        return *this;
    }

    PayloadWriter& PayloadWriter::Tuples(std::vector<std::vector<std::string>> const& tuples, std::size_t maxItems)
    {
        BeginField();
        std::size_t n = 0;
        for (std::vector<std::string> const& t : tuples)
        {
            if (maxItems && n >= maxItems)
                break;
            if (n++)
                _out += ':';
            for (std::size_t k = 0; k < t.size(); ++k)
            {
                if (k)
                    _out += '~';
                _out += t[k];
            }
        }
        EndField();
        return *this;
    }

    bool IsOpName(std::string_view s)
    {
        if (s.size() < 2 || s.size() > 6)
            return false;
        for (char c : s)
            if (c < 'A' || c > 'Z')
                return false;
        return true;
    }

    std::vector<std::string> BuildFrames(std::string_view op, uint32_t seq, std::string_view payload, std::size_t maxBody)
    {
        std::vector<std::string> frames;
        if (!IsOpName(op) || payload.size() > MaxAssembled)
            return frames;
        if (maxBody > MaxServerBody)
            maxBody = MaxServerBody;
        std::string const seqStr = Base36(seq);
        // worst-case header: "1 OP SEQ 99/99 "
        std::size_t const header = 2 + op.size() + 1 + seqStr.size() + 1 + 5 + 1;
        if (maxBody < header + 8)
            return frames;
        std::size_t const room = maxBody - header;

        std::vector<std::string_view> parts;
        std::size_t i = 0;
        std::size_t const n = payload.size();
        while (i < n)
        {
            if (n - i <= room)
            {
                parts.push_back(payload.substr(i));
                break;
            }
            std::size_t const end = i + room; // exclusive
            std::size_t cut = 0;
            for (std::size_t k = end; k > i + room / 2; --k)
            {
                if (payload[k - 1] == ';')
                {
                    cut = k;
                    break;
                }
            }
            if (!cut)
            {
                cut = end;
                // Repeat until stable: never end a part inside %XX, never start one on a UTF-8
                // continuation byte.
                bool moved = true;
                while (moved && cut > i)
                {
                    moved = false;
                    if (payload[cut - 1] == '%')
                    {
                        cut -= 1;
                        moved = true;
                    }
                    else if (cut >= i + 2 && payload[cut - 2] == '%')
                    {
                        cut -= 2;
                        moved = true;
                    }
                    while (cut > i && cut < n && IsCont(static_cast<unsigned char>(payload[cut])))
                    {
                        --cut;
                        moved = true;
                    }
                }
                if (cut <= i)
                    return {};
            }
            parts.push_back(payload.substr(i, cut - i));
            i = cut;
        }
        if (parts.empty())
            parts.push_back(std::string_view());
        if (parts.size() > MaxParts)
            return {};

        std::string const total = std::to_string(parts.size());
        frames.reserve(parts.size());
        for (std::size_t p = 0; p < parts.size(); ++p)
        {
            std::string body;
            body.reserve(header + parts[p].size());
            body += "1 ";
            body.append(op.data(), op.size());
            body += ' ';
            body += seqStr;
            body += ' ';
            body += std::to_string(p + 1);
            body += '/';
            body += total;
            if (!parts[p].empty())
            {
                body += ' ';
                body.append(parts[p].data(), parts[p].size());
            }
            frames.push_back(std::move(body));
        }
        return frames;
    }

    std::optional<int64_t> ParseDecimal(std::string_view s)
    {
        std::size_t i = 0;
        bool neg = false;
        if (!s.empty() && s[0] == '-')
        {
            neg = true;
            i = 1;
        }
        std::size_t const digits = s.size() - i;
        if (digits == 0 || digits > 15)
            return std::nullopt;
        int64_t v = 0;
        for (; i < s.size(); ++i)
        {
            char const c = s[i];
            if (c < '0' || c > '9')
                return std::nullopt;
            v = v * 10 + (c - '0');
        }
        return neg ? -v : v;
    }
}
