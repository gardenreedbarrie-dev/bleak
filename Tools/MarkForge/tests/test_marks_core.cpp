// Tests of WoW/Common/ComponentCore/BleakMarks.h, the game-free part of the glowing marks and eyes (BLEAKHOLD(glow)):
// the byte encodings, `_Glow` names and the name sets, the texture size guards (held against a model of the client's
// own paste loops), the atlas paste and the pass rule of the glow bake, the memory budget, the distance rules and who
// gives a glow texture up, the let-go texture's black latch, and the dump helpers.
// run_marks_core.sh builds and runs it with the host compiler.
#include "WoW/Common/ComponentCore/BleakMarks.h"
#include <cmath>
#include <cstdio>
#include <cstring>
#include <limits>
#include <string>
#include <vector>

using namespace BleakMarks;

namespace {
    int s_failed = 0;
    int s_checks = 0;

    void Check(bool ok, const std::string& what) {
        s_checks++;

        if (!ok) {
            s_failed++;
            printf("FAIL: %s\n", what.c_str());
        }
    }

    std::string Str(uint32_t v) {
        return std::to_string(v);
    }

    // The contract's B (CharacterFacialHairStyles rows of the pinned package) per race and sex, male then female:
    // Human, Orc, Dwarf, Night Elf, Undead, Tauren, Gnome, Troll, Blood Elf / High Elf, Draenei / Eredar.
    const uint32_t kB[10][2] = {
        { 9, 7 }, { 11, 7 }, { 11, 6 }, { 6, 19 }, { 17, 8 }, { 7, 5 }, { 8, 7 }, { 11, 6 }, { 10, 11 }, { 8, 7 },
    };

    void TestFaces() {
        uint32_t valid = 0;

        for (uint32_t v = 0; v <= 300; v++) {
            FaceValue face;
            bool ok = DecodeFace(v, &face);
            bool expect = v <= 255 && v / 40 < 6;
            Check(ok == expect, "DecodeFace accepts " + Str(v) + " exactly when it is a byte with eye < 6");

            if (ok) {
                valid++;
                uint32_t back = 0;
                Check(EncodeFace(face.base, face.eye, &back) && back == v, "face " + Str(v) + " round trips");
                Check(face.base < 40 && face.eye < 6, "face " + Str(v) + " parts in range");
            }
        }

        Check(valid == 240, "240 face values decode (0-239)");
        uint32_t value = 0;
        Check(EncodeFace(38, 5, &value) && value == 238, "the largest face of the contract is 38 + 200 = 238");
        Check(!EncodeFace(40, 0, &value), "a base of 40 is refused");
        Check(!EncodeFace(0, 6, &value), "eye 6 is refused");
        Check(kFirstDeathKnightEye == 4 && kEyeCount == 6, "eyes 4 and 5 are the Death Knight eyes");
    }

    void TestFeatures() {
        Check(kLookCount == 13, "13 looks: none plus 4 designs x 3 colours");
        Check(LookFor(1, 1) == 1 && LookFor(1, 3) == 3 && LookFor(2, 1) == 4 && LookFor(4, 3) == 12, "LookFor is 3 * (design - 1) + colour");
        Check(LookFor(0, 1) == 0 && LookFor(5, 1) == 0 && LookFor(1, 0) == 0 && LookFor(1, 4) == 0, "LookFor refuses designs and colours out of range");

        uint32_t largest = 0;

        for (uint32_t race = 0; race < 10; race++) {
            for (uint32_t sex = 0; sex < 2; sex++) {
                uint32_t b = kB[race][sex];
                std::string rs = "race " + Str(race) + " sex " + Str(sex);

                for (uint32_t v = 0; v <= 255; v++) {
                    FeatureValue f;
                    bool ok = DecodeFeature(v, b, &f);
                    Check(ok == (v < 13 * b), rs + ": features " + Str(v) + " decodes exactly below 13 x B");

                    if (!ok) {
                        continue;
                    }

                    if (v > largest) {
                        largest = v;
                    }

                    uint32_t back = 0;
                    Check(EncodeFeature(f.base, f.look, b, &back) && back == v, rs + ": features " + Str(v) + " round trips");
                    Check(f.look ? LookFor(f.design, f.colour) == f.look : (f.design == 0 && f.colour == 0), rs + ": design and colour of " + Str(v));
                }
            }
        }

        Check(largest == 246, "the largest features value is 13 x 19 - 1 = 246 (Night Elf female)");
        uint32_t value = 0;
        Check(!DecodeFeature(5, 0, nullptr) && !EncodeFeature(0, 1, 0, &value), "B = 0 is refused");
        Check(!EncodeFeature(19, 0, 19, &value), "a base of B is refused");
        Check(!EncodeFeature(0, 13, 19, &value), "look 13 is refused");
        Check(!EncodeFeature(4, 12, 21, &value), "a value above 255 is refused (12 x 21 + 4 = 256)");
        Check(EncodeFeature(3, 12, 21, &value) && value == 255, "255 itself is a byte");
    }

    void TestNames() {
        char out[kNameMax];
        Check(GlowName("Character\\BleakholdMarks\\NightElf\\Female\\Moonwell_EluneBlue.blp", out, sizeof(out)) && strcmp(out, "Character\\BleakholdMarks\\NightElf\\Female\\Moonwell_EluneBlue_Glow.blp") == 0, "a mark's glow name");
        Check(GlowName("Character\\X\\Skin.BLP", out, sizeof(out)) && strcmp(out, "Character\\X\\Skin_Glow.BLP") == 0, "an upper-case extension stays");
        Check(GlowName("Character\\X\\Skin", out, sizeof(out)) && strcmp(out, "Character\\X\\Skin_Glow") == 0, "a name without an extension");
        Check(!GlowName("Character\\X\\Skin_Glow.blp", out, sizeof(out)), "a glow has no glow");
        Check(!GlowName("Character\\X\\Skin_GLOW.blp", out, sizeof(out)), "a glow has no glow, in any case");
        Check(GlowName("a.blp", out, sizeof(out)) && strcmp(out, "a_Glow.blp") == 0, "a short name");
        Check(!GlowName("", out, sizeof(out)) && !GlowName(nullptr, out, sizeof(out)), "empty names");

        std::string fits(254, 'a');
        Check(GlowName(fits.c_str(), out, sizeof(out)) && strlen(out) == 259, "254 + 5 characters fit 260 bytes");
        std::string tooLong(255, 'a');
        Check(!GlowName(tooLong.c_str(), out, sizeof(out)), "255 + 5 characters do not fit");
        char small[8];
        Check(!GlowName("ab.blp", small, sizeof(small)), "a small buffer is refused, not overrun");

        Check(NameHash("Character\\A\\B.blp") == NameHash("CHARACTER/a/b.BLP"), "names hash without case and slash direction");
        Check(NameHash("Character\\A\\B.blp") != NameHash("Character\\A\\C.blp"), "different names hash differently");
        Check(NameHash("") != 0 && NameHash(nullptr) != 0, "no hash is 0");
        Check(HasTexture("x") && !HasTexture("") && !HasTexture(nullptr), "HasTexture");
    }

