# M40 (E-201): the SDK's FFmpeg (libavutil + libavcodec, exactly the SDK's source lists) and the xmaframes harness,
# all built with AddressSanitizer. FFMPEG_CMAKE is the FFmpeg section cut from the SDK's thirdparty/CMakeLists.txt
# by tools/m40_asan_check.py (sources and defines unchanged; only the directory variable is made absolute).
cmake_minimum_required(VERSION 3.20)
project(m40_asan C)
set(IS_X86_64 TRUE)
set(IS_ARM64 FALSE)
set(M40_SAN "-fsanitize=address -g -O1 -march=x86-64-v2 -fno-omit-frame-pointer")
set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} ${M40_SAN}")
set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} -fsanitize=address")
include(${FFMPEG_CMAKE})
add_executable(xma_fuzz ${CMAKE_CURRENT_SOURCE_DIR}/xma_fuzz.c)
target_link_libraries(xma_fuzz PRIVATE libavcodec libavutil)
