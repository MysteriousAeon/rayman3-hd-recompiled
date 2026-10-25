"""Milestone 3 scripted patches to pinned ReXGlue c94f5eb. Run after m2_runtime_patch.py.

1. Generator (analysis only): seed an SEH owner's block discovery with its
   scope-table __except bodies, and emit them as labels, so every inline body is
   translated *inside its owner* instead of needing a (wrong) standalone-function
   hint. No guest semantics are altered; unreachable blocks become translated.
2. Runtime instrumentation (observational): see the INSTRUMENT table below.
Each replacement asserts that its anchor occurs exactly once.
"""
from pathlib import Path
import subprocess, sys

ROOT = Path(__file__).resolve().parents[1]
SDK = ROOT / 'external/rexglue-sdk'
PIN = 'c94f5ebdcb3c9d1a460ca48e04f9758448f8d518'
assert subprocess.check_output(['git', '-C', str(SDK), 'rev-parse', 'HEAD'], text=True).strip() == PIN


def patch(rel, edits, from_head=True):
    path = SDK / rel
    text = (subprocess.check_output(['git', '-C', str(SDK), 'show', 'HEAD:' + rel]).decode()
            if from_head else path.read_text())
    for before, after in edits:
        if after in text and before not in after:
            continue  # already applied on top of an M2-patched working file
        assert text.count(before) == 1, (rel, before[:60], text.count(before))
        text = text.replace(before, after)
    if not path.exists() or path.read_text() != text:
        path.write_text(text)
        print('patched', rel)


GENERATOR = {
    'include/rex/codegen/function_scanner.h': [(
        '    const std::unordered_set<uint32_t>& knownFunctions, uint32_t pdataSize = 0,\n'
        '    const std::unordered_map<uint32_t, JumpTable>* manualSwitchTables = nullptr);',
        '    const std::unordered_set<uint32_t>& knownFunctions, uint32_t pdataSize = 0,\n'
        '    const std::unordered_map<uint32_t, JumpTable>* manualSwitchTables = nullptr,\n'
        '    const std::vector<uint32_t>* extraBlockSeeds = nullptr);')],
    'src/codegen/function_scanner.cpp': [(
        '    const std::unordered_set<uint32_t>& knownFunctions, uint32_t pdataSize,\n'
        '    const std::unordered_map<uint32_t, JumpTable>* manualSwitchTables) {',
        '    const std::unordered_set<uint32_t>& knownFunctions, uint32_t pdataSize,\n'
        '    const std::unordered_map<uint32_t, JumpTable>* manualSwitchTables,\n'
        '    const std::vector<uint32_t>* extraBlockSeeds) {'), (
        '  worklist.push(entryPoint);\n  blockStarts.insert(entryPoint);\n',
        '  worklist.push(entryPoint);\n  blockStarts.insert(entryPoint);\n'
        '  // M3: inline __except bodies are only reachable through exception dispatch.\n'
        '  if (extraBlockSeeds) {\n'
        '    for (uint32_t seed : *extraBlockSeeds) {\n'
        '      if (isWithinFunction(seed) && blockStarts.insert(seed).second) {\n'
        '        worklist.push(seed);\n'
        '        result.labels.insert(seed);\n'
        '      }\n'
        '    }\n'
        '  }\n')],
    'src/codegen/phase_discover.cpp': [(
        '  auto result = discoverBlocks(decoded, funcAddr, *region, knownFunctions, pdataSize,\n'
        '                               &ctx.Config().switchTables);',
        '  std::vector<uint32_t> m3SehBodies;\n'
        '  if (node->hasExceptionInfo()) {\n'
        '    if (const auto* seh = node->exceptionInfo()->asSeh()) {\n'
        '      for (const auto& scope : seh->scopes)\n'
        '        if (scope.filter != 0 && scope.handler != 0)\n'
        '          m3SehBodies.push_back(scope.handler);\n'
        '    }\n'
        '  }\n'
        '  auto result = discoverBlocks(decoded, funcAddr, *region, knownFunctions, pdataSize,\n'
        '                               &ctx.Config().switchTables, &m3SehBodies);')],
    'src/codegen/function_graph.cpp': [(
        '  std::unordered_set<size_t> labels;\n  labels.reserve(64);\n',
        '  std::unordered_set<size_t> labels;\n  labels.reserve(64);\n'
        '  // M3: keep every inline __except body addressable as a label of its owner.\n'
        '  if (sehInfo) {\n'
        '    for (const auto& scope : sehInfo->scopes)\n'
        '      if (scope.filter != 0 && scope.handler != 0)\n'
        '        labels.emplace(scope.handler);\n'
        '  }\n')],
}

