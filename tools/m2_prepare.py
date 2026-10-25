"""Prepare the ignored ReXGlue init project without copying game material to git."""
from pathlib import Path
import hashlib, json, re, shutil, subprocess, os

ROOT = Path(__file__).resolve().parents[1]
W = ROOT / 'private/work/rex'
G = W / 'generated/default'

def write_text_if_changed(path, text):
    if not path.exists() or path.read_text() != text:
        path.write_text(text)

def source_hashes():
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(G.glob('*')) if p.suffix in ('.cpp', '.h')}

if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['snapshot', 'prepare', 'instrument'])
    ap.add_argument('--output')
    args = ap.parse_args()
    if args.mode == 'snapshot':
        Path(args.output).write_text(json.dumps(source_hashes(), indent=2) + '\n')
    elif args.mode == 'prepare':
        pin = subprocess.check_output(['git', '-C', str(ROOT/'external/rexglue-sdk'),
                                       'rev-parse', 'HEAD'], text=True).strip()
        assert pin == 'c94f5ebdcb3c9d1a460ca48e04f9758448f8d518', pin
        # M28 (D-062): R3HD_GAME_DIR names the extracted game data root (tools/r3hd_intake.py extract writes it
        # as OUT/content); the default is the developer layout, written relative as before.
        game_dir = Path(os.environ.get('R3HD_GAME_DIR') or ROOT/'private/extracted/5841123F').resolve()
        if game_dir == (ROOT/'private/extracted/5841123F').resolve():
            game_ref = '../../extracted/5841123F'
        else:
            game_ref = game_dir.as_posix()
        xex = game_dir/'Default.xex'
        if not xex.is_file():
            raise SystemExit(f'm2_prepare: no Default.xex in {game_dir} (set R3HD_GAME_DIR to the intake output content directory)')
        assert hashlib.sha256(xex.read_bytes()).hexdigest() == '77a4df54340aebcc79eb0f0053938c03b8efd2efdd3ffee26c00fdfef3c6e8ca'
        if not (W/'CMakeLists.txt').exists():
            W.mkdir(parents=True, exist_ok=True)
            subprocess.run([str(ROOT/'external/rexglue-sdk/out/win-amd64/Release/rexglue.exe'),
                'init', '--project-name', 'r3hd', '--xex-path', f'{game_ref}/Default.xex',
                '--game-root', game_ref, '--project-root', '.', '--scan-dll'],
                cwd=W, check=True)
        text = (ROOT/'config/rexglue/r3hd_functions_e09_experimental.toml').read_text()
        targets = re.findall(r'^(0x[0-9A-F]+) =', text, re.M)
        targets = [a for a in targets if a not in ('0x823D90DC', '0x826C2D88')]
        assert len(targets) == 122
        write_text_if_changed(ROOT/'config/rexglue/r3hd_indirect.toml',
            '# E-15: E-09 data-only entrypoints, excluding the two inline __except bodies.\n'
            '# Provenance and exception scope metadata: RE_NOTES.md, Milestone 2.\n'
            '[functions]\n' + ''.join(a+' = {}\n' for a in targets))
        write_text_if_changed(W/'r3hd_manifest.toml', f'''[project]
name = "r3hd"
sdk_version = "0.10.0"
game_root = "{game_ref}"
[entrypoint]
file_path = "{game_ref}/Default.xex"
out_directory_path = "generated/default"
includes = ["../../../config/rexglue/r3hd_functions.toml", "../../../config/rexglue/r3hd_indirect.toml", "../../../config/rexglue/r3hd_runtime_targets.toml", "../../../config/rexglue/r3hd_observe.toml", "../../../config/rexglue/r3hd_nonlocal.toml"]
generate_exception_handlers = true
''')
        for name in ('main.cpp', 'r3hd_app.h', 'r3hd_window_icon.h', 'r3hd_discord.h', 'm2_trace.h', 'm2_trace.cpp'):
            source, target = ROOT/'tools/m2_host'/name, W/'src'/name
            if not target.exists() or source.read_bytes() != target.read_bytes():
                shutil.copyfile(source, target)
        cmake = (W/'CMakeLists.txt').read_text()
        if 'src/m2_trace.cpp' not in cmake:
            cmake = cmake.replace('src/main.cpp', 'src/main.cpp\n    src/m2_trace.cpp')
        cmake = cmake.replace('rexglue_setup_target(r3hd)', 'rexglue_setup_target(r3hd GPU_PLUGINS xenos)')
        discord_include = '\ntarget_include_directories(r3hd PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/../../../external/rexglue-sdk/thirdparty/inja/third_party/include")\n'
        cmake += '\nfind_package(Python3 REQUIRED COMPONENTS Interpreter)\nadd_custom_target(m2_instrument\n COMMAND ${Python3_EXECUTABLE} "${CMAKE_CURRENT_SOURCE_DIR}/../../../tools/m2_prepare.py" instrument\n DEPENDS r3hd_codegen)\nadd_dependencies(r3hd_recomp m2_instrument)\ntarget_link_options(r3hd PRIVATE "LINKER:/DEBUG" "LINKER:/MAP:${CMAKE_CURRENT_BINARY_DIR}/r3hd.map")\nadd_executable(m2_nonlocal_test "${CMAKE_CURRENT_SOURCE_DIR}/../../../tools/m2_tests/nonlocal.cpp")\ntarget_include_directories(m2_nonlocal_test PRIVATE src generated/default)\ntarget_link_libraries(m2_nonlocal_test PRIVATE rex::runtime)\nrexglue_apply_target_settings(m2_nonlocal_test)\ntarget_compile_options(m2_nonlocal_test PRIVATE -fasync-exceptions)\nadd_dependencies(m2_nonlocal_test m2_instrument)\n'
        # Re-running preparation should not duplicate the custom target.
        cmake = cmake[:cmake.find('\nfind_package(Python3')] + cmake[cmake.rfind('\nfind_package(Python3'):]
        if discord_include not in cmake:
            cmake += discord_include
        write_text_if_changed(W/'CMakeLists.txt', cmake)
    elif args.mode == 'instrument':
        pch = G/'r3hd_pch.h'
        cache = W/'m2_pch_cache.json'
        text = pch.read_text()
        marker = '// M2 observational instrumentation'
        text = text.split(marker)[0]
        text += '''// M2 observational instrumentation
#include "m2_trace.h"
#undef REX_FUNC_PROLOGUE
#define REX_FUNC_PROLOGUE() M2Enter(__func__, ctx); __builtin_assume(((size_t)base & 0x1F) == 0)
'''
        if pch.read_text() != text:
            pch.write_text(text)
        digest = hashlib.sha256(pch.read_bytes()).hexdigest()
        # Codegen temporarily removes the observer include. Restore its prior
        # timestamp only if the final bytes are identical, avoiding a full PCH
        # rebuild for each one-address analysis hint.
        prior = json.loads(cache.read_text()) if cache.exists() else {}
        if prior.get('sha256') == digest:
            os.utime(pch, ns=(pch.stat().st_atime_ns, prior['mtime_ns']))
        cache.write_text(json.dumps({'sha256': digest, 'mtime_ns': pch.stat().st_mtime_ns}))
