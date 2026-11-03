// mod-bleakhold-ui tests: the glowing marks' rules (section 22, src/BleakholdMarksRules.h): the catalogue, a choice,
// MARKSET's checks in their order with every code, the price and the cooldown, the lists and their pages, DEF N, and the
// module's SQL and configuration against the rules.
//
//   bh_marks <repo root>
//
// SPDX-License-Identifier: GPL-2.0-or-later

#include "bh_check.h"

#include "BleakholdCodec.h"
#include "BleakholdMarksRules.h"
#include "BleakholdMessages.h"

#include <map>
#include <set>

using namespace Bleakhold;
namespace R = Bleakhold::MarksRules;

static std::string g_repo;

namespace
{
    std::vector<std::string> Split(std::string const& s, char sep)
    {
        std::vector<std::string> out;
        std::size_t start = 0;
        while (true)
        {
            std::size_t const p = s.find(sep, start);
            if (p == std::string::npos)
            {
                out.push_back(s.substr(start));
                return out;
            }
            out.push_back(s.substr(start, p - start));
            start = p + 1;
        }
    }

    char const* const DesignKeys[] = { "MoonwellSigils", "CenarionVines", "SentinelTalon", "Starfall" };
    char const* const DesignNames[] = { "Moonwell Sigils", "Cenarion Vines", "Sentinel Talon", "Starfall" };
    char const* const ColourKeys[] = { "EluneBlue", "MoonwellTeal", "MidnightInk" };
    char const* const ColourNames[] = { "Elune Blue", "Moonwell Teal", "Midnight Ink" };
    char const* const ColourHex[] = { "5FB4FF", "3FE0C5", "2A2350" };
    char const* const EyeKeys[] = { "MoonlightSilver", "DruidAmber", "DreamEmerald", "BloodRed", "UnholyGreen" };
    char const* const EyeNames[] = { "Moonlight Silver", "Druid Amber", "Dream Emerald", "Blood Red", "Unholy Green" };
    char const* const EyeHex[] = { "CFE3FF", "FFB43A", "4CFF8A", "FF1E1E", "7CFF3A" };

    R::CatalogueRow Look(uint32_t race, uint32_t sex, char const* raceFile, uint32_t d, uint32_t c)
    {
        R::CatalogueRow r;
        r.race = race; r.sex = sex; r.kind = 'M'; r.design = d; r.colour = c; r.raceFile = raceFile;
        r.designKey = DesignKeys[d - 1]; r.designName = DesignNames[d - 1];
        r.colourKey = ColourKeys[c - 1]; r.colourName = ColourNames[c - 1]; r.hex = ColourHex[c - 1];
        r.glow = c < 3 ? 1 : 0;
        r.texture = R::MarkTexture(raceFile, sex, r.designKey, r.colourKey);
        return r;
    }

    R::CatalogueRow Eye(uint32_t race, uint32_t sex, char const* raceFile, uint32_t e)
    {
        R::CatalogueRow r;
        r.race = race; r.sex = sex; r.kind = 'E'; r.design = 0; r.colour = e; r.raceFile = raceFile;
        r.colourKey = EyeKeys[e - 1]; r.colourName = EyeNames[e - 1]; r.hex = EyeHex[e - 1];
        r.dkOnly = e >= 4 ? 1 : 0;
        r.texture = R::EyeTexture(raceFile, sex, r.colourKey);
        return r;
    }

    // a whole race-sex: 12 looks and the eyes asked for
    std::vector<R::CatalogueRow> RaceSex(uint32_t race, uint32_t sex, char const* raceFile, std::vector<uint32_t> eyes = { 1, 2, 3, 4, 5 })
    {
        std::vector<R::CatalogueRow> rows;
        for (uint32_t d = 1; d <= 4; ++d)
            for (uint32_t c = 1; c <= 3; ++c)
                rows.push_back(Look(race, sex, raceFile, d, c));
        for (uint32_t e : eyes)
            rows.push_back(Eye(race, sex, raceFile, e));
        return rows;
    }

    void Add(std::vector<R::CatalogueRow>& to, std::vector<R::CatalogueRow> const& rows) { to.insert(to.end(), rows.begin(), rows.end()); }

    // Night Elf women (4/1) with every eye, Blood Elf men (10/0) with three, Tauren women (6/1) with none
    R::Catalogue Sample()
    {
        std::vector<R::CatalogueRow> rows;
        Add(rows, RaceSex(4, 1, "NightElf"));
        Add(rows, RaceSex(10, 0, "BloodElf", { 1, 2, 3 }));
        Add(rows, RaceSex(6, 1, "Tauren", {}));
        return R::BuildCatalogue(rows);
    }

    R::Settings Defaults() { return R::Settings{ true, false, 100000, true, 1, 2000 }; }

    R::SetInput Ilyssa()
    {
        R::SetInput in;
        in.feature = true; in.alive = true; in.inCombat = false;
        in.race = 4; in.sex = 1; in.classId = 11;   // a druid
        in.wanted = R::Choice{ 4, 1, 2 };
        in.maxCopper = 100000; in.money = 500000; in.now = 1800000000;
        return in;
    }
}

