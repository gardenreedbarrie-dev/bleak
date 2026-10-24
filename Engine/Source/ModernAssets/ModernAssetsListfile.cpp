#include "Engine/Source/ModernAssets/ModernAssetsListfile.h"
#include "Engine/Source/BlizzardCore/SFile2-Core.h"

#include "Host.hpp"
#include "core/Logger.hpp"

#include <algorithm>
#include <cstring>
#include <cstdio>

namespace {

bool ReadLooseFile(const std::string& path, std::vector<char>& out) {
    FILE* file = fopen(path.c_str(), "rb");

    if (!file) {
        return false;
    }

    bool ok = fseek(file, 0, SEEK_END) == 0;
    long size = ok ? ftell(file) : -1;
    ok = ok && size > 0 && fseek(file, 0, SEEK_SET) == 0;

    if (ok) {
        out.resize(static_cast<size_t>(size));
        ok = fread(out.data(), 1, out.size(), file) == out.size();
    }

    fclose(file);

    return ok;
}

bool ReadArchiveFile(const char* name, std::vector<char>& out) {
    SFileImpl* file;

    if (!SFile::OpenEx(nullptr, name, 0, &file)) {
        return false;
    }

    uint32_t sizeHigh = 0;
    uint32_t size = SFileGetFileSize(file, &sizeHigh);
    bool ok = sizeHigh == 0 && size != 0;

    if (ok) {
        out.resize(size);
        uint32_t read = 0;
        ok = SFileReadFile(file, out.data(), size, &read, nullptr, 0) && read == size;
    }

    SFileCloseFile(file);

    return ok;
}

}

ModernAssetsListfile& ModernAssetsListfile::Get() {
    static ModernAssetsListfile s_listfile;
    return s_listfile;
}

bool ModernAssetsListfile::Resolve(uint32_t fileDataId, std::string& outPath) {
    std::call_once(this->m_loadOnce, [this] {
        this->Load();
    });

    auto it = std::lower_bound(this->m_entries.begin(), this->m_entries.end(), fileDataId, [](const Entry& entry, uint32_t id) {
        return entry.m_fileDataId < id;
    });

    if (it == this->m_entries.end() || it->m_fileDataId != fileDataId) {
        return false;
    }

    outPath.assign(this->m_names.c_str() + it->m_nameOffset);

    return true;
}

void ModernAssetsListfile::Load() {
    std::string root = wxl::host::ClientRoot();
    std::string prefix = root.empty() ? std::string() : root + "\\";

    std::vector<char> data;
    const char* source = nullptr;
    std::string loosePath;

    if (ReadLooseFile(loosePath = prefix + "listfile.csv", data)) {
        source = loosePath.c_str();
    } else if (ReadLooseFile(loosePath = prefix + "Data\\listfile.csv", data)) {
        source = loosePath.c_str();
    } else if (ReadArchiveFile("listfile.csv", data)) {
        source = "listfile.csv (archives)";
    }

    if (!source) {
        WLOG_WARN("modern-assets: no listfile.csv found; assets that name files by FileDataID will use placeholders");
        return;
    }

    if (!this->Parse(data.data(), data.size())) {
        WLOG_WARN("modern-assets: %s holds no 'id;path' entries", source);
        return;
    }

    WLOG_INFO("modern-assets: loaded %zu FileDataIDs from %s", this->m_entries.size(), source);
}

bool ModernAssetsListfile::Parse(const char* data, size_t size) {
    // A listfile re-saved by a Windows editor can start with a UTF-8 byte order mark.
    if (size >= 3 && memcmp(data, "\xEF\xBB\xBF", 3) == 0) {
        data += 3;
        size -= 3;
    }

    const char* end = data + size;

    for (const char* line = data; line < end; ) {
        const char* lineEnd = std::find(line, end, '\n');
        const char* separator = std::find(line, lineEnd, ';');

        uint32_t fileDataId = 0;
        bool digits = separator != line;

        for (const char* c = line; c < separator; c++) {
            if (*c < '0' || *c > '9') {
                digits = false;
                break;
            }

            fileDataId = fileDataId * 10 + static_cast<uint32_t>(*c - '0');
        }

        const char* name = separator + 1;
        const char* nameEnd = lineEnd;

        while (nameEnd > name && (nameEnd[-1] == '\r' || nameEnd[-1] == ' ')) {
            nameEnd--;
        }

        if (digits && separator < lineEnd && nameEnd > name && this->m_names.size() < 0xFFFFFFFF) {
            Entry entry;
            entry.m_fileDataId = fileDataId;
            entry.m_nameOffset = static_cast<uint32_t>(this->m_names.size());
            this->m_entries.push_back(entry);

            // The listfile spells paths the modern way (lowercase, forward slashes); archive paths use
            // backslashes. Case does not matter to the archive lookup.
            for (const char* c = name; c < nameEnd; c++) {
                this->m_names.push_back(*c == '/' ? '\\' : *c);
            }

            this->m_names.push_back('\0');
        }

        line = lineEnd < end ? lineEnd + 1 : end;
    }

    std::stable_sort(this->m_entries.begin(), this->m_entries.end(), [](const Entry& a, const Entry& b) {
        return a.m_fileDataId < b.m_fileDataId;
    });

    this->m_entries.shrink_to_fit();
    this->m_names.shrink_to_fit();

    return !this->m_entries.empty();
}
