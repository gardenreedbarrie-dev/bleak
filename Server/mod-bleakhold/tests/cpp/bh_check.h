// mod-bleakhold tests: a minimal check framework (no dependencies).
// SPDX-License-Identifier: GPL-2.0-or-later
#ifndef BH_CHECK_H
#define BH_CHECK_H

#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <functional>
#include <sstream>
#include <string>
#include <vector>

namespace bhtest
{
    struct Case
    {
        char const* name;
        std::function<void()> fn;
    };

    inline std::vector<Case>& Cases()
    {
        static std::vector<Case> c;
        return c;
    }

    inline int& Failures()
    {
        static int f = 0;
        return f;
    }

    struct Register
    {
        Register(char const* name, std::function<void()> fn) { Cases().push_back({ name, std::move(fn) }); }
    };

    inline std::string Show(std::string const& s)
    {
        std::string out;
        for (unsigned char c : s)
        {
            if (c < 0x20 || c >= 0x7F)
            {
                char buf[8];
                std::snprintf(buf, sizeof(buf), "\\x%02X", c);
                out += buf;
            }
            else
                out += static_cast<char>(c);
        }
        return out;
    }

    inline void Fail(char const* file, int line, std::string const& what)
    {
        ++Failures();
        std::fprintf(stderr, "  FAIL %s:%d: %s\n", file, line, what.c_str());
    }

    inline int RunAll()
    {
        int failedCases = 0;
        for (Case const& c : Cases())
        {
            int const before = Failures();
            c.fn();
            if (Failures() != before)
            {
                ++failedCases;
                std::fprintf(stderr, "FAIL %s\n", c.name);
            }
        }
        std::printf("%zu cases, %d failed, %d failed checks\n", Cases().size(), failedCases, Failures());
        return failedCases ? 1 : 0;
    }

    inline std::string ReadFile(std::string const& path)
    {
        std::ifstream f(path, std::ios::binary);
        if (!f)
        {
            std::fprintf(stderr, "cannot read %s\n", path.c_str());
            std::exit(2);
        }
        std::ostringstream ss;
        ss << f.rdbuf();
        return ss.str();
    }
}

#define BH_CONCAT2(a, b) a##b
#define BH_CONCAT(a, b) BH_CONCAT2(a, b)
#define TEST(name) \
    static void BH_CONCAT(bh_test_, __LINE__)(); \
    static bhtest::Register BH_CONCAT(bh_reg_, __LINE__)(name, BH_CONCAT(bh_test_, __LINE__)); \
    static void BH_CONCAT(bh_test_, __LINE__)()

#define CHECK(cond) do { if (!(cond)) bhtest::Fail(__FILE__, __LINE__, #cond); } while (0)
#define CHECK_MSG(cond, msg) do { if (!(cond)) bhtest::Fail(__FILE__, __LINE__, std::string(#cond) + " -- " + (msg)); } while (0)
#define CHECK_EQ(a, b) do { std::string const _a = std::string(a); std::string const _b = std::string(b); if (!(_a == _b)) { std::ostringstream _s; \
    _s << #a << " == " << #b << "  (got [" << bhtest::Show(_a) << "] expected [" << bhtest::Show(_b) << "])"; \
    bhtest::Fail(__FILE__, __LINE__, _s.str()); } } while (0)
#define CHECK_EQN(a, b) do { auto const _a = (a); auto const _b = (b); if (!(_a == _b)) { std::ostringstream _s; \
    _s << #a << " == " << #b << "  (got " << +_a << " expected " << +_b << ")"; bhtest::Fail(__FILE__, __LINE__, _s.str()); } } while (0)

#endif