// =================================================================================================================
// The path rule and the rows
// =================================================================================================================
TEST("the texture paths follow the rule every builder shares")
{
    CHECK_EQ(R::MarkTexture("NightElf", 1, "Starfall", "EluneBlue"), "Character\\BleakholdMarks\\NightElf\\Female\\Starfall_EluneBlue.blp");
    CHECK_EQ(R::EyeTexture("BloodElf", 0, "DruidAmber"), "Character\\BleakholdEyes\\BloodElf\\Male\\Eye_DruidAmber.blp");
    // the longest path the key rules allow is 118 bytes (123 with _Glow), under the client's 127; the column holds 120
    std::string const longest = R::MarkTexture(std::string(16, 'R'), 1, std::string(32, 'D'), std::string(32, 'C'));
    CHECK(longest.size() <= R::MaxTextureBytes && longest.size() + 5 < 127);
    CHECK(R::IsKey("UnholyGreen") && R::IsKey("A1") && R::IsKey(std::string(32, 'k')));
    CHECK(!R::IsKey("") && !R::IsKey(std::string(33, 'k')) && !R::IsKey("Moon well") && !R::IsKey("a_b") && !R::IsKey("a\\b"));
    CHECK(R::IsRaceFile("Scourge") && !R::IsRaceFile("Night Elf") && !R::IsRaceFile("Elf2") && !R::IsRaceFile(std::string(17, 'a')));
    CHECK(R::IsHex6("5fb4FF") && !R::IsHex6("#5FB4F") && !R::IsHex6("5FB4FG") && !R::IsHex6("5FB4F"));
    CHECK(R::IsName("Caf\xC3\xA9 Noir") && !R::IsName("") && !R::IsName(std::string(49, 'n')) && !R::IsName("bad\xFF"));
}

TEST("a catalogue row that breaks a rule is dropped with its reason")
{
    struct Case { char const* what; R::CatalogueRow row; };
    std::vector<Case> bad;
    auto look = [] { return Look(4, 1, "NightElf", 2, 1); };
    auto eye = [] { return Eye(4, 1, "NightElf", 4); };
    { auto r = look(); r.race = 0; bad.push_back({ "race 0", r }); }
    { auto r = look(); r.race = 256; bad.push_back({ "race 256", r }); }
    { auto r = look(); r.sex = 2; bad.push_back({ "sex 2", r }); }
    { auto r = look(); r.kind = 'X'; bad.push_back({ "kind X", r }); }
    { auto r = look(); r.design = 5; r.texture = R::MarkTexture("NightElf", 1, r.designKey, r.colourKey); bad.push_back({ "design 5", r }); }
    { auto r = look(); r.design = 0; bad.push_back({ "design 0", r }); }
    { auto r = look(); r.colour = 4; bad.push_back({ "colour 4", r }); }
    { auto r = look(); r.designKey = "Bad Key"; r.texture = R::MarkTexture("NightElf", 1, r.designKey, r.colourKey); bad.push_back({ "key", r }); }
    { auto r = look(); r.designName = ""; bad.push_back({ "no name", r }); }
    { auto r = look(); r.colourName = std::string(49, 'n'); bad.push_back({ "long name", r }); }
    { auto r = look(); r.hex = "#5FB4F"; bad.push_back({ "hex", r }); }
    { auto r = look(); r.glow = 2; bad.push_back({ "glow 2", r }); }
    { auto r = look(); r.dkOnly = 1; bad.push_back({ "a mark with dk_only", r }); }
    { auto r = look(); r.raceFile = "Night Elf"; bad.push_back({ "race_file", r }); }
    { auto r = look(); r.texture = "character\\BleakholdMarks\\NightElf\\Female\\CenarionVines_EluneBlue.blp"; bad.push_back({ "case", r }); }
    { auto r = look(); r.texture += "x"; bad.push_back({ "texture", r }); }
    { auto r = look(); r.texture = "\\" + r.texture; bad.push_back({ "leading backslash", r }); }
    { auto r = look(); r.texture = R::MarkTexture("NightElf", 0, r.designKey, r.colourKey); bad.push_back({ "other sex", r }); }
    { auto r = eye(); r.dkOnly = 0; bad.push_back({ "eye 4 not dk_only", r }); }
    { auto r = Eye(4, 1, "NightElf", 2); r.dkOnly = 1; bad.push_back({ "eye 2 dk_only", r }); }
    { auto r = eye(); r.design = 1; bad.push_back({ "eye with a design", r }); }
    { auto r = eye(); r.colour = 6; bad.push_back({ "eye 6", r }); }
    { auto r = eye(); r.colour = 0; bad.push_back({ "eye 0", r }); }
    { auto r = eye(); r.texture = R::MarkTexture("NightElf", 1, "x", r.colourKey); bad.push_back({ "eye path", r }); }
    for (Case const& c : bad)
        CHECK_MSG(!R::RowProblem(c.row).empty(), c.what);
    CHECK(R::RowProblem(look()).empty());
    CHECK(R::RowProblem(eye()).empty());
    // the longest keys the rule allows still make a path that fits the column (118 bytes)
    R::CatalogueRow longKeys = Look(4, 1, "NightElf", 1, 1);
    longKeys.designKey = std::string(32, 'D'); longKeys.colourKey = std::string(32, 'C'); longKeys.raceFile = std::string(16, 'R');
    longKeys.texture = R::MarkTexture(longKeys.raceFile, 1, longKeys.designKey, longKeys.colourKey);
    CHECK_EQN(longKeys.texture.size(), std::size_t(118));
    CHECK(R::RowProblem(longKeys).empty());
    longKeys.texture += std::string(3, 'x');
    CHECK_EQ(R::RowProblem(longKeys), "texture longer than 120 bytes");
    // an E row's glow is not read
    R::CatalogueRow glowingEye = eye();
    glowingEye.glow = 1;
    CHECK(R::RowProblem(glowingEye).empty());
}

