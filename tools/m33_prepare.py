"""M33 host additions (D-070): the mod overlay test (tools/m33_mod_overlay_test.cpp). Runs after m32_prepare.py (each
prepare script rewrites everything after its own marker)."""
from m2_prepare import W, write_text_if_changed

if __name__ == '__main__':
    p = W / 'CMakeLists.txt'
    mark = '\n# --- Milestone 33 targets ---\n'
    write_text_if_changed(p, p.read_text().split(mark)[0] + mark + '''add_executable(m33_mod_overlay_test "${CMAKE_CURRENT_SOURCE_DIR}/../../../tools/m33_mod_overlay_test.cpp")
target_include_directories(m33_mod_overlay_test PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/../../../tools")
target_compile_features(m33_mod_overlay_test PRIVATE cxx_std_20)
''')
