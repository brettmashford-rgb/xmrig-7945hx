# Included after XMRig's project() by CMAKE_PROJECT_xmrig_INCLUDE.
# Alpine fortify's always_inline snprintf wrapper fails during GCC LTO in fmt.
# Keep fortify enabled and compile only fmt as a conventional object.
set_source_files_properties(
    "${CMAKE_CURRENT_SOURCE_DIR}/src/3rdparty/fmt/format.cc"
    PROPERTIES COMPILE_FLAGS "-fno-lto"
)
