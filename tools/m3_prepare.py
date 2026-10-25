"""Milestone 3 additions to the ignored ReXGlue project (idempotent; run after m2_prepare.py prepare)."""
from pathlib import Path
import json, re

ROOT = Path(__file__).resolve().parents[1]
W = ROOT / 'private/work/rex'
MARK = '\n# --- Milestone 3 targets ---\n'
BLOCK = MARK + '''add_executable(m3_exception_test "${CMAKE_CURRENT_SOURCE_DIR}/../../../tools/m3_tests/exceptions.cpp")
target_include_directories(m3_exception_test PRIVATE src generated/default "${CMAKE_CURRENT_SOURCE_DIR}/../../../tools/m3_tests")
target_link_libraries(m3_exception_test PRIVATE rex::runtime)
rexglue_apply_target_settings(m3_exception_test)
target_compile_options(m3_exception_test PRIVATE -fasync-exceptions)
add_dependencies(m3_exception_test m2_instrument)
'''
INCLUDES_M2 = '"../../../config/rexglue/r3hd_indirect.toml"'
INCLUDES_M3 = '"../../../config/rexglue/r3hd_indirect_m3.toml"'
SYNTH = '"../../../config/rexglue/r3hd_synth_targets.toml"'


def write_if_changed(path, text):
    if not path.exists() or path.read_text() != text:
        path.write_text(text)


def write_indirect_config():
    """E-23: the 100 M2 data-only hints that have a genuine data holder. The other 22
    were inline __except bodies referenced only by SEH scope tables (see RE_NOTES.md)."""
    reclass = json.loads((ROOT / 'reports/milestone3/data/indirect_reclass.json').read_text())
    genuine = set(reclass['genuine'])
    bodies = {a for a, _ in reclass['eh_only']}
    old = re.findall(r'^(0x[0-9A-F]+) =', (ROOT / 'config/rexglue/r3hd_indirect.toml').read_text(), re.M)
    assert set(old) == genuine | bodies and len(genuine) == 100 and len(bodies) == 22
    lines = ['# E-23 (Milestone 3): data-referenced entrypoints with a non-exception-table holder.',
             '# Supersedes r3hd_indirect.toml, which also promoted 22 inline __except bodies.',
             '[functions]'] + [a + ' = {}' for a in old if a in genuine]
    write_if_changed(ROOT / 'config/rexglue/r3hd_indirect_m3.toml', '\n'.join(lines) + '\n')


if __name__ == '__main__':
    write_indirect_config()
    manifest = W / 'r3hd_manifest.toml'
    text = manifest.read_text().replace(INCLUDES_M2, INCLUDES_M3)
    if SYNTH not in text:
        text = text.replace(INCLUDES_M3, INCLUDES_M3 + ', ' + SYNTH)
    write_if_changed(manifest, text)
    cmake = W / 'CMakeLists.txt'
    write_if_changed(cmake, cmake.read_text().split(MARK)[0] + BLOCK)
