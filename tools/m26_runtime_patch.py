"""Replay after the M24 patch at the same pin: optional texture orientation correction (M26, D-058).

`tools/m26_texture_orient.h`: with R3HD_TEXTURE_ORIENT=corrected, a host read of a listed bundle file
(`fact_55_2.btf`) returns the four listed atlas pages (`fac_sbire01..04`, the Robo-Pirate statues of `fact_55`)
mirrored top to bottom, base level and mip chain, exactly (block rows and the rows inside each DXT5 block; no
decode). The title's bundles store pages bottom row first and its meshes count on that; these four are stored
top row first in the Xbox 360 HD release, so every statue part samples the mirror cell (RE_NOTES "M26").
Without the variable nothing changes: the read returns the file's bytes, and the cost is one flag test per read.

One site: HostPathFile::ReadSync, after a successful host read. A page is corrected only when the file has the
listed size and the page's bytes have the listed hash before and after; otherwise the read is returned as it is
and one `M26 texture_orient ... state=refused_*` line says why. Host-only: no generated code, no guest patch, no
file written, no texel of the title in the repository.
"""
from m8_runtime_patch import patch_once
from m16_runtime_patch import install

if __name__ == '__main__':
    install('m26_texture_orient.h')

    # host_path_file.cpp is rebuilt from the pin by m20_runtime_patch.py on every replay.
    patch_once('src/filesystem/devices/host_path_file.cpp', [
        ('#include <rex/m20_save_commit.h>\n',
         '#include <rex/m20_save_commit.h>\n#include <rex/logging.h>\n#include <rex/m26_texture_orient.h>\n'),
        ('namespace rex::filesystem {\n\nHostPathFile::HostPathFile(',
         'namespace rex::filesystem {\n\n'
         '// M26 (D-058): optional texture orientation correction, see tools/m26_texture_orient.h.\n'
         'static void M26Log(const char* line) {\n'
         '  REXLOG_INFO("{}", line);\n'
         '}\n\n'
         'HostPathFile::HostPathFile('),
        ('  if (file_handle_->Read(byte_offset, buffer.data(), buffer.size(), out_bytes_read)) {\n'
         '    return X_STATUS_SUCCESS;\n',
         '  if (file_handle_->Read(byte_offset, buffer.data(), buffer.size(), out_bytes_read)) {\n'
         '    // M26 (D-058): off unless R3HD_TEXTURE_ORIENT=corrected; listed pages of listed bundle files only.\n'
         '    if (m26tex::Enabled()) {\n'
         '      m26tex::state().log = &M26Log;\n'
         '      m26tex::AfterRead(static_cast<HostPathEntry*>(entry())->host_path(), byte_offset, buffer.data(),\n'
         '                        out_bytes_read ? *out_bytes_read : buffer.size());\n'
         '    }\n'
         '    return X_STATUS_SUCCESS;\n'),
    ])

    patch_once('src/graphics/d3d12/command_processor.cpp', [
        ('#include <rex/m23_water_layers.h>\n', '#include <rex/m23_water_layers.h>\n#include <rex/m26_texture_orient.h>\n'),
        # In front of the M23 line: the M23 patch must still find its own two lines together on a replay.
        ('  REXGPU_INFO("M23 layer_coords={}", m23water::Enabled() ? "separate" : "original");\n',
         '  REXGPU_INFO("M26 texture_orient={}", m26tex::Enabled() ? "corrected" : "original");\n'
         '  REXGPU_INFO("M23 layer_coords={}", m23water::Enabled() ? "separate" : "original");\n'),
    ])