    void TestNameSet() {
        static NameSet<16> set;
        uint8_t v = 9;
        Check(!set.Find(NameHash("a"), &v) && v == 9, "an empty set finds nothing");
        Check(set.Insert(NameHash("a"), 1), "insert a");
        Check(!set.Insert(NameHash("a"), 2), "a second insert replaces");
        Check(set.Find(NameHash("a"), &v) && v == 2, "the value was replaced");
        Check(set.Insert(0, 5) && set.Find(0, &v) && v == 5, "key 0 is kept apart from empty slots");

        set.Clear();

        for (uint32_t i = 0; i < 12; i++) {
            set.Insert(NameHash(("name" + Str(i)).c_str()), static_cast<uint8_t>(i));
        }

        Check(set.Count() == 12, "12 names fit a 16-slot set");

        for (uint32_t i = 0; i < 12; i++) {
            Check(set.Find(NameHash(("name" + Str(i)).c_str()), &v) && v == i, "name " + Str(i) + " is found with its value");
        }

        set.Insert(NameHash("name12"), 12);
        Check(set.Count() == 1 && set.Find(NameHash("name12"), &v) && !set.Find(NameHash("name0"), &v), "the 13th name starts the set over");

        static NameSet<4096> big;

        for (uint32_t i = 0; i < 100000; i++) {
            big.Insert(NameHash(("n" + Str(i)).c_str()), 1);
        }

        Check(big.Count() > 0 && big.Count() <= 3072, "a set never grows past three quarters");
    }

    TextureFacts Facts(uint32_t w, uint32_t h, uint32_t alpha = 8, bool pal = true) {
        TextureFacts t;
        t.width = w;
        t.height = h;
        uint32_t m = 1;

        for (uint32_t s = w > h ? w : h; s > 1; s >>= 1) {
            m++;
        }

        t.mipCount = m;
        t.alphaBits = alpha;
        t.palettized = pal;
        return t;
    }

    // A model of the client's PasteToSection / PasteFromSkin and the paste functions they call, written from
    // CharacterComponent.cpp: whether it ends, and the furthest texel row and column it reads at every level, and
    // the destination levels it writes. `rectX`/`rectY` are where the source is read (0 for a section texture, the
    // section's place for a skin); `toDst` is the size of the destination texture.
    struct ClientRun {
        bool ends;
        bool readsInside;
        bool writesInside;
    };

    ClientRun RunClient(const TextureFacts& t, uint32_t targetWidth, uint32_t targetHeight, uint32_t rectX, uint32_t rectY, uint32_t sectionWidth, uint32_t sectionHeight, uint32_t dstSize) {
        ClientRun run = { true, true, true };
        uint32_t dstMips = MipCountFor(dstSize);

        if (t.width < targetWidth && t.height < targetHeight) {
            // Scale: level 0 read at (rect / 2 + texel / 2), then a 1:1 paste of mips 0.. into destination levels 1..
            if (rectX / 2 + (sectionWidth / 2 ? sectionWidth / 2 : 1) > t.width || rectY / 2 + (sectionHeight / 2 ? sectionHeight / 2 : 1) > t.height) {
                run.readsInside = false;
            }

            if (t.mipCount + 1 > dstMips) {
                run.writesInside = false;
            }

            if (t.mipCount > kCacheMipLevels) {
                run.readsInside = false; // the cache keeps 16 mip offsets: level 16 on is read from past them
            }

            return run;
        }

        uint32_t width = t.width;
        uint32_t mip = 0;
        uint32_t guard = 0;

        while (width != targetWidth) {
            width >>= 1;
            mip++;

            if (++guard > 64) {
                run.ends = false;
                return run;
            }
        }

        // Paste from `mip` on: source level m is read over (rect >> (m - mip)) + (size >> (m - mip)).
        for (uint32_t m = mip; m < t.mipCount; m++) {
            uint32_t d = m - mip;

            if (d >= dstMips) {
                run.writesInside = false;
                break;
            }

            if (m >= kCacheMipLevels) {
                run.readsInside = false; // TextureCacheGetMip(texture, 16) reads m_mipOffsets[16], past the array
                break;
            }

            uint32_t w = t.width >> m ? t.width >> m : 1;
            uint32_t h = t.height >> m ? t.height >> m : 1;
            uint32_t sw = sectionWidth >> d ? sectionWidth >> d : 1;
            uint32_t sh = sectionHeight >> d ? sectionHeight >> d : 1;

            if ((rectX >> d) + sw > w || (rectY >> d) + sh > h) {
                run.readsInside = false; // rows or columns past the level: read from outside the texture
            }
        }

        return run;
    }

    void TestSectionGuards() {
        struct Section {
            uint32_t w, h; // at the 512 layout
        };
        const Section sections[] = { { 256, 128 }, { 256, 64 } };
        uint32_t checked = 0;

        for (uint32_t level = 7; level <= 9; level++) {
            uint32_t dstSize = 1u << level;

            for (const Section& s : sections) {
                uint32_t sw = s.w >> (9 - level);
                uint32_t sh = s.h >> (9 - level);

                for (uint32_t w = 1; w <= 1100; w += (w < 64 ? 1 : 3)) {
                    for (uint32_t h : { 1u, 8u, 16u, 31u, 32u, 64u, 100u, 128u, 256u, 512u, 1024u, 2048u }) {
                        TextureFacts t = Facts(w, h);
                        PastePlan plan = PlanSectionPaste(t, sw, sh, dstSize);
                        ClientRun run = RunClient(t, sw, sh, 0, 0, sw, sh, dstSize);
                        bool safe = run.ends && run.readsInside && run.writesInside;
                        std::string what = "section " + Str(sw) + "x" + Str(sh) + " texture " + Str(w) + "x" + Str(h);

                        if (PastePlanOk(plan)) {
                            Check(safe, what + ": a pasted texture ends and stays inside");
                        } else {
                            Check(!safe, what + ": a refused texture would hang or overrun (" + std::string(VerdictName(plan.verdict)) + ")");
                        }

                        checked++;
                    }
                }
            }
        }

        Check(checked > 1000, "the section guard sweep ran");

        // The package's and the contract's sizes.
        PastePlan plan = PlanSectionPaste(Facts(256, 128), 128, 64, 256);
        Check(plan.verdict == kPasteMip && plan.mip == 1, "a package face lower (256x128) at level 8 pastes from mip 1");
        plan = PlanSectionPaste(Facts(256, 128), 256, 128, 512);
        Check(plan.verdict == kPasteMip && plan.mip == 0, "at level 9 from mip 0");
        plan = PlanSectionPaste(Facts(256, 128), 64, 32, 128);
        Check(plan.verdict == kPasteMip && plan.mip == 2, "at level 7 from mip 2");
        plan = PlanSectionPaste(Facts(128, 64), 256, 128, 512);
        Check(plan.verdict == kPasteScale, "a stock face (128x64) at level 9 is scaled");
        Check(PlanSectionPaste(Facts(384, 128), 128, 64, 256).verdict == kSkipSize, "a width of 384 would loop for ever");
        Check(PlanSectionPaste(Facts(514, 256), 128, 64, 256).verdict == kPasteMip && PlanSectionPaste(Facts(514, 256), 128, 64, 256).mip == 2, "514 halves to 257 and 128: the client stops there, so it pastes");
        Check(ClientMipLevel(512, 128) == 2 && ClientMipLevel(384, 128) == -1 && ClientMipLevel(100, 128) == -1 && ClientMipLevel(128, 128) == 0, "ClientMipLevel");
        Check(PowerOfTwoMultiple(514, 128) == -1 && PowerOfTwoMultiple(512, 128) == 2, "atlases need an exact power-of-two multiple");
        Check(PlanSectionPaste(Facts(100, 256), 128, 64, 256).verdict == kSkipSize, "narrower but not shorter would loop for ever");
        Check(PlanSectionPaste(Facts(256, 32), 256, 128, 512).verdict == kSkipSize, "too short reads past the end");
        Check(PlanSectionPaste(Facts(32, 16), 128, 64, 256).verdict == kSkipSize, "too small to scale reads past the end");
        Check(PlanSectionPaste(Facts(128, 1024), 128, 64, 256).verdict == kSkipTarget, "a tall texture has more levels than the character texture");
        TextureFacts one = Facts(256, 128);
        one.mipCount = 1;
        Check(PlanSectionPaste(one, 128, 64, 256).verdict == kSkipMips, "one level cannot paste from level 1");
        Check(PlanSectionPaste(Facts(0, 128), 128, 64, 256).verdict == kSkipFormat, "an empty texture");
    }