TEST("a race-sex is offered only with all 12 looks, one key and name per design and colour; eyes one by one")
{
    R::Catalogue const cat = Sample();
    CHECK_EQN(cat.Offered(), std::size_t(3));
    CHECK(cat.problems.empty());
    CHECK_EQN(cat.rows, std::size_t(12 + 5 + 12 + 3 + 12));
    CHECK_EQN(cat.goodRows, cat.rows);
    R::RaceSex const* ne = cat.Find(4, 1);
    CHECK(ne && ne->offered && ne->raceFile == "NightElf");
    CHECK(!cat.Find(4, 0) && !cat.Find(5, 1));
    CHECK_EQ(ne->designs[3].key, "Starfall");
    CHECK_EQ(ne->colours[1].hex, "3FE0C5");
    CHECK(ne->colours[0].glow && ne->colours[1].glow && !ne->colours[2].glow);
    CHECK(ne->eyeOffered[3] && ne->eyes[3].dkOnly && !ne->eyes[2].dkOnly);
    CHECK(!cat.Find(6, 1)->eyeOffered[0]);

    // 11 looks: not offered, and its eyes neither
    std::vector<R::CatalogueRow> rows = RaceSex(4, 1, "NightElf");
    rows.erase(rows.begin() + 5);
    R::Catalogue missing = R::BuildCatalogue(rows);
    CHECK_EQN(missing.Offered(), std::size_t(0));
    CHECK_EQN(missing.problems.size(), std::size_t(1));
    CHECK(missing.problems[0].find("no look for design 2 colour 3") != std::string::npos);
    // a bad row of the 12 is the same as a missing one
    rows = RaceSex(4, 1, "NightElf");
    rows[7].hex = "nothex";
    R::Catalogue badRow = R::BuildCatalogue(rows);
    CHECK_EQN(badRow.Offered(), std::size_t(0));
    CHECK_EQN(badRow.problems.size(), std::size_t(2));   // the row, then the race-sex
    // two names for one design across its colours, two hex values for one colour across its designs
    rows = RaceSex(4, 1, "NightElf");
    rows[1].designName = "Moonwell Sigils II";
    CHECK_EQN(R::BuildCatalogue(rows).Offered(), std::size_t(0));
    rows = RaceSex(4, 1, "NightElf");
    rows[3 * 2 + 1].hex = "000000";   // design 3, colour 2
    CHECK_EQN(R::BuildCatalogue(rows).Offered(), std::size_t(0));
    rows = RaceSex(4, 1, "NightElf");
    rows[3 * 3 + 2].glow = 1;         // the paint glowing on design 4 only
    CHECK_EQN(R::BuildCatalogue(rows).Offered(), std::size_t(0));
    // two designs with one key: their paths would be the same files
    rows.clear();
    for (uint32_t d = 1; d <= 4; ++d)
        for (uint32_t c = 1; c <= 3; ++c)
        {
            R::CatalogueRow r = Look(4, 1, "NightElf", d, c);
            if (d == 4)
            {
                r.designKey = DesignKeys[0];
                r.texture = R::MarkTexture("NightElf", 1, r.designKey, r.colourKey);
            }
            rows.push_back(r);
        }
    R::Catalogue shared = R::BuildCatalogue(rows);
    CHECK(shared.Offered() == 0 && shared.problems.back().find("two designs share a key") != std::string::npos);
    // a second row of the same look is dropped (the first counts)
    rows = RaceSex(4, 1, "NightElf");
    rows.push_back(Look(4, 1, "NightElf", 1, 1));
    R::Catalogue twice = R::BuildCatalogue(rows);
    CHECK(twice.Offered() == 1 && twice.problems.size() == 1);
    // eyes one by one: a bad eye row, an eye of another race_file, an eye key used twice
    rows = RaceSex(4, 1, "NightElf", { 1, 3 });
    rows.push_back(Eye(4, 1, "NightElf", 2));
    rows.back().hex = "zz";
    rows.push_back(Eye(4, 1, "Scourge", 4));
    rows.push_back(Eye(4, 1, "NightElf", 5));
    rows.back().colourKey = EyeKeys[0];
    rows.back().texture = R::EyeTexture("NightElf", 1, rows.back().colourKey);
    R::Catalogue eyes = R::BuildCatalogue(rows);
    R::RaceSex const* e = eyes.Find(4, 1);
    CHECK(e && e->eyeOffered[0] && !e->eyeOffered[1] && e->eyeOffered[2] && !e->eyeOffered[3] && !e->eyeOffered[4]);
    CHECK_EQN(eyes.problems.size(), std::size_t(3));
    // a look of another race_file than the race-sex's: not offered
    rows = RaceSex(4, 1, "NightElf");
    rows[11] = Look(4, 1, "Scourge", 4, 3);
    CHECK_EQN(R::BuildCatalogue(rows).Offered(), std::size_t(0));
    // the comparison the reload uses
    CHECK(Sample() == Sample());
    CHECK(!(Sample() == eyes));
    CHECK(R::Catalogue() == R::BuildCatalogue({}));
}

