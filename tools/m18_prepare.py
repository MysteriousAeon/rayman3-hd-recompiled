"""M18 host additions (D-047): the revisit compatibility hooks in the codegen manifest, their header beside the
host sources, and the regression target for the decision table. Runs after m11_prepare.py (manifest) and
m16_prepare.py (CMake section order)."""
import shutil

from m2_prepare import ROOT, W, write_text_if_changed

if __name__ == '__main__':
    source, target = ROOT / 'tools/m18_revisit.h', W / 'src/m18_revisit.h'
    if not target.exists() or source.read_bytes() != target.read_bytes():
        shutil.copyfile(source, target)
    manifest = W / 'r3hd_manifest.toml'
    text = manifest.read_text()
    entry = '"../../../config/rexglue/r3hd_compat.toml"'
    if entry not in text:
        anchor = '"../../../config/rexglue/r3hd_wait.toml"]'
        assert text.count(anchor) == 1, 'manifest include list not recognised (run m11_prepare.py first)'
        text = text.replace(anchor, anchor[:-1] + ', ' + entry + ']')
    write_text_if_changed(manifest, text)
    p = W / 'CMakeLists.txt'
    mark = '\n# --- Milestone 18 targets ---\n'
    write_text_if_changed(p, p.read_text().split(mark)[0] + mark + '''add_executable(m18_revisit_test "${CMAKE_CURRENT_SOURCE_DIR}/../../../tools/m18_revisit_test.cpp")
target_include_directories(m18_revisit_test PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/../../../tools")
target_compile_features(m18_revisit_test PRIVATE cxx_std_20)
''')