    void TestSkinGuards() {
        struct Rect {
            uint32_t x, y, w, h;
        };
        // s_sectionInfoRaw at the 512 layout.
        const Rect rects[10] = {
            { 0, 0, 256, 128 }, { 0, 128, 256, 128 }, { 0, 256, 256, 64 }, { 256, 0, 256, 128 }, { 256, 128, 256, 64 },
            { 256, 192, 256, 128 }, { 256, 320, 256, 128 }, { 256, 448, 256, 64 }, { 0, 320, 256, 64 }, { 0, 384, 256, 128 },
        };

        for (uint32_t level = 7; level <= 9; level++) {
            uint32_t dstSize = 1u << level;

            for (const Rect& r : rects) {
                uint32_t x = r.x >> (9 - level), y = r.y >> (9 - level), w = r.w >> (9 - level), h = r.h >> (9 - level);

                for (uint32_t tw : { 1u, 63u, 64u, 100u, 128u, 192u, 256u, 300u, 512u, 768u, 1024u, 2048u }) {
                    for (uint32_t th : { 1u, 64u, 128u, 256u, 300u, 512u, 1024u, 2048u }) {
                        TextureFacts t = Facts(tw, th, 0);
                        PastePlan plan = PlanSkinPaste(t, x + w, y + h, dstSize);
                        ClientRun run = RunClient(t, dstSize, dstSize, x, y, w, h, dstSize);
                        bool safe = run.ends && run.readsInside && run.writesInside;
                        std::string what = "skin " + Str(tw) + "x" + Str(th) + " rect " + Str(x) + "," + Str(y) + " at " + Str(dstSize);

                        if (PastePlanOk(plan)) {
                            Check(safe, what + ": a pasted skin ends and stays inside");
                        } else {
                            Check(!safe, what + ": a refused skin would hang or overrun (" + std::string(VerdictName(plan.verdict)) + ")");
                        }
                    }
                }
            }
        }

        PastePlan plan = PlanSkinPaste(Facts(512, 512, 0), 256, 256, 256);
        Check(plan.verdict == kPasteMip && plan.mip == 1, "a package skin at level 8 pastes from mip 1");
        plan = PlanSkinPaste(Facts(512, 512, 0), 512, 512, 512);
        Check(plan.verdict == kPasteMip && plan.mip == 0, "and at level 9 from mip 0");
        Check(PlanSkinPaste(Facts(256, 256, 0), 512, 512, 512).verdict == kPasteScale, "a stock skin at level 9 is scaled");
        Check(PlanSkinPaste(Facts(512, 256, 0), 512, 512, 512).verdict == kSkipSize, "a half-height skin cannot reach the foot");
        Check(PlanSkinPaste(Facts(512, 256, 0), 256, 128, 512).verdict == kPasteMip, "but can reach the upper arm");
        Check(PlanSkinPaste(Facts(1024, 1024, 0), 512, 512, 512).verdict == kPasteMip, "a 1024 skin pastes from mip 1 at level 9");
    }

    void TestAtlasGuards() {
        for (uint32_t level = 7; level <= 9; level++) {
            PastePlan plan = PlanAtlasPaste(Facts(512, 512, 8), 1u << level);
            Check(plan.verdict == kPasteMip && plan.mip == 9 - level, "a mark at level " + Str(level) + " pastes from mip " + Str(9 - level));
        }

        Check(PlanAtlasPaste(Facts(512, 512, 8), 256).mip == 1, "a mark into the 256 glow texture pastes from mip 1");
        Check(PlanAtlasPaste(Facts(512, 512, 8, false), 256).verdict == kSkipFormat, "a mark that is not palettized is refused, not painted green");
        Check(PlanAtlasPaste(Facts(512, 512, 2), 256).verdict == kSkipFormat, "alpha size 2 is refused");
        Check(PlanAtlasPaste(Facts(256, 256, 8), 512).verdict == kSkipSize, "a 256 mark is not scaled up to level 9");
        Check(PlanAtlasPaste(Facts(512, 256, 8), 256).verdict == kSkipSize, "a mark must be square");
        Check(PlanAtlasPaste(Facts(384, 384, 8), 128).verdict == kSkipSize, "384 is no power-of-two multiple");
        TextureFacts few = Facts(512, 512, 8);
        few.mipCount = 1;
        Check(PlanAtlasPaste(few, 256).verdict == kSkipMips, "one level cannot paste from level 1");
        Check(PlanAtlasPaste(Facts(512, 512, 0), 512).verdict == kPasteMip, "an opaque atlas (a skin's _Glow) pastes");
        Check(PlanAtlasPaste(Facts(512, 512, 1), 512).verdict == kPasteMip && PlanAtlasPaste(Facts(512, 512, 4), 512).verdict == kPasteMip, "alpha 1 and 4 paste");
    }

    // The client's PasteAtlasLayer: levels plan.mip .. plan.mip + the destination's levels - 1, but no further than
    // the chain; whether it reads a level past the cache's 16 mip offsets.
    bool AtlasReadsPastOffsets(const TextureFacts& t, uint32_t mip, uint32_t dstSize) {
        uint32_t last = mip + MipCountFor(dstSize) - 1;

        if (last >= t.mipCount) {
            last = t.mipCount - 1;
        }

        return last >= kCacheMipLevels;
    }

