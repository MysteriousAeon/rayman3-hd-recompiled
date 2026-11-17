"""Replay last in the patch chain: host display V-Sync for the D3D12 presenter (D-220).

`tools/r3hd_display_vsync.h`: with R3HD_DISPLAY_VSYNC=on (a launch-time Settings preference) the D3D12 presenter
calls Present(1, 0), reports implicit V-Sync for its paint connection (so the SDK presenter paints on the UI thread
only and stops its DXGI WaitForVBlank UI tick) and bounds the present queue with a frame-latency waitable object
(maximum latency 1, bounded wait before each paint). Without the variable the pinned presentation is unchanged:
Present(0, RESTART | ALLOW_TEARING when supported), no waitable object, no implicit V-Sync.

Observation in both modes: one start-up line per swap chain (requested mode, flags, Present arguments) and one
summary line per 600 presents (Present call time, latency wait, HRESULT classes, DXGI frame statistics).

Host presentation only: no generated code, no guest state, no change to guest vblank scheduling (M16, D-046),
the SDK's `vsync` cvar or the Vulkan presenter. Run after every other step so no earlier anchor moves.
"""
from m8_runtime_patch import patch_once
from m16_runtime_patch import install

CPP = 'src/ui/d3d12/d3d12_presenter.cpp'