INSTRUMENT = {
    # (edits, from_head). d3d12/command_processor.cpp is first rewritten by m2_runtime_patch.py.
    'src/graphics/d3d12/command_processor.cpp': ([
        ('#include <rex/logging.h>\n', '#include <rex/logging.h>\n#include <rex/m3_gpu_trace.h>\n'),
        ('  REXGPU_INFO("M2 shader_submit type={} guest_address={:08X} dwords={}", unsigned(shader_type), guest_address, dword_count);\n',
         '  m3gpu::ShaderSubmit(unsigned(shader_type), guest_address, host_address, dword_count);\n'),
        ('    // Special copy handling.\n    return IssueCopy();\n  }\n',
         '    // Special copy handling.\n    return IssueCopy();\n  }\n'
         '  m3gpu::Draw(regs.values, unsigned(primitive_type), index_count);\n'),
        ('bool D3D12CommandProcessor::IssueCopy() {\n#if XE_GPU_FINE_GRAINED_DRAW_SCOPES\n  SCOPE_profile_cpu_f("gpu");\n#endif  // XE_GPU_FINE_GRAINED_DRAW_SCOPES\n',
         'bool D3D12CommandProcessor::IssueCopy() {\n#if XE_GPU_FINE_GRAINED_DRAW_SCOPES\n  SCOPE_profile_cpu_f("gpu");\n#endif  // XE_GPU_FINE_GRAINED_DRAW_SCOPES\n'
         '  m3gpu::Copy(register_file_->values);\n'),
        ('        SubmitBarriers();\n        EndSubmission(true);\n        return true;\n      });\n',
         '        SubmitBarriers();\n        EndSubmission(true);\n        ++m3gpu::counters().refreshed;\n        return true;\n      });\n'),
        ('  // was not called), to prevent leaking per-frame resources.\n  EndSubmission(true);\n}\n',
         '  // was not called), to prevent leaking per-frame resources.\n  EndSubmission(true);\n'
         '  m3gpu::Swap(presenter, frontbuffer_ptr, frontbuffer_width, frontbuffer_height, source_width_scaled,\n'
         '              source_height_scaled, unsigned(swap_texture_desc.Format), unsigned(frontbuffer_format),\n'
         '              guest_output_width, guest_output_height, display_width, display_height);\n}\n'),
    ], False),
    'src/ui/d3d12/d3d12_presenter.cpp': ([
        ('#include <rex/logging.h>\n', '#include <rex/logging.h>\n#include <atomic>\n'),
        ('    swap_chain_desc.BufferCount = UINT(PaintContext::kSwapChainBufferCount);\n',
         '    swap_chain_desc.BufferCount = UINT(PaintContext::kSwapChainBufferCount);\n'
         '    REXLOG_INFO("M3 host_swapchain_create size={}x{} format=B8G8R8A8_UNORM({}) buffers={}", swap_chain_desc.Width,\n'
         '                swap_chain_desc.Height, unsigned(kSwapChainFormat), swap_chain_desc.BufferCount);\n'),
        ('  paint_context_.present_submission_tracker.NextSubmission();\n',
         '  paint_context_.present_submission_tracker.NextSubmission();\n'
         '  {\n'
         '    static std::atomic<uint64_t> m3_presents{0};\n'
         '    uint64_t m3_n = ++m3_presents;\n'
         '    if ((m3_n & (m3_n - 1)) == 0)\n'
         '      REXLOG_INFO("M3 host_present count={} hresult={:08X} swap_chain={}x{}", m3_n, uint32_t(present_result),\n'
         '                  paint_context_.swap_chain_width, paint_context_.swap_chain_height);\n'
         '  }\n'),
    ], True),
    # The guest-raise trace lives in the import wrapper (tools/m2_runtime_import_trace.h),
    # which has the live register context; xboxkrnl_debug.cpp stays pristine (PRISTINE below).
}

PRISTINE = ['src/kernel/xboxkrnl/xboxkrnl_debug.cpp']

if __name__ == '__main__':
    for rel, edits in GENERATOR.items():
        patch(rel, edits)
    import shutil
    for rel in PRISTINE:
        (SDK / rel).write_bytes(subprocess.check_output(['git', '-C', str(SDK), 'show', 'HEAD:' + rel]))
    shutil.copyfile(ROOT / 'tools/m3_gpu_trace.h', SDK / 'include/rex/m3_gpu_trace.h')
    for rel, (edits, from_head) in INSTRUMENT.items():
        patch(rel, edits, from_head)
