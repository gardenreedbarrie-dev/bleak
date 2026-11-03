// BLEAKHOLD(modernassets): runs the WarcraftXL asset transforms (ThirdParty/WarcraftXL) on the files the
// client opens, and implements the host services those transforms call.
//
// Copyright (C) 2026 WarcraftXL (transform code), Bleakhold (client integration)
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with this program. If not, see <https://www.gnu.org/licenses/>.

#include "Engine/Source/ModernAssets/ModernAssets.h"
#include "Engine/Source/ModernAssets/ModernAssetsListfile.h"
#include "Engine/Source/BlizzardCore/SFile2-Core.h"
#include "Engine/Source/BlizzardCore/Source/System/Memory/MemoryStorm.h"

#include "Host.hpp"
#include "core/Logger.hpp"
#include "mpq/MpqStore.hpp"
#include "structure/m2/M2Format.hpp"

#include "ThirdParty/WarcraftXL/adt/AdtMerge.hpp"
#include "ThirdParty/WarcraftXL/adt/AdtTexScale.hpp"
#include "ThirdParty/WarcraftXL/adt/WdlFixup.hpp"
#include "ThirdParty/WarcraftXL/adt/WdtFixup.hpp"
#include "ThirdParty/WarcraftXL/shared/common/Text.hpp"
#include "ThirdParty/WarcraftXL/shared/models/m2/Contract.hpp"
#include "ThirdParty/WarcraftXL/shared/models/m2/Textures.hpp"

#include <algorithm>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <set>
#include <span>
#include <string>
#include <string_view>
#include <vector>

namespace wxl::modern::assets::textures::blp {

// Defined in ThirdParty/WarcraftXL/host/textures/blp/BlpHost.cpp.
bool MayTransformBlp(std::string_view name, std::span<const uint8_t> header);

}

namespace {

namespace text = wxl::modern::assets::common::text;
namespace fmt = wxl::structure::m2;

enum ASSET_KIND {
    ASSET_NONE,
    ASSET_M2,
    ASSET_ANIM,
    ASSET_BLP,
    ASSET_WMO,
    ASSET_ADT,
    ASSET_WDT,
    ASSET_WDL,
    NUM_ASSET_KINDS,
};

// Bytes read to decide whether a file can need converting: the BLP2 header is 0x94 bytes, every other
// check needs less.
const uint32_t s_headerPeekSize = 0x94;

// Opens made while this is nonzero are served as they are. The transforms read sibling files (a model's
// .skel, a tile's _tex0/_obj0) through SFile, and those reads must see the raw bytes.
thread_local int32_t s_suppressDepth = 0;

class SuppressTransforms {
    public:
    SuppressTransforms() {
        s_suppressDepth++;
    }

