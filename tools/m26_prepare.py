"""M26 host additions (D-058): regression target for the texture orientation correction. Runs after
m23_prepare.py (each prepare script rewrites everything after its own marker)."""
from m2_prepare import W, write_text_if_changed

if __name__ == '__main__':
    p = W / 'CMakeLists.txt'
    mark = '\n# --- Milestone 26 targets ---\n'
    write_text_if_changed(p, p.read_text().split(mark)[0] + mark + '''add_executable(m26_texture_orient_test "${CMAKE_CURRENT_SOURCE_DIR}/../../../tools/m26_texture_orient_test.cpp")
target_include_directories(m26_texture_orient_test PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/../../../tools")
target_compile_features(m26_texture_orient_test PRIVATE cxx_std_20)
''')
