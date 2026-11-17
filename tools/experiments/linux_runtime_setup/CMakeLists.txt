cmake_minimum_required(VERSION 3.24)
# Linux Runtime Setup Ownership (LRSO): opt-in, isolated, native Linux x86-64
# only, never part of the Windows release build. Consumes an EXISTING installed
# SDK; never builds or patches it. No generated code and no private inputs.
project(linux_runtime_setup LANGUAGES C CXX ASM)
find_package(rexglue CONFIG REQUIRED)
if(NOT TARGET rex::runtime)
  message(FATAL_ERROR "An existing matching SDK installation exporting rex::runtime is required")
endif()
if(NOT CMAKE_CXX_COMPILER_ID MATCHES "Clang|GNU")
  message(FATAL_ERROR "Clang or GCC required")
endif()
if(NOT CMAKE_SYSTEM_NAME STREQUAL "Linux" OR NOT CMAKE_SYSTEM_PROCESSOR MATCHES "x86_64|AMD64")
  message(FATAL_ERROR "LRSO requires native Linux x86-64")
endif()
if(NOT LRSO_OPT STREQUAL "0" AND NOT LRSO_OPT STREQUAL "2")
  message(FATAL_ERROR "Set LRSO_OPT=0 or 2")
endif()
set(LRB_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../linux_runtime_bootstrap")
set(LWR_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../linux_write_watch_restart")
set(LRSO_STRICT -O${LRSO_OPT} -Wall -Wextra -Werror -fno-fast-math -frounding-math)

# The audited LRB owner/transport and the audited LWR admission path, built
# exactly as the LWR gate builds them (same per-source flags, LRB_RESTART hook).
set_source_files_properties("${LWR_DIR}/lwr_restart.c" PROPERTIES COMPILE_OPTIONS
                            "-fno-stack-protector;-mgeneral-regs-only")
add_executable(lrso_tests lrso_tests.cpp "${LRB_DIR}/lrb_bootstrap.cpp"
               "${LRB_DIR}/lrb_owner.c" "${LRB_DIR}/lrb_access.S"
               "${LWR_DIR}/lwr_restart.c" "${LWR_DIR}/lwr_test_leaf.S")
target_compile_features(lrso_tests PRIVATE cxx_std_23)
set_property(TARGET lrso_tests PROPERTY C_STANDARD 11)
target_include_directories(lrso_tests PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}" "${LRB_DIR}" "${LWR_DIR}")
target_compile_definitions(lrso_tests PRIVATE LRB_TEST LRB_RESTART)
target_compile_options(lrso_tests PRIVATE ${LRSO_STRICT} -pthread)
# Eager binding: no lazy PLT resolution on any signal-context path.
target_link_options(lrso_tests PRIVATE -Wl,-z,now -Wl,-z,relro)
target_link_libraries(lrso_tests PRIVATE rex::runtime pthread ${CMAKE_DL_LIBS})
