"""M16 host additions: regression target for the system-UI input gate (D-044). Runs after m10_prepare.py, which
rewrites everything after its own marker."""
from m2_prepare import W, write_text_if_changed

if __name__ == '__main__':
    p = W/'CMakeLists.txt'
    mark = '\n# --- Milestone 16 targets ---\n'
    write_text_if_changed(p, p.read_text().split(mark)[0] + mark + '''add_executable(m16_sysui_test "${CMAKE_CURRENT_SOURCE_DIR}/../../../tools/m16_sysui_test.cpp")
target_link_libraries(m16_sysui_test PRIVATE rex::runtime)
rexglue_apply_target_settings(m16_sysui_test)
''')
