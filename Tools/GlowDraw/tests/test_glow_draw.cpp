// Tests of the glow pass's rules (Engine/Source/Model2/M2Glow.h, BLEAKHOLD(glow)); run_tests.sh builds and runs them:
//   test_glow_draw <repo root>
// Besides the rules themselves it holds them against the client source they mirror: the section table against
// CCharacterComponent::s_sectionInfoRaw, and the glow's brightness against BleakFx's bloom threshold (a C++ copy of
// bh_bloom_pre_ps.hlsl's SoftThreshold), printing what the bloom keeps of a glowing and a plain pixel.
#include "Engine/Source/Model2/M2Glow.h"
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <limits>
#include <sstream>
#include <string>
#include <vector>

using namespace M2Glow;

namespace {
    int s_failed = 0;
    int s_checks = 0;

    void Check(bool ok, const char* what) {
        s_checks++;

        if (!ok) {
            s_failed++;
            printf("FAIL: %s\n", what);
        }
    }

    bool Near(double a, double b, double tolerance) {
        return fabs(a - b) <= tolerance;
    }

    std::string ReadFile(const std::string& path) {
        std::ifstream file(path, std::ios::binary);
        std::stringstream text;
        text << file.rdbuf();
        return text.str();
    }

    BatchInfo Body() {
        BatchInfo batch;
        batch.textureType = kSkinTextureType;
        batch.textureCount = 1;
        batch.materialLayer = 0;
        batch.shader = 0;
        batch.baseBlend = 0;
        batch.projected = false;
        return batch;
    }

    void TestMaterials() {
        for (uint32_t flags = 0; flags < 0x200; flags++) {
            uint32_t slot = MaterialSlot(static_cast<uint16_t>(flags));
            uint16_t glow = MaterialFlags(slot);
            Check(slot < kMaterialCount, "material slot within the fixed table");
            Check((glow & kMaterialUnlit) && (glow & kMaterialNoDepthWrite), "glow is unlit and writes no depth");
            Check((glow & kKeptMaterialFlags) == (flags & kKeptMaterialFlags), "glow keeps fog, culling, depth test");
            Check(!(glow & ~(kKeptMaterialFlags | kMaterialUnlit | kMaterialNoDepthWrite)), "glow drops other bits");
        }

        bool used[kMaterialCount] = {};

        for (uint32_t slot = 0; slot < kMaterialCount; slot++) {
            used[MaterialSlot(MaterialFlags(slot))] = true;
            Check(MaterialSlot(MaterialFlags(slot)) == slot, "slot round trip");
        }

        for (uint32_t slot = 0; slot < kMaterialCount; slot++) {
            Check(used[slot], "every glow material reachable");
        }

        Check(kBlendMode == 4, "additive blend, as the eye glow (M2Scene.cpp s_blendModes: 4 -> GxBlend_Add)");
        Check(MaterialFlags(MaterialSlot(0)) == 0x11, "a plain skin's glow is the eye glow's material (flags 17)");
    }

    void TestBatches() {
        Check(IsGlowBatch(Body()), "body batch glows");

        BatchInfo batch = Body();
        batch.baseBlend = 1;
        Check(IsGlowBatch(batch), "alpha-keyed skin glows");

        batch = Body();
        batch.textureType = 2;
        Check(!IsGlowBatch(batch), "cape (type 2) does not glow");

        batch = Body();
        batch.textureType = 6;
        Check(!IsGlowBatch(batch), "hair (type 6) does not glow");

        batch = Body();
        batch.textureType = 0;
        Check(!IsGlowBatch(batch), "file textures (eye glow, type 0) do not glow");

        batch = Body();
        batch.textureType = kNoTexture;
        Check(!IsGlowBatch(batch), "batch without texture does not glow");

        batch = Body();
        batch.textureCount = 2;
        Check(!IsGlowBatch(batch), "two-texture batch does not glow");

        batch = Body();
        batch.textureCount = 0;
        Check(!IsGlowBatch(batch), "untextured batch does not glow");

        batch = Body();
        batch.materialLayer = 1;
        Check(!IsGlowBatch(batch), "material layers above the base do not glow");

        batch = Body();
        batch.baseBlend = 2;
        Check(!IsGlowBatch(batch), "alpha-blended skin does not glow");

        batch = Body();
        batch.baseBlend = 4;
        Check(!IsGlowBatch(batch), "additive skin does not glow");

        batch = Body();
        batch.shader = 0x8001;
        Check(!IsGlowBatch(batch), "fixed env combos do not glow");

        batch = Body();
        batch.shader = 0x80;
        Check(!IsGlowBatch(batch), "sphere-mapped first texture does not glow");

        batch = Body();
        batch.shader = 0x10;
        Check(IsGlowBatch(batch), "modulating combiner glows");

        for (uint16_t op = 2; op < 8; op++) {
            batch = Body();
            batch.shader = static_cast<uint16_t>(op << 4);
            Check(!IsGlowBatch(batch), "decal, add, mod2x, fade and other combiners do not glow");
        }

        batch = Body();
        batch.projected = true;
        Check(!IsGlowBatch(batch), "projected batches do not glow");
    }

