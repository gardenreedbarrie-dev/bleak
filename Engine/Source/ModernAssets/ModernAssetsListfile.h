#ifndef ENGINE_SOURCE_MODERNASSETS_MODERNASSETSLISTFILE_H
#define ENGINE_SOURCE_MODERNASSETS_MODERNASSETSLISTFILE_H

#include <cstdint>
#include <mutex>
#include <string>
#include <vector>

// BLEAKHOLD(modernassets): FileDataID -> path table. Modern models, map objects and terrain name some of
// their files by FileDataID instead of by path; the community listfile ("id;path" per line, as published
// by wow.tools / wowdev) maps them back. The table is loaded on first use from, in order:
//   <client>\listfile.csv, <client>\Data\listfile.csv, listfile.csv inside the client's archives.
class ModernAssetsListfile {
    public:
    static ModernAssetsListfile& Get();

    bool Resolve(uint32_t fileDataId, std::string& outPath);

    private:
    struct Entry {
        uint32_t m_fileDataId;
        uint32_t m_nameOffset;
    };

    void Load();
    bool Parse(const char* data, size_t size);

    std::once_flag m_loadOnce;
    std::vector<Entry> m_entries;
    std::string m_names;
};

#endif
