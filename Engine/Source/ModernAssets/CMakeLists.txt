file(GLOB_RECURSE PRIVATE_SOURCES CONFIGURE_DEPENDS "*.cpp")

add_library(ModernAssets STATIC
    ${PRIVATE_SOURCES}
)

# The WarcraftXL sources this calls into use C++20 (std::span).
set_target_properties(ModernAssets PROPERTIES
    CXX_STANDARD 20
    CXX_STANDARD_REQUIRED ON
)

target_include_directories(ModernAssets
    PUBLIC
        ${CMAKE_SOURCE_DIR}
    PRIVATE
        ${CMAKE_SOURCE_DIR}/ThirdParty/WarcraftXL/include
)

target_link_libraries(ModernAssets
    PUBLIC
        BlizzardCore
)
