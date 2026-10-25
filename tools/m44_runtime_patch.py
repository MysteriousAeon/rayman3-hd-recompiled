"""Replay after the M36 patch at the same pin: optional gameplay voice subtitles (M44, D-081; experimental).

`tools/m44_gameplay_subtitles.h`: with R3HD_GAMEPLAY_SUBTITLES=all, the VdSwap export stores 0 in the title's
gameplay-subtitle restriction word 82837348 (1 in the image, never written by the title), so the title's own
update 8212F150 shows every voiced subtitle it has started, outside cinematics too (RE_NOTES "M44"). Only while
the guest image holds the two instructions of 8212F150 that read the word. Without the variable nothing is written.
Every log carries `M44 gameplay_subtitles=original|all`; an applied run one `M44 gameplay_subtitles mode=all
state=applied` line, a refused one `state=refused_guard|refused_value`.
"""
from m8_runtime_patch import patch_once
from m16_runtime_patch import install

if __name__ == '__main__':
    install('m44_gameplay_subtitles.h')

    patch_once('src/kernel/xboxkrnl/xboxkrnl_video.cpp', [
        # (in front of the pin's own hook.h line: M24 and M31 insert their includes after the M17 / M24 lines)
        ('#include <rex/hook.h>\n', '#include <rex/m44_gameplay_subtitles.h>\n#include <rex/hook.h>\n'),
        # In front of the M24 / M17 lines: those patches must still find their own lines together on a replay.
        ('  if (m24ev::Enabled()) m24ev::Event(m24ev::kVdSwap, m24ev::ThreadKiloCyclesSinceLast());  // M24: observation only\n',
         '  // M44 (D-081): optional gameplay voice subtitles, off unless R3HD_GAMEPLAY_SUBTITLES=all.\n'
         '  m44sub::Swap(REX_KERNEL_MEMORY()->virtual_membase(), [](const char* mode, const char* state, uint32_t n) {\n'
         '    REXLOG_INFO("M44 gameplay_subtitles mode={} state={} frames={}", mode, state, n);\n'
         '  });\n'
         '  if (m24ev::Enabled()) m24ev::Event(m24ev::kVdSwap, m24ev::ThreadKiloCyclesSinceLast());  // M24: observation only\n'),
    ])

    patch_once('src/graphics/d3d12/command_processor.cpp', [
        ('#include <rex/m33_mod_overlay.h>\n', '#include <rex/m33_mod_overlay.h>\n#include <rex/m44_gameplay_subtitles.h>\n'),
        # In front of the M33 line: the M33, M26 and M23 patches still find their own lines together on a replay.
        ('  REXGPU_INFO("M33 mods={}", m33mods::Enabled() ? "plan" : "off");\n',
         '  REXGPU_INFO("M44 gameplay_subtitles={}", m44sub::ModeName());\n'
         '  REXGPU_INFO("M33 mods={}", m33mods::Enabled() ? "plan" : "off");\n'),
    ])
