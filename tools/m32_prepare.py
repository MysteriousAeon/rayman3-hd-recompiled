"""M32 host additions: the keyboard-map driver test (tools/m32_keymap_test.cpp; cases from tools/m32_regression.py)."""
from m2_prepare import W, write_text_if_changed

if __name__ == '__main__':
    p = W/'CMakeLists.txt'
    mark = '\n# --- Milestone 32 targets ---\n'
    write_text_if_changed(p, p.read_text().split(mark)[0] + mark + '''add_executable(m32_keymap_test "${CMAKE_CURRENT_SOURCE_DIR}/../../../tools/m32_keymap_test.cpp")
target_link_libraries(m32_keymap_test PRIVATE rex::runtime)
rexglue_apply_target_settings(m32_keymap_test)
''')