    ~SuppressTransforms() {
        s_suppressDepth--;
    }
};

std::mutex& TransformMutex() {
    static std::mutex mutex;
    return mutex;
}

wxl::host::TransformFn& TransformSlot(ASSET_KIND kind) {
    static wxl::host::TransformFn s_transforms[NUM_ASSET_KINDS] = {};
    return s_transforms[kind];
}

wxl::host::TransformFn GetTransform(ASSET_KIND kind) {
    std::lock_guard<std::mutex> lock(TransformMutex());
    return TransformSlot(kind);
}

ASSET_KIND KindForName(std::string_view name) {
    if (text::EndsWithCI(name, ".m2")) {
        return ASSET_M2;
    }

    if (text::EndsWithCI(name, ".anim")) {
        return ASSET_ANIM;
    }

    if (text::EndsWithCI(name, ".blp")) {
        return ASSET_BLP;
    }

    if (text::EndsWithCI(name, ".wmo")) {
        return ASSET_WMO;
    }

    if (text::EndsWithCI(name, ".adt")) {
        return ASSET_ADT;
    }

    if (text::EndsWithCI(name, ".wdt")) {
        return ASSET_WDT;
    }

    if (text::EndsWithCI(name, ".wdl")) {
        return ASSET_WDL;
    }

    return ASSET_NONE;
}

uint32_t ReadU32(const uint8_t* data) {
    uint32_t value;
    memcpy(&value, data, sizeof(value));
    return value;
}

// Reads the whole archive file `name` with the transforms suspended.
bool ReadRawFile(const std::string& name, std::vector<uint8_t>& out) {
    SuppressTransforms suppress;

    SFileImpl* file;

    if (!SFile::OpenEx(nullptr, name.c_str(), 0, &file)) {
        return false;
    }

    uint32_t sizeHigh = 0;
    uint32_t size = SFileGetFileSize(file, &sizeHigh);
    bool ok = sizeHigh == 0;

    if (ok) {
        out.resize(size);
        uint32_t read = 0;
        ok = !size || (SFileReadFile(file, out.data(), size, &read, nullptr, 0) && read == size);
    }

    SFileCloseFile(file);

    if (!ok) {
        out.clear();
    }

    return ok;
}

bool FileExistsRaw(const std::string& name) {
    return SFile::FileExists(name.c_str()) != 0;
}

void RewindFile(SFileImpl* file) {
    if (file->m_type == SFILE_MEMORY) {
        file->m_position = 0;
    } else {
        int32_t high = 0;
        SFile::SetFilePointer(file, 0, &high, 0);
    }
}

// Reads up to `count` bytes from the start of a just-opened file, then rewinds it.
uint32_t PeekFile(SFileImpl* file, uint32_t fileSize, uint8_t* buffer, uint32_t count) {
    count = std::min(count, fileSize);

    if (!count) {
        return 0;
    }

    uint32_t read = 0;

    if (file->m_type == SFILE_MEMORY) {
        read = std::min(count, file->m_size);
        memcpy(buffer, file->m_data, read);
    } else if (!SFileReadFile(file, buffer, count, &read, nullptr, 0)) {
        read = 0;
    }

    RewindFile(file);

    return read;
}

bool ReadWholeFile(SFileImpl* file, uint32_t fileSize, std::vector<uint8_t>& out) {
    out.resize(fileSize);

    if (file->m_type == SFILE_MEMORY) {
        if (file->m_size != fileSize || !file->m_data) {
            return false;
        }

        memcpy(out.data(), file->m_data, fileSize);
        return true;
    }

    uint32_t read = 0;
    bool ok = SFileReadFile(file, out.data(), fileSize, &read, nullptr, 0) && read == fileSize;
    RewindFile(file);

    return ok;
}

// Replaces the file's contents with `bytes`: from here on the handle serves them from memory. The stream or
// archive handle the file was opened with stays attached and is closed with the file.
bool ServeFromMemory(SFileImpl* file, const std::vector<uint8_t>& bytes) {
    uint32_t size = static_cast<uint32_t>(bytes.size());
    uint8_t* data = static_cast<uint8_t*>(Blizzard::Memory::Allocate(size ? size : 1, 0, __FILE__, __LINE__));

    if (!data) {
        return false;
    }

    if (size) {
        memcpy(data, bytes.data(), size);
    }

    if (file->m_data) {
        Blizzard::Memory::Free(file->m_data);
    }

    file->m_data = data;
    file->m_size = size;
    file->m_position = 0;
    file->m_type = SFILE_MEMORY;

    return true;
}

// Answers from the first bytes of a file whether its transform could change it, so files that are already
// in the 3.3.5a format are never read twice.
bool MayTransform(ASSET_KIND kind, std::string_view name, const uint8_t* header, uint32_t size) {
    switch (kind) {
        case ASSET_M2: {
            if (size < 8) {
                return false;
            }

            uint32_t magic = ReadU32(header);
            uint32_t version = ReadU32(header + 4);

            return magic == fmt::kMagicMD21 || (magic == fmt::kMagicMD20 && version >= wxl::modern::assets::m2::kSourceVersionMin && version <= wxl::modern::assets::m2::kSourceVersionMax);
        }

        case ASSET_ANIM: {
            return size >= 8 && ReadU32(header) == fmt::kMagicAFM2;
        }

        case ASSET_BLP: {
            return wxl::modern::assets::textures::blp::MayTransformBlp(name, std::span<const uint8_t>(header, size));
        }

        default: {
            return true;
        }
    }
}

// The base name of a terrain file: "World\Maps\X\X_32_48.adt" -> "World\Maps\X\X_32_48".
std::string StripExtension(std::string_view name) {
    size_t dot = name.rfind('.');
    return std::string(name.substr(0, dot == std::string_view::npos ? name.size() : dot));
}

// Sibling tiles carry their part of a split tile; only the root tile is merged and served.
bool IsSplitTileSibling(std::string_view name) {
    return text::EndsWithCI(name, "_tex0.adt") || text::EndsWithCI(name, "_tex1.adt") || text::EndsWithCI(name, "_obj0.adt") || text::EndsWithCI(name, "_obj1.adt") || text::EndsWithCI(name, "_lod.adt");
}

bool HasSplitSiblings(std::string_view name) {
    if (IsSplitTileSibling(name)) {
        return false;
    }

    std::string base = StripExtension(name);
    return FileExistsRaw(base + "_tex0.adt") || FileExistsRaw(base + "_obj0.adt");
}

bool ResolveAdtFdid(void* user, uint32_t fileDataId, std::string& outPath) {
    (void)user;

    if (!wxl::host::ResolveFdid(fileDataId, outPath)) {
        return false;
    }

    if (text::EndsWithCI(outPath, ".blp")) {
        wxl::host::MarkModernTexture(outPath);
    }

    return true;
}

wxl::modern::adt::Options AdtOptions() {
    // The 3.3.5a terrain has neither hi-res holes, more than four layers nor height blending, so the merge
    // folds or drops them. BLEAKHOLD(terraintiling): the per-texture UV scale table is kept; the terrain
    // draw reads it from the tile (WoW/Source/WorldClient/MapTerrainTiling.cpp).
    wxl::modern::adt::Options options;
    options.highResHoles = false;
    options.packExtraTextureLayers = false;
    options.uvScaleTable = true;
    options.heightBlendTable = false;
    return options;
}

bool TransformAdt(std::string_view name, std::span<const uint8_t> raw, std::vector<uint8_t>& out) {
    if (IsSplitTileSibling(name)) {
        return false;
    }

    std::string base = StripExtension(name);
    std::vector<uint8_t> tex0;
    std::vector<uint8_t> obj0;
    bool hasTex = ReadRawFile(base + "_tex0.adt", tex0);
    bool hasObj = ReadRawFile(base + "_obj0.adt", obj0);

    if (!hasTex && !hasObj) {
        return false;
    }

    static std::once_flag s_configured;
    std::call_once(s_configured, [] {
        wxl::modern::adt::Configure(AdtOptions());
    });

    wxl::modern::adt::ResolveCtx resolve { &ResolveAdtFdid, nullptr };
    return wxl::modern::adt::MergeSplitAdt(raw, tex0, obj0, out, name, resolve);
}

bool TransformWdt(std::string_view name, std::span<const uint8_t> raw, std::vector<uint8_t>& out) {
    // Merged tiles carry 4-bit alpha maps, so a map whose tiles are split loses the map-wide 8-bit alpha flag.
    bool clearBigAlpha = false;
    uint32_t x;
    uint32_t y;

    if (wxl::modern::adt::FirstPresentTile(raw, x, y)) {
        std::string base = StripExtension(name);
        char tile[64];

        snprintf(tile, sizeof(tile), "_%u_%u_tex0.adt", x, y);
        clearBigAlpha = FileExistsRaw(base + tile);

        if (!clearBigAlpha) {
            snprintf(tile, sizeof(tile), "_%u_%u_tex0.adt", y, x);
            clearBigAlpha = FileExistsRaw(base + tile);
        }
    }

    return wxl::modern::adt::FixWdt(raw, clearBigAlpha, out);
}

bool TransformWdl(std::string_view name, std::span<const uint8_t> raw, std::vector<uint8_t>& out) {
    (void)name;
    return wxl::modern::adt::FixWdl(raw, out);
}

// Runs the transform for `kind` on the bytes of the file called `name`.
bool RunTransform(ASSET_KIND kind, std::string_view name, const std::vector<uint8_t>& raw, std::vector<uint8_t>& out) {
    std::span<const uint8_t> bytes(raw.data(), raw.size());

    switch (kind) {
        case ASSET_ADT: {
            return TransformAdt(name, bytes, out);
        }

        case ASSET_WDT: {
            return TransformWdt(name, bytes, out);
        }

        case ASSET_WDL: {
            return TransformWdl(name, bytes, out);
        }

        default: {
            break;
        }
    }

    wxl::host::TransformFn transform = GetTransform(kind);

    if (!transform || !transform(name, bytes, out)) {
        return false;
    }

    // Some modern actor and item models carry their skin texture as WEAPON_BLADE; WarcraftXL rewrites it on
    // the converted image before the parse, so it is done here, on the bytes the model is loaded from.
    if (kind == ASSET_M2 && wxl::modern::assets::m2::textures::AllowsWeaponBladeRemap(name) && out.size() >= sizeof(fmt::M2Header)) {
        auto* header = reinterpret_cast<fmt::M2Header*>(out.data());
        auto fixed = wxl::modern::assets::m2::textures::FixWeaponBladeTextureTypes(header, static_cast<uint32_t>(out.size()));

        if (fixed.Total()) {
            WLOG_INFO("modern-assets: %.*s fixed WEAPON_BLADE textures objectSkin=%u hardcoded=%u", static_cast<int>(name.size()), name.data(), fixed.toObjectSkin, fixed.toHardcoded);
        }
    }

    return true;
}

std::mutex& ModernTextureMutex() {
    static std::mutex mutex;
    return mutex;
}

std::set<std::string>& ModernTextures() {
    static std::set<std::string> textures;
    return textures;
}

std::string NormalizeTextureName(std::string_view name) {
    std::string normalized = text::LowerSlashed(name);
    return normalized;
}

}

