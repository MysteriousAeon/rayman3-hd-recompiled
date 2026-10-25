"""Replay after M21 at the same pin: fidelity instrumentation and the hidden-run mute (M22, D-051).

1. `tools/m22_draw_trace.h`: with R3HD_M22_DRAW_TRACE set, the guest frame that follows an explicit frame capture
   is written as one private file of draw records (registers, shader microcode, vertex / index bytes, the first
   bytes of each bound texture). Read-only; decoded by tools/m22_draw_report.py. Off by default.
2. `tools/m22_audio_probe.h`: a hidden test run (R3HD_NONINTRUSIVE) sets the SDL stream gain to 0, so it cannot
   be heard; mixing, statistics and captures are unchanged. R3HD_AUDIO_AUDIBLE=1 restores the audible run. With
   R3HD_M22_AUDIO set, per-callback output statistics and XMA context events go to m22_audio.txt (no samples).

Host-only: no generated code, no guest patch, no guest memory write, nothing rendered or decoded differently.
"""
from m8_runtime_patch import patch_once
from m16_runtime_patch import install

DRAW_TRACE = '''  // M22: one-frame draw-state trace (off unless R3HD_M22_DRAW_TRACE; rex/m22_draw_trace.h). Read-only.
  if (m22draw::Tracing(m3gpu::counters().swaps.load())) {
    m22draw::Shader(vertex_shader->ucode_data_hash(), 0, vertex_shader->ucode_data().data(),
                    uint32_t(vertex_shader->ucode_dword_count()));
    if (pixel_shader)
      m22draw::Shader(pixel_shader->ucode_data_hash(), 1, pixel_shader->ucode_data().data(),
                      uint32_t(pixel_shader->ucode_dword_count()));
    std::vector<uint8_t> m22;
    m22draw::Head head = {};
    head.draw = m22draw::state().draw++;
    head.primitive = uint32_t(primitive_type);
    head.index_count = index_count;
    if (index_buffer_info) {
      head.indexed = 1;
      head.index_format = uint32_t(index_buffer_info->format);
      head.index_endian = uint32_t(index_buffer_info->endianness);
      head.index_base = index_buffer_info->guest_base;
      head.index_bytes = m22draw::Bounded(
          head.index_base,
          index_buffer_info->count * (index_buffer_info->format == xenos::IndexFormat::kInt32 ? 4 : 2),
          m22draw::kIndexCap);
    }
    head.vs_hash = vertex_shader->ucode_data_hash();
    head.ps_hash = pixel_shader ? pixel_shader->ucode_data_hash() : 0;
    const auto& m22_bindings = vertex_shader->vertex_bindings();
    head.binding_count = uint32_t(m22_bindings.size());
    head.texture_count = uint32_t(vertex_shader->texture_bindings().size() +
                                  (pixel_shader ? pixel_shader->texture_bindings().size() : 0));
    m22draw::Append(m22, head);
    std::vector<std::pair<uint32_t, uint32_t>> m22_vertex_ranges;
    for (const auto& binding : m22_bindings) {
      auto vf = regs.GetVertexFetch(binding.fetch_constant);
      const bool valid = vf.type == xenos::FetchConstantType::kVertex;
      m22draw::BindingHead bh = {binding.fetch_constant, binding.stride_words,
                                 uint32_t(binding.attributes.size()), uint32_t(vf.address << 2),
                                 uint32_t(vf.size * 4),
                                 valid ? m22draw::Bounded(uint32_t(vf.address << 2), uint32_t(vf.size * 4),
                                                          m22draw::kVertexCap)
                                       : 0};
      m22draw::Append(m22, bh);
      for (const auto& attribute : binding.attributes) {
        const auto& a = attribute.fetch_instr.attributes;
        m22draw::AttributeRow row = {uint32_t(a.data_format), uint32_t(a.offset), a.is_signed, a.is_integer,
                                     uint32_t(a.exp_adjust),
                                     uint32_t(attribute.fetch_instr.result.storage_index)};
        m22draw::Append(m22, row);
      }
      m22_vertex_ranges.emplace_back(bh.address, bh.captured_bytes);
    }
    auto m22_texture = [&](uint32_t fetch_constant) {
      auto tf = regs.GetTextureFetch(fetch_constant);
      m22draw::TextureRow row = {};
      row.fetch_constant = fetch_constant;
      row.base = tf.dword_1 & 0xFFFFF000u;
      if ((tf.dword_0 & 3) == 2 && row.base) {
        row.head_bytes = m22draw::kTextureHead;
        std::memcpy(row.head, memory_->TranslatePhysical(row.base), m22draw::kTextureHead);
      }
      m22draw::Append(m22, row);
    };
    for (const auto& binding : vertex_shader->texture_bindings()) m22_texture(binding.fetch_constant);
    if (pixel_shader)
      for (const auto& binding : pixel_shader->texture_bindings()) m22_texture(binding.fetch_constant);
    m22draw::Append(m22, &regs.values[0x2000], 0x400 * 4);
    m22draw::Append(m22, &regs.values[0x4000], 0x8C0 * 4);
    if (head.index_bytes)
      m22draw::Append(m22, memory_->TranslatePhysical(head.index_base), head.index_bytes);
    for (const auto& range : m22_vertex_ranges)
      if (range.second) m22draw::Append(m22, memory_->TranslatePhysical(range.first), range.second);
    m22draw::Record(0, m22);
  }
'''