    // The section table against CCharacterComponent::s_sectionInfoRaw.
    void TestSectionTable(const std::string& root) {
        std::string source = ReadFile(root + "/WoW/Common/ComponentCore/CharacterComponent.cpp");
        size_t at = source.find("CompSectionInfo CCharacterComponent::s_sectionInfoRaw[NUM_COMPONENT_SECTIONS] = {");
        Check(at != std::string::npos, "s_sectionInfoRaw found in CharacterComponent.cpp");

        if (at == std::string::npos) {
            return;
        }

        size_t end = source.find("};", at);
        std::string table = source.substr(at, end - at);
        uint32_t found = 0;
        size_t pos = table.find("{ {");

        while (pos != std::string::npos && found < kSectionCount + 1) {
            int x = 0;
            int y = 0;
            int w = 0;
            int h = 0;

            if (sscanf(table.c_str() + pos, "{ { %d , %d } , { %d , %d } }", &x, &y, &w, &h) == 4 ||
                sscanf(table.c_str() + pos, "{ { %d, %d }, { %d, %d } }", &x, &y, &w, &h) == 4) {
                if (found < kSectionCount) {
                    const SectionRect& rect = kSections[found];
                    bool same = rect.x == x && rect.y == y && rect.width == w && rect.height == h;
                    Check(same, "section matches s_sectionInfoRaw");
                }

                found++;
            }

            pos = table.find("{ {", pos + 3);
        }

        Check(found == kSectionCount, "s_sectionInfoRaw has the ten sections");

        // The sections tile the 512 layout once each (checked on an 8-texel grid: every size is a multiple of 64).
        for (uint32_t y = 4; y < 512; y += 8) {
            for (uint32_t x = 4; x < 512; x += 8) {
                uint32_t hits = 0;

                for (uint32_t i = 0; i < kSectionCount; i++) {
                    const SectionRect& rect = kSections[i];
                    hits += x >= rect.x && x < rect.x + rect.width && y >= rect.y && y < rect.y + rect.height;
                }

                Check(hits == 1, "every texel in exactly one section");
            }
        }
    }

    uint32_t SectionsOf(std::initializer_list<std::pair<float, float>> points) {
        UvBounds bounds;

        for (const auto& point : points) {
            bounds.Add(point.first, point.second);
        }

        return bounds.Sections();
    }