void ModernAssetsFilterOpenedFile(const char* name, SFileImpl* file) {
    if (!name || !file || s_suppressDepth) {
        return;
    }

    std::string_view fileName(name);
    ASSET_KIND kind = KindForName(fileName);

    if (kind == ASSET_NONE) {
        return;
    }

    // A tile without split siblings is a 3.3.5a tile: decided by name alone, without reading it.
    if (kind == ASSET_ADT && !HasSplitSiblings(fileName)) {
        return;
    }

    uint32_t sizeHigh = 0;
    uint32_t fileSize = SFileGetFileSize(file, &sizeHigh);

    if (sizeHigh || !fileSize) {
        return;
    }

    uint8_t header[s_headerPeekSize];
    uint32_t headerSize = PeekFile(file, fileSize, header, sizeof(header));

    if (!MayTransform(kind, fileName, header, headerSize)) {
        return;
    }

    std::vector<uint8_t> raw;

    if (!ReadWholeFile(file, fileSize, raw)) {
        WLOG_WARN("modern-assets: could not read %s", name);
        return;
    }

    std::vector<uint8_t> converted;
    bool transformed;

    {
        SuppressTransforms suppress;
        transformed = RunTransform(kind, fileName, raw, converted);
    }

    if (!transformed) {
        return;
    }

    if (!ServeFromMemory(file, converted)) {
        WLOG_WARN("modern-assets: out of memory serving %s (%zu bytes)", name, converted.size());
        return;
    }

    WLOG_DEBUG("modern-assets: %s converted (%u -> %zu bytes)", name, fileSize, converted.size());
}