if __name__ == '__main__':
    install('r3hd_display_vsync.h')

    patch_once('include/rex/ui/d3d12/d3d12_presenter.h', [
        ('    bool swap_chain_allows_tearing = false;\n',
         '    bool swap_chain_allows_tearing = false;\n'
         '    // D-220: V-Sync On only: the swap chain carries FRAME_LATENCY_WAITABLE_OBJECT and its object.\n'
         '    bool r3hd_latency_flag = false;\n'
         '    HANDLE r3hd_latency_waitable = nullptr;\n'),
    ])

    patch_once(CPP, [
        ('#include <rex/m24_event_trace.h>\n',
         '#include <rex/m24_event_trace.h>\n#include <chrono>\n#include <rex/r3hd_display_vsync.h>\n'),
        # A same-size reconnection keeps reporting the requested mode (never silently hands painting back to
        # the guest-output thread while Present waits for a vertical blank).
        ('      is_vsync_implicit_out = false;\n'
         '      return SurfacePaintConnectResult::kSuccessUnchanged;\n',
         '      is_vsync_implicit_out = r3hdvsync::Enabled();  // D-220\n'
         '      return SurfacePaintConnectResult::kSuccessUnchanged;\n'),
        # ResizeBuffers must repeat the creation flags; Off reproduces the pinned value.
        ('        paint_context_.swap_chain_allows_tearing ? DXGI_SWAP_CHAIN_FLAG_ALLOW_TEARING : 0));\n',
         '        UINT(r3hdvsync::SwapChainFlags(paint_context_.r3hd_latency_flag,\n'
         '                                       paint_context_.swap_chain_allows_tearing))));  // D-220\n'),
        ('      swap_chain_desc.Flags |= DXGI_SWAP_CHAIN_FLAG_ALLOW_TEARING;\n'
         '    }\n',
         '      swap_chain_desc.Flags |= DXGI_SWAP_CHAIN_FLAG_ALLOW_TEARING;\n'
         '    }\n'
         '    // D-220: V-Sync On bounds the present queue with a frame-latency object (Off: unchanged).\n'
         '    if (r3hdvsync::Enabled()) {\n'
         '      swap_chain_desc.Flags |= DXGI_SWAP_CHAIN_FLAG_FRAME_LATENCY_WAITABLE_OBJECT;\n'
         '    }\n'),
        ('    paint_context_.swap_chain_allows_tearing =\n'
         '        (swap_chain_desc.Flags & DXGI_SWAP_CHAIN_FLAG_ALLOW_TEARING) != 0;\n',
         '    paint_context_.swap_chain_allows_tearing =\n'
         '        (swap_chain_desc.Flags & DXGI_SWAP_CHAIN_FLAG_ALLOW_TEARING) != 0;\n'
         '    // D-220: requested presentation mode of this swap chain.\n'
         '    static_assert(r3hdvsync::kPresentRestart == DXGI_PRESENT_RESTART);\n'
         '    static_assert(r3hdvsync::kPresentAllowTearing == DXGI_PRESENT_ALLOW_TEARING);\n'
         '    static_assert(r3hdvsync::kSwapChainAllowTearing == DXGI_SWAP_CHAIN_FLAG_ALLOW_TEARING);\n'
         '    static_assert(r3hdvsync::kSwapChainLatencyWaitable == DXGI_SWAP_CHAIN_FLAG_FRAME_LATENCY_WAITABLE_OBJECT);\n'
         '    paint_context_.r3hd_latency_flag =\n'
         '        (swap_chain_desc.Flags & DXGI_SWAP_CHAIN_FLAG_FRAME_LATENCY_WAITABLE_OBJECT) != 0;\n'
         '    HRESULT r3hd_latency_hr = S_FALSE;\n'
         '    if (paint_context_.r3hd_latency_flag) {\n'
         '      r3hd_latency_hr = paint_context_.swap_chain->SetMaximumFrameLatency(r3hdvsync::kMaxFrameLatency);\n'
         '      if (SUCCEEDED(r3hd_latency_hr)) {\n'
         '        paint_context_.r3hd_latency_waitable = paint_context_.swap_chain->GetFrameLatencyWaitableObject();\n'
         '      }\n'
         '    }\n'
         '    {\n'
         '      const r3hdvsync::PresentArgs r3hd_args =\n'
         '          r3hdvsync::Choose(r3hdvsync::Enabled(), paint_context_.swap_chain_allows_tearing);\n'
         '      REXLOG_INFO(\n'
         '          "R3HD display_vsync={} swapchain_flags=0x{:X} tearing_supported={} sync_interval={} "\n'
         '          "present_flags=0x{:X} max_frame_latency={} latency_hr={:08X} waitable={} implicit_vsync={}",\n'
         '          r3hdvsync::Enabled() ? "on" : "off", unsigned(swap_chain_desc.Flags), dxgi_supports_tearing_ ? 1 : 0,\n'
         '          r3hd_args.sync_interval, r3hd_args.flags,\n'
         '          paint_context_.r3hd_latency_flag ? r3hdvsync::kMaxFrameLatency : 0u, uint32_t(r3hd_latency_hr),\n'
         '          paint_context_.r3hd_latency_waitable ? 1 : 0, r3hdvsync::Enabled() ? 1 : 0);\n'
         '    }\n'),
        ('  is_vsync_implicit_out = false;\n'
         '  return SurfacePaintConnectResult::kSuccess;\n',
         '  is_vsync_implicit_out = r3hdvsync::Enabled();  // D-220\n'
         '  return SurfacePaintConnectResult::kSuccess;\n'),
        ('  swap_chain.Reset();\n'
         '  swap_chain_allows_tearing = false;\n',
         '  if (r3hd_latency_waitable) {  // D-220\n'
         '    CloseHandle(r3hd_latency_waitable);\n'
         '    r3hd_latency_waitable = nullptr;\n'
         '  }\n'
         '  r3hd_latency_flag = false;\n'
         '  swap_chain.Reset();\n'
         '  swap_chain_allows_tearing = false;\n'),
        # Every call of this function reaches the single Present below (no early return), so a wait that
        # took a latency count is always followed by the present that returns it.
        ('Presenter::PaintResult D3D12Presenter::PaintAndPresentImpl(bool execute_ui_drawers) {\n',
         'Presenter::PaintResult D3D12Presenter::PaintAndPresentImpl(bool execute_ui_drawers) {\n'
         '  // D-220: V-Sync On waits (bounded) until the queue has room for this frame. Off: no object, no wait.\n'
         '  int64_t r3hd_wait_us = 0;\n'
         '  bool r3hd_wait_timeout = false;\n'
         '  if (paint_context_.r3hd_latency_waitable) {\n'
         '    const auto r3hd_wait_start = std::chrono::steady_clock::now();\n'
         '    r3hd_wait_timeout = WaitForSingleObjectEx(paint_context_.r3hd_latency_waitable,\n'
         '                                              r3hdvsync::kLatencyWaitTimeoutMs, TRUE) == WAIT_TIMEOUT;\n'
         '    r3hd_wait_us = std::chrono::duration_cast<std::chrono::microseconds>(\n'
         '                       std::chrono::steady_clock::now() - r3hd_wait_start).count();\n'
         '  }\n'),
        ('  HRESULT present_result = paint_context_.swap_chain->Present(\n'
         '      0, DXGI_PRESENT_RESTART |\n'
         '             (paint_context_.swap_chain_allows_tearing ? DXGI_PRESENT_ALLOW_TEARING : 0));\n',
         '  // D-220: Off = the pinned call above; On = Present(1, 0).\n'
         '  const r3hdvsync::PresentArgs r3hd_args =\n'
         '      r3hdvsync::Choose(r3hdvsync::Enabled(), paint_context_.swap_chain_allows_tearing);\n'
         '  const auto r3hd_call_start = std::chrono::steady_clock::now();\n'
         '  HRESULT present_result =\n'
         '      paint_context_.swap_chain->Present(UINT(r3hd_args.sync_interval), UINT(r3hd_args.flags));\n'
         '  {\n'
         '    static r3hdvsync::Stats r3hd_stats;  // touched only by the presenting thread of the mode\n'
         '    r3hdvsync::Summary r3hd_sum;\n'
         '    const int64_t r3hd_call_us = std::chrono::duration_cast<std::chrono::microseconds>(\n'
         '                                     std::chrono::steady_clock::now() - r3hd_call_start).count();\n'
         '    const int r3hd_class = present_result == DXGI_STATUS_OCCLUDED ? 1 : FAILED(present_result) ? 2 : 0;\n'
         '    if (r3hdvsync::Add(r3hd_stats, r3hd_call_us, r3hd_wait_us, r3hd_wait_timeout, r3hd_class, r3hd_sum)) {\n'
         '      DXGI_FRAME_STATISTICS r3hd_fs = {};\n'
         '      const HRESULT r3hd_fs_hr = paint_context_.swap_chain->GetFrameStatistics(&r3hd_fs);\n'
         '      UINT r3hd_last_present = 0;\n'
         '      paint_context_.swap_chain->GetLastPresentCount(&r3hd_last_present);\n'
         '      REXLOG_INFO(\n'
         '          "R3HD present_stats window={} n={} vsync={} sync_interval={} flags=0x{:X} call_p50_us={} "\n'
         '          "call_p95_us={} call_max_us={} wait_p50_us={} wait_p95_us={} wait_max_us={} wait_timeouts={} "\n'
         '          "occluded={} failed={} fs_hr={:08X} fs_present_count={} fs_present_refresh={} "\n'
         '          "fs_sync_refresh={} fs_sync_qpc={} last_present_count={}",\n'
         '          r3hd_sum.window, r3hdvsync::kWindow, r3hdvsync::Enabled() ? "on" : "off", r3hd_args.sync_interval,\n'
         '          r3hd_args.flags, r3hd_sum.call_p50, r3hd_sum.call_p95, r3hd_sum.call_max, r3hd_sum.wait_p50,\n'
         '          r3hd_sum.wait_p95, r3hd_sum.wait_max, r3hd_sum.timeouts, r3hd_sum.occluded, r3hd_sum.failed,\n'
         '          uint32_t(r3hd_fs_hr), r3hd_fs.PresentCount, r3hd_fs.PresentRefreshCount, r3hd_fs.SyncRefreshCount,\n'
         '          int64_t(r3hd_fs.SyncQPCTime.QuadPart), r3hd_last_present);\n'
         '    }\n'
         '  }\n'),
    ])
