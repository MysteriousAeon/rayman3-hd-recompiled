"""G6-P89 (test only): build the three 3:2 D3D12 shader variants from pinned public Xenia source.

Source: Xenia `0b2ffa31485318f18838afa142cdb51cf1b35213` (BSD 3-clause; the SDK's D3D12 bytecode, D-336 / G6-P87),
as `git archive 0b2ffa314 src/xenia/gpu/shaders src/xenia/ui/shaders LICENSE` in private/work/g6p87/src_0b2ffa314.
Compiler: the G6-P87 recipe, `fxc /D SHADING_LANGUAGE_HLSL_XE=1 /Fh <id>.h /T cs_5_1 /Vn <id> /nologo <src>`, with the
pinned Windows SDK FXC 10.0.26100.7705 (SHA-256 checked). No compiled byte is edited by hand and no game shader is
involved. Sources and outputs stay under private/; this file and the metadata manifest are the only committed parts.

The edits below add one preprocessor switch, XE_RESOLUTION_SCALE_3_2, used only by three new wrapper files:
  * texture_address.xesli: XeTextureScaledTiledOffset implements model R (G6-P88): 2 x 2 guest Nx1 units -> 3 x 3 host
    Nx1 sub-units, column-major, at 9/4 of the group's guest address (4 / 8 / 16 bytes per block, 2D). The companion
    XeTextureScaledRightSubUnitOffsetInConsecutivePair does not exist under the switch (its callers recompute);
  * edram.xesli: 120x24-sample host tiles;
  * resolve.xesli: offsets and the width x 3/2 (exact for the multiples of 16 the C++ side admits), a one-host-pixel
    half-pixel fill (ceil(0.75)); the scale fields are not read;
  * resolve_fast_32bpp_1x2xmsaa.xesli: the second 4-pixel EDRAM load and the second destination store are addressed
    on their own (an 8-pixel run can cross the 60-sample depth half-tile swap at 3:2); G6-P92: 8x4 thread groups
    (64x4 host pixels), so any 8-aligned guest height (12 host rows) is whole groups without a Y bound;
  * texture_load.xesli / texture_load_32bpb.xesli: the second 4-block guest load is addressed on its own.
Without the switch the preprocessed text of every existing shader is unchanged; `build` proves it by rebuilding every
SDK shader from the edited tree and requiring byte-identical containers (the G6-P87 baseline set).

  python tools/g6p89_shader_build.py build  [--src DIR] [--sdk DIR] [--fxc EXE] --work DIR
  python tools/g6p89_shader_build.py ensure [--src DIR] [--sdk DIR] [--fxc EXE]   (used by g6p89_scale32_patch.py)
  python tools/g6p89_shader_build.py selftest
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import g6p87_shader_repro as g87  # noqa: E402

DEFAULT_SRC = os.path.join(ROOT, 'private', 'work', 'g6p87', 'src_0b2ffa314')
DEFAULT_SDK = os.path.join(ROOT, 'external', 'rexglue-sdk')
DEFAULT_FXC = r'C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\fxc.exe'
DEFAULT_OUT = os.path.join(ROOT, 'private', 'work', 'g6p89', 'shaders_out')
MANIFEST = os.path.join(ROOT, 'tools', 'g6p89_shader_manifest.py')
MANIFEST_HEAD = '"""G6-P89: metadata of the three 3:2 shader variants (names, hashes, sizes, counts; no shader bytes).\n\nWritten by `python tools/g6p89_shader_build.py build --write-manifest`; checked by g6p89_shader_build.ensure and\ntools/g6p89_scale32_regression.py."""\n\nMANIFEST = '
SOURCE_REVISION = '0b2ffa31485318f18838afa142cdb51cf1b35213'
FXC_SHA256 = '31fa10504b1551337de4d06ec2194143885a76a8b5a81177999e2faa34729183'
D3DCOMPILER_SHA256 = '2b23efdc8b45adc4b79c1c0b940a906336628cd35ed80defd489d70d22ff6d74'
G87_BASELINE_L3 = 107  # every SDK shader that rebuilds at all (FXAA pair lacks a submodule), G6-P87

# Pristine pinned sources that are edited (SHA-256 of the archived bytes).
PRISTINE = {
    'texture_address.xesli': 'b3a90b7e65ff9699fb5bdc7166a68ef3fdc0c6d73133e45c734b7dedb606a551',
    'edram.xesli': '72b3fb2c4ff88da143a4ab6bea412cf5a63724bdae0038f895b03b92346bf775',
    'resolve.xesli': 'd379a20244c42bac6649107ea2dbb849f6bf09cda70a911f4a1917a11fe62b1d',
    'resolve_fast_32bpp_1x2xmsaa.xesli': '6e87a51cf59e80392ed225c226d9cc8956b3bfc800b77ae0cb9f49638400b304',
    'texture_load.xesli': 'c7635140059280bc2c90d731722e7fba84677e432ccf5acbd855b4e9cad5b197',
    'texture_load_32bpb.xesli': '83a4a2257a366c88be7ff977850f656cd7c34ffe55e753c3afae1bea08982fd8',
}

VARIANTS = ['resolve_fast_32bpp_1x2xmsaa_scaled32_cs', 'texture_load_32bpb_scaled32_cs',
            'texture_load_depth_unorm_scaled32_cs']

R_FUNCTION = '''#ifdef XE_RESOLUTION_SCALE_3_2
// G6-P89 (test only): exact 3:2 scaled layout (G6-P88 model R) for 4, 8 and 16 bytes per block, 2D only. Two by two
// guest Nx1 units (one aligned contiguous run of 4 units in the guest tiled layout) are stored as 3 x 3 host Nx1
// sub-units of the same shape, column-major, at 9/4 of the group's guest address. `scale` is not read.
uint XeTextureScaledTiledOffset(bool is_3d, uint3_xe p, uint pitch_aligned,
                                uint height_aligned, uint bpb_log2,
                                uint2_xe scale) {
  uint unit_width_log2 = XeTextureTiledConsecutiveBlocksLog2(bpb_log2);
  uint x_subunits = p.x >> unit_width_log2;
  uint2_xe group = uint2_xe(x_subunits, p.y) / 3u;
  uint2_xe group_subunit = uint2_xe(x_subunits, p.y) - group * 3u;
  uint group_guest_address = uint(XeTextureTiledOffset2D(
      int2_xe(int(group.x << (unit_width_log2 + 1u)), int(group.y << 1u)),
      pitch_aligned, bpb_log2));
  return (group_guest_address >> 2u) * 9u +
         ((((group_subunit.x * 3u + group_subunit.y) << unit_width_log2) +
           (p.x & ((1u << unit_width_log2) - 1u)))
          << bpb_log2);
}
#else
'''

LICENSE_HEADER = '''/**
 ******************************************************************************
 * Xenia : Xbox 360 Emulator Research Project                                 *
 ******************************************************************************
 * Copyright 2022 Ben Vanik. All rights reserved.                             *
 * Released under the BSD license - see LICENSE in the root for more details. *
 ******************************************************************************
 */
// G6-P89 (test only): 3:2 (1.5x) variant built by tools/g6p89_shader_build.py.

'''

# (file, old, new): exact, each `old` must occur once in the pinned file.
EDITS = [
    ('texture_address.xesli',
     '''// for simplicity, especially of the division involved, assuming everything is
// unsigned.
uint XeTextureScaledTiledOffset(bool is_3d, uint3_xe p, uint pitch_aligned,''',
     '''// for simplicity, especially of the division involved, assuming everything is
// unsigned.
''' + R_FUNCTION + '''uint XeTextureScaledTiledOffset(bool is_3d, uint3_xe p, uint pitch_aligned,'''),
    ('texture_address.xesli',
     '''// Offset of the beginning of next host sub-unit along the horizontal axis
// within a pair of guest units.''',
     '''#endif  // XE_RESOLUTION_SCALE_3_2

#ifndef XE_RESOLUTION_SCALE_3_2
// Offset of the beginning of next host sub-unit along the horizontal axis
// within a pair of guest units.'''),
    ('texture_address.xesli',
     '''  // The layout of sub-units within one unit is column-major.
  return right_sub_unit_offset_columns * scale.y;
}
''',
     '''  // The layout of sub-units within one unit is column-major.
  return right_sub_unit_offset_columns * scale.y;
}
#endif  // !XE_RESOLUTION_SCALE_3_2
'''),
    ('edram.xesli',
     '''  uint2_xe tile_size_at_32bpp = uint2_xe(80u, 16u) * resolution_scale;
''',
     '''  #ifdef XE_RESOLUTION_SCALE_3_2
    // G6-P89 (test only): 80x16 x 3/2.
    uint2_xe tile_size_at_32bpp = uint2_xe(120u, 24u);
  #else
    uint2_xe tile_size_at_32bpp = uint2_xe(80u, 16u) * resolution_scale;
  #endif
'''),
    ('resolve.xesli',
     '''  #ifdef XE_RESOLVE_RESOLUTION_SCALED
    resolve_info.resolution_scale =
        (uint_x2_xe(coordinate_info) >> uint2_xe(16u, 19u)) & 7u;''',
     '''  #if defined(XE_RESOLVE_RESOLUTION_SCALED) && defined(XE_RESOLUTION_SCALE_3_2)
    // G6-P89 (test only): 3:2. The integer scale fields are 0 and not read; the half-pixel offset is 0.75 host
    // pixel, which leaves one host column / row uncovered, so the fill source is 1.
    resolve_info.resolution_scale = uint_x2_xe(0u);
    resolve_info.half_pixel_offset_fill_source =
        uint_x2_xe((edram_info & (1u << 29u)) != 0u ? 1u : 0u);
  #elif defined(XE_RESOLVE_RESOLUTION_SCALED)
    resolve_info.resolution_scale =
        (uint_x2_xe(coordinate_info) >> uint2_xe(16u, 19u)) & 7u;'''),
    ('resolve.xesli',
     '''  resolve_info.edram_offset_scaled =
      (((uint_x2_xe(coordinate_info) >> uint2_xe(0u, 4u)) &
        ((uint_x2_xe(1u) << uint2_xe(4u, 1u)) - 1u)) <<
       3u) *
      resolve_info.resolution_scale;
  resolve_info.width_div_8_scaled =
      ((coordinate_info >> 5u) & ((1u << 11u) - 1u)) *
      resolve_info.resolution_scale.x;
''',
     '''  #ifdef XE_RESOLUTION_SCALE_3_2
    // G6-P89 (test only): x 3/2, exact (offsets are multiples of 8, widths of 16 guest pixels).
    resolve_info.edram_offset_scaled =
        ((((uint_x2_xe(coordinate_info) >> uint2_xe(0u, 4u)) &
           ((uint_x2_xe(1u) << uint2_xe(4u, 1u)) - 1u)) <<
          3u) *
         3u) >> 1u;
    resolve_info.width_div_8_scaled =
        (((coordinate_info >> 5u) & ((1u << 11u) - 1u)) * 3u) >> 1u;
  #else
  resolve_info.edram_offset_scaled =
      (((uint_x2_xe(coordinate_info) >> uint2_xe(0u, 4u)) &
        ((uint_x2_xe(1u) << uint2_xe(4u, 1u)) - 1u)) <<
       3u) *
      resolve_info.resolution_scale;
  resolve_info.width_div_8_scaled =
      ((coordinate_info >> 5u) & ((1u << 11u) - 1u)) *
      resolve_info.resolution_scale.x;
  #endif
'''),
    ('resolve.xesli',
     '''    resolve_info.dest_xy_offset_scaled =
        (((uint_x2_xe(dest_coordinate_info) >> uint2_xe(20u, 24u)) &
          ((1u << 4u) - 1u)) <<
         3u) *
        resolve_info.resolution_scale;
''',
     '''    #ifdef XE_RESOLUTION_SCALE_3_2
      // G6-P89 (test only): x 3/2, exact (multiples of 8 guest pixels).
      resolve_info.dest_xy_offset_scaled =
          ((((uint_x2_xe(dest_coordinate_info) >> uint2_xe(20u, 24u)) &
             ((1u << 4u) - 1u)) <<
            3u) *
           3u) >> 1u;
    #else
    resolve_info.dest_xy_offset_scaled =
        (((uint_x2_xe(dest_coordinate_info) >> uint2_xe(20u, 24u)) &
          ((1u << 4u) - 1u)) <<
         3u) *
        resolve_info.resolution_scale;
    #endif
'''),
    ('resolve.xesli',
     '''  // Offset of the beginning of the odd R32G32/R32G32B32A32 store address from
  // the address of the even store.
  uint XeResolveDestRightConsecutiveBlocksOffset(uint x, uint bpp_log2,''',
     '''  #ifndef XE_RESOLUTION_SCALE_3_2
  // Offset of the beginning of the odd R32G32/R32G32B32A32 store address from
  // the address of the even store.
  uint XeResolveDestRightConsecutiveBlocksOffset(uint x, uint bpp_log2,'''),
    ('resolve.xesli',
     '''      return XeTextureTiledOddConsecutiveBlocksOffset(bpp_log2);
    #endif
  }
''',
     '''      return XeTextureTiledOddConsecutiveBlocksOffset(bpp_log2);
    #endif
  }
  #endif  // !XE_RESOLUTION_SCALE_3_2
'''),
    ('resolve_fast_32bpp_1x2xmsaa.xesli',
     '''#define LOCAL_SIZE_X_XE 8
#define LOCAL_SIZE_Y_XE 8
''',
     '''#define LOCAL_SIZE_X_XE 8
#ifdef XE_RESOLUTION_SCALE_3_2
  // G6-P92 (test only): 8x4 threads = 64x4 host pixels. A guest resolve
  // height is a multiple of 8 pixels, i.e. of 12 host rows at 3:2 - a
  // multiple of 4 but not always of 8 - and there is no Y bound below, so the
  // group height must divide 12 (GetCopyShader dispatches 4-row groups).
  #define LOCAL_SIZE_Y_XE 4
#else
#define LOCAL_SIZE_Y_XE 8
#endif
'''),
    ('resolve_fast_32bpp_1x2xmsaa.xesli',
     '''  uint4_xe pixels_4567 =
      array_buffer_load_xe(xe_resolve_edram, source_address_int4s + 1u);
''',
     '''  #ifdef XE_RESOLUTION_SCALE_3_2
    // G6-P89 (test only): at 3:2 an 8-pixel run can cross the 60-sample depth
    // half-tile swap (or a 120-sample tile edge with an offset); a 4-pixel run
    // cannot, so the second load is addressed on its own.
    uint source_address_4567_int4s =
        XeEdramOffsetInts(
            uint2_xe(pixel_index.x + 4u,
                     max(pixel_index.y,
                         resolve_info.half_pixel_offset_fill_source.y)) +
                resolve_info.edram_offset_scaled,
            resolve_info.edram_base_tiles, true, resolve_info.edram_pitch_tiles,
            resolve_info.edram_msaa_samples, resolve_info.edram_is_depth, 0u,
            XeResolveFirstSampleIndex(resolve_info.sample_select),
            resolve_info.resolution_scale)
        >> 2u;
    uint4_xe pixels_4567 =
        array_buffer_load_xe(xe_resolve_edram, source_address_4567_int4s);
  #else
  uint4_xe pixels_4567 =
      array_buffer_load_xe(xe_resolve_edram, source_address_int4s + 1u);
  #endif
'''),
    ('resolve_fast_32bpp_1x2xmsaa.xesli',
     '''  dest_address += XeResolveDestRightConsecutiveBlocksOffset(
                      pixel_index.x, 2u, resolve_info.resolution_scale) >> 4u;
''',
     '''  #ifdef XE_RESOLUTION_SCALE_3_2
    // G6-P89 (test only): the next 4x1 sub-unit may be in the next 3:2 group.
    dest_address =
        XeResolveDestPixelAddress(resolve_info, pixel_index + uint2_xe(4u, 0u),
                                  2u) >> 4u;
  #else
  dest_address += XeResolveDestRightConsecutiveBlocksOffset(
                      pixel_index.x, 2u, resolve_info.resolution_scale) >> 4u;
  #endif
'''),
    ('texture_load.xesli',
     '''// Offset of the beginning of the odd R32G32/R32G32B32A32 load address from the
// address of the even load, for power-of-two-sized textures.
uint XeTextureLoadRightConsecutiveBlocksOffset(XeTextureLoadInfo load_info,''',
     '''#ifndef XE_RESOLUTION_SCALE_3_2
// Offset of the beginning of the odd R32G32/R32G32B32A32 load address from the
// address of the even load, for power-of-two-sized textures.
uint XeTextureLoadRightConsecutiveBlocksOffset(XeTextureLoadInfo load_info,'''),
    ('texture_load.xesli',
     '''      offset = 1u << (consecutive_blocks_log2 + bpb_log2);
    }
    return offset;
  #endif
}
''',
     '''      offset = 1u << (consecutive_blocks_log2 + bpb_log2);
    }
    return offset;
  #endif
}
#endif  // !XE_RESOLUTION_SCALE_3_2
'''),
    ('texture_load_32bpb.xesli',
     '''  block_offset_guest +=
      XeTextureLoadRightConsecutiveBlocksOffset(load_info, block_index.x, 2u) >>
      4u;
''',
     '''  #ifdef XE_RESOLUTION_SCALE_3_2
    // G6-P89 (test only): the next 4x1 sub-unit may be in the next 3:2 group.
    block_offset_guest =
        XeTextureLoadGuestBlockOffset(load_info,
                                      block_index + uint3_xe(4u, 0u, 0u), 4u,
                                      2u) >> 4u;
  #else
  block_offset_guest +=
      XeTextureLoadRightConsecutiveBlocksOffset(load_info, block_index.x, 2u) >>
      4u;
  #endif
'''),
]

NEW_FILES = {
    'resolve_fast_32bpp_1x2xmsaa_scaled32.cs.xesl': LICENSE_HEADER + '''#define XE_RESOLVE_RESOLUTION_SCALED
#define XE_RESOLUTION_SCALE_3_2
#include "resolve_fast_32bpp_1x2xmsaa.xesli"
''',
    'texture_load_32bpb_scaled32.cs.xesl': LICENSE_HEADER + '''#define XE_TEXTURE_LOAD_RESOLUTION_SCALED
#define XE_RESOLUTION_SCALE_3_2
#define XE_TEXTURE_LOAD_32BPB_TRANSFORM(blocks) (blocks)
#include "texture_load_32bpb.xesli"
''',
    'texture_load_depth_unorm_scaled32.cs.xesl': LICENSE_HEADER + '''#define XE_TEXTURE_LOAD_RESOLUTION_SCALED
#define XE_RESOLUTION_SCALE_3_2
#include "pixel_formats.xesli"
#define XE_TEXTURE_LOAD_32BPB_TRANSFORM(blocks) \\
  (float_bits_to_uint_xe(XeUNorm24To32((blocks) >> 8u)))
#include "texture_load_32bpb.xesli"
''',
}


def load_manifest():
    import importlib
    import g6p89_shader_manifest
    return importlib.reload(g6p89_shader_manifest).MANIFEST


def sha256_file(path):
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


def apply_edits(shader_dir):
    """Apply EDITS / NEW_FILES to a copied shader directory. Returns the edit count per file."""
    counts = {}
    for name, digest in PRISTINE.items():
        got = sha256_file(os.path.join(shader_dir, name))
        if got != digest:
            raise SystemExit(f'pinned source mismatch: {name} {got}')
    for name, old, new in EDITS:
        path = os.path.join(shader_dir, name)
        with open(path, 'rb') as f:
            raw = f.read().decode('utf-8')
        nl = '\r\n' if '\r\n' in raw else '\n'
        text = raw.replace('\r\n', '\n')
        if text.count(old) != 1:
            raise SystemExit(f'edit anchor count {text.count(old)} in {name}: {old[:60]!r}')
        text = text.replace(old, new)
        with open(path, 'wb') as f:
            f.write(text.replace('\n', nl).encode('utf-8'))
        counts[name] = counts.get(name, 0) + 1
    for name, text in NEW_FILES.items():
        with open(os.path.join(shader_dir, name), 'wb') as f:
            f.write(text.replace('\n', '\r\n').encode('utf-8'))
    return counts


def check_fxc(fxc):
    ident = g87.fxc_identity(fxc)
    if ident.get('sha256') != FXC_SHA256 or ident.get('d3dcompiler_47_sha256') != D3DCOMPILER_SHA256:
        raise SystemExit(f'FXC identity mismatch: {ident}')
    return ident


def build(src, sdk, fxc, work, full_check=True):
    src, sdk, work = os.path.abspath(src), os.path.abspath(sdk), os.path.abspath(work)
    ident = check_fxc(fxc)
    if os.path.exists(work):
        shutil.rmtree(work)
    tree = os.path.join(work, 'src')
    for sub in (os.path.join('src', 'xenia', 'gpu', 'shaders'), os.path.join('src', 'xenia', 'ui', 'shaders')):
        shutil.copytree(os.path.join(src, sub), os.path.join(tree, sub),
                        ignore=shutil.ignore_patterns('bytecode'))
    shader_dir = os.path.join(tree, g87.SHADER_REL)
    counts = apply_edits(shader_dir)
    out_dir = os.path.join(work, 'out')
    os.makedirs(out_dir)
    variants = []
    for ident_name in VARIANTS:
        src_name = ident_name[:-3] + '.cs.xesl'
        out_h = os.path.join(out_dir, ident_name + '.h')
        rc, err = g87.compile_one(fxc, os.path.join(shader_dir, src_name), out_h, ident_name)
        if rc != 0 or not os.path.exists(out_h):
            raise SystemExit(f'FXC failed for {src_name}: {err}')
        with open(out_h, encoding='utf-8', errors='replace') as f:
            listing, data, array_id = g87.parse_header(f.read())
        variants.append({'header': ident_name + '.h', 'source': src_name, 'array': array_id,
                         'dxbc_sha256': g87.sha256(data), 'dxbc_bytes': len(data),
                         'instructions': len(g87.listing_instructions(listing)),
                         'warnings': err[:500] if err else ''})
    result = {'source_revision': SOURCE_REVISION, 'fxc': {k: ident[k] for k in ('sha256', 'd3dcompiler_47_sha256')
                                                          if k in ident},
              'command_template': 'fxc /D SHADING_LANGUAGE_HLSL_XE=1 /Fh <id>.h /T cs_5_1 /Vn <id> /nologo <src>',
              'edits_per_file': counts, 'new_files': sorted(NEW_FILES), 'variants': variants}
    if full_check:
        # Every existing SDK shader rebuilt from the edited tree must equal the SDK bytes (the switch is off there).
        full = g87.build(tree, sdk, fxc, os.path.join(work, 'existing'), True)
        # G6-P92: after a replay the SDK also holds the installed 3:2 variants (from an earlier manifest); they are
        # this build's outputs, not existing SDK shaders, so they are excluded from the unchanged-shader count.
        ours = {v + '.h' for v in VARIANTS}
        existing = [r for r in full['results'] if r['header'] not in ours]
        result['existing_unchanged'] = {'L1': sum(1 for r in existing if r.get('L1_compiled')),
                                        'L3': sum(1 for r in existing if r.get('L3_container_equal')),
                                        'baseline_L3': G87_BASELINE_L3,
                                        'scaled_L3': sum(1 for r in existing
                                                         if '_scaled' in r['header'] and r.get('L3_container_equal'))}
        if result['existing_unchanged']['L3'] != G87_BASELINE_L3:
            raise SystemExit(f'existing shaders changed: {result["existing_unchanged"]}')
    with open(os.path.join(work, 'build.json'), 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=1)
    return result


def install(out_dir, sdk, manifest):
    bc_dir = os.path.join(sdk, g87.SDK_BC_REL)
    expected = {v['header']: v['dxbc_sha256'] for v in manifest['variants']}
    changed = []
    for header, digest in expected.items():
        src_h = os.path.join(out_dir, header)
        with open(src_h, encoding='utf-8', errors='replace') as f:
            _, data, _ = g87.parse_header(f.read())
        if g87.sha256(data) != digest:
            raise SystemExit(f'{header}: DXBC {g87.sha256(data)} != manifest {digest}')
        dst = os.path.join(bc_dir, header)
        if not os.path.exists(dst) or sha256_file(dst) != sha256_file(src_h):
            shutil.copyfile(src_h, dst)
            changed.append(header)
    return changed


def ensure(src, sdk, fxc):
    manifest = load_manifest()
    out_dir = os.path.join(DEFAULT_OUT, 'out')
    ok = all(os.path.exists(os.path.join(out_dir, v['header'])) for v in manifest['variants'])
    if ok:
        for v in manifest['variants']:
            with open(os.path.join(out_dir, v['header']), encoding='utf-8', errors='replace') as f:
                ok = ok and g87.sha256(g87.parse_header(f.read())[1]) == v['dxbc_sha256']
    if not ok:
        res = build(src, sdk, fxc, DEFAULT_OUT, full_check=False)
        got = {v['header']: v['dxbc_sha256'] for v in res['variants']}
        want = {v['header']: v['dxbc_sha256'] for v in manifest['variants']}
        if got != want:
            raise SystemExit(f'rebuilt 3:2 shaders differ from the manifest: {got} != {want}')
    return install(out_dir, sdk, manifest)


def selftest():
    """Offline: edits apply exactly once to the pinned files, the switch appears only under #ifdef / new wrappers,
    and two clean builds give identical variants (when the pinned source and FXC are present)."""
    names = {e[0] for e in EDITS}
    assert names == set(PRISTINE), names
    for name, old, new in EDITS:
        assert old in new or 'XE_RESOLUTION_SCALE_3_2' in new, name
    for name, text in NEW_FILES.items():
        assert '#define XE_RESOLUTION_SCALE_3_2' in text and name.endswith('_scaled32.cs.xesl')
    assert [n[:-len('.cs.xesl')] + '_cs' for n in sorted(NEW_FILES)] == sorted(VARIANTS)
    if not (os.path.isdir(DEFAULT_SRC) and os.path.exists(DEFAULT_FXC)):
        print('g6p89_shader_build selftest: static checks PASS (pinned source or FXC absent; no build)')
        return
    with tempfile.TemporaryDirectory() as tmp:
        a = build(DEFAULT_SRC, DEFAULT_SDK, DEFAULT_FXC, os.path.join(tmp, 'a'), full_check=False)
        b = build(DEFAULT_SRC, DEFAULT_SDK, DEFAULT_FXC, os.path.join(tmp, 'b'), full_check=False)
        assert [v['dxbc_sha256'] for v in a['variants']] == [v['dxbc_sha256'] for v in b['variants']]
        if os.path.exists(MANIFEST):
            want = [v['dxbc_sha256'] for v in load_manifest()['variants']]
            assert [v['dxbc_sha256'] for v in a['variants']] == want, 'manifest drift'
    print('g6p89_shader_build selftest: PASS (edits exact, two clean builds identical, manifest equal)')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['build', 'ensure', 'selftest'])
    ap.add_argument('--src', default=DEFAULT_SRC)
    ap.add_argument('--sdk', default=DEFAULT_SDK)
    ap.add_argument('--fxc', default=DEFAULT_FXC)
    ap.add_argument('--work', default=DEFAULT_OUT)
    ap.add_argument('--write-manifest', action='store_true')
    a = ap.parse_args()
    if a.cmd == 'build':
        res = build(a.src, a.sdk, a.fxc, a.work)
        if a.write_manifest:
            data = {k: res[k] for k in ('source_revision', 'fxc', 'command_template', 'edits_per_file',
                                        'new_files', 'variants', 'existing_unchanged')}
            with open(MANIFEST, 'w', encoding='utf-8', newline='\n') as f:
                f.write(MANIFEST_HEAD + repr(data) + '\n')
        print(json.dumps({'variants': res['variants'], 'existing_unchanged': res.get('existing_unchanged')},
                         indent=1))
    elif a.cmd == 'ensure':
        changed = ensure(a.src, a.sdk, a.fxc)
        print('g6p89 shaders installed:', ', '.join(changed) if changed else 'unchanged')
    else:
        selftest()


if __name__ == '__main__':
    main()
