"""Replay last in the chain: the HD+ shader corrections M23 (layer coordinates) and UVS (lit UV scroll) on Vulkan
(LX-3, E-374).

Both corrections are portable headers (tools/m23_water_layers.h, tools/uvs_lit_scroll.h: microcode edits of one
title shader pair / one vertex shader) with a single call site, in the D3D12 IssueDraw (m23_runtime_patch.py,
uvs_runtime_patch.py). The Linux build draws with Vulkan, so with R3HD_LAYER_COORDS=separate or
R3HD_LIT_UV_SCROLL=applied (the HD+ preset) nothing happened there.

This script inserts the SAME block into VulkanCommandProcessor::IssueDraw, at the same point (after the vertex and
pixel shader analysis, before the memexport and interpolator use of the pixel shader). The block is not retyped: it
is copied from the D3D12 command processor after the chain, between its UVS comment and its M22 trace comment, so
both backends always carry one text. It uses only `pipeline_cache_->LoadShader` / `AnalyzeShaderUcode` and shader
hashes, which the Vulkan pipeline cache provides with the same signatures. Off (the variables unset) it costs one
flag test per draw, as on D3D12. The D3D12 file and the Windows build are unchanged.
HDL (E-383): the accepted red-correction bypass also needs a Vulkan constant-buffer upload site. Invalidate
before uploading and leave the pixel buffer dirty afterwards so neither an earlier original upload nor this
bypassed upload can be reused across draws. Descriptor invalidation remains the SDK's own upload path.
Regression: tools/r3hd_vulkan_parity_regression.py.
"""
from m8_runtime_patch import SDK, patch_once

D3D12 = 'src/graphics/d3d12/command_processor.cpp'
VULKAN = 'src/graphics/vulkan/command_processor.cpp'
BEGIN = '  // Lit UV scroll (E-353, D-157): optional'
END = '\n  // M22: one-frame draw-state trace'
ANCHOR = '  bool memexport_used_pixel = pixel_shader && (pixel_shader->memexport_eM_written() != 0);\n'
INCLUDE = '#include <rex/graphics/registers.h>\n'
HEADER = ('  // LX-3 (E-374): the D3D12 IssueDraw block of the HD+ shader corrections UVS and M23, copied verbatim by\n'
          '  // tools/r3hd_vulkan_parity_patch.py (same insertion point: after the shader analysis).\n')

RED_SELECT = '''  // E-383: accepted HD+ red correction, host pixel constants only (D-151).
  bool hdl_red_bypass = false;
  if (pixel_shader != nullptr && pixel_shader->ucode_data_hash() == hdlred::kPixelShaderHash) {
    const Shader::ConstantRegisterMap& map = pixel_shader->constant_register_map();
    const bool wanted = hdlred::Wanted();
    const bool layout = hdlred::LayoutMatches(map.float_bitmap, map.float_count);
    hdl_red_bypass = wanted && layout;
    if (hdl_red_bypass) {
      current_constant_buffers_up_to_date_ &=
          ~(UINT32_C(1) << SpirvShaderTranslator::kConstantBufferFloatPixel);
    }
    static int logged = -1;
    const int state = !wanted ? 0 : layout ? 1 : 2;
    if (state != logged) {
      logged = state;
      float c0[2];
      std::memcpy(c0, &regs[XE_GPU_REG_SHADER_CONSTANT_256_X], sizeof(c0));
      REXGPU_INFO("HDL red_correction backend=vulkan pass={} c0=({},{})",
                  state == 0 ? "original" : state == 1 ? "bypassed" : "refused", c0[0], c0[1]);
    }
  }

'''


def red_edits():
    pixel = '      current_constant_buffers_up_to_date_ |= UINT32_C(1)\n' \
            '                                              << SpirvShaderTranslator::kConstantBufferFloatPixel;\n'
    anchor = '      buffer_info.range = VkDeviceSize(float_constants_size);\n'
    # The range assignment appears twice: scope this anchor with the pixel-specific size expression.
    allocation = '''      size_t float_constants_size =
          sizeof(float) * 4 * std::max(float_constant_count_pixel, UINT32_C(1));
      uint8_t* mapping = uniform_buffer_pool_->Request(frame_current_, float_constants_size,
                                                       uniform_buffer_alignment, buffer_info.buffer,
                                                       buffer_info.offset);
      if (!mapping) {
        return false;
      }
'''
    return [
        ('#include <rex/graphics/vulkan/command_processor.h>\n',
         '#include <rex/graphics/vulkan/command_processor.h>\n#include <rex/hdl_red_correction.h>  // E-383\n'),
        ('  // Write the new constant buffers.\n', RED_SELECT + '  // Write the new constant buffers.\n'),
        (allocation + anchor, allocation + anchor + '      uint8_t* const hdl_pixel_c0 = mapping;\n'),
        (pixel, '''      if (hdl_red_bypass) {
        std::memcpy(hdl_pixel_c0, &hdlred::kBypassThreshold, sizeof(float));
      } else {
''' + pixel + '''      }
      // A bypassed upload stays dirty: the next draw must upload its original guest constants.
'''),
    ]


def shared_block() -> str:
    text = (SDK / D3D12).read_text()
    assert text.count(BEGIN) == 1 and text.count(END) == 1, 'D3D12 UVS/M23 block markers'
    block = text[text.index(BEGIN):text.index(END) + 1]
    assert 'uvslit::Enabled()' in block and 'm23water::Enabled()' in block and 'M22' not in block
    return block


def edits():
    return [
        (INCLUDE, INCLUDE + '#include <rex/m23_water_layers.h>  // LX-3\n#include <rex/uvs_lit_scroll.h>  // LX-3\n'),
        (ANCHOR, HEADER + shared_block() + ANCHOR),
    ]


if __name__ == '__main__':
    path = SDK / VULKAN
    text = path.read_text(encoding='utf-8')
    # Replace an existing LX-3 UVS/M23 block span in place when the D3D12 block evolves (e.g. G6-P121),
    # because M2 resets D3D12 command_processor.cpp but not Vulkan command_processor.cpp.
    if HEADER in text and ANCHOR in text:
        start = text.index(HEADER)
        end = text.index(ANCHOR, start)
        desired = HEADER + shared_block()
        if text[start:end] != desired:
            path.write_text(text[:start] + desired + text[end:], encoding='utf-8')
    patch_once(VULKAN, edits() + red_edits())
