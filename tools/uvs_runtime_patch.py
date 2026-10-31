"""Replay after the HD+ lighting patch at the same pin: optional lit UV scroll (E-353, D-157; experimental, off in
every preset).

`tools/uvs_lit_scroll.h`: with R3HD_LIT_UV_SCROLL=applied every draw that binds the title's `1t_d_lighting` vertex
shader (`D64D176416571592`) is issued with an edited copy of it that adds the UV offset c10.xy the engine writes,
as the title's other one-layer vertex shaders do. The fist-charge trail's fire gradient then scrolls with the
charge. Without the variable nothing changes: the shader is drawn as the Xbox 360 HD release draws it. The cost
when off is one flag test per draw.

Host-only: no generated code, no guest patch, no guest memory or register write, no other shader touched. The
edited copy is analysed like any shader the title binds, so its constant usage (c10) comes from the edited code.
"""
from m8_runtime_patch import SDK, patch_once
from m16_runtime_patch import install

# Inserted before the M23 block (whose first line is the anchor), so the M23 script's own text stays contiguous and
# both edits precede the M22 trace, which therefore records the shader the draw was issued with.
M23_FIRST = '  // M23 (D-052): optional two-layer surface correction (off unless R3HD_LAYER_COORDS=separate;\n'

SUBSTITUTE = '''  // Lit UV scroll (E-353, D-157): optional (off unless R3HD_LIT_UV_SCROLL=applied; rex/uvs_lit_scroll.h). The
  // title's `1t_d_lighting` vertex shader is replaced by an edited copy that adds the UV offset c10.xy; a shader
  // that is not exactly the expected one is drawn as issued.
  if (uvslit::Enabled() && vertex_shader->ucode_data_hash() == uvslit::kVertexShaderHash) {
    static const std::vector<uint32_t> uvs_vs =
        uvslit::Corrected(vertex_shader->ucode_data(), uvslit::kVertexPlan);
    static bool uvs_logged = false;
    const uint64_t uvs_original = vertex_shader->ucode_data_hash();
    if (!uvs_vs.empty()) {
      vertex_shader = pipeline_cache_->LoadShader(xenos::ShaderType::kVertex, uvs_vs.data(),
                                                  uint32_t(uvs_vs.size()));
      pipeline_cache_->AnalyzeShaderUcode(*vertex_shader);
    }
    if (!uvs_logged) {
      uvs_logged = true;
      REXGPU_INFO("UVS lit_uv_scroll shader={} vs={:016X} edited={:016X}", !uvs_vs.empty() ? "applied" : "refused",
                  uvs_original, vertex_shader->ucode_data_hash());
    }
  }

'''

# Each edit with a marker that occurs only once it is applied. Later scripts insert next to these sites (M26, M33), so on
# a rerun over a fully patched file an edit's "after" text is no longer contiguous; the marker keeps it from being
# inserted twice. A replay from the pin applies all three.
EDITS = [
    ('#include <rex/uvs_lit_scroll.h>\n',
     ('#include <rex/m23_water_layers.h>\n', '#include <rex/m23_water_layers.h>\n#include <rex/uvs_lit_scroll.h>\n')),
    ('uvslit::Enabled() && vertex_shader', (M23_FIRST, SUBSTITUTE + M23_FIRST)),
    ('REXGPU_INFO("UVS lit_uv_scroll={}"',
     ('  REXGPU_INFO("M23 layer_coords={}", m23water::Enabled() ? "separate" : "original");\n',
      '  REXGPU_INFO("UVS lit_uv_scroll={}", uvslit::Enabled() ? "applied" : "original");\n'
      '  REXGPU_INFO("M23 layer_coords={}", m23water::Enabled() ? "separate" : "original");\n')),
]
CP = 'src/graphics/d3d12/command_processor.cpp'

if __name__ == '__main__':
    install('uvs_lit_scroll.h')
    text = (SDK / CP).read_text()
    patch_once(CP, [edit for marker, edit in EDITS if marker not in text])
