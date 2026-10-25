"""M21 host additions (D-050): regression target for the cursor rule and the time-zone bias. Runs after
m20_prepare.py, which rewrites everything after its own marker."""
from m2_prepare import W, write_text_if_changed

if __name__ == '__main__':
    p = W / 'CMakeLists.txt'
    mark = '\n# --- Milestone 21 targets ---\n'
    write_text_if_changed(p, p.read_text().split(mark)[0] + mark + '''add_executable(m21_host_test "${CMAKE_CURRENT_SOURCE_DIR}/../../../tools/m21_host_test.cpp")
target_include_directories(m21_host_test PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/../../../tools")
target_compile_features(m21_host_test PRIVATE cxx_std_20)
''')
