"""Replay after M16 at the same pin: read-only per-frame guest trace (M17).

`tools/m17_frame_trace.h` is called once per guest frame from the VdSwap export. It does nothing unless
`R3HD_FRAME_TRACE` names an output file; then it appends the swap index, host and guest clocks and the bytes of
the guest memory ranges listed in `<output>.watch`. Guest memory is read, never written; no guest-visible value,
no scheduling and no generated code is changed. Tools: `tools/m17_frame_trace.py`.
"""
from m3_runtime_patch import SDK
from m8_runtime_patch import patch_once
from m16_runtime_patch import install

if __name__ == '__main__':
    install('m17_frame_trace.h')
    patch_once('src/kernel/xboxkrnl/xboxkrnl_video.cpp', [
        ('#include <rex/kernel/xboxkrnl/video.h>\n',
         '#include <rex/kernel/xboxkrnl/video.h>\n'
         '#include <rex/chrono/clock.h>\n'
         '#include <rex/m17_frame_trace.h>\n'),
        ('  // All of these parameters are REQUIRED.\n'
         '  assert(buffer_ptr);\n'
         '  assert(fetch_ptr);\n',
         '  // M17: read-only frame trace, off unless R3HD_FRAME_TRACE is set.\n'
         '  m17trace::Swap(REX_KERNEL_MEMORY()->virtual_membase(), rex::chrono::Clock::QueryGuestTickCount());\n'
         '  // All of these parameters are REQUIRED.\n'
         '  assert(buffer_ptr);\n'
         '  assert(fetch_ptr);\n'),
    ])
