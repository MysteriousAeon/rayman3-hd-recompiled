"""Create a separate private codegen project; never patch generated C++ or shared build outputs."""
import json
import shutil
import subprocess
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'private/work/rex'
DEST = ROOT / 'private/work/trailer_capture'

def prepared_app():
    # Preserve the established m5_prepare host replay, including the M6 timer in m5_host_input.h.
    text = (ROOT / 'tools/m2_host/r3hd_app.h').read_text()
    for before, after in (
        ('#include "m2_trace.h"', '#include "m2_trace.h"\n#include "m5_host_input.h"'),
        (' public:', '  M5HostInput m5_input_;\n public:'),
        ('REXLOG_INFO("M2 launch_prepared");', 'REXLOG_INFO("M2 launch_prepared"); m5_input_.Start(window());'),
        ('  void OnShutdown() override {', '  void OnShutdown() override {\n    m5_input_.Stop();'),
    ):
        assert text.count(before) == 1, before
        text = text.replace(before, after)
    return text.encode()

def refresh():
    if not (DEST / 'capture.toml').is_file():
        raise SystemExit('Prepare the separate capture project first')
    for name in ('trailer_capture_gate.cpp', 'trailer_capture_input.h'):
        shutil.copyfile(ROOT / 'tools' / name, DEST / 'src' / name)
    timer = (SOURCE / 'src/m5_host_input.h').read_bytes()
    assert b'R3HD_TEST_SECONDS' in timer and b'M6 bounded_exit' in timer
    (DEST / 'src/m5_host_input.h').write_bytes(timer)
    (DEST / 'src/r3hd_app.h').write_bytes(prepared_app())
    cmake = DEST / 'CMakeLists.txt'
    text = cmake.read_text()
    marker = '# Capture input regression (window-less real driver)'
    if marker not in text:
        text += '''
# Capture input regression (window-less real driver)
add_executable(capture_input_test "../../../tools/trailer_capture_input_test.cpp")
target_compile_definitions(capture_input_test PRIVATE R3HD_PRIVATE_CAPTURE=1)
target_link_libraries(capture_input_test PRIVATE rex::runtime)
rexglue_apply_target_settings(capture_input_test)
'''
        cmake.write_bytes(text.encode())
    print('CAPTURE_REFRESH_OK (host input only; codegen unchanged)')

def seal():
    import r3hd_release_audit as audit
    binary = DEST / 'build/r3hd.exe'
    assert audit.capture_binary(binary.read_bytes()), 'Capture identity missing'
    for name in ('trailer_capture_gate.cpp', 'trailer_capture_input.h'):
        assert (DEST / 'src' / name).read_bytes() == (ROOT / 'tools' / name).read_bytes(), 'Capture source differs; refresh and rebuild'
    assert (DEST / 'src/r3hd_app.h').read_bytes() == prepared_app(), 'Capture app source differs'
    names = json.loads((ROOT / 'private/trailer_20261101/runtime_hashes.json').read_bytes())
    hashes = {n: hashlib.sha256((DEST / 'build' / n).read_bytes()).hexdigest() for n in names}
    (DEST / 'runtime_hashes.json').write_bytes((json.dumps(hashes, indent=2) + '\n').encode())
    command = '@echo off\r\npowershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0../../../tools/trailer_capture_launch.ps1"\r\npause\r\n'
    (DEST / 'Start Experimental Capture.cmd').write_bytes(command.encode())
    print('CAPTURE_SEAL_OK')

def main():
    if sys.argv[1:] == ['refresh']:
        refresh()
        return
    if sys.argv[1:] == ['seal']:
        seal()
        return
    if sys.argv[1:]:
        raise SystemExit('Usage: trailer_capture_prepare.py [refresh|seal]')
    if DEST.exists():
        raise SystemExit('Refusing existing capture project')
    DEST.mkdir(parents=True)
    shutil.copytree(SOURCE / 'src', DEST / 'src')
    shutil.copyfile(ROOT / 'tools/trailer_capture_gate.cpp', DEST / 'src/trailer_capture_gate.cpp')
    (DEST / 'generated').mkdir()
    shutil.copyfile(SOURCE / 'generated/rexglue.cmake', DEST / 'generated/rexglue.cmake')
    text = (SOURCE / 'r3hd_manifest.toml').read_text()
    anchor = '"../../../config/rexglue/r3hd_compat.toml"]'
    assert text.count(anchor) == 1
    text = text.replace(anchor, anchor[:-1] + ', "capture.toml"]')
    (DEST / 'r3hd_manifest.toml').write_bytes(text.encode())
    (DEST / 'capture.toml').write_bytes(b'[[midasm_hook]]\naddress = 0x821A0158\nname = "TrailerCaptureGate"\nregisters = ["r11"]\n')
    cmake = '''cmake_minimum_required(VERSION 3.25)
project(r3hd LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 23)
include(generated/rexglue.cmake)
add_executable(r3hd WIN32 src/main.cpp src/m2_trace.cpp src/trailer_capture_gate.cpp)
target_compile_definitions(r3hd PRIVATE R3HD_PRIVATE_CAPTURE=1)
target_include_directories(r3hd PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/../../../external/rexglue-sdk/thirdparty/inja/third_party/include")
rexglue_setup_target(r3hd GPU_PLUGINS xenos)
'''
    (DEST / 'CMakeLists.txt').write_bytes(cmake.encode())
    refresh()
    codegen = ROOT / 'external/rexglue-sdk/out/win-amd64/Release/rexglue.exe'
    subprocess.run([str(codegen), 'codegen', str(DEST / 'r3hd_manifest.toml')], cwd=DEST, check=True)
    audit = DEST / 'target_audit.json'
    with (DEST / 'target_audit.log').open('w') as log:
        subprocess.run(['python', str(ROOT / 'tools/m3_target_audit.py'), str(DEST / 'generated/default'),
                        str(ROOT / 'private/work/default_image.bin'), str(ROOT / 'private/work/pe_analysis.json'),
                        str(ROOT / 'reports/milestone3/data/eh_map.json'), str(audit)], stdout=log, check=True)
    report = json.loads(audit.read_bytes())
    assert not report['data_pointers']['untranslated']
    assert not report['unclassified_synthesised']
    assert not report['exception_representation']['seh_bodies_registered_as_functions']
    print('CAPTURE_PREPARE_OK target audit clean')

if __name__ == '__main__':
    main()