    // A BLP header whose side is 65536 or more makes a chain of 17 levels or more (TextureCalcMipCount has no cap),
    // and the pastes read every level of it: level 16 on would come from past m_mipOffsets[16]. Every plan refuses
    // such a texture outright (kSkipSize) instead of letting the paste read part of it; 16 levels still paste.
    void TestMipChainCap() {
        TextureFacts huge = Facts(65536, 65536);
        Check(huge.mipCount == 17, "a 65536 side makes 17 levels");
        Check(kCacheMipLevels == 16, "the cache keeps 16 mip offsets");

        for (uint32_t level = 7; level <= 9; level++) {
            uint32_t dstSize = 1u << level;
            std::string at = " at level " + Str(level);
            uint32_t sw = 256u >> (9 - level);
            uint32_t sh = 128u >> (9 - level);

            // Without the cap each of these pastes 1:1 (level 8: section from mip 9, skin and atlas from mip 8) and
            // reads level 16.
            Check(PlanSectionPaste(huge, sw, sh, dstSize).verdict == kSkipSize, "a 65536 section texture is refused" + at);
            Check(PlanSectionPaste(huge, sw / 2, sh / 2, dstSize).verdict == kSkipSize, "and into a half-width section" + at);
            Check(PlanSkinPaste(huge, dstSize, dstSize, dstSize).verdict == kSkipSize, "a 65536 skin is refused" + at);
            Check(PlanSkinPaste(huge, dstSize / 2, dstSize / 4, dstSize).verdict == kSkipSize, "for an upper arm too" + at);
            Check(PlanAtlasPaste(huge, dstSize).verdict == kSkipSize, "a 65536 mark is refused" + at);
            Check(PlanAtlasPaste(Facts(65536, 65536, 0), dstSize).verdict == kSkipSize, "a 65536 skin _Glow is refused" + at);

            for (uint32_t width : { sw, sw / 2 }) {
                ClientRun section = RunClient(huge, width, sh, 0, 0, width, sh, dstSize);
                Check(section.ends && section.writesInside && !section.readsInside, "the client's paste into a " + Str(width) + " wide section would read level 16" + at);
            }

            ClientRun skin = RunClient(huge, dstSize, dstSize, 0, 0, dstSize, dstSize, dstSize);
            Check(skin.ends && skin.writesInside && !skin.readsInside, "the client's skin paste would read level 16" + at);
            uint32_t atlasMip = static_cast<uint32_t>(PowerOfTwoMultiple(huge.width, dstSize));
            Check(atlasMip == 16 - level && AtlasReadsPastOffsets(huge, atlasMip, dstSize), "the client's atlas paste would read level 16" + at);

            // The largest chain the cache holds still pastes, and the client's paste stays inside it.
            TextureFacts big = Facts(32768, 32768);
            PastePlan plan = PlanSkinPaste(big, dstSize, dstSize, dstSize);
            ClientRun bigRun = RunClient(big, dstSize, dstSize, 0, 0, dstSize, dstSize, dstSize);
            Check(big.mipCount == 16 && PastePlanOk(plan) == (bigRun.ends && bigRun.readsInside && bigRun.writesInside), "a 32768 skin pastes exactly when the client stays inside" + at);
            plan = PlanAtlasPaste(big, dstSize);
            Check(plan.verdict == kPasteMip && !AtlasReadsPastOffsets(big, plan.mip, dstSize), "a 32768 mark pastes and reads no level past 15" + at);
        }

        // Tall or wide alone is enough to make the chain.
        Check(PlanSectionPaste(Facts(128, 65536), 128, 64, 256).verdict == kSkipSize, "a 128x65536 face is refused for its chain");
        Check(PlanSkinPaste(Facts(65536, 32768, 0), 128, 64, 256).verdict == kSkipSize, "a 65536x32768 skin is refused for its chain");
        Check(PlanAtlasPaste(Facts(1u << 20, 1u << 20), 256).verdict == kSkipSize, "a 2^20 mark is refused");

        // Should a chain past the offsets reach MipsReadable, it is refused, never cut down.
        uint32_t offsets[16] = {};

        for (uint32_t m = 0; m < 16; m++) {
            offsets[m] = 1172;
        }

        Check(!MipsReadable(offsets, 0xFFFFFFFFu, huge, 8, 16, false), "MipsReadable refuses level 16");
    }

    void TestMipBounds() {
        TextureFacts t = Facts(512, 512, 8);
        uint32_t offsets[16] = {};
        uint32_t at = 1172; // BLP2 header with its palette

        for (uint32_t m = 0; m < t.mipCount; m++) {
            offsets[m] = at;
            at += PalMipBytes(512, 512, m, 8);
        }

        Check(PalMipBytes(512, 512, 0, 8) == 524288 && PalMipBytes(512, 512, 9, 8) == 2 && PalMipBytes(256, 128, 0, 1) == 32768 + 4096, "mip sizes");
        Check(at < (1u << 20), "a 512 mark with 8-bit alpha is under 1 MB (the texture cache's 20-bit size)");
        Check(MipsReadable(offsets, at, t, 0, 9, true), "a whole mark is readable");
        Check(!MipsReadable(offsets, at - 1, t, 0, 9, true), "a file one byte short is not");
        Check(MipsReadable(offsets, at - 1, t, 0, 8, true), "unless the last level is not read");
        offsets[9] = 0;
        Check(!MipsReadable(offsets, at, t, 0, 9, true), "a missing level is refused for marks");
        Check(MipsReadable(offsets, at, t, 0, 9, false), "and allowed for stock textures (it reads the header, inside the file)");
        Check(!MipsReadable(offsets, at, t, 0, 16, false) && !MipsReadable(offsets, at, t, 3, 2, false), "bad ranges");
    }

    // markforge.py fixture's Bad files (tests/fixture_bad_facts.inc, numbers only): what the fixture manifest says
    // the exe does with each, held against the guards the mark layer runs (PasteAtlasLayer: PlanAtlasPaste, then
    // BleakPastePlanUsable's MipsReadable from the plan's level to the last one the paste reads, every offset there)
    // and the _Glow pairing (GlowFileFor: palettized, the mark's width, height and alphaSize), at both character
    // texture sizes.
    struct BadFile {
        const char* name;
        bool glow;
        uint32_t width;
        uint32_t height;
        uint32_t mipCount;
        uint32_t alphaBits;
        bool palettized;
        uint32_t size;
        uint32_t offsets[16];
        bool pastes;
        uint32_t markWidth;
        uint32_t markHeight;
        uint32_t markAlphaBits;
    };

    const BadFile kBadFiles[] = {
#include "fixture_bad_facts.inc"
    };

