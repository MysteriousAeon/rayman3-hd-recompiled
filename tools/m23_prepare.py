"""M23 host additions (D-052): regression targets for the two-layer surface correction's microcode edit
and for the hidden-run haptics policy (D-053). Runs
after m21_prepare.py (each prepare script rewrites everything after its own marker)."""
from m2_prepare import W, write_text_if_changed

if __name__ == '__main__':
    p = W / 'CMakeLists.txt'
    mark = '\n# --- Milestone 23 targets ---\n'
    write_text_if_changed(p, p.read_text().split(mark)[0] + mark + '''add_executable(m23_water_test "${CMAKE_CURRENT_SOURCE_DIR}/../../../tools/m23_water_test.cpp")
target_include_directories(m23_water_test PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/../../../tools")
target_compile_features(m23_water_test PRIVATE cxx_std_20)
add_executable(m23_haptics_test "${CMAKE_CURRENT_SOURCE_DIR}/../../../tools/m23_haptics_test.cpp")
target_include_directories(m23_haptics_test PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/../../../tools")
target_compile_features(m23_haptics_test PRIVATE cxx_std_20)
''')
