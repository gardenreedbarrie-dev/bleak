# WarcraftXL modern-asset transforms (GPL-3.0-or-later, see LICENSE and README.md).
#
# An OBJECT library: the host transforms register themselves from static initializers, and a static
# library would let the linker drop those objects because nothing references them by name. Linking the
# objects straight into the executables keeps every registration.

file(GLOB_RECURSE WARCRAFTXL_SOURCES CONFIGURE_DEPENDS
    "${CMAKE_CURRENT_SOURCE_DIR}/shared/*.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/host/*.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/adt/*.cpp"
)

add_library(WarcraftXL OBJECT ${WARCRAFTXL_SOURCES})

set_target_properties(WarcraftXL PROPERTIES
    CXX_STANDARD 20
    CXX_STANDARD_REQUIRED ON
)

# WXL_HOST selects the byte-transform half of the shared sources; their live-engine half is ported into
# Engine/Source/Model2 instead.
target_compile_definitions(WarcraftXL PRIVATE WXL_HOST)

target_include_directories(WarcraftXL
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/include
)
