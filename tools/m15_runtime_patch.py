"""Replay after M12 at the same pin: resolution-chain instrumentation (M15, D-042).

The SDK already carries the draw resolution scale of its Xenia-derived renderer (`--resolution_scale=N`): host
render targets, viewports, scissors, resolves and the guest output image are N times the guest size along each
axis while every guest-visible register and address keeps its 1280x720 value. M15 changes no rendering code; this
patch only makes each link of the chain visible in the log so a run can be checked mechanically
(`tools/m15_resolution_check.py`):

  M15 window       SDL window size in points and pixels, fullscreen state, desktop display mode, pixel density
  M15 draw_scale   the scale the renderer really uses after the device clamp
  M15 rt_create    one line per host render target: guest size and host size, colour or depth, format, MSAA
  M15 viewport     host viewport and scissor of a draw, once per distinct (surface, viewport, scissor) tuple
  M15 present      guest output image -> swap chain: sizes and the rectangle it is painted into, on change

All lines are observational and low volume (each is logged on first occurrence or on change). Host-only: no
guest memory, no guest-visible value and no generated code changes.
"""
from m8_runtime_patch import patch_once

if __name__ == '__main__':
    patch_once('src/ui/window_sdl.cpp', [
        ('  SDL_GetWindowSizeInPixels(sdl_window_, &pixel_width, &pixel_height);\n'
         '  WindowDestructionReceiver destruction_receiver(this);\n'
         '  OnActualSizeUpdate(uint32_t(pixel_width), uint32_t(pixel_height), destruction_receiver);\n'
         '  if (destruction_receiver.IsWindowDestroyed()) {\n'
         '    return true;\n',
         '  SDL_GetWindowSizeInPixels(sdl_window_, &pixel_width, &pixel_height);\n'
         '  {\n'
         '    // M15: window, fullscreen state and display mode as SDL reports them at open.\n'
         '    int m15_w = 0, m15_h = 0;\n'
         '    SDL_GetWindowSize(sdl_window_, &m15_w, &m15_h);\n'
         '    const SDL_DisplayMode* m15_desktop =\n'
         '        SDL_GetDesktopDisplayMode(SDL_GetDisplayForWindow(sdl_window_));\n'
         '    REXLOG_INFO("M15 window fullscreen_requested={} sdl_fullscreen={} exclusive_mode={} size={}x{} "\n'
         '                "pixels={}x{} desktop_mode={}x{}@{:.2f} pixel_density={:.2f} display_scale={:.2f}",\n'
         '                IsFullscreen(), (SDL_GetWindowFlags(sdl_window_) & SDL_WINDOW_FULLSCREEN) != 0,\n'
         '                SDL_GetWindowFullscreenMode(sdl_window_) != nullptr, m15_w, m15_h, pixel_width,\n'
         '                pixel_height, m15_desktop ? m15_desktop->w : 0, m15_desktop ? m15_desktop->h : 0,\n'
         '                m15_desktop ? m15_desktop->refresh_rate : 0.0f,\n'
         '                SDL_GetWindowPixelDensity(sdl_window_), SDL_GetWindowDisplayScale(sdl_window_));\n'
         '  }\n'
         '  WindowDestructionReceiver destruction_receiver(this);\n'
         '  OnActualSizeUpdate(uint32_t(pixel_width), uint32_t(pixel_height), destruction_receiver);\n'
         '  if (destruction_receiver.IsWindowDestroyed()) {\n'
         '    return true;\n'),
    ])
    patch_once('src/graphics/d3d12/command_processor.cpp', [
        ('  shared_memory_ = std::make_unique<D3D12SharedMemory>(*this, *memory_);\n',
         '  // M15: the scale in effect after the configuration and device clamps.\n'
         '  REXGPU_INFO("M15 draw_scale x={} y={} as_requested={}", draw_resolution_scale_x,\n'
         '              draw_resolution_scale_y, draw_resolution_scale_not_clamped);\n'
         '\n'
         '  shared_memory_ = std::make_unique<D3D12SharedMemory>(*this, *memory_);\n'),
        ('  scissor.extent[1] *= draw_resolution_scale_y;\n',
         '  scissor.extent[1] *= draw_resolution_scale_y;\n'
         '  {\n'
         '    // M15: host viewport and scissor, once per distinct (surface, viewport, scissor) tuple.\n'
         '    static uint64_t m15_seen[96];\n'
         '    static unsigned m15_seen_count = 0;\n'
         '    uint32_t m15_surface = regs.Get<reg::RB_SURFACE_INFO>().value;\n'
         '    uint64_t m15_key = m15_surface;\n'
         '    for (uint32_t m15_v : {viewport_info.xy_offset[0], viewport_info.xy_offset[1],\n'
         '                           viewport_info.xy_extent[0], viewport_info.xy_extent[1], scissor.offset[0],\n'
         '                           scissor.offset[1], scissor.extent[0], scissor.extent[1]}) {\n'
         '      m15_key = (m15_key ^ m15_v) * 0x100000001B3ull;\n'
         '    }\n'
         '    bool m15_new = m15_seen_count < 96;\n'
         '    for (unsigned i = 0; m15_new && i < m15_seen_count; ++i) m15_new = m15_seen[i] != m15_key;\n'
         '    if (m15_new) {\n'
         '      m15_seen[m15_seen_count++] = m15_key;\n'
         '      REXGPU_INFO("M15 viewport draw={} surface_info={:08X} guest_pitch={} msaa={} host_viewport={},{} {}x{} "\n'
         '                  "host_scissor={},{} {}x{} scale={}x{}",\n'
         '                  m3gpu::counters().draws.load(), m15_surface, m15_surface & 0x3FFF,\n'
         '                  (m15_surface >> 16) & 3, viewport_info.xy_offset[0], viewport_info.xy_offset[1],\n'
         '                  viewport_info.xy_extent[0], viewport_info.xy_extent[1], scissor.offset[0],\n'
         '                  scissor.offset[1], scissor.extent[0], scissor.extent[1], draw_resolution_scale_x,\n'
         '                  draw_resolution_scale_y);\n'
         '    }\n'
         '  }\n'),
    ])
    patch_once('src/graphics/d3d12/render_target_cache.cpp', [
        ('    resource->SetName(reinterpret_cast<LPCWSTR>(resource_name.c_str()));\n'
         '  }\n',
         '    resource->SetName(reinterpret_cast<LPCWSTR>(resource_name.c_str()));\n'
         '  }\n'
         '  // M15: one line per host render target (guest size against host size).\n'
         '  REXGPU_INFO("M15 rt_create kind={} guest_format={} dxgi_format={} msaa={} guest={}x{} host={}x{} "\n'
         '              "samples={} scale={}x{}",\n'
         '              key.is_depth ? "depth" : "color", uint32_t(key.resource_format),\n'
         '              uint32_t(resource_desc.Format), uint32_t(key.msaa_samples), key.GetWidth(),\n'
         '              GetRenderTargetHeight(key.pitch_tiles_at_32bpp, key.msaa_samples),\n'
         '              uint64_t(resource_desc.Width), uint32_t(resource_desc.Height),\n'
         '              uint32_t(resource_desc.SampleDesc.Count), draw_resolution_scale_x(),\n'
         '              draw_resolution_scale_y());\n'),
    ])
    patch_once('src/ui/presenter.cpp', [
        ('  uint32_t output_width_clamped = std::min(output_width, max_rt_width);\n',
         '  {\n'
         '    // M15: where the guest output image lands in the swap chain, logged when it changes.\n'
         '    static std::atomic<uint64_t> m15_last{0};\n'
         '    uint64_t m15_key = properties.frontbuffer_width;\n'
         '    for (uint32_t m15_v : {properties.frontbuffer_height, host_rt_width, host_rt_height,\n'
         '                           uint32_t(flow.output_x), uint32_t(flow.output_y), output_width,\n'
         '                           output_height}) {\n'
         '      m15_key = (m15_key ^ m15_v) * 0x100000001B3ull;\n'
         '    }\n'
         '    if (m15_last.exchange(m15_key) != m15_key) {\n'
         '      REXLOG_INFO("M15 present guest_output={}x{} aspect={}:{} swap_chain={}x{} surface={}x{} "\n'
         '                  "output_rect={},{} {}x{} ratio_x={:.3f} ratio_y={:.3f}",\n'
         '                  properties.frontbuffer_width, properties.frontbuffer_height,\n'
         '                  properties.display_aspect_ratio_x, properties.display_aspect_ratio_y, host_rt_width,\n'
         '                  host_rt_height, surface_width_in_paint_connection_,\n'
         '                  surface_height_in_paint_connection_, flow.output_x, flow.output_y, output_width,\n'
         '                  output_height, double(output_width) / double(properties.frontbuffer_width),\n'
         '                  double(output_height) / double(properties.frontbuffer_height));\n'
         '    }\n'
         '  }\n'
         '  uint32_t output_width_clamped = std::min(output_width, max_rt_width);\n'),
    ])
