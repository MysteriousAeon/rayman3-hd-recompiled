"""Native host test of the private Combo handle binding; no game is started.

Run under tools/devenv.bat. Synthetic registry tests are not guest execution.
"""
import ast
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'tools/m2_host/m2_trace.cpp').read_text()
patch_tree = ast.parse((ROOT / 'tools/m8_runtime_patch.py').read_text())
capture_edits = next(ast.literal_eval(node.args[1]) for node in ast.walk(patch_tree)
                     if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                     and node.func.id == 'patch_once' and isinstance(node.args[0], ast.Constant)
                     and node.args[0].value == 'include/rex/m3_gpu_trace.h')
live_header = (ROOT / 'external/rexglue-sdk/include/rex/m3_gpu_trace.h').read_text()
capture_before, capture_after = capture_edits[1]
assert live_header.count(capture_after) == 1

def replay(text):
    for before, after in capture_edits:
        if after in text:
            continue
        assert text.count(before) == 1
        text = text.replace(before, after)
    return text

assert replay(live_header.replace(capture_after, capture_before)) == live_header
assert replay(live_header) == live_header
binding = source.split('static bool ComboPlayableObject(uint32_t object) {', 1)[1].split('\n}\n', 1)[0]
fixture = r'''
#include <cassert>
#include <cstdint>
#include <map>
static std::map<uint32_t, uint32_t> memory;
static uint32_t M18Load(uint32_t address) { return memory.at(address); }
static bool ComboPlayableObject(uint32_t object) {
BODY
}
int main() {
  memory = {{0x8288D658, 2}, {0x829A3E18, 2},
            {0x82890598, 1}, {0x828905A8, 2}, {0x828905B0, 0x828A3E88}};
  assert(ComboPlayableObject(0x828A3E98));
  // Synthetic recreation: old address no longer belongs to the active handle.
  memory[0x8288D658] = 3;
  memory[0x828905A8] = 3;
  memory[0x828905B0] = 0x828A5000;
  assert(!ComboPlayableObject(0x828A3E98));
  assert(ComboPlayableObject(0x828A5010));
  assert(!ComboPlayableObject(0x828A5014));
  memory[0x8288D658] = 4;
  assert(!ComboPlayableObject(0x828A5010));
  memory[0x8288D658] = 0;
  assert(!ComboPlayableObject(0x828A5010));
  memory[0x8288D658] = 3;
  memory[0x829A3E18] = 257;
  assert(!ComboPlayableObject(0x828A5010));
  memory[0x829A3E18] = 2;
  memory[0x828905B0] = 0x828A5001;
  assert(!ComboPlayableObject(0x828A5011));
  memory[0x828905B0] = 0xFFFFFFFF;
  assert(!ComboPlayableObject(15));
}
'''.replace('BODY', binding)
compiler = shutil.which('clang-cl')
if not compiler:
    raise SystemExit('Run through tools/devenv.bat (clang-cl and MSVC headers required)')
work = (ROOT / 'private/work').resolve(strict=True)
work.relative_to(ROOT.resolve())
with tempfile.TemporaryDirectory(dir=work, prefix='combo_binding_') as tmp:
    directory = Path(tmp).resolve(strict=True)
    directory.relative_to(work)  # Validate the eventual recursive temp cleanup target.
    cpp, exe = directory / 'binding.cpp', directory / 'binding.exe'
    cpp.write_text(fixture)
    subprocess.run([compiler, '/nologo', '/std:c++20', '/UNDEBUG', str(cpp),
                    f'/Fe{exe}', f'/Fo{directory / "binding.obj"}'], cwd=directory, check=True)
    subprocess.run([str(exe)], cwd=directory, check=True)
    profile = source.split('static bool ComboProfileEnabled() {', 1)[1].split('\n}\n', 1)[0]
    cpp.write_text('''
#include <cassert>
#include <cstdlib>
#include <cstring>
#define REXLOG_INFO(...)
static bool ComboProfileEnabled() { BODY
}
int main(int argc, char**) { assert(ComboProfileEnabled() == (argc == 2)); }
'''.replace('BODY', profile))
    subprocess.run([compiler, '/nologo', '/std:c++20', '/UNDEBUG', str(cpp),
                    f'/Fe{exe}', f'/Fo{directory / "binding.obj"}'], cwd=directory, check=True)
    for value in ('', 'original', 'delayed', 'wrong', 'DELAYED'):
        environment = dict(os.environ, R3HD_COMBO_CLOSE=value)
        environment.pop('R3HD_TEST_COMBO_CLOSE', None)
        environment.pop('R3HD_TEST_COMBO_PLAYTEST', None)
        subprocess.run([str(exe)] + (['enabled'] if value == 'delayed' else []),
                       cwd=directory, env=environment, check=True)
    capture_header = (ROOT / 'external/rexglue-sdk/include/rex/m3_gpu_trace.h').read_text()
    capture = capture_header.split('inline bool CaptureAt(uint64_t swap) {', 1)[1].split('\n}\n', 1)[0]
    gate = r'''
#include <cassert>
#include <cstdint>
#include <cstdlib>
#include <cstring>
namespace m6frame { static unsigned calls = 0; bool CaptureAt(uint64_t) { ++calls; return true; } }
bool CaptureAt(uint64_t swap) { BODY
}
int main() {
  _putenv_s("R3HD_NONINTRUSIVE", "");
  _putenv_s("R3HD_M5_CAPTURE", "");
  _putenv_s("R3HD_PLAY", "1");
  _putenv_s("R3HD_TEST_COMBO_CAPTURE", "");
  _putenv_s("R3HD_FRAME_REQUEST", "request.txt");
  assert(!CaptureAt(2) && m6frame::calls == 0);
  _putenv_s("R3HD_TEST_COMBO_CAPTURE", "wrong");
  assert(!CaptureAt(2) && m6frame::calls == 0);
  _putenv_s("R3HD_TEST_COMBO_CAPTURE", "1");
  assert(CaptureAt(2) && m6frame::calls == 1);
  _putenv_s("R3HD_FRAME_REQUEST", "");
  assert(!CaptureAt(2) && m6frame::calls == 1);
}
'''.replace('BODY', capture)
    cpp.write_text(gate)
    subprocess.run([compiler, '/nologo', '/std:c++20', '/UNDEBUG', str(cpp),
                    f'/Fe{exe}', f'/Fo{directory / "binding.obj"}'], cwd=directory, check=True)
    subprocess.run([str(exe)], cwd=directory, check=True)
print('COMBO_BINDING_NATIVE PASS (synthetic old/recreated/stale/missing/invalid registry cases)')
print('COMBO_PROFILE_NATIVE PASS (normal configuration, no private flags, exact delayed value only)')
print('COMBO_CAPTURE_GATE_NATIVE PASS (ordinary Play off, exact private flag and request required)')
print('COMBO_CAPTURE_PATCH_REPLAY PASS (fresh and repeated transforms match installed header)')
