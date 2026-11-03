// BLEAKHOLD(modernassets): the log the WarcraftXL transforms write to (ThirdParty/WarcraftXL/include/core/Logger.hpp).
// Lines go to Logs\ModernAssets.log under the client directory. Debug lines are written only when the
// WXL_VERBOSE_ASSET_LOGS (or WXL_ASSET_LOGS) environment variable is set, as in WarcraftXL.

#include "Host.hpp"
#include "core/Logger.hpp"

#include "ThirdParty/WarcraftXL/shared/common/Env.hpp"

#include <cstdarg>
#include <cstdio>
#include <ctime>
#include <filesystem>
#include <mutex>
#include <string>

namespace {

std::mutex& LogMutex() {
    static std::mutex mutex;
    return mutex;
}

FILE* LogFile() {
    static FILE* s_file = nullptr;
    static bool s_opened = false;

    if (!s_opened) {
        s_opened = true;

        std::string root = wxl::host::ClientRoot();
        std::filesystem::path directory = root.empty() ? std::filesystem::path("Logs") : std::filesystem::path(root) / "Logs";

        std::error_code error;
        std::filesystem::create_directories(directory, error);

        s_file = fopen((directory / "ModernAssets.log").string().c_str(), "w");
    }

    return s_file;
}

const char* LevelName(wxl::log::Level level) {
    switch (level) {
        case wxl::log::Level::Debug:
            return "DEBUG";
        case wxl::log::Level::Info:
            return "INFO";
        case wxl::log::Level::Warn:
            return "WARN";
        case wxl::log::Level::Error:
            return "ERROR";
    }

    return "INFO";
}

void WriteLine(wxl::log::Level level, const char* format, va_list args) {
    char message[1024];
    vsnprintf(message, sizeof(message), format, args);

    time_t now = time(nullptr);
    struct tm local;
#if defined(_WIN32)
    localtime_s(&local, &now);
#else
    localtime_r(&now, &local);
#endif

    std::lock_guard<std::mutex> lock(LogMutex());
    FILE* file = LogFile();

    if (!file) {
        return;
    }

    fprintf(file, "%02d:%02d:%02d [%s] %s\n", local.tm_hour, local.tm_min, local.tm_sec, LevelName(level), message);
    fflush(file);
}

}

namespace wxl::log {

bool Enabled(Level level) {
    return level != Level::Debug || wxl::modern::assets::common::env::VerboseAssetLogs();
}

}

namespace wxl::core::log {

void Write(::wxl::log::Level level, const char* format, ...) {
    if (!::wxl::log::Enabled(level)) {
        return;
    }

    va_list args;
    va_start(args, format);
    WriteLine(level, format, args);
    va_end(args);
}

void Printf(const char* format, ...) {
    va_list args;
    va_start(args, format);
    WriteLine(::wxl::log::Level::Info, format, args);
    va_end(args);
}

void Info(const char* format, ...) {
    va_list args;
    va_start(args, format);
    WriteLine(::wxl::log::Level::Info, format, args);
    va_end(args);
}

}
