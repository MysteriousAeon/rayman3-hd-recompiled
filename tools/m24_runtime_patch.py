"""Replay after the M23 patches at the same pin: observational host event trace (M24).

`tools/m24_event_trace.h` does nothing unless `R3HD_M24_EVENTS` names an output file; then seven call sites
append timestamped records (guest VdSwap, command-processor swap with the frame's draw / copy / clear counts,
swap-chain Present with the time spent inside it, pad button changes, vibration changes, host pipeline
creation, host texture loads). Nothing is waited on, no guest memory is read or written, no generated code is
changed and nothing is rendered or scheduled differently. Reader: `tools/m24_pause_resume.py`.
"""
from m8_runtime_patch import patch_once
from m16_runtime_patch import install

if __name__ == '__main__':
    install('m24_event_trace.h')

    patch_once('src/kernel/xboxkrnl/xboxkrnl_video.cpp', [
        ('#include <rex/m17_frame_trace.h>\n', '#include <rex/m17_frame_trace.h>\n#include <rex/m24_event_trace.h>\n'),
        # (in front of the M17 lines, not between them: the M17 patch must still find its own text on a replay)
        ('  // M17: read-only frame trace, off unless R3HD_FRAME_TRACE is set.\n',
         '  if (m24ev::Enabled()) m24ev::Event(m24ev::kVdSwap, m24ev::ThreadKiloCyclesSinceLast());  // M24: observation only\n'
         '  // M17: read-only frame trace, off unless R3HD_FRAME_TRACE is set.\n'),
    ])

    # Every kernel import wrapper: a timer object that records the call when it took 300 us or more.
    patch_once('include/rex/m2_import_trace.h', [
        ('#include <rex/ppc/context.h>\n', '#include <rex/ppc/context.h>\n#include <rex/m24_event_trace.h>\n'),
        ('      name, stub, m2_n, unsigned(ctx.lr) - 4, ctx.r3.u32, ctx.r4.u32, ctx.r5.u32, ctx.r6.u32); \\\n} while (0)\n',
         '      name, stub, m2_n, unsigned(ctx.lr) - 4, ctx.r3.u32, ctx.r4.u32, ctx.r5.u32, ctx.r6.u32); \\\n} while (0); \\\n'
         '  m24ev::ImportTimer m24_import_timer(name, unsigned(ctx.lr) - 4)\n'),
    ])

    patch_once('include/rex/m3_gpu_trace.h', [
        ('#include <rex/m11_frame_pacing.h>\n', '#include <rex/m11_frame_pacing.h>\n#include <rex/m24_event_trace.h>\n'),
        ('  uint64_t draws = c.draws, copies = c.copies, clears = c.clears;\n',
         '  uint64_t draws = c.draws, copies = c.copies, clears = c.clears;\n'
         '  m24ev::Event(m24ev::kCpSwap, uint32_t(draws - c.draws_at_swap),\n'
         '               (uint32_t(copies - c.copies_at_swap) << 16) | (uint32_t(clears - c.clears_at_swap) & 0xFFFF));\n'
         '  m24ev::FenceFrame();  // M24: closes a `M24 gpu_bound` burst (log line only)\n'),
    ])

    patch_once('src/ui/d3d12/d3d12_presenter.cpp', [
        ('#include <rex/m11_frame_pacing.h>\n', '#include <rex/m11_frame_pacing.h>\n#include <rex/m24_event_trace.h>\n'),
        ('  HRESULT present_result = paint_context_.swap_chain->Present(\n',
         '  const int64_t m24_present_start = m24ev::Enabled() ? m24ev::Now() : 0;  // M24: observation only\n'
         '  HRESULT present_result = paint_context_.swap_chain->Present(\n'),
        ('    m11pace::HostPresent();\n',
         '    m11pace::HostPresent();\n'
         '    if (m24ev::Enabled())\n'
         '      m24ev::EventAt(m24ev::kPresent, m24_present_start, m24ev::MicrosSince(m24_present_start), uint32_t(present_result));\n'),
    ])

    patch_once('src/kernel/xam/xam_input.cpp', [
        ('#include <rex/m23_haptics.h>\n', '#include <rex/m23_haptics.h>\n#include <rex/m24_event_trace.h>\n'),
        ('    if (input_state) {\n      *input_state = {};\n      input_state->packet_number = s.packet;\n',
         '    m24ev::Buttons(s.buttons, (uint32_t(s.lt) << 8) | uint32_t(s.rt));  // M24: on change, when tracing\n'
         '    if (input_state) {\n      *input_state = {};\n      input_state->packet_number = s.packet;\n'),
        ('    input_state->gamepad = {};\n  }\n  return m16_result;\n',
         '    input_state->gamepad = {};\n  }\n'
         '  if (m16_result == X_ERROR_SUCCESS && input_state)  // M24: on change, when tracing\n'
         '    m24ev::Buttons(uint16_t(input_state->gamepad.buttons),\n'
         '                   (uint32_t(uint8_t(input_state->gamepad.left_trigger)) << 8) | uint8_t(input_state->gamepad.right_trigger));\n'
         '  return m16_result;\n'),
        ('  // M23 (D-053): a hidden run answers vibration itself; no input driver is called.\n',
         '  m24ev::Vibration(uint16_t(vibration->left_motor_speed), uint16_t(vibration->right_motor_speed));  // M24: record only\n'
         '  // M23 (D-053): a hidden run answers vibration itself; no input driver is called.\n'),
    ])

    patch_once('src/graphics/d3d12/pipeline_cache.cpp', [
        # (a top-level include: the shader bytecode headers further down sit inside a namespace)
        ('#include <rex/assert.h>\n#include <rex/chrono/clock.h>\n',
         '#include <rex/assert.h>\n#include <rex/m24_event_trace.h>\n#include <rex/chrono/clock.h>\n'),
        ('  ID3D12PipelineState* state;\n  if (FAILED(device->CreateGraphicsPipelineState(&state_desc, IID_PPV_ARGS(&state)))) {\n',
         '  ID3D12PipelineState* state;\n'
         '  const int64_t m24_pipeline_start = m24ev::Enabled() ? m24ev::Now() : 0;  // M24: observation only\n'
         '  const HRESULT m24_pipeline_result = device->CreateGraphicsPipelineState(&state_desc, IID_PPV_ARGS(&state));\n'
         '  if (m24ev::Enabled()) m24ev::EventAt(m24ev::kPipeline, m24_pipeline_start, m24ev::MicrosSince(m24_pipeline_start), 0);\n'
         '  if (FAILED(m24_pipeline_result)) {\n'),
    ])

    # The title paces a frame with one WAIT_REG_MEM on a memory word (its vblank count): when the wait began, how
    # long it lasted, the reference and the first value read.
    patch_once('src/graphics/command_processor.cpp', [
        ('#include <rex/m16_vblank.h>\n', '#include <rex/m16_vblank.h>\n#include <rex/m24_event_trace.h>\n'),
        ('  bool is_memory = (wait_info & 0x10) != 0;\n\n  bool matched = false;\n  do {\n    uint32_t value = 0;\n',
         '  bool is_memory = (wait_info & 0x10) != 0;\n\n'
         '  const bool m24_record = is_memory && m24ev::Enabled();  // M24: observation only\n'
         '  const int64_t m24_wait_start = m24_record ? m24ev::Now() : 0;\n'
         '  uint32_t m24_first_value = 0;\n'
         '  bool m24_first = true;\n'
         '  bool matched = false;\n  do {\n    uint32_t value = 0;\n'),
        ('    switch (wait_info & 0x7) {\n      case 0x0:  // Never.\n        matched = false;\n',
         '    if (m24_first) {\n      m24_first = false;\n      m24_first_value = value & mask;\n    }\n'
         '    switch (wait_info & 0x7) {\n      case 0x0:  // Never.\n        matched = false;\n'),
        ('  } while (!matched);\n\n  return true;\n}\n\n'
         'bool CommandProcessor::ExecutePacketType3_REG_RMW(',
         '  } while (!matched);\n\n'
         '  if (m24_record)\n'
         '    m24ev::EventAt(m24ev::kCpWait, m24_wait_start, m24ev::MicrosSince(m24_wait_start),\n'
         '                   ((ref & 0xFFFF) << 16) | (m24_first_value & 0xFFFF));\n'
         '  return true;\n}\n\n'
         'bool CommandProcessor::ExecutePacketType3_REG_RMW('),
    ])

    # The command processor opens a frame only when the host GPU has finished the frame three back: how long
    # that wait for the Direct3D fence lasted.
    patch_once('src/graphics/d3d12/command_processor.cpp', [
        ('      PROFILE_CMD_BUFFER_STALL();\n      WaitForSingleObject(fence_completion_event_, INFINITE);\n'
         '      submission_completed_ = submission_fence_->GetCompletedValue();\n',
         '      PROFILE_CMD_BUFFER_STALL();\n'
         '      const int64_t m24_fence_start = m24ev::Now();  // M24: observation only (always: the `M24 gpu_bound` line)\n'
         '      const uint64_t m24_fence_behind = await_submission - submission_completed_;\n'
         '      WaitForSingleObject(fence_completion_event_, INFINITE);\n'
         '      m24ev::FenceWaited(m24_fence_start, uint32_t(m24_fence_behind));\n'
         '      submission_completed_ = submission_fence_->GetCompletedValue();\n'),
    ])

    patch_once('src/graphics/d3d12/texture_cache.cpp', [
        ('#include <rex/assert.h>\n#include <rex/dbg.h>\n',
         '#include <rex/assert.h>\n#include <rex/m24_event_trace.h>\n#include <rex/dbg.h>\n'),
        ('bool D3D12TextureCache::LoadTextureDataFromResidentMemoryImpl(Texture& texture, bool load_base,\n'
         '                                                              bool load_mips) {\n',
         'bool D3D12TextureCache::LoadTextureDataFromResidentMemoryImpl(Texture& texture, bool load_base,\n'
         '                                                              bool load_mips) {\n'
         '  m24ev::Event(m24ev::kTextureLoad);  // M24: off unless R3HD_M24_EVENTS is set\n'),
    ])