if __name__ == '__main__':
    install('m22_draw_trace.h')
    install('m22_audio_probe.h')

    patch_once('include/rex/m3_gpu_trace.h', [
        ('#include <rex/ui/presenter.h>\n', '#include <rex/ui/presenter.h>\n#include <rex/m22_draw_trace.h>\n'),
        ('  if (!presenter || !CaptureAt(n)) return;\n',
         '  m22draw::OnSwap(n, presenter && CaptureAt(n));\n'
         '  if (!presenter || !CaptureAt(n)) return;\n'),
    ])
    patch_once('src/graphics/d3d12/command_processor.cpp', [
        ('  m3gpu::Copy(register_file_->values);\n',
         '  m3gpu::Copy(register_file_->values);\n'
         '  if (m22draw::Tracing(m3gpu::counters().swaps.load())) m22draw::Copy(register_file_->values);\n'),
        ('  // M5: active shader binding and fetch state at representative menu draws.\n',
         DRAW_TRACE + '  // M5: active shader binding and fetch state at representative menu draws.\n'),
    ])
    patch_once('src/audio/sdl/sdl_audio_driver.cpp', [
        ('#include <rex/m6_audio_capture.h>\n', '#include <rex/m6_audio_capture.h>\n#include <rex/m22_audio_probe.h>\n'),
        ('  if (!SDL_ResumeAudioDevice(sdl_device)) {\n',
         '  // M22 (D-051): a hidden test run is inaudible; the samples are still mixed, counted and captured.\n'
         '  if (m22audio::HiddenMute()) SDL_SetAudioStreamGain(sdl_stream_, 0.0f);\n'
         '  REXAPU_INFO("M22 audio hidden_mute={}", m22audio::HiddenMute() ? 1 : 0);\n'
         '  if (!SDL_ResumeAudioDevice(sdl_device)) {\n'),
        ('      std::memset(data, 0, len);\n      m6audio::Capture(data, sample_count, driver->sdl_device_channels_);\n',
         '      std::memset(data, 0, len);\n      m6audio::Capture(data, sample_count, driver->sdl_device_channels_);\n'
         '      m22audio::Output(driver, data, sample_count, driver->sdl_device_channels_, false);\n'),
        ('      }\n      m6audio::Capture(data, sample_count, driver->sdl_device_channels_);\n',
         '      }\n      m6audio::Capture(data, sample_count, driver->sdl_device_channels_);\n'
         '      m22audio::Output(driver, data, sample_count, driver->sdl_device_channels_, true);\n'),
    ])
    patch_once('src/audio/xma_context.cpp', [
        ('namespace rex::audio {\n\nusing stream::BitStream;\n',
         '#include <rex/m22_audio_probe.h>\n\nnamespace rex::audio {\n\nusing stream::BitStream;\n'),
        ('  const XMA_CONTEXT_DATA initial_data = data;\n\n  if (!data.output_buffer_valid) {\n',
         '  const XMA_CONTEXT_DATA initial_data = data;\n'
         '  m22audio::XmaInput(id(), data.IsAnyInputBufferValid());\n\n  if (!data.output_buffer_valid) {\n'),
        ('void XmaContext::ResetDecoderState() {\n',
         'void XmaContext::ResetDecoderState() {\n  m22audio::XmaReset(id());\n'),
        ('  if (decoded) {\n    ConvertFrame(',
         '  if (decoded) {\n    m22audio::XmaFrame(id());\n    ConvertFrame('),
        ("    // A dropped frame breaks the carry's adjacency; re-prime rather than splice\n",
         "    m22audio::XmaError(id(), 1);\n"
         "    // A dropped frame breaks the carry's adjacency; re-prime rather than splice\n"),
    ])
