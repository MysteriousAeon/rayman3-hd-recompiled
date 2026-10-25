"""Replay after the M44 patch at the same pin: the DXBC container hash without AMD's DXBCChecksum (M45, D-083).

The pinned SDK hashes every DXBC container it builds (shader translator, pipeline cache, render-target cache: four
call sites) with thirdparty/dxbc/DXBCChecksum.cpp, whose AMD notice grants no licence (release blocker L-5,
reports/milestone42). This script

  * installs tools/m45_dxbc_hash.h as include/rex/m45_dxbc_hash.h (derived from Microsoft DirectXShaderCompiler's
    DxilHash.cpp ComputeHashRetail, University of Illinois/NCSA licence; byte-equal to the AMD routine over the M45
    differential corpus, reports/milestone45);
  * replaces the include and the call at the four call sites (same arguments, same 16 bytes at container offset 4);
  * drops DXBCChecksum.cpp and its include directory from src/graphics/CMakeLists.txt and corrects the dxbc.h
    comments that named it;
  * deletes thirdparty/dxbc/DXBCChecksum.cpp / .h from the SDK working tree, so nothing can build against them.

Host-only: no generated code, no guest patch. Files keep their own line endings (bytes in, bytes out).
"""
from m3_runtime_patch import SDK
from m16_runtime_patch import install


def patch_bytes(rel, edits):
    path = SDK / rel
    data = path.read_bytes()
    nl = b'\r\n' if b'\r\n' in data else b'\n'
    text = data.replace(b'\r\n', b'\n')
    for before, after in edits:
        before, after = before.encode(), after.encode()
        if after in text and before not in text:
            continue
        assert text.count(before) == 1, (rel, before[:60], text.count(before))
        text = text.replace(before, after)
    out = text.replace(b'\n', nl)
    if out != data:
        path.write_bytes(out)
        print('patched', rel)


INCLUDE = ('#include "thirdparty/dxbc/DXBCChecksum.h"\n',
           '#include <rex/m45_dxbc_hash.h>  // M45 (D-083): replaces AMD DXBCChecksum\n')


def call(buf, size):
    return ('    CalculateDXBCChecksum(reinterpret_cast<unsigned char*>(%s.data()),\n'
            '                          static_cast<unsigned int>(%s),\n'
            '                          reinterpret_cast<unsigned int*>(&container_header.hash));\n' % (buf, size),
            '    m45dxbc::ContainerHash(%s.data(), static_cast<uint32_t>(%s), container_header.hash);\n'
            % (buf, size))


if __name__ == '__main__':
    install('m45_dxbc_hash.h')
    patch_bytes('src/graphics/pipeline/shader/dxbc_translator.cpp',
                [INCLUDE, call('shader_object_', 'shader_object_size_bytes')])
    patch_bytes('src/graphics/d3d12/pipeline_cache.cpp', [INCLUDE, call('shader_out', 'shader_size_bytes')])
    path = SDK / 'src/graphics/d3d12/render_target_cache.cpp'
    # Two identical call sites in this file: replace both.
    data = path.read_bytes()
    nl = b'\r\n' if b'\r\n' in data else b'\n'
    text = data.replace(b'\r\n', b'\n')
    old, new = (s.encode() for s in call('built_shader_', 'built_shader_size_bytes'))
    inc_old, inc_new = (s.encode() for s in INCLUDE)
    assert text.count(old) in (0, 2) and text.count(inc_old) + text.count(inc_new) == 1
    text = text.replace(old, new).replace(inc_old, inc_new)
    assert text.count(new) == 2
    if text.replace(b'\n', nl) != data:
        path.write_bytes(text.replace(b'\n', nl))
        print('patched', 'src/graphics/d3d12/render_target_cache.cpp')
    patch_bytes('src/graphics/CMakeLists.txt', [
        ('    # DXBC third-party dependency\n'
         '    set(REXGPU_XENOS_DXBC_THIRDPARTY_SOURCES\n'
         '        ${REXGLUE_ROOT}/thirdparty/dxbc/DXBCChecksum.cpp\n'
         '    )\n',
         '    # M45 (D-083): no DXBC third-party source; the container hash is include/rex/m45_dxbc_hash.h.\n'
         '    set(REXGPU_XENOS_DXBC_THIRDPARTY_SOURCES)\n'),
        ('    ${REXGLUE_ROOT}/thirdparty/renderdoc\n'
         '    ${REXGLUE_ROOT}  # For thirdparty/dxbc/DXBCChecksum.h include\n',
         '    ${REXGLUE_ROOT}/thirdparty/renderdoc\n'),
    ])
    patch_bytes('include/rex/graphics/format/dxbc.h', [
        ('//   - DXBCChecksum from GPUOpen-Archive/common-src-ShaderUtils\n',
         '//   - ComputeHashRetail from Microsoft DirectXShaderCompiler lib/DxilHash/DxilHash.cpp\n'
         '//     (rex/m45_dxbc_hash.h, M45)\n'),
        ('  // Of the entire DXBC container including this header, with this set to 0\n'
         '  // before hashing. Calculate using CalculateDXBCChecksum from\n'
         '  // GPUOpen-Archive/common-src-ShaderUtils.\n',
         '  // Of the DXBC container from version_major (offset 20) to its end; the\n'
         '  // magic and this field are not hashed. Calculate using\n'
         '  // m45dxbc::ContainerHash (rex/m45_dxbc_hash.h, M45).\n'),
    ])
    for name in ('DXBCChecksum.cpp', 'DXBCChecksum.h'):
        p = SDK / 'thirdparty/dxbc' / name
        if p.exists():
            p.unlink()
            print('removed', 'thirdparty/dxbc/' + name)
