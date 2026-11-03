// Bleakhold shim: the logging surface the vendored WarcraftXL sources call (wxl-core's core/Logger.hpp).
// The functions are implemented by Engine/Source/ModernAssets/ModernAssetsLog.cpp, which writes to
// Logs\ModernAssets.log next to the client.

#pragma once

namespace wxl::log
{
    enum class Level
    {
        Debug,
        Info,
        Warn,
        Error,
    };

    bool Enabled(Level level);
}

namespace wxl::core::log
{
    void Write(::wxl::log::Level level, const char* format, ...);
    void Printf(const char* format, ...);
    void Info(const char* format, ...);
}

#define WLOG_DEBUG(...) \
    do { \
        if (::wxl::log::Enabled(::wxl::log::Level::Debug)) { \
            ::wxl::core::log::Write(::wxl::log::Level::Debug, __VA_ARGS__); \
        } \
    } while (0)

#define WLOG_INFO(...) ::wxl::core::log::Write(::wxl::log::Level::Info, __VA_ARGS__)
#define WLOG_WARN(...) ::wxl::core::log::Write(::wxl::log::Level::Warn, __VA_ARGS__)
#define WLOG_ERROR(...) ::wxl::core::log::Write(::wxl::log::Level::Error, __VA_ARGS__)