    bool LayerPastes(const BadFile& f, uint32_t dstSize) {
        TextureFacts t = { f.width, f.height, f.mipCount, f.alphaBits, f.palettized };
        PastePlan plan = PlanAtlasPaste(t, dstSize);

        if (!PastePlanOk(plan)) {
            return false;
        }

        uint32_t last = plan.mip + MipCountFor(dstSize) - 1;

        if (last > t.mipCount - 1) {
            last = t.mipCount - 1;
        }

        return MipsReadable(f.offsets, f.size, t, plan.mip, last, true);
    }

    void TestFixtureBadFiles() {
        uint32_t layers = 0;

        for (const BadFile& f : kBadFiles) {
            if (f.glow) {
                bool used = f.palettized && f.width == f.markWidth && f.height == f.markHeight && f.alphaBits == f.markAlphaBits;
                Check(used == f.pastes, std::string(f.name) + ": the exe " + (used ? "uses" : "skips") + " this _Glow, as the fixture manifest says");
                continue;
            }

            layers++;

            for (uint32_t dst : { 256u, 512u }) {
                bool pastes = LayerPastes(f, dst);
                Check(pastes == f.pastes, std::string(f.name) + " at a " + Str(dst) + " character texture: the exe " + (pastes ? "pastes" : "skips") + " it, as the fixture manifest says");
            }
        }

        Check(layers == 9, "the fixture has its nine Bad layers");
    }

    // A tiny palettized atlas: `w` x `h` indices then the alpha plane.
    std::vector<uint8_t> Atlas(uint32_t w, uint32_t h, uint32_t alphaBits, uint8_t index, uint32_t alpha) {
        uint32_t n = w * h;
        std::vector<uint8_t> data(n + (n * alphaBits + 7) / 8, 0);

        for (uint32_t i = 0; i < n; i++) {
            data[i] = index;

            if (alphaBits == 8) {
                data[n + i] = static_cast<uint8_t>(alpha);
            } else if (alphaBits == 4) {
                data[n + i / 2] |= static_cast<uint8_t>((alpha >> 4) << (4 * (i & 1)));
            } else if (alphaBits == 1 && alpha) {
                data[n + i / 8] |= static_cast<uint8_t>(1 << (i & 7));
            }
        }

        return data;
    }

    void TestPixels() {
        uint8_t palette[1024] = {};
        palette[4 * 3 + 0] = 30;  // index 3: b 30, g 60, r 90
        palette[4 * 3 + 1] = 60;
        palette[4 * 3 + 2] = 90;

        std::vector<uint8_t> dst(8 * 8 * 4, 200);
        std::vector<uint8_t> a8 = Atlas(8, 8, 8, 3, 128);
        PalMip mip = { a8.data(), 8, 8, 8 };
        PasteAtlasRect(mip, palette, 2, 2, 3, 3, dst.data(), 8 * 4);
        uint8_t* p = &dst[(2 * 8 + 2) * 4];
        Check(p[0] == ((127 * 200 + 128 * 30) >> 8) && p[1] == ((127 * 200 + 128 * 60) >> 8) && p[2] == ((127 * 200 + 128 * 90) >> 8) && p[3] == 255, "8-bit alpha blends with the client's arithmetic");
        Check(dst[(1 * 8 + 1) * 4] == 200 && dst[(5 * 8 + 5) * 4] == 200, "only the rectangle changes");

        std::vector<uint8_t> clear = Atlas(8, 8, 8, 3, 0);
        std::vector<uint8_t> keep(8 * 8 * 4, 200);
        PalMip clearMip = { clear.data(), 8, 8, 8 };
        PasteAtlasRect(clearMip, palette, 0, 0, 8, 8, keep.data(), 8 * 4);
        Check(keep == std::vector<uint8_t>(8 * 8 * 4, 200), "alpha 0 leaves the texture exactly as it was (no 1/256 darkening)");

        std::vector<uint8_t> a1 = Atlas(8, 8, 1, 3, 255);
        std::vector<uint8_t> d1(8 * 8 * 4, 0);
        PalMip mip1 = { a1.data(), 8, 8, 1 };
        PasteAtlasRect(mip1, palette, 0, 0, 8, 8, d1.data(), 8 * 4);
        Check(d1[2] == ((255 * 90) >> 8), "1-bit alpha");

        std::vector<uint8_t> a4 = Atlas(8, 8, 4, 3, 0xF0);
        std::vector<uint8_t> d4(8 * 8 * 4, 0);
        PalMip mip4 = { a4.data(), 8, 8, 4 };
        PasteAtlasRect(mip4, palette, 0, 0, 8, 8, d4.data(), 8 * 4);
        Check(d4[4 * 9 + 2] == ((255 * 90) >> 8) && AlphaAt(a4.data() + 64, 4, 1) == 255 && AlphaAt(a4.data() + 64, 4, 0) == 255, "4-bit alpha, both nibbles");

        std::vector<uint8_t> a0 = Atlas(8, 8, 0, 3, 0);
        std::vector<uint8_t> d0(8 * 8 * 4, 7);
        PalMip mip0 = { a0.data(), 8, 8, 0 };
        PasteAtlasRect(mip0, palette, 0, 0, 8, 8, d0.data(), 8 * 4);
        Check(d0[0] == 30 && d0[1] == 60 && d0[2] == 90 && d0[3] == 255, "an opaque atlas copies");

        std::vector<uint8_t> clip(8 * 8 * 4, 1);
        PasteAtlasRect(mip0, palette, 6, 6, 10, 10, clip.data(), 8 * 4);
        Check(clip[(7 * 8 + 7) * 4] == 30 && clip[(5 * 8 + 5) * 4] == 1, "a rectangle past the edge is clipped");
        PasteAtlasRect(mip0, palette, 9, 0, 1, 1, clip.data(), 8 * 4);

        uint8_t black[1024];
        BlackPalette(black);
        std::vector<uint8_t> glow(8 * 8 * 4, 200);
        PasteAtlasRect(mip, black, 0, 0, 8, 8, glow.data(), 8 * 4);
        Check(glow[0] == ((127 * 200) >> 8), "black through alpha darkens the glow under it by the layer's alpha");

        std::vector<uint8_t> fill(4 * 4 * 4, 9);
        FillRect(fill.data(), 16, 1, 1, 2, 2, 0xFF000000u);
        Check(fill[(1 * 4 + 1) * 4] == 0 && fill[(1 * 4 + 1) * 4 + 3] == 255 && fill[0] == 9, "FillRect");
    }

