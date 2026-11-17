"""Replay last in the patch chain: HD+ power-up beam colour restoration as a verified read overlay (D-219).

`tools/r3hd_beam_color.h`: with R3HD_BEAM_COLOR=restored a host read of one of the 39 listed level bundles returns
the `trans_ray` / `trans_colonne` pages with the inverse of the HD release's channel rotation applied to their DXT1
endpoints, gated by file size and the stored and restored page hashes. Without the variable nothing changes.

One site: HostPathFile::ReadSync, after the M26 correction and before the M33 mod overlay, so a data-only mod that
replaces either page still wins. Inserted between those two existing blocks and run after every other step, so no
earlier step's anchor moves. One start-up mode line beside the others (D3D12). Host-only: no generated code, no guest
patch, no file written.
"""
from m8_runtime_patch import patch_once
from m16_runtime_patch import install

if __name__ == '__main__':
    install('r3hd_beam_color.h')

    patch_once('src/filesystem/devices/host_path_file.cpp', [
        ('#include <rex/m33_mod_overlay.h>\n',
         '#include <rex/m33_mod_overlay.h>\n#include <rex/r3hd_beam_color.h>\n'),
        ('    // M33 (D-070): off unless R3HD_MODS_PLAN names a verified plan; listed ranges of listed files only.\n',
         '    // D-219: HD+ beam colours, off unless R3HD_BEAM_COLOR=restored; two pages of listed bundles only.\n'
         '    // Before M33 so that a mod replacing either page wins.\n'
         '    if (r3hdbeam::Enabled()) {\n'
         '      r3hdbeam::state().log = &M26Log;\n'
         '      r3hdbeam::AfterRead(static_cast<HostPathEntry*>(entry())->host_path(), byte_offset, buffer.data(),\n'
         '                          out_bytes_read ? *out_bytes_read : buffer.size());\n'
         '    }\n'
         '    // M33 (D-070): off unless R3HD_MODS_PLAN names a verified plan; listed ranges of listed files only.\n'),
    ])

    patch_once('src/graphics/d3d12/command_processor.cpp', [
        ('#include <rex/m33_mod_overlay.h>\n', '#include <rex/m33_mod_overlay.h>\n#include <rex/r3hd_beam_color.h>\n'),
        ('  // M15: the scale in effect after the configuration and device clamps.\n',
         '  // M15: the scale in effect after the configuration and device clamps.\n'
         '  REXGPU_INFO("R3HD beam_color={}", r3hdbeam::Enabled() ? "restored" : "original");\n'),
    ])
