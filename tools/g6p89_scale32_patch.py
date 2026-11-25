"""Replay after g6p127_crown_blend_patch.py at the same pin (last in the chain): native 3:2 (1.5x) D3D12 renderer.

G6-P89 / G6-P92 / G6-P140 (development integration, off by default). Nothing changes unless the D3D12 command
processor activates the path via R3HD_RENDER_SCALE_3_2=1 (or legacy hidden-test gate R3HD_NONINTRUSIVE +
R3HD_TEST_G6P89_SCALE_3_2=1 when R3HD_RENDER_SCALE_3_2 is unset) and device support for scaled resolve memory.
Inactive, every edited expression is the SDK's integer expression (`value * scale` through g6p89::Scale{x, y, 1}),
so scales 1 / 2 / 3 are unchanged.

Steps:
  1. install tools/g6p89_scale32.h as include/rex/g6p89_scale32.h;
  2. tools/g6p89_shader_build.py `ensure`: the three 3:2 FXC variants (resolve_fast_32bpp_1x2xmsaa_scaled32_cs,
     texture_load_32bpb_scaled32_cs, texture_load_depth_unorm_scaled32_cs) built from pinned Xenia 0b2ffa314 with the
     pinned FXC, checked against tools/g6p89_shader_manifest.py, copied into src/graphics/shaders/bytecode/d3d12_5_1;
  3. the exact hunks of tools/g6p89_scale32_edits.py in the shared render target / texture caches, draw utilities,
     the D3D12 render target / texture caches, command processor, pipeline cache and the DXBC translator. No hunk
     changes a line another chain patch inserted.
Regression: tools/g6p89_scale32_regression.py. Reader: tools/g6p89_scale32.py.
"""
from m8_runtime_patch import patch_once
from m16_runtime_patch import install
from g6p89_scale32_edits import EDITS
import g6p89_shader_build

TAG = 'G6-P89'


if __name__ == '__main__':
    install('g6p89_scale32.h')
    changed = g6p89_shader_build.ensure(g6p89_shader_build.DEFAULT_SRC, g6p89_shader_build.DEFAULT_SDK,
                                        g6p89_shader_build.DEFAULT_FXC)
    if changed:
        print('installed', ', '.join(changed))
    for rel, edits in EDITS.items():
        patch_once(rel, edits)