    // The pass rule on a 16 x 8 strip of two "sections" (left 8 columns, right 8 columns): a plain skin, a glowing
    // mark across both, and a chest item over the right half.
    void TestPassRule() {
        Check(GlowLayer(false, true) == kGlowNone && GlowLayer(true, true) == kGlowEmit && GlowLayer(true, false) == kGlowOcclude, "GlowLayer");
        Check(WantsGlow(true, false, 1) && !WantsGlow(false, false, 1) && !WantsGlow(true, true, 1) && !WantsGlow(true, false, 0), "WantsGlow");

        const uint32_t w = 16, h = 8, stride = w * 4;
        uint8_t black[1024];
        BlackPalette(black);
        uint8_t markGlowPal[1024] = {};
        markGlowPal[4 * 1 + 0] = 255; // index 1: bright blue light

        std::vector<uint8_t> markAlpha = Atlas(w, h, 8, 1, 0);

        for (uint32_t y = 2; y < 6; y++) {
            for (uint32_t x = 0; x < w; x++) {
                markAlpha[w * h + y * w + x] = 255; // a band across both halves
            }
        }

        std::vector<uint8_t> item = Atlas(8, h, 8, 2, 255); // an opaque chest for the right section

        std::vector<uint8_t> out(w * h * 4, 0x55); // stale texels of another character
        FillRect(out.data(), stride, 0, 0, w, h, 0xFF000000u); // each section starts black (skin without _Glow)
        PalMip markMip = { markAlpha.data(), w, h, 8 };

        for (uint32_t section = 0; section < 2; section++) {
            PasteAtlasRect(markMip, markGlowPal, section * 8, 0, 8, h, out.data(), stride); // emit
        }

        PalMip itemMip = { item.data(), 8, h, 8 };
        PasteAtlasRect(itemMip, black, 0, 0, 8, h, out.data() + 8 * 4, stride); // occlude: the item's own section texture

        Check(out[(3 * w + 2) * 4 + 0] == 254 && out[(3 * w + 2) * 4 + 2] == 0, "the mark glows on the bare section");
        Check(out[(0 * w + 2) * 4 + 0] == 0, "no glow beside the mark");
        Check(out[(3 * w + 10) * 4 + 0] == 0, "the chest hides the mark's glow");
        Check(AnyLight(out.data(), stride, 0, 0, 8, h) && !AnyLight(out.data(), stride, 8, 0, 8, h), "only the bare section holds light (the draw's section mask)");
        Check(!AnyLight(out.data(), stride, 0, 0, 8, 2), "no light above the band");
    }

    void TestBudget() {
        Check(GlowSize(128) == 128 && GlowSize(256) == 256 && GlowSize(512) == 256, "glow textures are 256 at most");
        Check(TextureBytes(256, true) == 43704, "a 256 DXT1 glow texture with mips is 43,704 bytes");
        Check(TextureBytes(256, false) == 174762, "a 256 RGB565 one 174,762 bytes");
        Check(TextureBytes(512, false) == 699050, "a 512 RGB565 one would be 699,050 (the 683 KB of CRITIC 18)");
        Check(kGlowBudgetBytes / TextureBytes(256, true) == 191 && kGlowBudgetBytes / TextureBytes(256, false) == 48, "the budget holds 191 DXT1 or 48 RGB565 glow textures");
        Check(GlowFits(0, 43704, kGlowBudgetBytes) && !GlowFits(kGlowBudgetBytes - 10, 43704, kGlowBudgetBytes) && !GlowFits(0, kGlowBudgetBytes + 1, kGlowBudgetBytes), "GlowFits");
        Check(InGlowRange(59.0f * 59.0f, false) && !InGlowRange(61.0f * 61.0f, false), "glow starts within 60 yards");
        Check(InGlowRange(69.0f * 69.0f, true) && !InGlowRange(71.0f * 71.0f, true), "and stays until beyond 70");
        Check(!InGlowRange(std::numeric_limits<float>::quiet_NaN(), true), "a NaN distance is out of range");
        Check(MipCountFor(256) == 9 && MipCountFor(512) == 10 && MipCountFor(1) == 1, "MipCountFor");
    }

    // The distance is current only while the scene animates the model (CM2Model::m_frameStamp against its scene's).
    void TestFreshDistance() {
        Check(FramesSinceAnimated(kNeverAnimated, 500) == kNeverAnimated && !DistanceFresh(kNeverAnimated), "a model never animated has no distance");
        Check(FramesSinceAnimated(500, 500) == 0 && DistanceFresh(0), "animated this frame: fresh");
        Check(FramesSinceAnimated(498, 500) == 2 && DistanceFresh(2), "two frames ago: still fresh");
        Check(FramesSinceAnimated(497, 500) == 3 && !DistanceFresh(3), "three frames ago: stale");
        Check(DistanceFresh(FramesSinceAnimated(0xFFFFFFFEu, 0)), "the scene's stamp wrapping round keeps it fresh");
        Check(!DistanceFresh(FramesSinceAnimated(501, 500)), "a stamp ahead of the scene's counts as stale");

        // The defect: m_scaleSq is 0 until the first animation, and InGlowRange took 0 as 0 yards away.
        Check(InGlowRange(0.0f, false), "InGlowRange alone takes an unanimated model's 0 as in range");
        Check(!GlowMayCreate(kNeverAnimated, 0.0f, false) && !GlowMayCreate(kNeverAnimated, 0.0f, true), "an unanimated character gets no glow texture");
        Check(!GlowMayCreate(40, 10.0f * 10.0f, true), "nor does one measured in range but not since");
        Check(GlowMayCreate(1, 30.0f * 30.0f, false) && !GlowMayCreate(1, 61.0f * 61.0f, false) && GlowMayCreate(1, 65.0f * 65.0f, true), "a fresh distance: within 60 yards, or 70 once in range");

        Check(!GlowMustDrop(40, 200.0f * 200.0f, true) && !GlowMustDrop(kNeverAnimated, 0.0f, true), "a stale distance never drops a texture");
        Check(GlowMustDrop(0, 71.0f * 71.0f, true) && !GlowMustDrop(0, 69.0f * 69.0f, true), "a fresh one beyond 70 yards does");
        Check(GlowMustDrop(0, std::numeric_limits<float>::quiet_NaN(), true), "and a fresh NaN does");

        Check(GlowRangeAfter(40, 0.0f, true) && !GlowRangeAfter(40, 0.0f, false), "a stale distance leaves the range answer as it was");
        Check(GlowRangeAfter(0, 65.0f * 65.0f, true) && !GlowRangeAfter(0, 65.0f * 65.0f, false), "a fresh one decides it, with the margin");
    }