TEST("DEF N comes from the offered race-sexes, in id order, each record under 1000 bytes")
{
    Definitions d;
    R::FillDefinitions(Sample(), d);
    CHECK_EQN(d.markRaces.size(), std::size_t(3));
    CHECK_EQN(d.markRaces[0].raceId, 4u);    // id 9
    CHECK_EQN(d.markRaces[1].raceId, 6u);    // id 13
    CHECK_EQN(d.markRaces[2].raceId, 10u);   // id 20
    CHECK_EQN(d.markRaces[1].eyes.size(), std::size_t(0));
    CHECK_EQN(d.markRaces[2].eyes.size(), std::size_t(3));
    std::vector<std::string> p = EncodeDefinitions(d, 9);
    CHECK_EQN(p.size(), std::size_t(2));
    std::vector<std::string> recs = Split(p[0], ';');
    CHECK_EQN(recs.size(), std::size_t(4));
    // the document's example, byte for byte
    CHECK_EQ(recs[1], "9,4,1,NightElf,1~MoonwellSigils~Moonwell Sigils:2~CenarionVines~Cenarion Vines:3~SentinelTalon~"
        "Sentinel Talon:4~Starfall~Starfall,1~EluneBlue~Elune Blue~5FB4FF~1:2~MoonwellTeal~Moonwell Teal~3FE0C5~1:3~"
        "MidnightInk~Midnight Ink~2A2350~0,1~MoonlightSilver~Moonlight Silver~CFE3FF~0:2~DruidAmber~Druid Amber~FFB43A~0:"
        "3~DreamEmerald~Dream Emerald~4CFF8A~0:4~BloodRed~Blood Red~FF1E1E~1:5~UnholyGreen~Unholy Green~7CFF3A~1");
    CHECK_EQ(recs[2], "13,6,1,Tauren,1~MoonwellSigils~Moonwell Sigils:2~CenarionVines~Cenarion Vines:3~SentinelTalon~"
        "Sentinel Talon:4~Starfall~Starfall,1~EluneBlue~Elune Blue~5FB4FF~1:2~MoonwellTeal~Moonwell Teal~3FE0C5~1:3~"
        "MidnightInk~Midnight Ink~2A2350~0");
    for (std::size_t i = 1; i < recs.size(); ++i)
        CHECK_MSG(recs[i].size() <= 1000, std::to_string(recs[i].size()) + " bytes");
    // the worst record: every name 48 bytes of separators (escaped three times longer), every key 32 bytes
    std::vector<R::CatalogueRow> rows;
    for (uint32_t dd = 1; dd <= 4; ++dd)
        for (uint32_t c = 1; c <= 3; ++c)
        {
            R::CatalogueRow r = Look(15, 1, "HighElf", dd, c);
            r.designKey = std::string(31, 'd') + char('0' + dd); r.colourKey = std::string(31, 'c') + char('0' + c);
            r.designName = std::string(48, ';'); r.colourName = std::string(48, ',');
            r.texture = R::MarkTexture("HighElf", 1, r.designKey, r.colourKey);
            rows.push_back(r);
        }
    R::Catalogue worst = R::BuildCatalogue(rows);
    CHECK_EQN(worst.Offered(), std::size_t(1));
    Definitions w;
    R::FillDefinitions(worst, w);
    std::string const big = Split(EncodeDefinitions(w, 1)[0], ';')[1];
    CHECK_MSG(big.size() > 1000, "names of separators make a long record: " + std::to_string(big.size()));
    // ...which still frames (it is cut between records only when it can, inside escapes never)
    CHECK(!Proto::BuildFrames("DEF", 1, EncodeDefinitions(w, 1)[0], 1000).empty());
    // with the real names it stays under 1000 bytes
    for (R::CatalogueRow& r : rows)
    {
        r.designName = std::string(48, 'n');
        r.colourName = std::string(48, 'm');
    }
    Definitions plain;
    R::FillDefinitions(R::BuildCatalogue(rows), plain);
    CHECK(Split(EncodeDefinitions(plain, 1)[0], ';')[1].size() <= 1000);
}

// =================================================================================================================
// A choice
// =================================================================================================================
TEST("what is offered to a race, sex and class, and what the server applies of a stored choice")
{
    R::Catalogue const cat = Sample();
    CHECK(R::Offered(cat, 4, 1, 11, { 4, 1, 2 }));
    CHECK(R::Offered(cat, 4, 1, 11, { 0, 0, 0 }));             // nothing at all: always
    CHECK(R::Offered(cat, 5, 0, 1, { 0, 0, 0 }));              // also for a body without marks
    CHECK(!R::Offered(cat, 5, 0, 1, { 1, 1, 0 }));             // no look for that body
    CHECK(!R::Offered(cat, 5, 0, 1, { 0, 0, 1 }));
    CHECK(!R::Offered(cat, 4, 1, 11, { 0, 0, 4 }));            // Blood Red: Death Knights only
    CHECK(R::Offered(cat, 4, 1, R::ClassDeathKnight, { 0, 0, 4 }));
    CHECK(R::Offered(cat, 4, 1, R::ClassDeathKnight, { 2, 3, 5 }));
    CHECK(!R::Offered(cat, 10, 0, R::ClassDeathKnight, { 0, 0, 4 }));   // no sprite for that body
    CHECK(!R::Offered(cat, 6, 1, 1, { 1, 1, 1 }));             // a body without eye sprites
    CHECK(R::Offered(cat, 6, 1, 1, { 1, 1, 0 }));
    CHECK(!R::Offered(cat, 4, 1, 11, { 5, 1, 0 }) && !R::Offered(cat, 4, 1, 11, { 1, 0, 0 }) &&
        !R::Offered(cat, 4, 1, 11, { 0, 1, 0 }) && !R::Offered(cat, 4, 1, 11, { 1, 4, 0 }) && !R::Offered(cat, 4, 1, 11, { 0, 0, 6 }));
    // applied: layer by layer, the row keeps the rest
    R::Choice const a = R::Applied(cat, 6, 1, 1, { 2, 2, 3 });
    CHECK(a == (R::Choice{ 2, 2, 0 }));
    CHECK(R::Applied(cat, 5, 0, 1, { 2, 2, 3 }).None());
    CHECK(R::Applied(cat, 4, 1, 11, { 1, 3, 5 }) == (R::Choice{ 1, 3, 0 }));   // a DK eye on a druid
    CHECK(R::Applied(cat, 4, 1, R::ClassDeathKnight, { 1, 3, 5 }) == (R::Choice{ 1, 3, 5 }));
    CHECK(R::Applied(cat, 4, 1, 11, { 1, 0, 2 }) == (R::Choice{ 0, 0, 2 }));   // a broken row: no mark
}

