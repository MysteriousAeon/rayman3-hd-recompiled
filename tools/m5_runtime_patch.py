"""M5 observations after M2/M3/M4 replay; no emulation semantics change."""
from m3_runtime_patch import SDK, patch
import os

if __name__ == '__main__':
    patch('include/rex/m3_gpu_trace.h', [
        ('#include <atomic>', '#include <atomic>\n#include <cstdlib>'),
        ('inline bool CaptureAt(uint64_t swap) {', 'inline bool CaptureAt(uint64_t swap) {\n  if (std::getenv("R3HD_M5_CAPTURE") && swap % 300 == 0) return true;')
    ], from_head=False)
    patch('src/graphics/d3d12/command_processor.cpp', [(
        '  bool memexport_used_pixel = pixel_shader && (pixel_shader->memexport_eM_written() != 0);',
        '''  // M5: active shader binding and fetch state at representative menu draws.
  if (std::getenv("R3HD_M5_CAPTURE") &&
      (m3gpu::counters().swaps == 2400 || m3gpu::counters().swaps == 3000)) {
    auto fetch = regs.GetTextureFetch(0);
    auto vf = regs.GetVertexFetch(95);
    REXGPU_INFO("M5 menu_draw swap={} draw={} primitive={} indices={} vs={:016X} ps={:016X} fetch0={:08X},{:08X},{:08X},{:08X},{:08X},{:08X} scissor={:08X},{:08X}",
      m3gpu::counters().swaps.load(), m3gpu::counters().draws.load(), unsigned(primitive_type), index_count,
      vertex_shader->ucode_data_hash(), pixel_shader ? pixel_shader->ucode_data_hash() : 0,
      fetch.dword_0, fetch.dword_1, fetch.dword_2, fetch.dword_3, fetch.dword_4, fetch.dword_5,
      regs.Get<reg::PA_SC_WINDOW_SCISSOR_TL>().value, regs.Get<reg::PA_SC_WINDOW_SCISSOR_BR>().value);
    REXGPU_INFO("M5 menu_vertex draw={} slot=95 fetch={:08X},{:08X} c255={:08X},{:08X},{:08X},{:08X}",
      m3gpu::counters().draws.load(), vf.dword_0, vf.dword_1,
      regs.values[0x43FC], regs.values[0x43FD], regs.values[0x43FE], regs.values[0x43FF]);
    auto& cmap = vertex_shader->constant_register_map();
    REXGPU_INFO("M5 menu_vertex_mask draw={} bitmap={:08X},{:08X},{:08X}",
      m3gpu::counters().draws.load(), cmap.vertex_fetch_bitmap[0], cmap.vertex_fetch_bitmap[1], cmap.vertex_fetch_bitmap[2]);
    // Selected geometry of every draw in one menu frame: header, raw index bytes, raw vertex
    // buffer bytes as the guest wrote them (private, decoded by tools/m5_menu_draws.py).
    if (vf.type == xenos::FetchConstantType::kVertex && m3gpu::counters().swaps == 2400) {
      char path[80];
      std::snprintf(path, sizeof(path), "m5_draw_%llu.bin", (unsigned long long)m3gpu::counters().draws.load());
      if (auto* file = std::fopen(path, "wb")) {
        uint32_t index_bytes = index_buffer_info ? index_buffer_info->count * (index_buffer_info->format == xenos::IndexFormat::kInt32 ? 4 : 2) : 0;
        uint32_t vertex_bytes = std::min<uint32_t>(vf.size * 4, 1 << 22);
        uint32_t header[20] = {0x4D354452, uint32_t(primitive_type), index_count, index_buffer_info ? 1u : 0u,
          index_buffer_info ? uint32_t(index_buffer_info->format) : 0, index_buffer_info ? uint32_t(index_buffer_info->endianness) : 0,
          index_buffer_info ? index_buffer_info->guest_base : 0, uint32_t(regs.Get<reg::VGT_INDX_OFFSET>().indx_offset),
          uint32_t(vf.address << 2), vertex_bytes, index_bytes, uint32_t(vertex_shader->ucode_data_hash() >> 32),
          fetch.dword_0, fetch.dword_1, fetch.dword_2, fetch.dword_3, fetch.dword_4, fetch.dword_5,
          regs.Get<reg::PA_SC_WINDOW_SCISSOR_BR>().value, uint32_t(pixel_shader ? pixel_shader->ucode_data_hash() >> 32 : 0)};
        std::fwrite(header, 4, 20, file);
        if (index_bytes) std::fwrite(memory_->TranslatePhysical(index_buffer_info->guest_base), 1, index_bytes, file);
        std::fwrite(memory_->TranslatePhysical(vf.address << 2), 1, vertex_bytes, file);
        // Trailer: render state, first vertex/pixel float constants and fetch constants.
        std::fwrite(&regs.values[0x2000], 4, 0x400, file);
        std::fwrite(&regs.values[0x4000], 4, 0x40, file);
        std::fwrite(&regs.values[0x4400], 4, 0x40, file);
        std::fwrite(&regs.values[0x4800], 4, 0x60, file);
        std::fclose(file);
      }
      // Guest-memory bytes of each distinct DXT4/5 texture bound to fetch 0 in that frame (once per base).
      static uint32_t dumped[16]; static unsigned dumped_count = 0;
      uint32_t texture_base = fetch.dword_1 & 0xFFFFF000u;
      bool seen = false;
      for (unsigned i = 0; i < dumped_count; ++i) seen |= dumped[i] == texture_base;
      if (!seen && dumped_count < 16 && (fetch.dword_1 & 0x3F) == 0x14 && (fetch.dword_0 & 3) == 2) {
        dumped[dumped_count++] = texture_base;
        uint32_t tw = (fetch.dword_2 & 0x1FFF) + 1, th = ((fetch.dword_2 >> 13) & 0x1FFF) + 1;
        std::snprintf(path, sizeof(path), "m5_texture_%08X_%ux%u.bin", texture_base, tw, th);
        if (auto* file = std::fopen(path, "wb")) {
          std::fwrite(memory_->TranslatePhysical(texture_base), 1, size_t((tw + 3) / 4) * ((th + 3) / 4) * 16, file);
          std::fclose(file);
        }
      }
    }
  }
  bool memexport_used_pixel = pixel_shader && (pixel_shader->memexport_eM_written() != 0);''')
    ], from_head=False)
    # D-020: the pinned SDK caches "vertex buffer resident" per fetch slot and then skips
    # SharedMemory::RequestRange while the fetch constant's address/size are unchanged. RequestRange is
    # what uploads guest pages modified since the last request, so a dynamic vertex buffer rewritten by
    # the CPU under an unchanged fetch constant was drawn with stale host data (menu atlas overlay).
    # Always request the range (already-valid ranges return early); R3HD_M5_VB_RESIDENCY_CACHE=1
    # restores the pinned behaviour for the A/B experiment only.
    patch('src/graphics/d3d12/command_processor.cpp', [(
        '''      if (vertex_buffers_in_sync_[vfetch_index >> 6] & vfetch_bit) {
        continue;
      }
      xenos::xe_gpu_vertex_fetch_t vfetch_constant = regs.GetVertexFetch(vfetch_index);''',
        '''      static const bool m5_residency_cache = std::getenv("R3HD_M5_VB_RESIDENCY_CACHE") != nullptr;
      if (m5_residency_cache && (vertex_buffers_in_sync_[vfetch_index >> 6] & vfetch_bit)) {
        continue;
      }
      xenos::xe_gpu_vertex_fetch_t vfetch_constant = regs.GetVertexFetch(vfetch_index);'''), (
        '''      if (state.address == vfetch_constant.address && state.size == vfetch_constant.size) {''',
        '''      if (m5_residency_cache && state.address == vfetch_constant.address &&
          state.size == vfetch_constant.size) {''')
    ], from_head=False)
    patch('src/kernel/xam/xam_input.cpp', [
        ('uint16_t buttons = 0; uint32_t packet = 0;', 'uint16_t buttons = 0; uint32_t packet = 0;\n  int16_t lx = 0, ly = 0, rx = 0, ry = 0;'),
        ('buttons = s->gamepad.buttons; packet = s->packet_number;', 'buttons = s->gamepad.buttons; packet = s->packet_number;\n    lx = s->gamepad.thumb_lx; ly = s->gamepad.thumb_ly; rx = s->gamepad.thumb_rx; ry = s->gamepad.thumb_ry;'),
        ('uint32_t key = uint32_t(buttons) | (ctx.r3.u32 ? 0x10000 : 0);', 'uint32_t key = uint32_t(buttons) | (ctx.r3.u32 ? 0x10000 : 0);\n  static thread_local int16_t previous_axes[4][4] = {};'),
        ('previous[user] != key)', 'previous[user] != key || (user < 4 && (previous_axes[user][0] != lx || previous_axes[user][1] != ly || previous_axes[user][2] != rx || previous_axes[user][3] != ry)))'),
        ('    previous[user] = key;', '    previous[user] = key;\n    previous_axes[user][0] = lx; previous_axes[user][1] = ly; previous_axes[user][2] = rx; previous_axes[user][3] = ry;'),
        ('packet={} buttons={:04X}",', 'packet={} buttons={:04X} lx={} ly={} rx={} ry={}",'),
        ('state, packet, buttons);', 'state, packet, buttons, lx, ly, rx, ry);')
    ], from_head=False)
