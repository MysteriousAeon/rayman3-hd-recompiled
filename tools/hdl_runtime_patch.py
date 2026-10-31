"""Replay after M23 at the same pin: optional bypass of the HD release's final red-correction pass (HD+ lighting L1,
D-150; experimental HD+ candidate, off in every preset).

`tools/hdl_red_correction.h`: with R3HD_RED_CORRECTION=bypass the draw that binds pixel shader `DB19DF80422CD907`
(`psm/redcorrection.psh`) is uploaded with c0.x = 2.0 in the host's copy of its pixel constants, so the shader's
own test fails everywhere and it writes the sampled colour unchanged. The draw, its shaders, render target,
texture and resolve are untouched; the bypassed upload is never reused by the next draw. Without the variable
nothing changes: the pass runs with the title's coefficients. The cost when off is one hash compare per draw.

Host-only: no generated code, no guest patch, no guest memory or register write, no microcode edit.
"""
from m8_runtime_patch import patch_once
from m16_runtime_patch import install

SELECT = '''  // HD+ lighting L1 (D-150): optional red-correction bypass (off unless R3HD_RED_CORRECTION=bypass;
  // rex/hdl_red_correction.h). Only the host copy of this draw's c0.x changes; a shader that does not read c0
  // is drawn as issued.
  bool hdl_red_bypass = false;
  if (pixel_shader != nullptr && pixel_shader->ucode_data_hash() == hdlred::kPixelShaderHash) {
    const Shader::ConstantRegisterMap& hdl_map = pixel_shader->constant_register_map();
    const bool hdl_wanted = hdlred::Wanted();
    const bool hdl_layout = hdlred::LayoutMatches(hdl_map.float_bitmap, hdl_map.float_count);
    hdl_red_bypass = hdl_wanted && hdl_layout;
    if (hdl_red_bypass) {
      cbuffer_binding_float_pixel_.up_to_date = false;
    }
    static int hdl_logged = -1;
    const int hdl_state = !hdl_wanted ? 0 : hdl_layout ? 1 : 2;
    if (hdl_state != hdl_logged) {
      hdl_logged = hdl_state;
      float hdl_c0[2];
      std::memcpy(hdl_c0, &regs[XE_GPU_REG_SHADER_CONSTANT_256_X], sizeof(hdl_c0));
      REXGPU_INFO("HDL red_correction pass={} c0=({},{})",
                  hdl_state == 0 ? "original" : hdl_state == 1 ? "bypassed" : "refused", hdl_c0[0], hdl_c0[1]);
    }
  }

'''

SPLIT = '''  // HD+ lighting L1 (D-150), hidden diagnostic only (R3HD_RED_CORRECTION_AB=split; rex/hdl_red_correction.h):
  // the red-correction draw is issued again with the bypassed c0, moved right by half and clipped to the right
  // half, so the right half shows the left half through the bypass.
  const bool hdl_split = hdlred::Split() && pixel_shader != nullptr &&
                         pixel_shader->ucode_data_hash() == hdlred::kPixelShaderHash &&
                         hdlred::LayoutMatches(pixel_shader->constant_register_map().float_bitmap,
                                               pixel_shader->constant_register_map().float_count);
  D3D12_RECT hdl_saved_scissor = ff_scissor_;
  D3D12_VIEWPORT hdl_saved_viewport = ff_viewport_;
  auto hdl_split_begin = [&]() -> bool {
    const Shader::ConstantRegisterMap& map = pixel_shader->constant_register_map();
    D3D12_GPU_VIRTUAL_ADDRESS address;
    uint8_t* constants = constant_buffer_pool_->Request(
        frame_current_, sizeof(float) * 4 * map.float_count, D3D12_CONSTANT_BUFFER_DATA_PLACEMENT_ALIGNMENT,
        nullptr, nullptr, &address);
    if (constants == nullptr) {
      return false;
    }
    uint8_t* const first = constants;
    for (uint32_t i = 0; i < 4; ++i) {
      uint64_t entry = map.float_bitmap[i];
      uint32_t index;
      while (rex::bit_scan_forward(entry, &index)) {
        entry &= ~(1ull << index);
        std::memcpy(constants, &regs[XE_GPU_REG_SHADER_CONSTANT_256_X + (i << 8) + (index << 2)],
                    4 * sizeof(float));
        constants += 4 * sizeof(float);
      }
    }
    std::memcpy(first, &hdlred::kBypassThreshold, sizeof(float));
    deferred_command_list_.D3DSetGraphicsRootConstantBufferView(
        bindless_resources_used_ ? kRootParameter_Bindless_FloatConstantsPixel
                                 : kRootParameter_Bindful_FloatConstantsPixel,
        address);
    hdl_saved_scissor = ff_scissor_;
    hdl_saved_viewport = ff_viewport_;
    // The copy is moved right by half the scissor width and clipped to the right half, so the right half shows
    // the left half's picture through the bypass: the same pixels and the same frame as the left half.
    const LONG half = (hdl_saved_scissor.right - hdl_saved_scissor.left) / 2;
    D3D12_RECT right = hdl_saved_scissor;
    right.left = hdl_saved_scissor.left + half;
    D3D12_VIEWPORT shifted = hdl_saved_viewport;
    shifted.TopLeftX += float(half);
    SetScissorRect(right);
    SetViewport(shifted);
    static bool logged = false;
    if (!logged) {
      logged = true;
      REXGPU_INFO("HDL red_correction pass=split scissor=({},{})-({},{}) viewport_x={} width={} shift={}",
                  hdl_saved_scissor.left, hdl_saved_scissor.top, hdl_saved_scissor.right,
                  hdl_saved_scissor.bottom, hdl_saved_viewport.TopLeftX, hdl_saved_viewport.Width, half);
      // The captured frame has passed through the guest's 256-entry display gamma ramp (10-bit entries);
      // the judge needs it to compare in the pass's own values. Read-only.
      for (uint32_t channel = 0; channel < 3; ++channel) {
        std::string values;
        for (uint32_t i = 0; i < 256; ++i) {
          const reg::DC_LUT_30_COLOR& entry = gamma_ramp_256_entry_table()[i];
          values += std::to_string(channel == 0 ? entry.color_10_red
                                   : channel == 1 ? entry.color_10_green : entry.color_10_blue);
          values += i < 255 ? "," : "";
        }
        REXGPU_INFO("HDL red_correction ramp channel={} values={}", "rgb"[channel], values);
      }
    }
    return true;
  };
  auto hdl_split_end = [&]() {
    SetViewport(hdl_saved_viewport);
    SetScissorRect(hdl_saved_scissor);
    deferred_command_list_.D3DSetGraphicsRootConstantBufferView(
        bindless_resources_used_ ? kRootParameter_Bindless_FloatConstantsPixel
                                 : kRootParameter_Bindful_FloatConstantsPixel,
        cbuffer_binding_float_pixel_.address);
  };

'''