TEST("the price: nothing at all is free, the first change free with FirstFree, else Price")
{
    R::Settings s = Defaults();
    CHECK_EQN(R::PriceNow(s, 0), 0u);
    CHECK_EQN(R::PriceNow(s, 1), 100000u);
    CHECK_EQN(R::PriceFor(s, 0, { 1, 1, 0 }), 0u);
    CHECK_EQN(R::PriceFor(s, 3, { 1, 1, 0 }), 100000u);
    CHECK_EQN(R::PriceFor(s, 3, { 0, 0, 2 }), 100000u);        // an eye alone costs too
    CHECK_EQN(R::PriceFor(s, 3, { 0, 0, 0 }), 0u);
    s.firstFree = false;
    CHECK_EQN(R::PriceNow(s, 0), 100000u);
    CHECK_EQN(R::PriceFor(s, 0, { 0, 0, 0 }), 0u);
    s.priceCopper = 0;
    CHECK_EQN(R::PriceFor(s, 9, { 4, 3, 5 }), 0u);
    // the configuration's ranges
    R::Settings wild;
    wild.priceCopper = 4000000000u; wild.cooldownHours = 1000; wild.maxListEntries = 0;
    R::Settings const c = R::Clamped(wild);
    CHECK_EQN(c.priceCopper, 2147483647u);
    CHECK_EQN(c.cooldownHours, 720u);
    CHECK_EQN(c.maxListEntries, 1u);
    wild.maxListEntries = 5000;
    CHECK_EQN(R::Clamped(wild).maxListEntries, 2000u);
    R::Settings const def;
    CHECK(!def.enable && def.gmOnly && def.priceCopper == 100000 && def.firstFree && def.cooldownHours == 1 &&
        def.maxListEntries == 2000);
}

TEST("the cooldown: CooldownHours after the last change, never longer than one cooldown, and its sentence")
{
    R::Settings s = Defaults();
    uint32_t const t = 1800000000;
    CHECK_EQN(R::CooldownLeft(s, 0, t), 0u);                   // never changed
    CHECK_EQN(R::CooldownLeft(s, t, t), 3600u);
    CHECK_EQN(R::CooldownLeft(s, t, t + 3599), 1u);
    CHECK_EQN(R::CooldownLeft(s, t, t + 3600), 0u);
    CHECK_EQN(R::CooldownLeft(s, t, t - 500), 3600u);          // the clock went back
    s.cooldownHours = 0;
    CHECK_EQN(R::CooldownLeft(s, t, t), 0u);
    s.cooldownHours = 720;
    CHECK_EQN(R::CooldownLeft(s, t, t + 1), 720u * 3600 - 1);
    CHECK_EQN(R::CooldownLeft(s, 4294967295u, 4294967295u), 720u * 3600);   // no overflow at the end of time
    CHECK_EQ(R::CooldownText(3600), "You can change your markings again in 60 minutes.");
    CHECK_EQ(R::CooldownText(3541), "You can change your markings again in 60 minutes.");
    CHECK_EQ(R::CooldownText(1), "You can change your markings again in 1 minute.");
    CHECK_EQ(R::CooldownText(0), "You can change your markings again in 1 minute.");
    CHECK_EQ(R::CooldownText(7200), "You can change your markings again in 120 minutes.");
    CHECK_EQ(R::CooldownText(7201), "You can change your markings again in 3 hours.");
    CHECK_EQ(R::CooldownText(720 * 3600), "You can change your markings again in 720 hours.");
    for (uint32_t sec : { 1u, 59u, 3600u, 2592000u })
        CHECK(R::CooldownText(sec).size() <= 160 && Proto::CleanText(R::CooldownText(sec)) == R::CooldownText(sec));
}

