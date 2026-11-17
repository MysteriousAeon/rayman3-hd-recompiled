cmake_minimum_required(VERSION 3.25)
# LM-2: the Linux r3hd executable from the DIAGNOSTIC, SEH-disabled generated tree (tools/linux/r3hd_diag_tree.py).
#
# It assembles the target exactly as the production generated/rexglue.cmake does (an OBJECT library of the
# generated sources with the r3hd_pch.h precompiled header and the SDK target settings, linked into r3hd with the
# prepared host sources, then rexglue_configure_target with the xenos GPU plugin), but never re-runs codegen: the
# tree arrives fully generated and instrumented from the Windows host, and the production codegen command would
# need the game executable and Windows paths. Clang only (the SDK requires it). Never a production build.
project(r3hd LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(NOT CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  message(FATAL_ERROR "The Linux r3hd build uses Clang, as the ReXGlue SDK requires")
endif()
# Two marked tree kinds: the LM-2 diagnostic tree (no guest SEH) and the LM-A production tree (M4 owners on the
# portable backend, tools/m4_seh_portable.h). Each gets its own banner; anything unmarked is refused.
if(R3HD_TREE AND EXISTS "${R3HD_TREE}/DIAGNOSTIC_SEH_DISABLED.txt")
  set(R3HD_BANNER diag_banner.cpp)
elseif(R3HD_TREE AND EXISTS "${R3HD_TREE}/LMA_PORTABLE_M4.txt")
  set(R3HD_BANNER lma_banner.cpp)
else()
  message(FATAL_ERROR "R3HD_TREE must be a marked tree (DIAGNOSTIC_SEH_DISABLED.txt or LMA_PORTABLE_M4.txt)")
endif()
set(R3HD_REPO "${CMAKE_CURRENT_SOURCE_DIR}/../../..")
if(NOT R3HD_SDK_SOURCE)
  set(R3HD_SDK_SOURCE "${R3HD_REPO}/external/rexglue-sdk")
endif()
find_package(rexglue 0.10.0 CONFIG REQUIRED)

set(R3HD_GEN "${R3HD_TREE}/generated/default")
include("${R3HD_GEN}/sources.cmake")  # GENERATED_SOURCES
# Production REXGLUE_RECOMP_OPTIONS outside Windows with Clang: line tables only (no -fasync-exceptions: no SEH).
# Never -fnon-call-exceptions: with asynchronous thread cancellation it turns a forced unwind into std::terminate (E-372).
set(R3HD_RECOMP_OPTIONS -gline-tables-only)

add_library(r3hd_recomp OBJECT ${GENERATED_SOURCES})
target_include_directories(r3hd_recomp PRIVATE "${R3HD_TREE}" "${R3HD_TREE}/src" "${R3HD_GEN}"
                           "${R3HD_REPO}/tools/linux/compat")
target_link_libraries(r3hd_recomp PRIVATE rex::runtime)
rexglue_apply_target_settings(r3hd_recomp)
target_precompile_headers(r3hd_recomp PRIVATE "${R3HD_GEN}/r3hd_pch.h")
target_compile_options(r3hd_recomp PRIVATE ${R3HD_RECOMP_OPTIONS})

add_executable(r3hd "${R3HD_TREE}/src/main.cpp" "${R3HD_TREE}/src/m2_trace.cpp" ${R3HD_BANNER})
target_include_directories(r3hd PRIVATE "${R3HD_TREE}" "${R3HD_TREE}/src" "${R3HD_GEN}"
                           "${R3HD_REPO}/tools/linux/compat"
                           "${R3HD_SDK_SOURCE}/thirdparty/inja/third_party/include")
target_link_libraries(r3hd PRIVATE r3hd_recomp rex::runtime)
rexglue_configure_target(r3hd GPU_PLUGINS xenos)
