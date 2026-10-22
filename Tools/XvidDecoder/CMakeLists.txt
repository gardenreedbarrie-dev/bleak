# BLEAKHOLD(nodll): the x64 movie decoder is linked into the executables, so the client ships no DLL.
add_library(XvidDecoder STATIC
    XvidDecoder.cpp
)

target_include_directories(XvidDecoder
    PRIVATE
        ${CMAKE_SOURCE_DIR}
        ${CMAKE_SOURCE_DIR}/ThirdParty/xvidcore/include
)

# libxvidcore.lib is built against the release C runtime DLL (MSVCRT); Debug executables use MSVCRTD instead.
target_link_libraries(XvidDecoder
    PRIVATE
        ${CMAKE_SOURCE_DIR}/ThirdParty/xvidcore/lib/x64/libxvidcore.lib
    INTERFACE
        $<$<CONFIG:Debug>:-NODEFAULTLIB:MSVCRT>
)
