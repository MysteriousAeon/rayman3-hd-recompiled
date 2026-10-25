"""M8 host additions: last-chance crash record in the host and its standalone regression target."""
from m2_prepare import ROOT, W, write_text_if_changed
import shutil

if __name__ == '__main__':
    source, target = ROOT/'tools/m8_crash_report.h', W/'src/m8_crash_report.h'
    if not target.exists() or source.read_bytes() != target.read_bytes():
        shutil.copyfile(source, target)
    p = W/'CMakeLists.txt'
    mark = '\n# --- Milestone 8 targets ---\n'
    write_text_if_changed(p, p.read_text().split(mark)[0] + mark + '''add_executable(m8_crash_test "${CMAKE_CURRENT_SOURCE_DIR}/../../../tools/m8_tests/crash_test.cpp")
target_include_directories(m8_crash_test PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/../../../tools")
target_compile_features(m8_crash_test PRIVATE cxx_std_20)
''')
