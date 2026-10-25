"""Prepare M4 tests and build configuration; all extracted emission stays private."""
from pathlib import Path
from m2_prepare import ROOT, W, G, write_text_if_changed

MARK = '\n# --- Milestone 4 targets ---\n'
if __name__ == '__main__':
    # Keep M3's 79 assertions untouched. Exercise the production helper with the
    # same scaffold; the C++ table tests remain explicitly test-only prototypes.
    src = (ROOT / 'tools/m3_tests/exceptions.cpp').read_text().replace('M3', 'M4').replace('m3_', 'm4_').replace('m3 exception regressions:', 'm4 exception regressions:')
    src = src.replace('#include "m4_guest_seh.h"', '#include <rex/m4_seh.h>\n#include "m4_cxx_prototype.h"')
    src = src.replace('Resolve(uint32_t address)', 'Resolve(uint32_t address, uint8_t*)')
    src = src.replace('static uint8_t g_mem[0x20000];', 'alignas(4096) static uint8_t g_mem[0x20000];')
    src = src.replace('g_null = nullptr;', 'g_null = reinterpret_cast<volatile uint32_t*>(g_mem + 0x18000);')
    src = src.replace('int main() {', 'int main() {\n  DWORD old_protection;\n  if (!VirtualProtect(g_mem + 0x18000, 4096, PAGE_NOACCESS, &old_protection)) return 2;')
    src = src.replace('int main() {', '#include "../../../tools/m4_extra_tests.h"\nint main() {')
    src = src.replace('  std::printf("m4 exception regressions:', '  ExtraTests();\n  std::printf("m4 exception regressions:')
    write_text_if_changed(W / 'm4_exceptions.cpp', src)
    cxx = (ROOT / 'tools/m3_tests/m3_guest_seh.h').read_text().split('// ---- C++ EH')[1]
    cxx = ('// Test-only C++ EH prototype; not emitted or enabled in production.\n// ---- C++ EH' + cxx).replace('M3', 'M4')
    cxx = cxx.replace('resolve(e.action)(ctx, base);', 'resolve(e.action, base)(ctx, base);')
    write_text_if_changed(W / 'm4_cxx_prototype.h', cxx)
    cmake = W / 'CMakeLists.txt'
    block = MARK + '''add_executable(m4_exception_test m4_exceptions.cpp)
target_include_directories(m4_exception_test PRIVATE src generated/default .)
target_link_libraries(m4_exception_test PRIVATE rex::runtime)
rexglue_apply_target_settings(m4_exception_test)
target_compile_options(m4_exception_test PRIVATE -fasync-exceptions)
add_dependencies(m4_exception_test m2_instrument)
add_executable(m4_generated_test m4_generated_test.cpp)
target_include_directories(m4_generated_test PRIVATE src generated/default .)
target_link_libraries(m4_generated_test PRIVATE rex::runtime)
rexglue_apply_target_settings(m4_generated_test)
target_compile_options(m4_generated_test PRIVATE -fasync-exceptions)
add_dependencies(m4_generated_test m2_instrument)
add_executable(m4_input_test "${CMAKE_CURRENT_SOURCE_DIR}/../../../tools/m4_input_test.cpp")
target_link_libraries(m4_input_test PRIVATE rex::runtime)
rexglue_apply_target_settings(m4_input_test)
'''
    write_text_if_changed(cmake, cmake.read_text().split(MARK)[0] + block)
