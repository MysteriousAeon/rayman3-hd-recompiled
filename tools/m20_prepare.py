"""M20 host additions (D-049): regression target for the staged save replacement. Runs after m18_prepare.py,
which rewrites everything after its own marker."""
from m2_prepare import W, write_text_if_changed

if __name__ == '__main__':
    p = W / 'CMakeLists.txt'
    mark = '\n# --- Milestone 20 targets ---\n'
    write_text_if_changed(p, p.read_text().split(mark)[0] + mark + '''add_executable(m20_save_commit_test "${CMAKE_CURRENT_SOURCE_DIR}/../../../tools/m20_save_commit_test.cpp")
target_include_directories(m20_save_commit_test PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/../../../tools")
target_compile_features(m20_save_commit_test PRIVATE cxx_std_20)
target_link_options(m20_save_commit_test PRIVATE -municode)
''')
