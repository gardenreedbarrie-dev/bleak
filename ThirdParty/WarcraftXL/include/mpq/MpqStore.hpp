// Bleakhold shim: the archive reader the vendored WarcraftXL host transforms use for sibling files
// (a model's .skel, a helm-offset sidecar). WarcraftXL's host mounts the MPQs with StormLib; inside the
// client the archives are already mounted, so this reads through SFile without running the transforms
// again. Implemented by Engine/Source/ModernAssets/ModernAssets.cpp.

#pragma once

#include <cstdint>
#include <string>
#include <string_view>
#include <vector>

namespace wxl::host::mpq
{
    class MpqStore
    {
        public:
        // The client's archives are always mounted; returns true.
        bool Mount(const std::string& root);

        // Reads the whole file `name` from the mounted archives into `out`. False when it does not exist.
        bool ReadAll(std::string_view name, std::vector<uint8_t>& out);
    };
}
