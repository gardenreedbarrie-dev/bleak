// Host test of WoW/Common/BleakholdEmoji.h (the client's emoji kits and bubble timeline), built and run by
// test_client_header.py: c++ -std=c++17 -Wall -Wextra -Werror -I<repo>. Exits 0 when every check passes.

#include "WoW/Common/BleakholdEmoji.h"
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>

static int s_failures = 0;

#define CHECK(cond) \
    do { \
        if (!(cond)) { \
            std::fprintf(stderr, "%s:%d: CHECK failed: %s\n", __FILE__, __LINE__, #cond); \
            s_failures++; \
        } \
    } while (0)

static bool Near(float a, float b) {
    return std::fabs(a - b) <= 1e-5f;
}

// FromKit's result for kitId, or -1 for an ordinary kit.
static int64_t Emoji(uint32_t kitId) {
    uint32_t emoji = 0xDEADBEEF;

    if (!BleakholdEmojiFromKit(kitId, &emoji)) {
        CHECK(emoji == 0xDEADBEEF);  // untouched
        return -1;
    }

    return emoji;
}

struct Pose {
    bool live;
    float scale;
    float alpha;
    float rise;
};

static Pose PoseAt(uint32_t ageMs) {
    Pose p = { false, -9.0f, -9.0f, -9.0f };
    p.live = BleakholdEmojiPose(ageMs, &p.scale, &p.alpha, &p.rise);
    return p;
}

static void TestConstants() {
    CHECK(BLEAKHOLD_EMOJI_KIT_BASE == 900000);
    CHECK(BLEAKHOLD_EMOJI_MAX == 256);
    CHECK(BLEAKHOLD_EMOJI_POP_MS == 120);
    CHECK(BLEAKHOLD_EMOJI_SETTLE_MS == 250);
    CHECK(BLEAKHOLD_EMOJI_HOLD_MS == 2750);
    CHECK(BLEAKHOLD_EMOJI_LIFETIME_MS == 3250);
    CHECK(Near(BLEAKHOLD_EMOJI_POP_SCALE, 1.25f));

    char path[64];
    std::snprintf(path, sizeof(path), BLEAKHOLD_EMOJI_TEXTURE, 7u);
    CHECK(std::strcmp(path, "Interface\\Bleakhold\\Emoji\\Emoji007") == 0);
    std::snprintf(path, sizeof(path), BLEAKHOLD_EMOJI_TEXTURE, 255u);
    CHECK(std::strcmp(path, "Interface\\Bleakhold\\Emoji\\Emoji255") == 0);
}

static void TestFromKit() {
    CHECK(Emoji(899999) == -1);
    CHECK(Emoji(900000) == 0);
    CHECK(Emoji(900007) == 7);
    CHECK(Emoji(900255) == 255);
    CHECK(Emoji(900256) == -1);
    CHECK(Emoji(0) == -1);
    CHECK(Emoji(UINT32_MAX) == -1);
}

static void TestPose() {
    Pose p = PoseAt(0);
    CHECK(p.live && Near(p.scale, 0.0f) && Near(p.alpha, 1.0f) && Near(p.rise, 0.0f));

    p = PoseAt(60);
    CHECK(p.live && Near(p.scale, 0.9375f) && Near(p.alpha, 1.0f) && Near(p.rise, 0.0f));

    p = PoseAt(120);
    CHECK(p.live && Near(p.scale, 1.25f) && Near(p.alpha, 1.0f) && Near(p.rise, 0.0f));

    p = PoseAt(185);
    CHECK(p.live && Near(p.scale, 1.125f) && Near(p.alpha, 1.0f) && Near(p.rise, 0.0f));

    static const uint32_t holding[] = { 250, 1000, 2749, 2750 };

    for (uint32_t age : holding) {
        p = PoseAt(age);
        CHECK(p.live && Near(p.scale, 1.0f) && Near(p.alpha, 1.0f) && Near(p.rise, 0.0f));
    }

    p = PoseAt(3000);
    CHECK(p.live && Near(p.scale, 1.0f) && Near(p.alpha, 0.5f) && Near(p.rise, 0.5f));

    p = PoseAt(3249);
    CHECK(p.live && p.alpha > 0.0f && p.alpha < 0.01f && p.rise > 0.99f && p.rise <= 1.0f);

    CHECK(!PoseAt(3250).live);
    CHECK(!PoseAt(10000).live);
    CHECK(!PoseAt(UINT32_MAX).live);

    // No jumps between the phases: the pose moves by small steps from one ms to the next, and stays in range.
    Pose prev = PoseAt(0);

    for (uint32_t age = 1; age < BLEAKHOLD_EMOJI_LIFETIME_MS; age++) {
        Pose cur = PoseAt(age);
        CHECK(cur.live);
        CHECK(cur.scale >= 0.0f && cur.scale <= BLEAKHOLD_EMOJI_POP_SCALE + 1e-5f);
        CHECK(cur.alpha >= 0.0f && cur.alpha <= 1.0f && cur.rise >= 0.0f && cur.rise <= 1.0f);
        CHECK(std::fabs(cur.scale - prev.scale) < 0.025f);
        CHECK(std::fabs(cur.alpha - prev.alpha) < 0.005f && std::fabs(cur.rise - prev.rise) < 0.005f);
        prev = cur;
    }
}

int main() {
    TestConstants();
    TestFromKit();
    TestPose();

    if (s_failures) {
        std::fprintf(stderr, "%d check(s) failed\n", s_failures);
        return 1;
    }

    std::printf("BleakholdEmoji.h: all checks passed\n");
    return 0;
}