    void TestSections() {
        Check(kAllSections == 0x3FF, "ten section bits");

        for (uint32_t i = 0; i < kSectionCount; i++) {
            const SectionRect& rect = kSections[i];
            float u0 = (rect.x + 2.0f) / 512.0f;
            float v0 = (rect.y + 2.0f) / 512.0f;
            float u1 = (rect.x + rect.width - 2.0f) / 512.0f;
            float v1 = (rect.y + rect.height - 2.0f) / 512.0f;
            Check(SectionsOf({ { u0, v0 }, { u1, v1 } }) == (1u << i), "a batch inside one section touches only it");

            // Coordinates exactly on the section's borders do not reach the neighbours.
            float e0 = rect.x / 512.0f;
            float f0 = rect.y / 512.0f;
            float e1 = (rect.x + rect.width) / 512.0f;
            float f1 = (rect.y + rect.height) / 512.0f;
            Check(SectionsOf({ { e0, f0 }, { e1, f1 } }) == (1u << i), "border coordinates stay in their section");
        }

        Check(SectionsOf({ { 0.0f, 0.0f }, { 1.0f, 1.0f } }) == kAllSections, "whole texture: every section");
        // A body chunk from the upper arm (left column) to the chest (right column), down to 150 texels.
        Check(SectionsOf({ { 0.2f, 0.05f }, { 0.8f, 150.0f / 512.0f } }) == 0x1B, "arm and chest chunk");
        // A face batch: head upper and lower.
        Check(SectionsOf({ { 0.1f, 330.0f / 512.0f }, { 0.4f, 500.0f / 512.0f } }) == 0x300, "face batch");
        Check(SectionsOf({}) == 0, "no coordinates: no sections");
        Check(SectionsOf({ { 0.5f, 0.5f } }) == kAllSections, "a single point on a corner: all (safe side)");
        Check(SectionsOf({ { 0.1f, 0.1f }, { 1.5f, 0.2f } }) == kAllSections, "tiling coordinates: all");
        Check(SectionsOf({ { -0.5f, 0.1f } }) == kAllSections, "negative coordinates: all");
        Check(SectionsOf({ { std::nanf(""), 0.1f } }) == kAllSections, "NaN: all");
        Check(SectionsOf({ { std::numeric_limits<float>::infinity(), 0.1f } }) == kAllSections, "infinity: all");
        Check(SectionsOf({ { -0.001f, 0.01f }, { 0.3f, 0.2f } }) == 0x1, "rounding below 0 within the slack");
        Check(SectionsOf({ { 0.1f, 0.01f }, { 0.3f, 1.001f } }) == 0x307, "rounding above 1 within the slack");
    }

    void TestStrength() {
        Check(Strength(0, 1.0f) == 0.0f, "bleakGlow 0: no glow");
        Check(Strength(1, 1.0f) == 1.0f, "full strength");
        Check(Strength(1, 0.4f) == 0.4f, "strength passes through");
        Check(Strength(1, -2.0f) == 0.0f, "negative strength: 0");
        Check(Strength(1, 7.0f) == 1.0f, "strength above 1: 1 (the alpha ends there)");
        Check(Strength(2, 0.5f) == 0.5f, "any non-zero bleakGlow is on");
        Check(Strength(1, std::nanf("")) == kDefaultStrength, "NaN strength: default");
        Check(Strength(1, std::numeric_limits<float>::infinity()) == kDefaultStrength, "infinite strength: default");

        Check(DistanceFade(0.0f) == 1.0f, "at the camera: full");
        Check(DistanceFade(30.0f * 30.0f) == 1.0f, "30 yards: full");
        Check(DistanceFade(kFadeStartYards * kFadeStartYards) == 1.0f, "fade start: full");
        Check(Near(DistanceFade(52.5f * 52.5f), 0.5, 1e-5), "half way: half");
        Check(DistanceFade(kFadeEndYards * kFadeEndYards) == 0.0f, "fade end: none");
        Check(DistanceFade(1.0e9f) == 0.0f, "far: none");
        Check(DistanceFade(-1.0f) == 0.0f, "negative distance: none");
        Check(DistanceFade(std::nanf("")) == 0.0f, "NaN distance: none");

        float last = 1.0f;

        for (float d = 0.0f; d < 80.0f; d += 0.25f) {
            float fade = DistanceFade(d * d);
            Check(fade <= last + 1e-6f && fade >= 0.0f && fade <= 1.0f, "fade falls with distance, within 0..1");
            last = fade;
        }

        Check(ModelAlpha(0.5f, 10.0f) == 0.5f, "model alpha: strength near the camera");
        Check(ModelAlpha(1.0f, 61.0f * 61.0f) < kMinAlpha, "model alpha: nothing past the fade");
        Check(ModelAlpha(0.0f, 1.0f) < kMinAlpha, "model alpha: nothing when off");
    }

