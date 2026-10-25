"""Apply a bounded observational patch to pinned ReXGlue (not guest code)."""
from pathlib import Path
import hashlib, subprocess, shutil, re
ROOT = Path(__file__).resolve().parents[1]
SDK = ROOT/'external/rexglue-sdk'
assert subprocess.check_output(['git', '-C', str(SDK), 'rev-parse', 'HEAD'], text=True).strip() == 'c94f5ebdcb3c9d1a460ca48e04f9758448f8d518'
p = SDK/'include/rex/hook.h'
original = subprocess.check_output(['git', '-C', str(SDK), 'show', 'HEAD:include/rex/hook.h']).decode()
text = original.replace('#include <rex/logging.h>', '#include <rex/logging.h>\n#include <rex/m2_import_trace.h>')
# Typed export wrappers: retain original marshaling and return behavior.
text = text.replace('    rex::ppc::HostToGuestFunction<function>(ctx, base);',
                    '    M2_IMPORT_TRACE(#subroutine, false); \\\n+    rex::ppc::HostToGuestFunction<function>(ctx, base);')
# Stub wrappers: retain the exact original warning and result behavior.
text = text.replace('    (void)base;', '    M2_IMPORT_TRACE(#subroutine, true); \\\n+    (void)base;')
text = text.replace('\n+    ', '\n    ')
p.write_text(text)
shutil.copyfile(ROOT/'tools/m2_runtime_import_trace.h', SDK/'include/rex/m2_import_trace.h')
print('hook.h sha256', hashlib.sha256(p.read_bytes()).hexdigest())
for source in (SDK/'src/kernel').rglob('*.cpp'):
    rel = source.relative_to(SDK).as_posix()
    original = subprocess.check_output(['git', '-C', str(SDK), 'show', 'HEAD:'+rel]).decode()
    text = re.sub(r'(REX_HOOK_RAW\((\w+)\)\s*\{)',
                  lambda m: m[1]+'\n  M2_IMPORT_TRACE("'+m[2]+'", false);', original)
    if text != original:
        source.write_text(text)
for rel, before, after in (
    ('src/graphics/command_processor.cpp',
     '  read_ptr_index_ = 0;\n  primary_buffer_ptr_ = ptr;',
     '  REXGPU_INFO("M2 ring_initialized address={:08X} size_log2={}", ptr, size_log2);\n  read_ptr_index_ = 0;\n  primary_buffer_ptr_ = ptr;'),
    ('src/graphics/d3d12/command_processor.cpp',
     '  return pipeline_cache_->LoadShader(shader_type, host_address, dword_count);',
     '  REXGPU_INFO("M2 shader_submit type={} guest_address={:08X} dwords={}", unsigned(shader_type), guest_address, dword_count);\n  return pipeline_cache_->LoadShader(shader_type, host_address, dword_count);'),
    ('src/kernel/xboxkrnl/xboxkrnl_io.cpp',
     '  if (XFAILED(result)) {\n    REXKRNL_IMPORT_FAIL("NtCreateFile",',
     '  REXKRNL_INFO("M2 vfs_open path={} result={:08X}", target_path, result);\n  if (XFAILED(result)) {\n    REXKRNL_IMPORT_FAIL("NtCreateFile",'),
):
    source = SDK/rel
    text = source.read_text()
    # Kernel raw-hook instrumentation may already be applied above.
    if rel.startswith('src/graphics/'):
        text = subprocess.check_output(['git', '-C', str(SDK), 'show', 'HEAD:'+rel]).decode()
    elif after in text:
        # M16: this file is not reset to the pin, and `after` still contains `before`, so every replay used to
        # add the inserted line once more (59 copies of the vfs_open trace after 59 builds: each file open was
        # logged 58 times in the M16 human session). Keep one copy and leave the file alone otherwise.
        added = after[:after.index(before)]
        collapsed = text
        while added + added in collapsed:
            collapsed = collapsed.replace(added + added, added)
        if collapsed != text:
            source.write_text(collapsed)
            print('collapsed repeated trace line in', rel)
        continue
    assert text.count(before) == 1, rel
    source.write_text(text.replace(before, after))