bool ModernAssetsIsModernTexture(const char* name) {
    return name && wxl::host::IsModernTexture(name);
}

void ModernAssetsForEachTileTiling(const void* tile, uint32_t size, void (*fn)(void* user, const char* texture, uint32_t exponent), void* user) {
    if (!tile || !fn) {
        return;
    }

    const uint8_t* bytes = static_cast<const uint8_t*>(tile);
    std::vector<wxl::modern::adt::TexScaleEntry> scales;

    // The merge appends the table after the chunks the client reads, so walk the top-level chunks to it.
    for (size_t offset = 0; offset + 8 <= size; ) {
        uint32_t magic = ReadU32(bytes + offset);
        uint32_t chunkSize = ReadU32(bytes + offset + 4);

        if (chunkSize > size - offset - 8) {
            break;
        }

        if (magic == wxl::modern::adt::kATSC && wxl::modern::adt::ParseTexScales(bytes + offset + 8, chunkSize, scales)) {
            for (const auto& scale : scales) {
                fn(user, scale.name.c_str(), scale.exponent);
            }
        }

        offset += 8 + size_t(chunkSize);
    }
}

namespace wxl::host {

void RegisterTransform(const char* id, TransformFn fn) {
    ASSET_KIND kind = ASSET_NONE;

    if (!strcmp(id, "modern-m2")) {
        kind = ASSET_M2;
    } else if (!strcmp(id, "modern-anim")) {
        kind = ASSET_ANIM;
    } else if (!strcmp(id, "modern-blp")) {
        kind = ASSET_BLP;
    } else if (!strcmp(id, "modern-wmo")) {
        kind = ASSET_WMO;
    }

    if (kind == ASSET_NONE) {
        return;
    }

    std::lock_guard<std::mutex> lock(TransformMutex());
    TransformSlot(kind) = fn;
}

std::string ClientRoot() {
    char path[260];
    SFile::GetBasePath(path, sizeof(path));

    std::string root(path);

    while (!root.empty() && (root.back() == '\\' || root.back() == '/')) {
        root.pop_back();
    }

    return root;
}

bool ResolveFdid(uint32_t fileDataId, std::string& outPath) {
    return ModernAssetsListfile::Get().Resolve(fileDataId, outPath);
}

void MarkModernTexture(const std::string& path) {
    std::string name = NormalizeTextureName(path);
    std::lock_guard<std::mutex> lock(ModernTextureMutex());
    ModernTextures().insert(std::move(name));
}

bool IsModernTexture(std::string_view name) {
    std::string normalized = NormalizeTextureName(name);
    std::lock_guard<std::mutex> lock(ModernTextureMutex());
    return ModernTextures().count(normalized) != 0;
}

namespace mpq {

bool MpqStore::Mount(const std::string& root) {
    (void)root;
    return true;
}

bool MpqStore::ReadAll(std::string_view name, std::vector<uint8_t>& out) {
    return ReadRawFile(std::string(name), out);
}

}

}