    void TestCalls() {
        Check(CallHoldsTexture(0), "ReplaceTexture holds a texture");

        for (uint32_t type = 1; type <= 14; type++) {
            Check(!CallHoldsTexture(type), "stock calls 1-14 hold no texture");
        }

        Check(CallHoldsTexture(kCallSetGlowTexture), "SetGlowTexture holds a texture");
        Check(CallHoldsTexture(kCallReplaceTextureAtIndex), "ReplaceTextureAtIndex holds a texture");
        Check(CallHoldsTexture(kCallReplaceGeosetTexture), "ReplaceGeosetTexture holds a texture");
        Check(!CallHoldsTexture(0x103) && !CallHoldsTexture(0xFFFFFFFF), "unknown calls hold no texture");
        Check(kCallSetGlowTexture > 14 && kCallReplaceTextureAtIndex > 14 && kCallReplaceGeosetTexture > 14,
            "new calls clear of the stock ones");
    }

    void TestGeosetTextures() {
        // Body (geoset 0) on texture 0, cape (1501) on 1, eyes 1702 on 2 and 1703 on 3; 1703 has two batches.
        std::vector<BatchTexture> items = {
            { 0, 0 }, { 0, 0 }, { 1501, 1 }, { 1702, 2 }, { 1703, 3 }, { 1703, 3 }, { 1703, kNoTexture },
        };
        uint32_t out[8] = {};
        uint32_t n = GeosetOnlyTextures(items.data(), static_cast<uint32_t>(items.size()), 1703, out, 8);
        Check(n == 1 && out[0] == 3, "1703's own texture, once");

        n = GeosetOnlyTextures(items.data(), static_cast<uint32_t>(items.size()), 1700, out, 8);
        Check(n == 0, "a geoset the model lacks: nothing");

        // 1703 also samples the body texture in a second unit: that one is shared and left alone.
        items.push_back({ 1703, 0 });
        n = GeosetOnlyTextures(items.data(), static_cast<uint32_t>(items.size()), 1703, out, 8);
        Check(n == 1 && out[0] == 3, "a texture other geosets use is not swapped");

        // Two own textures, written in order of first use, cut at outMax.
        items.push_back({ 1703, 7 });
        n = GeosetOnlyTextures(items.data(), static_cast<uint32_t>(items.size()), 1703, out, 8);
        Check(n == 2 && out[0] == 3 && out[1] == 7, "two own textures");
        n = GeosetOnlyTextures(items.data(), static_cast<uint32_t>(items.size()), 1703, out, 1);
        Check(n == 1 && out[0] == 3, "outMax respected");
        n = GeosetOnlyTextures(nullptr, 0, 1703, out, 8);
        Check(n == 0, "no batches: nothing");
    }

    // The text between `from` and the next `to` after it in `text`, or "" when either is missing.
    std::string Between(const std::string& text, const std::string& from, const std::string& to) {
        size_t start = text.find(from);

        if (start == std::string::npos) {
            return "";
        }

        size_t end = text.find(to, start + from.size());
        return end == std::string::npos ? "" : text.substr(start, end - start);
    }