if __name__ == '__main__':
    install('hdl_red_correction.h')

    # Every anchor is a line of the pinned SDK that no other patch's text touches, so each patch of the chain
    # still finds its own text when build_milestone8.bat replays them all.
    patch_once('src/graphics/d3d12/command_processor.cpp', [
        ('#include <rex/memory/utils.h>\n', '#include <rex/hdl_red_correction.h>\n#include <rex/memory/utils.h>\n'),
        ('  // Write the constant buffer data.\n', SELECT + '  // Write the constant buffer data.\n'),
        ('        &cbuffer_binding_float_pixel_.address);\n'
         '    if (float_constants == nullptr) {\n'
         '      return false;\n'
         '    }\n',
         '        &cbuffer_binding_float_pixel_.address);\n'
         '    if (float_constants == nullptr) {\n'
         '      return false;\n'
         '    }\n'
         '    uint8_t* const hdl_pixel_c0 = float_constants;\n'),
        ('    cbuffer_binding_float_pixel_.up_to_date = true;\n',
         '    if (hdl_red_bypass) {\n'
         '      // The buffer starts with c0 (layout checked above); x is the red-share threshold.\n'
         '      std::memcpy(hdl_pixel_c0, &hdlred::kBypassThreshold, sizeof(float));\n'
         '    }\n'
         '    // A bypassed upload is never reused by the next draw.\n'
         '    cbuffer_binding_float_pixel_.up_to_date = !hdl_red_bypass;\n'),
        ('  // Draw.\n  if (primitive_processing_result.index_buffer_type ==\n',
         SPLIT + '  // Draw.\n  if (primitive_processing_result.index_buffer_type ==\n'),
        ('    deferred_command_list_.D3DDrawInstanced(primitive_processing_result.host_draw_vertex_count, 1,\n'
         '                                            0, 0);\n',
         '    deferred_command_list_.D3DDrawInstanced(primitive_processing_result.host_draw_vertex_count, 1,\n'
         '                                            0, 0);\n'
         '    if (hdl_split && hdl_split_begin()) {\n'
         '      deferred_command_list_.D3DDrawInstanced(primitive_processing_result.host_draw_vertex_count, 1,\n'
         '                                              0, 0);\n'
         '      hdl_split_end();\n'
         '    }\n'),
        ('        primitive_processing_result.host_draw_vertex_count, 1, 0, 0, 0);\n',
         '        primitive_processing_result.host_draw_vertex_count, 1, 0, 0, 0);\n'
         '    if (hdl_split && hdl_split_begin()) {\n'
         '      deferred_command_list_.D3DDrawIndexedInstanced(\n'
         '          primitive_processing_result.host_draw_vertex_count, 1, 0, 0, 0);\n'
         '      hdl_split_end();\n'
         '    }\n'),
        ('    REXGPU_ERROR("Failed to initialize shared memory");\n'
         '    return false;\n'
         '  }\n',
         '    REXGPU_ERROR("Failed to initialize shared memory");\n'
         '    return false;\n'
         '  }\n'
         '  REXGPU_INFO("HDL red_correction={}", hdlred::Split() ? "split"\n'
         '              : hdlred::Selected() ? "bypass" : "original");\n'),
    ])
