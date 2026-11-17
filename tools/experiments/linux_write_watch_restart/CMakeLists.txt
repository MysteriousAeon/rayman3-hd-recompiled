cmake_minimum_required(VERSION 3.24)
# Linux Write-Watch Restart (LWR): opt-in, isolated, never part of the Windows
# release build. Consumes an EXISTING installed SDK; never builds or patches it.
# The selected generated functions come from the PRIVATE LGE extract
# (LGE_GENERATED_DIR: lge_generated.cpp + verbatim r3hd_pch.h), never from Git.
project(linux_write_watch_restart LANGUAGES C CXX)
find_package(rexglue CONFIG REQUIRED)
if(NOT TARGET rex::runtime)
  message(FATAL_ERROR "An existing matching SDK installation exporting rex::runtime is required")
endif()
if(NOT CMAKE_CXX_COMPILER_ID MATCHES "Clang|GNU")
  message(FATAL_ERROR "Clang or GCC required")
endif()
if(NOT LWR_OPT STREQUAL "0" AND NOT LWR_OPT STREQUAL "2")
  message(FATAL_ERROR "Set LWR_OPT=0 or 2")
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
set(LGE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../linux_guest_entry")
# Exactly the LGE flags, so the generated object is the audited LGE object.
set(LWR_STRICT -O${LWR_OPT} -Wall -Wextra -Werror -fno-fast-math -frounding-math)
if(CMAKE_SYSTEM_PROCESSOR MATCHES "x86_64|AMD64")
  list(APPEND LWR_STRICT $<$<COMPILE_LANGUAGE:CXX>:-msse4.1>)
endif()

add_library(lge_generated OBJECT "${LGE_GENERATED_DIR}/lge_generated.cpp")
target_compile_features(lge_generated PRIVATE cxx_std_23)
target_include_directories(lge_generated BEFORE PRIVATE "${LGE_DIR}" "${LGE_GENERATED_DIR}")
target_link_libraries(lge_generated PRIVATE rex::runtime)
target_compile_options(lge_generated PRIVATE ${LWR_STRICT})
if(CMAKE_CXX_COMPILER_ID STREQUAL "GNU")
  set(LGE_PORTABLE_DEFINE_DEFAULT ON)
else()
  set(LGE_PORTABLE_DEFINE_DEFAULT OFF)
endif()
option(LGE_PORTABLE_DEFINE "Force-include lge_define_rex_func.h for the generated object"
       ${LGE_PORTABLE_DEFINE_DEFAULT})
if(LGE_PORTABLE_DEFINE)
  target_compile_options(lge_generated PRIVATE -include "${LGE_DIR}/lge_define_rex_func.h")
endif()

add_executable(lwr_tests lwr_tests.cpp "${LRB_DIR}/lrb_bootstrap.cpp" $<TARGET_OBJECTS:lge_generated>)
target_compile_features(lwr_tests PRIVATE cxx_std_23)
target_include_directories(lwr_tests PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}" "${LRB_DIR}")
target_compile_options(lwr_tests PRIVATE ${LWR_STRICT})
target_link_libraries(lwr_tests PRIVATE rex::runtime)
if(WIN32)
  target_compile_definitions(lwr_tests PRIVATE _CRT_SECURE_NO_WARNINGS)
endif()
if(LRB_ORDINARY_ONLY)
  target_compile_definitions(lwr_tests PRIVATE LRB_ORDINARY_ONLY)
else()
  if(NOT CMAKE_SYSTEM_NAME STREQUAL "Linux" OR NOT CMAKE_SYSTEM_PROCESSOR MATCHES "x86_64|AMD64")
    message(FATAL_ERROR "The native LWR owner requires Linux x86-64")
  endif()
  enable_language(ASM)
  # The signal-context admission path: no stack protector, no vector or x87
  # registers. Its machine code is audited for calls, TLS model and stores.
  set_source_files_properties(lwr_restart.c PROPERTIES COMPILE_OPTIONS
                              "-fno-stack-protector;-mgeneral-regs-only")
  set(LWR_OWNER_SOURCES "${LRB_DIR}/lrb_owner.c" "${LRB_DIR}/lrb_access.S" lwr_restart.c lwr_test_leaf.S)
  # The audited LRB owner and transport; LRB_RESTART compiles in only the
  # documented admission hook (LRB/LGE builds never define it).
  target_sources(lwr_tests PRIVATE ${LWR_OWNER_SOURCES})
  target_compile_definitions(lwr_tests PRIVATE LRB_TEST LRB_RESTART)
  set_property(TARGET lwr_tests PROPERTY C_STANDARD 11)
  target_compile_options(lwr_tests PRIVATE -pthread)
  # Eager binding: no lazy PLT resolution on any signal-context path.
  target_link_options(lwr_tests PRIVATE -Wl,-z,now -Wl,-z,relro)
  target_link_libraries(lwr_tests PRIVATE pthread)

  # Synthetic mechanism probe: no SDK, no generated code.
  add_executable(lwr_probe lwr_probe.c ${LWR_OWNER_SOURCES})
  target_include_directories(lwr_probe PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}" "${LRB_DIR}")
  target_compile_definitions(lwr_probe PRIVATE LRB_TEST LRB_RESTART)
  set_property(TARGET lwr_probe PROPERTY C_STANDARD 11)
  target_compile_options(lwr_probe PRIVATE -O${LWR_OPT} -Wall -Wextra -Werror -pthread)
  target_link_options(lwr_probe PRIVATE -Wl,-z,now -Wl,-z,relro)
  target_link_libraries(lwr_probe PRIVATE pthread)
endif()
