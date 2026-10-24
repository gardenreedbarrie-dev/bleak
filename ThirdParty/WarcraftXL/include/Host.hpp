// Bleakhold shim: the host services the vendored WarcraftXL host transforms call (WarcraftXL's Host.hpp).
// WarcraftXL runs these transforms in a separate asset-host process; here they run inside the client, on
// the bytes SFile::OpenEx has just opened. Implemented by Engine/Source/ModernAssets/ModernAssets.cpp.

#pragma once

#include <cstdint>
#include <span>
#include <string>
#include <string_view>
#include <vector>

namespace wxl::host
{
    // Reshapes `raw` (the bytes of the file called `name`) into `out`. Returns false to serve the file unchanged.
    using TransformFn = bool (*)(std::string_view name, std::span<const uint8_t> raw, std::vector<uint8_t>& out);

    // Registers a transform under one of the WarcraftXL module ids ("modern-m2", "modern-anim", "modern-blp",
    // "modern-wmo"). The id selects the file extension the transform is offered.
    void RegisterTransform(const char* id, TransformFn fn);

    // The client install directory (where Wow.exe and the Data folder live), without a trailing separator.
    std::string ClientRoot();

    // Resolves a FileDataID to an archive path through listfile.csv. False when the id is unknown.
    bool ResolveFdid(uint32_t fileDataId, std::string& outPath);

    // Records that a modern model or map object references this texture.
    void MarkModernTexture(const std::string& path);

    // True when MarkModernTexture saw this texture name.
    bool IsModernTexture(std::string_view name);
}