    void TestEvictionRules() {
        const float near5 = 5.0f * 5.0f;
        GlowHolder unseen = { 300, 20.0f * 20.0f };
        GlowHolder unseenLonger = { 900, 20.0f * 20.0f };
        GlowHolder near3 = { 0, 3.0f * 3.0f };
        GlowHolder within = { 0, 9.5f * 9.5f };
        GlowHolder beyond = { 1, 10.5f * 10.5f };
        GlowHolder far50 = { 0, 50.0f * 50.0f };
        GlowHolder nan = { 0, std::numeric_limits<float>::quiet_NaN() };

        Check(MayEvict(unseen, near5) && MayEvict(unseen, 59.0f * 59.0f), "a holder the scene has not measured lately may give its texture up");
        Check(!MayEvict(near3, near5), "a nearer holder may not");
        Check(!MayEvict(within, near5) && MayEvict(beyond, near5), "a farther one only beyond the 5 yard margin");
        Check(MayEvict(nan, near5), "a NaN distance counts as far");
        Check(EvictsBefore(unseen, far50) && !EvictsBefore(far50, unseen), "unseen holders go before measured ones");
        Check(EvictsBefore(unseenLonger, unseen) && !EvictsBefore(unseen, unseenLonger), "the longest unseen first");
        Check(EvictsBefore(far50, beyond) && !EvictsBefore(beyond, far50), "then the farthest first");
        Check(EvictsBefore(nan, far50) && !EvictsBefore(far50, nan), "a NaN distance as the farthest");

        // PickEviction walks a list like s_glowList.
        struct Item {
            GlowHolder holder;
            bool texture;
            Item* next;
        };

        std::vector<Item> items = {
            { near3, true, nullptr }, { far50, true, nullptr }, { unseen, true, nullptr }, { beyond, false, nullptr }, { unseenLonger, true, nullptr },
        };

        for (size_t i = 0; i + 1 < items.size(); i++) {
            items[i].next = &items[i + 1];
        }

        auto next = [](Item* item) { return item->next; };
        auto holderOf = [](Item* item, GlowHolder& out) {
            out = item->holder;
            return item->texture;
        };

        Check(PickEviction(&items[0], next, holderOf, near5) == &items[4], "PickEviction: the longest unseen holder");
        items[4].texture = false;
        items[2].texture = false;
        Check(PickEviction(&items[0], next, holderOf, near5) == &items[1], "then the farthest one beyond the margin");
        Check(PickEviction(&items[0], next, holderOf, 48.0f * 48.0f) == nullptr, "nobody for a candidate near the farthest holder");
        items[1].texture = false;
        Check(PickEviction(&items[0], next, holderOf, near5) == nullptr, "nor a nearer one, nor one with no texture");
        Check(PickEviction<Item>(nullptr, next, holderOf, near5) == nullptr, "an empty list");
    }

    // GlowSweep and GlowRenderPrep's create branch (WoW/Common/ComponentCore/CharacterComponent.cpp) on a crowd, with
    // bakes that answer at once: before the fix (InGlowRange of m_scaleSq, first come first served) and after.
    struct Character {
        uint32_t stamp;   // CM2Model::m_frameStamp
        float distanceSq; // CM2Model::m_scaleSq
        bool inRange;     // GLOW_IN_RANGE
        bool requested;   // GLOW_REQUESTED
        bool texture;
        Character* next;
    };

    struct Crowd {
        std::vector<Character> people;
        uint32_t sceneStamp;
        uint32_t used;
        uint32_t budget;
        uint32_t bytes;
        uint32_t bakes;
        bool fixed;

        Crowd(size_t count, uint32_t slots, bool fixedRules)
            : people(count), sceneStamp(1000), used(0), budget(slots * TextureBytes(256, false)), bytes(TextureBytes(256, false)), bakes(0), fixed(fixedRules) {
            for (size_t i = 0; i < count; i++) {
                people[i] = { kNeverAnimated, 0.0f, false, false, false, nullptr };
                people[i].next = i + 1 < count ? &people[i + 1] : nullptr;
            }
        }

        // The scene animated `c` this frame, at `yards` from the camera.
        void Seen(size_t c, float yards) {
            people[c].stamp = sceneStamp;
            people[c].distanceSq = yards * yards;
        }

        void Destroy(Character& c) {
            if (c.texture) {
                c.texture = false;
                used -= bytes;
            }
        }

        // A whole bake ends (GlowRenderPrep): the texture is made if the rules and the budget allow.
        void Bake(Character& c) {
            bakes++;
            c.requested = false;
            uint32_t frames = FramesSinceAnimated(c.stamp, sceneStamp);
            bool may = fixed ? GlowMayCreate(frames, c.distanceSq, c.inRange) : InGlowRange(c.distanceSq, c.inRange);
            c.inRange = fixed ? GlowRangeAfter(frames, c.distanceSq, c.inRange) : may;

            if (!c.texture && may && GlowFits(used, bytes, budget)) {
                c.texture = true;
                used += bytes;
            }
        }

        void Sweep() {
            uint32_t requestedBytes = 0;

            for (Character* c = &people[0]; c; c = c->next) {
                uint32_t frames = FramesSinceAnimated(c->stamp, sceneStamp);
                bool was = c->inRange;

                if (!fixed) {
                    c->inRange = InGlowRange(c->distanceSq, was);

                    if (c->texture && !c->inRange) {
                        Destroy(*c);
                    } else if (!c->texture && c->inRange && !c->requested && GlowFits(used, bytes, budget)) {
                        c->requested = true;
                    }

                    continue;
                }

                c->inRange = GlowRangeAfter(frames, c->distanceSq, was);

                if (c->texture) {
                    if (GlowMustDrop(frames, c->distanceSq, was)) {
                        Destroy(*c);
                    }

                    continue;
                }

                if (!GlowMayCreate(frames, c->distanceSq, was) || c->requested) {
                    continue;
                }

                uint32_t now = sceneStamp;
                auto next = [](Character* item) { return item->next; };
                auto holderOf = [now](Character* item, GlowHolder& out) {
                    out.framesSince = FramesSinceAnimated(item->stamp, now);
                    out.distanceSq = item->distanceSq;
                    return item->texture;
                };

                while (!GlowFits(used + requestedBytes, bytes, budget)) {
                    Character* holder = PickEviction(&people[0], next, holderOf, c->distanceSq);

                    if (!holder) {
                        break;
                    }

                    Destroy(*holder);
                }

                if (GlowFits(used + requestedBytes, bytes, budget)) {
                    c->requested = true;
                    requestedBytes += bytes;
                }
            }

            for (Character& c : people) {
                if (c.requested) {
                    Bake(c);
                }
            }
        }

        uint32_t Holders() const {
            uint32_t n = 0;

            for (const Character& c : people) {
                n += c.texture ? 1 : 0;
            }

            return n;
        }
    };