// =================================================================================================================
// MARKSET
// =================================================================================================================
TEST("MARKSET's checks come in their order, each with its code")
{
    R::Catalogue const cat = Sample();
    R::Settings const s = Defaults();
    auto verdict = [&](R::SetInput const& in) { return R::CheckSet(cat, s, in).verdict; };
    R::SetInput in = Ilyssa();
    CHECK(verdict(in) == R::Verdict::Ok);
    CHECK_EQN(R::CheckSet(cat, s, in).price, 0u);              // the first change is free

    // every condition at once, then one by one off, from the first check to the last
    R::SetInput all = in;
    all.feature = false; all.alive = false; all.inCombat = true; all.wanted = { 4, 1, 4 }; all.stored = { 4, 1, 4 };
    all.changes = 1; all.changedAt = in.now - 10; all.maxCopper = 0; all.money = 0;
    CHECK(verdict(all) == R::Verdict::Off);
    all.feature = true;
    CHECK(verdict(all) == R::Verdict::Dead);
    all.alive = true;
    CHECK(verdict(all) == R::Verdict::Combat);
    all.inCombat = false;
    CHECK(verdict(all) == R::Verdict::Unknown);                // eye 4 for a druid
    all.wanted = { 4, 1, 2 }; all.stored = { 4, 1, 2 };
    CHECK(verdict(all) == R::Verdict::Same);
    all.stored = { 3, 1, 2 };
    R::SetResult r = R::CheckSet(cat, s, all);
    CHECK(r.verdict == R::Verdict::Cooldown && r.cooldownSec == 3590);
    all.changedAt = in.now - 3600;
    r = R::CheckSet(cat, s, all);
    CHECK(r.verdict == R::Verdict::Price && r.price == 100000);
    all.maxCopper = 99999;
    CHECK(verdict(all) == R::Verdict::Price);
    all.maxCopper = 100000;
    CHECK(verdict(all) == R::Verdict::Gold);
    all.money = 99999;
    CHECK(verdict(all) == R::Verdict::Gold);
    all.money = 100000;
    r = R::CheckSet(cat, s, all);
    CHECK(r.verdict == R::Verdict::Ok && r.price == 100000);

    // Same compares with the applied choice: a stored eye the class cannot have reads as none
    R::SetInput stale = in;
    stale.stored = { 2, 2, 5 };   // a former Death Knight's eye on a druid (applied: 2,2,0)
    stale.wanted = { 2, 2, 0 };
    CHECK(verdict(stale) == R::Verdict::Same);
    stale.wanted = { 0, 0, 0 };
    CHECK(verdict(stale) == R::Verdict::Ok);
    // a body the catalogue does not have: only nothing at all, and that is the same as what it has
    R::SetInput gnome = in;
    gnome.race = 7; gnome.sex = 0;
    CHECK(verdict(gnome) == R::Verdict::Unknown);
    gnome.wanted = {};
    CHECK(verdict(gnome) == R::Verdict::Same);
    // nothing at all is free even during the price, but not during the cooldown
    R::SetInput back = in;
    back.stored = { 4, 1, 2 }; back.wanted = {}; back.changes = 4; back.changedAt = in.now - 60; back.maxCopper = 0; back.money = 0;
    CHECK(verdict(back) == R::Verdict::Cooldown);
    back.changedAt = in.now - 3600;
    r = R::CheckSet(cat, s, back);
    CHECK(r.verdict == R::Verdict::Ok && r.price == 0);
    // no GM exemptions: the inputs have no game master at all; CooldownHours 0 lets a tester change at once
    R::Settings quick = s;
    quick.cooldownHours = 0;
    back.changedAt = in.now;
    CHECK(R::CheckSet(cat, quick, back).verdict == R::Verdict::Ok);
}

TEST("every refusal of MARKSET has its documented code; MARKME follows cooldown and price only")
{
    std::map<R::Verdict, std::string> const codes = {
        { R::Verdict::Off, "marks_off" }, { R::Verdict::Dead, "dead" }, { R::Verdict::Combat, "marks_combat" },
        { R::Verdict::Unknown, "marks_unknown" }, { R::Verdict::Same, "marks_same" },
        { R::Verdict::Cooldown, "marks_cooldown" }, { R::Verdict::Price, "marks_price" }, { R::Verdict::Gold, "marks_gold" },
    };
    std::string const doc = bhtest::ReadFile(g_repo + "/docs/BleakholdProtocol.md");
    std::size_t const section = doc.find("## 22. Glowing marks");
    CHECK(section != std::string::npos);
    for (auto const& [v, code] : codes)
    {
        Refusal const ref = R::RefusalOf(v);
        CHECK_EQ(ref.code, code);
        CHECK_MSG(std::string(ref.text).size() > 5, code);
        CHECK_MSG(doc.find("| `" + code + "` |", section) != std::string::npos, code + " in section 22's table");
        CHECK_EQN(R::MarkMeFollows(v), v == R::Verdict::Cooldown || v == R::Verdict::Price);
    }
    CHECK_EQ(R::RefusalOf(R::Verdict::Ok).code, "");
    CHECK_EQ(MarksErr::Failed.code, "failed");
    CHECK(doc.find("| `failed` |", section) != std::string::npos);
    CHECK_EQ(MarksErr::Same.text, "That is how you look already.");
}

TEST("an accepted change counts, starts the cooldown and adds what was paid")
{
    R::Stored s;
    R::Stored const a = R::Accept(s, { 4, 1, 2 }, 0, 1800000000);
    CHECK(a.choice == (R::Choice{ 4, 1, 2 }) && a.changes == 1 && a.changedAt == 1800000000 && a.paidTotal == 0);
    R::Stored const b = R::Accept(a, {}, 100000, 1800003600);
    CHECK(b.choice.None() && b.changes == 2 && b.changedAt == 1800003600 && b.paidTotal == 100000);
    R::Stored full;
    full.changes = UINT32_MAX; full.paidTotal = UINT32_MAX - 5;
    R::Stored const c = R::Accept(full, { 1, 1, 0 }, 100000, 0);
    CHECK(c.changes == UINT32_MAX && c.paidTotal == UINT32_MAX && c.changedAt == 1);   // a change is never "never"
    // the free first change, then the price, then the cooldown, played through the rules
    R::Catalogue const cat = Sample();
    R::Settings const st = Defaults();
    R::SetInput in = Ilyssa();
    R::SetResult r = R::CheckSet(cat, st, in);
    CHECK(r.verdict == R::Verdict::Ok && r.price == 0);
    R::Stored row = R::Accept(R::Stored{}, in.wanted, r.price, in.now);
    in.stored = row.choice; in.changes = row.changes; in.changedAt = row.changedAt;
    CHECK_EQN(R::PriceNow(st, row.changes), 100000u);
    CHECK_EQN(R::CooldownLeft(st, row.changedAt, in.now), 3600u);
    in.wanted = {};
    in.now += 60;
    r = R::CheckSet(cat, st, in);
    CHECK(r.verdict == R::Verdict::Cooldown && R::CooldownText(r.cooldownSec) == "You can change your markings again in 59 minutes.");
}

