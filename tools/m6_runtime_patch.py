"""Replay after M5 at the same pin: hidden window, scoped XAM controller, observations."""
from m3_runtime_patch import SDK, ROOT, patch
import shutil

if __name__ == '__main__':
    shutil.copyfile(ROOT/'tools/m6_test_input.h', SDK/'include/rex/m6_test_input.h')
    shutil.copyfile(ROOT/'tools/m6_audio_capture.h', SDK/'include/rex/m6_audio_capture.h')
    shutil.copyfile(ROOT/'tools/m6_frame_capture.h', SDK/'include/rex/m6_frame_capture.h')
    # M6 hidden runs suppress every legacy M3/M5 screenshot trigger. A manual
    # monotonically increasing request file is polled on the present thread;
    # M3 calls CaptureAt twice per swap, so the M6 header caches that decision.
    patch('include/rex/m3_gpu_trace.h', [
        ('#include <rex/ui/presenter.h>', '#include <rex/ui/presenter.h>\n#include <rex/m6_frame_capture.h>'),
        ('''  if (FILE* f = std::fopen(name, "wb")) { std::fwrite(host, 4, dwords, f); std::fclose(f); }''',
         '''  // Hidden traversal retains shader metadata without game-derived dumps.
  if (FILE* f = std::getenv("R3HD_NONINTRUSIVE") ? nullptr : std::fopen(name, "wb")) {
    std::fwrite(host, 4, dwords, f); std::fclose(f);
  }'''),
        ('''inline bool CaptureAt(uint64_t swap) {
  if (std::getenv("R3HD_M5_CAPTURE") && swap % 300 == 0) return true;
  switch (swap) { case 2: case 30: case 120: case 300: case 600: case 900: case 1500: case 2400: case 3600: case 5400: return true; }
  return false;
}''', '''inline bool CaptureAt(uint64_t swap) {
  if (std::getenv("R3HD_NONINTRUSIVE")) return m6frame::CaptureAt(swap);
  if (std::getenv("R3HD_M5_CAPTURE") && swap % 300 == 0) return true;
  switch (swap) { case 2: case 30: case 120: case 300: case 600: case 900: case 1500: case 2400: case 3600: case 5400: return true; }
  return false;
}'''),
        ('''inline void WriteBmp(const char* name, const rex::ui::RawImage& image) {
  FILE* f = std::fopen(name, "wb");
  if (!f) return;
  uint32_t w = image.width, h = image.height, row = w * 3 + ((4 - (w * 3) % 4) % 4), size = 54 + row * h;
  uint8_t header[54] = {'B', 'M'};
  auto put = [&](int at, uint32_t v) { std::memcpy(header + at, &v, 4); };
  put(2, size); put(10, 54); put(14, 40); put(18, w); put(22, h);
  header[26] = 1; header[28] = 24; put(34, row * h);
  std::fwrite(header, 1, 54, f);
  std::vector<uint8_t> line(row);
  for (uint32_t y = 0; y < h; ++y) {
    const uint8_t* src = image.data.data() + size_t(h - 1 - y) * image.stride;
    for (uint32_t x = 0; x < w; ++x) { line[x * 3] = src[x * 4 + 2]; line[x * 3 + 1] = src[x * 4 + 1]; line[x * 3 + 2] = src[x * 4]; }
    std::fwrite(line.data(), 1, row, f);
  }
  std::fclose(f);
}''', '''inline bool WriteBmp(const char* name, const rex::ui::RawImage& image) {
  FILE* f = std::fopen(name, "wb");
  if (!f) return false;
  uint32_t w = image.width, h = image.height, row = w * 3 + ((4 - (w * 3) % 4) % 4), size = 54 + row * h;
  uint8_t header[54] = {'B', 'M'};
  auto put = [&](int at, uint32_t v) { std::memcpy(header + at, &v, 4); };
  put(2, size); put(10, 54); put(14, 40); put(18, w); put(22, h);
  header[26] = 1; header[28] = 24; put(34, row * h);
  bool ok = std::fwrite(header, 1, 54, f) == 54;
  std::vector<uint8_t> line(row);
  for (uint32_t y = 0; y < h; ++y) {
    const uint8_t* src = image.data.data() + size_t(h - 1 - y) * image.stride;
    for (uint32_t x = 0; x < w; ++x) { line[x * 3] = src[x * 4 + 2]; line[x * 3 + 1] = src[x * 4 + 1]; line[x * 3 + 2] = src[x * 4]; }
    ok = std::fwrite(line.data(), 1, row, f) == row && ok;
  }
  return std::fclose(f) == 0 && ok;
}'''),
        ('''    REXGPU_INFO("M3 frame_capture swap={} result=unavailable", n);''', '''    if (std::getenv("R3HD_NONINTRUSIVE")) m6frame::ReadbackUnavailable(n);
    else REXGPU_INFO("M3 frame_capture swap={} result=unavailable", n);'''),
        ('''  WriteBmp(name, image);
  REXGPU_INFO("M3 frame_capture swap={} file={} size={}x{} mean_channel={:.2f} nonblack_fraction={:.4f} pixels_vary={} sampled_distinct_colors={}",
              n, name, image.width, image.height, double(sum) / double(pixels * 3), double(nonblack) / double(pixels), varies, colors.size());''', '''  if (std::getenv("R3HD_NONINTRUSIVE")) {
    bool saved = m6frame::SaveIfNew(image, name, n,
        [](const char* path, const rex::ui::RawImage& frame) { return WriteBmp(path, frame); });
    if (saved)
      REXGPU_INFO("M3 frame_capture swap={} file={} size={}x{} mean_channel={:.2f} nonblack_fraction={:.4f} pixels_vary={} sampled_distinct_colors={}",
                  n, name, image.width, image.height, double(sum) / double(pixels * 3), double(nonblack) / double(pixels), varies, colors.size());
  } else {
    (void)WriteBmp(name, image);
    REXGPU_INFO("M3 frame_capture swap={} file={} size={}x{} mean_channel={:.2f} nonblack_fraction={:.4f} pixels_vary={} sampled_distinct_colors={}",
                n, name, image.width, image.height, double(sum) / double(pixels * 3), double(nonblack) / double(pixels), varies, colors.size());
  }''')
    ], from_head=False)
    patch('src/core/system_win.cpp', [
        ('#include <rex/string.h>', '#include <rex/string.h>\n#include <rex/logging.h>\n#include <cstdlib>'),
        ('  UINT flags = MB_OK | MB_TOPMOST | MB_SETFOREGROUND;', '''  if (std::getenv("R3HD_NONINTRUSIVE")) {
    REXLOG_ERROR("M6 native_dialog suppressed=true message={}", message);
    return; // The caller still handles the initialization failure; never activate a dialog.
  }
  UINT flags = MB_OK | MB_TOPMOST | MB_SETFOREGROUND;''')
    ])
    patch('src/ui/window_sdl.cpp', [
        ('#include <rex/ui/window_sdl.h>', '#include <rex/ui/window_sdl.h>\n#include <cstdlib>'),
        ('  SDL_ShowWindow(sdl_window_);', '''  if (!std::getenv("R3HD_NONINTRUSIVE")) SDL_ShowWindow(sdl_window_);
  else REXLOG_INFO("M6 window hidden=true show=false");'''),
        ('void WindowSDL::FocusImpl() {', '''void WindowSDL::FocusImpl() {
  if (std::getenv("R3HD_NONINTRUSIVE")) { REXLOG_INFO("M6 focus_request suppressed=true"); return; }'''),
        ('bool WindowSDL::SetRelativeMouseMode(bool enable) {', 'bool WindowSDL::SetRelativeMouseMode(bool enable) {\n  if (std::getenv("R3HD_NONINTRUSIVE")) return false;'),
        ('bool WindowSDL::WarpMouseToCenter(int32_t& x_out, int32_t& y_out) {', 'bool WindowSDL::WarpMouseToCenter(int32_t& x_out, int32_t& y_out) {\n  if (std::getenv("R3HD_NONINTRUSIVE")) return false;'),
        ('void WindowSDL::ApplyCursorVisibilityNow() {', 'void WindowSDL::ApplyCursorVisibilityNow() {\n  if (std::getenv("R3HD_NONINTRUSIVE")) return;'),
        ('  if (IsFullscreen()) {', '  if (IsFullscreen() && !std::getenv("R3HD_NONINTRUSIVE")) {'),
        ('  SDL_SetWindowFullscreen(sdl_window_, IsFullscreen());', '  if (!std::getenv("R3HD_NONINTRUSIVE")) SDL_SetWindowFullscreen(sdl_window_, IsFullscreen());')
    ])
    patch('src/kernel/xam/xam_input.cpp', [
        ('#include <rex/input/input.h>', '#include <rex/input/input.h>\n#include <rex/m6_test_input.h>'),
        ('  return is->GetState(actual_user_index, input_state);', '''  if (m6input::Enabled()) {
    if (actual_user_index != 0) return X_ERROR_DEVICE_NOT_CONNECTED;
    auto s = m6input::Sample(bool(input_state));
    if (input_state) {
      *input_state = {};
      input_state->packet_number = s.packet;
      input_state->gamepad.buttons = s.buttons;
      input_state->gamepad.thumb_lx = s.lx; input_state->gamepad.thumb_ly = s.ly;
      input_state->gamepad.thumb_rx = s.rx; input_state->gamepad.thumb_ry = s.ry;
      input_state->gamepad.left_trigger = s.lt; input_state->gamepad.right_trigger = s.rt;
    }
    return X_ERROR_SUCCESS;
  }
  return is->GetState(actual_user_index, input_state);'''),
        ('  REXKRNL_TRACE("[XAM] XamInputGetCapabilities called:', '''  if (m6input::Enabled()) {
    if (!caps) return X_ERROR_BAD_ARGUMENTS;
    if ((flags & 0xFF) && !(flags & XINPUT_FLAG_GAMEPAD)) return X_ERROR_DEVICE_NOT_CONNECTED;
    if (uint32_t(user_index) != 0 && (user_index & 0xFF) != 0xFF && !(flags & XINPUT_FLAG_ANY_USER)) return X_ERROR_DEVICE_NOT_CONNECTED;
    *caps = {}; caps->type = 1; caps->sub_type = 1;
    return X_ERROR_SUCCESS;
  }
  REXKRNL_TRACE("[XAM] XamInputGetCapabilities called:''')
        ,('  return is->GetKeystroke(actual_user_index, flags, keystroke);', '''  // M6 state-only test controller: desktop/physical keystrokes cannot leak in.
  if (m6input::Enabled()) return actual_user_index == 0 ? X_ERROR_EMPTY : X_ERROR_DEVICE_NOT_CONNECTED;
  return is->GetKeystroke(actual_user_index, flags, keystroke);''')
        ,('  auto result = is->GetKeystroke(user_index, flags, keystroke);', '''  if (m6input::Enabled()) return user_index == 0 ? X_ERROR_EMPTY : X_ERROR_DEVICE_NOT_CONNECTED;
  auto result = is->GetKeystroke(user_index, flags, keystroke);''')
    ], from_head=False)
    patch('src/kernel/xam/xam_content.cpp', [
        ('REX_EXPORT(__imp__XamContentGetLicenseMask, rex::kernel::xam::XamContentGetLicenseMask_entry)', '''REX_HOOK_RAW(__imp__XamContentGetLicenseMask) {
  M2_IMPORT_TRACE("__imp__XamContentGetLicenseMask", false);
  uint32_t ptr = ctx.r3.u32, overlapped = ctx.r4.u32, caller = uint32_t(ctx.lr) - 4;
  rex::ppc::HostToGuestFunction<rex::kernel::xam::XamContentGetLicenseMask_entry>(ctx, base);
  REXLOG_INFO("M6 license caller={:08X} mask_ptr={:08X} overlapped={:08X} result={:08X} mask={:08X}", caller, ptr, overlapped, ctx.r3.u32, ptr ? uint32_t(*reinterpret_cast<rex::be<uint32_t>*>(base + ptr)) : 0);
}
static rex::ppc::detail::PPCFuncRegistrar m6license("__imp__XamContentGetLicenseMask", &__imp__XamContentGetLicenseMask);''')
    ])
    for name in ('XamContentCreateEx', 'XamContentFlush', 'XamContentClose'):
        patch('src/kernel/xam/xam_content.cpp', [(
            f'REX_EXPORT(__imp__{name}, rex::kernel::xam::{name}_entry)',
            f'''REX_HOOK_RAW(__imp__{name}) {{
  M2_IMPORT_TRACE("__imp__{name}", false);
  uint32_t caller = uint32_t(ctx.lr)-4, a3=ctx.r3.u32, a4=ctx.r4.u32, a5=ctx.r5.u32, a6=ctx.r6.u32;
  rex::ppc::HostToGuestFunction<rex::kernel::xam::{name}_entry>(ctx, base);
  REXLOG_INFO("M6 content api={name} caller={{:08X}} arg3={{:08X}} arg4={{:08X}} arg5={{:08X}} arg6={{:08X}} result={{:08X}}", caller,a3,a4,a5,a6,ctx.r3.u32);
}}
static rex::ppc::detail::PPCFuncRegistrar m6{name}("__imp__{name}", &__imp__{name});'''
        )], from_head=False)
    patch('src/audio/sdl/sdl_audio_driver.cpp', [
        ('#include <rex/audio/sdl/sdl_audio_driver.h>', '#include <rex/audio/sdl/sdl_audio_driver.h>\n#include <rex/m6_audio_capture.h>'),
        ('\n      std::memset(data, 0, len);', '\n      std::memset(data, 0, len);\n      m6audio::Capture(data, sample_count, driver->sdl_device_channels_);'),
        ('      }\n      if (!SDL_PutAudioStreamData(stream, data, len)) {', '      }\n      m6audio::Capture(data, sample_count, driver->sdl_device_channels_);\n      if (!SDL_PutAudioStreamData(stream, data, len)) {')
    ], from_head=False)