    // A copy made by CM2Scene::DuplicateModel (the PlayerModel frames of the character pane, inspect and the dressing
    // room, and portraits) holds its source in m_model30 only until it has loaded: CM2Model::InitializeLoaded lets go
    // of it before the copy is first drawn. So the copy has to take the source's glow there, before it lets go, and
    // the glow the draw reads (GetGlowTexture) is the model's own.
    void TestCopySource(const std::string& root) {
        std::string cpp = ReadFile(root + "/Engine/Source/Model2/M2Model.cpp");
        std::string loaded = Between(cpp, "int32_t CM2Model::InitializeLoaded() {", "this->UpdateLoaded();");
        Check(!loaded.empty(), "CM2Model::InitializeLoaded found in M2Model.cpp");

        size_t source = loaded.find("CM2Model* source = this->m_model30;");
        size_t take = loaded.find("M2Glow::TakeSourceGlow(*this, source");
        size_t release = loaded.find("source->m_refCount-- == 1");
        size_t cleared = loaded.find("this->m_model30 = nullptr;");
        size_t calls = loaded.find("while (this->m_modelCallList)");
        Check(source != std::string::npos && release != std::string::npos && cleared != std::string::npos &&
            calls != std::string::npos, "InitializeLoaded still lets go of the source before the queued calls");
        Check(take != std::string::npos, "InitializeLoaded takes the source's glow (M2Glow::TakeSourceGlow)");
        Check(take != std::string::npos && source < take && take < release && take < cleared,
            "the copy takes the source's glow while it still holds the source");
        Check(release < cleared && cleared < calls,
            "the copy's own queued glow runs after it took the source's, and replaces it");

        std::string header = ReadFile(root + "/Engine/Source/Model2/M2Model.h");
        std::string getter = Between(header, "CTexture* GetGlowTexture(uint32_t* sections) const {", "\n    }\n");
        Check(!getter.empty(), "CM2Model::GetGlowTexture found in M2Model.h");
        Check(getter.find("m_model30") == std::string::npos,
            "GetGlowTexture does not read m_model30 (cleared before a copy is ever drawn)");
        Check(getter.find("return this->m_bleakGlowTexture;") != std::string::npos,
            "GetGlowTexture returns the model's own glow");

        std::string destructor = Between(cpp, "CM2Model::~CM2Model() {", "CM2Model* model30 = this->m_model30;");
        Check(destructor.find("HandleClose(reinterpret_cast<HOBJECT>(this->m_bleakGlowTexture));") !=
            std::string::npos, "the destructor closes the model's glow handle, a copy's included");
    }

    // TakeSourceGlow on stand-ins for CM2Model and its texture handles, in the order CM2Model::InitializeLoaded runs:
    // take the source's glow, let go of the source (m_model30 = nullptr), then run the calls the copy queued while it
    // loaded. FakeSetGlow follows CM2Model::SetGlowTexture (new handle first, then the old one closed).
    struct FakeTexture {
        int refs = 1;
    };

    struct FakeModel {
        FakeTexture* m_bleakGlowTexture = nullptr;
        uint32_t m_bleakGlowSections = 0;
        FakeModel* m_model30 = nullptr;
        FakeTexture* queuedGlow = nullptr; // a SetGlowTexture queued on the copy while it loaded
        uint32_t queuedSections = 0;
        bool queued = false;
    };

    int s_duplicates = 0;

    FakeTexture* FakeDuplicate(FakeTexture* texture) {
        s_duplicates++;

        if (texture) {
            texture->refs++;
        }

        return texture;
    }

    void FakeClose(FakeTexture* texture) {
        if (texture) {
            texture->refs--;
        }
    }

    void FakeSetGlow(FakeModel& model, FakeTexture* texture, uint32_t sections) {
        FakeTexture* previous = model.m_bleakGlowTexture;
        model.m_bleakGlowTexture = texture ? FakeDuplicate(texture) : nullptr;
        model.m_bleakGlowSections = texture ? (sections & kAllSections) : 0;
        FakeClose(previous);
    }

    void FakeQueueGlow(FakeModel& model, FakeTexture* texture, uint32_t sections) {
        model.queuedGlow = texture ? FakeDuplicate(texture) : nullptr;
        model.queuedSections = sections;
        model.queued = true;
    }

    // CM2Scene::DuplicateModel: Initialize holds the source, the shared model is loaded so InitializeLoaded runs.
    void FakeDuplicateAndLoad(FakeModel& copy, FakeModel* source) {
        copy.m_model30 = source;

        if (copy.m_model30) {
            TakeSourceGlow(copy, copy.m_model30, FakeDuplicate);
            copy.m_model30 = nullptr;
        }

        if (copy.queued) {
            FakeSetGlow(copy, copy.queuedGlow, copy.queuedSections);
            FakeClose(copy.queuedGlow);
            copy.queuedGlow = nullptr;
            copy.queued = false;
        }
    }

    void FakeDestroy(FakeModel& model) {
        FakeClose(model.m_bleakGlowTexture);
        model.m_bleakGlowTexture = nullptr;
    }