    void TestGlowCrowd() {
        // Arriving in a city: 60 marked characters behind the camera and beyond 33 yards make their first whole bake
        // before the scene ever animates them; then one walks up 5 yards in front of the camera.
        for (int fixed = 0; fixed < 2; fixed++) {
            Crowd crowd(61, 48, fixed != 0);

            for (size_t i = 0; i < 60; i++) {
                crowd.Bake(crowd.people[i]);
            }

            crowd.Seen(60, 5.0f);

            for (int frame = 0; frame < 20; frame++) {
                crowd.sceneStamp++;
                crowd.Seen(60, 5.0f);
                crowd.Sweep();
            }

            if (!fixed) {
                Check(crowd.Holders() == 48 && !crowd.people[60].texture, "before: unseen characters fill the budget and the one in front gets no glow");
            } else {
                Check(crowd.Holders() == 1 && crowd.people[60].texture, "after: only the character in front has a glow texture");
            }
        }

        // 48 characters measured within 20 yards, then the camera turns away (they are beyond 33 yards, not animated):
        // they keep their textures; one walking up in front takes the longest unseen one's.
        Crowd crowd(49, 48, true);

        for (size_t i = 0; i < 48; i++) {
            crowd.Seen(i, 10.0f + static_cast<float>(i) * 0.2f);
        }

        crowd.Sweep();
        Check(crowd.Holders() == 48, "48 characters in range hold the budget");
        uint32_t bakes = crowd.bakes;

        crowd.people[5].stamp = crowd.sceneStamp - 1; // seen a frame before the others
        crowd.sceneStamp += 100;

        for (int sweep = 0; sweep < 5; sweep++) {
            crowd.sceneStamp++;
            crowd.Sweep();
        }

        Check(crowd.Holders() == 48 && crowd.bakes == bakes, "turning away keeps every glow texture and bakes nothing");

        crowd.Seen(48, 5.0f);
        crowd.Sweep();
        Check(crowd.people[48].texture && crowd.Holders() == 48, "the character in front takes one");
        Check(!crowd.people[5].texture && crowd.people[0].texture, "from the longest unseen holder");

        // Turning back to all but the first: they are measured where they are, one beyond 70 yards lets go, and the
        // room goes to the one that gave its texture up; the first, still unseen, keeps its own.
        for (size_t i = 1; i < 48; i++) {
            crowd.Seen(i, 20.0f);
        }

        crowd.Seen(1, 80.0f);
        crowd.Seen(48, 5.0f);
        bakes = crowd.bakes;
        crowd.Sweep();
        Check(!crowd.people[1].texture && crowd.people[5].texture && crowd.people[0].texture && crowd.Holders() == 48, "a holder measured beyond 70 yards lets go, the room goes to the one waiting in range");
        Check(crowd.bakes == bakes + 1, "with one bake");

        // Two characters at about the same distance do not take the last place from each other in turn.
        Crowd pair(2, 1, true);
        pair.Seen(0, 30.0f);
        pair.Sweep();
        pair.Seen(0, 30.0f);
        pair.Seen(1, 27.0f);
        bakes = pair.bakes;

        for (int sweep = 0; sweep < 5; sweep++) {
            pair.sceneStamp++;
            pair.Seen(0, 30.0f);
            pair.Seen(1, 27.0f);
            pair.Sweep();
        }

        Check(pair.people[0].texture && !pair.people[1].texture && pair.bakes == bakes, "within the margin nobody gives way and nothing bakes");

        pair.sceneStamp++;
        pair.Seen(0, 30.0f);
        pair.Seen(1, 20.0f);
        pair.Sweep();

        for (int sweep = 0; sweep < 5; sweep++) {
            pair.sceneStamp++;
            pair.Seen(0, 30.0f);
            pair.Seen(1, 20.0f);
            pair.Sweep();
        }

        Check(!pair.people[0].texture && pair.people[1].texture && pair.bakes == bakes + 1, "a character well nearer takes it once, and keeps it");

        // A sweep asks for no more bakes than the budget has room for.
        Crowd room(3, 1, true);
        room.Seen(0, 10.0f);
        room.Seen(1, 12.0f);
        room.Seen(2, 14.0f);
        room.Sweep();
        Check(room.bakes == 1 && room.people[0].texture, "one place, one bake");
    }

    // A glow texture let go of while a copy of the model holds it latches black (CharacterComponent.cpp,
    // GlowLetGoUserFunc): every mip of every glow texture the client makes must fit in kGlowBlackBytes, since the
    // OpenGL upload reads whatever it latches.
    void TestLetGoLatch() {
        bool stride = true;

        for (uint32_t w = 1; w <= 512; w++) {
            uint32_t blocks = (w >> 2) ? 8 * (w >> 2) : 8; // UpdateGlowTexture's DXT1 stride before GlowLatchStride
            stride = stride && GlowLatchStride(w, true) == blocks && GlowLatchStride(w, false) == 4 * w;
        }

        Check(stride, "GlowLatchStride: 4x4 DXT1 blocks of 8 bytes (one at least), or 4 bytes a texel");

        bool fits = true;
        uint32_t largest = 0;
        const uint32_t componentSizes[] = { 128, 256, 512, 1024 };

        for (uint32_t componentSize : componentSizes) {
            uint32_t size = GlowSize(componentSize);

            for (int dxt1 = 0; dxt1 < 2; dxt1++) {
                for (uint32_t s = size; s; s >>= 1) {
                    uint32_t bytes = GlowLatchBytes(s, s, dxt1 != 0);
                    fits = fits && bytes <= kGlowBlackBytes;
                    largest = bytes > largest ? bytes : largest;
                }
            }
        }

        Check(fits, "every mip of every glow texture fits in the black buffer");
        Check(largest == kGlowBlackBytes, "and the largest fills it (256 x 256 ARGB)");
        Check(GlowLatchBytes(256, 256, true) == 32768 && GlowLatchBytes(2, 2, true) == 8 && GlowLatchBytes(1, 1, false) == 4, "GlowLatchBytes");
    }

    void TestDump() {
        uint8_t header[18];
        TgaHeader(header, 256, 512);
        Check(header[2] == 2 && header[12] == 0 && header[13] == 1 && header[14] == 0 && header[15] == 2 && header[16] == 32 && header[17] == 0x28, "TGA header");

        uint8_t texels[64];
        const uint8_t red[8] = { 0x00, 0xF8, 0x1F, 0x00, 0, 0, 0, 0 };
        DecodeDxt1Block(red, texels);
        Check(texels[0] == 0 && texels[1] == 0 && texels[2] == 255 && texels[3] == 255 && texels[60] == 0 && texels[62] == 255, "DXT1: index 0 everywhere is colour 0");
        const uint8_t mix[8] = { 0x00, 0xF8, 0x1F, 0x00, 0x0E, 0, 0, 0 }; // texel 1 index 3, texel 2.. index 0
        DecodeDxt1Block(mix, texels);
        Check(texels[4 + 2] == 85 && texels[4 + 0] == 170, "DXT1: index 3 is 1/3 of the way from colour 0 to colour 1");
        const uint8_t three[8] = { 0x1F, 0x00, 0x00, 0xF8, 0x0F, 0, 0, 0 }; // c0 < c1: texel 0 index 3, texel 1 index 3
        DecodeDxt1Block(three, texels);
        Check(texels[3] == 0 && texels[0] == 0 && texels[2] == 0, "DXT1: c0 <= c1 makes index 3 transparent black");
    }
}

int main() {
    TestFaces();
    TestFeatures();
    TestNames();
    TestNameSet();
    TestSectionGuards();
    TestSkinGuards();
    TestAtlasGuards();
    TestMipChainCap();
    TestMipBounds();
    TestFixtureBadFiles();
    TestPixels();
    TestPassRule();
    TestBudget();
    TestFreshDistance();
    TestEvictionRules();
    TestGlowCrowd();
    TestLetGoLatch();
    TestDump();

    printf("test_marks_core: %d checks, %d failed\n", s_checks, s_failed);
    return s_failed ? 1 : 0;
}