// =================================================================================================================
// Lists
// =================================================================================================================
TEST("who is listed: the owner's bit and a mark or an eye")
{
    MarkEntry const e = R::EntryOf(1201, 4, 1, { 4, 1, 2 });
    CHECK(e.guid == 1201 && e.race == 4 && e.sex == 1 && e.design == 4 && e.colour == 1 && e.eye == 2);
    CHECK(R::Listed(true, e));
    CHECK(!R::Listed(false, e));                                // GmOnly: a player without the bit
    CHECK(!R::Listed(true, R::EntryOf(1201, 4, 1, {})));
    CHECK(R::Listed(true, R::EntryOf(1502, 6, 1, { 0, 0, 2 })));
    CHECK(!R::Listed(true, R::EntryOf(0, 4, 1, { 1, 1, 0 })));  // never a guid 0
    CHECK(!R::Listed(true, R::EntryOf(9, 0, 1, { 1, 1, 0 })));  // nor race 0
    CHECK_EQN(R::EntryOf(9, 300, 2, {}).race, 255u);
    CHECK_EQN(R::EntryOf(9, 4, 2, {}).sex, 1u);
}

TEST("a list of 2000 is 5 pages of 400 in guid order; the cap, the page size of the frame, deltas of 50")
{
    std::vector<MarkEntry> entries;
    for (uint32_t g = 4000; g > 1000; g -= 1)
        entries.push_back(R::EntryOf(g, 1 + g % 11, g % 2, { static_cast<uint8_t>(g % 5), static_cast<uint8_t>(g % 5 ? 1 + g % 3 : 0),
            static_cast<uint8_t>(g % 4) }));
    std::size_t listable = 0;
    for (MarkEntry const& e : entries)
        listable += R::Listed(true, e) ? 1 : 0;
    MarksList list;
    list.listId = 12;
    list.entries = entries;
    MarksListPages const p = EncodeMarksList(list, 2000, R::PageRecordsFor(1000));
    CHECK_EQN(R::PageRecordsFor(1000), std::size_t(400));
    CHECK_EQN(p.payloads.size(), std::size_t(5));
    CHECK_EQN(p.listed, std::size_t(2000));
    CHECK_EQN(p.leftOut, listable - 2000);
    uint32_t last = 0;
    std::set<uint32_t> seen;
    for (std::size_t i = 0; i < p.payloads.size(); ++i)
    {
        std::vector<std::string> recs = Split(p.payloads[i], ';');
        CHECK_EQ(recs[0], "12," + std::to_string(i + 1) + ",5,2000");
        CHECK(recs.size() - 1 <= MaxMarkPageRecords);
        for (std::size_t k = 1; k < recs.size(); ++k)
        {
            std::vector<std::string> f = Split(recs[k], ',');
            CHECK_EQN(f.size(), std::size_t(6));
            uint32_t const g = static_cast<uint32_t>(std::stoul(f[0]));
            CHECK(g > last);
            last = g;
            seen.insert(g);
            CHECK((f[3] == "0") == (f[4] == "0"));
            CHECK(f[3] != "0" || f[5] != "0");
        }
        // every page fits in 99 frames of 1000 bytes
        CHECK(!Proto::BuildFrames("MARKS", 2176782335u, p.payloads[i], 1000).empty());
    }
    CHECK_EQN(seen.size(), std::size_t(2000));
    // the lowest guids are kept
    CHECK(*seen.begin() > 1000 && *seen.rbegin() < 4000);

    // at every frame size a page fits in 99 frames (the server's BleakholdUi.Frame.MaxBody is 64..1000)
    for (std::size_t body : { std::size_t(64), std::size_t(100), std::size_t(251), std::size_t(500), std::size_t(1000) })
    {
        std::size_t const per = R::PageRecordsFor(body);
        CHECK(per >= 1 && per <= MaxMarkPageRecords);
        std::vector<MarkEntry> worst;
        for (uint32_t k = 0; k < per; ++k)
            worst.push_back({ 4294967295u - k, 255, 1, 4, 3, 5 });
        MarksList w;
        w.listId = 2147483647;
        w.entries = worst;
        MarksListPages const wp = EncodeMarksList(w, 2000, per);
        CHECK_EQN(wp.payloads.size(), std::size_t(1));
        CHECK_MSG(!Proto::BuildFrames("MARKS", 2176782335u, wp.payloads[0], body).empty(), "body " + std::to_string(body));
    }
    CHECK(R::PageRecordsFor(64) < 100);
    CHECK_EQN(R::PageRecordsFor(5000), std::size_t(400));

    // MARK: 50 records per message, every one of them a valid entry, removals too
    std::vector<MarkEntry> changes;
    for (uint32_t g = 1; g <= 101; ++g)
        changes.push_back(R::EntryOf(g, 4, 1, g % 2 ? R::Choice{ 1, 1, 0 } : R::Choice{}));
    std::vector<std::string> const d = EncodeMarkDeltas(changes);
    CHECK_EQN(d.size(), std::size_t(3));
    CHECK_EQN(Split(d[0], ';').size(), std::size_t(50));
    CHECK_EQN(Split(d[1], ';').size(), std::size_t(50));
    CHECK_EQ(d[2], "101,4,1,1,1,0");
    CHECK_EQ(Split(d[0], ';')[1], "2,4,1,0,0,0");

    // an empty list
    MarksList none;
    none.listId = 1;
    CHECK_EQ(EncodeMarksList(none, 2000, 400).payloads.at(0), "1,1,1,0");
}

