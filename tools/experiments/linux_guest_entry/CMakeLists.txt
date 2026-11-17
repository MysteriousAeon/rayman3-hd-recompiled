cmake_minimum_required(VERSION 3.24)
# Linux Guest Entry (LGE): opt-in, isolated, never part of the Windows release
# build. Consumes an EXISTING installed SDK; never builds or patches it.
# The selected generated functions come from a PRIVATE directory
# (LGE_GENERATED_DIR: lge_generated.cpp + verbatim r3hd_pch.h) that is never
# part of the repository.
project(linux_guest_entry LANGUAGES C CXX)
find_package(rexglue CONFIG REQUIRED)
if(NOT TARGET rex::runtime)
  message(FATAL_ERROR "An existing matching SDK installation exporting rex::runtime is required")
endif()
if(NOT CMAKE_CXX_COMPILER_ID MATCHES "Clang|GNU")
  message(FATAL_ERROR "Clang or GCC required")
endif()
if(NOT LGE_OPT STREQUAL "0" AND NOT LGE_OPT STREQUAL "2")
  message(FATAL_ERROR "Set LGE_OPT=0 or 2")
endif()
if(NOT LGE_GENERATED_DIR OR NOT EXISTS "${LGE_GENERATED_DIR}/lge_generated.cpp"
   OR NOT EXISTS "${LGE_GENERATED_DIR}/r3hd_pch.h")
  message(FATAL_ERROR "LGE_GENERATED_DIR must hold the private lge_generated.cpp and r3hd_pch.h")
endif()
if(EXISTS "${LGE_GENERATED_DIR}/m2_trace.h")
  message(FATAL_ERROR "The private directory must not shadow the LGE m2_trace.h shim")
endif()
option(LRB_ORDINARY_ONLY "No signal owner or hardware faults (any platform)" OFF)
set(LRB_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../linux_runtime_bootstrap")
set(LGE_STRICT -O${LGE_OPT} -Wall -Wextra -Werror -fno-fast-math -frounding-math)
# Production applies -msse4.1 to generated code on x86-64 (rexglue_apply_target_settings).
if(CMAKE_SYSTEM_PROCESSOR MATCHES "x86_64|AMD64")
  # C++ only: the LRB owner (C) and transport (asm) keep their audited flags.
  list(APPEND LGE_STRICT $<$<COMPILE_LANGUAGE:CXX>:-msse4.1>)
endif()

# The verbatim generated functions: own object library, own include order
# (the LGE m2_trace.h shim, then the private prelude directory).
add_library(lge_generated OBJECT "${LGE_GENERATED_DIR}/lge_generated.cpp")
target_compile_features(lge_generated PRIVATE cxx_std_23)
target_include_directories(lge_generated BEFORE PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}" "${LGE_GENERATED_DIR}")
target_link_libraries(lge_generated PRIVATE rex::runtime)
target_compile_options(lge_generated PRIVATE ${LGE_STRICT})
# GCC rejects the pinned template's attribute placement in DEFINE_REX_FUNC; use
# the same declaration with GCC-accepted placement (see lge_define_rex_func.h).
# Clang keeps the pinned macro unless verification forces the replacement.
if(CMAKE_CXX_COMPILER_ID STREQUAL "GNU")
  set(LGE_PORTABLE_DEFINE_DEFAULT ON)
else()
  set(LGE_PORTABLE_DEFINE_DEFAULT OFF)
endif()
option(LGE_PORTABLE_DEFINE "Force-include lge_define_rex_func.h for the generated object"
       ${LGE_PORTABLE_DEFINE_DEFAULT})
if(LGE_PORTABLE_DEFINE)
  target_compile_options(lge_generated PRIVATE -include "${CMAKE_CURRENT_SOURCE_DIR}/lge_define_rex_func.h")
endif()

add_executable(lge_tests lge_tests.cpp "${LRB_DIR}/lrb_bootstrap.cpp" $<TARGET_OBJECTS:lge_generated>)
target_compile_features(lge_tests PRIVATE cxx_std_23)
target_include_directories(lge_tests PRIVATE "${LRB_DIR}")
target_compile_options(lge_tests PRIVATE ${LGE_STRICT})
target_link_libraries(lge_tests PRIVATE rex::runtime)
if(WIN32)
  target_compile_definitions(lge_tests PRIVATE _CRT_SECURE_NO_WARNINGS)
endif()
if(LRB_ORDINARY_ONLY)
  target_compile_definitions(lge_tests PRIVATE LRB_ORDINARY_ONLY)
else()
  if(NOT CMAKE_SYSTEM_NAME STREQUAL "Linux" OR NOT CMAKE_SYSTEM_PROCESSOR MATCHES "x86_64|AMD64")
    message(FATAL_ERROR "The native LGE owner requires Linux x86-64")
  endif()
  enable_language(ASM)
  # The audited LRB owner and transport, unchanged.
  target_sources(lge_tests PRIVATE "${LRB_DIR}/lrb_owner.c" "${LRB_DIR}/lrb_access.S")
  target_compile_definitions(lge_tests PRIVATE LRB_TEST)
  set_property(TARGET lge_tests PROPERTY C_STANDARD 11)
  target_compile_options(lge_tests PRIVATE -pthread)
  # Eager binding: the owner's terminal path makes its first PLT calls in signal
  # context; with BIND_NOW they no longer enter the lazy resolver there.
  target_link_options(lge_tests PRIVATE -Wl,-z,now -Wl,-z,relro)
  target_link_libraries(lge_tests PRIVATE pthread)
endif()
