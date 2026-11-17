"""M4 v1: bounded Windows SEH emission patch on top of M2/M3 at c94f5eb.

No generated translations are edited. Re-run M2, M3, then this script.
"""
from pathlib import Path
import re, shutil, subprocess
from m3_runtime_patch import SDK, ROOT, patch

def replace_once(text, before, after):
    assert text.count(before) == 1, before[:80]
    return text.replace(before, after)

PCH_TEMPLATE = 'resources/templates/codegen/pch_h.inja'
PCH_END = '  } while (0)\n'
# Appended after the template's last macro so that no Windows line (and no __LINE__ in the pch) moves; the whole
# block is excluded on Windows, so the Windows preprocessed pch is unchanged.
PCH_PORTABLE = '''
// LM-A (A4): portable guest setjmp/longjmp. MSVC's longjmp unwinds through the intervening M4 owners and runs their
// __finally; glibc's does not. Record the owner registry at setjmp and run that cleanup before the host longjmp.
#if !defined(_WIN32) || defined(R3HD_M4_PORTABLE)
#include <rex/m4_seh.h>
#undef ppc_setjmp
#define ppc_setjmp(guest_buf_addr) (::M4NoteSetjmp(guest_buf_addr), setjmp(::get_jmp_buf_map()[(guest_buf_addr)]))
[[noreturn]] inline void m4_portable_longjmp(u32 guest_buf_addr, int val) {
  ::M4LongjmpPrepare(guest_buf_addr);
  (ppc_longjmp)(guest_buf_addr, val);
}
#define ppc_longjmp(guest_buf_addr, val) ::m4_portable_longjmp(guest_buf_addr, val)
#endif
'''


def apply_portable_hooks():
    """LM-A (A4, D4): portable-backend hooks that leave the Windows preprocessed sources and line numbers unchanged."""
    text = subprocess.check_output(['git', '-C', str(SDK), 'show', 'HEAD:' + PCH_TEMPLATE]).decode()
    assert text.endswith(PCH_END) and 'M4NoteSetjmp' not in text, 'unexpected pch template'
    path = SDK / PCH_TEMPLATE
    if not path.exists() or path.read_text() != text + PCH_PORTABLE:
        path.write_text(text + PCH_PORTABLE)
        print('patched', PCH_TEMPLATE)
    # D4: an SDK host->guest call is a boundary that a guest exception transfer may not cross. The include replaces a
    # blank line and the macro replaces the call line (Windows: the same call).
    shutil.copyfile(ROOT / 'tools/m4_dispatch.h', SDK / 'include/rex/m4_dispatch.h')
    patch('src/system/function_dispatcher.cpp', [
        ('#include <rex/system/thread_state.h>\n\nnamespace rex::runtime {',
         '#include <rex/system/thread_state.h>\n#include <rex/m4_dispatch.h>\nnamespace rex::runtime {'),
        ('  fn(*ctx, memory_->virtual_membase());\n',
         '  M4_DISPATCH(fn, *ctx, memory_->virtual_membase(), address);\n')])