// =================================================================================================================
// The module's SQL and configuration
// =================================================================================================================
TEST("the module SQL holds the tables the server creates at startup, and the uninstall drops them")
{
    std::string const mod = g_repo + "/Server/mod-bleakhold-ui";
    std::string const world = bhtest::ReadFile(mod + "/data/sql/db-world/05_bleakhold_marks_catalogue.sql");
    std::string const chars = bhtest::ReadFile(mod + "/data/sql/db-characters/02_bleakhold_marks_characters.sql");
    std::string const uninstall = bhtest::ReadFile(mod + "/data/sql/uninstall/marks_uninstall.sql");
    auto tableOf = [](std::string_view sql) {
        std::size_t const a = sql.find('`') + 1;
        return std::string(sql.substr(a, sql.find('`', a) - a));
    };
    for (std::string_view sql : R::WorldTablesSql)
    {
        CHECK_MSG(world.find(std::string(sql) + ";\n") != std::string::npos, tableOf(sql));
        CHECK_MSG(uninstall.find("DROP TABLE IF EXISTS `" + tableOf(sql) + "`;") != std::string::npos, tableOf(sql));
        CHECK(uninstall.find("DROP TABLE IF EXISTS `" + tableOf(sql) + "`;") < uninstall.find("-- Part 2"));
    }
    for (std::string_view sql : R::CharacterTablesSql)
    {
        CHECK_MSG(chars.find(std::string(sql) + ";\n") != std::string::npos, tableOf(sql));
        CHECK_MSG(uninstall.find("DROP TABLE IF EXISTS `" + tableOf(sql) + "`;") > uninstall.find("-- Part 2"), tableOf(sql));
    }
    CHECK_EQ(tableOf(R::WorldTablesSql[0]), "bleakhold_mark_catalogue");
    CHECK_EQ(tableOf(R::CharacterTablesSql[0]), "bleakhold_marks");
    // the catalogue's columns are the ones the server reads, and the texture column holds 120 bytes
    for (char const* col : { "`race`", "`sex`", "`kind`", "`design`", "`colour`", "`race_file`", "`design_key`", "`design_name`",
             "`colour_key`", "`colour_name`", "`hex`", "`glow`", "`dk_only`", "`texture` VARCHAR(120)", "`sha1`", "`build`" })
        CHECK_MSG(std::string(R::WorldTablesSql[0]).find(col) != std::string::npos, col);
    CHECK(std::string(R::WorldTablesSql[0]).find("PRIMARY KEY (`race`, `sex`, `kind`, `design`, `colour`)") != std::string::npos);
    // the uninstall file itself never touches `updates`
    std::size_t const part1 = uninstall.find("-- Part 1: the world database");
    CHECK(part1 != std::string::npos && uninstall.find("`updates`", part1) == std::string::npos);
}

TEST("every glowing marks key the server reads is in the config file, and marks ship off")
{
    std::string const conf = bhtest::ReadFile(g_repo + "/Server/mod-bleakhold-ui/conf/mod_bleakhold_ui.conf.dist");
    std::map<std::string, std::string> const keys = {
        { "BleakholdUi.Marks.Enable", "0" }, { "BleakholdUi.Marks.GmOnly", "1" }, { "BleakholdUi.Marks.Price", "100000" },
        { "BleakholdUi.Marks.FirstFree", "1" }, { "BleakholdUi.Marks.CooldownHours", "1" },
        { "BleakholdUi.Marks.MaxListEntries", "2000" }, { "BleakholdUi.RateLimit.MarksIntervalMs", "2000" },
    };
    for (auto const& [key, value] : keys)
        CHECK_MSG(conf.find("\n" + key + " = " + value + "\n") != std::string::npos, key + " = " + value);
    // the defaults of the rules are the file's
    R::Settings const d;
    CHECK(!d.enable && d.gmOnly && d.priceCopper == 100000 && d.firstFree && d.cooldownHours == 1 && d.maxListEntries == 2000);
    // the core side reads exactly these keys
    std::string const src = bhtest::ReadFile(g_repo + "/Server/mod-bleakhold-ui/src/BleakholdMarks.cpp") +
        bhtest::ReadFile(g_repo + "/Server/mod-bleakhold-ui/src/BleakholdMgr.cpp");
    for (auto const& [key, value] : keys)
        CHECK_MSG(src.find("\"" + key + "\"") != std::string::npos, key + " is read");
}

int main(int argc, char** argv)
{
    if (argc < 2)
    {
        std::fprintf(stderr, "usage: bh_marks <repo root>\n");
        return 2;
    }
    g_repo = argv[1];
    return bhtest::RunAll();
}
