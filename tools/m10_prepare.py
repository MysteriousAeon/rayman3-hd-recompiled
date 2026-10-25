"""M10 host additions: regression target for the keyboard confirm / cancel bindings."""
from m2_prepare import W, write_text_if_changed

if __name__ == '__main__':
    p = W/'CMakeLists.txt'
    mark = '\n# --- Milestone 10 targets ---\n'
    write_text_if_changed(p, p.read_text().split(mark)[0] + mark + '''add_executable(m10_input_test "${CMAKE_CURRENT_SOURCE_DIR}/../../../tools/m10_input_test.cpp")
target_link_libraries(m10_input_test PRIVATE rex::runtime)
rexglue_apply_target_settings(m10_input_test)
''')
