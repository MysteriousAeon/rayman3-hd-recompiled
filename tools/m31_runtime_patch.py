"""Replay after the M26 patch at the same pin: window size apart from the guest video mode, bounded playtest logs
(M31, D-068).

1. `src/kernel/xboxkrnl/xboxkrnl_video.cpp`: the SDK makes a non-default `window_width` / `window_height` the guest
   video mode as well (VdQueryVideoMode). The title always renders a 1280x720 frame (E-82..E-84), so a window of
   another size must not change what the title is told: the window size no longer feeds the video mode; the
   `video_mode_*` settings and the resolution preset still do. One `M31 video_mode=` line records the answer.
2. `src/graphics/pipeline/texture/cache.cpp` (rebuilt from the pin by m4_runtime_patch.py on every replay): the
   SDK's "invalid type" texture-fetch warning and the M4 `invalid_fetch` line are sampled in a standard-diagnostics
   playtest session (`tools/m31_diagnostics.h`: the first 8, then every 1000th with its count). Hidden runs and
   `-Diagnostics detailed` keep every line.

Host-only: no generated code, no guest memory write, no scheduling change.
"""
from m8_runtime_patch import patch_once
from m16_runtime_patch import install

VIDEO = 'src/kernel/xboxkrnl/xboxkrnl_video.cpp'

if __name__ == '__main__':
    install('m31_diagnostics.h')

    patch_once(VIDEO, [
        ('#include <rex/m24_event_trace.h>\n', '#include <rex/m24_event_trace.h>\n#include <mutex>\n'),
        ('    if (rex::cvar::HasNonDefaultValue("window_width") && REXCVAR_GET(window_width) > 0) {\n'
         '      configured_width = REXCVAR_GET(window_width);\n'
         '    } else {\n',
         '    // M31 (D-068): the window size is not the guest video mode (the title renders 1280x720 either way).\n'
         '    {\n'),
        ('    if (rex::cvar::HasNonDefaultValue("window_height") && REXCVAR_GET(window_height) > 0) {\n'
         '      configured_height = REXCVAR_GET(window_height);\n'
         '    } else {\n',
         '    // M31 (D-068): the window size is not the guest video mode.\n'
         '    {\n'),
        ('  video_mode->unknown_0x01 = 0x01;\n',
         '  video_mode->unknown_0x01 = 0x01;\n'
         '  static std::once_flag m31_logged;\n'
         '  std::call_once(m31_logged, [&] {\n'
         '    REXKRNL_INFO("M31 video_mode={}x{} window_cvar={}x{} (the window size does not set the video mode)",\n'
         '                 display_width, display_height, REXCVAR_GET(window_width), REXCVAR_GET(window_height));\n'
         '  });\n'),
    ])

    patch_once('src/graphics/pipeline/texture/cache.cpp', [
        ('#include <rex/m3_gpu_trace.h>\n', '#include <rex/m3_gpu_trace.h>\n#include <rex/m31_diagnostics.h>\n'),
        ('    if (fetch.type == xenos::FetchConstantType::kInvalidTexture)\n      REXGPU_INFO("M4 invalid_fetch ',
         '    // M31 (D-068): sampled in a standard-diagnostics playtest session (tools/m31_diagnostics.h).\n'
         '    static std::atomic<uint64_t> m31_invalid_info{0};\n'
         '    uint64_t m31_info_n = 0;\n'
         '    if (fetch.type == xenos::FetchConstantType::kInvalidTexture && m31diag::Sample(m31_invalid_info, &m31_info_n)'
         ' && m31diag::Sampled(m31_info_n))\n'
         '      REXGPU_INFO("M31 sampled invalid_fetch count={} (first {}, then every {})", m31_info_n, m31diag::kFirst,\n'
         '                  m31diag::kEvery);\n'
         '    if (fetch.type == xenos::FetchConstantType::kInvalidTexture && (!m31diag::Quiet() || m31_info_n <= m31diag::kFirst))\n'
         '      REXGPU_INFO("M4 invalid_fetch '),
        ('      if (REXCVAR_GET(gpu_allow_invalid_fetch_constants)) {\n'
         '        break;\n'
         '      }\n'
         '      REXGPU_WARN(\n',
         '      if (REXCVAR_GET(gpu_allow_invalid_fetch_constants)) {\n'
         '        break;\n'
         '      }\n'
         '      {  // M31 (D-068): sampled in a standard-diagnostics playtest session (tools/m31_diagnostics.h).\n'
         '        static std::atomic<uint64_t> m31_invalid_warn{0};\n'
         '        uint64_t m31_warn_n = 0;\n'
         '        if (!m31diag::Sample(m31_invalid_warn, &m31_warn_n)) return;\n'
         '        if (m31diag::Sampled(m31_warn_n))\n'
         '          REXGPU_INFO("M31 sampled invalid_type_warning count={} (first {}, then every {})", m31_warn_n,\n'
         '                      m31diag::kFirst, m31diag::kEvery);\n'
         '      }\n'
         '      REXGPU_WARN(\n'),
    ])