def apply():
    p = SDK / 'src/codegen/function_graph.cpp'
    t = p.read_text()
    assert '// M4 scope dispatch' not in t, 'Run M3 patch first'
    t = replace_once(t, '  // --- First pass: collect labels from all blocks ---',
        '  // M4 scope dispatch\n'
        '  bool generateSeh = sehInfo && !sehInfo->scopes.empty() && ctx.config.generateExceptionHandlers;\n'
        '  if (generateSeh) emit_println(out, "#include <rex/m4_seh.h>");\n\n'
        '  // --- First pass: collect labels from all blocks ---')
    # Every instruction gets a PC marker. Only actual emitted calls take a snapshot.
    t = replace_once(t, '      Disassemble(data, 4, blockBase, insn);',
        '      if (generateSeh) emit_println(body, "\\tm4.pc = 0x{:X};", blockBase);\n'
        '      Disassemble(data, 4, blockBase, insn);')
    t = replace_once(t, '        if (!DispatchInstruction(id, builderCtx)) {',
        '        size_t m4InstructionStart = body.size();\n'
        '        if (!DispatchInstruction(id, builderCtx)) {')
    anchor = '        // Check for mid-asm hook AFTER instruction'
    t = replace_once(t, anchor, r'''        if (generateSeh) {
          std::string instruction = body.substr(m4InstructionStart);
          // Transform only the emitter's statement, never disassembly comments.
          // A conditional tail call retains its condition around the whole sequence.
          const std::regex call(R"((\b\w+\(ctx, base\);|REX_CALL_INDIRECT_FUNC\([^;]+;|ppc_longjmp\([^;]+;))");
          instruction = std::regex_replace(instruction, call,
              "M4BeforeCall(m4, ctx); $1 m4.in_call = false;");
          const std::regex ret(R"(\breturn;)");
          instruction = std::regex_replace(instruction, ret, "M4_RETURN");
          if (instruction.find("ppc_setjmp(") != std::string::npos)
            instruction += fmt::format("\tm4.in_call = false; m4.pc = 0x{:X};\n", blockBase);
          body.resize(m4InstructionStart);
          body += instruction;
        }

''' + anchor)
    t = t.replace('#include <fmt/format.h>', '#include <fmt/format.h>\n#include <regex>')
    begin = t.index('  // --- Close function body (or SEH try block) ---')
    end = t.index('  // --- Emit local variable declarations, then body ---', begin)
    t = t[:begin] + '''  // --- Close emitted dispatch region ---
  if (generateSeh) {
    // LM-A (D1): project macros (tools/m4_seh.h). On Windows M4_TRY_END expands to the former
    // __finally/__except text; the portable backend gives them its own expansion. The five blank
    // lines keep every following line number (and so every __LINE__ and debug line) as before.
    emit_println(body, "\\tM4_TRY_END\\n\\n\\n\\n\\n\\n}}\\n");
  } else {
    emit_println(body, "}}\\n");
  }

''' + t[end:]
    begin = t.index('  // If SEH, emit SEH_TRY and indent body')
    end = t.index('  return out;', begin)
    t = t[:begin] + '''  if (generateSeh) {
    emit_println(out, "\\tstatic const M4Scope m4scopes[] = {{");
    for (const auto& s : sehInfo->scopes)
      emit_println(out, "\\t\\t{{0x{:X}, 0x{:X}, 0x{:X}, 0x{:X}}},", s.tryStart, s.tryEnd,
                   s.filter ? s.filter : s.handler, s.filter ? s.handler : 0);
    emit_println(out, "\\t}};");
    emit_println(out, "\\tauto m4resolve = +[](uint32_t a, uint8_t* b) -> PPCFunc* {{ return REX_LOOKUP_FUNC(b, a); }};");
    emit_println(out, "\\tM4_FRAME({})", sehInfo->scopes.size());
    emit_println(out, "m4_retry:");
    emit_println(out, "\\tM4_TRY_BEGIN");
    emit_println(out, "\\tuint32_t m4resume = m4.resume; m4.resume = 0; m4.resume_index = m4.count; m4.unwind = false;");
    emit_println(out, "\\tswitch (m4resume) {{");
    // All emitted labels are valid same-frame unwind continuations. Inline
    // except bodies are already labels of the owner due to the M3 patch.
    for (size_t label : emittedLabels)
      emit_println(out, "\\tcase 0x{:X}: goto loc_{:X};", label, label);
    emit_println(out, "\\tcase 0: break; default: M4_FAIL(7); }}");
  }
  out += body;

''' + t[end:]
    p.write_text(t)
    shutil.copyfile(ROOT / 'tools/m4_seh.h', SDK / 'include/rex/m4_seh.h')
    shutil.copyfile(ROOT / 'tools/m4_seh_portable.h', SDK / 'include/rex/m4_seh_portable.h')
    apply_portable_hooks()
    gpu = (ROOT / 'tools/m3_gpu_trace.h').read_text()
    gpu = replace_once(gpu, '  uint64_t draws_at_swap = 0, copies_at_swap = 0, clears_at_swap = 0;',
                      '  std::atomic<uint64_t> last_shader_hash[2]{};\n  uint64_t draws_at_swap = 0, copies_at_swap = 0, clears_at_swap = 0;')
    gpu = replace_once(gpu, '  std::lock_guard<std::mutex> lock(mutex);\n  if (seen[hash]++) return;',
                      '  c.last_shader_hash[type].store(hash);\n  std::lock_guard<std::mutex> lock(mutex);\n  if (seen[hash]++) return;')
    (SDK / 'include/rex/m3_gpu_trace.h').write_text(gpu)
    # Use raw wrappers so transport receives the live translated context.
    for rel, old, new in [
        ('src/kernel/xboxkrnl/xboxkrnl_debug.cpp',
         'REX_EXPORT(__imp__RtlRaiseException, rex::kernel::xboxkrnl::RtlRaiseException_entry)',
         '''REX_HOOK_RAW(__imp__RtlRaiseException) {
  M2_IMPORT_TRACE("__imp__RtlRaiseException", false);
  M4GuestRecord rec{};
  uint32_t a = ctx.r3.u32;
  rec.code = M4Ld32(base, a); rec.flags = M4Ld32(base, a + 4);
  rec.record_chain = M4Ld32(base, a + 8); rec.address = M4Ld32(base, a + 12);
  rec.nparams = M4Ld32(base, a + 16);
  if (rec.nparams > 15) __fastfail(7);
  for (uint32_t i = 0; i < rec.nparams; ++i) rec.info[i] = M4Ld32(base, a + 20 + i * 4);
  // Keep the debugger naming side effect, but guest dispatch decides disposition.
  if (rec.code == 0x406D1388)
    rex::ppc::HostToGuestFunction<rex::kernel::xboxkrnl::RtlRaiseException_entry>(ctx, base);
  M4Raise(rec);
}
static rex::ppc::detail::PPCFuncRegistrar m4raise("__imp__RtlRaiseException", &__imp__RtlRaiseException);'''),
        ('src/kernel/xboxkrnl/xboxkrnl_rtl.cpp',
         'REX_EXPORT(__imp__RtlUnwind, rex::kernel::xboxkrnl::RtlUnwind_entry)',
         '''REX_HOOK_RAW(__imp__RtlUnwind) {
  M2_IMPORT_TRACE("__imp__RtlUnwind", false);
  M4UnwindRequest req{ctx.r3.u32, ctx.r4.u32, ctx.r6.u32};
  M4RequestUnwind(req);
}
static rex::ppc::detail::PPCFuncRegistrar m4unwind("__imp__RtlUnwind", &__imp__RtlUnwind);''')]:
        p = SDK / rel
        text = replace_once(subprocess.check_output(['git', '-C', str(SDK), 'show', 'HEAD:' + rel]).decode(), old, new)
        p.write_text('#include <rex/m4_seh.h>\n' + text)
    print('M4 v1 emitter and live-context raise/unwind wrappers applied')
    # Observation only: host key events, returned guest input, mixed PCM submitted
    # to SDL, and invalid fetch slot/command counters. No result is overridden.
    for rel, before, after in [
        ('src/input/mnk/mnk_input_driver.cpp', '  SetKeyState(vk, true);',
         '  REXLOG_INFO("M4 host_key down={} vk={} focus={} active={}", true, vk, has_focus_.load(), is_active());\n  SetKeyState(vk, true);'),
        ('src/input/mnk/mnk_input_driver.cpp', '  SetKeyState(vk, false);',
         '  REXLOG_INFO("M4 host_key down={} vk={} focus={} active={}", false, vk, has_focus_.load(), is_active());\n  SetKeyState(vk, false);'),
        ('src/audio/sdl/sdl_audio_driver.cpp',
         '      driver->frames_unused_.push(buffer);\n\n      auto ret',
         '''      {
        static uint64_t frames = 0, nonzero = 0;
        double energy = 0; float peak = 0;
        for (int i = 0; i < sample_count; ++i) {
          energy += double(data[i]) * data[i]; peak = std::max(peak, std::abs(data[i]));
        }
        ++frames; if (energy > 0) ++nonzero;
        if ((frames & (frames - 1)) == 0 || (energy > 0 && nonzero == 1))
          REXAPU_INFO("M4 audio_output frames={} nonzero={} channels={} rate=48000 samples={} energy={} peak={} submitted=true",
                      frames, nonzero, unsigned(driver->sdl_device_channels_), sample_count, energy, peak);
      }
      driver->frames_unused_.push(buffer);

      auto ret'''),
        ('src/graphics/pipeline/texture/cache.cpp',
         '    BindingInfoFromFetchConstant(fetch, binding.key, &binding.swizzled_signs);',
         '''    if (fetch.type == xenos::FetchConstantType::kInvalidTexture)
      REXGPU_INFO("M4 invalid_fetch slot={} used_mask={:08X} swaps={} draws={} last_ps={:016X} last_vs={:016X} descriptor={:08X},{:08X},{:08X},{:08X},{:08X},{:08X}",
                  index, used_texture_mask, m3gpu::counters().swaps.load(), m3gpu::counters().draws.load(),
                  m3gpu::counters().last_shader_hash[1].load(), m3gpu::counters().last_shader_hash[0].load(),
                  fetch.dword_0, fetch.dword_1, fetch.dword_2, fetch.dword_3, fetch.dword_4, fetch.dword_5);
    BindingInfoFromFetchConstant(fetch, binding.key, &binding.swizzled_signs);'''),
        ('src/audio/xma_context.cpp',
         '                 decoded_frame_.data());',
         '''                 decoded_frame_.data());
    {
      static std::atomic<uint64_t> frames{0};
      uint64_t n = ++frames; size_t nonzero_bytes = 0;
      for (auto b : decoded_frame_) if (b) ++nonzero_bytes;
      if ((n & (n - 1)) == 0)
        REXAPU_INFO("M4 xma_decoded frames={} context={} guest={:08X} channels={} rate={} samples={} nonzero_bytes={}",
                    n, id(), guest_ptr(), data->is_stereo ? 2 : 1, av_context_->sample_rate,
                    av_frame_->nb_samples, nonzero_bytes);
    }''')]:
        p = SDK / rel
        # First edit starts from pin; second MnK edit continues the first.
        if 'SetKeyState(vk, false)' in before:
            text = p.read_text()
        else:
            text = subprocess.check_output(['git', '-C', str(SDK), 'show', 'HEAD:' + rel]).decode()
        text = replace_once(text, before, after)
        if rel.endswith('texture/cache.cpp'):
            text = '#include <rex/m3_gpu_trace.h>\n' + text
        if rel.endswith('xma_context.cpp'):
            text = '#include <atomic>\n' + text
        p.write_text(text)
    p = SDK / 'src/kernel/xam/xam_input.cpp'
    old = 'REX_EXPORT(__imp__XamInputGetState, rex::kernel::xam::XamInputGetState_entry)'
    new = '''REX_HOOK_RAW(__imp__XamInputGetState) {
  M2_IMPORT_TRACE("__imp__XamInputGetState", false);
  uint32_t user = ctx.r3.u32, state = ctx.r5.u32, caller = uint32_t(ctx.lr) - 4;
  rex::ppc::HostToGuestFunction<rex::kernel::xam::XamInputGetState_entry>(ctx, base);
  uint16_t buttons = 0; uint32_t packet = 0;
  if (state && ctx.r3.u32 == 0) {
    auto* s = reinterpret_cast<rex::input::X_INPUT_STATE*>(base + state);
    buttons = s->gamepad.buttons; packet = s->packet_number;
  }
  static thread_local uint32_t previous[4] = {0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF};
  uint32_t key = uint32_t(buttons) | (ctx.r3.u32 ? 0x10000 : 0);
  if (user < 4 && previous[user] != key) {
    previous[user] = key;
    REXKRNL_INFO("M4 input_state user={} api=XamInputGetState caller={:08X} result={:08X} state={:08X} packet={} buttons={:04X}",
                 user, caller, ctx.r3.u32, state, packet, buttons);
  }
}
static rex::ppc::detail::PPCFuncRegistrar m4input("__imp__XamInputGetState", &__imp__XamInputGetState);'''
    text = subprocess.check_output(['git', '-C', str(SDK), 'show', 'HEAD:src/kernel/xam/xam_input.cpp']).decode()
    p.write_text(replace_once(text, old, new))
    # A tap can be shorter than one guest polling interval (demonstrated by
    # native down/up events in the same millisecond). Retain discrete button
    # presses for one successful state sample; axes/held keys stay unchanged.
    p = SDK / 'src/input/mnk/mnk_input_driver.cpp'
    text = p.read_text()
    mappings = re.findall(r'if \(IsBindPressed\(key_down_, REXCVAR_GET\((keybind_\w+)\)\)\)\s+buttons \|= (X_INPUT_GAMEPAD_\w+);', text)
    assert len(mappings) == 15, len(mappings)
    pending = ''.join(f'  if (IsBindPressed(key_down_, REXCVAR_GET({bind}))) pending_buttons_ |= {button};\n'
                      for bind, button in mappings)
    text = replace_once(text, '  SetKeyState(vk, true);', '  SetKeyState(vk, true);\n' + pending)
    text = replace_once(text, '    out_state->gamepad.buttons = buttons;',
                        '    out_state->gamepad.buttons = buttons | pending_buttons_;\n    pending_buttons_ = 0;')
    text = replace_once(text, '    std::memset(key_down_, 0, sizeof(key_down_));',
                        '    std::memset(key_down_, 0, sizeof(key_down_));\n    pending_buttons_ = 0;')
    p.write_text(text)
    patch('include/rex/input/mnk/mnk_input_driver.h', [(
        '  bool key_down_[256] = {};', '  bool key_down_[256] = {};\n  uint16_t pending_buttons_ = 0;')])

if __name__ == '__main__':
    apply()