    void TestCopies() {
        // The component's glow texture, handed to the world model.
        FakeTexture glow;
        FakeModel world;
        FakeSetGlow(world, &glow, 0x18);
        Check(glow.refs == 2, "component and world model hold the glow");

        // Character pane, inspect, portrait: the copy draws the world model's glow once loaded.
        FakeModel pane;
        FakeDuplicateAndLoad(pane, &world);
        Check(pane.m_model30 == nullptr, "a loaded copy no longer holds its source");
        Check(pane.m_bleakGlowTexture == &glow && pane.m_bleakGlowSections == 0x18,
            "a loaded copy draws its source's glow and sections");
        Check(glow.refs == 3, "with a handle of its own");

        // Not tracked after that: the bake drops the world model's glow (DestroyGlowTexture).
        FakeSetGlow(world, nullptr, 0);
        FakeClose(&glow);
        Check(pane.m_bleakGlowTexture == &glow && glow.refs == 1, "the copy keeps the glow it loaded with");
        FakeDestroy(pane);
        Check(glow.refs == 0, "and lets go of it when it is destroyed");

        // A glow queued on the copy itself replaces the source's, which is not leaked.
        FakeTexture own;
        FakeTexture sourceGlow;
        FakeModel source;
        FakeSetGlow(source, &sourceGlow, kAllSections);
        FakeModel dressed;
        FakeQueueGlow(dressed, &own, 0x1);
        FakeDuplicateAndLoad(dressed, &source);
        Check(dressed.m_bleakGlowTexture == &own && dressed.m_bleakGlowSections == 0x1, "the copy's own glow wins");
        Check(sourceGlow.refs == 2 && own.refs == 2, "the source's glow taken and given back, the queued call closed");
        FakeDestroy(dressed);
        Check(own.refs == 1, "the copy's own glow let go with it");

        // A queued SetGlowTexture(nullptr) on the copy: no glow, nothing leaked.
        FakeModel cleared;
        FakeQueueGlow(cleared, nullptr, 0);
        FakeDuplicateAndLoad(cleared, &source);
        Check(!cleared.m_bleakGlowTexture && !cleared.m_bleakGlowSections && sourceGlow.refs == 2,
            "a copy cleared by its own call has no glow");

        // A source without glow (today's data, no `_Glow` files), and a model that is not a copy: nothing, no handle.
        s_duplicates = 0;
        FakeModel plain;
        FakeModel plainCopy;
        FakeDuplicateAndLoad(plainCopy, &plain);
        FakeModel loaded;
        FakeDuplicateAndLoad(loaded, nullptr);
        Check(!plainCopy.m_bleakGlowTexture && !plainCopy.m_bleakGlowSections && !loaded.m_bleakGlowTexture &&
            s_duplicates == 0, "no glow in, no glow out, no handle taken");
        Check(!TakeSourceGlow(loaded, static_cast<const FakeModel*>(nullptr), FakeDuplicate), "no source: false");

        // A copy that already holds a glow keeps it.
        FakeTexture held;
        FakeModel holder;
        FakeSetGlow(holder, &held, 0x2);
        Check(!TakeSourceGlow(holder, &source, FakeDuplicate) && holder.m_bleakGlowTexture == &held &&
            holder.m_bleakGlowSections == 0x2 && sourceGlow.refs == 2, "a glow of the copy's own is kept");

        // A duplicate that fails leaves no sections behind.
        FakeModel failed;
        Check(!TakeSourceGlow(failed, &source, [](FakeTexture*) { return static_cast<FakeTexture*>(nullptr); }) &&
            !failed.m_bleakGlowSections, "a failed duplicate: no glow, no sections");
    }

    // bh_bloom_pre_ps.hlsl, per pixel: the frame is gamma, the threshold works on linear light.
    float ToLinear(float c) {
        return powf(c > 0.0f ? c : 0.0f, 2.2f);
    }

    float BloomKept(float gammaPixel, float threshold, float knee) {
        float c = ToLinear(gammaPixel);
        float brightness = c;
        float kneeWidth = threshold * knee + 1e-4f;
        float soft = brightness - threshold + kneeWidth;
        soft = soft < 0.0f ? 0.0f : (soft > 2.0f * kneeWidth ? 2.0f * kneeWidth : soft);
        soft = soft * soft / (4.0f * kneeWidth);
        float kept = soft > brightness - threshold ? soft : brightness - threshold;
        return c * (kept / (brightness > 1e-4f ? brightness : 1e-4f));
    }

