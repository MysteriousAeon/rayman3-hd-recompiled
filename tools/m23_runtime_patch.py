"""Replay after M22 at the same pin: optional correction of the title's two-layer surface shader (M23, D-052).

`tools/m23_water_layers.h`: with R3HD_LAYER_COORDS=separate (first name R3HD_WATER_LAYERS, still read when the
new variable is absent; D-054), the draw that binds the title's `2t_d_sppt` / `tvt_tVT` shader pair (a two-layer
translucent sheet: haze, clouds) is issued with edited copies of those two shaders, so the second layer
is sampled with its own coordinates and scroll offset, as the original shader in the title's source file does.
Without the variable nothing changes: the pair is drawn as the Xbox 360 HD release draws it (both layers on the
first layer's coordinates). The cost when off is one flag test per draw.

Host-only: no generated code, no guest patch, no guest memory or register write, no other shader touched.
"""
from m8_runtime_patch import patch_once
from m16_runtime_patch import install

SUBSTITUTE = '''  // M23 (D-052): optional two-layer surface correction (off unless R3HD_LAYER_COORDS=separate;
  // rex/m23_water_layers.h). The pair is replaced by edited copies of its own microcode; a pair that is not
  // exactly the expected one is drawn as issued.
  if (m23water::Enabled() && pixel_shader &&
      vertex_shader->ucode_data_hash() == m23water::kVertexShaderHash &&
      pixel_shader->ucode_data_hash() == m23water::kPixelShaderHash) {
    static const std::vector<uint32_t> m23_vs =
        m23water::Corrected(vertex_shader->ucode_data(), m23water::kVertexPlan);
    static const std::vector<uint32_t> m23_ps =
        m23water::Corrected(pixel_shader->ucode_data(), m23water::kPixelPlan);
    static bool m23_logged = false;
    if (!m23_vs.empty() && !m23_ps.empty()) {
      vertex_shader = pipeline_cache_->LoadShader(xenos::ShaderType::kVertex, m23_vs.data(),
                                                  uint32_t(m23_vs.size()));
      pixel_shader = pipeline_cache_->LoadShader(xenos::ShaderType::kPixel, m23_ps.data(),
                                                 uint32_t(m23_ps.size()));
      pipeline_cache_->AnalyzeShaderUcode(*vertex_shader);
      pipeline_cache_->AnalyzeShaderUcode(*pixel_shader);
    }
    if (!m23_logged) {
      m23_logged = true;
      REXGPU_INFO("M23 layer_coords pair={} vs={:016X} ps={:016X}",
                  (!m23_vs.empty() && !m23_ps.empty()) ? "corrected" : "refused",
                  vertex_shader->ucode_data_hash(), pixel_shader->ucode_data_hash());
    }
  }

'''

if __name__ == '__main__':
    install('m23_water_layers.h')

    patch_once('src/graphics/d3d12/command_processor.cpp', [
        ('#include <rex/m3_gpu_trace.h>\n', '#include <rex/m3_gpu_trace.h>\n#include <rex/m23_water_layers.h>\n'),
        # Before the M22 trace block, so a trace records the shaders the draw was issued with.
        ('  // M22: one-frame draw-state trace (off unless R3HD_M22_DRAW_TRACE; rex/m22_draw_trace.h). Read-only.\n',
         SUBSTITUTE
         + '  // M22: one-frame draw-state trace (off unless R3HD_M22_DRAW_TRACE; rex/m22_draw_trace.h). Read-only.\n'),
        ('  REXGPU_INFO("M15 draw_scale x={} y={} as_requested={}", draw_resolution_scale_x,',
         '  REXGPU_INFO("M23 layer_coords={}", m23water::Enabled() ? "separate" : "original");\n'
         '  REXGPU_INFO("M15 draw_scale x={} y={} as_requested={}", draw_resolution_scale_x,'),
    ])