    // Additive blending happens on the gamma back buffer: skin + glow x alpha, saturated.
    float Blend(float skin, float glow, float alpha) {
        float sum = skin + glow * alpha;
        return sum > 1.0f ? 1.0f : sum;
    }

    void TestBloom(const std::string& root) {
        std::string fx = ReadFile(root + "/Engine/Source/BleakFx/BleakFx.cpp");
        float threshold = 0.0f;
        float knee = 0.0f;
        size_t at = fx.find("\"bleakFxBloomThreshold\"");
        Check(at != std::string::npos, "bleakFxBloomThreshold registered in BleakFx.cpp");

        if (at != std::string::npos) {
            size_t quote = fx.find("0x1, \"", at);
            Check(quote != std::string::npos && sscanf(fx.c_str() + quote, "0x1, \"%f\"", &threshold) == 1,
                "bloom threshold default read");
        }

        at = fx.find("SetPsVector(kPsParams, settings.bloomThreshold, ");
        Check(at != std::string::npos && sscanf(fx.c_str() + at, "SetPsVector(kPsParams, settings.bloomThreshold, %ff",
            &knee) == 1, "bloom knee read");
        Check(threshold > 0.0f && threshold <= 1.0f && knee > 0.0f && knee <= 1.0f, "bloom settings sane");
        std::string pre = ReadFile(root + "/Engine/Source/BleakFx/Shaders/bh_bloom_pre_ps.hlsl");
        Check(pre.find("float brightness = max(c.r, max(c.g, c.b));") != std::string::npos,
            "bloom still thresholds the brightest channel (the copy below matches the shader)");

        struct Case {
            const char* what;
            float skin;
            float glow;
            float alpha;
        };

        const Case cases[] = {
            { "day, pale skin, no glow", 0.80f, 0.0f, 1.0f },
            { "day, mid skin, no glow", 0.60f, 0.0f, 1.0f },
            { "night, skin, no glow", 0.10f, 0.0f, 1.0f },
            { "night, glow peak 255, strength 1", 0.10f, 1.0f, 1.0f },
            { "day, mid skin, glow peak 255, strength 1", 0.60f, 1.0f, 1.0f },
            { "night, glow peak 230, strength 1", 0.10f, 230.0f / 255.0f, 1.0f },
            { "night, glow peak 255, strength 0.75", 0.10f, 1.0f, 0.75f },
            { "night, glow peak 255, strength 0.5", 0.10f, 1.0f, 0.5f },
        };

        printf("bloom (threshold %.2f, knee %.2f): share of a pixel's brightest channel the bloom keeps\n", threshold,
            knee);

        for (const Case& c : cases) {
            float pixel = Blend(c.skin, c.glow, c.alpha);
            printf("  %-44s frame %.3f  kept %.4f\n", c.what, pixel, BloomKept(pixel, threshold, knee));
        }

        float plainDay = BloomKept(Blend(0.80f, 0.0f, 1.0f), threshold, knee);
        float glowNight = BloomKept(Blend(0.10f, 1.0f, 1.0f), threshold, knee);
        float glowDay = BloomKept(Blend(0.60f, 1.0f, 1.0f), threshold, knee);
        Check(glowNight > 0.2f, "a full-strength glow blooms at night");
        Check(glowDay > 0.2f, "a full-strength glow blooms by day");
        Check(glowNight > 5.0f * plainDay, "the glow blooms several times more than pale skin in daylight");
        Check(BloomKept(Blend(0.10f, 0.0f, 1.0f), threshold, knee) == 0.0f, "dark skin alone does not bloom");
    }
}

int main(int argc, char** argv) {
    if (argc < 2) {
        printf("usage: test_glow_draw <repo root>\n");
        return 2;
    }

    std::string root = argv[1];
    TestMaterials();
    TestBatches();
    TestSectionTable(root);
    TestSections();
    TestStrength();
    TestCalls();
    TestGeosetTextures();
    TestCopies();
    TestCopySource(root);
    TestBloom(root);

    printf("%d checks, %d failed\n", s_checks, s_failed);
    return s_failed ? 1 : 0;
}
